"""
=============================================================================
  AGENTE AUTÓNOMO PRO - IA Local + IA en la Nube
  Versión con Bridge a IA avanzada, ejecución de comandos y más
=============================================================================
  Funcionalidades:
  - Agente autónomo con Plan → Ejecutar → Replanear → Responder
  - Ejecución de comandos del sistema (git, npm, pip, python, etc.)
  - Clonar repositorios de GitHub
  - Instalar dependencias (npm, pip)
  - Leer, escribir y modificar archivos
  - Buscar en la web
  - 🆕 Consultar con IA avanzada en la nube (Groq, OpenRouter, etc.)
  - 🆕 Modo híbrido: local para lo rápido, nube para lo complejo
  - RAG con documentos
  - Asistente de código
  
  Modelos:
  - Local (Ollama): qwen2.5:14b (agente), llama3.1:8b (chat), qwen2.5-coder:7b (código)
  - Nube: Groq (gratis), OpenRouter, OpenAI, DeepSeek
  
  Requisitos:
  pip install streamlit ollama chromadb pypdf ddgs psutil
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
OLLAMA_URL = "http://localhost:11434"

# Detectar sistema operativo
IS_WINDOWS = platform.system() == "Windows"

# Directorios del usuario
USER_HOME = os.path.expanduser("~")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
DOCUMENTS_DIR = os.path.join(USER_HOME, "Documents")
DESKTOP_DIR = os.path.join(USER_HOME, "Desktop")

# Directorio de proyectos
PROJECTS_DIR = os.path.join(USER_HOME, "Projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

# Directorio de backups
BACKUP_DIR = os.path.join(USER_HOME, ".ia-backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

# Directorio de configuración del bridge
CONFIG_DIR = os.path.join(USER_HOME, ".ia-local")
os.makedirs(CONFIG_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIR, "bridge_config.json")

# Comandos peligrosos que requieren confirmación
DANGEROUS_COMMANDS = [
    "rm ", "del ", "rmdir", "format", "mkfs", "dd ", 
    "shutdown", "restart", "reboot",
    "reg ", "registry", "net user", "net localgroup",
    "taskkill", "kill ", "pkill",
    "format ", "fdisk", "diskpart",
    "cipher", "icacls",
    "wget", "curl -X DELETE",
    "docker rm", "docker rmi", "docker system prune",
    "> ", "2>nul", "out-null",
    "Remove-Item", "rm -rf", "rm -r",
]

# Comandos BLOQUEADOS (nunca se ejecutan)
BLOCKED_COMMANDS = [
    "format c:", "format d:", "del /f /s /q c:", "del /f /s /q d:",
    "rm -rf /", "rm -rf /*", "rd /s /q c:", "rd /s /q d:",
    "shutdown /s", "shutdown /r",
]

# Timeout por defecto para comandos (segundos)
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

# =====================================================================
# ESTILOS CSS
# =====================================================================

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
    .tool-warning {
        background: #1e1e2e;
        border: 1px solid #f38ba8;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        color: #f38ba8;
    }
    .tool-success {
        background: #1e1e2e;
        border: 1px solid #a6e3a1;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        color: #a6e3a1;
    }
    .plan-box {
        background: linear-gradient(135deg, #1e1e2e, #313244);
        border: 1px solid #cba6f7;
        border-radius: 10px;
        padding: 16px;
        margin: 12px 0;
        color: #cba6f7;
    }
    .bridge-box {
        background: linear-gradient(135deg, #1e1e2e, #1e3a5f);
        border: 1px solid #89b4fa;
        border-radius: 10px;
        padding: 16px;
        margin: 12px 0;
        color: #89b4fa;
    }
    .confirm-box {
        background: #1e1e2e;
        border: 2px solid #f9e2af;
        border-radius: 10px;
        padding: 16px;
        margin: 12px 0;
        color: #f9e2af;
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
        "modelos": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it"
        ],
        "modelo_default": "llama-3.3-70b-versatile",
        "como_obtener_key": "https://console.groq.com/keys",
        "gratis": True,
        "descripcion": "Gratis, muy rápido, buenos modelos. Ideal para empezar."
    },
    "openrouter": {
        "nombre": "OpenRouter (Múltiples modelos)",
        "url_base": "https://openrouter.ai/api/v1",
        "modelos": [
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
            "deepseek/deepseek-chat:free",
            "qwen/qwen-2.5-72b-instruct:free",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o"
        ],
        "modelo_default": "meta-llama/llama-3.3-70b-instruct:free",
        "como_obtener_key": "https://openrouter.ai/keys",
        "gratis": True,
        "descripcion": "Acceso a muchos modelos. Tiene opciones gratuitas y de pago."
    },
    "openai": {
        "nombre": "OpenAI (GPT-4)",
        "url_base": "https://api.openai.com/v1",
        "modelos": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo"
        ],
        "modelo_default": "gpt-4o-mini",
        "como_obtener_key": "https://platform.openai.com/api-keys",
        "gratis": False,
        "descripcion": "La IA más conocida. De pago pero muy capaz."
    },
    "deepseek": {
        "nombre": "DeepSeek (Barato y muy bueno)",
        "url_base": "https://api.deepseek.com/v1",
        "modelos": [
            "deepseek-chat",
            "deepseek-reasoner"
        ],
        "modelo_default": "deepseek-chat",
        "como_obtener_key": "https://platform.deepseek.com/api_keys",
        "gratis": False,
        "descripcion": "Muy buen razonamiento a bajo precio. Excelente para código."
    }
}

def load_bridge_config():
    """Carga la configuración del bridge"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "proveedor": "groq",
        "api_key": "",
        "modelo": "",
        "auto_consultar": True,
        "contexto_proyecto": "",
        "historial_consultas": []
    }

