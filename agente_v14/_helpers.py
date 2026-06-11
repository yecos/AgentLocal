"""
=============================================================
AGENTE v14 - Helpers para start.bat
=============================================================
Ejecuta verificaciones complejas que son imposibles en .bat
Uso: python _helpers.py <comando> [args]
  check_ollama      - Verifica si Ollama corre, lo inicia si no
  list_models       - Lista modelos disponibles
  check_imports     - Verifica que todos los modulos importen
  check_streamlit   - Verifica si streamlit esta instalado
  check_ollama_lib  - Verifica si la lib ollama de Python esta instalada
  install_deps      - Instala dependencias faltantes
  check_model       - Verifica si hay al menos un modelo descargado
  full_diag         - Diagnostico completo del sistema
  check_port        - Verifica si un puerto esta en uso
  check_gpu_quick   - Verificacion rapida de GPU
  check_versions    - Muestra versiones de todas las dependencias
=============================================================
"""

import sys
import os
import json
import subprocess
import platform
import time

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
            os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe"),
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

        # Esperar con reintentos (hasta 20 segundos)
        for i in range(20):
            time.sleep(1)
            if _is_ollama_running():
                print(f"OK:Ollama iniciado correctamente! ({i+1} seg)")
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
        details = m.get("details", {})
        family = details.get("family", "?")
        fmt = details.get("format", "?")
        print(f"  - {m['name']} ({size_gb:.1f} GB, familia: {family}, formato: {fmt})")
    return 0


def check_imports():
    """Verifica que todos los modulos importen correctamente. Retorna codigo de salida."""
    tests = [
        ("config", "from config import REPOS_DIR, IS_WINDOWS"),
        ("utils.security", "from utils.security import is_dangerous_command, validate_path"),
        ("utils.helpers", "from utils.helpers import strip_prefixes, open_in_browser"),
        ("utils.metrics", "from utils.metrics import get_metrics"),
        ("memory.vectorstore", "from memory.vectorstore import VectorStore"),
        ("memory.chroma_store", "from memory.chroma_store import create_vector_store"),
        ("memory.learning", "from memory.learning import LearningSystem"),
        ("memory.triple_memory", "from memory.triple_memory import TripleMemory"),
        ("tools", "from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS"),
        ("llm", "from llm import ollama"),
        ("agent", "from agent import ReactAgent"),
        ("agent.metacognition", "from agent.metacognition import Metacognition"),
        ("agent.schemas", "from agent.schemas import SYSTEM_PROMPT"),
    ]

    failed = 0
    for name, code in tests:
        try:
            exec(code)
            print(f"OK:{name}")
        except Exception as e:
            print(f"FAIL:{name}: {e}")
            failed += 1

    if failed:
        print(f"\nWARN:{failed} modulo(s) con error de importacion")
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
        ver = getattr(ollama, "__version__", "instalada")
        print(f"OK:ollama python ({ver})")
        return 0
    except ImportError:
        print("MISSING:ollama python (opcional, se usa HTTP directo como fallback)")
        return 0  # Opcional


def install_deps():
    """Instala dependencias faltantes."""
    # Primero intentar con requirements.txt si existe
    req_file = os.path.join(SCRIPT_DIR, "requirements.txt")
    if os.path.exists(req_file):
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("OK:Dependencias instaladas desde requirements.txt")
            return 0
        else:
            print(f"WARN:Error con requirements.txt: {result.stderr[:200]}")
            print("INFO:Instalando manualmente...")

    # Fallback: instalar manualmente
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


