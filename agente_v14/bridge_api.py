"""
=============================================================
AGENTE v16 - Bridge FastAPI para la interfaz web
=============================================================
Expone el agente ReAct completo (tools, memory, streaming)
como API REST para la interfaz Next.js.

Endpoints:
- GET  /api/system      - Recursos del sistema (CPU, RAM, Disco, GPU reales)
- GET  /api/status      - Estado del sistema
- GET  /api/models      - Modelos disponibles
- GET  /api/tools       - Lista de herramientas
- GET  /api/memory      - Stats de memoria
- POST /api/memory/save  - Guardar sesion
- POST /api/memory/clear - Limpiar sesion
- POST /api/reset       - Resetear contexto de conversacion
- GET  /api/version     - Informacion de version
- GET  /api/config      - Configuracion actual (non-sensitive)
- GET  /api/sessions    - Listar sesiones guardadas
- POST /api/execute     - Ejecutar una herramienta directamente
- POST /api/chat        - Chat completo con streaming SSE
- POST /api/chat/simple - Chat directo con Ollama
- POST /api/upload      - Subir archivos
- GET  /api/history     - Historial de conversacion
- GET  /api/health      - Health check

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

import logging
import signal
import uuid
import glob as glob_mod
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, List

# Agregar directorio del agente al path
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Security, Request
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
    version="17.0.0",
    description="API completa para el Agente Autonomo v17 - con autenticacion opcional, request tracking, y validacion",
)

# --- Configuracion de seguridad ---
_BRIDGE_TOKEN = os.environ.get("BRIDGE_TOKEN", "")  # Token vacio = modo local (sin auth)
_AUTH_ENABLED = bool(_BRIDGE_TOKEN)  # Solo autenticar si se configuro un token

# --- CORS from environment ---
# Default to secure local origins; override with CORS_ORIGINS env var (comma-separated)
_DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://localhost:3001"
_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Solo metodos necesarios
    allow_headers=["Authorization", "Content-Type", "Accept"],  # Solo headers necesarios
)

# --- Request validation constants ---
_MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB
# POST endpoints that accept multipart/form-data (upload)
_MULTIPART_PATHS = {"/api/upload"}

# --- Production error handling ---
_PRODUCTION = os.environ.get("ENV", "development") == "production"

# --- Logger for bridge ---
_bridge_logger = logging.getLogger("bridge_api")


# ============================================================
# REQUEST ID TRACKING MIDDLEWARE
# ============================================================

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Genera un UUID por request, lo agrega como X-Request-ID header y lo almacena en request.state."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    request.state.request_start = time.time()

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    return response


# ============================================================
# REQUEST VALIDATION MIDDLEWARE
# ============================================================

@app.middleware("http")
async def request_validation_middleware(request: Request, call_next):
    """Valida Content-Type para POST y tamano del body."""
    # Validate Content-Type for POST requests (except multipart paths)
    if request.method == "POST" and request.url.path not in _MULTIPART_PATHS:
        content_type = request.headers.get("content-type", "")
        if content_type and not content_type.startswith("application/json"):
            request_id = getattr(request.state, "request_id", "unknown")
            return JSONResponse(
                status_code=415,
                content=_error_body(
                    detail="Content-Type must be application/json",
                    request_id=request_id,
                ),
                headers={"X-Request-ID": request_id},
            )

    # Validate body size via Content-Length header (quick check)
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > _MAX_BODY_SIZE:
                    request_id = getattr(request.state, "request_id", "unknown")
                    return JSONResponse(
                        status_code=413,
                        content=_error_body(
                            detail=f"Request body too large. Max size: {_MAX_BODY_SIZE // (1024*1024)}MB",
                            request_id=request_id,
                        ),
                        headers={"X-Request-ID": request_id},
                    )
            except (ValueError, TypeError):
                pass

    response = await call_next(request)
    return response


# ============================================================
# RATE LIMIT MIDDLEWARE
# ============================================================

@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    """Rate limiting por IP: max _rate_limit_max requests por _rate_limit_window segundos."""
    # Skip rate limit for health checks and OPTIONS
    if request.url.path == "/api/health" or request.method == "OPTIONS":
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    err = _check_rate_limit(client_ip)
    if err:
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=429,
            content=_error_body(detail=err, request_id=request_id),
            headers={
                "Retry-After": str(_rate_limit_window),
                "X-Request-ID": request_id,
            },
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


# ============================================================
# ERROR RESPONSE HELPERS
# ============================================================

def _error_body(detail: str, request_id: str = "unknown", internal_detail: str = None) -> dict:
    """Construye un cuerpo de error estandarizado.

    In production mode, hides internal_detail if provided.
    Always includes: detail, request_id, timestamp.
    """
    body = {
        "detail": detail,
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # In non-production, include internal details for debugging
    if internal_detail and not _PRODUCTION:
        body["internal_detail"] = internal_detail
    return body


# ============================================================
# CUSTOM EXCEPTION HANDLER
# ============================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Todas las HTTPException responses incluyen request_id y timestamp."""
    request_id = getattr(request.state, "request_id", "unknown")
    # In production, truncate detail if too long
    detail = str(exc.detail)
    if _PRODUCTION and len(detail) > 200:
        detail = detail[:200] + "..."
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(detail=detail, request_id=request_id),
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all: any unhandled exception returns structured 500."""
    request_id = getattr(request.state, "request_id", "unknown")
    _bridge_logger.error(f"[{request_id}] Unhandled exception: {exc}", exc_info=True)
    detail = "Internal server error" if _PRODUCTION else f"Internal server error: {str(exc)}"
    if _PRODUCTION and len(detail) > 200:
        detail = detail[:200] + "..."
    return JSONResponse(
        status_code=500,
        content=_error_body(detail=detail, request_id=request_id),
        headers={"X-Request-ID": request_id},
    )


# --- Singleton del agente ---
_agent: Optional[ReactAgent] = None
_memory: Optional[TripleMemory] = None
_start_time = time.time()
_busy = False  # Flag: el agente esta procesando
_agent_lock = threading.Lock()  # Protege acceso a _agent, _memory, _busy
_upload_dir = os.path.join(os.path.expanduser("~"), ".ia-local", "uploads")
os.makedirs(_upload_dir, exist_ok=True)


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

@app.get("/api/system")
async def system_info(auth=Depends(verify_token)):
    """Retorna informacion REAL de hardware: CPU, RAM, Disco, GPU.

    Usa psutil para metricas reales y nvidia-smi para GPU/VRAM.
    """
    info = {
        "cpu_percent": 0,
        "ram_percent": 0,
        "ram_total_gb": 0,
        "ram_used_gb": 0,
        "disk_percent": 0,
        "disk_total_gb": 0,
        "disk_used_gb": 0,
        "gpu": None,
    }
    try:
        import psutil
        info["cpu_percent"] = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        info["ram_percent"] = mem.percent
        info["ram_total_gb"] = round(mem.total / (1024**3), 1)
        info["ram_used_gb"] = round(mem.used / (1024**3), 1)
        disk = psutil.disk_usage("/")
        info["disk_percent"] = disk.percent
        info["disk_total_gb"] = round(disk.total / (1024**3), 1)
        info["disk_used_gb"] = round(disk.used / (1024**3), 1)
    except ImportError:
        _bridge_logger.debug("psutil no instalado, metricas de sistema no disponibles")
    except Exception as e:
        _bridge_logger.debug(f"Error obteniendo metricas de sistema: {e}")

    # GPU detection via nvidia-smi
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 5:
                info["gpu"] = {
                    "name": parts[0],
                    "vram_total_mb": int(float(parts[1])),
                    "vram_used_mb": int(float(parts[2])),
                    "vram_free_mb": int(float(parts[3])),
                    "gpu_utilization": int(float(parts[4])),
                }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        pass  # No NVIDIA GPU or nvidia-smi not available

    return info


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
        except Exception as e:
            _bridge_logger.debug(f"Error verificando Ollama en health endpoint: {e}")
            ollama_status = "unreachable"
    return {
        "status": "ok",
        "agent": AGENT_AVAILABLE,
        "ollama": ollama_status,
        "busy": _busy,
        "version": "17.0.0",
        "uptime": int(time.time() - _start_time),
        "auth_enabled": _AUTH_ENABLED,
        "memory_loaded": _memory is not None,
    }


@app.get("/api/health/skills")
async def health_skills():
    """Skill health check - verifies that each tool works correctly."""
    if not AGENT_AVAILABLE:
        return {"status": "unavailable", "reason": "Agent not available"}

    try:
        from tools.skill_health import get_skill_health_checker
        checker = get_skill_health_checker()
        checker.run_health_check()
        return checker.get_detailed()
    except Exception as e:
        _bridge_logger.error(f"Error in skill health check: {e}")
        return {"status": "error", "error": str(e)[:200]}


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
    except Exception as e:
        _bridge_logger.debug(f"Error conectando a Ollama en status endpoint: {e}")

    uptime = int(time.time() - _start_time)

    # Tool count
    tool_count = len(TOOL_FUNCTIONS) if AGENT_AVAILABLE else 0

    return {
        "connected": ollama_ok,
        "agent_available": AGENT_AVAILABLE,
        "busy": _busy,
        "version": "17.0.0",
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

    # Tool categorization based on name prefixes
    _TOOL_CATEGORIES = {
        "ejecutar_": "sistema", "procesos_": "sistema", "matar_": "sistema",
        "programar_": "sistema", "ejecutar_subagente": "sistema", "listar_subagentes": "sistema",
        "orquestar": "sistema", "limpiar_contexto": "sistema", "estadisticas": "sistema",
        "configurar_": "sistema", "listar_api_keys": "sistema", "diagnosticar_error": "sistema",
        "leer_archivo": "archivos", "escribir_archivo": "archivos", "listar_archivos": "archivos",
        "listar_glob": "archivos", "buscar_en_archivos": "archivos", "buscar_patron": "archivos",
        "leer_archivo_comprimido": "archivos", "leer_csv": "datos", "leer_xlsx": "datos",
        "leer_docx": "archivos", "leer_pptx": "archivos", "leer_pdf": "archivos",
        "leer_epub": "archivos", "leer_documento": "archivos", "leer_imagen_ocr": "archivos",
        "buscar_reemplazar": "archivos", "editar_lineas": "archivos", "insertar_en_linea": "archivos",
        "analizar_proyecto": "proyecto", "clonar_repositorio": "proyecto",
        "instalar_dependencias": "proyecto", "git_operacion": "proyecto",
        "consultar_sqlite": "datos", "crear_proyecto_web": "proyecto",
        "ejecutar_archivo": "sistema", "ejecutar_tests": "sistema",
        "buscar_web": "web", "buscar_web_cloud": "web", "busqueda_profunda": "web",
        "leer_web": "web", "resumir_url": "web", "scrapear_web": "web",
        "automatizar_web": "web", "llamar_api": "web", "abrir_aplicacion": "sistema",
        "abrir_url": "web", "buscar_youtube": "web", "buscar_imagenes": "web",
        "escribir_portapapeles": "sistema", "leer_portapapeles": "sistema",
        "generar_codigo": "generacion", "crear_docx": "generacion", "crear_pdf": "generacion",
        "crear_pptx": "generacion", "crear_xlsx": "generacion", "crear_grafico": "generacion",
        "crear_grafico_avanzado": "generacion", "crear_diagrama": "generacion",
        "generar_mermaid": "generacion", "crear_dashboard": "generacion",
        "generar_imagen": "multimedia", "generar_imagen_cloud": "multimedia",
        "editar_imagen": "multimedia", "editar_multiples": "multimedia",
        "generacion_batch": "generacion",
        "analizar_imagen": "multimedia", "analizar_imagen_cloud": "multimedia",
        "analizar_video": "multimedia", "texto_a_voz": "multimedia",
        "llm_cloud_chat": "multimedia",
        "parsear_datos": "datos", "limpiar_datos": "datos", "merge_datos": "datos",
        "tabla_pivote": "datos", "exportar_datos": "datos",
        "enviar_email": "comunicacion", "leer_email": "comunicacion",
        "crear_nota": "memoria", "ver_notas": "memoria",
        "planificar_tarea": "planificacion", "listar_tareas": "planificacion",
    }

    def _get_category(name: str) -> str:
        for prefix, cat in _TOOL_CATEGORIES.items():
            if name.startswith(prefix) or name == prefix:
                return cat
        return "general"

    tools_list = []
    for name in sorted(TOOL_FUNCTIONS.keys()):
        schema = schema_map.get(name, {})
        tools_list.append({
            "name": name,
            "description": schema.get("description", ""),
            "parameters": schema.get("parameters", {}),
            "available": True,
            "category": _get_category(name),
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
    """Configuracion actual del agente (non-sensitive only).

    Returns: model, temperature, max_tokens, tools_count, memory_type,
    and other non-sensitive configuration.
    """
    try:
        import config as cfg

        # Determine memory type from current memory instance
        memory_type = "none"
        if _memory is not None:
            memory_type = type(_memory.long_term).__name__

        # Determine active model
        active_model = None
        if AGENT_AVAILABLE:
            active_model = getattr(ollama, 'model', None)

        # Tools count
        tools_count = len(TOOL_FUNCTIONS) if AGENT_AVAILABLE else 0

        return {
            # Core model config
            "model": active_model,
            "temperature": getattr(cfg, 'TEMPERATURE', 0.7),  # Default if not in config
            "max_tokens": getattr(cfg, 'MAX_TOKENS', 4096),    # Default if not in config
            "tools_count": tools_count,
            "memory_type": memory_type,
            # Behavioral config
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
        _bridge_logger.error(f"Error leyendo config: {e}")
        raise HTTPException(status_code=500, detail="Error leyendo configuracion")


@app.get("/api/sessions")
async def sessions(auth=Depends(verify_token)):
    """Lista sesiones guardadas del agente.

    Returns: list of {session_id, date, message_count}
    """
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    sessions_list = []
    try:
        # Scan LEARN_DIR for session files
        from config import LEARN_DIR
        session_pattern = os.path.join(LEARN_DIR, "session*.json")
        for filepath in glob_mod.glob(session_pattern):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Extract session info
                filename = os.path.basename(filepath)
                session_id = filename.replace(".json", "")
                saved_at = data.get("saved_at", "")
                messages = data.get("short_term", [])
                message_count = len(messages) if isinstance(messages, list) else 0

                # Format date
                date_str = saved_at
                if saved_at:
                    try:
                        dt = datetime.fromisoformat(saved_at)
                        date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        pass

                sessions_list.append({
                    "session_id": session_id,
                    "date": date_str,
                    "message_count": message_count,
                })
            except (json.JSONDecodeError, OSError, KeyError) as e:
                _bridge_logger.debug(f"Error reading session file {filepath}: {e}")
                continue

        # Sort by date descending (newest first)
        sessions_list.sort(key=lambda s: s.get("date", ""), reverse=True)

    except Exception as e:
        _bridge_logger.warning(f"Error listing sessions: {e}")

    return {
        "sessions": sessions_list,
        "count": len(sessions_list),
    }


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


def _sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks (B3 fix)."""
    import re
    # Remove any directory path
    filename = os.path.basename(filename)
    # Replace special characters with underscore
    filename = re.sub(r'[^\w.\-]', '_', filename)
    # Collapse multiple underscores
    filename = re.sub(r'_{2,}', '_', filename)
    # Limit length
    filename = filename[:255]
    # Ensure we have a valid name
    if not filename or filename.startswith('.'):
        filename = f"upload_{int(time.time())}"
    return filename


