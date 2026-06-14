"""
=============================================================
AGENTE v14 - SkillError
=============================================================
Errores estructurados de skills.
Provee informacion accionable al agente sobre qué fallo
y como recuperarse.

v16.3: SkillError con sugerencias de recuperacion,
       alternativa local, y serializacion para API.
=============================================================
"""

from __future__ import annotations


# ============================================================
# C2: FALLBACK MAP — z-ai skills → local alternatives
# ============================================================
SKILL_FALLBACK_MAP: dict[str, str | None] = {
    # Web search
    "buscar_web_api": "buscar_web",
    "leer_web_api": "resumir_url",
    # Documents
    "crear_documento": "crear_docx",
    "crear_pdf": "crear_pdf",          # mismo nombre, diferente impl
    "crear_presentacion": "crear_pptx",
    "crear_hoja_calculo": "crear_xlsx",
    # Multimedia
    "texto_a_voz": None,               # No full local alternative
    "generar_imagen": "buscar_imagen",  # No genera, pero busca
    "analizar_imagen_api": "analizar_imagen",  # VLM local via Ollama
    "navegar_web": "leer_web",         # No automatiza, pero lee
}


class SkillError(Exception):
    """Error tipado de un skill con sugerencias de recuperacion.

    Attributes:
        skill_name: Name of the skill that failed.
        error_type: Predefined error type constant.
        message: Human-readable error description.
        suggestion: Optional recovery suggestion.
        recoverable: Whether the error can be recovered automatically.
        alternative_tool: Optional alternative tool name to try.
    """

    # Tipos de error predefinidos
    MISSING_DEPENDENCY = "missing_dependency"
    BAD_PARAMS = "bad_params"
    FILE_EXISTS = "file_exists"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    NOT_AVAILABLE = "not_available"
    INTERNAL = "internal"

    def __init__(
        self,
        skill_name: str,
        error_type: str,
        message: str,
        suggestion: str | None = None,
        recoverable: bool = True,
        alternative_tool: str | None = None,
    ):
        self.skill_name = skill_name
        self.error_type = error_type
        self.message = message
        self.suggestion = suggestion
        self.recoverable = recoverable
        self.alternative_tool = alternative_tool
        super().__init__(message)

    def to_agent_message(self) -> str:
        """Converts the error into a useful message for the agent."""
        msg = f"ERROR en {self.skill_name}: {self.message}"
        if self.suggestion:
            msg += f"\nSUGERENCIA: {self.suggestion}"
        if self.alternative_tool:
            msg += f"\nALTERNATIVA: Usa '{self.alternative_tool}' en su lugar."
        if not self.recoverable:
            msg += "\nEste error NO es recuperable automaticamente."
        return msg

    def to_dict(self) -> dict:
        """Serializes error for API responses."""
        return {
            "skill": self.skill_name,
            "error_type": self.error_type,
            "message": self.message,
            "suggestion": self.suggestion,
            "recoverable": self.recoverable,
            "alternative_tool": self.alternative_tool,
        }


def create_missing_dependency_error(
    skill_name: str, dependency: str = "z-ai CLI"
) -> SkillError:
    """Helper: error for missing dependencies (z-ai not installed).

    Args:
        skill_name: The tool that requires the missing dependency.
        dependency: Name of the missing dependency (default: z-ai CLI).

    Returns:
        SkillError with recovery information and local fallback if available.
    """
    from tools.skill_router import get_skill_router
    router = get_skill_router()
    fallback = router.get_fallback(skill_name)

    suggestion = "Instala con: npm install -g z-ai-web-dev-sdk"
    if fallback:
        suggestion += f"\nO usa la alternativa local: {fallback}"

    return SkillError(
        skill_name=skill_name,
        error_type=SkillError.MISSING_DEPENDENCY,
        message=f"Dependencia faltante: {dependency}",
        suggestion=suggestion,
        recoverable=bool(fallback),
        alternative_tool=fallback,
    )


def create_timeout_error(skill_name: str, timeout_secs: int) -> SkillError:
    """Helper: error for timeouts.

    Args:
        skill_name: The tool that timed out.
        timeout_secs: Timeout duration in seconds.

    Returns:
        SkillError with timeout-specific recovery suggestion.
    """
    return SkillError(
        skill_name=skill_name,
        error_type=SkillError.TIMEOUT,
        message=f"Timeout despues de {timeout_secs} segundos",
        suggestion="Intenta con parametros mas simples o un timeout mayor",
        recoverable=True,
    )


def create_bad_params_error(
    skill_name: str, param_name: str, reason: str
) -> SkillError:
    """Helper: error for invalid parameters.

    Args:
        skill_name: The tool that received bad params.
        param_name: The invalid parameter name.
        reason: Why the parameter is invalid.

    Returns:
        SkillError with parameter-specific recovery suggestion.
    """
    return SkillError(
        skill_name=skill_name,
        error_type=SkillError.BAD_PARAMS,
        message=f"Parametro '{param_name}' invalido: {reason}",
        suggestion=f"Revisa el formato esperado de '{param_name}'",
        recoverable=True,
    )
