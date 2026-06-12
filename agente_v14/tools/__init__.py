"""
Registro centralizado de herramientas.
El agente importa TOOL_FUNCTIONS y TOOL_SCHEMAS desde aqui.

v16: + Skill Loader, Task Planner, Code Executor, File Editor,
     Git Tool, Database Tool, Error Recovery.
v14.5: Usa registry.py con decorator @tool para registro automatico.
Las herramientas de sub-modulos se registran manualmente con register_tool()
hasta que se migren al decorator. Las herramientas inline usan @tool.
"""
import os
import json

# Importar el registry
from .registry import tool, register_tool, TOOL_FUNCTIONS, TOOL_SCHEMAS

# Importar herramientas de sub-modulos
from .sistema import ejecutar_comando, procesos_activos, matar_proceso
from .archivos import leer_archivo, escribir_archivo, listar_archivos, buscar_en_archivos
from .apps import abrir_aplicacion, abrir_url, buscar_youtube
from .proyecto import analizar_proyecto, clonar_repositorio, instalar_dependencias
from .codigo import generar_codigo
from .web import buscar_web, leer_web, buscar_web_profundo

# Importar schemas predefinidos (para herramientas de sub-modulos)
from .schemas import TOOL_SCHEMAS as _SCHEMAS_FROM_FILE


# ============================================================
# REGISTRAR HERRAMIENTAS DE SUB-MODULOS
# (Se usa register_tool manual hasta migrar esos archivos a @tool)
# ============================================================

