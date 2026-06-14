"""
=============================================================
AGENTE v16 - Bridge FastAPI para la interfaz web
=============================================================
Expone el agente ReAct completo (tools, memory, streaming)
como API REST para la interfaz Next.js.

Endpoints:
- GET  /api/status     - Estado del sistema
- GET  /api/models     - Modelos disponibles
- GET  /api/tools      - Lista de herramientas
- GET  /api/memory     - Stats de memoria
- POST /api/memory/save - Guardar sesion
- POST /api/memory/clear - Limpiar sesion
- GET  /api/config     - Configuracion actual
- POST /api/execute    - Ejecutar una herramienta directamente
- POST /api/chat       - Chat completo con streaming SSE
- POST /api/chat/simple - Chat directo con Ollama
- POST /api/upload     - Subir archivos
- GET  /api/history    - Historial de conversacion
- GET  /api/health     - Health check

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
import shutil
import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional, List

# Agregar directorio del agente al path
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# --- Importar agente ---
try:
    from agent import ReactAgent
    from memory.triple_memory import TripleMemory
    from llm import ollama
    from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
    AGENT_AVAILABLE = True
except Exception as e:
    print(f"[WARN] No se pudo importar el agente: {e}")
    AGENT_AVAILABLE = False

# --- App ---
app = FastAPI(
    title="ZAI Agent Bridge API",
    version="16.5.0",
    description="API completa para el Agente Autonomo v16 - con autenticacion opcional",
)

# --- Configuracion de seguridad ---
_BRIDGE_TOKEN = os.environ.get("BRIDGE_TOKEN", "")  # Token vacio = modo local (sin auth)
_ALLOWED_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
_AUTH_ENABLED = bool(_BRIDGE_TOKEN)  # Solo autenticar si se configuro un token

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Solo metodos necesarios
    allow_headers=["Authorization", "Content-Type", "Accept"],  # Solo headers necesarios
)


@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    """Rate limiting por IP: max _rate_limit_max requests por _rate_limit_window segundos."""
    # Skip rate limit for health checks and OPTIONS
    if request.url.path == "/api/health" or request.method == "OPTIONS":
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    err = _check_rate_limit(client_ip)
    if err:
        return JSONResponse(
            status_code=429,
            content={"detail": err},
            headers={"Retry-After": str(_rate_limit_window)},
        )
    return await call_next(request)

# --- Seguridad Bearer Token ---
_bearer_scheme = HTTPBearer(auto_error=False)

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(_bearer_scheme)):
    """Verifica el token Bearer si la autenticacion esta habilitada.
    
    Si BRIDGE_TOKEN no esta configurado (modo local), permite todo.
    Si BRIDGE_TOKEN esta configurado, requiere token valido.
    """
    if not _AUTH_ENABLED:
        return True  # Modo local: sin autenticacion
    if credentials is None:
        raise HTTPException(status_code=401, detail="Token de autenticacion requerido")
    if credentials.credentials != _BRIDGE_TOKEN:
        raise HTTPException(status_code=403, detail="Token invalido")
    return True

# --- Rate Limiting ---
_rate_limit_window = 60  # segundos
_rate_limit_max = 30  # max requests por IP por ventana
_rate_limits: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()


def _check_rate_limit(client_ip: str) -> Optional[str]:
    """Verifica rate limit por IP. Retorna mensaje de error si excedido, None si OK."""
    now = time.time()
    with _rate_lock:
        # Limpiar requests fuera de ventana
        _rate_limits[client_ip] = [
            t for t in _rate_limits[client_ip]
            if now - t < _rate_limit_window
        ]
        if len(_rate_limits[client_ip]) >= _rate_limit_max:
            return f"Rate limit excedido. Max {_rate_limit_max} requests por {_rate_limit_window}s."
        _rate_limits[client_ip].append(now)
    return None


# --- Singleton del agente ---
_agent: Optional[ReactAgent] = None
_memory: Optional[TripleMemory] = None
_start_time = time.time()
_busy = False  # Flag: el agente esta procesando
_agent_lock = threading.Lock()  # Protege acceso a _agent, _memory, _busy
_upload_dir = os.path.join(os.path.expanduser("~"), ".ia-local", "uploads")
os.makedirs(_upload_dir, exist_ok=True)

# --- Production error handling ---
_PRODUCTION = os.environ.get("ENV", "development") == "production"


def get_agent() -> ReactAgent:
    """Obtiene o crea la instancia singleton del agente."""
    global _agent, _memory
    with _agent_lock:
        if _agent is None:
            if not AGENT_AVAILABLE:
                raise HTTPException(status_code=503, detail="Agente no disponible. Verifica que Ollama esté corriendo.")
            _memory = TripleMemory()
            _memory.load_session()  # Cargar sesión persistente
            _agent = ReactAgent(memory=_memory)
        return _agent


def get_memory() -> TripleMemory:
    """Obtiene la instancia de memoria."""
    global _memory
    with _agent_lock:
        if _memory is None:
            _memory = TripleMemory()
            _memory.load_session()
        return _memory


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
    token_stats: Optional[dict] = None
    deep_thinking_stats: Optional[dict] = None

class ExecuteRequest(BaseModel):
    tool: str
    params: dict = {}

class ModelSwitchRequest(BaseModel):
    model: str


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/api/health")
async def health():
    """Health check - rapido, nunca bloquea, no requiere auth."""
    # Diagnostico rapido: verificar que Ollama responde
    ollama_status = "unknown"
    if AGENT_AVAILABLE:
        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                ollama_status = "ok"
        except Exception:
            ollama_status = "unreachable"
    return {
        "status": "ok",
        "agent": AGENT_AVAILABLE,
        "ollama": ollama_status,
        "busy": _busy,
        "version": "16.5.0",
        "uptime": int(time.time() - _start_time),
        "auth_enabled": _AUTH_ENABLED,
        "memory_loaded": _memory is not None,
    }


@app.get("/api/status")
async def status(auth=Depends(verify_token)):
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

    # Tool count
    tool_count = len(TOOL_FUNCTIONS) if AGENT_AVAILABLE else 0

    return {
        "connected": ollama_ok,
        "agent_available": AGENT_AVAILABLE,
        "busy": _busy,
        "version": "16.5.0",
        "tools_count": tool_count,
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
        "active_model": ollama.model if AGENT_AVAILABLE else None,
    }


@app.get("/api/models")
async def models(auth=Depends(verify_token)):
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


@app.post("/api/models/switch")
async def switch_model(request: ModelSwitchRequest, auth=Depends(verify_token)):
    """Cambia el modelo activo."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    try:
        ollama.model = request.model
        if _agent:
            _agent._models_cache = None
        return {"status": "ok", "model": request.model}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error cambiando modelo: {e}")


