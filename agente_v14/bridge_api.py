"""
=============================================================
AGENTE v16 - Bridge FastAPI para la interfaz web
=============================================================
Expone el agente ReAct completo (tools, memory, streaming)
como API REST para la interfaz Next.js.

v16: Nuevos endpoints para tools, planner, skills, y db.

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
import logging

# Agregar directorio del agente al path
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

# --- Logger del bridge ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] bridge: %(message)s",
)
bridge_logger = logging.getLogger("bridge")

# --- Importar agente ---
try:
    from agent import ReactAgent
    from memory.triple_memory import TripleMemory
    from llm import ollama
    AGENT_AVAILABLE = True
except Exception as e:
    bridge_logger.warning(f"No se pudo importar el agente: {e}")
    AGENT_AVAILABLE = False

# --- Importar herramientas v16 ---
try:
    from tools.registry import TOOL_FUNCTIONS, TOOL_SCHEMAS, tool_count, list_tools
    TOOLS_AVAILABLE = True
except Exception as e:
    bridge_logger.warning(f"No se pudo importar tools.registry: {e}")
    TOOLS_AVAILABLE = False

try:
    from tools.skill_loader import get_skills_status, list_available_skills
    SKILLS_AVAILABLE = True
except Exception as e:
    bridge_logger.warning(f"No se pudo importar tools.skill_loader: {e}")
    SKILLS_AVAILABLE = False

try:
    from tools.task_planner import get_planner
    PLANNER_AVAILABLE = True
except Exception as e:
    bridge_logger.warning(f"No se pudo importar tools.task_planner: {e}")
    PLANNER_AVAILABLE = False

try:
    from tools.error_recovery import get_error_history
    ERROR_RECOVERY_AVAILABLE = True
except Exception as e:
    bridge_logger.warning(f"No se pudo importar tools.error_recovery: {e}")
    ERROR_RECOVERY_AVAILABLE = False

try:
    from agent.orchestrator import get_orchestrator
    ORCHESTRATOR_AVAILABLE = True
except Exception as e:
    bridge_logger.warning(f"No se pudo importar agent.orchestrator: {e}")
    ORCHESTRATOR_AVAILABLE = False

try:
    from tools.browser_automation import browser_automation, cleanup_browser
    BROWSER_AVAILABLE = True
except Exception as e:
    bridge_logger.warning(f"No se pudo importar tools.browser_automation: {e}")
    BROWSER_AVAILABLE = False

# --- App ---
app = FastAPI(
    title="ZAI Agent Bridge",
    version="17.0.0",
    description="Bridge API v17 - ReAct Agent con orchestrator, browser, plan, skills y error recovery",
)

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
_busy = False


def get_agent() -> ReactAgent:
    """Obtiene o crea la instancia singleton del agente."""
    global _agent
    if _agent is None:
        if not AGENT_AVAILABLE:
            raise HTTPException(status_code=503, detail="Agente no disponible. Verifica que Ollama este corriendo.")
        memory = TripleMemory()
        _agent = ReactAgent(memory=memory)
        bridge_logger.info("Instancia del agente creada")
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

class ToolExecuteRequest(BaseModel):
    tool_name: str
    params: dict = {}

class PlanRequest(BaseModel):
    goal: str
    task_type: Optional[str] = None

class PlanAdvanceRequest(BaseModel):
    result: str = ""


# ============================================================
# STARTUP / SHUTDOWN EVENTS
# ============================================================

@app.on_event("startup")
async def startup_event():
    """Carga inicial de skills y planes al arrancar."""
    bridge_logger.info("Iniciando Bridge API v16...")

    # Auto-cargar skills
    if SKILLS_AVAILABLE:
        try:
            from tools.skill_loader import load_all_skills
            result = load_all_skills()
            bridge_logger.info(
                f"Skills cargados: {result.get('loaded', 0)} herramientas, "
                f"{result.get('reference', 0)} referencia, "
                f"{result.get('errors', 0)} errores"
            )
        except Exception as e:
            bridge_logger.error(f"Error cargando skills al inicio: {e}")

    # Cargar planes existentes
    if PLANNER_AVAILABLE:
        try:
            planner = get_planner()
            bridge_logger.info("Planificador inicializado y planes cargados")
        except Exception as e:
            bridge_logger.error(f"Error inicializando planificador: {e}")

    bridge_logger.info(
        f"Bridge listo - Agente: {'OK' if AGENT_AVAILABLE else 'NO'}, "
        f"Tools: {tool_count() if TOOLS_AVAILABLE else 0}, "
        f"Skills: {'OK' if SKILLS_AVAILABLE else 'NO'}, "
        f"Planner: {'OK' if PLANNER_AVAILABLE else 'NO'}, "
        f"Orchestrator: {'OK' if ORCHESTRATOR_AVAILABLE else 'NO'}, "
        f"Browser: {'OK' if BROWSER_AVAILABLE else 'NO'}"
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Limpieza al apagar."""
    bridge_logger.info("Bridge API v16 apagandose...")
    global _agent
    _agent = None


