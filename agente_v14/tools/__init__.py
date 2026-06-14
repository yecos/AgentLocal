"""
Registro centralizado de herramientas.
El agente importa TOOL_FUNCTIONS y TOOL_SCHEMAS desde aqui.

v16.3: SkillRouter + SkillError para seleccion inteligente
       de herramientas y errores estructurados.
v16: Super Agente - sub-agentes con herramientas reales,
     APIs cloud como fallback, diagramas profesionales,
     documentos mejorados, gestion de tokens.
"""
import os
import json

# Importar el registry
from .registry import tool, register_tool, TOOL_FUNCTIONS, TOOL_SCHEMAS

# Importar Skill Router y SkillError (v16.3)
from .skill_router import SkillRouter, get_skill_router, ZAI_TO_LOCAL_FALLBACK, INTENT_TO_TOOLS
from .skill_errors import SkillError, create_missing_dependency_error, create_timeout_error, create_bad_params_error

# Importar SkillPipeline y ToolSelector (C5/C3/S3)
from .skill_pipeline import SkillPipeline
from .tool_selector import detect_intent, get_tools_for_context, get_reduced_schemas

# Importar herramientas de sub-modulos (originales)
from .sistema import ejecutar_comando, procesos_activos, matar_proceso
from .archivos import leer_archivo, escribir_archivo, listar_archivos, buscar_en_archivos
from .apps import abrir_aplicacion, abrir_url, buscar_youtube
from .proyecto import analizar_proyecto, clonar_repositorio, instalar_dependencias
from .codigo import generar_codigo
from .web import buscar_web, recall_search_facts

# Importar herramientas v14.7 (Super Agente)
from .documentos import (
    leer_pdf, leer_docx, leer_xlsx, leer_pptx,
    leer_csv, leer_archivo_comprimido, consultar_sqlite,
    leer_epub, leer_documento, resumir_documento,
    extraer_datos, guardar_conocimiento, buscar_conocimiento, listar_conocimiento
)
from .crear_documentos import crear_pdf, crear_docx, crear_xlsx, crear_grafico, crear_pptx

# Importar herramientas v16 (Database, Code Review)
from .database_tool import query_natural_language
from .code_executor import review_code
from .percepcion import (
    transcribir_audio, leer_imagen_ocr,
    scrapear_web, automatizar_web
)
from .integracion import (
    leer_email, enviar_email, configurar_email,
    llamar_api, programar_tarea, listar_tareas,
    leer_portapapeles, escribir_portapapeles
)

# Importar herramientas v15 (Super Agente Avanzado)
from .visualizacion import crear_grafico_avanzado, crear_dashboard
from .diagramas import crear_diagrama, generar_mermaid
from .datos import (
    ejecutar_python, ejecutar_bash, ejecutar_nodo,
    estadisticas, tabla_pivote, merge_datos,
    limpiar_datos, transformar_datos, parsear_datos, exportar_datos
)
from .multimedia import (
    texto_a_voz, generar_imagen, editar_imagen,
    buscar_imagenes, analizar_video, notas_reunion
)
from .subagentes import (
    ejecutar_subagente, ejecutar_paralelo, orquestar,
    listar_subagentes, ver_contexto_compartido, limpiar_contexto
)

# Importar herramientas v15.2 (Super Agente Avanzado)
from .avanzado import (
    busqueda_profunda, editar_multiples, generacion_batch,
    buscar_patron, listar_glob, crear_proyecto_web, resumir_url
)

# Importar herramientas v16 (Cloud APIs)
from .cloud import (
    configurar_api_key, listar_api_keys,
    generar_imagen_cloud, analizar_imagen_cloud,
    buscar_web_cloud, llm_cloud_chat
)

# Importar schemas predefinidos (para herramientas de sub-modulos)
from .schemas import TOOL_SCHEMAS as _SCHEMAS_FROM_FILE


# ============================================================
# REGISTRAR HERRAMIENTAS DE SUB-MODULOS
# ============================================================

