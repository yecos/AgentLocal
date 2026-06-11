"""
=============================================================================
  AGENTE AUTÓNOMO PRO v3 - Con Tool Calling NATIVO de Ollama
=============================================================================
  Esta versión usa la API nativa de tool/function calling de Ollama.
  El modelo YA NO da instrucciones en texto - EJECUTA herramientas directamente
  porque Ollama lo obliga a devolver llamadas estructuradas.

  Modelos que soportan tool calling:
  - qwen2.5:14b ✅ (recomendado)
  - qwen2.5:7b ✅
  - llama3.1:8b ✅
  
  Requisitos:
  pip install streamlit ollama chromadb pypdf ddgs psutil
  Ollama >= 0.4
=============================================================================
"""

import streamlit as st
import ollama
import json
import os
import sys
import subprocess
import platform
import datetime
import re
import shutil
import time
import urllib.request
import urllib.error
from pathlib import Path

# =====================================================================
# CONFIGURACIÓN
# =====================================================================

AGENT_MODEL = "qwen2.5:14b"
CHAT_MODEL = "llama3.1:8b"
CODE_MODEL = "qwen2.5-coder:7b"

IS_WINDOWS = platform.system() == "Windows"

USER_HOME = os.path.expanduser("~")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
DOCUMENTS_DIR = os.path.join(USER_HOME, "Documents")
DESKTOP_DIR = os.path.join(USER_HOME, "Desktop")
PROJECTS_DIR = os.path.join(USER_HOME, "Projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

BACKUP_DIR = os.path.join(USER_HOME, ".ia-backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

CONFIG_DIR = os.path.join(USER_HOME, ".ia-local")
os.makedirs(CONFIG_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIR, "bridge_config.json")

DANGEROUS_COMMANDS = [
    "rm ", "del ", "rmdir", "format", "mkfs", "dd ",
    "shutdown", "restart", "reboot",
    "reg ", "registry", "net user", "net localgroup",
    "taskkill", "kill ", "pkill",
    "format ", "fdisk", "diskpart",
    "docker rm", "docker rmi", "docker system prune",
    "Remove-Item", "rm -rf", "rm -r",
]

BLOCKED_COMMANDS = [
    "format c:", "format d:", "del /f /s /q c:", "del /f /s /q d:",
    "rm -rf /", "rm -rf /*", "rd /s /q c:", "rd /s /q d:",
    "shutdown /s", "shutdown /r",
]

DEFAULT_COMMAND_TIMEOUT = 120

# =====================================================================
# CONFIGURACIÓN DE PÁGINA
# =====================================================================

st.set_page_config(
    page_title="IA Local Pro - Agente Autónomo",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp { max-width: 1400px; margin: 0 auto; }
    .tool-result {
        background: #1e1e2e;
        border: 1px solid #45475a;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        font-family: 'Consolas', monospace;
        font-size: 13px;
        color: #cdd6f4;
        white-space: pre-wrap;
        max-height: 400px;
        overflow-y: auto;
    }
    .tool-cmd {
        background: #1e1e2e;
        border: 1px solid #89b4fa;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        font-family: 'Consolas', monospace;
        font-size: 13px;
        color: #89b4fa;
    }
    .tool-success {
        background: #1e1e2e;
        border: 1px solid #a6e3a1;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        color: #a6e3a1;
    }
    .bridge-box {
        background: linear-gradient(135deg, #1e1e2e, #1e3a5f);
        border: 1px solid #89b4fa;
        border-radius: 10px;
        padding: 16px;
        margin: 12px 0;
        color: #89b4fa;
    }
    .plan-box {
        background: linear-gradient(135deg, #1e1e2e, #313244);
        border: 1px solid #cba6f7;
        border-radius: 10px;
        padding: 16px;
        margin: 12px 0;
        color: #cba6f7;
    }
</style>
""", unsafe_allow_html=True)

# =====================================================================
# IA BRIDGE - Conexión con IA en la nube
# =====================================================================

PROVEEDORES = {
    "groq": {
        "nombre": "Groq (GRATIS - Súper rápido)",
        "url_base": "https://api.groq.com/openai/v1",
        "modelos": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],
        "modelo_default": "llama-3.3-70b-versatile",
        "como_obtener_key": "https://console.groq.com/keys",
        "gratis": True,
        "descripcion": "Gratis, muy rápido, buenos modelos."
    },
    "openrouter": {
        "nombre": "OpenRouter (Múltiples modelos)",
        "url_base": "https://openrouter.ai/api/v1",
        "modelos": ["meta-llama/llama-3.3-70b-instruct:free", "deepseek/deepseek-chat:free", "qwen/qwen-2.5-72b-instruct:free"],
        "modelo_default": "meta-llama/llama-3.3-70b-instruct:free",
        "como_obtener_key": "https://openrouter.ai/keys",
        "gratis": True,
        "descripcion": "Acceso a muchos modelos con opciones gratuitas."
    },
    "openai": {
        "nombre": "OpenAI (GPT-4)",
        "url_base": "https://api.openai.com/v1",
        "modelos": ["gpt-4o", "gpt-4o-mini"],
        "modelo_default": "gpt-4o-mini",
        "como_obtener_key": "https://platform.openai.com/api-keys",
        "gratis": False,
        "descripcion": "La IA más conocida. De pago pero muy capaz."
    },
    "deepseek": {
        "nombre": "DeepSeek (Barato y muy bueno)",
        "url_base": "https://api.deepseek.com/v1",
        "modelos": ["deepseek-chat", "deepseek-reasoner"],
        "modelo_default": "deepseek-chat",
        "como_obtener_key": "https://platform.deepseek.com/api_keys",
        "gratis": False,
        "descripcion": "Excelente para código a bajo precio."
    }
}

def load_bridge_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"proveedor": "groq", "api_key": "", "modelo": "", "contexto_proyecto": "", "historial_consultas": []}

def save_bridge_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def call_cloud_api(url_base, api_key, model, messages, temperature=0.7, max_tokens=2048):
    endpoint = f"{url_base}/chat/completions"
    payload = json.dumps({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}).encode('utf-8')
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    if "openrouter" in url_base:
        headers["HTTP-Referer"] = "https://ia-local.app"
        headers["X-Title"] = "IA Local Pro"
    req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            return {"success": True, "content": result["choices"][0]["message"]["content"]}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        try:
            error_msg = json.loads(error_body).get("error", {}).get("message", error_body[:200])
        except:
            error_msg = error_body[:200]
        return {"success": False, "error": f"HTTP {e.code}: {error_msg}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def consultar_experto(pregunta, contexto="", modo="general"):
    config = load_bridge_config()
    if not config.get("api_key"):
        return "❌ No hay API key configurada. Configúrala en ☁️ IA Bridge en el sidebar."
    proveedor = config.get("proveedor", "groq")
    prov_config = PROVEEDORES.get(proveedor, PROVEEDORES["groq"])
    modelo = config.get("modelo") or prov_config["modelo_default"]
    system_prompts = {
        "general": "Eres un experto consultor. Respondes en español.",
        "codigo": "Eres un programador experto senior. Código en inglés, explicaciones en español.",
        "analisis": "Eres un analista de software experto. Respondes en español.",
        "plan": "Eres un arquitecto de software. Creas planes detallados. Respondes en español."
    }
    messages = [{"role": "system", "content": system_prompts.get(modo, system_prompts["general"])}]
    contexto_proyecto = config.get("contexto_proyecto", "")
    if contexto_proyecto:
        messages.append({"role": "system", "content": f"Contexto del proyecto:\n{contexto_proyecto}"})
    if contexto:
        messages.append({"role": "user", "content": f"Contexto:\n{contexto}\n\nPregunta: {pregunta}"})
    else:
        messages.append({"role": "user", "content": pregunta})
    result = call_cloud_api(prov_config["url_base"], config["api_key"], modelo, messages)
    if result["success"]:
        return result["content"]
    return f"❌ Error consultando IA: {result['error']}"

def test_bridge_connection():
    config = load_bridge_config()
    if not config.get("api_key"):
        return False, "No hay API key configurada"
    proveedor = config.get("proveedor", "groq")
    prov_config = PROVEEDORES.get(proveedor, PROVEEDORES["groq"])
    modelo = config.get("modelo") or prov_config["modelo_default"]
    result = call_cloud_api(prov_config["url_base"], config["api_key"], modelo,
        [{"role": "user", "content": "Responde solo: CONEXION_OK"}], temperature=0, max_tokens=10)
    if result["success"]:
        return True, f"✅ Conexión exitosa con {prov_config['nombre']}"
    return False, f"❌ Error: {result['error']}"

# =====================================================================
# FUNCIONES AUXILIARES
# =====================================================================

def create_backup(filepath):
    try:
        if os.path.exists(filepath):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            basename = os.path.basename(filepath)
            backup_path = os.path.join(BACKUP_DIR, f"{basename}.{timestamp}.bak")
            shutil.copy2(filepath, backup_path)
            return backup_path
    except:
        pass
    return None

def is_dangerous_command(cmd):
    cmd_lower = cmd.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return "blocked"
    for dangerous in DANGEROUS_COMMANDS:
        if dangerous.lower() in cmd_lower:
            return "dangerous"
    return "safe"

def run_command(command, cwd=None, timeout=DEFAULT_COMMAND_TIMEOUT):
    try:
        danger_level = is_dangerous_command(command)
        if danger_level == "blocked":
            return "⛔ COMANDO BLOQUEADO por seguridad.", -1
        if danger_level == "dangerous":
            return "⚠️ Comando peligroso. Requiere confirmación.", -2
        result = subprocess.run(command, shell=IS_WINDOWS, capture_output=True, text=True,
            timeout=timeout, cwd=cwd, encoding='utf-8', errors='replace')
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[STDERR]: {result.stderr}"
        if not output.strip():
            output = "(Comando ejecutado sin salida visible)"
        return output.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return f"⏱️ Tiempo agotado ({timeout}s).", -3
    except FileNotFoundError:
        return "❌ Comando no encontrado.", -4
    except Exception as e:
        return f"❌ Error: {str(e)}", -5

def force_run_command(command, cwd=None, timeout=DEFAULT_COMMAND_TIMEOUT):
    try:
        result = subprocess.run(command, shell=IS_WINDOWS, capture_output=True, text=True,
            timeout=timeout, cwd=cwd, encoding='utf-8', errors='replace')
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[STDERR]: {result.stderr}"
        if not output.strip():
            output = "(Comando ejecutado sin salida visible)"
        return output.strip(), result.returncode
    except Exception as e:
        return f"❌ Error: {str(e)}", -5

# =====================================================================
# IMPLEMENTACIÓN DE HERRAMIENTAS (funciones reales)
# =====================================================================

def tool_ejecutar_comando(comando: str, directorio: str = None) -> str:
    """Ejecuta un comando del sistema operativo como git, npm, pip, python, dir, etc."""
    cwd = directorio if directorio and os.path.isdir(directorio) else None
    if cwd:
        result, code = run_command(comando, cwd=cwd)
    else:
        result, code = run_command(comando)
    if code == -2:
        return result + "\n\nSi estás seguro, indica que se fuerce la ejecución."
    return result

def tool_clonar_repositorio(url: str, directorio_destino: str = None) -> str:
    """Clona un repositorio de GitHub automáticamente. Descarga todo el código del proyecto."""
    if not url.startswith("https://github.com/") and not url.startswith("git@github.com:"):
        return "❌ URL inválida. Debe ser una URL de GitHub (https://github.com/usuario/repo)."
    if not directorio_destino:
        repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
        directorio_destino = os.path.join(PROJECTS_DIR, repo_name)
    if os.path.exists(directorio_destino):
        return f"⚠️ El directorio ya existe: {directorio_destino}\nUsa ejecutar_comando con 'git pull' para actualizar."
    result, code = run_command(f'git clone {url} "{directorio_destino}"')
    if code == 0:
        return f"✅ Repositorio clonado exitosamente en: {directorio_destino}\n\nContenido:\n" + tool_listar_archivos(directorio_destino, 2)
    return f"❌ Error clonando repositorio:\n{result}"

def tool_instalar_dependencias(directorio: str, tipo: str = None) -> str:
    """Instala las dependencias de un proyecto. Detecta automáticamente si es npm o pip."""
    if not os.path.isdir(directorio):
        return f"❌ Directorio no encontrado: {directorio}"
    if not tipo:
        if os.path.exists(os.path.join(directorio, "package.json")):
            tipo = "npm"
        elif os.path.exists(os.path.join(directorio, "requirements.txt")):
            tipo = "pip"
        elif os.path.exists(os.path.join(directorio, "pyproject.toml")):
            tipo = "pip"
        else:
            return "❌ No se detectó tipo de proyecto. Especifica: npm o pip."
    if tipo == "npm":
        result, code = run_command("npm install", cwd=directorio, timeout=300)
        if code == 0:
            return f"✅ Dependencias npm instaladas en: {directorio}\n\n{result[:500]}"
        return f"❌ Error instalando npm:\n{result}"
    elif tipo == "pip":
        req_file = os.path.join(directorio, "requirements.txt")
        if os.path.exists(req_file):
            result, code = run_command(f'pip install -r "{req_file}"', cwd=directorio, timeout=300)
            if code == 0:
                return f"✅ Dependencias pip instaladas\n\n{result[:500]}"
            return f"❌ Error instalando pip:\n{result}"
        return "❌ No se encontró requirements.txt"
    return f"❌ Tipo no soportado: {tipo}"

def tool_listar_archivos(ruta: str, profundidad: int = 3) -> str:
    """Lista los archivos y carpetas de un directorio. Muestra la estructura del proyecto."""
    if not os.path.exists(ruta):
        return f"❌ Ruta no encontrada: {ruta}"
    if os.path.isfile(ruta):
        return f"📄 Archivo: {ruta} ({os.path.getsize(ruta)} bytes)"
    resultado = [f"📂 {ruta}\n"]
    for root, dirs, files in os.walk(ruta):
        rel_path = os.path.relpath(root, ruta)
        depth = rel_path.count(os.sep) if rel_path != "." else 0
        if depth >= profundidad:
            dirs.clear()
            continue
        skip_dirs = ['node_modules', '.git', '.next', '__pycache__', '.venv', 'venv', 'dist', '.cache', '.turbo']
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
        indent = "  " * (depth + 1)
        for d in sorted(dirs):
            resultado.append(f"{indent}📁 {d}/")
        for f in sorted(files):
            size = 0
            try:
                size = os.path.getsize(os.path.join(root, f))
            except:
                pass
            size_str = f" ({size}b)" if size < 1024 else f" ({size//1024}kb)"
            resultado.append(f"{indent}📄 {f}{size_str}")
    return "\n".join(resultado)

def tool_leer_archivo(ruta: str) -> str:
    """Lee el contenido completo de un archivo de texto o código fuente."""
    if not os.path.exists(ruta):
        return f"❌ Archivo no encontrado: {ruta}"
    try:
        with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
            contenido = f.read()
        if len(contenido) > 15000:
            contenido = contenido[:15000] + f"\n\n... [Truncado - {len(contenido)} caracteres total]"
        return contenido
    except Exception as e:
        return f"❌ Error leyendo archivo: {str(e)}"

def tool_escribir_archivo(ruta: str, contenido: str) -> str:
    """Escribe contenido en un archivo. Crea el archivo si no existe. Hace backup automático."""
    try:
        directorio = os.path.dirname(ruta)
        if directorio:
            os.makedirs(directorio, exist_ok=True)
        backup_path = create_backup(ruta)
        backup_msg = f"\n📦 Backup: {backup_path}" if backup_path else ""
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(contenido)
        return f"✅ Archivo escrito: {ruta} ({len(contenido)} caracteres){backup_msg}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def tool_modificar_archivo(ruta: str, texto_original: str, texto_nuevo: str) -> str:
    """Modifica una parte específica de un archivo. Busca texto_original y lo reemplaza con texto_nuevo."""
    if not os.path.exists(ruta):
        return f"❌ Archivo no encontrado: {ruta}"
    try:
        with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
            contenido = f.read()
        if texto_original not in contenido:
            return f"❌ Texto no encontrado. Usa leer_archivo primero para ver el contenido exacto."
        backup_path = create_backup(ruta)
        backup_msg = f"\n📦 Backup: {backup_path}" if backup_path else ""
        nuevo_contenido = contenido.replace(texto_original, texto_nuevo)
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(nuevo_contenido)
        return f"✅ Archivo modificado: {ruta}{backup_msg}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def tool_buscar_en_archivos(directorio: str, texto: str, extension: str = None) -> str:
    """Busca un texto dentro de todos los archivos de un directorio (como grep)."""
    if not os.path.isdir(directorio):
        return f"❌ Directorio no encontrado: {directorio}"
    resultados = []
    skip_dirs = ['node_modules', '.git', '.next', '__pycache__', '.venv', 'venv', 'dist', '.cache', '.turbo', 'build']
    skip_exts = ['.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.woff', '.woff2', '.ttf', '.eot', '.map', '.lock']
    for root, dirs, files in os.walk(directorio):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
        for fname in files:
            fpath = os.path.join(root, fname)
            _, ext = os.path.splitext(fname)
            if ext.lower() in skip_exts:
                continue
            if extension and ext.lower() != extension.lower():
                continue
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    for i, line in enumerate(f, 1):
                        if texto.lower() in line.lower():
                            rel_path = os.path.relpath(fpath, directorio)
                            resultados.append(f"{rel_path}:{i} → {line.strip()[:120]}")
                            if len(resultados) >= 50:
                                return "\n".join(resultados) + "\n\n... [50 resultados máximo]"
            except:
                continue
    if not resultados:
        return f"🔍 No se encontró '{texto}' en {directorio}"
    return "\n".join(resultados)

def tool_calcular(expresion: str) -> str:
    """Evalúa una expresión matemática. Solo acepta números y operadores."""
    expresion = expresion.replace("^", "**")
    if not re.match(r'^[\d\s\+\-\*\/\.\(\)eE]+$', expresion):
        return "❌ Solo números y operadores (+, -, *, /, (), **)"
    try:
        return str(eval(expresion, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"❌ Error: {str(e)}"

def tool_buscar(consulta: str) -> str:
    """Busca información en internet usando DuckDuckGo."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(consulta, max_results=5))
        if not results:
            return "🔍 No se encontraron resultados"
        return "\n\n".join([f"📌 {r.get('title', '')}\n   {r.get('body', '')}\n   🔗 {r.get('href', '')}" for r in results])
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(consulta, max_results=5))
            if not results:
                return "🔍 No se encontraron resultados"
            return "\n\n".join([f"📌 {r.get('title', '')}\n   {r.get('body', '')}\n   🔗 {r.get('href', '')}" for r in results])
        except ImportError:
            return "❌ Instala: pip install ddgs"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def tool_consultar_experto(pregunta: str, modo: str = "general") -> str:
    """Consulta con una IA avanzada en la nube para tareas complejas o cuando se necesita razonamiento profundo."""
    return consultar_experto(pregunta, modo=modo)

def tool_consultar_plan(tarea: str, contexto: str = "") -> str:
    """Pide a la IA avanzada que cree un plan de implementación detallado paso a paso."""
    return consultar_experto(tarea, contexto=contexto, modo="plan")

def tool_info_sistema() -> str:
    """Muestra información del sistema: OS, RAM, disco, CPU, proyectos."""
    info = [f"🖥️ Sistema: {platform.system()} {platform.release()}", f"💻 Procesador: {platform.processor()}",
            f"🏠 Usuario: {USER_HOME}", f"📂 Proyectos: {PROJECTS_DIR}"]
    try:
        if IS_WINDOWS:
            for drive in ['C:', 'D:']:
                if os.path.exists(drive + '\\'):
                    usage = shutil.disk_usage(drive + '\\')
                    info.append(f"💾 Disco {drive}: {usage.free // (1024**3)}GB libres de {usage.total // (1024**3)}GB")
    except:
        pass
    try:
        import psutil
        mem = psutil.virtual_memory()
        info.append(f"🧠 RAM: {mem.available // (1024**3)}GB disponibles de {mem.total // (1024**3)}GB")
    except:
        info.append("🧠 RAM: (pip install psutil)")
    bridge_config = load_bridge_config()
    if bridge_config.get("api_key"):
        info.append(f"☁️ IA Nube: {bridge_config.get('proveedor', '?')} ✅")
    else:
        info.append("☁️ IA Nube: No configurada")
    return "\n".join(info)

# =====================================================================
# MAPA DE FUNCIONES - Nombre → Función Python
# =====================================================================

AVAILABLE_FUNCTIONS = {
    "ejecutar_comando": tool_ejecutar_comando,
    "clonar_repositorio": tool_clonar_repositorio,
    "instalar_dependencias": tool_instalar_dependencias,
    "listar_archivos": tool_listar_archivos,
    "leer_archivo": tool_leer_archivo,
    "escribir_archivo": tool_escribir_archivo,
    "modificar_archivo": tool_modificar_archivo,
    "buscar_en_archivos": tool_buscar_en_archivos,
    "calcular": tool_calcular,
    "buscar": tool_buscar,
    "consultar_experto": tool_consultar_experto,
    "consultar_plan": tool_consultar_plan,
    "info_sistema": tool_info_sistema,
}

# =====================================================================
# DEFINICIÓN DE HERRAMIENTAS PARA OLLAMA (JSON Schema)
# Esta es la clave: Ollama usa estos schemas para el tool calling NATIVO
# =====================================================================

OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ejecutar_comando",
            "description": "Ejecuta un comando del sistema operativo (git, npm, pip, python, dir, etc.). El comando se ejecuta directamente en la terminal y retorna la salida.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comando": {
                        "type": "string",
                        "description": "El comando a ejecutar, ej: 'git clone https://...', 'npm install', 'dir', 'python script.py'"
                    },
                    "directorio": {
                        "type": "string",
                        "description": "Directorio donde ejecutar el comando (opcional)"
                    }
                },
                "required": ["comando"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clonar_repositorio",
            "description": "Clona un repositorio de GitHub automáticamente. Descarga todo el código del proyecto a la carpeta de proyectos del usuario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL del repositorio de GitHub, ej: https://github.com/usuario/repo.git"
                    },
                    "directorio_destino": {
                        "type": "string",
                        "description": "Directorio donde clonar (opcional, por defecto va a la carpeta Projects)"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "instalar_dependencias",
            "description": "Instala las dependencias de un proyecto. Detecta automáticamente si es npm o pip.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directorio": {
                        "type": "string",
                        "description": "Ruta del directorio del proyecto"
                    },
                    "tipo": {
                        "type": "string",
                        "description": "Tipo de proyecto: 'npm' o 'pip' (opcional, se autodetecta)",
                        "enum": ["npm", "pip"]
                    }
                },
                "required": ["directorio"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_archivos",
            "description": "Lista los archivos y carpetas de un directorio mostrando la estructura del proyecto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {
                        "type": "string",
                        "description": "Ruta del directorio a listar"
                    },
                    "profundidad": {
                        "type": "integer",
                        "description": "Profundidad máxima de carpetas (por defecto 3)"
                    }
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leer_archivo",
            "description": "Lee el contenido completo de un archivo de texto o código fuente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {
                        "type": "string",
                        "description": "Ruta del archivo a leer"
                    }
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escribir_archivo",
            "description": "Escribe contenido en un archivo. Crea el archivo si no existe. Hace backup automático del archivo anterior.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {
                        "type": "string",
                        "description": "Ruta del archivo a escribir"
                    },
                    "contenido": {
                        "type": "string",
                        "description": "Contenido a escribir en el archivo"
                    }
                },
                "required": ["ruta", "contenido"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "modificar_archivo",
            "description": "Modifica una parte específica de un archivo. Busca texto_original y lo reemplaza con texto_nuevo. Más seguro que escribir todo el archivo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {
                        "type": "string",
                        "description": "Ruta del archivo a modificar"
                    },
                    "texto_original": {
                        "type": "string",
                        "description": "Texto que se va a buscar y reemplazar"
                    },
                    "texto_nuevo": {
                        "type": "string",
                        "description": "Texto nuevo que reemplazará al original"
                    }
                },
                "required": ["ruta", "texto_original", "texto_nuevo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_en_archivos",
            "description": "Busca un texto dentro de todos los archivos de un directorio (como grep).",
            "parameters": {
                "type": "object",
                "properties": {
                    "directorio": {
                        "type": "string",
                        "description": "Directorio donde buscar"
                    },
                    "texto": {
                        "type": "string",
                        "description": "Texto a buscar"
                    },
                    "extension": {
                        "type": "string",
                        "description": "Filtrar por extensión, ej: '.tsx', '.py' (opcional)"
                    }
                },
                "required": ["directorio", "texto"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calcular",
            "description": "Evalúa una expresión matemática. Solo acepta números y operadores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expresion": {
                        "type": "string",
                        "description": "Expresión matemática, ej: '2 + 3 * 4', '100 * 0.15'"
                    }
                },
                "required": ["expresion"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar",
            "description": "Busca información en internet usando DuckDuckGo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {
                        "type": "string",
                        "description": "Consulta de búsqueda"
                    }
                },
                "required": ["consulta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_experto",
            "description": "Consulta con una IA avanzada en la nube para tareas complejas, razonamiento profundo, o código difícil.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pregunta": {
                        "type": "string",
                        "description": "Pregunta o tarea para la IA experta"
                    },
                    "modo": {
                        "type": "string",
                        "description": "Modo: 'general', 'codigo', 'analisis', 'plan'",
                        "enum": ["general", "codigo", "analisis", "plan"]
                    }
                },
                "required": ["pregunta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_plan",
            "description": "Pide a la IA avanzada que cree un plan de implementación detallado paso a paso.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tarea": {
                        "type": "string",
                        "description": "Tarea para la cual crear un plan"
                    },
                    "contexto": {
                        "type": "string",
                        "description": "Contexto adicional (opcional)"
                    }
                },
                "required": ["tarea"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "info_sistema",
            "description": "Muestra información del sistema: OS, RAM, disco, CPU, proyectos.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

# =====================================================================
# AGENTE AUTÓNOMO - CON TOOL CALLING NATIVO
# =====================================================================

AGENT_SYSTEM_MSG = f"""Eres un agente de IA que ejecuta acciones reales en la computadora del usuario.
Tienes herramientas para ejecutar comandos, clonar repositorios, leer/escribir archivos, etc.
Cuando el usuario te pida algo, USA LAS HERRAMIENTAS para hacerlo directamente.
NUNCA le digas al usuario que abra una terminal o ejecute comandos manualmente. TÚ lo haces.
Responde siempre en español.
Directorios del usuario: Proyectos={PROJECTS_DIR}, Descargas={DOWNLOADS_DIR}, Documentos={DOCUMENTS_DIR}"""

def run_agent(user_message, history=[]):
    """Ejecuta el agente usando Ollama tool calling NATIVO"""
    
    # Construir mensajes
    messages = [{"role": "system", "content": AGENT_SYSTEM_MSG}]
    # Agregar historial (últimos 10 mensajes)
    for msg in history[-10:]:
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})
    
    # === LLAMADA A OLLAMA CON TOOLS NATIVO ===
    try:
        response = ollama.chat(
            model=AGENT_MODEL,
            messages=messages,
            tools=OLLAMA_TOOLS,
        )
    except Exception as e:
        return f"❌ Error conectando con Ollama: {str(e)}", []
    
    results = []
    tool_results_container = st.container()
    max_iterations = 5  # Máximo de iteraciones de tool calling
    
    for iteration in range(max_iterations):
        # Verificar si el modelo quiere llamar herramientas
        if not response.message.tool_calls:
            # El modelo respondió con texto, no con herramientas
            break
        
        # === EJECUTAR CADA HERRAMIENTA ===
        # Agregar mensaje del asistente (con tool_calls) al historial
        messages.append(response.message)
        
        for tool_call in response.message.tool_calls:
            fn_name = tool_call.function.name
            fn_args = tool_call.function.arguments
            
            with tool_results_container:
                is_bridge = fn_name.startswith("consultar")
                css_class = "bridge-box" if is_bridge else "tool-cmd"
                icon = "☁️" if is_bridge else "🔧"
                args_preview = ", ".join(f"{k}={str(v)[:40]}" for k, v in fn_args.items())
                st.markdown(f'<div class="{css_class}">{icon} Paso {len(results)+1}: {fn_name}({args_preview})</div>', unsafe_allow_html=True)
                
                # Ejecutar la función
                fn = AVAILABLE_FUNCTIONS.get(fn_name)
                if fn:
                    try:
                        result = fn(**fn_args)
                    except Exception as e:
                        result = f"❌ Error ejecutando {fn_name}: {str(e)}"
                else:
                    result = f"❌ Función no encontrada: {fn_name}"
                
                results.append({"tool": fn_name, "args": fn_args, "result": result})
                
                # Mostrar resultado
                result_preview = str(result)[:800]
                st.markdown(f'<div class="tool-result">{result_preview}</div>', unsafe_allow_html=True)
            
            # Agregar resultado de la herramienta al historial de mensajes
            messages.append({
                "role": "tool",
                "content": str(result),
            })
        
        # === PEDIR SIGUIENTE RESPUESTA ===
        try:
            response = ollama.chat(
                model=AGENT_MODEL,
                messages=messages,
                tools=OLLAMA_TOOLS,
            )
        except Exception as e:
            break
    
    # === RESPUESTA FINAL ===
    final_text = ""
    if response.message.content:
        final_text = response.message.content
    elif results:
        # Si no hay texto final pero sí resultados, generar resumen
        results_summary = "Resultados:\n\n"
        for r in results:
            results_summary += f"- {r['tool']}: {str(r['result'])[:300]}\n"
        
        summary_messages = messages.copy()
        summary_messages.append({
            "role": "user",
            "content": "Basándote en los resultados de las herramientas, da una respuesta final clara y útil en español. Explica lo que hiciste y los resultados."
        })
        try:
            summary_response = ollama.chat(model=AGENT_MODEL, messages=summary_messages)
            final_text = summary_response.message.content
        except:
            final_text = results_summary
    else:
        final_text = "No se pudo completar la tarea. Intenta de nuevo."
    
    new_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": final_text}
    ]
    
    return final_text, new_history