@app.get("/api/tools")
async def tools(auth=Depends(verify_token)):
    """Lista de herramientas disponibles con sus schemas."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    schema_map = {}
    for s in TOOL_SCHEMAS:
        func = s.get("function", {})
        name = func.get("name", "")
        if name:
            schema_map[name] = {
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {}),
            }

    tools_list = []
    for name in sorted(TOOL_FUNCTIONS.keys()):
        schema = schema_map.get(name, {})
        tools_list.append({
            "name": name,
            "description": schema.get("description", ""),
            "parameters": schema.get("parameters", {}),
            "available": True,
        })

    return {
        "tools": tools_list,
        "count": len(tools_list),
    }


@app.get("/api/memory")
async def memory_stats(auth=Depends(verify_token)):
    """Estadisticas de la memoria del agente."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    mem = get_memory()
    stats = mem.get_stats()

    # Agregar token stats si hay agente
    token_info = None
    if _agent and hasattr(_agent, 'token_manager'):
        token_info = _agent.token_manager.stats()

    return {
        **stats,
        "token_stats": token_info,
    }


@app.post("/api/memory/save")
async def memory_save(auth=Depends(verify_token)):
    """Guarda la sesion de memoria."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    mem = get_memory()
    mem.save_session()
    return {"status": "ok", "message": "Sesion guardada"}


@app.post("/api/memory/clear")
async def memory_clear(auth=Depends(verify_token)):
    """Limpia la sesion de memoria."""
    global _agent
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    mem = get_memory()
    mem.clear_session()
    _agent = ReactAgent(memory=mem)
    return {"status": "ok", "message": "Sesion limpiada"}


@app.get("/api/config")
async def config(auth=Depends(verify_token)):
    """Configuracion actual del agente."""
    try:
        import config as cfg
        return {
            "deep_thinking_mode": cfg.DEEP_THINKING_MODE,
            "max_react_iterations": cfg.MAX_REACT_ITERATIONS,
            "max_conversation_memory": cfg.MAX_CONVERSATION_MEMORY,
            "use_streaming": cfg.USE_STREAMING,
            "use_hybrid_search": cfg.USE_HYBRID_SEARCH,
            "use_reranker": cfg.USE_RERANKER,
            "max_tool_output": cfg.MAX_TOOL_OUTPUT,
            "subagent_max_parallel": cfg.SUBAGENT_MAX_PARALLEL,
            "default_timeout": cfg.DEFAULT_TIMEOUT,
            "llm_timeout_small": cfg.LLM_TIMEOUT_SMALL,
            "llm_timeout_large": cfg.LLM_TIMEOUT_LARGE,
            "deep_thinking_min_complexity": cfg.DEEP_THINKING_MIN_COMPLEXITY,
            "web_search_cache_ttl": cfg.WEB_SEARCH_CACHE_TTL,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo config: {e}")


@app.post("/api/execute")
async def execute_tool(request: ExecuteRequest, auth=Depends(verify_token)):
    """Ejecuta una herramienta directamente."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    tool_name = request.tool
    params = request.params

    if tool_name not in TOOL_FUNCTIONS:
        raise HTTPException(status_code=404, detail=f"Herramienta '{tool_name}' no encontrada.")

    try:
        func = TOOL_FUNCTIONS[tool_name]

        # Resolver placeholders
        if "REPOS_DIR" in str(params):
            from config import REPOS_DIR
            for key, val in params.items():
                if isinstance(val, str):
                    params[key] = val.replace("REPOS_DIR", REPOS_DIR)

        # Ejecutar
        start_time = time.time()
        result = func(**params)
        elapsed = (time.time() - start_time) * 1000

        # Truncar resultado si es muy largo
        result_str = str(result)
        if len(result_str) > 5000:
            result_str = result_str[:5000] + "\n... [resultado truncado]"

        return {
            "tool": tool_name,
            "result": result_str,
            "elapsed_ms": round(elapsed, 1),
            "success": "ERROR" not in result_str,
        }

    except Exception as e:
        return {
            "tool": tool_name,
            "result": f"ERROR: {e}",
            "elapsed_ms": 0,
            "success": False,
        }


