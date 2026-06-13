"""
=============================================================
AGENTE v15 - Sistema de Sub-Agentes con Ejecucion Paralela
=============================================================
Sistema que permite delegar tareas a sub-agentes especializados:
- Ejecucion paralela de multiples sub-agentes
- Sub-agentes especializados por tipo de tarea
- Agregacion y sintesis de resultados
- Timeout y manejo de errores por sub-agente
- Comunicacion entre sub-agentes via contexto compartido

Tipos de sub-agente:
- researcher: busqueda y recopilacion de informacion
- coder: generacion y analisis de codigo
- analyst: analisis de datos y estadisticas
- writer: redaccion y creacion de contenido
- reviewer: revision y critica de resultados

Uso:
    from tools.subagentes import ejecutar_subagente, ejecutar_paralelo
    resultado = ejecutar_subagente("researcher", "Busca info sobre Python 3.12")
    resultados = ejecutar_paralelo([
        ("researcher", "Busca info sobre React 19"),
        ("coder", "Genera un componente React"),
    ])
=============================================================
"""

import os
import json
import time
import logging
import threading
import concurrent.futures
from datetime import datetime
from config import LEARN_DIR, logger


# ============================================================
# CONFIGURACION DE SUB-AGENTES
# ============================================================

SUBAGENT_TYPES = {
    "researcher": {
        "description": "Busca y recopila informacion de multiples fuentes",
        "system_prompt": (
            "Eres un agente investigador especializado. Tu trabajo es buscar, "
            "recopilar y sintetizar informacion de multiples fuentes. "
            "Se preciso, cita fuentes, y organiza la informacion de forma clara. "
            "Responde en espanol."
        ),
        "tools": ["buscar_web", "scrapear_web", "leer_documento", "leer_archivo"],
        "max_iterations": 3,
    },
    "coder": {
        "description": "Genera, analiza y modifica codigo",
        "system_prompt": (
            "Eres un agente programador especializado. Tu trabajo es generar, "
            "analizar y modificar codigo. Escribe codigo limpio, documentado y funcional. "
            "Responde en espanol con el codigo en el formato apropiado."
        ),
        "tools": ["generar_codigo", "ejecutar_python", "ejecutar_bash", "leer_archivo", "escribir_archivo"],
        "max_iterations": 3,
    },
    "analyst": {
        "description": "Analiza datos, calcula estadisticas y genera insights",
        "system_prompt": (
            "Eres un agente analista de datos especializado. Tu trabajo es analizar datos, "
            "calcular estadisticas, identificar patrones y generar insights accionables. "
            "Presenta resultados de forma clara con numeros y visualizaciones. "
            "Responde en espanol."
        ),
        "tools": ["estadisticas", "transformar_datos", "crear_grafico_avanzado", "limpiar_datos", "tabla_pivote"],
        "max_iterations": 3,
    },
    "writer": {
        "description": "Redacta y crea contenido textual",
        "system_prompt": (
            "Eres un agente escritor especializado. Tu trabajo es redactar contenido "
            "de alta calidad: articulos, resumenes, documentos, correos, etc. "
            "Escribe de forma clara, profesional y bien estructurada. "
            "Responde en espanol."
        ),
        "tools": ["crear_docx", "crear_pdf", "escribir_archivo", "leer_archivo"],
        "max_iterations": 2,
    },
    "reviewer": {
        "description": "Revisa y critica resultados de otros agentes",
        "system_prompt": (
            "Eres un agente revisor especializado. Tu trabajo es revisar el trabajo "
            "de otros agentes, identificar errores, inconsistencias o mejoras posibles. "
            "Se constructivo y especifico en tus criticas. "
            "Responde en espanol."
        ),
        "tools": ["leer_archivo", "buscar_web", "buscar_en_archivos"],
        "max_iterations": 2,
    },
    "general": {
        "description": "Agente general para tareas variadas",
        "system_prompt": (
            "Eres un agente general versatil. Puedes realizar cualquier tipo de tarea "
            "usando las herramientas disponibles. Se eficiente y preciso. "
            "Responde en espanol."
        ),
        "tools": [],  # Todas las herramientas disponibles
        "max_iterations": 3,
    },
}