# =====================================================================
# CHAT SIMPLE
# =====================================================================

def chat_simple(message, history=[]):
    messages = [{"role": "system", "content": "Eres un asistente útil. Respondes en español."}]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": message})
    try:
        response = ollama.chat(model=CHAT_MODEL, messages=messages, stream=False)
        return response["message"]["content"]
    except Exception as e:
        return f"❌ Error: {str(e)}"

# =====================================================================
# RAG - DOCUMENTOS
# =====================================================================

def init_chroma():
    try:
        import chromadb
        client = chromadb.PersistentClient(path=os.path.join(USER_HOME, ".ia-chromadb"))
        collection = client.get_or_create_collection("documentos")
        return client, collection
    except Exception as e:
        st.error(f"Error ChromaDB: {e}")
        return None, None

def add_document_to_chroma(text, source, collection):
    try:
        chunk_size = 500
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        for i, chunk in enumerate(chunks):
            embedding_response = ollama.embeddings(model="nomic-embed-text", prompt=chunk)
            collection.add(ids=[f"{source}_{i}"], embeddings=[embedding_response["embedding"]],
                documents=[chunk], metadatas=[{"source": source, "chunk": i}])
        return len(chunks)
    except Exception as e:
        st.error(f"Error: {e}")
        return 0

def rag_query(question, collection):
    try:
        query_embedding = ollama.embeddings(model="nomic-embed-text", prompt=question)["embedding"]
        results = collection.query(query_embeddings=[query_embedding], n_results=5)
        if not results["documents"][0]:
            return "No encontré documentos relevantes."
        context = "\n\n".join(results["documents"][0])
        messages = [{"role": "system", "content": f"Contexto:\n\n{context}\n\nResponde en español."},
            {"role": "user", "content": question}]
        response = ollama.chat(model=CHAT_MODEL, messages=messages, stream=False)
        return response["message"]["content"]
    except Exception as e:
        return f"❌ Error: {str(e)}"

