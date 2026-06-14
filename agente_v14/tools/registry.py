"""
=============================================================
AGENTE v14 - Registry de Herramientas con Decorador
=============================================================
Registro centralizado de herramientas usando @tool decorator.

Uso:
    from tools.registry import tool, TOOL_FUNCTIONS, TOOL_SCHEMAS

    @tool(schema={...})        # con schema para function calling
    def mi_herramienta(x: str) -> str:
        \"\"\"Descripcion de la herramienta.\"\"\"
        return x

    @tool                       # sin schema
    def otra_herramienta():
        pass

    # Registro manual:
    register_tool("nombre", func, schema={...})
=============================================================
"""

from __future__ import annotations

import inspect
import functools
from typing import Any, Callable

# ============================================================
# REGISTROS GLOBALES
# ============================================================

TOOL_FUNCTIONS: dict[str, Callable] = {}   # {name: callable}
TOOL_SCHEMAS: list[dict] = []     # [{type: "function", function: {...}}, ...]

# Metadata extendida por herramienta
_TOOL_METADATA: dict[str, dict] = {}   # {name: {"func": callable, "schema": dict|None, "description": str}}


# ============================================================
# FUNCION DE REGISTRO MANUAL
# ============================================================

def register_tool(
    name: str,
    func: Callable,
    schema: dict | None = None,
    *,
    overwrite: bool = False,
) -> None:
    """Registra una herramienta manualmente en el registry.

    Args:
        name: Nombre de la herramienta (clave en TOOL_FUNCTIONS).
        func: Funcion callable a registrar.
        schema: Schema de function calling para Ollama (formato completo).
            Si es None, se intenta generar uno basico automaticamente.
            Puede ser el schema completo con ``"type"``/``"function"`` keys,
            o solo la parte ``"function"`` (se envuelve automaticamente).
        overwrite: Si True, permite sobrescribir una herramienta existente.
            Si False (default), NO sobrescribe y emite warning.

    Raises:
        TypeError: Si func no es callable.
    """
    if not callable(func):
        raise TypeError(f"register_tool: func debe ser callable, se recibio {type(func)}")

    if name in TOOL_FUNCTIONS:
        if not overwrite:
            import logging
            logging.getLogger(__name__).debug(
                f"Herramienta '{name}' ya registrada, omitiendo duplicado (usar overwrite=True para forzar)"
            )
            return
        import warnings
        warnings.warn(
            f"Registro de herramienta: '{name}' ya existe y sera sobrescrito.",
            stacklevel=2
        )

    # Registrar en TOOL_FUNCTIONS
    TOOL_FUNCTIONS[name] = func

    # Extraer descripcion del docstring si no hay schema
    description = ""
    if func.__doc__:
        # Tomar solo la primera linea del docstring como descripcion
        description = func.__doc__.strip().split("\n")[0].strip()

    # Procesar schema
    if schema is not None:
        # Si el schema ya tiene formato completo de Ollama, usarlo directamente
        if "type" in schema and "function" in schema:
            TOOL_SCHEMAS.append(schema)
        else:
            # Si es solo la parte "function", envolver en formato Ollama
            full_schema = {
                "type": "function",
                "function": schema
            }
            TOOL_SCHEMAS.append(full_schema)
    else:
        # Auto-generar schema basico desde type hints y docstring
        auto_schema = _build_auto_schema(name, func, description)
        if auto_schema:
            TOOL_SCHEMAS.append(auto_schema)

    # Guardar metadata
    _TOOL_METADATA[name] = {
        "func": func,
        "schema": schema,
        "description": description,
    }


# ============================================================
# DECORADOR @tool
# ============================================================

def tool(
    func: Callable | None = None,
    *,
    schema: dict | None = None,
) -> Callable | Callable[[Callable], Callable]:
    """Decorador para registrar automaticamente una herramienta.

    Soporta tres formas de uso::

        @tool
        def mi_func():
            pass

        @tool()
        def mi_func():
            pass

        @tool(schema={\"name\": \"mi_func\", ...})
        def mi_func():
            pass

    Args:
        func: La funcion a decorar (cuando se usa sin parentesis).
        schema: Schema de function calling para Ollama (opcional).

    Returns:
        El wrapper de la funcion decorada con atributos ``_is_tool``,
        ``_tool_name`` y ``_tool_schema``, o un decorador si se usa con
        argumentos.
    """
    def decorator(fn: Callable) -> Callable:
        # Obtener nombre de la herramienta
        name = fn.__name__

        # Registrar la herramienta
        register_tool(name, fn, schema=schema)

        # Marcar la funcion como herramienta registrada
        fn._is_tool = True
        fn._tool_name = name
        fn._tool_schema = schema

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        # Preservar marca en el wrapper tambien
        wrapper._is_tool = True
        wrapper._tool_name = name
        wrapper._tool_schema = schema

        return wrapper

    # Si se usa como @tool (sin parentesis), func es la funcion
    if func is not None:
        return decorator(func)

    # Si se usa como @tool(schema=...), devolver el decorador
    return decorator