# ============================================================
# RUTAS ORIGINALES (v14 heritage)
# ============================================================

@app.get("/api/status")
async def status():
    """Estado del sistema."""
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

    skills_info = {}
    if SKILLS_AVAILABLE:
        try:
            skills_info = get_skills_status()
        except Exception:
            skills_info = {"loaded": False}

    return {
        "connected": ollama_ok,
        "agent_available": AGENT_AVAILABLE,
        "tools_available": TOOLS_AVAILABLE,
        "skills_available": SKILLS_AVAILABLE,
        "planner_available": PLANNER_AVAILABLE,
        "error_recovery_available": ERROR_RECOVERY_AVAILABLE,
        "busy": _busy,
        "tool_count": tool_count() if TOOLS_AVAILABLE else 0,
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
        "version": "v17",
        "skills": skills_info,
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
        loop = asyncio.get_event_loop()
        response, thinking_log = await loop.run_in_executor(None, agent.run, request.message)
        return ChatResponse(
            response=response,
            thinking_log=thinking_log,
            tool_calls=[],
            meta_status=agent.metacognition.get_status() if hasattr(agent, 'metacognition') else {},
        )


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
    return {
        "status": "ok",
        "agent": AGENT_AVAILABLE,
        "busy": _busy,
        "version": "v17",
        "tools": tool_count() if TOOLS_AVAILABLE else 0,
    }


# ============================================================
# RUTAS v16 - TOOLS
# ============================================================

@app.get("/api/tools")
async def tools_list():
    """Lista todas las herramientas registradas."""
    if not TOOLS_AVAILABLE:
        return {"tools": [], "count": 0}

    tools_info = []
    for name in list_tools():
        from tools.registry import get_tool_metadata
        meta = get_tool_metadata(name)
        tools_info.append({
            "name": name,
            "description": meta.get("description", "") if meta else "",
            "has_schema": meta.get("schema") is not None if meta else False,
        })

    return {
        "tools": tools_info,
        "count": len(tools_info),
        "categories": {
            "basicas": ["ejecutar_comando", "leer_archivo", "escribir_archivo", "listar_archivos",
                         "abrir_aplicacion", "abrir_url", "buscar_youtube", "generar_codigo",
                         "buscar_en_archivos", "procesos_activos", "matar_proceso"],
            "web": ["buscar_web", "leer_web", "buscar_web_profundo"],
            "planificacion": ["planificar_tarea"],
            "ejecucion": ["ejecutar_codigo", "ejecutar_archivo", "ejecutar_tests"],
            "edicion": ["buscar_reemplazar", "editar_lineas", "insertar_en_linea"],
            "git": ["git_operacion"],
            "base_datos": ["base_de_datos"],
            "diagnostico": ["diagnosticar_error"],
            "memoria": ["configurar_perfil", "crear_nota", "ver_notas", "analizar_imagen"],
        }
    }


@app.post("/api/tools/execute")
async def tools_execute(request: ToolExecuteRequest):
    """Ejecuta una herramienta directamente."""
    if not TOOLS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Sistema de herramientas no disponible")

    func = TOOL_FUNCTIONS.get(request.tool_name)
    if not func:
        raise HTTPException(status_code=404, detail=f"Herramienta no encontrada: {request.tool_name}")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: func(**request.params))
        return {"success": True, "tool": request.tool_name, "result": str(result)[:3000]}
    except Exception as e:
        bridge_logger.error(f"Error ejecutando herramienta {request.tool_name}: {e}")
        traceback.print_exc()
        return {"success": False, "tool": request.tool_name, "error": str(e)}


# ============================================================
# RUTAS v16 - SKILLS
# ============================================================

@app.get("/api/skills")
async def skills_list():
    """Lista los skills disponibles."""
    if not SKILLS_AVAILABLE:
        return {"skills": [], "loaded": False}
    return {"skills": list_available_skills(), "status": get_skills_status()}