# =====================================================================
# ASISTENTE DE CÓDIGO
# =====================================================================

def code_assistant(message, mode="explicar"):
    prompts = {"explicar": "Explica el código:", "mejorar": "Mejora el código:", "corregir": "Corrige el código:", "crear": "Crea el código:"}
    bridge_config = load_bridge_config()
    if bridge_config.get("api_key"):
        return consultar_experto(message, modo="codigo")
    messages = [{"role": "system", "content": "Eres un programador experto. Explicaciones en español, código en inglés."},
        {"role": "user", "content": f"{prompts.get(mode, 'Explica:')}\n\n{message}"}]
    try:
        response = ollama.chat(model=CODE_MODEL, messages=messages, stream=False)
        return response["message"]["content"]
    except Exception as e:
        return f"❌ Error: {str(e)}"

# =====================================================================
# INTERFAZ - IA BRIDGE SETTINGS
# =====================================================================

def render_bridge_settings():
    st.subheader("☁️ IA Bridge")
    config = load_bridge_config()
    proveedor_nombres = {k: v["nombre"] for k, v in PROVEEDORES.items()}
    selected = st.selectbox("Proveedor", options=list(proveedor_nombres.keys()),
        format_func=lambda x: proveedor_nombres[x],
        index=list(proveedor_nombres.keys()).index(config.get("proveedor", "groq")))
    config["proveedor"] = selected
    prov = PROVEEDORES[selected]
    if prov["gratis"]:
        st.success("🆓 Gratuito")
    else:
        st.info("💰 De pago")
    st.caption(prov["descripcion"])
    api_key = st.text_input("API Key", value=config.get("api_key", ""), type="password",
        help=f"Obtén tu key en: {prov['como_obtener_key']}")
    config["api_key"] = api_key
    st.markdown(f"🔑 [Obtener API Key]({prov['como_obtener_key']})")
    modelos = prov["modelos"]
    modelo_default = config.get("modelo") or prov["modelo_default"]
    modelo_index = modelos.index(modelo_default) if modelo_default in modelos else 0
    modelo = st.selectbox("Modelo", options=modelos, index=modelo_index)
    config["modelo"] = modelo
    with st.expander("📝 Contexto del Proyecto"):
        contexto = st.text_area("Describe tu proyecto", value=config.get("contexto_proyecto", ""), height=100,
            placeholder="Ej: SignalTrader Pro - Motor de trading con Next.js...")
        config["contexto_proyecto"] = contexto
    if st.button("💾 Guardar Configuración"):
        save_bridge_config(config)
        st.success("✅ Guardado")
    if st.button("🔌 Probar Conexión"):
        if not api_key:
            st.error("❌ Ingresa API Key")
        else:
            with st.spinner("Probando..."):
                success, msg = test_bridge_connection()
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
    st.divider()
    if config.get("api_key"):
        st.success(f"☁️ {prov['nombre']} ✅")
    else:
        st.warning("☁️ Sin configurar")