def _register_submodule_tools():
    """Registra las herramientas importadas de sub-modulos con sus schemas."""
    schema_by_name = {}
    for s in _SCHEMAS_FROM_FILE:
        func_info = s.get("function", {})
        name = func_info.get("name")
        if name:
            schema_by_name[name] = s

    submod_tools = {
        # Originales
        "ejecutar_comando": ejecutar_comando,
        "abrir_aplicacion": abrir_aplicacion,
        "abrir_url": abrir_url,
        "buscar_youtube": buscar_youtube,
        "generar_codigo": generar_codigo,
        "leer_archivo": leer_archivo,
        "escribir_archivo": escribir_archivo,
        "listar_archivos": listar_archivos,
        "analizar_proyecto": analizar_proyecto,
        "clonar_repositorio": clonar_repositorio,
        "instalar_dependencias": instalar_dependencias,
        "buscar_en_archivos": buscar_en_archivos,
        "procesos_activos": procesos_activos,
        "matar_proceso": matar_proceso,
        "buscar_web": buscar_web,
        # v14.7 Super Agente - Documentos (lectura)
        "leer_pdf": leer_pdf,
        "leer_docx": leer_docx,
        "leer_xlsx": leer_xlsx,
        "leer_pptx": leer_pptx,
        "leer_csv": leer_csv,
        "leer_archivo_comprimido": leer_archivo_comprimido,
        "consultar_sqlite": consultar_sqlite,
        "leer_epub": leer_epub,
        "leer_documento": leer_documento,
        # v14.7 Super Agente - Creacion
        "crear_pdf": crear_pdf,
        "crear_docx": crear_docx,
        "crear_xlsx": crear_xlsx,
        "crear_grafico": crear_grafico,
        "crear_pptx": crear_pptx,
        # v14.7 Super Agente - Percepcion
        "transcribir_audio": transcribir_audio,
        "leer_imagen_ocr": leer_imagen_ocr,
        "scrapear_web": scrapear_web,
        "automatizar_web": automatizar_web,
        # v14.7 Super Agente - Integracion
        "leer_email": leer_email,
        "enviar_email": enviar_email,
        "configurar_email": configurar_email,
        "llamar_api": llamar_api,
        "programar_tarea": programar_tarea,
        "listar_tareas": listar_tareas,
        "leer_portapapeles": leer_portapapeles,
        "escribir_portapapeles": escribir_portapapeles,
        # v15 Super Agente - Visualizacion
        "crear_grafico_avanzado": crear_grafico_avanzado,
        "crear_dashboard": crear_dashboard,
        # v15 Super Agente - Diagramas
        "crear_diagrama": crear_diagrama,
        "generar_mermaid": generar_mermaid,
        # v15 Super Agente - Datos
        "ejecutar_python": ejecutar_python,
        "ejecutar_bash": ejecutar_bash,
        "ejecutar_nodo": ejecutar_nodo,
        "estadisticas": estadisticas,
        "tabla_pivote": tabla_pivote,
        "merge_datos": merge_datos,
        "limpiar_datos": limpiar_datos,
        "transformar_datos": transformar_datos,
        "parsear_datos": parsear_datos,
        "exportar_datos": exportar_datos,
        # v15 Super Agente - Multimedia
        "texto_a_voz": texto_a_voz,
        "generar_imagen": generar_imagen,
        "editar_imagen": editar_imagen,
        "buscar_imagenes": buscar_imagenes,
        "analizar_video": analizar_video,
        # v15 Super Agente - Sub-agentes
        "ejecutar_subagente": ejecutar_subagente,
        "ejecutar_paralelo": ejecutar_paralelo,
        "orquestar": orquestar,
        "listar_subagentes": listar_subagentes,
        "ver_contexto_compartido": ver_contexto_compartido,
        "limpiar_contexto": limpiar_contexto,
        # v15.2 Super Agente - Herramientas avanzadas
        "busqueda_profunda": busqueda_profunda,
        "editar_multiples": editar_multiples,
        "generacion_batch": generacion_batch,
        "buscar_patron": buscar_patron,
        "listar_glob": listar_glob,
        "crear_proyecto_web": crear_proyecto_web,
        "resumir_url": resumir_url,
        # v16 Super Agente - Cloud APIs
        "configurar_api_key": configurar_api_key,
        "listar_api_keys": listar_api_keys,
        "buscar_web_cloud": buscar_web_cloud,
        "generar_imagen_cloud": generar_imagen_cloud,
        "analizar_imagen_cloud": analizar_imagen_cloud,
        "llm_cloud_chat": llm_cloud_chat,
        # v17 Skills nuevos (S5)
        "query_natural_language": query_natural_language,
        "review_code": review_code,
        "resumir_documento": resumir_documento,
        # v17.2 Skills nuevos (S5.4, S5.6, S5.7)
        "extraer_datos": extraer_datos,
        "guardar_conocimiento": guardar_conocimiento,
        "buscar_conocimiento": buscar_conocimiento,
        "listar_conocimiento": listar_conocimiento,
        "notas_reunion": notas_reunion,
    }

    for name, func in submod_tools.items():
        schema = schema_by_name.get(name)
        register_tool(name, func, schema=schema)