@app.post("/api/skills/reload")
async def skills_reload():
    """Recarga los skills desde disco."""
    if not SKILLS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Skill loader no disponible")
    from tools.skill_loader import load_all_skills
    result = load_all_skills()
    bridge_logger.info(f"Skills recargados: {result.get('loaded', 0)} herramientas, {result.get('errors', 0)} errores")
    return result


# ============================================================
# RUTAS v16 - PLAN
# ============================================================

@app.post("/api/plan")
async def plan_create(request: PlanRequest):
    """Crea un plan de ejecucion."""
    if not PLANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Planificador no disponible")
    planner = get_planner()
    plan = planner.create_plan(request.goal, task_type=request.task_type)
    bridge_logger.info(f"Plan creado: {plan.id} - {request.goal} ({len(plan.tasks)} tareas)")
    return {
        "plan_id": plan.id, "goal": plan.goal,
        "total_tasks": len(plan.tasks), "status": plan.status.value,
        "progress": plan.get_progress(),
        "tasks": [t.to_dict() for t in plan.tasks.values()],
    }


@app.get("/api/plan")
async def plan_get():
    """Obtiene el plan activo actual."""
    if not PLANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Planificador no disponible")
    planner = get_planner()
    plan = planner.get_active_plan()
    if not plan:
        return {"active": False, "message": "No hay plan activo"}
    return {
        "active": True, "plan_id": plan.id, "goal": plan.goal,
        "status": plan.status.value, "progress": plan.get_progress(),
        "tasks": [t.to_dict() for t in plan.tasks.values()],
    }


@app.post("/api/plan/advance")
async def plan_advance(request: PlanAdvanceRequest):
    """Avanza el plan activo."""
    if not PLANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Planificador no disponible")
    planner = get_planner()
    next_task = planner.advance_plan(request.result)
    if next_task:
        return {"completed": False, "next_task": next_task.to_dict(), "progress": planner.get_progress()}
    return {"completed": True, "message": "Plan completado", "progress": planner.get_progress()}


# ============================================================
# RUTAS v17 - ORCHESTRATOR
# ============================================================

class OrchestrateRequest(BaseModel):
    plan: dict
    strategy: Optional[str] = "adaptive"
    max_parallel: Optional[int] = 3

@app.post("/api/orchestrate")
async def orchestrate(request: OrchestrateRequest):
    """Ejecuta un plan usando el orchestrador multi-agente."""
    if not ORCHESTRATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Orchestrator no disponible")
    
    orchestrator = get_orchestrator()
    orchestrator._max_parallel = request.max_parallel
    orchestrator._strategy = request.strategy
    
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: orchestrator.orchestrate(request.plan))
    return result


@app.get("/api/orchestrator/status")
async def orchestrator_status():
    """Estado del orchestrador."""
    if not ORCHESTRATOR_AVAILABLE:
        return {"available": False}
    orchestrator = get_orchestrator()
    return {"available": True, **orchestrator.get_status()}


# ============================================================
# RUTAS v17 - BROWSER
# ============================================================

class BrowserRequest(BaseModel):
    action: str
    url: Optional[str] = ""
    selector: Optional[str] = ""
    text: Optional[str] = ""
    extract_type: Optional[str] = "text"
    full_page: Optional[bool] = False
    timeout: Optional[int] = 5000
    script: Optional[str] = ""
    output_path: Optional[str] = ""

@app.post("/api/browser")
async def browser_action(request: BrowserRequest):
    """Ejecuta una accion del navegador automatizado."""
    if not BROWSER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Browser automation no disponible. Instala: pip install playwright && playwright install chromium")
    
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: browser_automation(
        accion=request.action,
        url=request.url,
        selector=request.selector,
        text=request.text,
        extract_type=request.extract_type,
        full_page=request.full_page,
        timeout=request.timeout,
        script=request.script,
        output_path=request.output_path,
    ))
    return {"success": True, "action": request.action, "result": result[:3000]}


@app.get("/api/browser/status")
async def browser_status():
    """Estado del navegador."""
    if not BROWSER_AVAILABLE:
        return {"available": False}
    try:
        from tools.browser_automation import _browser_manager
        return {
            "available": True,
            "browser_active": _browser_manager._browser is not None,
            "page_active": _browser_manager._page is not None,
        }
    except Exception:
        return {"available": True, "browser_active": False, "page_active": False}