@app.post("/api/chat")
async def chat(request: ChatRequest, auth=Depends(verify_token)):
    """Chat con el agente completo. Streaming SSE por defecto."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    agent = get_agent()

    # Cambiar modelo si se especifica
    if request.model:
        ollama.model = request.model

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
        token_stats = None
        if hasattr(agent, 'token_manager'):
            token_stats = agent.token_manager.stats()
        return ChatResponse(
            response=response,
            thinking_log=thinking_log,
            tool_calls=[],
            meta_status=agent.metacognition.get_status() if hasattr(agent, 'metacognition') else {},
            token_stats=token_stats,
        )


@app.post("/api/chat/simple")
async def chat_simple(request: ChatRequest, auth=Depends(verify_token)):
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


@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...), auth=Depends(verify_token)):
    """Sube archivos para procesar con el agente."""
    uploaded = []
    for file in files:
        try:
            file_path = os.path.join(_upload_dir, file.filename)
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)
            uploaded.append({
                "name": file.filename,
                "path": file_path,
                "size": len(content),
                "type": file.content_type,
            })
        except Exception as e:
            uploaded.append({
                "name": file.filename,
                "error": str(e),
            })

    return {"files": uploaded, "count": len(uploaded)}


@app.get("/api/history")
async def history(limit: int = 50, auth=Depends(verify_token)):
    """Historial de conversacion."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    mem = get_memory()
    messages = mem.short_term[-limit:]

    return {
        "messages": [
            {
                "role": msg.get("role", ""),
                "content": msg.get("content", "")[:500],
                "timestamp": msg.get("timestamp", ""),
            }
            for msg in messages
        ],
        "count": len(messages),
    }