def save_bridge_config(config):
    """Guarda la configuración del bridge"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def call_cloud_api(url_base, api_key, model, messages, temperature=0.7, max_tokens=2048):
    """Llama a una API compatible con OpenAI usando solo urllib"""
    endpoint = f"{url_base}/chat/completions"
    
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }).encode('utf-8')
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    if "openrouter" in url_base:
        headers["HTTP-Referer"] = "https://ia-local.app"
        headers["X-Title"] = "IA Local Pro"
    
    req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            return {
                "success": True,
                "content": result["choices"][0]["message"]["content"],
                "model": result.get("model", model),
                "usage": result.get("usage", {})
            }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("error", {}).get("message", error_body[:200])
        except:
            error_msg = error_body[:200]
        return {"success": False, "error": f"HTTP {e.code}: {error_msg}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Error de conexión: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Error: {str(e)}"}

def consultar_experto(pregunta, contexto="", modo="general"):
    """Consulta con una IA avanzada en la nube"""
    config = load_bridge_config()
    
    if not config.get("api_key"):
        return "❌ No hay API key configurada. Ve a ⚙️ Configuración → IA Bridge en el sidebar."
    
    proveedor = config.get("proveedor", "groq")
    prov_config = PROVEEDORES.get(proveedor, PROVEEDORES["groq"])
    modelo = config.get("modelo") or prov_config["modelo_default"]
    
    system_prompts = {
        "general": "Eres un experto consultor de IA. Respondes en español de forma clara y detallada. Cuando te pidan ayuda con código, proporciona soluciones completas y funcionales.",
        "codigo": "Eres un programador experto senior. Proporcionas código limpio, bien estructurado y funcional. Respondes en español pero el código en inglés (convenciones). Incluye comentarios explicativos.",
        "analisis": "Eres un analista de software experto. Analizas código, arquitectura y sistemas de forma profunda. Identificas problemas, sugieres mejoras. Respondes en español.",
        "plan": "Eres un arquitecto de software experto. Creas planes de implementación detallados paso a paso. Respondes en español."
    }
    
    messages = [
        {"role": "system", "content": system_prompts.get(modo, system_prompts["general"])}
    ]
    
    contexto_proyecto = config.get("contexto_proyecto", "")
    if contexto_proyecto:
        messages.append({"role": "system", "content": f"Contexto del proyecto del usuario:\n{contexto_proyecto}"})
    
    if contexto:
        user_content = f"Contexto:\n{contexto}\n\nPregunta: {pregunta}"
    else:
        user_content = pregunta
    
    messages.append({"role": "user", "content": user_content})
    
    result = call_cloud_api(
        url_base=prov_config["url_base"],
        api_key=config["api_key"],
        model=modelo,
        messages=messages,
        temperature=0.7 if modo != "plan" else 0.5,
        max_tokens=4096 if modo == "codigo" else 2048
    )
    
    # Registrar consulta
    consulta_record = {
        "fecha": datetime.datetime.now().isoformat(),
        "pregunta": pregunta[:100],
        "modo": modo,
        "exito": result.get("success", False),
        "modelo": modelo,
        "proveedor": proveedor
    }
    config.setdefault("historial_consultas", []).append(consulta_record)
    config["historial_consultas"] = config["historial_consultas"][-100:]
    save_bridge_config(config)
    
    if result["success"]:
        return result["content"]
    else:
        return f"❌ Error consultando IA: {result['error']}"

def test_bridge_connection():
    """Prueba la conexión con el proveedor de IA en la nube"""
    config = load_bridge_config()
    
    if not config.get("api_key"):
        return False, "No hay API key configurada"
    
    proveedor = config.get("proveedor", "groq")
    prov_config = PROVEEDORES.get(proveedor, PROVEEDORES["groq"])
    modelo = config.get("modelo") or prov_config["modelo_default"]
    
    result = call_cloud_api(
        url_base=prov_config["url_base"],
        api_key=config["api_key"],
        model=modelo,
        messages=[{"role": "user", "content": "Responde solo: CONEXION_OK"}],
        temperature=0,
        max_tokens=10
    )
    
    if result["success"]:
        return True, f"✅ Conexión exitosa con {prov_config['nombre']} (modelo: {modelo})"
    else:
        return False, f"❌ Error: {result['error']}"

# =====================================================================
# FUNCIONES AUXILIARES
# =====================================================================

def create_backup(filepath):
    """Crea backup de un archivo antes de modificarlo"""
    try:
        if os.path.exists(filepath):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            basename = os.path.basename(filepath)
            backup_name = f"{basename}.{timestamp}.bak"
            backup_path = os.path.join(BACKUP_DIR, backup_name)
            shutil.copy2(filepath, backup_path)
            return backup_path
    except Exception as e:
        return f"Error creando backup: {str(e)}"
    return None

def is_dangerous_command(cmd):
    """Verifica si un comando es potencialmente peligroso"""
    cmd_lower = cmd.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return "blocked"
    for dangerous in DANGEROUS_COMMANDS:
        if dangerous.lower() in cmd_lower:
            return "dangerous"
    return "safe"

def run_command(command, cwd=None, timeout=DEFAULT_COMMAND_TIMEOUT):
    """Ejecuta un comando del sistema de forma segura"""
    try:
        danger_level = is_dangerous_command(command)
        if danger_level == "blocked":
            return "⛔ COMANDO BLOQUEADO por seguridad.", -1
        if danger_level == "dangerous":
            return "⚠️ Comando peligroso. Requiere confirmación.", -2
        
        shell = IS_WINDOWS
        result = subprocess.run(
            command, shell=shell, capture_output=True, text=True,
            timeout=timeout, cwd=cwd, encoding='utf-8', errors='replace'
        )
        
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
        return f"❌ Comando no encontrado.", -4
    except Exception as e:
        return f"❌ Error: {str(e)}", -5

def force_run_command(command, cwd=None, timeout=DEFAULT_COMMAND_TIMEOUT):
    """Ejecuta un comando incluso si es peligroso"""
    try:
        shell = IS_WINDOWS
        result = subprocess.run(
            command, shell=shell, capture_output=True, text=True,
            timeout=timeout, cwd=cwd, encoding='utf-8', errors='replace'
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[STDERR]: {result.stderr}"
        if not output.strip():
            output = "(Comando ejecutado sin salida visible)"
        return output.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return f"⏱️ Tiempo agotado ({timeout}s)", -3
    except Exception as e:
        return f"❌ Error: {str(e)}", -5

# =====================================================================
# DEFINICIÓN DE HERRAMIENTAS
# =====================================================================

TOOLS = {
    "ejecutar_comando": {
        "description": "Ejecuta un comando del sistema (git, npm, pip, python, etc.)",
        "params": ["comando", "directorio?"],
        "example": 'ejecutar_comando("git status", "C:\\Projects\\signalTrade")'
    },
    "clonar_repositorio": {
        "description": "Clona un repositorio de GitHub",
        "params": ["url_repositorio", "directorio_destino?"],
        "example": 'clonar_repositorio("https://github.com/yecos/signalTrade.git")'
    },
    "instalar_dependencias": {
        "description": "Instala dependencias de un proyecto (npm/pip)",
        "params": ["directorio_proyecto", "tipo?"],
        "example": 'instalar_dependencias("C:\\Projects\\signalTrade", "npm")'
    },
    "listar_archivos": {
        "description": "Lista archivos y carpetas de un directorio",
        "params": ["ruta", "profundidad?"],
        "example": 'listar_archivos("C:\\Projects\\signalTrade", 2)'
    },
    "leer_archivo": {
        "description": "Lee el contenido completo de un archivo",
        "params": ["ruta_archivo"],
        "example": 'leer_archivo("C:\\Projects\\signalTrade\\package.json")'
    },
    "escribir_archivo": {
        "description": "Escribe contenido en un archivo (con backup automático)",
        "params": ["ruta_archivo", "contenido"],
        "example": 'escribir_archivo("test.js", "console.log(\'hello\')")'
    },
    "modificar_archivo": {
        "description": "Modifica parte de un archivo. Busca texto_original y lo reemplaza con texto_nuevo",
        "params": ["ruta_archivo", "texto_original", "texto_nuevo"],
        "example": 'modificar_archivo("app.js", "version: 1.0", "version: 2.0")'
    },
    "buscar_en_archivos": {
        "description": "Busca texto dentro de archivos de un directorio",
        "params": ["directorio", "texto_buscar", "extension?"],
        "example": 'buscar_en_archivos("C:\\Projects\\signalTrade", "useEffect", ".tsx")'
    },
    "calcular": {
        "description": "Evalúa una expresión matemática",
        "params": ["expresion"],
        "example": 'calcular("2 + 3 * 4")'
    },
    "buscar": {
        "description": "Busca información en internet (DuckDuckGo)",
        "params": ["consulta"],
        "example": 'buscar("Next.js 14 app router tutorial")'
    },
    "consultar_experto": {
        "description": "🔍 Consulta con una IA avanzada en la nube para tareas complejas, código difícil, o cuando el modelo local no es suficiente. La IA experta es mucho más inteligente y puede ayudar con razonamiento profundo.",
        "params": ["pregunta", "modo?"],
        "example": 'consultar_experto("¿Cómo implementar WebSocket server en Next.js?", "codigo")'
    },
    "consultar_con_codigo": {
        "description": "🔍 Envía código a la IA avanzada para analizar, mejorar, corregir o extender",
        "params": ["pregunta", "codigo", "lenguaje?"],
        "example": 'consultar_con_codigo("Agrega manejo de errores", "function trade() { ... }", "typescript")'
    },
    "consultar_plan": {
        "description": "🔍 Pide a la IA avanzada que cree un plan de implementación detallado",
        "params": ["tarea", "contexto?"],
        "example": 'consultar_plan("Agregar sistema de alertas al motor de trading")'
    },
    "info_sistema": {
        "description": "Muestra información del sistema",
        "params": [],
        "example": 'info_sistema()'
    }
}

# =====================================================================
# IMPLEMENTACIÓN DE HERRAMIENTAS
# =====================================================================

def tool_ejecutar_comando(comando, directorio=None):
    cwd = directorio if directorio and os.path.isdir(directorio) else None
    if cwd:
        result, code = run_command(comando, cwd=cwd)
    else:
        result, code = run_command(comando)
    if code == -2:
        return result + "\n\nSi estás seguro, usa ejecutar_comando_forzado."
    return result

def tool_ejecutar_comando_forzado(comando, directorio=None):
    cwd = directorio if directorio and os.path.isdir(directorio) else None
    result, code = force_run_command(comando, cwd=cwd)
    return result

def tool_clonar_repositorio(url, directorio_destino=None):
    if not url.startswith("https://github.com/") and not url.startswith("git@github.com:"):
        return "❌ URL inválida. Debe ser una URL de GitHub."
    if not directorio_destino:
        repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
        directorio_destino = os.path.join(PROJECTS_DIR, repo_name)
    if os.path.exists(directorio_destino):
        return f"⚠️ El directorio ya existe: {directorio_destino}\nUsa ejecutar_comando('git pull', '{directorio_destino}') para actualizar."
    result, code = run_command(f'git clone {url} "{directorio_destino}"')
    if code == 0:
        return f"✅ Repositorio clonado en: {directorio_destino}\n\nContenido:\n" + tool_listar_archivos(directorio_destino, 2)
    else:
        return f"❌ Error clonando repositorio:\n{result}"

def tool_instalar_dependencias(directorio, tipo=None):
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
            return "❌ No se pudo detectar el tipo de proyecto. Especifica: npm, pip"
    if tipo == "npm":
        result, code = run_command("npm install", cwd=directorio, timeout=300)
        if code == 0:
            return f"✅ Dependencias npm instaladas en: {directorio}\n\n{result[:500]}"
        else:
            return f"❌ Error instalando npm:\n{result}"
    elif tipo == "pip":
        req_file = os.path.join(directorio, "requirements.txt")
        if os.path.exists(req_file):
            result, code = run_command(f'pip install -r "{req_file}"', cwd=directorio, timeout=300)
            if code == 0:
                return f"✅ Dependencias pip instaladas\n\n{result[:500]}"
            else:
                return f"❌ Error instalando pip:\n{result}"
        else:
            return "❌ No se encontró requirements.txt"
    else:
        return f"❌ Tipo no soportado: {tipo}"

def tool_listar_archivos(ruta, profundidad=3):
    if not os.path.exists(ruta):
        return f"❌ Ruta no encontrada: {ruta}"
    if os.path.isfile(ruta):
        size = os.path.getsize(ruta)
        return f"📄 Archivo: {ruta} ({size} bytes)"
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

def tool_leer_archivo(ruta):
    if not os.path.exists(ruta):
        return f"❌ Archivo no encontrado: {ruta}"
    try:
        with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
            contenido = f.read()
        if len(contenido) > 15000:
            contenido = contenido[:15000] + f"\n\n... [Archivo truncado - {len(contenido)} caracteres total]"
        return contenido
    except Exception as e:
        return f"❌ Error leyendo archivo: {str(e)}"

def tool_escribir_archivo(ruta, contenido):
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
        return f"❌ Error escribiendo archivo: {str(e)}"

def tool_modificar_archivo(ruta, texto_original, texto_nuevo):
    if not os.path.exists(ruta):
        return f"❌ Archivo no encontrado: {ruta}"
    try:
        with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
            contenido = f.read()
        if texto_original not in contenido:
            return f"❌ Texto original no encontrado.\nSugerencia: Usa leer_archivo('{ruta}') para ver el contenido."
        ocurrencias = contenido.count(texto_original)
        if ocurrencias > 1:
            return f"⚠️ El texto aparece {ocurrencias} veces. Se reemplazarán TODAS."
        backup_path = create_backup(ruta)
        backup_msg = f"\n📦 Backup: {backup_path}" if backup_path else ""
        nuevo_contenido = contenido.replace(texto_original, texto_nuevo)
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(nuevo_contenido)
        return f"✅ Archivo modificado: {ruta}{backup_msg}\nEliminado: {texto_original[:150]}...\nAgregado: {texto_nuevo[:150]}..."
    except Exception as e:
        return f"❌ Error modificando archivo: {str(e)}"

def tool_buscar_en_archivos(directorio, texto, extension=None):
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
                            line_clean = line.strip()[:120]
                            resultados.append(f"{rel_path}:{i} → {line_clean}")
                            if len(resultados) >= 50:
                                return "\n".join(resultados) + "\n\n... [Limitado a 50 resultados]"
            except:
                continue
    if not resultados:
        return f"🔍 No se encontró '{texto}' en {directorio}"
    return "\n".join(resultados)

def tool_calcular(expresion):
    expresion = expresion.replace("^", "**")
    permitido = re.match(r'^[\d\s\+\-\*\/\.\(\)eE]+$', expresion)
    if not permitido:
        return "❌ Solo se permiten números y operadores (+, -, *, /, (), **)"
    try:
        resultado = eval(expresion, {"__builtins__": {}}, {})
        return str(resultado)
    except Exception as e:
        return f"❌ Error en cálculo: {str(e)}"

def tool_buscar(consulta):
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(consulta, max_results=5))
        if not results:
            return "🔍 No se encontraron resultados"
        salida = []
        for r in results:
            salida.append(f"📌 {r.get('title', 'Sin título')}\n   {r.get('body', '')}\n   🔗 {r.get('href', '')}")
        return "\n\n".join(salida)
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(consulta, max_results=5))
            if not results:
                return "🔍 No se encontraron resultados"
            salida = []
            for r in results:
                salida.append(f"📌 {r.get('title', 'Sin título')}\n   {r.get('body', '')}\n   🔗 {r.get('href', '')}")
            return "\n\n".join(salida)
        except ImportError:
            return "❌ Instala: pip install ddgs"
    except Exception as e:
        return f"❌ Error buscando: {str(e)}"

def tool_consultar_experto(pregunta, modo="general"):
    """Herramienta del agente: consulta con IA avanzada en la nube"""
    return consultar_experto(pregunta, modo=modo)

def tool_consultar_con_codigo(pregunta, codigo, lenguaje="typescript"):
    """Herramienta del agente: envía código a la IA avanzada"""
    return consultar_experto(pregunta, contexto=f"```{lenguaje}\n{codigo}\n```", modo="codigo")

def tool_consultar_plan(tarea, contexto=""):
    """Herramienta del agente: pide un plan a la IA avanzada"""
    return consultar_experto(tarea, contexto=contexto, modo="plan")

def tool_info_sistema():
    info = []
    info.append(f"🖥️ Sistema: {platform.system()} {platform.release()}")
    info.append(f"💻 Procesador: {platform.processor()}")
    info.append(f"🏠 Usuario: {USER_HOME}")
    info.append(f"📂 Descargas: {DOWNLOADS_DIR}")
    info.append(f"📂 Proyectos: {PROJECTS_DIR}")
    try:
        if IS_WINDOWS:
            for drive in ['C:', 'D:']:
                if os.path.exists(drive + '\\'):
                    usage = shutil.disk_usage(drive + '\\')
                    info.append(f"💾 Disco {drive}: {usage.free // (1024**3)}GB libres de {usage.total // (1024**3)}GB")
        else:
            usage = shutil.disk_usage('/')
            info.append(f"💾 Disco: {usage.free // (1024**3)}GB libres de {usage.total // (1024**3)}GB")
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
        info.append(f"☁️ IA Nube: {bridge_config.get('proveedor', 'No configurado')} ✅")
    else:
        info.append("☁️ IA Nube: No configurada")
    return "\n".join(info)

# Mapa de funciones
TOOL_FUNCTIONS = {
    "ejecutar_comando": tool_ejecutar_comando,
    "ejecutar_comando_forzado": tool_ejecutar_comando_forzado,
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
    "consultar_con_codigo": tool_consultar_con_codigo,
    "consultar_plan": tool_consultar_plan,
    "info_sistema": tool_info_sistema,
}

# =====================================================================
# PROMPT DEL AGENTE AUTÓNOMO
# =====================================================================

AGENT_SYSTEM_PROMPT = """Eres un agente de IA que EJECUTA acciones reales en la computadora del usuario.
NO eres un asistente que da instrucciones. Eres un OPERADOR que HACE las cosas.