# ============================================================
# HERRAMIENTAS INLINE CON DECORATOR @tool
# ============================================================

@tool(schema={
    "type": "function",
    "function": {
        "name": "analizar_imagen",
        "description": "Analiza una imagen usando vision AI. Describe lo que ve, lee texto de la imagen, o responde preguntas sobre ella. Necesita un modelo de vision instalado (llava, llama3.2-vision, etc).",
        "parameters": {
            "type": "object",
            "properties": {
                "ruta": {"type": "string", "description": "Ruta de la imagen a analizar"},
                "pregunta": {"type": "string", "description": "Pregunta sobre la imagen (por defecto: describela)"}
            },
            "required": ["ruta"]
        }
    }
})
def analizar_imagen(ruta: str, pregunta: str = "Describe esta imagen") -> str:
    """Analiza una imagen usando vision AI (cloud o local)."""
    # Intentar cloud primero (mejor calidad)
    cloud_result = analizar_imagen_cloud(ruta, pregunta)
    if cloud_result:
        return cloud_result
    # Fallback: modelo local
    try:
        from llm import ollama
        result = ollama.generate_with_image(pregunta, ruta)
        return result
    except Exception as e:
        return f"ERROR: No se pudo analizar la imagen (ni cloud ni local): {e}"


@tool(schema={
    "type": "function",
    "function": {
        "name": "configurar_perfil",
        "description": "Configura el perfil del usuario para personalizar las respuestas del agente. Se guarda persistentemente entre sesiones. Ejemplo: nombre, rol profesional, intereses, idioma preferido, estilo de respuesta.",
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre del usuario"},
                "rol": {"type": "string", "description": "Rol profesional (ej: desarrollador, arquitecto, estudiante)"},
                "intereses": {"type": "string", "description": "Intereses principales separados por coma"},
                "idioma": {"type": "string", "description": "Idioma preferido (ej: espanol, ingles)"},
                "estilo": {"type": "string", "description": "Estilo de respuesta: conciso, detallado, tecnico, simple"}
            },
            "required": []
        }
    }
})
def configurar_perfil(nombre: str = "", rol: str = "", intereses: str = "",
                      idioma: str = "", estilo: str = "") -> str:
    """Configura el perfil del usuario para personalizar las respuestas del agente."""
    from config import USER_PROFILE_FILE, logger

    profile = {}
    try:
        if os.path.exists(USER_PROFILE_FILE):
            with open(USER_PROFILE_FILE, "r", encoding="utf-8") as f:
                profile = json.load(f)
    except Exception:
        pass

    if nombre: profile["name"] = nombre
    if rol: profile["role"] = rol
    if intereses: profile["interests"] = intereses
    if idioma: profile["language"] = idioma
    if estilo: profile["style"] = estilo

    try:
        with open(USER_PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        logger.info(f"Perfil de usuario actualizado: {list(profile.keys())}")
    except Exception as e:
        return f"ERROR guardando perfil: {e}"

    parts = []
    field_map = {"name": "Nombre", "role": "Rol", "interests": "Intereses",
                 "language": "Idioma", "style": "Estilo"}
    for key, label in field_map.items():
        if key in profile:
            parts.append(f"  {label}: {profile[key]}")

    return f"Perfil configurado:\n" + "\n".join(parts)


@tool(schema={
    "type": "function",
    "function": {
        "name": "crear_nota",
        "description": "Crea una nota rapida y la guarda persistentemente. Usar cuando el usuario pide anotar, recordar algo, o tomar nota de informacion importante.",
        "parameters": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Titulo corto de la nota"},
                "contenido": {"type": "string", "description": "Contenido de la nota"}
            },
            "required": ["titulo", "contenido"]
        }
    }
})
def crear_nota(titulo: str, contenido: str) -> str:
    """Crea una nota rapida y la guarda en la memoria del agente."""
    from config import LEARN_DIR, logger
    from utils.security import sanitize_input

    titulo = sanitize_input(titulo)

    notes_file = os.path.join(LEARN_DIR, "notes.json")
    notes = []
    try:
        if os.path.exists(notes_file):
            with open(notes_file, "r", encoding="utf-8") as f:
                notes = json.load(f)
    except Exception:
        pass

    from datetime import datetime
    note = {
        "id": len(notes) + 1,
        "title": titulo,
        "content": contenido[:1000],
        "created": datetime.now().isoformat(),
    }
    notes.append(note)

    try:
        with open(notes_file, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
        logger.info(f"Nota creada: {titulo}")
    except Exception as e:
        return f"ERROR guardando nota: {e}"

    return f"Nota creada: '{titulo}' (ID: {note['id']})"


@tool(schema={
    "type": "function",
    "function": {
        "name": "planificar_tarea",
        "description": "Descompone una tarea compleja en subtareas ejecutables con dependencias. Genera un plan paso a paso. Usar ANTES de ejecutar tareas complejas como crear apps, proyectos, o analisis multi-paso.",
        "parameters": {
            "type": "object",
            "properties": {
                "tarea": {"type": "string", "description": "Descripcion de la tarea compleja a planificar"}
            },
            "required": ["tarea"]
        }
    }
})
def planificar_tarea(tarea: str) -> str:
    """Descompone una tarea compleja en un plan de subtareas ejecutables."""
    from tools.task_planner import get_planner

    try:
        planner = get_planner()
        plan = planner.smart_decompose(tarea)

        if not plan or not plan.tasks:
            return "ERROR: No se pudo generar un plan para esta tarea."

        # Formatear plan como texto legible
        lines = [f"PLAN: {plan.goal}", f"Total de pasos: {len(plan.tasks)}", ""]

        for i, (task_id, task) in enumerate(plan.tasks.items(), 1):
            priority_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                task.priority.value, "⚪"
            )
            dep_str = ""
            if task.dependencies:
                # Find index of dependency tasks
                dep_indices = []
                for j, (tid, _) in enumerate(plan.tasks.items(), 1):
                    if tid in task.dependencies:
                        dep_indices.append(str(j))
                if dep_indices:
                    dep_str = f" (depende de paso {', '.join(dep_indices)})"

            lines.append(f"  {i}. {priority_icon} {task.title}{dep_str}")
            if task.description:
                lines.append(f"     → {task.description}")

        # Validate plan
        validation = planner.validate_plan(plan)
        if validation["warnings"]:
            lines.append("")
            lines.append("AVISOS:")
            for w in validation["warnings"]:
                lines.append(f"  ⚠ {w}")

        return "\n".join(lines)

    except Exception as e:
        return f"ERROR: No se pudo planificar la tarea: {e}"


@tool(schema={
    "type": "function",
    "function": {
        "name": "ver_notas",
        "description": "Lista las notas guardadas del usuario. Usar cuando el usuario pide ver sus notas o recordar lo que anoto.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
})
def ver_notas() -> str:
    """Lista todas las notas guardadas."""
    from config import LEARN_DIR

    notes_file = os.path.join(LEARN_DIR, "notes.json")
    try:
        if not os.path.exists(notes_file):
            return "No hay notas guardadas."
        with open(notes_file, "r", encoding="utf-8") as f:
            notes = json.load(f)
        if not notes:
            return "No hay notas guardadas."
        result = "NOTAS GUARDADAS:\n"
        for n in notes[-10:]:
            result += f"  [{n.get('id', '?')}] {n.get('title', 'Sin titulo')} - {n.get('content', '')[:80]}\n"
        return result
    except Exception as e:
        return f"ERROR leyendo notas: {e}"


# ============================================================
# REGISTRAR SUB-MODULOS AL FINAL
# ============================================================
_register_submodule_tools()