# ============================================================
# CONTEXTO COMPARTIDO
# ============================================================

class SharedContext:
    """Contexto compartido entre sub-agentes para comunicacion."""

    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    def set(self, key: str, value):
        """Almacena un valor en el contexto compartido."""
        with self._lock:
            self._data[key] = value

    def get(self, key: str, default=None):
        """Obtiene un valor del contexto compartido."""
        with self._lock:
            return self._data.get(key, default)

    def update(self, data: dict):
        """Actualiza multiples valores en el contexto."""
        with self._lock:
            self._data.update(data)

    def snapshot(self) -> dict:
        """Retorna una copia del contexto completo."""
        with self._lock:
            return dict(self._data)

    def clear(self):
        """Limpia el contexto."""
        with self._lock:
            self._data.clear()


# Contexto global compartido
_shared_context = SharedContext()


# ============================================================
# EJECUCION DE SUB-AGENTE INDIVIDUAL
# ============================================================

def ejecutar_subagente(
    tipo: str,
    tarea: str,
    contexto: str = "",
    timeout: int = 60,
    max_iteraciones: int = None,
) -> str:
    """Ejecuta un sub-agente especializado para una tarea especifica.

    Args:
        tipo: Tipo de sub-agente: researcher, coder, analyst, writer, reviewer, general
        tarea: Descripcion de la tarea a realizar
        contexto: Contexto adicional para el sub-agente (informacion previa)
        timeout: Timeout en segundos (default 60)
        max_iteraciones: Maximo de iteraciones (default: segun tipo)
    """
    tipo = tipo.lower().strip()
    if tipo not in SUBAGENT_TYPES:
        return (f"ERROR: Tipo de sub-agente '{tipo}' no reconocido.\n"
                f"Tipos disponibles: {', '.join(SUBAGENT_TYPES.keys())}")

    config = SUBAGENT_TYPES[tipo]
    max_iter = max_iteraciones or config["max_iterations"]

    logger.info(f"Sub-agente [{tipo}] iniciado: {tarea[:80]}...")

    start_time = time.time()

    try:
        # Construir prompt para el sub-agente
        system_prompt = config["system_prompt"]

        full_prompt = f"TAREA: {tarea}\n"
        if contexto:
            full_prompt += f"\nCONTEXTO:\n{contexto}\n"
        full_prompt += f"\nHerramientas disponibles: {', '.join(config['tools']) or 'todas'}"
        full_prompt += "\n\nRealiza la tarea de forma completa y precisa."

        # Ejecutar via el LLM del agente
        result = _run_subagent_llm(system_prompt, full_prompt, tipo, max_iter, timeout)

        elapsed = time.time() - start_time

        # Guardar en contexto compartido
        result_key = f"subagent_{tipo}_{int(start_time)}"
        _shared_context.set(result_key, {
            "type": tipo,
            "task": tarea,
            "result": result,
            "elapsed": elapsed,
            "timestamp": datetime.now().isoformat(),
        })

        logger.info(f"Sub-agente [{tipo}] completado en {elapsed:.1f}s")
        return result

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Sub-agente [{tipo}] fallo tras {elapsed:.1f}s: {e}")
        return f"ERROR: Sub-agente [{tipo}] fallo: {e}"


def _run_subagent_llm(system_prompt: str, user_prompt: str, tipo: str,
                       max_iter: int, timeout: int) -> str:
    """Ejecuta el sub-agente usando el LLM del agente principal."""
    try:
        from llm import ollama

        # Verificar si ollama tiene chat
        if hasattr(ollama, 'chat'):
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            # Intentar con las herramientas del tipo de sub-agente
            config = SUBAGENT_TYPES[tipo]
            tool_names = config.get("tools", [])

            # Por ahora, ejecutar sin tool calling (el LLM genera la respuesta directamente)
            response = ollama.chat(
                messages=messages,
                stream=False,
            )

            if isinstance(response, dict):
                return response.get("message", {}).get("content", str(response))
            elif isinstance(response, str):
                return response
            else:
                return str(response)

        elif hasattr(ollama, 'generate'):
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            response = ollama.generate(full_prompt)
            return response if isinstance(response, str) else str(response)

        else:
            return "ERROR: No se encontro metodo de comunicacion con el LLM."

    except ImportError:
        # Fallback: usar subprocess para llamar a ollama directamente
        return _run_subagent_cli(system_prompt, user_prompt, timeout)
    except Exception as e:
        return f"ERROR ejecutando sub-agente LLM: {e}"