# =====================================================================
# INTERFAZ PRINCIPAL
# =====================================================================

def main():
    with st.sidebar:
        st.title("🤖 IA Local Pro v3")
        st.caption("Con Tool Calling Nativo")
        
        mode = st.radio("Modo", ["🚀 Agente Autónomo", "💬 Chat Simple", "📚 RAG Documentos", "💻 Código"], index=0)
        
        st.divider()
        st.subheader("⚙️ Modelos Locales")
        agente_model = st.selectbox("Agente", ["qwen2.5:14b", "qwen2.5:7b", "llama3.1:8b"], index=0)
        global AGENT_MODEL
        AGENT_MODEL = agente_model
        
        st.divider()
        render_bridge_settings()
        
        st.divider()
        st.subheader("📁 Proyectos")
        if os.path.exists(PROJECTS_DIR):
            proyectos = [d for d in os.listdir(PROJECTS_DIR) if os.path.isdir(os.path.join(PROJECTS_DIR, d))]
            if proyectos:
                selected_project = st.selectbox("Proyecto activo", proyectos)
                st.session_state['active_project'] = os.path.join(PROJECTS_DIR, selected_project)
            else:
                st.info("Clona un repositorio")
        
        st.divider()
        if st.button("📊 Info Sistema"):
            st.text(tool_info_sistema())
        if st.button("🗑️ Limpiar Historial"):
            st.session_state['history'] = []
            st.rerun()
    
    if "🚀" in mode:
        render_autonomous_agent()
    elif "💬" in mode:
        render_simple_chat()
    elif "📚" in mode:
        render_rag()
    elif "💻" in mode:
        render_code_assistant()