# ============================================================
# RUTAS v16 - ERRORS
# ============================================================

@app.get("/api/errors")
async def errors_history():
    """Historial de errores."""
    if not ERROR_RECOVERY_AVAILABLE:
        return {"errors": [], "total": 0}
    history = get_error_history()
    return {"total": len(history._history), "recent": history._history[-20:]}


# ============================================================
# STREAMING HELPERS
# ============================================================

def _agent_runner(agent: ReactAgent, message: str, q: queue.Queue):
    """Ejecuta el agente en un thread separado para no bloquear el event loop."""
    global _busy
    _busy = True
    try:
        for event in agent.run_stream(message):
            q.put(event)
        q.put(None)
    except Exception as e:
        bridge_logger.error(f"Error en _agent_runner: {e}")
        traceback.print_exc()
        q.put({"type": "error", "data": str(e)})
        q.put(None)
    finally:
        _busy = False


async def _stream_agent_threaded(agent: ReactAgent, message: str):
    """Stream eventos del agente usando un thread y una queue."""
    q = queue.Queue()
    thread = threading.Thread(target=_agent_runner, args=(agent, message, q), daemon=True)
    thread.start()

    try:
        while True:
            event = await asyncio.get_event_loop().run_in_executor(None, q.get)
            if event is None:
                break

            event_type = event.get("type", "text")
            event_data = event.get("data", "")

            if event_type == "text":
                yield f"data: {json.dumps({'type': 'text', 'data': event_data}, ensure_ascii=False)}\n\n"
            elif event_type == "thinking":
                yield f"data: {json.dumps({'type': 'thinking', 'data': event_data if isinstance(event_data, dict) else {'message': str(event_data)}}, ensure_ascii=False)}\n\n"
            elif event_type == "tool_start":
                yield f"data: {json.dumps({'type': 'tool_start', 'data': {'name': event_data.get('name', 'unknown') if isinstance(event_data, dict) else str(event_data), 'arguments': event_data.get('arguments', {}) if isinstance(event_data, dict) else {}}}, ensure_ascii=False)}\n\n"
            elif event_type == "tool_result":
                yield f"data: {json.dumps({'type': 'tool_result', 'data': {'tool': event_data.get('tool', {}) if isinstance(event_data, dict) else {}, 'result': str(event_data.get('result', ''))[:500] if isinstance(event_data, dict) else str(event_data)[:500]}}, ensure_ascii=False)}\n\n"
            elif event_type == "plan_update":
                yield f"data: {json.dumps({'type': 'plan_update', 'data': event_data}, ensure_ascii=False)}\n\n"
            elif event_type == "meta":
                yield f"data: {json.dumps({'type': 'meta', 'data': event_data}, ensure_ascii=False)}\n\n"
            elif event_type == "done":
                yield f"data: {json.dumps({'type': 'done', 'data': event_data if isinstance(event_data, str) else '', 'thinking_log': event.get('thinking_log', []), 'meta_status': event.get('meta_status', {})}, ensure_ascii=False)}\n\n"
            elif event_type == "error":
                yield f"data: {json.dumps({'type': 'error', 'data': str(event_data)}, ensure_ascii=False)}\n\n"
    except Exception as e:
        bridge_logger.error(f"Error en _stream_agent_threaded: {e}")
        traceback.print_exc()
        yield f"data: {json.dumps({'type': 'error', 'data': f'Stream error: {str(e)}'}, ensure_ascii=False)}\n\n"


# --- Main ---

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  ZAI Agent Bridge API v17.0")
    print("  Puerto: 8000")
    print("  Agente:", "DISPONIBLE" if AGENT_AVAILABLE else "NO DISPONIBLE")
    print("  Herramientas:", tool_count() if TOOLS_AVAILABLE else 0)
    print("  Skills:", "DISPONIBLE" if SKILLS_AVAILABLE else "NO DISPONIBLE")
    print("  Planificador:", "DISPONIBLE" if PLANNER_AVAILABLE else "NO DISPONIBLE")
    print("  Error Recovery:", "DISPONIBLE" if ERROR_RECOVERY_AVAILABLE else "NO DISPONIBLE")
    print("  Orchestrator:", "DISPONIBLE" if ORCHESTRATOR_AVAILABLE else "NO DISPONIBLE")
    print("  Browser (Playwright):", "DISPONIBLE" if BROWSER_AVAILABLE else "NO DISPONIBLE")
    print("  Threading: ACTIVADO (no bloquea event loop)")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
