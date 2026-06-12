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
            _stream_agent(agent, request.message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    else:
        # Modo sin streaming
        response, thinking_log = agent.run(request.message)
        return ChatResponse(
            response=response,
            thinking_log=thinking_log,
            tool_calls=[],
            meta_status=agent.metacognition.get_status() if hasattr(agent, 'metacognition') else {},
        )


async def _stream_agent(agent: ReactAgent, message: str):
    """Genera eventos SSE desde el agente ReAct con streaming."""
    try:
        for event in agent.run_stream(message):
            event_type = event.get("type", "text")
            event_data = event.get("data", "")

            if event_type == "text":
                # Token de texto - enviar como SSE
                yield f"data: {json.dumps({'type': 'text', 'data': event_data}, ensure_ascii=False)}\n\n"

            elif event_type == "tool_start":
                # Inicio de tool call
                tool_info = {
                    "type": "tool_start",
                    "data": {
                        "name": event_data.get("name", "unknown"),
                        "arguments": event_data.get("arguments", {}),
                    }
                }
                yield f"data: {json.dumps(tool_info, ensure_ascii=False)}\n\n"

            elif event_type == "tool_result":
                # Resultado de tool call
                result_info = {
                    "type": "tool_result",
                    "data": {
                        "tool": event_data.get("tool", {}),
                        "result": event_data.get("result", "")[:500],  # Limitar resultado
                    }
                }
                yield f"data: {json.dumps(result_info, ensure_ascii=False)}\n\n"

            elif event_type == "meta":
                # Metacognicion
                meta_info = {
                    "type": "meta",
                    "data": event_data,
                }
                yield f"data: {json.dumps(meta_info, ensure_ascii=False)}\n\n"

            elif event_type == "done":
                # Respuesta final
                done_info = {
                    "type": "done",
                    "data": event_data if isinstance(event_data, str) else "",
                    "thinking_log": event.get("thinking_log", []),
                    "meta_status": event.get("meta_status", {}),
                }
                yield f"data: {json.dumps(done_info, ensure_ascii=False)}\n\n"

            # Pequeña pausa para no saturar
            await asyncio.sleep(0.001)

    except Exception as e:
        error_msg = f"Error del agente: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'data': error_msg}, ensure_ascii=False)}\n\n"


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
    """Health check."""
    return {"status": "ok", "agent": AGENT_AVAILABLE}


# --- Main ---

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  ZAI Agent Bridge API")
    print("  Puerto: 8000")
    print("  Agente:", "DISPONIBLE" if AGENT_AVAILABLE else "NO DISPONIBLE")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