def _register_submodule_tools():
    """Registra las herramientas importadas de sub-modulos con sus schemas."""
    # Mapeo nombre -> (funcion, schema)
    # Los schemas se toman del archivo schemas.py preexistente
    schema_by_name = {}
    for s in _SCHEMAS_FROM_FILE:
        func_info = s.get("function", {})
        name = func_info.get("name")
        if name:
            schema_by_name[name] = s

    submod_tools = {
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
        "leer_web": leer_web,
        "buscar_web_profundo": buscar_web_profundo,
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
    """Analiza una imagen usando el modelo de vision del LLM."""
    from llm import ollama
    result = ollama.generate_with_image(pregunta, ruta)
    return result


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
    """Configura el perfil del usuario para personalizar las respuestas del agente.

    Args:
        nombre: Nombre del usuario
        rol: Rol profesional (ej: desarrollador, arquitecto, estudiante)
        intereses: Intereses principales separados por coma
        idioma: Idioma preferido para respuestas (ej: espanol, ingles)
        estilo: Estilo de respuesta (conciso, detallado, tecnico, simple)
    """
    from config import USER_PROFILE_FILE, logger

    # Cargar perfil existente
    profile = {}
    try:
        if os.path.exists(USER_PROFILE_FILE):
            with open(USER_PROFILE_FILE, "r", encoding="utf-8") as f:
                profile = json.load(f)
    except Exception:
        pass

    # Actualizar solo los campos proporcionados
    if nombre:
        profile["name"] = nombre
    if rol:
        profile["role"] = rol
    if intereses:
        profile["interests"] = intereses
    if idioma:
        profile["language"] = idioma
    if estilo:
        profile["style"] = estilo

    # Guardar perfil
    try:
        with open(USER_PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        logger.info(f"Perfil de usuario actualizado: {list(profile.keys())}")
    except Exception as e:
        return f"ERROR guardando perfil: {e}"

    # Formatear resumen
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
    """Crea una nota rapida y la guarda en la memoria del agente.

    Args:
        titulo: Titulo de la nota
        contenido: Contenido de la nota
    """
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
        for n in notes[-10:]:  # Ultimas 10
            result += f"  [{n.get('id', '?')}] {n.get('title', 'Sin titulo')} - {n.get('content', '')[:80]}\n"
        return result
    except Exception as e:
        return f"ERROR leyendo notas: {e}"


# ============================================================
# HERRAMIENTAS v16 - NUEVAS CAPACIDADES AGENTICAS
# ============================================================

# --- Ejecucion de Codigo ---

@tool(schema={
    "type": "function",
    "function": {
        "name": "ejecutar_codigo",
        "description": "Ejecuta codigo de forma segura con captura de stdout/stderr y timeout. Soporta Python, JavaScript, TypeScript, Bash. Retorna resultado con exit code, output, y errores.",
        "parameters": {
            "type": "object",
            "properties": {
                "codigo": {"type": "string", "description": "Codigo fuente a ejecutar"},
                "lenguaje": {"type": "string", "description": "Lenguaje: python, javascript, typescript, bash"},
                "timeout": {"type": "integer", "description": "Timeout en segundos (default: 60)"},
                "directorio_trabajo": {"type": "string", "description": "Directorio de trabajo (opcional)"}
            },
            "required": ["codigo", "lenguaje"]
        }
    }
})
def ejecutar_codigo(codigo: str, lenguaje: str = "python", timeout: int = 60,
                    directorio_trabajo: str = "") -> str:
    """Ejecuta codigo de forma segura con captura de output."""
    from .code_executor import execute_code
    result = execute_code(
        code=codigo,
        language=lenguaje,
        timeout=timeout,
        working_dir=directorio_trabajo or None,
    )
    output = []
    if result.success:
        output.append(f"EXITO (exit code: {result.exit_code}, tiempo: {result.duration:.2f}s)")
    else:
        output.append(f"ERROR (exit code: {result.exit_code}, tiempo: {result.duration:.2f}s)")
    if result.stdout:
        output.append(f"STDOUT:\n{result.stdout[:2000]}")
    if result.stderr:
        output.append(f"STDERR:\n{result.stderr[:1000]}")
    return "\n".join(output) if output else "Sin salida"


@tool(schema={
    "type": "function",
    "function": {
        "name": "ejecutar_archivo",
        "description": "Ejecuta un archivo existente (.py, .js, .ts, .sh) de forma segura con timeout y captura de output.",
        "parameters": {
            "type": "object",
            "properties": {
                "ruta": {"type": "string", "description": "Ruta al archivo a ejecutar"},
                "timeout": {"type": "integer", "description": "Timeout en segundos (default: 60)"},
                "argumentos": {"type": "string", "description": "Argumentos adicionales separados por espacio"}
            },
            "required": ["ruta"]
        }
    }
})
def ejecutar_archivo(ruta: str, timeout: int = 60, argumentos: str = "") -> str:
    """Ejecuta un archivo existente de forma segura."""
    from .code_executor import execute_file
    args = argumentos.split() if argumentos else None
    result = execute_file(filepath=ruta, timeout=timeout, args=args)
    output = []
    if result.success:
        output.append(f"EXITO (tiempo: {result.duration:.2f}s)")
    else:
        output.append(f"ERROR (exit code: {result.exit_code}, tiempo: {result.duration:.2f}s)")
    if result.stdout:
        output.append(f"STDOUT:\n{result.stdout[:2000]}")
    if result.stderr:
        output.append(f"STDERR:\n{result.stderr[:1000]}")
    return "\n".join(output) if output else "Sin salida"


@tool(schema={
    "type": "function",
    "function": {
        "name": "ejecutar_tests",
        "description": "Ejecuta los tests de un proyecto. Auto-detecta el framework (pytest, jest, vitest, mocha). Retorna resultados con passed/failed counts.",
        "parameters": {
            "type": "object",
            "properties": {
                "ruta_proyecto": {"type": "string", "description": "Ruta al proyecto"},
                "framework": {"type": "string", "description": "Framework de tests: pytest, jest, vitest, mocha (auto-detectar si vacio)"},
                "ruta_test": {"type": "string", "description": "Ruta especifica de test (opcional)"},
                "timeout": {"type": "integer", "description": "Timeout en segundos (default: 120)"}
            },
            "required": ["ruta_proyecto"]
        }
    }
})
def ejecutar_tests(ruta_proyecto: str, framework: str = "", ruta_test: str = "",
                   timeout: int = 120) -> str:
    """Ejecuta los tests de un proyecto."""
    from .code_executor import run_tests
    result = run_tests(
        project_path=ruta_proyecto,
        test_framework=framework or None,
        test_path=ruta_test or None,
        timeout=timeout,
    )
    output = []
    if result.success:
        output.append(f"TESTS PASARON (tiempo: {result.duration:.2f}s)")
    else:
        output.append(f"TESTS FALLARON (exit code: {result.exit_code}, tiempo: {result.duration:.2f}s)")
    if result.stdout:
        output.append(result.stdout[:3000])
    if result.stderr and not result.success:
        output.append(f"ERRORES:\n{result.stderr[:1000]}")
    return "\n".join(output) if output else "Sin salida"


# --- Edicion Incremental de Archivos ---

@tool(schema={
    "type": "function",
    "function": {
        "name": "buscar_reemplazar",
        "description": "Busca y reemplaza texto en un archivo sin reescribirlo completo. Crea backup automatico. Soporta regex. Mas eficiente que escribir_archivo para ediciones pequenas.",
        "parameters": {
            "type": "object",
            "properties": {
                "ruta": {"type": "string", "description": "Ruta del archivo"},
                "buscar": {"type": "string", "description": "Texto o patron a buscar"},
                "reemplazar": {"type": "string", "description": "Texto de reemplazo"},
                "usar_regex": {"type": "boolean", "description": "Usar expresiones regulares (default: false)"},
                "case_sensitive": {"type": "boolean", "description": "Busqueda sensible a mayusculas (default: true)"},
                "max_reemplazos": {"type": "integer", "description": "Maximo de reemplazos (0 = todos)"}
            },
            "required": ["ruta", "buscar", "reemplazar"]
        }
    }
})
def buscar_reemplazar(ruta: str, buscar: str, reemplazar: str,
                      usar_regex: bool = False, case_sensitive: bool = True,
                      max_reemplazos: int = 0) -> str:
    """Busca y reemplaza texto en un archivo de forma incremental."""
    from .file_editor import search_and_replace
    result = search_and_replace(
        filepath=ruta, search=buscar, replace=reemplazar,
        use_regex=usar_regex, case_sensitive=case_sensitive,
        max_replacements=max_reemplazos,
    )
    if result["success"]:
        msg = result.get("message", "OK")
        if result.get("diff"):
            return f"{msg}\n\nDiff:\n{result['diff'][:1000]}"
        return msg
    return f"ERROR: {result.get('error', 'Error desconocido')}"


@tool(schema={
    "type": "function",
    "function": {
        "name": "editar_lineas",
        "description": "Reemplaza un rango de lineas en un archivo. Mas preciso que buscar_reemplazar para cambios en lineas especificas. Crea backup automatico.",
        "parameters": {
            "type": "object",
            "properties": {
                "ruta": {"type": "string", "description": "Ruta del archivo"},
                "linea_inicio": {"type": "integer", "description": "Linea de inicio (1-indexed, inclusiva)"},
                "linea_fin": {"type": "integer", "description": "Linea de fin (1-indexed, inclusiva)"},
                "nuevo_contenido": {"type": "string", "description": "Nuevo contenido para el rango de lineas"}
            },
            "required": ["ruta", "linea_inicio", "linea_fin", "nuevo_contenido"]
        }
    }
})
def editar_lineas(ruta: str, linea_inicio: int, linea_fin: int,
                  nuevo_contenido: str) -> str:
    """Reemplaza un rango de lineas en un archivo."""
    from .file_editor import edit_lines
    result = edit_lines(
        filepath=ruta, start_line=linea_inicio, end_line=linea_fin,
        new_content=nuevo_contenido,
    )
    if result["success"]:
        msg = result.get("message", "OK")
        if result.get("diff"):
            return f"{msg}\n\nDiff:\n{result['diff'][:1000]}"
        return msg
    return f"ERROR: {result.get('error', 'Error desconocido')}"


@tool(schema={
    "type": "function",
    "function": {
        "name": "insertar_en_linea",
        "description": "Inserta contenido antes o despues de una linea especifica en un archivo. No reemplaza lineas existentes.",
        "parameters": {
            "type": "object",
            "properties": {
                "ruta": {"type": "string", "description": "Ruta del archivo"},
                "linea": {"type": "integer", "description": "Numero de linea de referencia (1-indexed)"},
                "contenido": {"type": "string", "description": "Contenido a insertar"},
                "posicion": {"type": "string", "description": "Posicion: 'before' o 'after' (default: 'after')"}
            },
            "required": ["ruta", "linea", "contenido"]
        }
    }
})
def insertar_en_linea(ruta: str, linea: int, contenido: str,
                      posicion: str = "after") -> str:
    """Inserta contenido en una posicion especifica del archivo."""
    from .file_editor import insert_at_line
    result = insert_at_line(
        filepath=ruta, line_number=linea, content=contenido, position=posicion,
    )
    if result["success"]:
        return result.get("message", "OK")
    return f"ERROR: {result.get('error', 'Error desconocido')}"


# --- Git Tool ---

@tool(schema={
    "type": "function",
    "function": {
        "name": "git_operacion",
        "description": "Ejecuta operaciones Git de forma estructurada. Soporta: status, diff, add, commit, branch, log, push, pull, stash, init. No usa ejecutar_comando — parsea y valida cada operacion.",
        "parameters": {
            "type": "object",
            "properties": {
                "operacion": {"type": "string", "description": "Operacion: status, diff, add, commit, branch, log, push, pull, stash, init"},
                "ruta_repo": {"type": "string", "description": "Ruta al repositorio (default: directorio de trabajo)"},
                "mensaje": {"type": "string", "description": "Mensaje para commit o stash"},
                "branch": {"type": "string", "description": "Nombre del branch (para branch/push/pull)"},
                "archivos": {"type": "string", "description": "Archivos para add (separados por coma, o 'all')"},
                "accion_branch": {"type": "string", "description": "Para branch: list, create, switch, delete"},
                "accion_stash": {"type": "string", "description": "Para stash: save, list, pop, drop"},
                "staged": {"type": "boolean", "description": "Para diff: mostrar solo staged (default: false)"},
                "count": {"type": "integer", "description": "Para log: numero de commits (default: 10)"}
            },
            "required": ["operacion"]
        }
    }
})
def git_operacion(operacion: str, ruta_repo: str = "", mensaje: str = "",
                  branch: str = "", archivos: str = "",
                  accion_branch: str = "list", accion_stash: str = "save",
                  staged: bool = False, count: int = 10) -> str:
    """Ejecuta operaciones Git de forma estructurada."""
    from . import git_tool as gt

    path = ruta_repo or None
    op = operacion.lower().strip()

    if op == "status":
        result = gt.git_status(path)
    elif op == "diff":
        result = gt.git_diff(path, staged=staged)
    elif op == "add":
        files = [f.strip() for f in archivos.split(",")] if archivos and archivos != "all" else None
        result = gt.git_add(path, files=files, all_changes=archivos == "all" or not archivos)
    elif op == "commit":
        result = gt.git_commit(path, message=mensaje or None, add_all=False)
    elif op == "branch":
        result = gt.git_branch(path, action=accion_branch, branch_name=branch or None)
    elif op == "log":
        result = gt.git_log(path, count=count)
    elif op == "push":
        result = gt.git_push(path, branch=branch or None)
    elif op == "pull":
        result = gt.git_pull(path, branch=branch or None)
    elif op == "stash":
        result = gt.git_stash(path, action=accion_stash, message=mensaje)
    elif op == "init":
        result = gt.git_init(path)
    else:
        return f"Operacion no soportada: {op}. Usa: status, diff, add, commit, branch, log, push, pull, stash, init"

    if result.get("success"):
        # Formatear resultado para el agente
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)[:2000]
    return f"ERROR: {result.get('error', 'Error desconocido')}"


# --- Database Tool ---

@tool(schema={
    "type": "function",
    "function": {
        "name": "base_de_datos",
        "description": "Operaciones de base de datos: conectar, consultar, listar tablas, describir estructura, crear tablas, exportar datos. Soporta SQLite, PostgreSQL, MySQL.",
        "parameters": {
            "type": "object",
            "properties": {
                "accion": {"type": "string", "description": "Accion: conectar, consultar, tablas, describir, crear_tabla, exportar"},
                "ruta_db": {"type": "string", "description": "Ruta a la base de datos (SQLite) o connection string"},
                "tipo_db": {"type": "string", "description": "Tipo: sqlite, postgres, mysql (default: sqlite)"},
                "query": {"type": "string", "description": "Query SQL (para accion=consultar)"},
                "tabla": {"type": "string", "description": "Nombre de tabla (para describir, exportar, crear_tabla)"},
                "columnas": {"type": "string", "description": "Columnas para crear_tabla en formato JSON: [{name, type, primary_key}]"},
                "formato_exportacion": {"type": "string", "description": "Formato para exportar: json o csv (default: json)"},
                "limit": {"type": "integer", "description": "Maximo de filas a retornar (default: 100)"}
            },
            "required": ["accion"]
        }
    }
})
def base_de_datos(accion: str, ruta_db: str = "", tipo_db: str = "sqlite",
                  query: str = "", tabla: str = "", columnas: str = "",
                  formato_exportacion: str = "json", limit: int = 100) -> str:
    """Operaciones de base de datos."""
    from . import database_tool as db

    accion = accion.lower().strip()

    if accion == "conectar":
        result = db.db_connect(ruta_db or ":memory:", tipo_db)
    elif accion == "consultar":
        if not query:
            return "ERROR: Se requiere query SQL"
        result = db.db_query(query, db_path=ruta_db or None, limit=limit)
    elif accion == "tablas":
        result = db.db_tables(db_path=ruta_db or None)
    elif accion == "describir":
        if not tabla:
            return "ERROR: Se requiere nombre de tabla"
        result = db.db_describe(tabla, db_path=ruta_db or None)
    elif accion == "crear_tabla":
        if not tabla or not columnas:
            return "ERROR: Se requiere nombre de tabla y columnas (JSON)"
        try:
            cols = json.loads(columnas)
        except Exception:
            return "ERROR: columnas debe ser JSON valido: [{\"name\": \"id\", \"type\": \"INTEGER\", \"primary_key\": true}]"
        result = db.db_create_table(tabla, cols, db_path=ruta_db or None)
    elif accion == "exportar":
        if not tabla:
            return "ERROR: Se requiere nombre de tabla"
        result = db.db_export(tabla, output_format=formato_exportacion, db_path=ruta_db or None)
    else:
        return f"Accion no soportada: {accion}. Usa: conectar, consultar, tablas, describir, crear_tabla, exportar"

    if result.get("success"):
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)[:2000]
    return f"ERROR: {result.get('error', 'Error desconocido')}"


