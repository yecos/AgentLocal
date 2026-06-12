"""
=============================================================
AGENTE v16 - Skill Loader
=============================================================
Carga dinamicamente los skills desde /skills/ y los registra
como herramientas disponibles en el motor ReAct.

Cada skill tiene un SKILL.md con metadata y scripts en /scripts/.
El loader los parsea y genera herramientas callable.

v16: Nueva arquitectura - Skills como herramientas de primera clase.
=============================================================
"""

import os
import re
import json
import subprocess
import logging
from pathlib import Path
from typing import Optional

from tools.registry import register_tool
from config import logger

# ============================================================
# CONFIGURACION
# ============================================================

# Directorio raiz de skills (2 niveles arriba de agente_v14)
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILLS_ROOT = os.path.normpath(os.path.join(_AGENT_DIR, "..", "skills"))

# Skills que se exponen como herramientas del agente
# Cada entry: skill_dir_name -> tool config
_SKILL_TOOL_MAP = {
    "web-search": {
        "tool_name": "buscar_web_api",
        "description": "Busca en internet usando z-ai-web-dev-sdk. Retorna resultados estructurados con URLs, snippets y metadata. Mas confiable que buscar_web (usa API oficial).",
        "cli_command": "z-ai function -n web_search -a",
        "param_mapping": {"consulta": "query", "num_resultados": "num"},
        "param_types": {"consulta": "string", "num_resultados": "integer"},
        "required": ["consulta"],
    },
    "web-reader": {
        "tool_name": "leer_web_api",
        "description": "Extrae contenido de una pagina web usando z-ai-web-dev-sdk. Retorna titulo, HTML y texto limpio. Mejor que leer_web para paginas complejas.",
        "cli_command": "z-ai function -n web_reader -a",
        "param_mapping": {"url": "url"},
        "param_types": {"url": "string"},
        "required": ["url"],
    },
    "image-generation": {
        "tool_name": "generar_imagen",
        "description": "Genera imagenes a partir de descripcion de texto usando IA. Retorna imagen en base64.",
        "cli_command": "z-ai-generate -p",
        "param_mapping": {"descripcion": "prompt", "tamano": "size", "ruta_destino": "output"},
        "param_types": {"descripcion": "string", "tamano": "string", "ruta_destino": "string"},
        "required": ["descripcion"],
    },
    "image-search": {
        "tool_name": "buscar_imagen",
        "description": "Busca imagenes en internet por descripcion. Retorna URLs directas de imagenes.",
        "cli_command": "z-ai function -n image_search -a",
        "param_mapping": {"consulta": "query", "num_resultados": "num"},
        "param_types": {"consulta": "string", "num_resultados": "integer"},
        "required": ["consulta"],
    },
    "LLM": {
        "tool_name": "consultar_llm",
        "description": "Consulta un LLM externo via z-ai-web-dev-sdk para tareas que requieren razonamiento avanzado, traduccion, resumen, o generacion de texto complejo.",
        "cli_command": "z-ai function -n llm_chat -a",
        "param_mapping": {"mensaje": "message", "sistema": "system_prompt"},
        "param_types": {"mensaje": "string", "sistema": "string"},
        "required": ["mensaje"],
    },
    "VLM": {
        "tool_name": "analizar_imagen_api",
        "description": "Analiza imagenes usando vision AI via z-ai-web-dev-sdk. Puede describir, extraer texto, responder preguntas sobre la imagen.",
        "cli_command": "z-ai function -n vlm_chat -a",
        "param_mapping": {"ruta_imagen": "image_url", "pregunta": "message"},
        "param_types": {"ruta_imagen": "string", "pregunta": "string"},
        "required": ["ruta_imagen", "pregunta"],
    },
    "TTS": {
        "tool_name": "texto_a_voz",
        "description": "Convierte texto a voz usando IA. Genera audio que se puede reproducir o guardar como archivo.",
        "cli_command": "z-ai function -n tts -a",
        "param_mapping": {"texto": "text", "voz": "voice", "velocidad": "speed"},
        "param_types": {"texto": "string", "voz": "string", "velocidad": "number"},
        "required": ["texto"],
    },
    "ASR": {
        "tool_name": "voz_a_texto",
        "description": "Transcribe audio a texto usando IA. Convierte archivos de audio en texto.",
        "cli_command": "z-ai function -n asr -a",
        "param_mapping": {"ruta_audio": "audio_path", "idioma": "language"},
        "param_types": {"ruta_audio": "string", "idioma": "string"},
        "required": ["ruta_audio"],
    },
    "image-edit": {
        "tool_name": "editar_imagen",
        "description": "Edita imagenes existentes usando IA. Puede modificar, transformar o crear variaciones basadas en una imagen y descripcion.",
        "cli_command": "z-ai function -n image_edit -a",
        "param_mapping": {"ruta_imagen": "image_url", "descripcion": "prompt", "tamano": "size"},
        "param_types": {"ruta_imagen": "string", "descripcion": "string", "tamano": "string"},
        "required": ["ruta_imagen", "descripcion"],
    },
    "video-understand": {
        "tool_name": "analizar_video",
        "description": "Analiza contenido de video usando IA. Extrae informacion de frames, describe escenas, entiende secuencias temporales.",
        "cli_command": "z-ai function -n video_understand -a",
        "param_mapping": {"ruta_video": "video_path", "pregunta": "query"},
        "param_types": {"ruta_video": "string", "pregunta": "string"},
        "required": ["ruta_video", "pregunta"],
    },
    "docx": {
        "tool_name": "crear_documento",
        "description": "Crea documentos Word (.docx) profesionales. Reportes, contratos, resumes, documentos academicos y mas.",
        "cli_command": "z-ai function -n docx_create -a",
        "param_mapping": {"tipo": "template", "contenido": "content", "ruta_destino": "output"},
        "param_types": {"tipo": "string", "contenido": "string", "ruta_destino": "string"},
        "required": ["tipo", "contenido"],
    },
    "pdf": {
        "tool_name": "crear_pdf",
        "description": "Crea documentos PDF profesionales. Reportes, presentaciones, documentos formateados.",
        "cli_command": "z-ai function -n pdf_create -a",
        "param_mapping": {"contenido": "content", "ruta_destino": "output"},
        "param_types": {"contenido": "string", "ruta_destino": "string"},
        "required": ["contenido"],
    },
    "pptx": {
        "tool_name": "crear_presentacion",
        "description": "Crea presentaciones PowerPoint (.pptx). Diapositivas con contenido, graficos y diseno profesional.",
        "cli_command": "z-ai function -n pptx_create -a",
        "param_mapping": {"tema": "topic", "diapositivas": "slides", "ruta_destino": "output"},
        "param_types": {"tema": "string", "diapositivas": "string", "ruta_destino": "string"},
        "required": ["tema"],
    },
    "xlsx": {
        "tool_name": "crear_hoja_calculo",
        "description": "Crea hojas de calculo Excel (.xlsx). Tablas de datos, graficos, formulas, reportes financieros.",
        "cli_command": "z-ai function -n xlsx_create -a",
        "param_mapping": {"datos": "data", "ruta_destino": "output"},
        "param_types": {"datos": "string", "ruta_destino": "string"},
        "required": ["datos"],
    },
    "charts": {
        "tool_name": "crear_grafico",
        "description": "Crea graficos y diagramas profesionales. Barras, lineas, pastel, diagramas de flujo, mapas mentales, arquitectura.",
        "cli_command": "z-ai function -n chart_create -a",
        "param_mapping": {"tipo": "chart_type", "datos": "data", "titulo": "title"},
        "param_types": {"tipo": "string", "datos": "string", "titulo": "string"},
        "required": ["tipo", "datos"],
    },
    "agent-browser": {
        "tool_name": "navegar_web",
        "description": "Automatiza un navegador headless. Navega a URLs, hace click, escribe texto, toma screenshots, extrae datos de paginas JavaScript.",
        "cli_command": "z-ai function -n browser_navigate -a",
        "param_mapping": {"url": "url", "accion": "action", "selector": "selector", "valor": "value"},
        "param_types": {"url": "string", "accion": "string", "selector": "string", "valor": "string"},
        "required": ["url"],
    },
}

