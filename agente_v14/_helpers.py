"""
=============================================================
AGENTE v14 - Helpers para start.bat
=============================================================
Ejecuta verificaciones complejas que son imposibles en .bat
Uso: python _helpers.py <comando> [args]
  check_ollama     - Verifica si Ollama corre, lo inicia si no
  list_models      - Lista modelos disponibles
  check_imports    - Verifica que todos los modulos importen
  install_deps     - Instala dependencias faltantes
=============================================================
"""

import sys
import os
import json
import subprocess
import platform

# Agregar el directorio de este script al path para imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def _ollama_request(endpoint, timeout=3):
    """Hace un request a la API de Ollama. Retorna dict o None."""
    try:
        import urllib.request
        url = f"http://localhost:11434{endpoint}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _is_ollama_running():
    """Verifica si Ollama esta corriendo."""
    return _ollama_request("/api/tags") is not None


def _start_ollama():
    """Intenta iniciar Ollama en Windows."""
    is_win = platform.system() == "Windows"

    if is_win:
        # Metodo 1: ollama app (system tray app en Windows)
        try:
            subprocess.Popen(
                ["ollama", "app"],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

        # Metodo 2: buscar en Start Menu / instalacion por defecto
        ollama_paths = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama app.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama app.exe"),
        ]
        for path in ollama_paths:
            if os.path.exists(path):
                try:
                    subprocess.Popen(
                        [path],
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    break
                except Exception:
                    continue
    else:
        # Linux/Mac
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception:
            pass


def check_ollama():
    """Verifica Ollama. Lo inicia si no esta corriendo. Retorna codigo de salida."""
    if _is_ollama_running():
        print("OK:Ollama corriendo en localhost:11434")
        return 0

    print("WARN:Ollama no responde en localhost:11434")

    # Intentar iniciar
    where_result = subprocess.run(
        ["where", "ollama"] if platform.system() == "Windows" else ["which", "ollama"],
        capture_output=True, text=True
    )

    if where_result.returncode == 0:
        print("INFO:Ollama instalado. Intentando iniciar...")
        _start_ollama()

        # Esperar con reintentos (hasta 15 segundos)
        import time
        for i in range(15):
            time.sleep(1)
            if _is_ollama_running():
                print("OK:Ollama iniciado correctamente!")
                return 0

        print("WARN:Ollama no pudo iniciarse. Inicielo manualmente.")
        return 1
    else:
        print("FAIL:Ollama no encontrado. Instalalo desde https://ollama.com")
        return 2


def list_models():
    """Lista modelos disponibles. Retorna codigo de salida."""
    data = _ollama_request("/api/tags", timeout=5)
    if data is None:
        print("FAIL:No se pudo conectar a Ollama")
        return 1

    models = data.get("models", [])
    if not models:
        print("WARN:No hay modelos descargados. Ejecuta: ollama pull qwen3:4b")
        return 1

    for m in models:
        size_gb = m.get("size", 0) / (1024**3)
        print(f"  - {m['name']} ({size_gb:.1f} GB)")
    return 0


def check_imports():
    """Verifica que todos los modulos importen correctamente. Retorna codigo de salida."""
    tests = [
        ("config", "from config import REPOS_DIR, IS_WINDOWS"),
        ("utils.security", "from utils.security import is_dangerous_command, validate_path"),
        ("utils.helpers", "from utils.helpers import strip_prefixes, open_in_browser"),
        ("memory.vectorstore", "from memory.vectorstore import VectorStore"),
        ("memory.chroma_store", "from memory.chroma_store import create_vector_store"),
        ("memory.learning", "from memory.learning import LearningSystem"),
        ("memory.triple_memory", "from memory.triple_memory import TripleMemory"),
        ("tools", "from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS"),
        ("llm", "from llm import ollama"),
        ("agent", "from agent import ReactAgent"),
    ]

    failed = 0
    for name, code in tests:
        try:
            exec(code)
            print(f"OK:{name}")
        except Exception as e:
            print(f"FAIL:{name}: {e}")
            failed += 1

    return 1 if failed else 0


def check_streamlit():
    """Verifica si streamlit esta instalado."""
    try:
        import streamlit
        print(f"OK:streamlit {streamlit.__version__}")
        return 0
    except ImportError:
        print("MISSING:streamlit")
        return 1


def check_ollama_lib():
    """Verifica si la lib ollama de Python esta instalada."""
    try:
        import ollama
        print("OK:ollama python")
        return 0
    except ImportError:
        print("MISSING:ollama python (opcional)")
        return 0  # Opcional


def install_deps():
    """Instala dependencias faltantes."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "streamlit", "ollama", "chromadb", "--quiet"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("OK:Dependencias instaladas")
        return 0
    else:
        print(f"FAIL:Error instalando: {result.stderr[:200]}")
        return 1


def check_model_available():
    """Verifica si hay al menos un modelo descargado."""
    data = _ollama_request("/api/tags", timeout=5)
    if data is None:
        print("FAIL:No se pudo conectar a Ollama")
        return 2

    models = data.get("models", [])
    if not models:
        print("WARN:No hay modelos. Descarga uno: ollama pull qwen3:4b")
        return 1

    print(f"OK:{len(models)} modelos disponibles")
    return 0


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python _helpers.py <comando>")
        print("Comandos: check_ollama, list_models, check_imports, check_streamlit, check_ollama_lib, install_deps, check_model_available")
        sys.exit(1)

    cmd = sys.argv[1]

    commands = {
        "check_ollama": check_ollama,
        "list_models": list_models,
        "check_imports": check_imports,
        "check_streamlit": check_streamlit,
        "check_ollama_lib": check_ollama_lib,
        "install_deps": install_deps,
        "check_model_available": check_model_available,
    }

    if cmd in commands:
        sys.exit(commands[cmd]())
    else:
        print(f"Comando desconocido: {cmd}")
        sys.exit(1)