def _run_subagent_cli(system_prompt: str, user_prompt: str, timeout: int) -> str:
    """Fallback: ejecuta sub-agente via CLI de ollama."""
    import subprocess

    try:
        # Detectar modelo disponible
        result = subprocess.run(
            ['ollama', 'list'], capture_output=True, text=True, timeout=5
        )

        # Buscar un modelo de chat
        models = result.stdout.strip().split('\n')
        chat_model = None
        for line in models:
            model_name = line.split()[0] if line.strip() else ""
            for pattern in ["qwen", "llama", "mistral", "gemma"]:
                if pattern in model_name.lower():
                    chat_model = model_name
                    break
            if chat_model:
                break

        if not chat_model:
            return "ERROR: No se encontro modelo de chat en Ollama."

        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        result = subprocess.run(
            ['ollama', 'run', chat_model, full_prompt],
            capture_output=True, text=True, timeout=timeout
        )

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"ERROR: {result.stderr[:500]}"

    except FileNotFoundError:
        return "ERROR: Ollama no instalado."
    except subprocess.TimeoutExpired:
        return f"ERROR: Timeout de {timeout}s alcanzado."
    except Exception as e:
        return f"ERROR: {e}"


# ============================================================
# EJECUCION PARALELA
# ============================================================

def ejecutar_paralelo(tareas: str, agregar_resultados: bool = True) -> str:
    """Ejecuta multiples sub-agentes en paralelo y agrega los resultados.

    Args:
        tareas: Lista JSON de tareas: [{"tipo": "researcher", "tarea": "..."}, ...]
        agregar_resultados: Si True, agrega y sintetiza todos los resultados
    """
    try:
        task_list = json.loads(tareas)
    except json.JSONDecodeError:
        return "ERROR: Formato de tareas invalido. Usa JSON: [{tipo, tarea}, ...]"

    if not task_list:
        return "ERROR: Lista de tareas vacia."

    if len(task_list) > 8:
        return "ERROR: Maximo 8 sub-agentes en paralelo."

    # Validar tareas
    for t in task_list:
        tipo = t.get("tipo", "general")
        if tipo not in SUBAGENT_TYPES:
            return f"ERROR: Tipo '{tipo}' no reconocido en tarea: {t.get('tarea', '?')}"

    logger.info(f"Ejecutando {len(task_list)} sub-agentes en paralelo...")

    results = {}
    errors = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(task_list), 4)) as executor:
        future_to_task = {}

        for i, task in enumerate(task_list):
            tipo = task.get("tipo", "general")
            tarea = task.get("tarea", task.get("task", ""))
            contexto = task.get("contexto", task.get("context", ""))
            timeout = task.get("timeout", 60)

            future = executor.submit(ejecutar_subagente, tipo, tarea, contexto, timeout)
            future_to_task[future] = (i, tipo, tarea)

        for future in concurrent.futures.as_completed(future_to_task):
            i, tipo, tarea = future_to_task[future]
            try:
                result = future.result(timeout=120)
                results[i] = {
                    "tipo": tipo,
                    "tarea": tarea[:80],
                    "resultado": result,
                }
            except Exception as e:
                errors[i] = {
                    "tipo": tipo,
                    "tarea": tarea[:80],
                    "error": str(e),
                }

    # Construir respuesta
    parts = [f"Sub-agentes ejecutados: {len(results)} exitosos, {len(errors)} errores\n"]

    for i in sorted(results.keys()):
        r = results[i]
        parts.append(f"\n--- Sub-agente [{r['tipo']}] ---")
        parts.append(f"Tarea: {r['tarea']}")
        parts.append(f"Resultado:\n{r['resultado']}")

    if errors:
        parts.append(f"\n--- ERRORES ---")
        for i in sorted(errors.keys()):
            e = errors[i]
            parts.append(f"[{e['tipo']}] {e['tarea']}: {e['error']}")

    # Sintesis final si se solicita
    if agregar_resultados and len(results) > 1:
        synthesis = _synthesize_results(results)
        if synthesis:
            parts.append(f"\n--- SINTESIS ---")
            parts.append(synthesis)

    return "\n".join(parts)