# ============================================================
# STREAMING HELPERS
# ============================================================

def _agent_runner(agent: ReactAgent, message: str, q: queue.Queue):
    """
    Corre agent.run_stream() en un thread separado.
    Pone cada evento en la queue para que el async generator lo consuma.
    """
    global _busy
    with _agent_lock:
        _busy = True
    try:
        for event in agent.run_stream(message):
            q.put(event)
        # Senal de fin
        q.put(None)
    except Exception as e:
        print(f"[ERROR] _agent_runner: {e}")
        traceback.print_exc()
        # Never expose raw JSON key names as error messages
        err_msg = str(e)
        if any(k in err_msg for k in ['pensamiento', 'accion', 'respuesta_final', 'params']):
            err_msg = "Error procesando respuesta del modelo"
        # In production, don't expose internal error details
        if _PRODUCTION and len(err_msg) > 200:
            err_msg = err_msg[:200] + "..."
        q.put({"type": "error", "data": err_msg})
        q.put(None)
    finally:
        with _agent_lock:
            _busy = False


async def _stream_agent_threaded(agent: ReactAgent, message: str):
    """
    Genera eventos SSE desde el agente ReAct SIN bloquear el event loop.
    Usa un thread separado para correr el generador sincrono.
    """
    q = queue.Queue()

    thread = threading.Thread(
        target=_agent_runner,
        args=(agent, message, q),
        daemon=True,
    )
    thread.start()

    try:
        while True:
            event = await asyncio.get_event_loop().run_in_executor(None, q.get)

            if event is None:
                break

            event_type = event.get("type", "")
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

            elif event_type == "thinking":
                # Evento de pensamiento profundo (deep thinking)
                thinking_info = {
                    "type": "thinking",
                    "data": {
                        "reasoning": event_data.get("reasoning", "") if isinstance(event_data, dict) else str(event_data),
                        "plan": event_data.get("plan", []) if isinstance(event_data, dict) else [],
                        "complexity": event_data.get("complexity", 0) if isinstance(event_data, dict) else 0,
                        "query_type": event_data.get("query_type", "") if isinstance(event_data, dict) else "",
                        "depth": event_data.get("depth", 0) if isinstance(event_data, dict) else 0,
                    }
                }
                yield f"data: {json.dumps(thinking_info, ensure_ascii=False)}\n\n"

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
                    "deep_thinking_stats": event.get("deep_thinking_stats", {}),
                    "token_stats": event.get("token_stats", {}),
                }
                yield f"data: {json.dumps(done_info, ensure_ascii=False)}\n\n"

            elif event_type == "error":
                yield f"data: {json.dumps({'type': 'error', 'data': str(event_data)}, ensure_ascii=False)}\n\n"

    except Exception as e:
        print(f"[ERROR] _stream_agent_threaded: {e}")
        traceback.print_exc()
        err_msg = "Stream error" if _PRODUCTION else f"Stream error: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'data': err_msg}, ensure_ascii=False)}\n\n"


# --- Main ---

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  ZAI Agent Bridge API v16.4")
    print("  Puerto: 8000")
    print("  Agente:", "DISPONIBLE" if AGENT_AVAILABLE else "NO DISPONIBLE")
    print("  Threading: ACTIVADO (no bloquea event loop)")
    print("  Endpoints: /api/status, /api/chat, /api/tools,")
    print("             /api/memory, /api/config, /api/execute,")
    print("             /api/upload, /api/history, /api/health")
    print("=" * 60)
    host = os.environ.get("BRIDGE_HOST", "127.0.0.1")  # Default: localhost only
    port = int(os.environ.get("BRIDGE_PORT", "8000"))
    print(f"  Auth: {'HABILITADA (token configurado)' if _AUTH_ENABLED else 'DESHABILITADA (modo local)'}")
    print(f"  Rate limit: {_rate_limit_max} req/{_rate_limit_window}s por IP")
    print(f"  Host: {host}:{port}")
    uvicorn.run(app, host=host, port=port)