## ⚠️ REGLA #1 - LA MÁS IMPORTANTE:
NUNCA le digas al usuario que abra una terminal, que ejecute un comando, o que haga algo manualmente.
TÚ ERES QUIEN EJECUTA. TÚ tienes las herramientas. ÚSALAS.

❌ MAL: "Abre una terminal y ejecuta git clone https://..."
❌ MAL: "Puedes usar el comando npm install para instalar dependencias"
❌ MAL: "Te sugiero que abras PowerShell y corras..."
❌ MAL: "Ejecuta el siguiente comando: git clone ..."
❌ MAL: "Para clonar el repositorio, sigue estos pasos:"

✅ BIEN: clonar_repositorio("https://github.com/user/repo.git")
✅ BIEN: ejecutar_comando("npm install", "C:\\Projects\\mi-app")
✅ BIEN: instalar_dependencias("C:\\Projects\\mi-app", "npm")
✅ BIEN: leer_archivo("C:\\Projects\\mi-app\\package.json")

## HERRAMIENTAS QUE TIENES (ÚSALAS DIRECTAMENTE):

1. clonar_repositorio(url, directorio_destino?) - Clona un repo de GitHub DIRECTAMENTE
   Ejemplo: clonar_repositorio("https://github.com/yecos/signalTrade.git")