@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...), auth=Depends(verify_token)):
    """Sube archivos para procesar con el agente."""
    uploaded = []
    for file in files:
        try:
            # Validate individual file size
            content = await file.read()
            if len(content) > _MAX_BODY_SIZE:
                uploaded.append({
                    "name": file.filename,
                    "error": f"File too large. Max size: {_MAX_BODY_SIZE // (1024*1024)}MB",
                })
                continue

            # Sanitize filename to prevent path traversal (B3 fix)
            safe_name = _sanitize_filename(file.filename or "unnamed")
            file_path = os.path.join(_upload_dir, safe_name)

            # Verify the resolved path is within the upload directory
            real_upload_dir = os.path.realpath(_upload_dir)
            real_file_path = os.path.realpath(file_path)
            if not real_file_path.startswith(real_upload_dir + os.sep) and real_file_path != real_upload_dir:
                uploaded.append({
                    "name": file.filename,
                    "error": "Invalid file path",
                })
                continue

            with open(file_path, "wb") as f:
                f.write(content)
            uploaded.append({
                "name": safe_name,
                "original_name": file.filename,
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


@app.get("/api/version")
async def version():
    """Version del API y del agente. No requiere auth."""
    version_info = {
        "api_version": "17.0.0",
        "agent_version": "17.0.0",
        "bridge_api": "v16",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "agent_available": AGENT_AVAILABLE,
    }
    if AGENT_AVAILABLE:
        try:
            version_info["tools_count"] = len(TOOL_FUNCTIONS)
            version_info["active_model"] = getattr(ollama, 'model', None)
        except Exception:
            pass
    return version_info


@app.post("/api/reset")
async def reset_conversation(auth=Depends(verify_token)):
    """Resetea el contexto de conversacion del agente.

    Limpia la memoria a corto plazo, el historial de thinking, y recrea el agente.
    La memoria a largo plazo (aprendizaje) se preserva.
    """
    global _agent
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    with _agent_lock:
        try:
            # Save current session before reset
            if _memory is not None:
                _memory.save_session()

            # Clear short-term memory but preserve long-term learning
            mem = get_memory()
            mem.short_term = []
            mem.medium_term = []

            # Recreate agent with same memory instance
            _agent = ReactAgent(memory=mem)

            _bridge_logger.info("Conversation context reset successfully")
            return {
                "status": "ok",
                "message": "Contexto de conversacion reiniciado. Memoria de aprendizaje preservada.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            _bridge_logger.error(f"Error resetting conversation: {e}")
            raise HTTPException(status_code=500, detail=f"Error reiniciando conversacion: {str(e)}")


@app.get("/api/plan")
async def plan_get(auth=Depends(verify_token)):
    """Obtiene el plan de tarea activo (si existe)."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    # Check if there's an active plan in the agent
    plan_info = {"active": False, "plan": None}
    try:
        agent = get_agent()
        if hasattr(agent, '_active_plan') and agent._active_plan:
            plan_info = {
                "active": True,
                "plan": agent._active_plan,
            }
    except Exception as e:
        _bridge_logger.debug(f"Error getting plan: {e}")

    return plan_info


class PlanRequest(BaseModel):
    goal: str
    task_type: Optional[str] = None


class PlanAdvanceRequest(BaseModel):
    result: str = ""


@app.post("/api/plan")
async def plan_create(request: PlanRequest, auth=Depends(verify_token)):
    """Crea un plan de tarea usando la herramienta planificar_tarea."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    try:
        from tools import TOOL_FUNCTIONS
        if "planificar_tarea" not in TOOL_FUNCTIONS:
            raise HTTPException(status_code=404, detail="Herramienta planificar_tarea no disponible.")

        result = TOOL_FUNCTIONS["planificar_tarea"](
            objetivo=request.goal,
            tipo_tarea=request.task_type or "general"
        )
        return {"success": True, "result": str(result)[:5000]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creando plan: {e}")


@app.post("/api/plan/advance")
async def plan_advance(request: PlanAdvanceRequest, auth=Depends(verify_token)):
    """Avanza al siguiente paso del plan activo."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    try:
        from tools import TOOL_FUNCTIONS
        if "listar_tareas" not in TOOL_FUNCTIONS:
            raise HTTPException(status_code=404, detail="Herramienta listar_tareas no disponible.")

        result = TOOL_FUNCTIONS["listar_tareas"]()
        return {"success": True, "result": str(result)[:5000]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error avanzando plan: {e}")


# --- Cancel flag for agent cancellation (B7) ---
_cancel_requested = False


@app.post("/api/chat/cancel")
async def cancel_chat(auth=Depends(verify_token)):
    """Solicita la cancelacion del agente que esta corriendo.

    El agente revisa esta bandera entre pasos del loop ReAct.
    """
    global _cancel_requested
    if not _busy:
        return {"status": "ok", "message": "No hay agente corriendo."}
    _cancel_requested = True
    return {"status": "ok", "message": "Cancelacion solicitada."}


# ============================================================
# ORCHESTRATOR, CIRCUIT BREAKER, AUTO-EVOLVE, MCP ENDPOINTS
# ============================================================

@app.get("/api/orchestrator/status")
async def orchestrator_status(auth=Depends(verify_token)):
    """Estado del orquestador multi-agente."""
    try:
        from agent.orchestrator import Orchestrator, detect_subagent_needs
        return {
            "available": True,
            "strategies": ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"],
            "subagent_types": list(detect_subagent_needs.__doc__ or ["researcher", "coder", "analyst", "writer"]),
        }
    except ImportError:
        return {"available": False, "reason": "Orchestrator module not importable"}
    except Exception as e:
        return {"available": False, "reason": str(e)[:200]}


class OrchestrateRequest(BaseModel):
    task: str
    strategy: Optional[str] = "ADAPTIVE"  # SEQUENTIAL, PARALLEL, ADAPTIVE
    max_subagents: Optional[int] = 3


@app.post("/api/orchestrator/run")
async def orchestrator_run(request: OrchestrateRequest, auth=Depends(verify_token)):
    """Ejecuta una tarea compleja usando el orquestador multi-agente."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    try:
        from agent.orchestrator import Orchestrator
        orc = Orchestrator()
        result = orc.orchestrate(
            task=request.task,
            strategy=request.strategy,
            max_subagents=request.max_subagents,
        )
        return {"success": True, "result": str(result)[:5000]}
    except ImportError:
        raise HTTPException(status_code=504, detail="Orchestrator no disponible.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en orquestacion: {str(e)[:200]}")


@app.get("/api/circuit-breaker/status")
async def circuit_breaker_status(auth=Depends(verify_token)):
    """Estado de todos los circuit breakers."""
    try:
        from agent.circuit_breaker import CircuitBreakerManager
        # Try to get the global instance, or create one
        cb = CircuitBreakerManager()
        return {
            "available": True,
            "circuits": cb.get_all_status() if hasattr(cb, 'get_all_status') else {},
        }
    except ImportError:
        return {"available": False, "reason": "Circuit breaker module not importable"}
    except Exception as e:
        return {"available": False, "circuits": {}, "error": str(e)[:200]}


@app.post("/api/circuit-breaker/reset/{tool_name}")
async def circuit_breaker_reset(tool_name: str, auth=Depends(verify_token)):
    """Resetea un circuit breaker especifico."""
    try:
        from agent.circuit_breaker import CircuitBreakerManager
        cb = CircuitBreakerManager()
        if hasattr(cb, 'reset'):
            cb.reset(tool_name)
        return {"status": "ok", "message": f"Circuit breaker '{tool_name}' reseteado"}
    except ImportError:
        raise HTTPException(status_code=504, detail="Circuit breaker no disponible.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@app.post("/api/auto-evolve")
async def auto_evolve(focus: Optional[str] = None, auth=Depends(verify_token)):
    """Ejecuta el ciclo de auto-evolucion del agente."""
    if not AGENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agente no disponible.")

    try:
        from agent.auto_evolve import AutoEvolver
        evolver = AutoEvolver()
        result = evolver.evolve(focus=focus)
        return {"success": True, "result": str(result)[:5000]}
    except ImportError:
        raise HTTPException(status_code=504, detail="Auto-evolve no disponible.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en auto-evolucion: {str(e)[:200]}")


@app.get("/api/auto-evolve/log")
async def auto_evolve_log(auth=Depends(verify_token)):
    """Historial de auto-evolucion."""
    try:
        from agent.auto_evolve import EVOLVE_LOG
        import os
        if os.path.exists(EVOLVE_LOG):
            with open(EVOLVE_LOG, "r") as f:
                data = json.load(f)
            return {"available": True, "log": data}
        return {"available": True, "log": []}
    except ImportError:
        return {"available": False, "log": []}
    except Exception as e:
        return {"available": False, "log": [], "error": str(e)[:200]}


@app.get("/api/mcp/status")
async def mcp_status(auth=Depends(verify_token)):
    """Estado del cliente MCP."""
    try:
        from mcp.client import MCPClient
        return {"available": True, "servers": []}
    except ImportError:
        return {"available": False, "reason": "MCP client module not importable"}
    except Exception as e:
        return {"available": False, "reason": str(e)[:200]}


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
    Revisa _cancel_requested entre eventos para soportar cancelacion (B7).
    """
    global _busy, _cancel_requested
    with _agent_lock:
        _busy = True
        _cancel_requested = False
    try:
        for event in agent.run_stream(message):
            if _cancel_requested:
                q.put({"type": "error", "data": "Generacion cancelada por el usuario"})
                break
            q.put(event)
        # Senal de fin
        q.put(None)
    except Exception as e:
        _bridge_logger.error(f"Agent runner error: {e}", exc_info=True)
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
            _cancel_requested = False


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
        _bridge_logger.error(f"Stream error: {e}", exc_info=True)
        err_msg = "Stream error" if _PRODUCTION else f"Stream error: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'data': err_msg}, ensure_ascii=False)}\n\n"


# ============================================================
# GRACEFUL SHUTDOWN
# ============================================================

_shutdown_event = threading.Event()
_server_instance = None  # Will hold uvicorn server reference


def _signal_handler(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    sig_name = signal.Signals(signum).name
    _bridge_logger.info(f"Received {sig_name}, initiating graceful shutdown...")
    print(f"\n[SHUTDOWN] Received {sig_name}, shutting down gracefully...")

    # Save session if memory is loaded
    if _memory is not None:
        try:
            _memory.save_session()
            _bridge_logger.info("Session saved before shutdown")
            print("[SHUTDOWN] Session saved.")
        except Exception as e:
            _bridge_logger.warning(f"Could not save session during shutdown: {e}")
            print(f"[SHUTDOWN] Warning: Could not save session: {e}")

    # Signal shutdown
    _shutdown_event.set()

    # If we have a server instance, trigger its shutdown
    if _server_instance is not None:
        _server_instance.should_exit = True

    _bridge_logger.info("Shutdown complete")
    print("[SHUTDOWN] Goodbye.")


# Register signal handlers
signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


# --- Main ---

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  ZAI Agent Bridge API v17.0")
    print("  Puerto: 8000")
    print("  Agente:", "DISPONIBLE" if AGENT_AVAILABLE else "NO DISPONIBLE")
    print("  Threading: ACTIVADO (no bloquea event loop)")
    print("  Endpoints: /api/status, /api/chat, /api/tools,")
    print("             /api/memory, /api/config, /api/sessions,")
    print("             /api/execute, /api/upload, /api/history,")
    print("             /api/health")
    print("=" * 60)
    host = os.environ.get("BRIDGE_HOST", "127.0.0.1")  # Default: localhost only
    port = int(os.environ.get("BRIDGE_PORT", "8000"))
    print(f"  Auth: {'HABILITADA (token configurado)' if _AUTH_ENABLED else 'DESHABILITADA (modo local)'}")
    print(f"  Rate limit: {_rate_limit_max} req/{_rate_limit_window}s por IP")
    print(f"  CORS origins: {_ALLOWED_ORIGINS}")
    print(f"  Max body size: {_MAX_BODY_SIZE // (1024*1024)}MB")
    print(f"  Request ID tracking: ENABLED")
    print(f"  Environment: {'PRODUCTION' if _PRODUCTION else 'DEVELOPMENT'}")
    print(f"  Host: {host}:{port}")
    config = uvicorn.Config(app, host=host, port=port)
    _server_instance = uvicorn.Server(config)
    _server_instance.run()
