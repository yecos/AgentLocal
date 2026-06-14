"""
=============================================================
AGENTE v24 - Herramienta auto_evolve
=============================================================
Registra auto_evolve como herramienta del agente para que
pueda auto-mejorarse cuando necesite capacidades que no tiene.

Uso (desde el agente):
    auto_evolve(focus="email")

v24: Implementacion inicial.
=============================================================
"""

from tools.registry import register_tool

try:
    from agent.auto_evolve import get_evolver
    AUTO_EVOLVE_AVAILABLE = True
except ImportError:
    AUTO_EVOLVE_AVAILABLE = False


def auto_evolve(focus: str = "") -> str:
    """Auto-evalua y mejora las capacidades del agente.

    Busca, instala y verifica nuevas herramientas cuando el agente
    necesita hacer algo que no puede. Tambien puede usarse sin focus
    para una evaluacion general de salud.

    Args:
        focus: Capacidad especifica a buscar/mejorar (ej: "email", "calendar")

    Returns:
        Resultado del ciclo de auto-evolucion
    """
    if not AUTO_EVOLVE_AVAILABLE:
        return "ERROR: Sistema de auto-evolucion no disponible"

    try:
        # Obtener herramientas actuales del registry
        from tools.registry import TOOL_FUNCTIONS
        evolver = get_evolver()

        result = evolver.evolve(focus=focus if focus else None, tool_functions=TOOL_FUNCTIONS)

        if result.get("success"):
            solution = result.get("solution", {})
            return (
                f"Auto-evolucion exitosa!\n"
                f"Tipo: {solution.get('type', 'unknown')}\n"
                f"Nombre: {solution.get('name', 'unknown')}\n"
                f"Descripcion: {solution.get('description', '')}\n"
                f"Test: {result.get('test', {})}\n"
                f"Tiempo: {result.get('elapsed', 0)}s"
            )
        else:
            phase = result.get("phase", "unknown")
            message = result.get("message", "Error desconocido")
            return f"Auto-evolucion no completada (fase: {phase}): {message}"

    except Exception as e:
        return f"ERROR en auto_evolve: {e}"


# Registrar en el Tool Registry
register_tool(
    "auto_evolve",
    auto_evolve,
    schema={
        "type": "function",
        "function": {
            "name": "auto_evolve",
            "description": (
                "Auto-evalua y mejora las capacidades del agente. "
                "Busca, instala y verifica nuevas herramientas cuando necesitas hacer algo que no puede. "
                "Usa focus para buscar una capacidad especifica (ej: 'email', 'calendar', 'spreadsheet'). "
                "Usa sin focus para una evaluacion general de salud."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": "Capacidad especifica a buscar/mejorar (ej: email, calendar, spreadsheet, image_edit). Dejar vacio para evaluacion general.",
                    },
                },
                "required": [],
            },
        },
    },
)