# --- Task Planner ---

@tool(schema={
    "type": "function",
    "function": {
        "name": "planificar_tarea",
        "description": "Descompone una tarea compleja en subtareas ejecutables con dependencias. Usa templates para tareas comunes (web_app, script, automation, analysis). Retorna un plan con progreso.",
        "parameters": {
            "type": "object",
            "properties": {
                "objetivo": {"type": "string", "description": "Objetivo o tarea compleja a descomponer"},
                "tipo": {"type": "string", "description": "Tipo de tarea: web_app, script, automation, analysis, project_setup (auto-detectar si vacio)"},
                "avanzar": {"type": "boolean", "description": "Si true, marca la tarea actual como completada y avanza a la siguiente"},
                "resultado_tarea": {"type": "string", "description": "Resultado de la tarea actual (para avanzar)"},
                "ver_progreso": {"type": "boolean", "description": "Si true, muestra el progreso del plan actual"}
            },
            "required": ["objetivo"]
        }
    }
})
def planificar_tarea(objetivo: str, tipo: str = "", avanzar: bool = False,
                     resultado_tarea: str = "", ver_progreso: bool = False) -> str:
    """Descompone tareas complejas en subtareas ejecutables."""
    from .task_planner import get_planner

    planner = get_planner()

    if ver_progreso:
        progress = planner.get_progress()
        return json.dumps(progress, ensure_ascii=False, indent=2)

    if avanzar:
        next_task = planner.advance_plan(resultado_tarea)
        if next_task:
            return json.dumps({
                "message": "Tarea completada. Siguiente tarea:",
                "task": next_task.to_dict(),
                "progress": planner.get_progress(),
            }, ensure_ascii=False, indent=2, default=str)
        else:
            return json.dumps({
                "message": "Plan completado o no hay mas tareas",
                "progress": planner.get_progress(),
            }, ensure_ascii=False, indent=2)

    # Crear nuevo plan
    plan = planner.create_plan(objetivo, task_type=tipo or None)
    return json.dumps({
        "plan_id": plan.id,
        "goal": plan.goal,
        "total_tasks": len(plan.tasks),
        "first_task": plan.get_next_task().to_dict() if plan.get_next_task() else None,
        "all_tasks": [t.to_dict() for t in plan.tasks.values()],
    }, ensure_ascii=False, indent=2, default=str)


