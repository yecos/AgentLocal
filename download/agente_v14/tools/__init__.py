"""
tools/__init__.py - Registry automatico de herramientas con decorator
Elimina la necesidad de editar 3 archivos al agregar una herramienta nueva.
"""
import inspect
from functools import wraps

# Registry global: nombre -> {func, schema, description}
TOOL_REGISTRY = {}


def tool(name: str, description: str, params: dict, required: list = None):
    """Decorator que registra una herramienta automaticamente.
    
    Uso:
        @tool(
            name="mi_herramienta",
            description="Hace algo util",
            params={"input": {"type": "string", "description": "El input"}},
            required=["input"]
        )
        def mi_herramienta(input: str) -> str:
            return f"Resultado: {input}"
    """
    def decorator(func):
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": params,
                    "required": required or []
                }
            }
        }
        TOOL_REGISTRY[name] = {
            "func": func,
            "schema": schema,
            "description": description
        }
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


def get_tool_schemas():
    """Retorna todos los schemas para function calling."""
    return [r["schema"] for r in TOOL_REGISTRY.values()]


def get_tool_functions():
    """Retorna el mapa nombre -> funcion para ejecucion."""
    return {n: r["func"] for n, r in TOOL_REGISTRY.items()}


def get_tool_names():
    """Retorna lista de nombres de herramientas registradas."""
    return list(TOOL_REGISTRY.keys())