def render_autonomous_agent():
    st.title("🚀 Agente Autónomo Pro v3")
    st.caption("Usa Tool Calling Nativo de Ollama — El agente EJECUTA, no da instrucciones")
    
    bridge_config = load_bridge_config()
    if bridge_config.get("api_key"):
        prov = PROVEEDORES.get(bridge_config.get("proveedor", "groq"), {})
        st.success(f"☁️ IA Avanzada: {prov.get('nombre', '?')}")
    else:
        st.caption("💡 Configura ☁️ IA Bridge para consultas avanzadas")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📥 Clonar signalTrade"):
            st.session_state['quick_task'] = "Clona el repositorio https://github.com/yecos/signalTrade.git en mi carpeta de proyectos"
    with col2:
        if st.button("📦 Instalar Deps"):
            project = st.session_state.get('active_project', '')
            if project and os.path.exists(project):
                st.session_state['quick_task'] = f"Instala las dependencias del proyecto en {project}"
    with col3:
        if st.button("🔍 Analizar Proyecto"):
            project = st.session_state.get('active_project', '')
            if project and os.path.exists(project):
                st.session_state['quick_task'] = f"Analiza el proyecto en {project}. Lista los archivos, lee el package.json y README, y dame un resumen completo."
    
    if 'history' not in st.session_state:
        st.session_state['history'] = []
    
    for msg in st.session_state['history']:
        if msg["role"] == "user":
            st.chat_message("user").write(msg["content"])
        elif msg["role"] == "assistant":
            st.chat_message("assistant").write(msg["content"])
    
    quick_task = st.session_state.pop('quick_task', None)
    prompt = st.chat_input("¿Qué quieres que haga?")
    user_input = quick_task or prompt
    
    if user_input:
        st.chat_message("user").write(user_input)
        with st.chat_message("assistant"):
            with st.spinner("🤖 Agente ejecutando..."):
                response, new_history = run_agent(user_input, st.session_state['history'])
                st.session_state['history'] = new_history
                st.markdown(response)

