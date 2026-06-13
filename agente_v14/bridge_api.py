"""
=============================================================
AGENTE v14 - Bridge FastAPI para la interfaz web
=============================================================
Expone el agente ReAct completo (tools, memory, streaming)
como API REST para la interfaz Next.js.

Ejecutar: python bridge_api.py
Puerto: 8000
=============================================================
"""

import sys
import os
import json
import asyncio
import time
import queue
import threading
import traceback

# Agregar directorio del agente al path
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

# --- Importar agente ---
try:
    from agent import ReactAgent
    from memory.triple_memory import TripleMemory
    from llm import ollama
    AGENT_AVAILABLE = True
except Exception as e:
    print(f"[WARN] No se pudo importar el agente: {e}")
    AGENT_AVAILABLE = False

# --- App ---
app = FastAPI(title="ZAI Agent Bridge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Singleton del agente ---
_agent: Optional[ReactAgent] = None
_start_time = time.time()
_busy = False  # Flag: el agente esta procesando


def get_agent() -> ReactAgent:
    """Obtiene o crea la instancia singleton del agente."""
    global _agent
    if _agent is None:
        if not AGENT_AVAILABLE:
            raise HTTPException(status_code=503, detail="Agente no disponible. Verifica que Ollama esté corriendo.")
        memory = TripleMemory()
        _agent = ReactAgent(memory=memory)
    return _agent


# --- Models ---

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    stream: bool = True

class ChatResponse(BaseModel):
    response: str
    thinking_log: list
    tool_calls: list
    meta_status: dict


# --- Routes ---

@app.get("/api/status")
async def status():
    """Estado del sistema."""
    # Verificar Ollama
    ollama_ok = False
    models = []
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        data = json.loads(resp.read())
        models = data.get("models", [])
        ollama_ok = True
    except Exception:
        pass

    uptime = int(time.time() - _start_time)

    return {
        "connected": ollama_ok,
        "agent_available": AGENT_AVAILABLE,
        "busy": _busy,
        "models": [
            {
                "name": m.get("name", ""),
                "size": m.get("size", 0),
                "family": m.get("details", {}).get("family", ""),
                "parameter_size": m.get("details", {}).get("parameter_size", ""),
            }
            for m in models
        ],
        "modelCount": len(models),
        "uptime": uptime,
    }


@app.get("/api/models")
async def models():
    """Lista de modelos disponibles."""
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
        data = json.loads(resp.read())
        model_list = data.get("models", [])
        return {
            "models": [
                {
                    "name": m.get("name", ""),
                    "size": m.get("size", 0),
                    "family": m.get("details", {}).get("family", ""),
                    "parameter_size": m.get("details", {}).get("parameter_size", ""),
                    "quantization_level": m.get("details", {}).get("quantization_level", ""),
                }
                for m in model_list
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama no disponible: {e}")


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Chat con el agente completo. Streaming SSE por defecto."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    agent = get_agent()

    if request.stream:
        return StreamingResponse(
            _stream_agent_threaded(agent, request.message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    else:
        # Modo sin streaming - correr en thread para no bloquear
        loop = asyncio.get_event_loop()
        response, thinking_log = await loop.run_in_executor(None, agent.run, request.message)
        return ChatResponse(
            response=response,
            thinking_log=thinking_log,
            tool_calls=[],
            meta_status=agent.metacognition.get_status() if hasattr(agent, 'metacognition') else {},
        )


def _agent_runner(agent: ReactAgent, message: str, q: queue.Queue):
    """
    Corre agent.run_stream() en un thread separado.
    Pone cada evento en la queue para que el async generator lo consuma.
    Esto evita bloquear el event loop de FastAPI.
    """
    global _busy
    _busy = True
    try:
        for event in agent.run_stream(message):
            q.put(event)
        # Senal de fin
        q.put(None)
    except Exception as e:
        print(f"[ERROR] _agent_runner: {e}")
        traceback.print_exc()
        q.put({"type": "error", "data": str(e)})
        q.put(None)
    finally:
        _busy = False


async def _stream_agent_threaded(agent: ReactAgent, message: str):
    """
    Genera eventos SSE desde el agente ReAct SIN bloquear el event loop.
    Usa un thread separado para correr el generador sincrono.
    """
    q = queue.Queue()

    # Iniciar el generador sincrono en un thread
    thread = threading.Thread(
        target=_agent_runner,
        args=(agent, message, q),
        daemon=True,
    )
    thread.start()

    try:
        while True:
            # Esperar evento de la queue sin bloquear el event loop
            event = await asyncio.get_event_loop().run_in_executor(None, q.get)

            # None = fin del stream
            if event is None:
                break

            event_type = event.get("type", "text")
            event_data = event.get("data", "")

            if event_type == "text":
                yield f"data: {json.dumps({'type': 'text', 'data': event_data}, ensure_ascii=False)}\n\n"

            elif event_type == "tool_start":
                tool_info = {
                    "type": "tool_start",
                    "data": {
                        "name": event_data.get("name", "unknown") if isinstance(event_data, dict) else str(event_data),
                        "arguments": event_data.get("arguments", {}) if isinstance(event_data, dict) else {},
                    }
                }
                yield f"data: {json.dumps(tool_info, ensure_ascii=False)}\n\n"

            elif event_type == "tool_result":
                result_info = {
                    "type": "tool_result",
                    "data": {
                        "tool": event_data.get("tool", {}) if isinstance(event_data, dict) else {},
                        "result": str(event_data.get("result", ""))[:500] if isinstance(event_data, dict) else str(event_data)[:500],
                    }
                }
                yield f"data: {json.dumps(result_info, ensure_ascii=False)}\n\n"

            elif event_type == "meta":
                meta_info = {
                    "type": "meta",
                    "data": event_data,
                }
                yield f"data: {json.dumps(meta_info, ensure_ascii=False)}\n\n"

            elif event_type == "done":
                done_info = {
                    "type": "done",
                    "data": event_data if isinstance(event_data, str) else "",
                    "thinking_log": event.get("thinking_log", []),
                    "meta_status": event.get("meta_status", {}),
                }
                yield f"data: {json.dumps(done_info, ensure_ascii=False)}\n\n"

            elif event_type == "error":
                yield f"data: {json.dumps({'type': 'error', 'data': str(event_data)}, ensure_ascii=False)}\n\n"

    except Exception as e:
        print(f"[ERROR] _stream_agent_threaded: {e}")
        traceback.print_exc()
        yield f"data: {json.dumps({'type': 'error', 'data': f'Stream error: {str(e)}'}, ensure_ascii=False)}\n\n"


@app.post("/api/chat/simple")
async def chat_simple(request: ChatRequest):
    """Chat simple directo con Ollama, sin el agente ReAct."""
    try:
        import urllib.request
        payload = json.dumps({
            "model": request.model or "qwen3:4b",
            "messages": [{"role": "user", "content": request.message}],
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return {
                "response": result.get("message", {}).get("content", ""),
                "model": result.get("model", ""),
                "total_duration": result.get("total_duration", 0),
            }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama no disponible: {e}")


@app.get("/api/health")
async def health():
    """Health check - rapido, nunca bloquea."""
    return {"status": "ok", "agent": AGENT_AVAILABLE, "busy": _busy}


# --- Main ---

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  ZAI Agent Bridge API v2.0")
    print("  Puerto: 8000")
    print("  Agente:", "DISPONIBLE" if AGENT_AVAILABLE else "NO DISPONIBLE")
    print("  Threading: ACTIVADO (no bloquea event loop)")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