2. ejecutar_comando(comando, directorio?) - Ejecuta un comando del sistema DIRECTAMENTE
   Ejemplo: ejecutar_comando("git status", "C:\\Projects\\signalTrade")

3. instalar_dependencias(directorio, tipo?) - Instala dependencias DIRECTAMENTE
   Ejemplo: instalar_dependencias("C:\\Projects\\signalTrade", "npm")

4. listar_archivos(ruta, profundidad?) - Lista archivos de un directorio
   Ejemplo: listar_archivos("C:\\Projects\\signalTrade", 3)

5. leer_archivo(ruta) - Lee el contenido de un archivo
   Ejemplo: leer_archivo("C:\\Projects\\signalTrade\\package.json")

6. escribir_archivo(ruta, contenido) - Escribe un archivo completo (con backup automático)
   Ejemplo: escribir_archivo("C:\\Projects\\signalTrade\\test.js", "console.log('hello')")

7. modificar_archivo(ruta, texto_original, texto_nuevo) - Modifica parte de un archivo
   Ejemplo: modificar_archivo("app.js", "version: 1.0", "version: 2.0")

8. buscar_en_archivos(directorio, texto, extension?) - Busca en archivos
   Ejemplo: buscar_en_archivos("C:\\Projects\\signalTrade", "useEffect", ".tsx")

