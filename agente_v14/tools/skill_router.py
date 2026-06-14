"""
=============================================================
AGENTE v14 - Skill Router
=============================================================
Seleccion inteligente de herramientas.
Prioriza herramientas disponibles, con buen historial,
y adecuadas al contexto.

v16.3: SkillRouter + fallback automatico z-ai → local.
       Integra con TOOL_FUNCTIONS del registry para
       verificar disponibilidad en tiempo real.
=============================================================
"""

from __future__ import annotations

import re
import logging
from typing import Optional

from tools.registry import TOOL_FUNCTIONS

logger = logging.getLogger(__name__)

# Mapa de herramientas z-ai → alternativas locales
ZAI_TO_LOCAL_FALLBACK = {
    "buscar_web_api":     "buscar_web",
    "leer_web_api":       "resumir_url",
    "crear_documento":    "crear_docx",
    "crear_presentacion": "crear_pptx",
    "crear_hoja_calculo": "crear_xlsx",
    "generar_imagen":     None,  # No hay alternativa local completa
    "texto_a_voz":        None,
    "analizar_imagen_api": "analizar_imagen",
    "navegar_web":        "resumir_url",
}

# Intenciones → herramientas optimas con prioridad
INTENT_TO_TOOLS = {
    "search_web": {
        "patterns": [r"busca?.*en internet", r"información.*sobre", r"últimas.*noticias", r"investiga"],
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
    "generate_image": {
        "patterns": [r"genera.*imagen", r"crea.*imagen", r"dibuja"],
        "tools_priority": ["generar_imagen"],
        "requires_zai": True,
    },
    "text_to_speech": {
        "patterns": [r"texto.*voz", r"lee.*en.*voz", r"audio"],
        "tools_priority": ["texto_a_voz"],
        "requires_zai": True,
    },
}


class SkillRouter:
    """Selecciona el skill optimo para una tarea basado en disponibilidad y calidad."""

    def __init__(self):
        self._failure_counts: dict[str, int] = {}
        self._success_counts: dict[str, int] = {}
        self._zai_available: bool | None = None

    def is_zai_available(self) -> bool:
        """Check if z-ai CLI is available (cached)."""
        if self._zai_available is None:
            try:
                from tools.skill_loader import is_zai_available as check
                self._zai_available = check()
            except ImportError:
                self._zai_available = False
        return self._zai_available

    def select_best_tool(self, tool_name: str, alternatives: list[str] | None = None) -> str:
        """Select the best available tool from alternatives.

        Args:
            tool_name: Primary tool name to try.
            alternatives: Optional list of alternative tool names.

        Returns:
            The best available tool name based on scoring.
        """
        candidates = alternatives or [tool_name]
        scored = []

        for candidate in candidates:
            score = 100  # Base score

            # Not registered = can't use
            if candidate not in TOOL_FUNCTIONS:
                score -= 90

            # Requires z-ai but not available
            if candidate in ZAI_TO_LOCAL_FALLBACK and not self.is_zai_available():
                score -= 80

            # Penalize by failure history
            fails = self._failure_counts.get(candidate, 0)
            score -= fails * 20

            # Bonify by success history
            successes = self._success_counts.get(candidate, 0)
            score += min(successes * 5, 30)

            scored.append((candidate, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        best = scored[0][0]

        if best != tool_name:
            logger.info(f"Skill routing: {tool_name} -> {best} (score: {scored[0][1]})")

        return best

    def get_fallback(self, tool_name: str) -> Optional[str]:
        """Get local fallback for a z-ai tool.

        Args:
            tool_name: The z-ai tool name to find a fallback for.

        Returns:
            The local fallback tool name if it exists in TOOL_FUNCTIONS, else None.
        """
        fallback = ZAI_TO_LOCAL_FALLBACK.get(tool_name)
        if fallback and fallback in TOOL_FUNCTIONS:
            return fallback
        return None

    def record_success(self, tool_name: str) -> None:
        """Record a successful tool call."""
        self._success_counts[tool_name] = self._success_counts.get(tool_name, 0) + 1

    def record_failure(self, tool_name: str) -> None:
        """Record a failed tool call."""
        self._failure_counts[tool_name] = self._failure_counts.get(tool_name, 0) + 1

    def detect_intent(self, user_message: str) -> Optional[dict]:
        """Detect user intent and return best tool + alternatives.

        Args:
            user_message: The user's message to analyze.

        Returns:
            Dict with intent info (intent, best_tool, alternatives, available, warning),
            or None if no intent matched.
        """
        msg_lower = user_message.lower()

        for intent_name, intent_config in INTENT_TO_TOOLS.items():
            for pattern in intent_config["patterns"]:
                if re.search(pattern, msg_lower):
                    requires_zai = intent_config.get("requires_zai", False)
                    if requires_zai and not self.is_zai_available():
                        return {
                            "intent": intent_name,
                            "best_tool": None,
                            "warning": (
                                "Esta herramienta requiere z-ai CLI. "
                                "¿Quieres usar la alternativa local?"
                            ),
                            "available": False,
                        }

                    for tool in intent_config["tools_priority"]:
                        if tool in TOOL_FUNCTIONS:
                            return {
                                "intent": intent_name,
                                "best_tool": tool,
                                "alternatives": intent_config["tools_priority"],
                                "available": True,
                            }

        return None

    def get_contextual_tools(self, user_message: str, max_tools: int = 15) -> list[str]:
        """Return only relevant tools for the message (not all 77+).

        Args:
            user_message: The user's message to analyze for context.
            max_tools: Maximum number of tools to return.

        Returns:
            List of tool names relevant to the message context.
        """
        # Core tools always available
        always = [
            "ejecutar_comando", "leer_archivo", "escribir_archivo",
            "listar_archivos", "buscar_web",
        ]

        contextual: list[str] = []
        intent = self.detect_intent(user_message)
        if intent and intent.get("alternatives"):
            contextual.extend(intent["alternatives"])

        msg_lower = user_message.lower()
        if any(w in msg_lower for w in ["código", "programa", "función"]):
            contextual.extend(["generar_codigo", "ejecutar_codigo"])
        if any(w in msg_lower for w in ["archivo", "documento", "carpeta"]):
            contextual.extend(["buscar_en_archivos", "buscar_reemplazar"])
        if any(w in msg_lower for w in ["datos", "csv", "excel", "tabla"]):
            contextual.extend(["estadisticas", "crear_grafico"])
        if any(w in msg_lower for w in ["git", "repositorio", "commit"]):
            contextual.extend(["git_operacion", "analizar_proyecto"])

        # Deduplicate and filter existing
        all_tools = list(dict.fromkeys(always + contextual))
        return [t for t in all_tools if t in TOOL_FUNCTIONS][:max_tools]


# Singleton
_router: SkillRouter | None = None


def get_skill_router() -> SkillRouter:
    """Return the global SkillRouter singleton."""
    global _router
    if _router is None:
        _router = SkillRouter()
    return _router
