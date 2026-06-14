"""
=============================================================
AGENTE v14 - ToolSelector
=============================================================
Intent-based tool selection.
Returns only the relevant tools for a given user message,
reducing LLM context from 77+ tools to ~15.

Usage:
    from tools.tool_selector import get_tools_for_context, get_reduced_schemas
    
    # Get relevant tool names
    tools = get_tools_for_context("busca noticias de tecnología")
    
    # Get filtered schemas for LLM call
    schemas = get_reduced_schemas(user_message, all_schemas)
=============================================================
"""

from __future__ import annotations

import re
import logging
from tools.registry import TOOL_FUNCTIONS
from tools.skill_router import get_skill_router

logger = logging.getLogger(__name__)

# Intent → tool mappings
INTENT_TO_TOOLS = {
    "search_web": {
        "patterns": [r"busca?.*en internet", r"qué.*noticias", r"información.*sobre",
                     r"últimas.*noticias", r"busca.*online", r"investiga.*web"],
        "tools_priority": ["buscar_web_api", "busqueda_profunda", "buscar_web"],
    },
    "create_pdf": {
        "patterns": [r"crea.*pdf", r"genera.*pdf", r"informe.*pdf"],
        "tools_priority": ["crear_pdf"],
    },
    "create_doc": {
        "patterns": [r"crea.*doc", r"documento.*word", r"informe.*word"],
        "tools_priority": ["crear_documento", "crear_docx"],
    },
    "create_chart": {
        "patterns": [r"gráfico.*de", r"grafica", r"visualiza.*datos"],
        "tools_priority": ["crear_grafico_avanzado", "crear_grafico"],
    },
    "run_code": {
        "patterns": [r"ejecuta.*código", r"corre.*script", r"prueba.*código"],
        "tools_priority": ["ejecutar_codigo", "ejecutar_python"],
    },
    "git_op": {
        "patterns": [r"git.*commit", r"git.*push", r"sube.*cambios"],
        "tools_priority": ["git_operacion"],
    },
    "analyze_project": {
        "patterns": [r"analiza.*proyecto", r"revisa.*código", r"estructura.*de"],
        "tools_priority": ["analizar_proyecto", "buscar_en_archivos"],
    },
}

# Core tools always included
ALWAYS_AVAILABLE = [
    "ejecutar_comando", "leer_archivo", "escribir_archivo",
    "listar_archivos", "buscar_web",
]

# Context keywords → additional tools
CONTEXT_KEYWORDS = {
    "código": ["generar_codigo", "ejecutar_codigo", "buscar_patron"],
    "programa": ["generar_codigo", "ejecutar_codigo"],
    "función": ["generar_codigo", "ejecutar_codigo"],
    "archivo": ["buscar_en_archivos", "buscar_reemplazar"],
    "documento": ["buscar_en_archivos", "crear_pdf"],
    "datos": ["estadisticas", "crear_grafico"],
    "csv": ["estadisticas", "crear_grafico"],
    "excel": ["estadisticas", "crear_xlsx"],
    "git": ["git_operacion", "analizar_proyecto"],
    "imagen": ["analizar_imagen", "generar_imagen"],
}


def detect_intent(user_message: str) -> dict | None:
    """Detect user intent and return best tool + alternatives."""
    msg_lower = user_message.lower()
    
    for intent_name, intent_config in INTENT_TO_TOOLS.items():
        for pattern in intent_config["patterns"]:
            if re.search(pattern, msg_lower):
                router = get_skill_router()
                for tool in intent_config["tools_priority"]:
                    if tool in TOOL_FUNCTIONS:
                        return {
                            "intent": intent_name,
                            "best_tool": tool,
                            "alternatives": intent_config["tools_priority"],
                            "available": True,
                        }
    
    return None


def get_tools_for_context(user_message: str, max_tools: int = 15) -> list[str]:
    """Return only relevant tools for the message (not all 77+)."""
    msg_lower = user_message.lower()
    
    # Start with core tools
    tools = list(ALWAYS_AVAILABLE)
    
    # Add intent-specific tools
    intent = detect_intent(user_message)
    if intent and intent.get("alternatives"):
        tools.extend(intent["alternatives"])
    
    # Add context-based tools
    for keyword, tool_list in CONTEXT_KEYWORDS.items():
        if keyword in msg_lower:
            tools.extend(tool_list)
    
    # Deduplicate and filter existing
    tools = list(dict.fromkeys(tools))
    tools = [t for t in tools if t in TOOL_FUNCTIONS]
    
    return tools[:max_tools]


def get_reduced_schemas(user_message: str, all_schemas: list[dict]) -> list[dict]:
    """Return only schemas for relevant tools (reduces LLM context)."""
    relevant_tools = get_tools_for_context(user_message)
    relevant_names = set(relevant_tools)
    
    filtered = []
    for schema in all_schemas:
        func_info = schema.get("function", {})
        name = func_info.get("name", "")
        if name in relevant_names:
            filtered.append(schema)
    
    # Always include at least 5 schemas
    if len(filtered) < 5:
        for schema in all_schemas:
            if schema not in filtered:
                filtered.append(schema)
                if len(filtered) >= 5:
                    break
    
    return filtered
