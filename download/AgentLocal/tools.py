# tools.py - Herramientas disponibles para el Agente Inteligente
# Cada herramienta devuelve un dict con "exito" (bool) y datos o "error".
import requests
import subprocess
import json
import os
from datetime import datetime


# ============================================================
# HERRAMIENTA 1: Búsqueda Web con DuckDuckGo
# ============================================================
def buscar_internet(query: str) -> dict:
    """Busca información en internet usando DuckDuckGo Instant Answer API.
    Úsalo cuando no sepas algo y necesites información actualizada."""
    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1,
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        resultados = []

        # Resumen principal
        if data.get("AbstractText"):
            resultados.append({
                "tipo": "resumen",
                "contenido": data["AbstractText"],
                "url": data.get("AbstractURL", ""),
            })

        # Temas relacionados
        for topic in data.get("RelatedTopics", [])[:8]:
            if isinstance(topic, dict) and "Text" in topic:
                resultados.append({
                    "tipo": "relacionado",
                    "contenido": topic["Text"],
                    "url": topic.get("FirstURL", ""),
                })
            elif isinstance(topic, dict) and "Topics" in topic:
                for sub in topic["Topics"][:3]:
                    if isinstance(sub, dict) and "Text" in sub:
                        resultados.append({
                            "tipo": "relacionado",
                            "contenido": sub["Text"],
                            "url": sub.get("FirstURL", ""),
                        })

        # Definición
        if data.get("Definition"):
            resultados.append({
                "tipo": "definicion",
                "contenido": data["Definition"],
                "url": data.get("DefinitionURL", ""),
            })

        return {
            "exito": len(resultados) > 0,
            "query": query,
            "resultados": resultados,
            "total": len(resultados),
        }
    except requests.Timeout:
        return {"exito": False, "error": "Timeout: la búsqueda tardó demasiado"}
    except Exception as e:
        return {"exito": False, "error": str(e)}


# ============================================================
# HERRAMIENTA 2: Búsqueda Web Profunda con SearXNG
# ============================================================
def buscar_web_profundo(query: str) -> dict:
    """Búsqueda web profunda usando SearXNG (requiere instancia local).
    Devuelve más resultados con más contexto que DuckDuckGo."""
    try:
        from config import Config

        response = requests.get(
            Config.SEARXNG_URL,
            params={"q": query, "format": "json", "language": "es"},
            timeout=15,
        )
        data = response.json()

        resultados = []
        for r in data.get("results", [])[:8]:
            resultados.append({
                "titulo": r.get("title", ""),
                "contenido": r.get("content", ""),
                "url": r.get("url", ""),
            })

        return {
            "exito": len(resultados) > 0,
            "query": query,
            "resultados": resultados,
            "total": len(resultados),
        }
    except Exception:
        # Fallback a DuckDuckGo si SearXNG no está disponible
        return buscar_internet(query)


# ============================================================
# HERRAMIENTA 3: Ejecución de Código Python
# ============================================================
def ejecutar_python(codigo: str) -> dict:
    """Ejecuta código Python de forma segura y devuelve el resultado.
    Úsalo para cálculos, procesar datos, o verificar soluciones."""
    try:
        from config import Config

        result = subprocess.run(
            ["python3", "-c", codigo],
            capture_output=True,
            text=True,
            timeout=Config.CODE_TIMEOUT,
            cwd="/tmp",
        )

        output = result.stdout if result.stdout else result.stderr

        return {
            "exito": result.returncode == 0,
            "output": output[:3000],
            "error": result.stderr[:1000] if result.returncode != 0 else "",
            "codigo_ejecutado": codigo[:500],
        }
    except subprocess.TimeoutExpired:
        return {
            "exito": False,
            "error": f"Timeout: código tardó más de {Config.CODE_TIMEOUT} segundos",
        }
    except Exception as e:
        return {"exito": False, "error": str(e)}


# ============================================================
# HERRAMIENTA 4: Lectura de Archivos
# ============================================================
def leer_archivo(ruta: str) -> dict:
    """Lee un archivo local y devuelve su contenido.
    Úsalo para leer código, configuraciones, o datos."""
    try:
        # Seguridad: solo leer archivos que existen
        ruta = os.path.abspath(ruta)
        if not os.path.isfile(ruta):
            return {"exito": False, "error": f"Archivo no encontrado: {ruta}"}

        with open(ruta, "r", encoding="utf-8") as f:
            contenido = f.read()

        # Obtener info del archivo
        stat = os.stat(ruta)
        size_kb = stat.st_size / 1024

        return {
            "exito": True,
            "contenido": contenido[:15000],
            "ruta": ruta,
            "tamano_kb": round(size_kb, 2),
            "lineas": contenido.count("\n") + 1,
        }
    except PermissionError:
        return {"exito": False, "error": f"Sin permisos para leer: {ruta}"}
    except Exception as e:
        return {"exito": False, "error": str(e)}


