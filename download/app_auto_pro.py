"""
=============================================================================
  AGENTE AUTÓNOMO PRO v4 - Tool Calling + Auto-ejecución forzada
=============================================================================
  v4: Si el usuario pide clonar un repo y el modelo no lo hace,
  lo ejecutamos AUTOMÁTICAMENTE. No dependemos 100% del modelo.
  
  Requisitos:
  pip install streamlit ollama chromadb pypdf ddgs psutil
=============================================================================
"""

import streamlit as st
import ollama
import json
import os
import subprocess
import platform
import datetime
import re
import shutil
import urllib.request
import urllib.error

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

# =====================================================================
# PÁGINA
# =====================================================================

st.set_page_config(page_title="IA Local Pro", page_icon="🤖", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .stApp { max-width: 1400px; margin: 0 auto; }
    .tool-result { background: #1e1e2e; border: 1px solid #45475a; border-radius: 8px; padding: 12px; margin: 8px 0; font-family: 'Consolas', monospace; font-size: 13px; color: #cdd6f4; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
    .tool-cmd { background: #1e1e2e; border: 1px solid #89b4fa; border-radius: 8px; padding: 12px; margin: 8px 0; font-family: 'Consolas', monospace; font-size: 13px; color: #89b4fa; }
    .tool-success { background: #1e1e2e; border: 1px solid #a6e3a1; border-radius: 8px; padding: 12px; margin: 8px 0; color: #a6e3a1; }
    .tool-auto { background: #1e1e2e; border: 2px solid #f9e2af; border-radius: 8px; padding: 12px; margin: 8px 0; font-family: 'Consolas', monospace; font-size: 13px; color: #f9e2af; }
    .bridge-box { background: linear-gradient(135deg, #1e1e2e, #1e3a5f); border: 1px solid #89b4fa; border-radius: 10px; padding: 16px; margin: 12px 0; color: #89b4fa; }
    .plan-box { background: linear-gradient(135deg, #1e1e2e, #313244); border: 1px solid #cba6f7; border-radius: 10px; padding: 16px; margin: 12px 0; color: #cba6f7; }
</style>
""", unsafe_allow_html=True)

# =====================================================================
# IA BRIDGE
# =====================================================================

PROVEEDORES = {
    "groq": {"nombre": "Groq (GRATIS)", "url_base": "https://api.groq.com/openai/v1",
        "modelos": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        "modelo_default": "llama-3.3-70b-versatile", "como_obtener_key": "https://console.groq.com/keys", "gratis": True},
    "openrouter": {"nombre": "OpenRouter", "url_base": "https://openrouter.ai/api/v1",
        "modelos": ["meta-llama/llama-3.3-70b-instruct:free", "deepseek/deepseek-chat:free"],
        "modelo_default": "meta-llama/llama-3.3-70b-instruct:free", "como_obtener_key": "https://openrouter.ai/keys", "gratis": True},
    "openai": {"nombre": "OpenAI (GPT-4)", "url_base": "https://api.openai.com/v1",
        "modelos": ["gpt-4o", "gpt-4o-mini"], "modelo_default": "gpt-4o-mini",
        "como_obtener_key": "https://platform.openai.com/api-keys", "gratis": False},
    "deepseek": {"nombre": "DeepSeek", "url_base": "https://api.deepseek.com/v1",
        "modelos": ["deepseek-chat", "deepseek-reasoner"], "modelo_default": "deepseek-chat",
        "como_obtener_key": "https://platform.deepseek.com/api_keys", "gratis": False},
}

def load_bridge_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {"proveedor": "groq", "api_key": "", "modelo": "", "contexto_proyecto": ""}

def save_bridge_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def call_cloud_api(url_base, api_key, model, messages, temperature=0.7, max_tokens=2048):
    endpoint = f"{url_base}/chat/completions"
    payload = json.dumps({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}).encode('utf-8')
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    if "openrouter" in url_base:
        headers["HTTP-Referer"] = "https://ia-local.app"
    req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            return {"success": True, "content": result["choices"][0]["message"]["content"]}
    except Exception as e:
        return {"success": False, "error": str(e)}

def consultar_experto(pregunta, contexto="", modo="general"):
    config = load_bridge_config()
    if not config.get("api_key"):
        return "❌ No hay API key. Configúrala en ☁️ IA Bridge en el sidebar."
    prov = PROVEEDORES.get(config.get("proveedor", "groq"), PROVEEDORES["groq"])
    modelo = config.get("modelo") or prov["modelo_default"]
    system_prompts = {"general": "Eres un experto. Respondes en español.", "codigo": "Eres un programador experto. Código en inglés, explicaciones en español.", "analisis": "Eres un analista experto. Respondes en español.", "plan": "Eres un arquitecto de software. Respondes en español."}
    messages = [{"role": "system", "content": system_prompts.get(modo, system_prompts["general"])}]
    if contexto:
        messages.append({"role": "user", "content": f"Contexto:\n{contexto}\n\nPregunta: {pregunta}"})
    else:
        messages.append({"role": "user", "content": pregunta})
    result = call_cloud_api(prov["url_base"], config["api_key"], modelo, messages)
    return result["content"] if result["success"] else f"❌ Error: {result['error']}"

def test_bridge():
    config = load_bridge_config()
    if not config.get("api_key"): return False, "Sin API key"
    prov = PROVEEDORES.get(config.get("proveedor", "groq"), PROVEEDORES["groq"])
    modelo = config.get("modelo") or prov["modelo_default"]
    result = call_cloud_api(prov["url_base"], config["api_key"], modelo,
        [{"role": "user", "content": "Responde: OK"}], temperature=0, max_tokens=5)
    return (True, f"✅ {prov['nombre']}") if result["success"] else (False, f"❌ {result['error']}")

# =====================================================================
# FUNCIONES AUXILIARES
# =====================================================================

def create_backup(filepath):
    try:
        if os.path.exists(filepath):
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            bp = os.path.join(BACKUP_DIR, f"{os.path.basename(filepath)}.{ts}.bak")
            shutil.copy2(filepath, bp)
            return bp
    except: pass
    return None

def is_dangerous(cmd):
    c = cmd.lower().strip()
    for b in BLOCKED_COMMANDS:
        if b in c: return "blocked"
    for d in DANGEROUS_COMMANDS:
        if d.lower() in c: return "dangerous"
    return "safe"

def run_cmd(command, cwd=None, timeout=120):
    try:
        dl = is_dangerous(command)
        if dl == "blocked": return "⛔ BLOQUEADO.", -1
        if dl == "dangerous": return "⚠️ Peligroso. Requiere confirmación.", -2
        r = subprocess.run(command, shell=IS_WINDOWS, capture_output=True, text=True, timeout=timeout, cwd=cwd, encoding='utf-8', errors='replace')
        out = (r.stdout or "") + (f"\n[STDERR]: {r.stderr}" if r.stderr else "")
        return (out.strip() or "(Sin salida)"), r.returncode
    except subprocess.TimeoutExpired: return f"⏱️ Timeout ({timeout}s)", -3
    except FileNotFoundError: return "❌ Comando no encontrado.", -4
    except Exception as e: return f"❌ Error: {e}", -5

# =====================================================================
# HERRAMIENTAS - Funciones Python reales
# =====================================================================

def tool_ejecutar_comando(comando: str, directorio: str = None) -> str:
    """Ejecuta un comando del sistema (git, npm, pip, python, etc.)"""
    cwd = directorio if directorio and os.path.isdir(directorio) else None
    result, code = run_cmd(comando, cwd=cwd)
    return result

def tool_clonar_repositorio(url: str, directorio_destino: str = None) -> str:
    """Clona un repositorio de GitHub automáticamente."""
    if not url.startswith("https://github.com/"): return "❌ URL inválida."
    if not directorio_destino:
        repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
        directorio_destino = os.path.join(PROJECTS_DIR, repo_name)
    if os.path.exists(directorio_destino):
        return f"⚠️ Ya existe: {directorio_destino}\nUsa ejecutar_comando('git pull', '{directorio_destino}') para actualizar."
    result, code = run_cmd(f'git clone {url} "{directorio_destino}"')
    if code == 0:
        return f"✅ Clonado en: {directorio_destino}\n\nContenido:\n" + tool_listar_archivos(directorio_destino, 2)
    return f"❌ Error:\n{result}"

def tool_instalar_dependencias(directorio: str, tipo: str = None) -> str:
    """Instala dependencias de un proyecto (npm o pip)."""
    if not os.path.isdir(directorio): return f"❌ Directorio no encontrado: {directorio}"
    if not tipo:
        if os.path.exists(os.path.join(directorio, "package.json")): tipo = "npm"
        elif os.path.exists(os.path.join(directorio, "requirements.txt")): tipo = "pip"
        else: return "❌ No se detectó tipo. Especifica: npm o pip."
    if tipo == "npm":
        result, code = run_cmd("npm install", cwd=directorio, timeout=300)
        return f"✅ npm install completado\n\n{result[:500]}" if code == 0 else f"❌ Error npm:\n{result}"
    elif tipo == "pip":
        rf = os.path.join(directorio, "requirements.txt")
        if os.path.exists(rf):
            result, code = run_cmd(f'pip install -r "{rf}"', cwd=directorio, timeout=300)
            return f"✅ pip install completado\n\n{result[:500]}" if code == 0 else f"❌ Error pip:\n{result}"
        return "❌ No hay requirements.txt"
    return f"❌ Tipo no soportado: {tipo}"

def tool_listar_archivos(ruta: str, profundidad: int = 3) -> str:
    """Lista archivos y carpetas de un directorio."""
    if not os.path.exists(ruta): return f"❌ Ruta no encontrada: {ruta}"
    if os.path.isfile(ruta): return f"📄 {ruta} ({os.path.getsize(ruta)} bytes)"
    res = [f"📂 {ruta}\n"]
    for root, dirs, files in os.walk(ruta):
        depth = os.path.relpath(root, ruta).count(os.sep) if os.path.relpath(root, ruta) != "." else 0
        if depth >= profundidad: dirs.clear(); continue
        skip = ['node_modules', '.git', '.next', '__pycache__', '.venv', 'venv', 'dist', '.cache', '.turbo']
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith('.')]
        indent = "  " * (depth + 1)
        for d in sorted(dirs): res.append(f"{indent}📁 {d}/")
        for f in sorted(files):
            try: s = os.path.getsize(os.path.join(root, f))
            except: s = 0
            res.append(f"{indent}📄 {f} ({s//1024}kb)" if s >= 1024 else f"{indent}📄 {f} ({s}b)")
    return "\n".join(res)

def tool_leer_archivo(ruta: str) -> str:
    """Lee el contenido de un archivo."""
    if not os.path.exists(ruta): return f"❌ No encontrado: {ruta}"
    try:
        with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
            c = f.read()
        return c[:15000] + f"\n... [Truncado: {len(c)} chars]" if len(c) > 15000 else c
    except Exception as e: return f"❌ Error: {e}"

def tool_escribir_archivo(ruta: str, contenido: str) -> str:
    """Escribe contenido en un archivo (con backup automático)."""
    try:
        d = os.path.dirname(ruta)
        if d: os.makedirs(d, exist_ok=True)
        bp = create_backup(ruta)
        with open(ruta, 'w', encoding='utf-8') as f: f.write(contenido)
        return f"✅ Escrito: {ruta} ({len(contenido)} chars)" + (f"\n📦 Backup: {bp}" if bp else "")
    except Exception as e: return f"❌ Error: {e}"

def tool_modificar_archivo(ruta: str, texto_original: str, texto_nuevo: str) -> str:
    """Modifica parte de un archivo (busca y reemplaza)."""
    if not os.path.exists(ruta): return f"❌ No encontrado: {ruta}"
    try:
        with open(ruta, 'r', encoding='utf-8', errors='replace') as f: c = f.read()
        if texto_original not in c: return f"❌ Texto no encontrado. Usa leer_archivo primero."
        bp = create_backup(ruta)
        with open(ruta, 'w', encoding='utf-8') as f: f.write(c.replace(texto_original, texto_nuevo))
        return f"✅ Modificado: {ruta}" + (f"\n📦 Backup: {bp}" if bp else "")
    except Exception as e: return f"❌ Error: {e}"

def tool_buscar_en_archivos(directorio: str, texto: str, extension: str = None) -> str:
    """Busca texto dentro de archivos de un directorio."""
    if not os.path.isdir(directorio): return f"❌ Directorio no encontrado: {directorio}"
    res = []
    skip_d = ['node_modules', '.git', '.next', '__pycache__', '.venv', 'venv', 'dist', '.cache', '.turbo', 'build']
    skip_e = ['.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.woff', '.woff2', '.ttf', '.eot', '.map', '.lock']
    for root, dirs, files in os.walk(directorio):
        dirs[:] = [d for d in dirs if d not in skip_d and not d.startswith('.')]
        for fn in files:
            fp = os.path.join(root, fn)
            ext = os.path.splitext(fn)[1]
            if ext.lower() in skip_e: continue
            if extension and ext.lower() != extension.lower(): continue
            try:
                with open(fp, 'r', encoding='utf-8', errors='replace') as f:
                    for i, line in enumerate(f, 1):
                        if texto.lower() in line.lower():
                            res.append(f"{os.path.relpath(fp, directorio)}:{i} → {line.strip()[:120]}")
                            if len(res) >= 50: return "\n".join(res) + "\n... [50 máx]"
            except: continue
    return "\n".join(res) if res else f"🔍 '{texto}' no encontrado en {directorio}"

def tool_calcular(expresion: str) -> str:
    """Evalúa una expresión matemática."""
    expresion = expresion.replace("^", "**")
    if not re.match(r'^[\d\s\+\-\*\/\.\(\)eE]+$', expresion): return "❌ Solo números y operadores"
    try: return str(eval(expresion, {"__builtins__": {}}, {}))
    except Exception as e: return f"❌ Error: {e}"

def tool_buscar(consulta: str) -> str:
    """Busca en internet con DuckDuckGo."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs: results = list(ddgs.text(consulta, max_results=5))
        if not results: return "🔍 Sin resultados"
        return "\n\n".join([f"📌 {r.get('title','')}\n   {r.get('body','')}\n   🔗 {r.get('href','')}" for r in results])
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs: results = list(ddgs.text(consulta, max_results=5))
            if not results: return "🔍 Sin resultados"
            return "\n\n".join([f"📌 {r.get('title','')}\n   {r.get('body','')}\n   🔗 {r.get('href','')}" for r in results])
        except: return "❌ pip install ddgs"
    except Exception as e: return f"❌ Error: {e}"

def tool_consultar_experto(pregunta: str, modo: str = "general") -> str:
    """Consulta con IA avanzada en la nube."""
    return consultar_experto(pregunta, modo=modo)

def tool_consultar_plan(tarea: str, contexto: str = "") -> str:
    """Pide un plan de implementación a la IA avanzada."""
    return consultar_experto(tarea, contexto=contexto, modo="plan")

def tool_info_sistema() -> str:
    """Información del sistema."""
    info = [f"🖥️ {platform.system()} {platform.release()}", f"💻 {platform.processor()}",
            f"📂 Proyectos: {PROJECTS_DIR}", f"📂 Descargas: {DOWNLOADS_DIR}"]
    try:
        for d in ['C:', 'D:']:
            if os.path.exists(d + '\\'):
                u = shutil.disk_usage(d + '\\')
                info.append(f"💾 {d}: {u.free//(1024**3)}GB libres de {u.total//(1024**3)}GB")
    except: pass
    try:
        import psutil; m = psutil.virtual_memory()
        info.append(f"🧠 RAM: {m.available//(1024**3)}GB de {m.total//(1024**3)}GB")
    except: pass
    return "\n".join(info)

# =====================================================================
# MAPA DE FUNCIONES
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
# HERRAMIENTAS PARA OLLAMA (JSON Schema)
# =====================================================================

OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "clonar_repositorio",
            "description": "Clona un repositorio de GitHub. Descarga todo el código a la carpeta Projects del usuario. Esta es la herramienta que debes usar SIEMPRE que el usuario quiera descargar o clonar un repositorio de GitHub.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL del repositorio de GitHub, ej: https://github.com/usuario/repo.git"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ejecutar_comando",
            "description": "Ejecuta un comando del sistema operativo. Úsalo para git, npm, pip, python, dir, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comando": {"type": "string", "description": "Comando a ejecutar"},
                    "directorio": {"type": "string", "description": "Directorio donde ejecutar (opcional)"}
                },
                "required": ["comando"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "instalar_dependencias",
            "description": "Instala las dependencias de un proyecto (npm install o pip install).",
            "parameters": {
                "type": "object",
                "properties": {
                    "directorio": {"type": "string", "description": "Ruta del proyecto"},
                    "tipo": {"type": "string", "description": "npm o pip (se autodetecta si no se especifica)", "enum": ["npm", "pip"]}
                },
                "required": ["directorio"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_archivos",
            "description": "Lista archivos y carpetas de un directorio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del directorio"},
                    "profundidad": {"type": "integer", "description": "Profundidad (default 3)"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leer_archivo",
            "description": "Lee el contenido de un archivo.",
            "parameters": {
                "type": "object",
                "properties": {"ruta": {"type": "string", "description": "Ruta del archivo"}},
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escribir_archivo",
            "description": "Escribe contenido en un archivo. Backup automático.",
            "parameters": {
                "type": "object",
                "properties": {"ruta": {"type": "string", "description": "Ruta del archivo"}, "contenido": {"type": "string", "description": "Contenido a escribir"}},
                "required": ["ruta", "contenido"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "modificar_archivo",
            "description": "Modifica parte de un archivo (buscar y reemplazar).",
            "parameters": {
                "type": "object",
                "properties": {"ruta": {"type": "string"}, "texto_original": {"type": "string"}, "texto_nuevo": {"type": "string"}},
                "required": ["ruta", "texto_original", "texto_nuevo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_en_archivos",
            "description": "Busca texto dentro de archivos de un directorio.",
            "parameters": {
                "type": "object",
                "properties": {"directorio": {"type": "string"}, "texto": {"type": "string"}, "extension": {"type": "string"}},
                "required": ["directorio", "texto"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar",
            "description": "Busca información en internet.",
            "parameters": {
                "type": "object",
                "properties": {"consulta": {"type": "string", "description": "Consulta de búsqueda"}},
                "required": ["consulta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calcular",
            "description": "Calcula una expresión matemática.",
            "parameters": {
                "type": "object",
                "properties": {"expresion": {"type": "string"}},
                "required": ["expresion"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_experto",
            "description": "Consulta con IA avanzada en la nube para tareas complejas.",
            "parameters": {
                "type": "object",
                "properties": {"pregunta": {"type": "string"}, "modo": {"type": "string", "enum": ["general", "codigo", "analisis", "plan"]}},
                "required": ["pregunta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_plan",
            "description": "Pide un plan de implementación a la IA avanzada.",
            "parameters": {
                "type": "object",
                "properties": {"tarea": {"type": "string"}, "contexto": {"type": "string"}},
                "required": ["tarea"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "info_sistema",
            "description": "Muestra información del sistema.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    }
]

# =====================================================================
# DETECCIÓN DE INTENCIÓN + AUTO-EJECUCIÓN
# Esta es la solución principal: NO dependemos del modelo para
# acciones críticas. Si el usuario menciona un GitHub URL, 
# EJECUTAMOS DIRECTAMENTE.
# =====================================================================

def detect_intent_actions(user_message):
    """Detecta intenciones claras y devuelve acciones a ejecutar directamente."""
    msg = user_message.lower()
    actions = []
    
    # Detectar GitHub URL + intención de clonar/descargar
    github_match = re.search(r'https://github\.com/[\w.-]+/[\w.-]+', user_message)
    if github_match:
        url = github_match.group(0)
        if not url.endswith(".git"):
            url += ".git"
        clone_keywords = ["clona", "descargar", "descarga", "baja", "download", "github", "repo", "repositorio"]
        if any(k in msg for k in clone_keywords):
            actions.append({
                "tool": "clonar_repositorio",
                "args": {"url": url},
                "reason": "🔗 GitHub URL detectada + intención de clonar"
            })
    
    # Detectar "instalar dependencias" con proyecto activo
    if any(k in msg for k in ["instal", "dependencia", "npm install"]):
        project = st.session_state.get('active_project', '')
        if project and os.path.exists(project):
            actions.append({
                "tool": "instalar_dependencias",
                "args": {"directorio": project},
                "reason": "📦 Intención de instalar + proyecto activo"
            })
    
    # Detectar "analizar proyecto" con proyecto activo
    if any(k in msg for k in ["analiz", "revis", "estructura"]) and not github_match:
        project = st.session_state.get('active_project', '')
        if project and os.path.exists(project):
            actions.append({
                "tool": "listar_archivos",
                "args": {"ruta": project, "profundidad": 3},
                "reason": "🔍 Intención de análisis + proyecto activo"
            })
    
    return actions

def execute_action(action, container):
    """Ejecuta una acción directa y muestra el resultado."""
    with container:
        fn = AVAILABLE_FUNCTIONS.get(action["tool"])
        if fn:
            st.markdown(f'<div class="tool-auto">⚡ AUTO-EJECUCIÓN: {action["reason"]}<br>🔧 {action["tool"]}({", ".join(f"{k}={str(v)[:40]}" for k,v in action["args"].items())})</div>', unsafe_allow_html=True)
            try:
                result = fn(**action["args"])
            except Exception as e:
                result = f"❌ Error: {e}"
            st.markdown(f'<div class="tool-result">{str(result)[:800]}</div>', unsafe_allow_html=True)
            return result
    return "❌ Función no encontrada"

# =====================================================================
# AGENTE PRINCIPAL
# =====================================================================

SYSTEM_MSG = f"""Eres un agente que EJECUTA acciones reales. Tienes herramientas para ejecutar comandos, clonar repositorios, leer/escribir archivos, etc.
CUANDO el usuario quiera descargar un repositorio de GitHub, usa clonar_repositorio.
CUANDO el usuario quiera instalar dependencias, usa instalar_dependencias.
CUANDO el usuario quiera analizar un proyecto, usa listar_archivos y leer_archivo.
NUNCA le digas al usuario que abra una terminal. TÚ ejecutas las herramientas.
Responde en español.
Proyectos: {PROJECTS_DIR}
Descargas: {DOWNLOADS_DIR}"""

def run_agent(user_message, history=[]):
    """Agente con auto-ejecución forzada + tool calling nativo"""
    
    # === PASO 0: AUTO-EJECUCIÓN - Acciones críticas detectadas ===
    auto_actions = detect_intent_actions(user_message)
    auto_results = []
    
    if auto_actions:
        container = st.container()
        for action in auto_actions:
            result = execute_action(action, container)
            auto_results.append({"tool": action["tool"], "args": action["args"], "result": result})
            
            # Si clonamos un repo, actualizar proyecto activo
            if action["tool"] == "clonar_repositorio" and "✅" in str(result):
                # Extraer ruta del resultado
                match = re.search(r'Clonado en: (.+)', str(result))
                if match:
                    project_path = match.group(1).strip()
                    st.session_state['active_project'] = project_path
    
    # === PASO 1: Llamar a Ollama con tools ===
    messages = [{"role": "system", "content": SYSTEM_MSG}]
    for msg in history[-10:]:
        messages.append(msg)
    
    # Agregar resultados de auto-ejecución al contexto
    if auto_results:
        context = "Ya ejecuté estas acciones automáticamente:\n\n"
        for r in auto_results:
            context += f"- {r['tool']}({r['args']}): {str(r['result'])[:500]}\n"
        context += "\nAhora necesito dar una respuesta al usuario basándome en estos resultados. Si faltan acciones, debo llamar más herramientas."
        messages.append({"role": "assistant", "content": context})
    
    messages.append({"role": "user", "content": user_message})
    
    results = list(auto_results)  # Empezar con resultados de auto-ejecución
    tool_container = st.container()
    
    try:
        response = ollama.chat(model=AGENT_MODEL, messages=messages, tools=OLLAMA_TOOLS)
    except Exception as e:
        # Si falla tool calling, generar respuesta con los resultados que tenemos
        if results:
            summary = "Resultados:\n\n"
            for r in results:
                summary += f"- {r['tool']}: {str(r['result'])[:300]}\n"
            try:
                final = ollama.chat(model=AGENT_MODEL, messages=[
                    {"role": "system", "content": "Responde en español basándote en estos resultados. Explica lo que se hizo."},
                    {"role": "user", "content": f"Tarea: {user_message}\n\n{summary}"}
                ])
                return final.message.content, history + [{"role": "user", "content": user_message}, {"role": "assistant", "content": final.message.content}]
            except:
                return summary, history + [{"role": "user", "content": user_message}, {"role": "assistant", "content": summary}]
        return f"❌ Error: {e}", []
    
    # === PASO 2: Loop de tool calling ===
    max_iter = 5
    for iteration in range(max_iter):
        if not response.message.tool_calls:
            break
        
        messages.append(response.message)
        
        for tool_call in response.message.tool_calls:
            fn_name = tool_call.function.name
            fn_args = tool_call.function.arguments
            
            with tool_container:
                icon = "☁️" if fn_name.startswith("consultar") else "🔧"
                args_preview = ", ".join(f"{k}={str(v)[:40]}" for k, v in fn_args.items())
                st.markdown(f'<div class="tool-cmd">{icon} {fn_name}({args_preview})</div>', unsafe_allow_html=True)
                
                fn = AVAILABLE_FUNCTIONS.get(fn_name)
                if fn:
                    try: result = fn(**fn_args)
                    except Exception as e: result = f"❌ Error: {e}"
                else:
                    result = f"❌ Función no encontrada: {fn_name}"
                
                results.append({"tool": fn_name, "args": fn_args, "result": result})
                st.markdown(f'<div class="tool-result">{str(result)[:800]}</div>', unsafe_allow_html=True)
            
            messages.append({"role": "tool", "content": str(result)})
        
        try:
            response = ollama.chat(model=AGENT_MODEL, messages=messages, tools=OLLAMA_TOOLS)
        except:
            break
    
    # === PASO 3: Respuesta final ===
    final_text = ""
    if response.message.content:
        final_text = response.message.content
    elif results:
        summary = "Acciones ejecutadas:\n\n"
        for r in results:
            summary += f"- {r['tool']}: {str(r['result'])[:300]}\n"
        try:
            final = ollama.chat(model=AGENT_MODEL, messages=[
                {"role": "system", "content": "Responde en español. Explica qué se hizo y los resultados. NUNCA des instrucciones de terminal."},
                {"role": "user", "content": f"Tarea: {user_message}\n\n{summary}"}
            ])
            final_text = final.message.content
        except:
            final_text = summary
    else:
        final_text = "No se pudo completar la tarea."
    
    new_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": final_text}
    ]
    return final_text, new_history

# =====================================================================
# CHAT / RAG / CÓDIGO (iguales que antes)
# =====================================================================

def chat_simple(message, history=[]):
    messages = [{"role": "system", "content": "Asistente útil. Español."}] + history[-10:] + [{"role": "user", "content": message}]
    try:
        r = ollama.chat(model=CHAT_MODEL, messages=messages)
        return r.message.content
    except Exception as e: return f"❌ {e}"

def init_chroma():
    try:
        import chromadb
        client = chromadb.PersistentClient(path=os.path.join(USER_HOME, ".ia-chromadb"))
        return client, client.get_or_create_collection("documentos")
    except Exception as e: st.error(f"ChromaDB: {e}"); return None, None

def rag_query(question, collection):
    try:
        emb = ollama.embeddings(model="nomic-embed-text", prompt=question)["embedding"]
        results = collection.query(query_embeddings=[emb], n_results=5)
        if not results["documents"][0]: return "Sin resultados."
        ctx = "\n\n".join(results["documents"][0])
        r = ollama.chat(model=CHAT_MODEL, messages=[{"role": "system", "content": f"Contexto:\n{ctx}\nEspañol."}, {"role": "user", "content": question}])
        return r.message.content
    except Exception as e: return f"❌ {e}"

def code_assistant(message, mode="explicar"):
    prompts = {"explicar": "Explica:", "mejorar": "Mejora:", "corregir": "Corrige:", "crear": "Crea:"}
    config = load_bridge_config()
    if config.get("api_key"): return consultar_experto(message, modo="codigo")
    try:
        r = ollama.chat(model=CODE_MODEL, messages=[{"role": "system", "content": "Programador experto. Español."}, {"role": "user", "content": f"{prompts.get(mode, 'Explica:')}\n\n{message}"}])
        return r.message.content
    except Exception as e: return f"❌ {e}"

# =====================================================================
# INTERFAZ
# =====================================================================

def render_bridge():
    st.subheader("☁️ IA Bridge")
    config = load_bridge_config()
    nombres = {k: v["nombre"] for k, v in PROVEEDORES.items()}
    sel = st.selectbox("Proveedor", list(nombres.keys()), format_func=lambda x: nombres[x],
        index=list(nombres.keys()).index(config.get("proveedor", "groq")))
    config["proveedor"] = sel
    prov = PROVEEDORES[sel]
    if prov["gratis"]: st.success("🆓 Gratis")
    else: st.info("💰 Pago")
    api_key = st.text_input("API Key", config.get("api_key", ""), type="password")
    config["api_key"] = api_key
    st.markdown(f"🔑 [Obtener Key]({prov['como_obtener_key']})")
    modelos = prov["modelos"]
    md = config.get("modelo") or prov["modelo_default"]
    mi = modelos.index(md) if md in modelos else 0
    config["modelo"] = st.selectbox("Modelo", modelos, index=mi)
    with st.expander("📝 Contexto"):
        config["contexto_proyecto"] = st.text_area("Proyecto", config.get("contexto_proyecto", ""), height=80)
    if st.button("💾 Guardar"): save_bridge_config(config); st.success("✅")
    if st.button("🔌 Probar"):
        if not api_key: st.error("Sin key")
        else:
            ok, msg = test_bridge()
            st.success(msg) if ok else st.error(msg)
    st.divider()
    st.success(f"☁️ {prov['nombre']} ✅") if api_key else st.warning("☁️ Sin configurar")

def main():
    with st.sidebar:
        st.title("🤖 IA Local Pro v4")
        st.caption("Auto-ejecución + Tool Calling")
        mode = st.radio("Modo", ["🚀 Agente Autónomo", "💬 Chat", "📚 RAG", "💻 Código"], index=0)
        st.divider()
        st.subheader("⚙️ Config")
        global AGENT_MODEL
        AGENT_MODEL = st.selectbox("Agente", ["qwen2.5:14b", "qwen2.5:7b", "llama3.1:8b"], index=0)
        st.divider()
        render_bridge()
        st.divider()
        st.subheader("📁 Proyectos")
        if os.path.exists(PROJECTS_DIR):
            proyectos = [d for d in os.listdir(PROJECTS_DIR) if os.path.isdir(os.path.join(PROJECTS_DIR, d))]
            if proyectos:
                sp = st.selectbox("Activo", proyectos)
                st.session_state['active_project'] = os.path.join(PROJECTS_DIR, sp)
        st.divider()
        if st.button("📊 Sistema"): st.text(tool_info_sistema())
        if st.button("🗑️ Limpiar"): st.session_state['history'] = []; st.rerun()

    if "🚀" in mode: render_agent()
    elif "💬" in mode: render_chat()
    elif "📚" in mode: render_rag()
    elif "💻" in mode: render_code()

def render_agent():
    st.title("🚀 Agente Autónomo v4")
    st.caption("Auto-ejecución forzada — Si detecta GitHub URL, clona directamente")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📥 Clonar signalTrade"):
            st.session_state['quick_task'] = "Clona https://github.com/yecos/signalTrade.git y analízalo"
    with col2:
        if st.button("📦 Instalar"):
            p = st.session_state.get('active_project', '')
            if p and os.path.exists(p): st.session_state['quick_task'] = f"Instala dependencias en {p}"
    with col3:
        if st.button("🔍 Analizar"):
            p = st.session_state.get('active_project', '')
            if p and os.path.exists(p): st.session_state['quick_task'] = f"Analiza {p}. Lee package.json y README."
    
    if 'history' not in st.session_state: st.session_state['history'] = []
    for msg in st.session_state['history']:
        st.chat_message(msg["role"]).write(msg["content"])
    
    qt = st.session_state.pop('quick_task', None)
    prompt = st.chat_input("¿Qué quieres que haga?")
    ui = qt or prompt
    if ui:
        st.chat_message("user").write(ui)
        with st.chat_message("assistant"):
            with st.spinner("🤖 Ejecutando..."):
                resp, hist = run_agent(ui, st.session_state['history'])
                st.session_state['history'] = hist
                st.markdown(resp)

def render_chat():
    st.title("💬 Chat")
    if 'ch' not in st.session_state: st.session_state['ch'] = []
    for m in st.session_state['ch']: st.chat_message(m["role"]).write(m["content"])
    p = st.chat_input("Mensaje...")
    if p:
        st.chat_message("user").write(p)
        with st.chat_message("assistant"):
            r = chat_simple(p, st.session_state['ch'])
            st.markdown(r)
        st.session_state['ch'].extend([{"role": "user", "content": p}, {"role": "assistant", "content": r}])

def render_rag():
    st.title("📚 RAG")
    _, col = init_chroma()
    if col:
        up = st.file_uploader("Subir", type=["pdf", "txt", "md"])
        if up:
            with st.spinner("Procesando..."):
                txt = ""
                if up.name.endswith(".pdf"):
                    try:
                        import pypdf
                        for pg in pypdf.PdfReader(up).pages: txt += pg.extract_text() or ""
                    except: st.error("pip install pypdf")
                else: txt = up.getvalue().decode("utf-8", errors="replace")
                if txt:
                    try:
                        chunks = [txt[i:i+500] for i in range(0, len(txt), 500)]
                        for i, ch in enumerate(chunks):
                            emb = ollama.embeddings(model="nomic-embed-text", prompt=ch)["embedding"]
                            col.add(ids=[f"{up.name}_{i}"], embeddings=[emb], documents=[ch])
                        st.success(f"✅ {up.name} ({len(chunks)} fragmentos)")
                    except Exception as e: st.error(e)
        if 'rh' not in st.session_state: st.session_state['rh'] = []
        for m in st.session_state['rh']: st.chat_message(m["role"]).write(m["content"])
        p = st.chat_input("Pregunta...")
        if p:
            st.chat_message("user").write(p)
            with st.chat_message("assistant"):
                r = rag_query(p, col); st.markdown(r)
            st.session_state['rh'].extend([{"role": "user", "content": p}, {"role": "assistant", "content": r}])

def render_code():
    st.title("💻 Código")
    mode = st.selectbox("Modo", ["explicar", "mejorar", "corregir", "crear"])
    if 'coh' not in st.session_state: st.session_state['coh'] = []
    for m in st.session_state['coh']: st.chat_message(m["role"]).write(m["content"])
    p = st.chat_input("Código...")
    if p:
        st.chat_message("user").write(p)
        with st.chat_message("assistant"):
            r = code_assistant(p, mode); st.markdown(r)
        st.session_state['coh'].extend([{"role": "user", "content": p}, {"role": "assistant", "content": r}])

if __name__ == "__main__":
    main()