9. calcular(expresion) - Calcula expresión matemática
   Ejemplo: calcular("100 * 0.15")

10. buscar(consulta) - Busca en internet
    Ejemplo: buscar("Next.js 14 app router tutorial")

11. consultar_experto(pregunta, modo?) - Consulta con IA avanzada en la nube
    Ejemplo: consultar_experto("¿Cómo implementar WebSocket en Next.js?", "codigo")

12. consultar_con_codigo(pregunta, codigo, lenguaje?) - Envía código a IA avanzada
    Ejemplo: consultar_con_codigo("Mejora esta función", "function x() { ... }", "typescript")

13. consultar_plan(tarea, contexto?) - Pide plan a IA avanzada
    Ejemplo: consultar_plan("Agregar alertas al motor de trading")

14. info_sistema() - Información del sistema

## CÓMO RESPONDER:

Cuando el usuario te pida algo, debes responder CON LLAMADAS A HERRAMIENTAS.
Escribe las llamadas directamente en tu respuesta. El sistema las ejecutará automáticamente.

Formato de llamada: nombre_herramienta("parametro1", "parametro2")

Puedes hacer múltiples llamadas en una sola respuesta.

## EJEMPLOS:

Usuario: "Clona mi repositorio https://github.com/yecos/signalTrade.git"
Tu respuesta:
clonar_repositorio("https://github.com/yecos/signalTrade.git")

Usuario: "Analiza el proyecto signalTrade"
Tu respuesta:
listar_archivos("{projects_dir}\\signalTrade", 3)
leer_archivo("{projects_dir}\\signalTrade\\package.json")
leer_archivo("{projects_dir}\\signalTrade\\README.md")

Usuario: "Instala las dependencias del proyecto"
Tu respuesta:
instalar_dependencias("{projects_dir}\\signalTrade", "npm")

Usuario: "Busca cómo se usa WebSocket en el proyecto"
Tu respuesta:
buscar_en_archivos("{projects_dir}\\signalTrade", "WebSocket", ".ts")
buscar_en_archivos("{projects_dir}\\signalTrade", "ws://", ".ts")

Usuario: "Crea un componente de dashboard"
Tu respuesta:
consultar_con_codigo("Crea un componente React de dashboard de trading con gráficos", "", "typescript")

## DIRECTORIOS DEL USUARIO:
- Descargas: {downloads_dir}
- Documentos: {documents_dir}
- Proyectos: {projects_dir}

## REGLAS FINALES:
1. NUNCA des instrucciones al usuario. EJECUTA tú mismo.
2. NUNCA digas "abre una terminal", "ejecuta este comando", "puedes usar..."
3. SIEMPRE llama a las herramientas directamente.
4. Si no sabes algo, usa buscar() o consultar_experto().
5. Los backups son automáticos, no te preocupes por perder datos.
6. Responde SIEMPRE en español.
7. Si el usuario te pide clonar un repo, USA clonar_repositorio(), NO le digas cómo hacerlo.
8. Si el usuario te pide instalar algo, USA instalar_dependencias() o ejecutar_comando(), NO le digas cómo.
""".format(
    downloads_dir=DOWNLOADS_DIR,
    documents_dir=DOCUMENTS_DIR,
    projects_dir=PROJECTS_DIR
)

# =====================================================================
# AGENTE AUTÓNOMO
# =====================================================================

def parse_tool_calls(text):
    """Extrae llamadas a herramientas del texto del agente"""
    calls = []
    pattern = r'(\w+)\((.*?)\)'
    matches = re.finditer(pattern, text, re.DOTALL)
    for match in matches:
        tool_name = match.group(1)
        params_str = match.group(2)
        if tool_name not in TOOL_FUNCTIONS:
            continue
        params = []
        try:
            params = json.loads(f'[{params_str}]')
        except:
            quoted = re.findall(r'"([^"]*)"', params_str)
            if quoted:
                params = quoted
            else:
                quoted = re.findall(r"'([^']*)'", params_str)
                if quoted:
                    params = quoted
                else:
                    params = [p.strip().strip('"').strip("'") for p in params_str.split(",")]
        calls.append({"tool": tool_name, "params": params})
    return calls

def execute_tool_call(tool_name, params):
    """Ejecuta una llamada a herramienta"""
    if tool_name not in TOOL_FUNCTIONS:
        return f"❌ Herramienta no encontrada: {tool_name}"
    func = TOOL_FUNCTIONS[tool_name]
    try:
        result = func(*params)
        return result
    except TypeError as e:
        try:
            result = func(*params[:func.__code__.co_argcount])
            return result
        except:
            return f"❌ Error en parámetros de {tool_name}: {str(e)}"
    except Exception as e:
        return f"❌ Error ejecutando {tool_name}: {str(e)}"

def detect_giving_instructions(text):
    """Detecta si el modelo está dando instrucciones en vez de ejecutar"""
    instruction_patterns = [
        "abre una terminal", "abre el terminal", "abre powershell", "abre cmd",
        "ejecuta el siguiente comando", "puedes usar el comando",
        "ejecuta este comando", "corre el comando", "run the command",
        "sigue estos pasos", "paso 1:", "paso 2:", "paso 3:",
        "ve a la terminal", "ve a powershell", "navega al directorio",
        "cd ", "para clonar el repositorio,",
        "primero necesitas", "luego necesitas", "después debes",
        "puedes clonar", "puedes ejecutar", "puedes instalar",
        "te sugiero que", "te recomiendo que",
        "git clone https", "npm install", "pip install",
        "abra una", "abra el", "ejecutarlo manualmente",
    ]
    text_lower = text.lower()
    matches = sum(1 for p in instruction_patterns if p in text_lower)
    return matches >= 2  # Si hay 2+ patrones, está dando instrucciones

def run_agent(user_message, history=[]):
    """Ejecuta el agente autónomo completo"""
    messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    messages.extend(history[-6:])
    messages.append({"role": "user", "content": user_message})
    
    # === PASO 1: El agente responde con llamadas a herramientas ===
    exec_prompt = messages.copy()
    exec_prompt.append({
        "role": "user", 
        "content": "\n\nEJECUTA las herramientas necesarias AHORA. Escribe las llamadas directamente. NO expliques cómo hacerlo, HAZLO tú. Ejemplo: clonar_repositorio(\"https://github.com/...\")"
    })
    
    try:
        response = ollama.chat(model=AGENT_MODEL, messages=exec_prompt, stream=False)
        agent_text = response["message"]["content"]
    except Exception as e:
        return f"❌ Error conectando con Ollama: {str(e)}", []
    
    # Mostrar lo que el agente quiere hacer
    st.markdown(f"""
    <div class="plan-box">
    <strong>🤖 Agente ejecutando:</strong><br><br>
    {agent_text.replace(chr(10), '<br>')}
    </div>
    """, unsafe_allow_html=True)
    
    # === PASO 2: Extraer y ejecutar herramientas ===
    tool_calls = parse_tool_calls(agent_text)
    
    # === AUTO-CORRECCIÓN: Si el modelo dio instrucciones en vez de ejecutar ===
    if not tool_calls and detect_giving_instructions(agent_text):
        st.markdown('<div class="tool-warning">⚠️ El agente dio instrucciones en vez de ejecutar. Corrigiendo automáticamente...</div>', unsafe_allow_html=True)
        
        # Extraer comandos del texto y ejecutarlos nosotros
        correction_prompt = messages.copy()
        correction_prompt.append({"role": "assistant", "content": agent_text})
        correction_prompt.append({
            "role": "user",
            "content": """NO expliques qué hacer. NO des pasos. NO digas 'ejecuta este comando'.