# ============================================================
# HERRAMIENTA 5: Escritura de Archivos
# ============================================================
def escribir_archivo(ruta: str, contenido: str) -> dict:
    """Escribe contenido en un archivo local. Crea directorios si no existen.
    Úsalo para crear código, guardar resultados, o generar archivos."""
    try:
        ruta = os.path.abspath(ruta)
        directorio = os.path.dirname(ruta)
        if directorio:
            os.makedirs(directorio, exist_ok=True)

        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)

        return {
            "exito": True,
            "ruta": ruta,
            "bytes_escritos": len(contenido.encode("utf-8")),
        }
    except PermissionError:
        return {"exito": False, "error": f"Sin permisos para escribir: {ruta}"}
    except Exception as e:
        return {"exito": False, "error": str(e)}


# ============================================================
# HERRAMIENTA 6: Listar Directorios
# ============================================================
def listar_directorio(ruta: str = ".") -> dict:
    """Lista archivos y directorios en una ruta dada.
    Úsalo para explorar la estructura de un proyecto."""
    try:
        ruta = os.path.abspath(ruta)
        if not os.path.isdir(ruta):
            return {"exito": False, "error": f"No es un directorio: {ruta}"}

        elementos = []
        for item in sorted(os.listdir(ruta)):
            item_path = os.path.join(ruta, item)
            es_dir = os.path.isdir(item_path)
            elementos.append({
                "nombre": item,
                "tipo": "directorio" if es_dir else "archivo",
                "tamano": os.path.getsize(item_path) if not es_dir else 0,
            })

        return {
            "exito": True,
            "ruta": ruta,
            "elementos": elementos,
            "total": len(elementos),
        }
    except Exception as e:
        return {"exito": False, "error": str(e)}


# ============================================================
# REGISTRO DE HERRAMIENTAS
# Este diccionario le dice al agente qué herramientas tiene
# disponibles y cómo usarlas.
# ============================================================
TOOL_REGISTRY = {
    "buscar_internet": {
        "func": buscar_internet,
        "description": (
            "Busca información en internet cuando no sabes algo "
            "o necesitas información actualizada. Devuelve resúmenes "
            "y enlaces relacionados."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "La consulta de búsqueda en lenguaje natural",
                }
            },
            "required": ["query"],
        },
    },
    "buscar_web_profundo": {
        "func": buscar_web_profundo,
        "description": (
            "Búsqueda web profunda usando SearXNG. Más resultados "
            "que buscar_internet pero requiere SearXNG instalado."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "La consulta de búsqueda",
                }
            },
            "required": ["query"],
        },
    },
    "ejecutar_python": {
        "func": ejecutar_python,
        "description": (
            "Ejecuta código Python y devuelve el resultado. "
            "Útil para cálculos, procesar datos, o verificar soluciones."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "codigo": {
                    "type": "string",
                    "description": "Código Python a ejecutar",
                }
            },
            "required": ["codigo"],
        },
    },
    "leer_archivo": {
        "func": leer_archivo,
        "description": "Lee el contenido de un archivo local del sistema.",
        "parameters": {
            "type": "object",
            "properties": {
                "ruta": {
                    "type": "string",
                    "description": "Ruta al archivo que se quiere leer",
                }
            },
            "required": ["ruta"],
        },
    },
    "escribir_archivo": {
        "func": escribir_archivo,
        "description": "Escribe contenido en un archivo local. Crea directorios si no existen.",
        "parameters": {
            "type": "object",
            "properties": {
                "ruta": {
                    "type": "string",
                    "description": "Ruta del archivo donde escribir",
                },
                "contenido": {
                    "type": "string",
                    "description": "Contenido a escribir en el archivo",
                },
            },
            "required": ["ruta", "contenido"],
        },
    },
    "listar_directorio": {
        "func": listar_directorio,
        "description": "Lista archivos y directorios en una ruta dada.",
        "parameters": {
            "type": "object",
            "properties": {
                "ruta": {
                    "type": "string",
                    "description": "Ruta del directorio a listar (default: '.')",
                }
            },
            "required": [],
        },
    },
}