# Skills que son solo de referencia (no se exponen como herramientas directas)
_REFERENCE_SKILLS = {
    "coding-agent", "fullstack-dev", "skill-creator", "task-review",
    "interview-designer", "blog-writer", "seo-content-writer",
    "resume-builder", "content-strategy", "contentanalysis",
    "finance", "stock-analysis-skill", "market-research-reports",
    "storyboard-manager", "podcast-generate", "video-generation",
    "quiz-mastery", "quiz-html", "study-buddy", "dream-interpreter",
    "get-fortune-analysis", "mindfulness-meditation", "anti-pua",
    "gift-evaluator", "cheat-sheet", "job-intent-tracker",
    "jd-resume-tailor", "interview-prep", "marketing-mode",
    "ui-ux-pro-max", "visual-design-foundations", "writing-plans",
    "version-management", "ai-news-collectors", "aminer-academic-search",
    "aminer-daily-paper", "aminer-free-academic", "qingyan-research",
    "multi-search-engine", "web-shader-extractor", "auto-target-tracker",
    "skill-finder-cn", "image-understand",
}


# ============================================================
# PARSER DE SKILL.MD
# ============================================================

def parse_skill_md(skill_dir: str) -> dict:
    """Parsea un archivo SKILL.md y extrae metadata y capacidades.

    Args:
        skill_dir: Ruta al directorio del skill

    Returns:
        Dict con name, description, scripts, capabilities
    """
    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(skill_md_path):
        return {}

    with open(skill_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Parsear frontmatter
    metadata = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    key, _, val = line.partition(":")
                    metadata[key.strip()] = val.strip()

    # Buscar scripts disponibles
    scripts_dir = os.path.join(skill_dir, "scripts")
    scripts = []
    if os.path.isdir(scripts_dir):
        for f in os.listdir(scripts_dir):
            if f.endswith((".ts", ".js", ".sh", ".py")):
                scripts.append(os.path.join(scripts_dir, f))

    return {
        "name": metadata.get("name", os.path.basename(skill_dir)),
        "description": metadata.get("description", ""),
        "scripts": scripts,
        "path": skill_dir,
        "has_cli": _detect_cli_capability(content),
    }


def _detect_cli_capability(content: str) -> bool:
    """Detecta si el skill menciona comandos CLI de z-ai."""
    cli_patterns = ["z-ai function", "z-ai-generate", "z-ai function"]
    return any(p in content for p in cli_patterns)


# ============================================================
# EJECUTOR DE SKILLS
# ============================================================

def _execute_skill_tool(tool_name: str, params: dict, config: dict) -> str:
    """Ejecuta un skill como herramienta via CLI.

    Args:
        tool_name: Nombre de la herramienta
        params: Parametros proporcionados por el agente
        config: Configuracion del skill desde _SKILL_TOOL_MAP

    Returns:
        Resultado de la ejecucion como string
    """
    import subprocess
    import shlex

    try:
        # Mapear parametros del agente a parametros del CLI
        param_mapping = config.get("param_mapping", {})
        mapped_params = {}
        for agent_param, cli_param in param_mapping.items():
            if agent_param in params:
                mapped_params[cli_param] = params[agent_param]

        # Construir comando
        cli_command = config.get("cli_command", "")

        if "z-ai function" in cli_command:
            # Formato: z-ai function -n <name> -a '<json>'
            json_args = json.dumps(mapped_params, ensure_ascii=False)
            cmd = f"{cli_command} '{json_args}'"
        elif "z-ai-generate" in cli_command:
            # Formato: z-ai-generate -p "<prompt>" -o "<output>" -s "<size>"
            prompt = mapped_params.get("prompt", "")
            output = mapped_params.get("output", "")
            size = mapped_params.get("size", "1024x1024")
            cmd = f'z-ai-generate -p "{prompt}"'
            if output:
                cmd += f' -o "{output}"'
            cmd += f' -s {size}'
        else:
            # Fallback generico
            json_args = json.dumps(mapped_params, ensure_ascii=False)
            cmd = f"{cli_command} '{json_args}'"

        logger.info(f"[SkillLoader] Ejecutando: {cmd[:200]}")

        # Ejecutar con timeout
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=_SKILLS_ROOT,
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode != 0:
            if error:
                return f"ERROR en {tool_name}: {error[:500]}"
            return f"ERROR en {tool_name}: comando fallo con codigo {result.returncode}"

        # Truncar salida muy larga
        if len(output) > 3000:
            output = output[:3000] + "\n... [truncado]"

        return output if output else "Comando ejecutado exitosamente (sin salida)"

    except subprocess.TimeoutExpired:
        return f"ERROR en {tool_name}: timeout (120s)"
    except Exception as e:
        return f"ERROR en {tool_name}: {str(e)}"


# ============================================================
# GENERADOR DE FUNCIONES TOOL
# ============================================================

def _make_skill_tool_func(tool_name: str, config: dict):
    """Crea una funcion callable que ejecuta un skill via CLI.

    Args:
        tool_name: Nombre de la herramienta
        config: Configuracion del skill

    Returns:
        Funcion callable con la firma correcta
    """
    def skill_tool_func(**kwargs) -> str:
        """Ejecuta un skill como herramienta del agente."""
        return _execute_skill_tool(tool_name, kwargs, config)

    # Asignar nombre y docstring
    skill_tool_func.__name__ = tool_name
    desc = config.get("description", f"Ejecuta el skill {tool_name}")
    skill_tool_func.__doc__ = desc

    return skill_tool_func


def _build_skill_schema(tool_name: str, config: dict) -> dict:
    """Construye el schema de function calling para un skill.

    Args:
        tool_name: Nombre de la herramienta
        config: Configuracion del skill

    Returns:
        Schema en formato Ollama function calling
    """
    param_mapping = config.get("param_mapping", {})
    param_types = config.get("param_types", {})
    required = config.get("required", [])

    properties = {}
    for agent_param, cli_param in param_mapping.items():
        json_type = param_types.get(agent_param, "string")
        prop = {
            "type": json_type,
            "description": f"Parametro {agent_param} (mapeado a {cli_param})"
        }
        properties[agent_param] = prop

    schema = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": config.get("description", f"Ejecuta skill {tool_name}"),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        }
    }

    return schema