# --- Error Recovery ---

@tool(schema={
    "type": "function",
    "function": {
        "name": "diagnosticar_error",
        "description": "Diagnostica un error y sugiere correcciones automaticas. Clasifica el error, identifica causa raiz, y propone pasos de recuperacion.",
        "parameters": {
            "type": "object",
            "properties": {
                "mensaje_error": {"type": "string", "description": "Mensaje de error a diagnosticar"},
                "herramienta": {"type": "string", "description": "Nombre de la herramienta que fallo (opcional)"},
                "contexto": {"type": "string", "description": "Contexto adicional en formato JSON (opcional)"}
            },
            "required": ["mensaje_error"]
        }
    }
})
def diagnosticar_error(mensaje_error: str, herramienta: str = "",
                       contexto: str = "") -> str:
    """Diagnostica un error y sugiere correcciones."""
    from .error_recovery import diagnose_error

    ctx = {}
    if contexto:
        try:
            ctx = json.loads(contexto)
        except Exception:
            ctx = {"raw_context": contexto}

    result = diagnose_error(mensaje_error, herramienta, ctx)
    return json.dumps(result, ensure_ascii=False, indent=2)


# --- Browser Automation (Playwright) ---

@tool(schema={
    "type": "function",
    "function": {
        "name": "navegador_web",
        "description": "Automatiza un navegador web real con Playwright. Navega, hace click, escribe, toma screenshots, extrae datos, llena formularios, ejecuta JavaScript. Mucho mas potente que abrir_url o navegar_web.",
        "parameters": {
            "type": "object",
            "properties": {
                "accion": {"type": "string", "description": "Accion: navigate, click, type, screenshot, extract, fill_form, wait, scroll, evaluate, pdf, download, get_page_info, start, stop"},
                "url": {"type": "string", "description": "URL para navigate/download"},
                "selector": {"type": "string", "description": "Selector CSS del elemento (para click, type, extract, wait)"},
                "texto": {"type": "string", "description": "Texto a escribir (para type)"},
                "tipo_extract": {"type": "string", "description": "Tipo de extraccion: text, html, href, src, value, all_links, all_images (default: text)"},
                "campos_formulario": {"type": "string", "description": "Campos para fill_form en JSON: [{selector, value}]"},
                "direccion_scroll": {"type": "string", "description": "Direccion scroll: up, down, left, right (default: down)"},
                "script_js": {"type": "string", "description": "JavaScript a ejecutar (para evaluate)"},
                "completa": {"type": "boolean", "description": "Screenshot completa (default: false)"},
                "esperar": {"type": "integer", "description": "Timeout en milisegundos (default: 5000)"},
                "presionar_enter": {"type": "boolean", "description": "Presionar Enter despues de escribir (default: false)"},
                "ruta_destino": {"type": "string", "description": "Ruta de destino para pdf/download"}
            },
            "required": ["accion"]
        }
    }
})
def navegador_web(accion: str, url: str = "", selector: str = "", texto: str = "",
                  tipo_extract: str = "text", campos_formulario: str = "",
                  direccion_scroll: str = "down", script_js: str = "",
                  completa: bool = False, esperar: int = 5000,
                  presionar_enter: bool = False, ruta_destino: str = "") -> str:
    """Automatiza un navegador web real con Playwright."""
    from .browser_automation import browser_automation
    return browser_automation(
        accion=accion,
        url=url,
        selector=selector,
        text=texto,
        extract_type=tipo_extract,
        fields_json=campos_formulario,
        direction=direccion_scroll,
        script=script_js,
        full_page=completa,
        timeout=esperar,
        press_enter=presionar_enter,
        output_path=ruta_destino,
    )