def check_model():
    """Verifica si hay al menos un modelo descargado."""
    data = _ollama_request("/api/tags", timeout=5)
    if data is None:
        print("FAIL:No se pudo conectar a Ollama")
        return 2

    models = data.get("models", [])
    if not models:
        print("WARN:No hay modelos. Descarga uno: ollama pull qwen3:4b")
        return 1

    # Verificar si hay un modelo recomendado
    preferred = ["qwen3:4b", "llama3.1:8b", "qwen2.5-coder:7b", "qwen3-coder"]
    model_names = [m["name"] for m in models]
    has_preferred = any(p in " ".join(model_names) for p in preferred)

    if has_preferred:
        print(f"OK:{len(models)} modelos disponibles (incluye modelo recomendado)")
    else:
        print(f"OK:{len(models)} modelos disponibles")
        print("INFO:Ninguno de los modelos recomendados encontrado.")
        print("INFO:Recomendado: ollama pull qwen3:4b")
    return 0


def check_port(port=8501):
    """Verifica si un puerto esta en uso."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(("localhost", port))
            if result == 0:
                print(f"WARN:Puerto {port} en uso")
                return 1
            else:
                print(f"OK:Puerto {port} disponible")
                return 0
    except Exception as e:
        print(f"FAIL:Error verificando puerto {port}: {e}")
        return 2


def check_gpu_quick():
    """Verificacion rapida de GPU para Ollama."""
    is_win = platform.system() == "Windows"

    # Verificar nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.free",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            for line in lines:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    print(f"OK:GPU: {parts[0]}")
                    print(f"INFO:Driver: {parts[1]}")
                    print(f"INFO:VRAM total: {parts[2]}")
                    print(f"INFO:VRAM libre: {parts[3]}")

                    # Verificar si hay suficiente VRAM (al menos 4 GB)
                    vram_str = parts[2].upper()
                    if "MIB" in vram_str:
                        try:
                            vram_mb = int(''.join(filter(str.isdigit, parts[2])))
                            if vram_mb < 4096:
                                print("WARN:VRAM menor a 4 GB. Modelos grandes pueden ser lentos.")
                            else:
                                print("OK:VRAM suficiente para modelos pequenos/medianos")
                        except ValueError:
                            pass

            # Verificar si Ollama esta usando la GPU
            if _is_ollama_running():
                try:
                    ps_result = subprocess.run(
                        ["ollama", "ps"],
                        capture_output=True, text=True, timeout=5
                    )
                    if ps_result.returncode == 0:
                        output = ps_result.stdout
                        if "100% CPU" in output:
                            print("WARN:Ollama esta usando 100% CPU (no GPU)")
                            print("INFO:Solucion: Panel de Control NVIDIA > Alto rendimiento")
                        elif "GPU" in output:
                            print("OK:Ollama esta usando GPU")
                except Exception:
                    pass

            return 0
        else:
            print("WARN:No se detecto GPU NVIDIA")
            return 1
    except FileNotFoundError:
        print("WARN:nvidia-smi no encontrado. No hay GPU NVIDIA o drivers no instalados.")
        return 1
    except subprocess.TimeoutExpired:
        print("WARN:nvidia-smi timeout")
        return 1
    except Exception as e:
        print(f"FAIL:Error verificando GPU: {e}")
        return 2


def check_versions():
    """Muestra versiones de todas las dependencias y componentes."""
    print(f"Python:     {sys.version}")
    print(f"Plataforma: {platform.platform()}")
    print(f"Arquitectura: {platform.architecture()[0]}")

    # Dependencias Python
    deps = [
        ("streamlit", "streamlit"),
        ("ollama", "ollama"),
        ("chromadb", "chromadb"),
        ("numpy", "numpy"),
        ("urllib", None),  # built-in
    ]

    for name, module in deps:
        if module is None:
            print(f"  {name}: built-in")
            continue
        try:
            mod = __import__(module)
            ver = getattr(mod, "__version__", "instalado")
            print(f"  {name}: {ver}")
        except ImportError:
            print(f"  {name}: NO INSTALADO")

    # Ollama
    if _is_ollama_running():
        data = _ollama_request("/api/version", timeout=3)
        if data:
            print(f"  Ollama server: {data.get('version', 'desconocida')}")
        else:
            print("  Ollama server: corriendo (version no disponible)")
    else:
        print("  Ollama server: NO CORRIENDO")

    # Git
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"  Git: {result.stdout.strip()}")
    except Exception:
        print("  Git: no encontrado")

    return 0


def full_diag():
    """Diagnostico completo del sistema."""
    print("=" * 60)
    print("   AGENTE v14 - DIAGNOSTICO COMPLETO")
    print("=" * 60)

    # 1. Versiones
    print("\n--- VERSIONES ---")
    check_versions()

    # 2. Ollama
    print("\n--- OLLAMA ---")
    check_ollama()
    list_models()

    # 3. GPU
    print("\n--- GPU ---")
    check_gpu_quick()

    # 4. Imports
    print("\n--- MODULOS ---")
    check_imports()

    # 5. Puerto
    print("\n--- PUERTO ---")
    check_port(8501)

    # 6. Directorios
    print("\n--- DIRECTORIOS ---")
    dirs = {
        "Documents": os.path.join(os.path.expanduser("~"), "Documents"),
        "ia-local/learning": os.path.join(os.path.expanduser("~"), ".ia-local", "learning"),
        "ia-local/learning/vectors": os.path.join(os.path.expanduser("~"), ".ia-local", "learning", "vectors"),
    }
    for name, path in dirs.items():
        exists = os.path.exists(path)
        writable = os.access(path, os.W_OK) if exists else False
        status = "OK" if exists and writable else ("EXISTS/NO-WRITE" if exists else "MISSING")
        print(f"  {name}: {status} ({path})")

    # 7. Variables de entorno relevantes
    print("\n--- VARIABLES DE ENTORNO ---")
    env_vars = [
        "CUDA_VISIBLE_DEVICES",
        "OLLAMA_HOST",
        "OLLAMA_LLM_LIBRARY",
        "OLLAMA_KEEP_ALIVE",
        "OLLAMA_MAX_VRAM",
        "OLLAMA_VULKAN",
        "HTTP_PROXY",
        "HTTPS_PROXY",
    ]
    for var in env_vars:
        val = os.environ.get(var, "(no definida)")
        if val != "(no definida)":
            print(f"  {var} = {val} <-- DEFINIDA")
        else:
            print(f"  {var} = {val}")

    print("\n" + "=" * 60)
    print("   DIAGNOSTICO COMPLETADO")
    print("=" * 60)
    return 0


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python _helpers.py <comando>")
        print()
        print("Comandos:")
        print("  check_ollama      - Verifica si Ollama corre, lo inicia si no")
        print("  list_models       - Lista modelos disponibles")
        print("  check_imports     - Verifica que todos los modulos importen")
        print("  check_streamlit   - Verifica si streamlit esta instalado")
        print("  check_ollama_lib  - Verifica si la lib ollama de Python esta instalada")
        print("  install_deps      - Instala dependencias faltantes")
        print("  check_model       - Verifica si hay al menos un modelo")
        print("  check_port        - Verifica si el puerto 8501 esta en uso")
        print("  check_gpu_quick   - Verificacion rapida de GPU")
        print("  check_versions    - Muestra versiones de todas las deps")
        print("  full_diag         - Diagnostico completo del sistema")
        sys.exit(1)

    cmd = sys.argv[1]

    commands = {
        "check_ollama": check_ollama,
        "list_models": list_models,
        "check_imports": check_imports,
        "check_streamlit": check_streamlit,
        "check_ollama_lib": check_ollama_lib,
        "install_deps": install_deps,
        "check_model": check_model,
        "check_port": check_port,
        "check_gpu_quick": check_gpu_quick,
        "check_versions": check_versions,
        "full_diag": full_diag,
    }

    if cmd in commands:
        sys.exit(commands[cmd]())
    else:
        print(f"Comando desconocido: {cmd}")
        print(f"Comandos disponibles: {', '.join(commands.keys())}")
        sys.exit(1)
