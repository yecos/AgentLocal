"""
=============================================================
AGENTE v16.2 - Skill Loader
=============================================================
Carga dinamicamente los skills desde /skills/ y los registra
como herramientas disponibles en el motor ReAct.

Cada skill tiene un SKILL.md con metadata y scripts en /scripts/.
El loader los parsea y genera herramientas callable.

v16.2: Validacion de z-ai CLI al startup + fallback graceful.
       Las herramientas que dependen de z-ai se marcan como
       disponibles/no-disponibles segun la presencia del CLI.
       Si z-ai no esta instalado, las herramientas no se registran
       y se loguea un warning claro en vez de fallar silenciosamente.
v16.1: Carga de conocimiento de referencia - Los skills de referencia
       ahora proveen contexto enriquecido para el agente, no solo metadata.
v16: Nueva arquitectura - Skills como herramientas de primera clase.
=============================================================
"""

import os
import re
import json
import subprocess
import logging
import shutil
from pathlib import Path
from typing import Optional

from tools.registry import register_tool
from config import logger

# ============================================================
# VALIDACION DE Z-AI CLI
# ============================================================

def _check_zai_cli_available() -> tuple[bool, str]:
    """Verifica si el CLI z-ai esta disponible en el sistema.

    Returns:
        (available, version_or_reason) tuple.
        Si disponible, version_or_reason contiene la version.
        Si no, contiene la razon de la falta.
    """
    # 1. Verificar si z-ai esta en PATH
    zai_path = shutil.which("z-ai")
    if not zai_path:
        return False, "z-ai no encontrado en PATH"

    # 2. Verificar si responde
    try:
        result = subprocess.run(
            ["z-ai", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version = (result.stdout or "").strip()[:50]
            return True, version or "version desconocida"
        return False, f"z-ai retorno codigo {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, "z-ai --version timeout (10s)"
    except Exception as e:
        return False, f"error ejecutando z-ai: {e}"


# Estado global de disponibilidad de z-ai CLI
_zai_available: bool = False
_zai_status: str = "no verificado"
_zai_checked: bool = False


def is_zai_available() -> bool:
    """Retorna True si el CLI z-ai esta disponible y funcional."""
    global _zai_available, _zai_status, _zai_checked
    if not _zai_checked:
        _zai_available, _zai_status = _check_zai_cli_available()
        _zai_checked = True
        if _zai_available:
            logger.info(f"[SkillLoader] z-ai CLI disponible: {_zai_status}")
        else:
            logger.warning(
                f"[SkillLoader] z-ai CLI NO disponible: {_zai_status}. "
                f"Las herramientas que dependen de z-ai (imagen, PDF, TTS, etc.) "
                f"no estaran disponibles. Instala z-ai-web-dev-sdk para habilitarlas."
            )
    return _zai_available


def get_zai_status() -> dict:
    """Retorna el estado del CLI z-ai para diagnostico.

    Returns:
        dict con: available, status, tools_affected
    """
    is_zai_available()  # Forzar verificacion si no se ha hecho
    # Listar herramientas que dependen de z-ai
    zai_tools = []
    for skill_dir_name, config in _SKILL_TOOL_MAP.items():
        cli_cmd = config.get("cli_command", "")
        if "z-ai" in cli_cmd:
            zai_tools.append(config["tool_name"])
    return {
        "available": _zai_available,
        "status": _zai_status,
        "tools_affected": zai_tools,
        "tools_count": len(zai_tools),
    }

# ============================================================
# CONFIGURACION
# ============================================================

# Directorio raiz de skills (3 niveles arriba de agente_v14/tools/)
# Estructura: AgentLocal/skills/ (hermano de agente_v14/)
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILLS_ROOT = os.path.normpath(os.path.join(_AGENT_DIR, "..", "..", "skills"))

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

# Limite maximo de caracteres para el texto de conocimiento extraido
_MAX_KNOWLEDGE_CHARS = 2000

# Patrones de secciones relevantes para extraer de SKILL.md
_SECTION_PATTERNS = [
    # Patrones para secciones de uso/como usar
    re.compile(r"^#{1,3}\s*(?:when\s+to\s+use|how\s+to\s+use|usage|uso|como\s+usar|trigger|workflow)", re.IGNORECASE | re.MULTILINE),
    # Patrones para secciones de reglas/guia
    re.compile(r"^#{1,3}\s*(?:core\s+rules|rules|guidelines|reglas|guia|key\s+(?:rules|guidelines)|important|best\s+practices)", re.IGNORECASE | re.MULTILINE),
    # Patrones para secciones de capacidades/overview
    re.compile(r"^#{1,3}\s*(?:overview|capabilities|core\s+capabilities|capacidades|scope|architecture)", re.IGNORECASE | re.MULTILINE),
    # Patrones para secciones de criterios de exito
    re.compile(r"^#{1,3}\s*(?:success\s+criteria|criterios|success|criterios\s+de\s+exito)", re.IGNORECASE | re.MULTILINE),
]


# ============================================================
# PARSER DE SKILL.MD (ENHANCED - extrae conocimiento)
# ============================================================

def parse_skill_md(skill_dir: str) -> dict:
    """Parsea un archivo SKILL.md y extrae metadata, capacidades y conocimiento.

    Lee el SKILL.md del directorio del skill, extrae el frontmatter como metadata,
    y ademas extrae contenido util del cuerpo del markdown:
    - Primeros 500 caracteres despues del frontmatter (descripcion general)
    - Secciones de uso/como usar
    - Secciones de reglas/guia
    - Secciones de capacidades/overview
    Todo esto se almacena en el campo 'knowledge' del dict retornado.

    Args:
        skill_dir: Ruta al directorio del skill

    Returns:
        Dict con name, description, scripts, capabilities, knowledge
    """
    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(skill_md_path):
        return {}

    with open(skill_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Parsear frontmatter
    metadata = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    key, _, val = line.partition(":")
                    metadata[key.strip()] = val.strip()
            # El cuerpo es todo lo que va despues del segundo ---
            body = parts[2].strip()

    # Buscar scripts disponibles
    scripts_dir = os.path.join(skill_dir, "scripts")
    scripts = []
    if os.path.isdir(scripts_dir):
        for f in os.listdir(scripts_dir):
            if f.endswith((".ts", ".js", ".sh", ".py")):
                scripts.append(os.path.join(scripts_dir, f))

    # ---- Extraccion de conocimiento enriquecido ----
    knowledge_parts = []

    # 1. Primeros 500 caracteres del cuerpo (descripcion general del skill)
    intro_text = body[:500].strip()
    if intro_text:
        knowledge_parts.append(intro_text)

    # 2. Extraer secciones relevantes (uso, reglas, capacidades, etc.)
    for pattern in _SECTION_PATTERNS:
        match = pattern.search(body)
        if match:
            # Extraer desde el heading hasta el siguiente heading del mismo nivel o superior
            section_start = match.start()
            section_header_level = len(match.group(0)) - len(match.group(0).lstrip('#'))
            # Buscar el final de la seccion (siguiente heading de nivel <= al encontrado)
            next_heading = re.search(
                rf"^#{{1,{section_header_level}}}\s",
                body[match.end():],
                re.MULTILINE
            )
            if next_heading:
                section_end = match.end() + next_heading.start()
            else:
                section_end = min(len(body), section_start + 1500)

            section_text = body[section_start:section_end].strip()
            if section_text and section_text not in knowledge_parts:
                knowledge_parts.append(section_text)

    # Combinar y truncar conocimiento
    knowledge = "\n\n---\n\n".join(knowledge_parts)
    if len(knowledge) > _MAX_KNOWLEDGE_CHARS:
        knowledge = knowledge[:_MAX_KNOWLEDGE_CHARS - 3] + "..."

    return {
        "name": metadata.get("name", os.path.basename(skill_dir)),
        "description": metadata.get("description", ""),
        "scripts": scripts,
        "path": skill_dir,
        "has_cli": _detect_cli_capability(content),
        "knowledge": knowledge,  # Campo nuevo: conocimiento extraido del SKILL.md
    }


def _detect_cli_capability(content: str) -> bool:
    """Detecta si el skill menciona comandos CLI de z-ai."""
    cli_patterns = ["z-ai function", "z-ai-generate", "z-ai function"]
    return any(p in content for p in cli_patterns)


# ============================================================
# CARGADOR DE CONOCIMIENTO DE SKILLS
# ============================================================

def load_skill_knowledge(skill_dir_name: str) -> str:
    """Lee el SKILL.md de un skill y extrae texto de conocimiento relevante.

    Esta funcion carga el contenido completo del SKILL.md y extrae las secciones
    mas utiles: descripcion, instrucciones de uso, reglas clave y guias.
    Se usa para inyectar contexto enriquecido en el prompt del agente.

    Args:
        skill_dir_name: Nombre del directorio del skill (ej: "blog-writer", "finance")

    Returns:
        Texto de conocimiento truncado a 2000 caracteres, o string vacio si no se encuentra
    """
    skill_dir = os.path.join(_SKILLS_ROOT, skill_dir_name)
    skill_md_path = os.path.join(skill_dir, "SKILL.md")

    if not os.path.exists(skill_md_path):
        logger.debug(f"[SkillKnowledge] SKILL.md no encontrado para: {skill_dir_name}")
        return ""

    try:
        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Separar frontmatter del cuerpo
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                body = parts[2].strip()

        knowledge_parts = []

        # 1. Extraer descripcion general (primeros 500 chars del cuerpo)
        intro = body[:500].strip()
        if intro:
            knowledge_parts.append(f"[DESCRIPCION]: {intro}")

        # 2. Extraer secciones de uso
        usage_match = re.search(
            r"^#{1,3}\s*(?:when\s+to\s+use|how\s+to\s+use|usage|uso|como\s+usar|trigger|workflow).*$",
            body,
            re.IGNORECASE | re.MULTILINE,
        )
        if usage_match:
            section_text = _extract_section(body, usage_match)
            if section_text:
                knowledge_parts.append(f"[USO]: {section_text}")

        # 3. Extraer reglas y guias clave
        rules_match = re.search(
            r"^#{1,3}\s*(?:core\s+rules|rules|guidelines|reglas|guia|key\s+(?:rules|guidelines)|important|best\s+practices).*$",
            body,
            re.IGNORECASE | re.MULTILINE,
        )
        if rules_match:
            section_text = _extract_section(body, rules_match)
            if section_text:
                knowledge_parts.append(f"[REGLAS]: {section_text}")

        # 4. Extraer capacidades/overview si no se capturo ya
        cap_match = re.search(
            r"^#{1,3}\s*(?:overview|capabilities|core\s+capabilities|capacidades|scope|architecture).*$",
            body,
            re.IGNORECASE | re.MULTILINE,
        )
        if cap_match:
            section_text = _extract_section(body, cap_match)
            if section_text:
                knowledge_parts.append(f"[CAPACIDADES]: {section_text}")

        # Combinar todas las partes
        result = "\n\n".join(knowledge_parts)

        # Truncar al limite maximo
        if len(result) > _MAX_KNOWLEDGE_CHARS:
            result = result[:_MAX_KNOWLEDGE_CHARS - 3] + "..."

        return result

    except Exception as e:
        logger.warning(f"[SkillKnowledge] Error leyendo SKILL.md de {skill_dir_name}: {e}")
        return ""


def _extract_section(body: str, match: re.Match) -> str:
    """Extrae el texto de una seccion desde un heading hasta el siguiente heading del mismo nivel o superior.

    Args:
        body: Texto completo del cuerpo del SKILL.md
        match: Objeto Match del heading encontrado

    Returns:
        Texto de la seccion, truncado a 800 caracteres maximo
    """
    section_start = match.start()
    header_text = match.group(0)
    # Determinar nivel del heading (numero de #)
    header_level = len(header_text) - len(header_text.lstrip('#'))

    # Buscar el siguiente heading de nivel igual o superior
    remaining = body[match.end():]
    next_heading = re.search(rf"^#{{1,{header_level}}}\s", remaining, re.MULTILINE)

    if next_heading:
        section_end = match.end() + next_heading.start()
    else:
        section_end = min(len(body), section_start + 1500)

    section_text = body[section_start:section_end].strip()

    # Limitar tamano de la seccion para no saturar el contexto
    if len(section_text) > 800:
        section_text = section_text[:797] + "..."

    return section_text


# ============================================================
# BUSQUEDA DE SKILLS RELEVANTES
# ============================================================

def find_relevant_skills(query: str, top_k: int = 3) -> list[dict]:
    """Busca skills relevantes para una consulta del usuario usando coincidencia de palabras clave.

    Analiza la consulta del usuario, la divide en palabras clave, y busca
    coincidencias en los nombres y descripciones de todos los skills cargados
    (tanto herramientas como referencia). Para cada skill relevante, carga
    su texto de conocimiento completo.

    Args:
        query: Consulta o descripcion de tarea del usuario
        top_k: Numero maximo de skills relevantes a retornar (default: 3)

    Returns:
        Lista de dicts, cada uno con: name, relevance_score, knowledge_text
        Ordenada por relevance_score descendente
    """
    if not _loaded_skills:
        logger.debug("[SkillFinder] No hay skills cargados aun")
        return []

    # Normalizar query y extraer palabras clave
    query_lower = query.lower()
    # Eliminar stopwords simples en espanol e ingles
    _stopwords = {
        "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
        "al", "a", "en", "por", "para", "con", "sin", "sobre", "entre",
        "que", "se", "su", "es", "son", "fue", "ser", "estar", "hay",
        "como", "mas", "menos", "muy", "este", "esta", "esto", "eso",
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "and", "or", "but", "not", "no", "if", "then", "than", "so",
        "it", "its", "this", "that", "these", "those", "me", "my",
        "tu", "te", "ti", "le", "les", "nos", "les", "yo",
    }
    keywords = [
        w for w in re.split(r"[\s,.;:!?()\-_]+", query_lower)
        if len(w) > 2 and w not in _stopwords
    ]

    if not keywords:
        return []

    # Evaluar cada skill cargado
    scored_skills = []
    for skill_key, skill_data in _loaded_skills.items():
        score = 0
        skill_info = skill_data.get("info", {})
        skill_name = skill_info.get("name", skill_key)
        skill_description = skill_info.get("description", "")
        skill_knowledge = skill_info.get("knowledge", "")

        # Texto combinado para busqueda (nombre + descripcion + conocimiento)
        searchable_text = f"{skill_name} {skill_description} {skill_knowledge}".lower()

        # Calcular puntuacion por coincidencias de palabras clave
        for kw in keywords:
            # Coincidencia exacta de palabra clave
            if kw in searchable_text:
                # Peso extra si coincide en el nombre
                if kw in skill_name.lower():
                    score += 3
                # Peso medio si coincide en la descripcion
                elif kw in skill_description.lower():
                    score += 2
                # Peso menor si coincide solo en el conocimiento
                else:
                    score += 1

        # Bonus por coincidencias parciales (substring en nombre)
        for kw in keywords:
            if len(kw) >= 4:
                for word in skill_name.lower().replace("-", " ").replace("_", " ").split():
                    if kw[:4] == word[:4] and kw != word:
                        score += 1

        if score > 0:
            # Cargar conocimiento completo del skill para los relevantes
            dir_name = skill_data.get("dir", "")
            knowledge_text = ""
            if dir_name and os.path.isdir(dir_name):
                # Intentar obtener knowledge del skill_data ya cargado
                knowledge_text = skill_knowledge
                # Si no hay knowledge precargado, cargarlo dinamicamente
                if not knowledge_text:
                    # Determinar el nombre del directorio del skill
                    skill_dir_name = os.path.basename(dir_name)
                    knowledge_text = load_skill_knowledge(skill_dir_name)

            scored_skills.append({
                "name": skill_name,
                "key": skill_key,
                "relevance_score": score,
                "knowledge_text": knowledge_text,
                "is_reference": skill_data.get("is_reference", False),
            })

    # Ordenar por puntuacion descendente y tomar top_k
    scored_skills.sort(key=lambda x: x["relevance_score"], reverse=True)
    result = scored_skills[:top_k]

    logger.debug(
        f"[SkillFinder] Query: '{query[:50]}...' -> "
        f"{len(scored_skills)} skills relevantes, top {min(top_k, len(scored_skills))}: "
        f"{[s['name'] for s in result]}"
    )

    return result


# ============================================================
# GENERADOR DE CONTEXTO PARA EL AGENTE
# ============================================================

def get_skills_context(query: str) -> str:
    """Genera un string de contexto con skills relevantes para inyectar en el prompt del agente.

    Busca los top 3 skills relevantes para la consulta del usuario,
    carga su conocimiento, y lo formatea como texto que puede ser
    inyectado directamente en el system prompt o como contexto adicional.

    Args:
        query: Consulta o descripcion de tarea del usuario

    Returns:
        String formateado con contexto de skills relevantes, o string vacio si no hay relevantes
    """
    relevant = find_relevant_skills(query, top_k=3)

    if not relevant:
        return ""

    context_lines = ["SKILLS RELEVANTES PARA ESTA TAREA:"]

    for skill in relevant:
        name = skill["name"]
        knowledge = skill["knowledge_text"]
        score = skill["relevance_score"]
        is_ref = skill.get("is_reference", False)

        # Indicador de tipo de skill
        skill_type = "(referencia)" if is_ref else "(herramienta)"

        # Si hay conocimiento, usarlo; si no, usar nombre y score
        if knowledge:
            # Truncar conocimiento para no saturar el contexto del prompt
            excerpt = knowledge[:600]
            if len(knowledge) > 600:
                excerpt += "..."
            context_lines.append(f"- {name} {skill_type}: {excerpt}")
        else:
            context_lines.append(f"- {name} {skill_type}: [sin detalle disponible, score={score}]")

    context = "\n".join(context_lines)

    logger.info(
        f"[SkillContext] Contexto generado para query '{query[:50]}...': "
        f"{len(relevant)} skills, {len(context)} caracteres"
    )

    return context


# ============================================================
# INTEGRACION CON REACTAGENT
# ============================================================

def enrich_prompt_with_skills(user_message: str, system_prompt: str = "") -> str:
    """Enriquece un prompt del sistema con contexto de skills relevantes.

    Funcion de integracion para ReactAgent: recibe el mensaje del usuario
    y el prompt del sistema actual, busca skills relevantes, y los inyecta
    como contexto adicional al final del prompt del sistema.

    Uso desde react.py:
        from tools.skill_loader import enrich_prompt_with_skills
        enriched = enrich_prompt_with_skills(user_message, current_system_prompt)

    Args:
        user_message: Mensaje del usuario (se usa para buscar skills relevantes)
        system_prompt: Prompt del sistema actual (opcional, se appendea al final)

    Returns:
        Prompt del sistema enriquecido con contexto de skills, o el original si no hay relevantes
    """
    skills_ctx = get_skills_context(user_message)

    if not skills_ctx:
        return system_prompt

    # Inyectar contexto de skills antes de cualquier seccion final del prompt
    # Separador claro para que el LLM distinga el contexto de skills
    enriched = f"{system_prompt}\n\n{skills_ctx}" if system_prompt else skills_ctx

    logger.debug(f"[SkillEnrich] Prompt enriquecido con {len(skills_ctx)} chars de contexto de skills")

    return enriched


# ============================================================
# EJECUTOR DE SKILLS
# ============================================================

def _execute_skill_tool(tool_name: str, params: dict, config: dict) -> str:
    """Ejecuta un skill como herramienta via CLI.

    v16.2: Verifica disponibilidad de z-ai antes de ejecutar.
    Si z-ai no esta disponible, retorna un mensaje claro en vez
    de fallar con un error generico de subprocess.

    Args:
        tool_name: Nombre de la herramienta
        params: Parametros proporcionados por el agente
        config: Configuracion del skill desde _SKILL_TOOL_MAP

    Returns:
        Resultado de la ejecucion como string
    """
    import subprocess
    import shlex

    # v16.2: Verificar si z-ai esta disponible antes de ejecutar
    cli_command = config.get("cli_command", "")
    if "z-ai" in cli_command and not is_zai_available():
        return (
            f"ERROR en {tool_name}: La herramienta requiere z-ai CLI pero no esta disponible. "
            f"Razon: {_zai_status}. "
            f"Instala z-ai-web-dev-sdk para habilitar esta capacidad. "
            f"Alternativas nativas: buscar_web, leer_web, generar_codigo, ejecutar_codigo."
        )

    try:
        # Mapear parametros del agente a parametros del CLI
        param_mapping = config.get("param_mapping", {})
        mapped_params = {}
        for agent_param, cli_param in param_mapping.items():
            if agent_param in params:
                mapped_params[cli_param] = params[agent_param]

        # Construir comando como lista para evitar shell=True
        cli_command = config.get("cli_command", "")

        if "z-ai function" in cli_command:
            # Formato: z-ai function -n <name> -a '<json>'
            json_args = json.dumps(mapped_params, ensure_ascii=False)
            cmd_list = shlex.split(cli_command) + [json_args]
        elif "z-ai-generate" in cli_command:
            # Formato: z-ai-generate -p "<prompt>" -o "<output>" -s "<size>"
            prompt = mapped_params.get("prompt", "")
            output = mapped_params.get("output", "")
            size = mapped_params.get("size", "1024x1024")
            cmd_list = ["z-ai-generate", "-p", prompt]
            if output:
                cmd_list.extend(["-o", output])
            cmd_list.extend(["-s", size])
        else:
            # Fallback generico
            json_args = json.dumps(mapped_params, ensure_ascii=False)
            cmd_list = shlex.split(cli_command) + [json_args]

        logger.info(f"[SkillLoader] Ejecutando: {' '.join(cmd_list)[:200]}")

        # Ejecutar con timeout (sin shell=True)
        result = subprocess.run(
            cmd_list,
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

    Ahora tambien extrae el conocimiento (knowledge) de cada SKILL.md
    para que este disponible como contexto enriquecido para el agente.

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
    # v16.2: Verificar z-ai CLI antes de cargar skills que dependen de el
    zai_ok = is_zai_available()
    zai_tools_skipped = []

    for skill_dir_name, config in _SKILL_TOOL_MAP.items():
        skill_dir = os.path.join(_SKILLS_ROOT, skill_dir_name)
        tool_name = config["tool_name"]
        cli_command = config.get("cli_command", "")

        # v16.2: Si la herramienta depende de z-ai y no esta disponible,
        # registrarla como no-disponible en vez de omitirla completamente.
        # El agente vera la herramienta en su lista pero recibira un mensaje
        # claro si intenta usarla, en vez de un error de subprocess.
        requires_zai = "z-ai" in cli_command
        if requires_zai and not zai_ok:
            # Registrar la herramienta de todas formas, pero marcarla
            # como no-disponible. El _execute_skill_tool verificara
            # disponibilidad al momento de ejecucion.
            try:
                skill_info = parse_skill_md(skill_dir) if os.path.isdir(skill_dir) else {}
                _loaded_skills[tool_name] = {
                    "config": config,
                    "info": skill_info,
                    "dir": skill_dir,
                    "zai_required": True,
                    "available": False,
                }

                # Registrar funcion que advertira al agente
                func = _make_skill_tool_func(tool_name, config)
                # Modificar schema para indicar que no esta disponible
                schema = _build_skill_schema(tool_name, config)
                original_desc = schema["function"]["description"]
                schema["function"]["description"] = (
                    f"[NO DISPONIBLE - requiere z-ai CLI] {original_desc}"
                )

                register_tool(tool_name, func, schema=schema)

                zai_tools_skipped.append(tool_name)
                logger.warning(
                    f"[SkillLoader] Registrado (NO DISPONIBLE): {tool_name} <- {skill_dir_name} "
                    f"(requiere z-ai CLI: {_zai_status})"
                )
            except Exception as e:
                _load_errors.append(f"{tool_name}: {str(e)}")
                logger.error(f"[SkillLoader] Error cargando {skill_dir_name}: {e}")
            continue

        try:
            # Parsear SKILL.md si existe (ahora con conocimiento enriquecido)
            skill_info = parse_skill_md(skill_dir) if os.path.isdir(skill_dir) else {}
            _loaded_skills[tool_name] = {
                "config": config,
                "info": skill_info,
                "dir": skill_dir,
                "zai_required": requires_zai,
                "available": True,
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

    # Cargar skills de referencia (metadata + conocimiento, no herramientas)
    for skill_dir_name in _REFERENCE_SKILLS:
        skill_dir = os.path.join(_SKILLS_ROOT, skill_dir_name)
        if os.path.isdir(skill_dir):
            try:
                # parse_skill_md ahora extrae conocimiento en el campo 'knowledge'
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

    # Contar cuantos skills tienen conocimiento extraido
    knowledge_count = sum(
        1 for v in _loaded_skills.values()
        if v.get("info", {}).get("knowledge", "")
    )

    # v16.2: Reportar estado de z-ai CLI
    if zai_tools_skipped:
        logger.warning(
            f"[SkillLoader] {len(zai_tools_skipped)} herramientas NO DISPONIBLES "
            f"(requieren z-ai CLI): {', '.join(zai_tools_skipped)}"
        )

    logger.info(
        f"[SkillLoader] Carga completa: {loaded_count} herramientas "
        f"({len(zai_tools_skipped)} sin z-ai), "
        f"{ref_count} referencia, {knowledge_count} con conocimiento, "
        f"{len(_load_errors)} errores"
    )

    return {
        "loaded": loaded_count,
        "available": loaded_count - len(zai_tools_skipped),
        "unavailable_zai": len(zai_tools_skipped),
        "zai_available": zai_ok,
        "reference": ref_count,
        "with_knowledge": knowledge_count,
        "errors": len(_load_errors),
        "skills": list(_loaded_skills.keys()),
        "unavailable_tools": zai_tools_skipped,
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

    Ahora incluye el campo 'knowledge_available' para indicar si el skill
    tiene conocimiento extraido utilizable como contexto.

    Returns:
        Lista de dicts con name, description, is_tool, is_reference, knowledge_available
    """
    result = []
    for name, data in _loaded_skills.items():
        info = data.get("info", {})
        result.append({
            "name": name,
            "description": info.get("description", ""),
            "is_tool": data.get("config") is not None,
            "is_reference": data.get("is_reference", False),
            "knowledge_available": bool(info.get("knowledge", "")),
        })
    return result


def get_skills_status() -> dict:
    """Retorna el estado del sistema de skills.

    Returns:
        Dict con estadisticas de carga
    """
    tool_count = sum(1 for v in _loaded_skills.values() if v.get("config"))
    ref_count = sum(1 for v in _loaded_skills.values() if v.get("is_reference"))
    knowledge_count = sum(
        1 for v in _loaded_skills.values()
        if v.get("info", {}).get("knowledge", "")
    )
    return {
        "total_skills": len(_loaded_skills),
        "tool_skills": tool_count,
        "reference_skills": ref_count,
        "with_knowledge": knowledge_count,
        "errors": len(_load_errors),
        "skills_root": _SKILLS_ROOT,
        "loaded": bool(_loaded_skills),
    }