def render_simple_chat():
    st.title("💬 Chat Simple")
    if 'chat_history' not in st.session_state:
        st.session_state['chat_history'] = []
    for msg in st.session_state['chat_history']:
        st.chat_message(msg["role"]).write(msg["content"])
    prompt = st.chat_input("Escribe tu mensaje...")
    if prompt:
        st.chat_message("user").write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                response = chat_simple(prompt, st.session_state['chat_history'])
                st.markdown(response)
        st.session_state['chat_history'].append({"role": "user", "content": prompt})
        st.session_state['chat_history'].append({"role": "assistant", "content": response})

def render_rag():
    st.title("📚 RAG - Documentos")
    client, collection = init_chroma()
    if collection:
        uploaded = st.file_uploader("Subir documento", type=["pdf", "txt", "md"])
        if uploaded:
            with st.spinner("Procesando..."):
                text = ""
                if uploaded.name.endswith(".pdf"):
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(uploaded)
                        for page in reader.pages:
                            text += page.extract_text() or ""
                    except:
                        st.error("pip install pypdf")
                else:
                    text = uploaded.getvalue().decode("utf-8", errors="replace")
                if text:
                    chunks = add_document_to_chroma(text, uploaded.name, collection)
                    st.success(f"✅ {uploaded.name} ({chunks} fragmentos)")
        if 'rag_history' not in st.session_state:
            st.session_state['rag_history'] = []
        for msg in st.session_state['rag_history']:
            st.chat_message(msg["role"]).write(msg["content"])
        prompt = st.chat_input("Pregunta sobre tus documentos...")
        if prompt:
            st.chat_message("user").write(prompt)
            with st.chat_message("assistant"):
                response = rag_query(prompt, collection)
                st.markdown(response)
            st.session_state['rag_history'].append({"role": "user", "content": prompt})
            st.session_state['rag_history'].append({"role": "assistant", "content": response})

def render_code_assistant():
    st.title("💻 Asistente de Código")
    bridge_config = load_bridge_config()
    if bridge_config.get("api_key"):
        st.success("☁️ Usando IA avanzada")
    else:
        st.caption(f"Modelo local {CODE_MODEL}")
    mode = st.selectbox("Modo", ["explicar", "mejorar", "corregir", "crear"])
    if 'code_history' not in st.session_state:
        st.session_state['code_history'] = []
    for msg in st.session_state['code_history']:
        st.chat_message(msg["role"]).write(msg["content"])
    prompt = st.chat_input("Pega código o describe qué crear...")
    if prompt:
        st.chat_message("user").write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Generando código..."):
                response = code_assistant(prompt, mode)
                st.markdown(response)
        st.session_state['code_history'].append({"role": "user", "content": prompt})
        st.session_state['code_history'].append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()