# ============================================================
# AUTO-GENERACION DE SCHEMAS
# ============================================================

def _build_auto_schema(name: str, func: Callable, description: str) -> dict | None:
    """Genera un schema de function calling basico desde type hints.

    Inspecciona la signatura de la funcion para extraer parametros,
    sus tipos y descripciones (desde la seccion Args: del docstring),
    y construye un schema compatible con el formato Ollama function calling.

    Args:
        name: Nombre de la herramienta.
        func: Funcion a inspeccionar.
        description: Descripcion extraida del docstring de la funcion.

    Returns:
        Schema en formato Ollama (``{"type": "function", "function": {...}}``)
        o None si no se puede obtener la signatura de la funcion.
    """
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return None

    properties = {}
    required = []

    # Mapeo de tipos Python -> JSON Schema
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    for param_name, param in sig.parameters.items():
        # Ignorar 'self' y 'cls'
        if param_name in ("self", "cls"):
            continue

        # Determinar tipo JSON
        json_type = "string"  # default
        if param.annotation != inspect.Parameter.empty:
            json_type = type_map.get(param.annotation, "string")

        # Construir propiedad
        prop = {"type": json_type}

        # Intentar extraer descripcion del docstring (Args section)
        param_desc = _extract_param_description(func.__doc__, param_name)
        if param_desc:
            prop["description"] = param_desc

        properties[param_name] = prop

        # Es requerido si no tiene valor por defecto
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    # Si no hay propiedades, no generar schema (ej: ver_notas)
    # Todavia generamos uno con properties vacias para consistencia
    schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": description or f"Herramienta: {name}",
            "parameters": {
                "type": "object",
                "properties": properties,
            }
        }
    }

    if required:
        schema["function"]["parameters"]["required"] = required
    else:
        schema["function"]["parameters"]["required"] = []

    return schema


def _extract_param_description(docstring: str | None, param_name: str) -> str | None:
    """Extrae la descripcion de un parametro del docstring (formato Args:).

    Parsea la seccion ``Args:`` del docstring buscando la descripcion
    asociada al parametro dado. Soporta formatos como:
        ``param_name: descripcion``
        ``param (tipo): descripcion``

    Args:
        docstring: El docstring completo de la funcion, o None.
        param_name: Nombre del parametro a buscar.

    Returns:
        La descripcion del parametro, o None si no se encuentra.
    """
    if not docstring:
        return None

    lines = docstring.split("\n")
    in_args = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Args:"):
            in_args = True
            continue
        if in_args:
            # Detectar nueva seccion (ej: Returns:, Raises:)
            if stripped and not stripped.startswith(param_name[:1]) and ":" in stripped:
                if not stripped.startswith(" "):
                    break
            # Buscar parametro por nombre
            if param_name in stripped:
                # Formato: "param_name: descripcion" o "param (tipo): desc"
                parts = stripped.split(":", 1)
                if len(parts) > 1 and param_name in parts[0]:
                    desc = parts[1].strip()
                    if desc:
                        return desc

    return None


# ============================================================
# UTILIDADES DEL REGISTRY
# ============================================================

def get_tool_metadata(name: str) -> dict | None:
    """Retorna la metadata completa de una herramienta registrada.

    Args:
        name: Nombre de la herramienta.

    Returns:
        Diccionario con keys ``"func"``, ``"schema"`` y ``"description"``,
        o None si la herramienta no esta registrada.
    """
    return _TOOL_METADATA.get(name)


def list_tools() -> list[str]:
    """Retorna los nombres de todas las herramientas registradas.

    Returns:
        Lista de nombres (str) de herramientas registradas.
    """
    return list(TOOL_FUNCTIONS.keys())


def tool_count() -> int:
    """Retorna la cantidad de herramientas registradas.

    Returns:
        Numero entero de herramientas registradas.
    """
    return len(TOOL_FUNCTIONS)


def clear_registry() -> None:
    """Limpia todo el registry. Util para testing.

    Vacia TOOL_FUNCTIONS, TOOL_SCHEMAS y _TOOL_METADATA.
    """
    TOOL_FUNCTIONS.clear()
    TOOL_SCHEMAS.clear()
    _TOOL_METADATA.clear()