# --- Docker Sandbox ---

@tool(schema={
    "type": "function",
    "function": {
        "name": "ejecutar_en_contenedor",
        "description": "Ejecuta codigo dentro de un contenedor Docker aislado. Mas seguro que ejecutar_codigo. Si Docker no esta disponible, hace fallback al sandbox local automaticamente.",
        "parameters": {
            "type": "object",
            "properties": {
                "codigo": {"type": "string", "description": "Codigo fuente a ejecutar"},
                "lenguaje": {"type": "string", "description": "Lenguaje: python, javascript, bash (default: python)"},
                "timeout": {"type": "integer", "description": "Timeout en segundos (default: 60)"},
                "permitir_red": {"type": "boolean", "description": "Permitir acceso a red en el contenedor (default: false)"},
                "directorio_trabajo": {"type": "string", "description": "Directorio de trabajo montado en el contenedor (opcional)"}
            },
            "required": ["codigo"]
        }
    }
})
def ejecutar_en_contenedor(codigo: str, lenguaje: str = "python", timeout: int = 60,
                           permitir_red: bool = False, directorio_trabajo: str = "") -> str:
    """Ejecuta codigo dentro de un contenedor Docker aislado."""
    from .docker_sandbox import execute_in_container
    result = execute_in_container(
        code=codigo,
        language=lenguaje,
        timeout=timeout,
        working_dir=directorio_trabajo or None,
        allow_network=permitir_red,
    )
    if result.get("success"):
        output = f"EXITO (docker, tiempo: {result.get('duration', 0):.2f}s)"
        if result.get("stdout"):
            output += f"\nSTDOUT:\n{result['stdout'][:2000]}"
        return output
    else:
        output = f"ERROR (docker, exit code: {result.get('exit_code', -1)})"
        if result.get("stderr"):
            output += f"\nSTDERR:\n{result['stderr'][:1000]}"
        return output


# ============================================================
# CARGAR SKILLS DINAMICAMENTE
# ============================================================

def load_skills():
    """Carga los skills disponibles como herramientas del agente."""
    try:
        from .skill_loader import load_all_skills
        result = load_all_skills()
        logger.info(f"[Tools] Skills cargados: {result['loaded']} herramientas, {result.get('reference', 0)} referencia")
        return result
    except Exception as e:
        logger.warning(f"[Tools] Error cargando skills: {e}")
        return {"loaded": 0, "errors": 1, "error_details": [str(e)]}


# ============================================================
# REGISTRAR SUB-MODULOS AL FINAL
# (Debe ejecutarse despues de que registry.py tenga sus dicts limpios
#  y despues de definir las herramientas inline con @tool)
# ============================================================
_register_submodule_tools()

# Cargar skills al importar (si es posible)
try:
    load_skills()
except Exception:
    pass