EJECUTA las herramientas directamente escribiendo las llamadas.

Ejemplo de lo que DEBES escribir:
clonar_repositorio("https://github.com/yecos/signalTrade.git")

Ejemplo de lo que NO debes escribir:
"Abre una terminal y ejecuta git clone..."
"Puedes usar el comando npm install"

Ahora EJECUTA las herramientas:"""
        })
        
        try:
            correction_response = ollama.chat(model=AGENT_MODEL, messages=correction_prompt, stream=False)
            agent_text = correction_response["message"]["content"]
            tool_calls = parse_tool_calls(agent_text)
            st.markdown(f"""
            <div class="plan-box">
            <strong>🔄 Corrección:</strong><br><br>
            {agent_text.replace(chr(10), '<br>')}
            </div>
            """, unsafe_allow_html=True)
        except Exception as e:
            pass
    
    # Segundo intento si aún no hay herramientas
    if not tool_calls:
        exec_prompt2 = messages.copy()
        exec_prompt2.append({
            "role": "user",
            "content": "Escribe SOLO las llamadas a herramientas, nada más. Formato: herramienta(\"param1\", \"param2\")"
        })
        try:
            response2 = ollama.chat(model=AGENT_MODEL, messages=exec_prompt2, stream=False)
            agent_text2 = response2["message"]["content"]
            tool_calls = parse_tool_calls(agent_text2)
        except:
            pass
    
    # Si aún no hay herramientas, intentar ejecución directa basada en la intención
    if not tool_calls:
        tool_calls = auto_execute_from_intent(user_message)
    
    results = []
    tool_results_container = st.container()
    
    for i, call in enumerate(tool_calls):
        with tool_results_container:
            is_bridge = call["tool"].startswith("consultar")
            css_class = "bridge-box" if is_bridge else "tool-cmd"
            icon = "☁️" if is_bridge else "🔧"
            st.markdown(f'<div class="{css_class}">{icon} Paso {i+1}: {call["tool"]}({", ".join(str(p)[:50] for p in call["params"])})</div>', unsafe_allow_html=True)
            
            result = execute_tool_call(call["tool"], call["params"])
            results.append({"tool": call["tool"], "params": call["params"], "result": result})
            
            result_preview = str(result)[:800]
            st.markdown(f'<div class="tool-result">{result_preview}</div>', unsafe_allow_html=True)
    
    # === PASO 3: REPLANIFICAR si es necesario ===
    replan_needed = any(
        "❌" in r["result"] or "Error" in r["result"] or "no encontrado" in r["result"].lower()
        for r in results
    )
    
    if replan_needed and len(results) > 0:
        replan_prompt = messages.copy()
        replan_prompt.append({"role": "assistant", "content": agent_text})
        results_text = "Resultados de la ejecución:\n\n"
        for r in results:
            results_text += f"- {r['tool']}({', '.join(str(p)[:30] for p in r['params'])}): {str(r['result'])[:300]}\n"
        replan_prompt.append({"role": "user", "content": results_text + "\n\nAlgunas herramientas fallaron. EJECUTA las herramientas corregidas directamente."})
        
        try:
            replan_response = ollama.chat(model=AGENT_MODEL, messages=replan_prompt, stream=False)
            replan_text = replan_response["message"]["content"]
            replan_calls = parse_tool_calls(replan_text)
            for i, call in enumerate(replan_calls):
                with tool_results_container:
                    st.markdown(f'<div class="tool-cmd">🔄 Replan {i+1}: {call["tool"]}({", ".join(str(p)[:50] for p in call["params"])})</div>', unsafe_allow_html=True)
                    result = execute_tool_call(call["tool"], call["params"])
                    results.append({"tool": call["tool"], "params": call["params"], "result": result})
                    result_preview = str(result)[:800]
                    st.markdown(f'<div class="tool-result">{result_preview}</div>', unsafe_allow_html=True)
        except:
            pass
    
    # === PASO 4: RESPUESTA FINAL ===
    final_prompt = messages.copy()
    final_prompt.append({"role": "assistant", "content": agent_text})
    results_summary = "Resultados de las herramientas:\n\n"
    for r in results:
        results_summary += f"- {r['tool']}: {str(r['result'])[:500]}\n"
    final_prompt.append({
        "role": "user", 
        "content": results_summary + "\n\nBasándote en estos resultados, da una respuesta final clara y útil al usuario en español. NO des instrucciones de comandos, solo explica lo que hiciste y los resultados."
    })
    
    try:
        final_response = ollama.chat(model=AGENT_MODEL, messages=final_prompt, stream=False)
        final_text = final_response["message"]["content"]
    except Exception as e:
        final_text = f"Error generando respuesta final: {str(e)}\n\nResultados:\n{results_summary}"
    
    new_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": final_text}
    ]
    
    return final_text, new_history

def auto_execute_from_intent(user_message):
    """Ejecución directa basada en la intención del mensaje cuando el modelo no genera herramientas"""
    msg_lower = user_message.lower()
    calls = []
    
    # Detectar clonar repositorio
    github_match = re.search(r'https://github\.com/[\w-]+/[\w-]+', user_message)
    if github_match and ("clona" in msg_lower or "descargar" in msg_lower or "descarga" in msg_lower or "github" in msg_lower):
        url = github_match.group(0)
        if not url.endswith(".git"):
            url += ".git"
        calls.append({"tool": "clonar_repositorio", "params": [url]})
    
    # Detectar instalar dependencias
    if ("instal" in msg_lower or "dependencia" in msg_lower or "npm install" in msg_lower) and not calls:
        project = st.session_state.get('active_project', '')
        if project and os.path.exists(project):
            calls.append({"tool": "instalar_dependencias", "params": [project]})
    
    # Detectar analizar proyecto
    if ("analiz" in msg_lower or "estructura" in msg_lower or "revisa" in msg_lower) and not calls:
        project = st.session_state.get('active_project', '')
        if project and os.path.exists(project):
            calls.append({"tool": "listar_archivos", "params": [project, "3"]})
            pkg_json = os.path.join(project, "package.json")
            if os.path.exists(pkg_json):
                calls.append({"tool": "leer_archivo", "params": [pkg_json]})
    
    # Detectar ejecutar proyecto
    if ("ejecuta" in msg_lower or "corre" in msg_lower or "run" in msg_lower or "inicia" in msg_lower) and "dev" in msg_lower and not calls:
        project = st.session_state.get('active_project', '')
        if project and os.path.exists(project):
            calls.append({"tool": "ejecutar_comando", "params": ["npm run dev", project]})
    
    return calls

# =====================================================================
# CHAT SIMPLE
# =====================================================================

def chat_simple(message, history=[]):
    messages = [{"role": "system", "content": "Eres un asistente útil y amigable. Respondes en español."}]
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
        st.error(f"Error inicializando ChromaDB: {e}")
        return None, None

def add_document_to_chroma(text, source, collection):
    try:
        chunk_size = 500
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        for i, chunk in enumerate(chunks):
            chunk_id = f"{source}_{i}"
            embedding_response = ollama.embeddings(model="nomic-embed-text", prompt=chunk)
            collection.add(
                ids=[chunk_id],
                embeddings=[embedding_response["embedding"]],
                documents=[chunk],
                metadatas=[{"source": source, "chunk": i}]
            )
        return len(chunks)
    except Exception as e:
        st.error(f"Error agregando documento: {e}")
        return 0

def rag_query(question, collection):
    try:
        query_embedding = ollama.embeddings(model="nomic-embed-text", prompt=question)["embedding"]
        results = collection.query(query_embeddings=[query_embedding], n_results=5)
        if not results["documents"][0]:
            return "No encontré documentos relevantes."
        context = "\n\n".join(results["documents"][0])
        messages = [
            {"role": "system", "content": f"Responde basándote en este contexto:\n\n{context}\n\nResponde en español."},
            {"role": "user", "content": question}
        ]
        response = ollama.chat(model=CHAT_MODEL, messages=messages, stream=False)
        return response["message"]["content"]
    except Exception as e:
        return f"❌ Error en RAG: {str(e)}"

# =====================================================================
# ASISTENTE DE CÓDIGO
# =====================================================================

def code_assistant(message, mode="explicar"):
    prompts = {
        "explicar": "Explica el siguiente código de forma clara y detallada en español:",
        "mejorar": "Mejora el siguiente código. Devuelve SOLO el código mejorado con comentarios en español:",
        "corregir": "Corrige los errores del siguiente código. Devuelve el código corregido:",
        "crear": "Crea el código solicitado. Devuelve código limpio y funcional:"
    }
    
    # Si el bridge está configurado, usar IA en la nube para código
    bridge_config = load_bridge_config()
    if bridge_config.get("api_key"):
        modo_map = {"explicar": "codigo", "mejorar": "codigo", "corregir": "codigo", "crear": "codigo"}
        return consultar_experto(message, modo=modo_map.get(mode, "codigo"))
    
    # Si no, usar modelo local
    system_prompt = "Eres un programador experto. Código en inglés, explicaciones en español."
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"{prompts.get(mode, prompts['explicar'])}\n\n{message}"}
    ]
    try:
        response = ollama.chat(model=CODE_MODEL, messages=messages, stream=False)
        return response["message"]["content"]
    except Exception as e:
        return f"❌ Error: {str(e)}"

# =====================================================================
# INTERFAZ STREAMLIT
# =====================================================================

def render_bridge_settings():
    """Renderiza la configuración del IA Bridge en el sidebar"""
    st.subheader("☁️ IA Bridge")
    
    config = load_bridge_config()
    
    # Selector de proveedor
    proveedor_nombres = {k: v["nombre"] for k, v in PROVEEDORES.items()}
    selected = st.selectbox(
        "Proveedor",
        options=list(proveedor_nombres.keys()),
        format_func=lambda x: proveedor_nombres[x],
        index=list(proveedor_nombres.keys()).index(config.get("proveedor", "groq"))
    )
    config["proveedor"] = selected
    
    # Mostrar info del proveedor
    prov = PROVEEDORES[selected]
    if prov["gratis"]:
        st.success("🆓 Gratuito")
    else:
        st.info("💰 De pago")
    
    st.caption(prov["descripcion"])
    
    # API Key
    api_key = st.text_input(
        "API Key",
        value=config.get("api_key", ""),
        type="password",
        help=f"Obtén tu key en: {prov['como_obtener_key']}"
    )
    config["api_key"] = api_key
    
    # Link para obtener key
    st.markdown(f"🔑 [Obtener API Key]({prov['como_obtener_key']})")
    
    # Modelo
    modelos = prov["modelos"]
    modelo_default = config.get("modelo") or prov["modelo_default"]
    modelo_index = modelos.index(modelo_default) if modelo_default in modelos else 0
    
    modelo = st.selectbox("Modelo", options=modelos, index=modelo_index)
    config["modelo"] = modelo
    
    # Contexto del proyecto
    with st.expander("📝 Contexto del Proyecto"):
        contexto = st.text_area(
            "Describe tu proyecto (ayuda a la IA a dar mejores respuestas)",
            value=config.get("contexto_proyecto", ""),
            height=100,
            placeholder="Ej: SignalTrader Pro - Motor de trading cuantitativo con Next.js, TypeScript, 10 engines..."
        )
        config["contexto_proyecto"] = contexto
    
    # Guardar configuración
    if st.button("💾 Guardar Configuración"):
        save_bridge_config(config)
        st.success("✅ Configuración guardada")
    
    # Probar conexión
    if st.button("🔌 Probar Conexión"):
        if not api_key:
            st.error("❌ Ingresa una API Key primero")
        else:
            with st.spinner("Probando conexión..."):
                success, msg = test_bridge_connection()
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
    
    # Estado
    st.divider()
    if config.get("api_key"):
        st.success(f"☁️ {PROVEEDORES[selected]['nombre']}")
        st.caption(f"Modelo: {modelo}")
    else:
        st.warning("☁️ Sin configurar")

def main():
    # Sidebar
    with st.sidebar:
        st.title("🤖 IA Local Pro")
        st.caption("Agente Autónomo + IA en la Nube")
        
        mode = st.radio(
            "Modo",
            ["🚀 Agente Autónomo", "💬 Chat Simple", "📚 RAG Documentos", "💻 Código"],
            index=0
        )
        
        st.divider()
        
        # Configuración de modelos locales
        st.subheader("⚙️ Modelos Locales")
        agente_model = st.selectbox(
            "Agente",
            ["qwen2.5:14b", "qwen2.5:7b", "llama3.1:8b"],
            index=0
        )
        global AGENT_MODEL
        AGENT_MODEL = agente_model
        
        st.divider()
        
        # IA Bridge Settings
        render_bridge_settings()
        
        st.divider()
        
        # Proyectos
        st.subheader("📁 Proyectos")
        if os.path.exists(PROJECTS_DIR):
            proyectos = [d for d in os.listdir(PROJECTS_DIR) if os.path.isdir(os.path.join(PROJECTS_DIR, d))]
            if proyectos:
                selected_project = st.selectbox("Proyecto activo", proyectos)
                st.session_state['active_project'] = os.path.join(PROJECTS_DIR, selected_project)
            else:
                st.info("Clona un repositorio para empezar")
        
        st.divider()
        
        # Herramientas
        with st.expander("🔧 Herramientas"):
            for name, info in TOOLS.items():
                icon = "☁️" if "consultar" in name else "🔧"
                st.markdown(f"{icon} **{name}**: {info['description']}")
        
        # Botones
        st.divider()
        if st.button("📊 Info Sistema"):
            st.text(tool_info_sistema())
        if st.button("🗑️ Limpiar Historial"):
            st.session_state['history'] = []
            st.rerun()
    
    # Contenido principal
    if "🚀" in mode:
        render_autonomous_agent()
    elif "💬" in mode:
        render_simple_chat()
    elif "📚" in mode:
        render_rag()
    elif "💻" in mode:
        render_code_assistant()

def render_autonomous_agent():
    st.title("🚀 Agente Autónomo Pro")
    
    # Indicador de IA Bridge
    bridge_config = load_bridge_config()
    if bridge_config.get("api_key"):
        prov = PROVEEDORES.get(bridge_config.get("proveedor", "groq"), {})
        st.markdown(f"☁️ **IA Avanzada conectada**: {prov.get('nombre', '?')} — El agente puede consultar al experto")
    else:
        st.caption("💡 Tip: Configura ☁️ IA Bridge en el sidebar para que el agente pueda consultar con IA avanzada")
    
    # Accesos rápidos
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("📥 Clonar Repo"):
            st.session_state['quick_task'] = "Clona el repositorio https://github.com/yecos/signalTrade.git en mi carpeta de proyectos"
    with col2:
        if st.button("📦 Instalar Deps"):
            project = st.session_state.get('active_project', '')
            if project and os.path.exists(project):
                st.session_state['quick_task'] = f"Instala las dependencias del proyecto en {project}"
    with col3:
        if st.button("🔍 Analizar"):
            project = st.session_state.get('active_project', '')
            if project and os.path.exists(project):
                st.session_state['quick_task'] = f"Analiza el proyecto en {project}. Lee package.json, README y archivos principales. Usa consultar_experto para dar un análisis experto completo."
    with col4:
        if st.button("☁️ Preguntar Experto"):
            st.session_state['quick_task'] = "Usa consultar_experto para responder esta pregunta de un experto:"
    
    if 'history' not in st.session_state:
        st.session_state['history'] = []
    
    for msg in st.session_state['history']:
        if msg["role"] == "user":
            st.chat_message("user").write(msg["content"])
        elif msg["role"] == "assistant":
            st.chat_message("assistant").write(msg["content"])
    
    quick_task = st.session_state.pop('quick_task', None)
    prompt = st.chat_input("¿Qué quieres que haga el agente?")
    
    user_input = quick_task or prompt
    
    if user_input:
        st.chat_message("user").write(user_input)
        with st.chat_message("assistant"):
            with st.spinner("🤖 Agente trabajando..."):
                response, new_history = run_agent(user_input, st.session_state['history'])
                st.session_state['history'] = new_history
                st.markdown(response)

def render_simple_chat():
    st.title("💬 Chat Simple")
    st.markdown(f"Chat directo con {CHAT_MODEL}")
    
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
    st.markdown("Sube documentos y pregunta sobre su contenido.")
    
    client, collection = init_chroma()
    
    if collection:
        uploaded = st.file_uploader("Subir documento", type=["pdf", "txt", "md"])
        if uploaded:
            with st.spinner("Procesando documento..."):
                text = ""
                if uploaded.name.endswith(".pdf"):
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(uploaded)
                        for page in reader.pages:
                            text += page.extract_text() or ""
                    except:
                        st.error("Instala: pip install pypdf")
                else:
                    text = uploaded.getvalue().decode("utf-8", errors="replace")
                if text:
                    chunks = add_document_to_chroma(text, uploaded.name, collection)
                    st.success(f"✅ Documento agregado: {uploaded.name} ({chunks} fragmentos)")
        
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
        st.success("☁️ Usando IA avanzada en la nube para código")
    else:
        st.caption(f"Usando modelo local {CODE_MODEL}. Configura IA Bridge para mejor calidad.")
    
    mode = st.selectbox("Modo", ["explicar", "mejorar", "corregir", "crear"])
    
    if 'code_history' not in st.session_state:
        st.session_state['code_history'] = []
    
    for msg in st.session_state['code_history']:
        st.chat_message(msg["role"]).write(msg["content"])
    
    prompt = st.chat_input("Pega tu código o describe qué quieres crear...")
    if prompt:
        st.chat_message("user").write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Generando código..."):
                response = code_assistant(prompt, mode)
                st.markdown(response)
        st.session_state['code_history'].append({"role": "user", "content": prompt})
        st.session_state['code_history'].append({"role": "assistant", "content": response})

# =====================================================================
# EJECUCIÓN
# =====================================================================

if __name__ == "__main__":
    main()