def _synthesize_results(results: dict) -> str:
    """Sintetiza los resultados de multiples sub-agentes."""
    try:
        from llm import ollama

        # Recopilar resultados
        summaries = []
        for i in sorted(results.keys()):
            r = results[i]
            summaries.append(f"[{r['tipo']}] {r['tarea']}: {r['resultado'][:500]}")

        prompt = (
            "Sintetiza los siguientes resultados de sub-agentes en un resumen "
            "coherente y unificado. Destaca los hallazgos clave, contradicciones, "
            "y conclusiones:\n\n" + "\n\n".join(summaries)
        )

        if hasattr(ollama, 'generate'):
            return ollama.generate(prompt)
        elif hasattr(ollama, 'chat'):
            response = ollama.chat(
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
            if isinstance(response, dict):
                return response.get("message", {}).get("content", "")
            return str(response)

    except Exception as e:
        logger.debug(f"Sintesis fallo: {e}")

    return ""


# ============================================================
# ORQUESTACION AVANZADA
# ============================================================

def orquestar(tarea_principal: str, estrategia: str = "auto",
              max_subagentes: int = 4) -> str:
    """Orquesta automaticamente sub-agentes para una tarea compleja.
    Divide la tarea, asigna sub-agentes y sintetiza resultados.

    Args:
        tarea_principal: Descripcion de la tarea compleja
        estrategia: Estrategia: auto, secuencial, paralelo, mixto
        max_subagentes: Maximo numero de sub-agentes a usar
    """
    logger.info(f"Orquestando tarea: {tarea_principal[:100]}...")

    # Paso 1: Planificacion - dividir la tarea en subtareas
    plan = _plan_task(tarea_principal, max_subagentes)

    if not plan:
        return "ERROR: No se pudo planificar la tarea. Intenta con una descripcion mas especifica."

    # Paso 2: Ejecucion segun estrategia
    if estrategia == "auto":
        # Si hay dependencias, secuencial; si no, paralelo
        has_deps = any(t.get("depende_de") for t in plan)
        estrategia = "secuencial" if has_deps else "paralelo"

    if estrategia == "paralelo":
        result = _execute_parallel(plan, tarea_principal)
    elif estrategia == "secuencial":
        result = _execute_sequential(plan, tarea_principal)
    else:  # mixto
        result = _execute_mixed(plan, tarea_principal)

    return result


def _plan_task(tarea: str, max_subagentes: int) -> list:
    """Planifica subtareas usando el LLM."""
    try:
        from llm import ollama

        prompt = f"""Divide la siguiente tarea en subtareas para sub-agentes especializados.
Tipos disponibles: {', '.join(SUBAGENT_TYPES.keys())}

TAREA: {tarea}

Responde SOLO con un JSON array, sin markdown, sin explicaciones:
[{{"tipo": "researcher", "tarea": "descripcion de la subtarea", "depende_de": null}},
 ...]

Maximo {max_subagentes} subtareas. Cada subtarea debe ser independiente o tener dependencias claras."""

        if hasattr(ollama, 'generate'):
            response = ollama.generate(prompt)
        elif hasattr(ollama, 'chat'):
            resp = ollama.chat(
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
            response = resp.get("message", {}).get("content", "") if isinstance(resp, dict) else str(resp)
        else:
            return []

        # Parsear JSON de la respuesta
        return _extract_json_list(response)

    except Exception as e:
        logger.error(f"Planificacion fallo: {e}")
        return []


def _execute_parallel(plan: list, tarea_principal: str) -> str:
    """Ejecuta subtareas en paralelo."""
    tareas_json = json.dumps(plan, ensure_ascii=False)
    return ejecutar_paralelo(tareas_json, agregar_resultados=True)


def _execute_sequential(plan: list, tarea_principal: str) -> str:
    """Ejecuta subtareas secuencialmente, pasando contexto entre ellas."""
    all_results = []
    accumulated_context = ""

    for i, subtask in enumerate(plan):
        tipo = subtask.get("tipo", "general")
        tarea = subtask.get("tarea", "")
        contexto = accumulated_context

        result = ejecutar_subagente(tipo, tarea, contexto)

        all_results.append(f"--- Sub-agente [{tipo}] (paso {i+1}/{len(plan)}) ---\n{result}")

        # Acumular contexto para la siguiente subtarea
        accumulated_context += f"\n[Paso {i+1}] {tarea[:50]}: {result[:500]}"

    return "\n\n".join(all_results)


def _execute_mixed(plan: list, tarea_principal: str) -> str:
    """Ejecuta subtareas mixto: paralelo cuando no hay dependencias, secuencial cuando las hay."""
    # Agrupar por niveles de dependencia
    levels = _group_by_dependency(plan)

    all_results = []
    accumulated_context = ""

    for level, tasks in levels.items():
        if len(tasks) == 1:
            # Ejecutar individualmente
            t = tasks[0]
            result = ejecutar_subagente(t["tipo"], t["tarea"], accumulated_context)
            all_results.append(f"--- [{t['tipo']}] (nivel {level}) ---\n{result}")
        else:
            # Ejecutar en paralelo
            tareas_json = json.dumps(tasks, ensure_ascii=False)
            result = ejecutar_paralelo(tareas_json, agregar_resultados=False)
            all_results.append(f"--- Nivel {level} (paralelo, {len(tasks)} agentes) ---\n{result}")

        accumulated_context += f"\n[Nivel {level}]: {result[:500]}"

    return "\n\n".join(all_results)


def _group_by_dependency(plan: list) -> dict:
    """Agrupa subtareas por nivel de dependencia."""
    levels = {}
    for i, task in enumerate(plan):
        dep = task.get("depende_de")
        level = 0
        if dep is not None:
            # Buscar el nivel de la dependencia
            for j, other in enumerate(plan):
                if j == dep or (isinstance(dep, str) and str(j) == dep):
                    level = max(level, 1)
                    break
        levels.setdefault(level, []).append(task)
    return levels


def _extract_json_list(text: str) -> list:
    """Extrae una lista JSON de un texto que puede contener markdown."""
    # Intentar parsear directamente
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Buscar JSON dentro de markdown code blocks
    import re
    patterns = [
        r'```json\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```',
        r'\[.*\]',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1) if '```' in pattern else match.group())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                continue

    return []


# ============================================================
# UTILIDADES
# ============================================================

def listar_subagentes() -> str:
    """Lista los tipos de sub-agentes disponibles y sus capacidades."""
    parts = [f"Sub-agentes disponibles ({len(SUBAGENT_TYPES)}):\n"]
    for tipo, config in SUBAGENT_TYPES.items():
        parts.append(f"  [{tipo}]")
        parts.append(f"    Descripcion: {config['description']}")
        parts.append(f"    Herramientas: {', '.join(config['tools']) or 'todas'}")
        parts.append(f"    Max iteraciones: {config['max_iterations']}")
        parts.append("")

    return "\n".join(parts)


def ver_contexto_compartido() -> str:
    """Muestra el contenido del contexto compartido entre sub-agentes."""
    ctx = _shared_context.snapshot()
    if not ctx:
        return "Contexto compartido vacio."

    parts = [f"Contexto compartido ({len(ctx)} entradas):\n"]
    for key, value in ctx.items():
        if isinstance(value, dict):
            parts.append(f"  {key}:")
            parts.append(f"    Tipo: {value.get('type', '?')}")
            parts.append(f"    Tarea: {value.get('task', '?')[:80]}")
            parts.append(f"    Tiempo: {value.get('elapsed', 0):.1f}s")
        else:
            parts.append(f"  {key}: {str(value)[:100]}")

    return "\n".join(parts)


def limpiar_contexto() -> str:
    """Limpia el contexto compartido."""
    count = len(_shared_context.snapshot())
    _shared_context.clear()
    return f"Contexto compartido limpiado ({count} entradas eliminadas)."