# ============================================================
# LOADER PRINCIPAL
# ============================================================

_loaded_skills = {}
_load_errors = []


def load_all_skills() -> dict:
    """Carga todos los skills disponibles y los registra como herramientas.

    Returns:
        Dict con resumen de carga: {loaded: int, errors: int, skills: list}
    """
    global _loaded_skills, _load_errors
    _loaded_skills = {}
    _load_errors = []

    if not os.path.isdir(_SKILLS_ROOT):
        _load_errors.append(f"Directorio de skills no encontrado: {_SKILLS_ROOT}")
        return {"loaded": 0, "errors": 1, "skills": []}

    # Cargar skills con tool mapping
    for skill_dir_name, config in _SKILL_TOOL_MAP.items():
        skill_dir = os.path.join(_SKILLS_ROOT, skill_dir_name)
        tool_name = config["tool_name"]

        try:
            # Parsear SKILL.md si existe
            skill_info = parse_skill_md(skill_dir) if os.path.isdir(skill_dir) else {}
            _loaded_skills[tool_name] = {
                "config": config,
                "info": skill_info,
                "dir": skill_dir,
            }

            # Crear funcion y schema
            func = _make_skill_tool_func(tool_name, config)
            schema = _build_skill_schema(tool_name, config)

            # Registrar en el registry global
            register_tool(tool_name, func, schema=schema)

            logger.info(f"[SkillLoader] Registrado: {tool_name} <- {skill_dir_name}")

        except Exception as e:
            _load_errors.append(f"{tool_name}: {str(e)}")
            logger.error(f"[SkillLoader] Error cargando {skill_dir_name}: {e}")

    # Cargar skills de referencia (solo metadata, no herramientas)
    for skill_dir_name in _REFERENCE_SKILLS:
        skill_dir = os.path.join(_SKILLS_ROOT, skill_dir_name)
        if os.path.isdir(skill_dir):
            try:
                skill_info = parse_skill_md(skill_dir)
                _loaded_skills[skill_dir_name] = {
                    "config": None,
                    "info": skill_info,
                    "dir": skill_dir,
                    "is_reference": True,
                }
            except Exception as e:
                _load_errors.append(f"{skill_dir_name} (ref): {str(e)}")

    loaded_count = sum(1 for v in _loaded_skills.values() if v.get("config"))
    ref_count = sum(1 for v in _loaded_skills.values() if v.get("is_reference"))

    logger.info(
        f"[SkillLoader] Carga completa: {loaded_count} herramientas, "
        f"{ref_count} referencia, {_load_errors.__len__()} errores"
    )

    return {
        "loaded": loaded_count,
        "reference": ref_count,
        "errors": len(_load_errors),
        "skills": list(_loaded_skills.keys()),
        "error_details": _load_errors,
    }


def get_skill_info(tool_name: str) -> Optional[dict]:
    """Retorna informacion de un skill cargado.

    Args:
        tool_name: Nombre de la herramienta

    Returns:
        Dict con info del skill o None
    """
    return _loaded_skills.get(tool_name)


def list_available_skills() -> list:
    """Lista todos los skills disponibles (herramientas + referencia).

    Returns:
        Lista de dicts con name, description, is_tool
    """
    result = []
    for name, data in _loaded_skills.items():
        result.append({
            "name": name,
            "description": data.get("info", {}).get("description", ""),
            "is_tool": data.get("config") is not None,
            "is_reference": data.get("is_reference", False),
        })
    return result


def get_skills_status() -> dict:
    """Retorna el estado del sistema de skills.

    Returns:
        Dict con estadisticas de carga
    """
    tool_count = sum(1 for v in _loaded_skills.values() if v.get("config"))
    ref_count = sum(1 for v in _loaded_skills.values() if v.get("is_reference"))
    return {
        "total_skills": len(_loaded_skills),
        "tool_skills": tool_count,
        "reference_skills": ref_count,
        "errors": len(_load_errors),
        "skills_root": _SKILLS_ROOT,
        "loaded": bool(_loaded_skills),
    }
