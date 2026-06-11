"""
=============================================================
AGENTE LOCAL AUTONOMO v13 - ReAct + Triple Memoria + URL Tools
Piensa → Actua → Observa → Piensa de nuevo → Repite
=============================================================

FASE 2 - TRIPLE MEMORIA:
  1. Memoria Corto Plazo: Conversacion actual (ventana deslizante)
  2. Memoria Largo Plazo: Conocimiento persistente con busqueda semantica
     Usa embeddings de Ollama (sin dependencias extras)
  3. Memoria de Trabajo: Estado de la tarea actual, scratchpad

v13 MEJORAS vs v12:
  - Herramienta abrir_url: abre paginas web y sitios conocidos
  - Herramienta buscar_youtube: busca videos en YouTube
  - abrir_aplicacion detecta sitios web y redirige a abrir_url
  - _llm_generate con logging de errores y diagnostico
  - _detect_tool_calling_support con heuristica rapida por nombre
  - Timeout adaptativo para modelos grandes (14b+)
  - 30+ sitios web reconocidos automaticamente

SIN DEPENDENCIAS EXTRAS:
  - Embeddings via Ollama /api/embeddings (ya lo tienes)
  - Vector store casero con numpy (o math puro si numpy no esta)
  - Persistencia en JSON + archivos binarios
=============================================================
"""

import streamlit as st
import subprocess
import os
import re
import json
import platform
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from collections import OrderedDict

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.expanduser("~"), ".ia-local", "learning", "agent.log"), encoding="utf-8"),
    ]
)
logger = logging.getLogger("agente")

# ============================================================
# CONFIGURACION
# ============================================================

# MODELOS: Se detectan automaticamente al iniciar.
# Si tienes qwen3 → tool calling nativo (mejor)
# Si tienes qwen2.5 → JSON fallback (funciona igual)
# NO necesitas cambiar nada aqui, se auto-detecta.
PREFERRED_MODELS = ["qwen3:4b", "qwen3-coder", "qwen3:30b-a3b", "qwen2.5:14b", "llama3.1:8b"]
AGENT_MODEL = None  # Se detecta automaticamente al iniciar
FALLBACK_MODEL = None  # Tambien se detecta
CHAT_MODEL = None

# Se resolveran en _detect_best_model() al primer uso
_detected_model = None
_detected_models_list = []

MAX_REACT_ITERATIONS = 8        # Max vueltas del bucle ReAct
MAX_CONVERSATION_MEMORY = 20    # Mensajes de contexto que recuerda

if platform.system() == "Windows":
    REPOS_DIR = os.path.join(os.path.expanduser("~"), "Documents")
    LEARN_DIR = os.path.join(os.path.expanduser("~"), ".ia-local", "learning")
else:
    REPOS_DIR = os.path.join(os.path.expanduser("~"), "repos")
    LEARN_DIR = os.path.join(os.path.expanduser("~"), ".ia-local", "learning")

os.makedirs(REPOS_DIR, exist_ok=True)
os.makedirs(LEARN_DIR, exist_ok=True)

CORRECTIONS_FILE = os.path.join(LEARN_DIR, "corrections.json")
FEEDBACK_FILE = os.path.join(LEARN_DIR, "feedback.json")
PATTERNS_FILE = os.path.join(LEARN_DIR, "patterns.json")
KNOWLEDGE_FILE = os.path.join(LEARN_DIR, "knowledge.json")

# Comandos que NUNCA se ejecutan sin confirmacion
COMANDOS_PELIGROSOS = [
    "rm -rf", "del /f /s /q", "format", "fdisk",
    "reg delete", "net user", "shutdown", "rmdir /s /q",
    "mkfs", "dd if=", "> /dev/sd", "curl | bash", "curl | sh",
    "rd /s /q", "taskkill /f /pid system",
    "powershell -enc", "certutil", "bitsadmin", "mshta",
    "cipher /w", "diskpart", "reg add",
]

# Comandos permitidos sin confirmacion (allowlist)
COMANDOS_SEGUROS = [
    "git", "npm", "pip", "python", "node", "dir", "ls",
    "cat", "echo", "cd", "type", "find", "where", "which",
    "tasklist", "start", "open", "xdg-open",
    "pipenv", "poetry", "bun", "yarn", "cargo",
    "docker ps", "docker images", "docker compose",
]

# Sitios web conocidos (centralizado)
SITIOS_CONOCIDOS = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "reddit": "https://www.reddit.com",
    "whatsapp web": "https://web.whatsapp.com",
    "whatsappweb": "https://web.whatsapp.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "twitch": "https://www.twitch.tv",
    "amazon": "https://www.amazon.com",
    "wikipedia": "https://es.wikipedia.org",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "translate": "https://translate.google.com",
    "google translate": "https://translate.google.com",
    "chatgpt": "https://chat.openai.com",
    "copilot": "https://copilot.microsoft.com",
    "outlook": "https://outlook.live.com",
    "notion": "https://www.notion.so",
    "figma": "https://www.figma.com",
    "canva": "https://www.canva.com",
    "trello": "https://trello.com",
}

# ============================================================
# UTILIDADES COMPARTIDAS
# ============================================================

def _strip_prefixes(text: str) -> str:
    """Elimina prefijos comunes de comandos de voz/texto."""
    text = text.strip()
    prefixes = ["abre ", "abrir ", "open ", "inicia ", "lanza ", "mi ",
                "ve a ", "ir a ", "navega a ", "busca ", "buscar ",
                "pon ", "ponme ", "reproduce "]
    for prefix in prefixes:
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    return text.strip()


def _open_in_browser(url: str) -> str:
    """Abre una URL en el navegador por defecto. Multi-plataforma."""
    if platform.system() == "Windows":
        return ejecutar_comando(f'start "" "{url}"')
    elif platform.system() == "Darwin":
        return ejecutar_comando(f'open "{url}"')
    else:
        return ejecutar_comando(f'xdg-open "{url}"')


def _validate_path(ruta: str) -> str:
    """Valida que una ruta este dentro de directorios permitidos. Previene path traversal."""
    allowed_dirs = [REPOS_DIR, LEARN_DIR]
    try:
        resolved = Path(ruta).resolve()
        for allowed in allowed_dirs:
            if str(resolved).startswith(str(Path(allowed).resolve())):
                return ruta  # Ruta segura
        # Tambien permitir rutas relativas dentro de REPOS_DIR
        if not os.path.isabs(ruta):
            resolved_in_repos = Path(os.path.join(REPOS_DIR, ruta)).resolve()
            if str(resolved_in_repos).startswith(str(Path(REPOS_DIR).resolve())):
                return ruta
    except (OSError, ValueError):
        pass
    # Ruta fuera de directorios permitidos - requerir confirmacion
    return f"ACCESO DENEGADO: La ruta '{ruta}' esta fuera de los directorios permitidos. Solo puedes acceder a archivos dentro de {REPOS_DIR}"


def _sanitize_input(text: str) -> str:
    """Sanitiza un input para prevenir inyeccion de comandos."""
    # Solo permitir caracteres alfanumericos, espacios, puntos, guiones y barras
    if not re.match(r'^[a-zA-Z0-9\s\.\-_:/\\@]+$', text):
        # Filtrar caracteres peligrosos
        text = re.sub(r'[`$\{\}();|&<>!#~]', '', text)
    return text


# ============================================================
# HERRAMIENTAS - Funciones que EJECUTAN de verdad
# ============================================================

def ejecutar_comando(comando: str, cwd: str = None, confirmar_peligroso: bool = False) -> str:
    """Ejecuta un comando en la terminal con VALIDACION de seguridad."""
    cmd_lower = comando.lower()

    # Validar comandos peligrosos (blocklist)
    for peligro in COMANDOS_PELIGROSOS:
        if peligro in cmd_lower:
            if not confirmar_peligroso:
                logger.warning(f"Comando peligroso bloqueado: {comando}")
                return (f"COMANDO PELIGROSO detectado: '{peligro}'\n"
                        f"Si estas seguro, dime: 'ejecuta confirmado: {comando}'")

    # Timeout adaptativo
    timeout = 120
    if any(w in cmd_lower for w in ["install", "build", "compile", "docker", "pull"]):
        timeout = 300

    try:
        result = subprocess.run(
            comando, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd or REPOS_DIR
        )
        output = ""
        if result.stdout:
            output += result.stdout.strip()
        if result.stderr:
            stderr = result.stderr.strip()
            if stderr and "npm notice" not in stderr.lower():
                output += ("\n[STDERR] " + stderr) if output else stderr
        if not output:
            output = "(sin salida)"
        return output
    except subprocess.TimeoutExpired:
        return f"ERROR_TIMEOUT: Comando cancelado (>{timeout}s)"
    except Exception as e:
        return f"ERROR: {e}"


def clonar_repositorio(url: str) -> str:
    repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
    target_dir = os.path.join(REPOS_DIR, repo_name)

    if os.path.exists(target_dir):
        git_dir = os.path.join(target_dir, ".git")
        contenido = os.listdir(target_dir) if os.path.isdir(target_dir) else []
        archivos_reales = [f for f in contenido if f != ".git"]
        if os.path.exists(git_dir) and len(archivos_reales) > 1:
            return f"Ya existe en: {target_dir}"
        else:
            import shutil
            try:
                shutil.rmtree(target_dir)
            except Exception as e:
                return f"Carpeta vacia, no se pudo borrar: {e}"

    resultado = ejecutar_comando(f'git clone {url} "{target_dir}"')
    if os.path.exists(target_dir) and len(os.listdir(target_dir)) > 1:
        return f"CLONADO OK en: {target_dir}"
    return f"ERROR al clonar:\n{resultado}"


def instalar_dependencias(ruta: str, gestor: str = "auto") -> str:
    if not os.path.exists(ruta):
        return f"Ruta no existe: {ruta}"

    if gestor == "auto":
        if os.path.exists(os.path.join(ruta, "package.json")):
            gestor = "npm"
        elif os.path.exists(os.path.join(ruta, "requirements.txt")):
            gestor = "pip"
        elif os.path.exists(os.path.join(ruta, "pyproject.toml")):
            gestor = "poetry"
        else:
            return "No se detecto gestor de paquetes"

    comandos = {
        "npm": f'cd "{ruta}" && npm install',
        "pip": f'cd "{ruta}" && pip install -r requirements.txt',
        "poetry": f'cd "{ruta}" && poetry install',
        "bun": f'cd "{ruta}" && bun install',
    }
    return ejecutar_comando(comandos.get(gestor, f'cd "{ruta}" && {gestor} install'))


def leer_archivo(ruta: str) -> str:
    # Validar path traversal
    validation = _validate_path(ruta)
    if validation != ruta:
        return validation  # Retorna mensaje de ACCESO DENEGADO

    rutas_posibles = [ruta]
    if not os.path.isabs(ruta):
        rutas_posibles.append(os.path.join(REPOS_DIR, ruta))
        try:
            for d in os.listdir(REPOS_DIR):
                rutas_posibles.append(os.path.join(REPOS_DIR, d, ruta))
        except OSError:
            pass

    for r in rutas_posibles:
        if os.path.exists(r) and os.path.isfile(r):
            try:
                with open(r, "r", encoding="utf-8", errors="replace") as f:
                    contenido = f.read()
                if len(contenido) > 8000:
                    contenido = contenido[:8000] + "\n... [truncado]"
                return contenido
            except (OSError, UnicodeDecodeError) as e:
                return f"ERROR leyendo: {e}"
    return f"Archivo no encontrado: {ruta}"


def listar_archivos(ruta: str = None) -> str:
    if ruta is None:
        ruta = REPOS_DIR
    if not os.path.exists(ruta):
        alt = os.path.join(REPOS_DIR, ruta) if not os.path.isabs(ruta) else ruta
        if os.path.exists(alt):
            ruta = alt
        else:
            return f"Directorio no existe: {ruta}"
    try:
        items = os.listdir(ruta)
        carpetas = sorted([f for f in items if os.path.isdir(os.path.join(ruta, f))])
        archivos = sorted([f for f in items if os.path.isfile(os.path.join(ruta, f))])
        resultado = f"Contenido de {ruta}:\n"
        for c in carpetas:
            resultado += f"  [CARPETA] {c}\n"
        for a in archivos:
            resultado += f"  [ARCHIVO] {a}\n"
        resultado += f"Total: {len(carpetas)} carpetas, {len(archivos)} archivos"
        return resultado
    except OSError as e:
        return f"ERROR: {e}"


def escribir_archivo(ruta: str, contenido: str) -> str:
    # Validar path traversal
    validation = _validate_path(ruta)
    if validation != ruta:
        return validation  # Retorna mensaje de ACCESO DENEGADO

    try:
        dir_name = os.path.dirname(ruta)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        return f"Archivo escrito: {ruta}"
    except OSError as e:
        return f"ERROR: {e}"


def analizar_proyecto(ruta: str) -> str:
    if not os.path.exists(ruta):
        alt = os.path.join(REPOS_DIR, ruta) if not os.path.isabs(ruta) else ruta
        if os.path.exists(alt):
            ruta = alt
        else:
            return f"Directorio no existe: {ruta}"

    resultado = f"Analisis de: {ruta}\n" + "=" * 40 + "\n\n"

    for root, dirs, files in os.walk(ruta):
        level = root.replace(ruta, "").count(os.sep)
        if level > 3:
            dirs.clear()
            continue
        indent = "  " * level
        resultado += f"{indent}{os.path.basename(root)}/\n"
        subindent = "  " * (level + 1)
        for f in sorted(files)[:20]:
            resultado += f"{subindent}{f}\n"
        if len(files) > 20:
            resultado += f"{subindent}... y {len(files) - 20} mas\n"

    resultado += "\nDeteccion:\n"
    checks = {
        "package.json": "Node.js", "tsconfig.json": "TypeScript",
        "next.config.js": "Next.js", "next.config.ts": "Next.js",
        "requirements.txt": "Python", "Dockerfile": "Docker",
        ".git": "Git", "README.md": "README",
    }
    for fname, desc in checks.items():
        if os.path.exists(os.path.join(ruta, fname)):
            resultado += f"  - {desc} ({fname})\n"

    return resultado


# ============================================================
# HERRAMIENTAS NUEVAS v11
# ============================================================

def buscar_en_archivos(ruta: str, patron: str) -> str:
    """Busca texto dentro de archivos (como grep/findstr)."""
    if platform.system() == "Windows":
        return ejecutar_comando(f'findstr /s /i /n "{patron}" "{ruta}\\*"')
    else:
        return ejecutar_comando(f'grep -rn "{patron}" "{ruta}" --include="*.py" --include="*.js" --include="*.html" --include="*.ts" --include="*.json" 2>/dev/null | head -50')


def procesos_activos(filtro: str = "") -> str:
    """Lista procesos corriendo. Opcionalmente filtra por nombre."""
    if platform.system() == "Windows":
        cmd = 'tasklist /fo csv'
        if filtro:
            cmd += f' | findstr /i "{filtro}"'
    else:
        cmd = 'ps aux'
        if filtro:
            cmd += f' | grep -i "{filtro}"'
    result = ejecutar_comando(cmd)
    if len(result) > 3000:
        result = result[:3000] + "\n... [truncado]"
    return result


def matar_proceso(pid_o_nombre: str) -> str:
    """Termina un proceso por PID o nombre."""
    if platform.system() == "Windows":
        # Intentar como PID primero
        if pid_o_nombre.isdigit():
            return ejecutar_comando(f"taskkill /pid {pid_o_nombre} /f")
        else:
            return ejecutar_comando(f'taskkill /f /im "{pid_o_nombre}"')
    else:
        if pid_o_nombre.isdigit():
            return ejecutar_comando(f"kill -9 {pid_o_nombre}")
        else:
            return ejecutar_comando(f"pkill -f {pid_o_nombre}")


def buscar_web(consulta: str) -> str:
    """Busca en internet usando DuckDuckGo API."""
    try:
        import urllib.request
        import urllib.parse
        encoded = urllib.parse.quote(consulta)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []
        if data.get("AbstractText"):
            results.append(f"Resumen: {data['AbstractText']}")
        if data.get("Answer"):
            results.append(f"Respuesta: {data['Answer']}")
        for r in data.get("RelatedTopics", [])[:5]:
            if isinstance(r, dict) and r.get("Text"):
                results.append(f"- {r['Text']}")

        if results:
            return "\n".join(results)
        return "No se encontraron resultados. Intenta con otra consulta."
    except Exception as e:
        return f"ERROR en busqueda web: {e}"


# ============================================================
# BUSQUEDA INTELIGENTE DE APLICACIONES
# ============================================================

def buscar_en_start_menu(nombre: str) -> str:
    nombre_lower = _strip_prefixes(nombre).lower()

    start_menu_dirs = []
    if platform.system() == "Windows":
        start_menu_dirs.append(os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"),
                                            "Microsoft", "Windows", "Start Menu", "Programs"))
        start_menu_dirs.append(os.path.join(os.environ.get("AppData", ""),
                                            "Microsoft", "Windows", "Start Menu", "Programs"))

    matches = []
    for sm_dir in start_menu_dirs:
        if not os.path.exists(sm_dir):
            continue
        for root, dirs, files in os.walk(sm_dir):
            for f in files:
                f_lower = f.lower()
                if f_lower.endswith(".lnk"):
                    name_no_ext = f_lower[:-4]
                    if nombre_lower in name_no_ext or name_no_ext in nombre_lower:
                        matches.append((os.path.join(root, f), name_no_ext))

    if not matches:
        return ""

    for path, name in matches:
        if nombre_lower == name:
            return path
    return matches[0][0]


# Cache para buscar_exe (evita escaneo de disco repetido)
_exe_cache = {}
_exe_cache_time = {}

def buscar_exe(nombre: str) -> str:
    nombre_lower = _strip_prefixes(nombre).lower()

    # Cache con TTL de 5 minutos
    import time
    cache_key = nombre_lower
    if cache_key in _exe_cache:
        cached_time = _exe_cache_time.get(cache_key, 0)
        if time.time() - cached_time < 300:  # 5 minutos
            return _exe_cache[cache_key]

    shortcut = buscar_en_start_menu(nombre)
    if shortcut:
        _exe_cache[cache_key] = shortcut
        _exe_cache_time[cache_key] = time.time()
        return shortcut

    # Sanitizar nombre para prevenir inyeccion
    if not re.match(r'^[a-zA-Z0-9\s\.\-_]+$', nombre_lower):
        logger.warning(f"Nombre de app rechazado por caracteres invalidos: {nombre_lower}")
        return ""

    if platform.system() == "Windows":
        try:
            reg_cmd = (
                f'powershell -Command "'
                f'Get-ItemProperty \'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*\', '
                f'\'HKLM:\\SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*\', '
                f'\'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*\' '
                f'| Where-Object {{$_.DisplayName -like \'*{nombre}*\'}} '
                f'| Select-Object -ExpandProperty InstallLocation '
                f'| Select-Object -First 1"'
            )
            reg_result = ejecutar_comando(reg_cmd)
            if reg_result and reg_result != "(sin salida)" and "ERROR" not in reg_result:
                install_path = reg_result.strip().split('\n')[0].strip()
                if install_path and os.path.exists(install_path):
                    for root, dirs, files in os.walk(install_path):
                        level = root.replace(install_path, "").count(os.sep)
                        if level > 2:
                            dirs.clear()
                            continue
                        for f in files:
                            if f.lower().endswith(".exe") and nombre_lower in f.lower():
                                return os.path.join(root, f)
        except:
            pass

    if platform.system() == "Windows":
        search_dirs = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        ]
        for base_dir in search_dirs:
            if not os.path.exists(base_dir):
                continue
            where_cmd = f'where /r "{base_dir}" *{nombre_lower}*.exe'
            where_result = ejecutar_comando(where_cmd)
            if where_result and where_result != "(sin salida)" and "ERROR" not in where_result:
                exes = [line.strip() for line in where_result.split('\n')
                        if line.strip() and line.strip().endswith(".exe")]
                if exes:
                    return exes[0]

    return ""


def abrir_url(url: str) -> str:
    """Abre una URL en el navegador por defecto."""
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url_lower = _strip_prefixes(url).lower()
        if url_lower in SITIOS_CONOCIDOS:
            url = SITIOS_CONOCIDOS[url_lower]
        elif "." in url_lower:
            url = "https://" + url_lower
        else:
            return f"No puedo determinar la URL para '{url}'. Intenta con una URL completa como https://www.youtube.com"

    # Validar esquema de URL (solo http/https)
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https", ""):
        return f"Esquema de URL no permitido: {parsed.scheme}. Solo se permite http:// y https://"

    resultado = _open_in_browser(url)
    if not resultado or resultado == "(sin salida)" or "error" not in resultado.lower():
        return f"URL abierta en el navegador: {url}"
    return f"Error al abrir URL: {resultado}"


def abrir_aplicacion(app: str) -> str:
    app_clean = _strip_prefixes(app).lower()

    # Si parece una URL o sitio web, usar abrir_url en su lugar
    indicadores_url = ["http://", "https://", "www.", ".com", ".org", ".net", ".io"]
    if any(ind in app_clean for ind in indicadores_url):
        return abrir_url(app)

    if app_clean in SITIOS_CONOCIDOS:
        return abrir_url(app_clean)

    aliases = {
        "chrome": "google chrome", "vscode": "visual studio code",
        "autocad": "autocad", "revit": "revit",
        "whatsapp": "whatsapp", "telegram": "telegram desktop",
        "word": "word", "excel": "excel", "powerpoint": "powerpoint",
        "photoshop": "adobe photoshop", "illustrator": "adobe illustrator",
        "figma": "figma", "blender": "blender", "sketchup": "sketchup",
        "notepad": "notepad", "bloc de notas": "notepad",
    }
    search_name = aliases.get(app_clean, app_clean)

    shortcut_path = buscar_en_start_menu(search_name)
    if shortcut_path:
        resultado = ejecutar_comando(f'start "" "{shortcut_path}"')
        if not resultado or resultado == "(sin salida)":
            return f"Aplicacion {app} abierta (via Start Menu)"
        if "error" not in resultado.lower():
            return f"Aplicacion {app} abierta (via Start Menu)"

    exe_path = buscar_exe(search_name)
    if exe_path:
        resultado = ejecutar_comando(f'start "" "{exe_path}"')
        if not resultado or resultado == "(sin salida)":
            return f"Aplicacion {app} abierta (encontrada en: {exe_path})"
        if "error" not in resultado.lower():
            return f"Aplicacion {app} abierta (encontrada en: {exe_path})"

    resultado = ejecutar_comando(f"start {app_clean}")
    if not resultado or resultado == "(sin salida)":
        return f"Aplicacion {app} abierta"

    if "no se puede" in resultado.lower() or "no encuentra" in resultado.lower():
        return (f"No encontre '{app}' en tu computadora. "
                f"Puede que no este instalada o tenga otro nombre.")
    return resultado


def buscar_youtube(consulta: str) -> str:
    """Busca un video en YouTube y lo abre en el navegador."""
    import urllib.parse
    consulta_clean = _strip_prefixes(consulta)
    encoded = urllib.parse.quote(consulta_clean)
    url = f"https://www.youtube.com/results?search_query={encoded}"

    resultado = _open_in_browser(url)
    if not resultado or resultado == "(sin salida)" or "error" not in resultado.lower():
        return f"Buscando '{consulta_clean}' en YouTube. Deberia abrirse en tu navegador."
    return f"Abriendo YouTube con la busqueda: {consulta_clean}"


def generar_codigo(descripcion: str, tipo: str, ruta: str = "") -> str:
    """Genera codigo/texto completo usando el LLM y lo guarda en un archivo."""
    if not ruta:
        ext_map = {
            "html": ".html", "python": ".py", "javascript": ".js",
            "css": ".css", "json": ".json", "markdown": ".md", "texto": ".txt"
        }
        ext = ext_map.get(tipo, ".txt")
        safe_name = re.sub(r'[^a-z0-9]', '_', descripcion[:30].lower()).strip('_')
        ruta = os.path.join(REPOS_DIR, f"{safe_name}{ext}")
    else:
        ruta = ruta.replace("REPOS_DIR", REPOS_DIR)

    tipo_prompts = {
        "html": (
            "Eres un desarrollador web EXPERTO. Genera una pagina web HTML COMPLETA y FUNCIONAL.\n"
            "REGLAS:\n"
            "- TODO debe estar en un SOLO archivo HTML (HTML + CSS inline + JavaScript inline)\n"
            "- CSS moderno con gradientes, sombras, animaciones\n"
            "- JavaScript funcional, no pseudocodigo\n"
            "- Si es un juego: HTML5 Canvas, game loop, controles, colisiones, puntuacion\n"
            "- Si es una pagina: responsive, secciones completas\n"
            "- NO uses placeholders, TODO debe funcionar\n"
            "- Responde SOLO con el codigo HTML, sin explicaciones, sin markdown"
        ),
        "python": (
            "Eres un desarrollador Python EXPERTO. Genera un script COMPLETO y FUNCIONAL.\n"
            "- Codigo ejecutable directamente\n"
            "- Incluye imports, funciones, manejo de errores\n"
            "- Responde SOLO con el codigo Python, sin explicaciones"
        ),
        "javascript": (
            "Eres un desarrollador JavaScript EXPERTO. Genera codigo COMPLETO.\n"
            "- Codigo funcional y ejecutable\n"
            "- Responde SOLO con el codigo, sin explicaciones"
        ),
        "css": "Eres un disenador CSS EXPERTO. Responde SOLO con el codigo CSS.",
        "json": "Genera un JSON valido y bien estructurado. Responde SOLO con el JSON.",
        "markdown": "Genera un documento Markdown bien formateado. Responde SOLO con Markdown.",
    }

    system_prompt = tipo_prompts.get(tipo, "Genera contenido completo y funcional. Responde SOLO con el contenido.")

    # Usar _ask_llm via una instancia temporal
    contenido = _llm_generate([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Crea: {descripcion}"}
    ])

    if not contenido:
        return "ERROR: No se pudo generar contenido (Ollama no responde)"

    # Limpiar markdown code blocks
    contenido = contenido.strip()
    if contenido.startswith("```"):
        contenido = re.sub(r'^```[a-z]*\n?', '', contenido)
        contenido = re.sub(r'\n?```$', '', contenido)
        contenido = contenido.strip()

    resultado = escribir_archivo(ruta, contenido)
    if "ERROR" in resultado:
        return resultado

    # Si es HTML, abrir en navegador
    if tipo == "html" and platform.system() == "Windows":
        ejecutar_comando(f'start "" "{ruta}"')
        return f"Contenido generado y guardado en: {ruta}\nAbierto en el navegador automaticamente!"

    size_kb = len(contenido) / 1024
    return f"Contenido generado ({size_kb:.1f}KB) y guardado en: {ruta}"


# ============================================================
# DEFINICION DE HERRAMIENTAS PARA FUNCTION CALLING
# ============================================================

# Esquemas para function calling nativo de Ollama/qwen3
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "ejecutar_comando",
            "description": "Ejecuta un comando en la terminal. Peligrosos requieren confirmacion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comando": {"type": "string", "description": "Comando a ejecutar"},
                    "confirmar_peligroso": {"type": "boolean", "description": "True si el usuario confirmo un comando peligroso"}
                },
                "required": ["comando"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_aplicacion",
            "description": "Abre una aplicacion de escritorio por nombre. Busca automaticamente en Start Menu, registro y disco. NO usar para abrir paginas web o sitios como YouTube, Google, etc. Para eso usar abrir_url.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "Nombre de la aplicacion de escritorio (ej: whatsapp, chrome, autocad, vscode)"}
                },
                "required": ["app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_url",
            "description": "Abre una pagina web o sitio en el navegador. Usar cuando el usuario pide abrir sitios web como YouTube, Google, Gmail, Netflix, etc. Tambien acepta URLs completas. Reconoce nombres de sitios populares automaticamente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL o nombre del sitio web (ej: youtube, https://google.com, netflix)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_youtube",
            "description": "Busca un video en YouTube y abre los resultados en el navegador. Usar cuando el usuario quiere BUSCAR o VER algo en YouTube (no solo abrir la pagina principal).",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Que buscar en YouTube (ej: tutorial python, musica relax, receta pasta)"}
                },
                "required": ["consulta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generar_codigo",
            "description": "Genera codigo/texto COMPLETO usando el LLM y lo guarda en un archivo. Usar cuando el usuario pide CREAR algo: juegos, paginas web, scripts, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "descripcion": {"type": "string", "description": "Que crear (detallado)"},
                    "tipo": {"type": "string", "enum": ["html", "python", "javascript", "css", "json", "markdown", "texto"], "description": "Tipo de archivo"},
                    "ruta": {"type": "string", "description": "Ruta donde guardar (opcional, se genera automaticamente)"}
                },
                "required": ["descripcion", "tipo"]
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
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escribir_archivo",
            "description": "Crea o modifica un archivo con contenido especifico. Solo usar cuando ya tienes el contenido exacto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo"},
                    "contenido": {"type": "string", "description": "Contenido a escribir"}
                },
                "required": ["ruta", "contenido"]
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
                    "ruta": {"type": "string", "description": "Ruta del directorio (por defecto el directorio de trabajo)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analizar_proyecto",
            "description": "Analiza la estructura completa de un proyecto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del proyecto"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clonar_repositorio",
            "description": "Clona un repositorio de GitHub.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL del repositorio"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "instalar_dependencias",
            "description": "Instala dependencias de un proyecto. Detecta automaticamente npm/pip/poetry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del proyecto"},
                    "gestor": {"type": "string", "description": "Gestor de paquetes (auto/npm/pip/poetry)"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_en_archivos",
            "description": "Busca texto dentro de archivos (como grep/findstr).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Directorio donde buscar"},
                    "patron": {"type": "string", "description": "Texto o patron a buscar"}
                },
                "required": ["ruta", "patron"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "procesos_activos",
            "description": "Lista procesos corriendo. Opcionalmente filtra por nombre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filtro": {"type": "string", "description": "Filtro por nombre de proceso (opcional)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "matar_proceso",
            "description": "Termina un proceso por PID o nombre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid_o_nombre": {"type": "string", "description": "PID numerico o nombre del proceso"}
                },
                "required": ["pid_o_nombre"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_web",
            "description": "Busca en internet cuando no sabes algo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Consulta de busqueda"}
                },
                "required": ["consulta"]
            }
        }
    },
]

# Mapa de funciones para ejecucion rapida
TOOL_FUNCTIONS = {
    "ejecutar_comando": ejecutar_comando,
    "abrir_aplicacion": abrir_aplicacion,
    "abrir_url": abrir_url,
    "buscar_youtube": buscar_youtube,
    "generar_codigo": generar_codigo,
    "leer_archivo": leer_archivo,
    "escribir_archivo": escribir_archivo,
    "listar_archivos": listar_archivos,
    "analizar_proyecto": analizar_proyecto,
    "clonar_repositorio": clonar_repositorio,
    "instalar_dependencias": instalar_dependencias,
    "buscar_en_archivos": buscar_en_archivos,
    "procesos_activos": procesos_activos,
    "matar_proceso": matar_proceso,
    "buscar_web": buscar_web,
}


# ============================================================
# SISTEMA DE APRENDIZAJE
# ============================================================

class LearningSystem:
    @staticmethod
    def _load(filepath, default=None):
        if default is None: default = []
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return default

    @staticmethod
    def _save(filepath, data):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except:
            pass

    def save_knowledge(self, topic, content, source="experience"):
        knowledge = self._load(KNOWLEDGE_FILE, [])
        for k in knowledge:
            if k["topic"].lower() == topic.lower():
                k["content"] = content
                k["updated"] = datetime.now().isoformat()
                self._save(KNOWLEDGE_FILE, knowledge)
                return
        knowledge.append({"topic": topic, "content": content, "source": source,
                          "created": datetime.now().isoformat()})
        self._save(KNOWLEDGE_FILE, knowledge)

    def get_knowledge(self, topic=None):
        knowledge = self._load(KNOWLEDGE_FILE, [])
        if topic:
            return [k for k in knowledge if topic.lower() in k["topic"].lower()]
        return knowledge

    def save_correction(self, user_msg, wrong_action, correct_action, reason=""):
        corrections = self._load(CORRECTIONS_FILE, [])
        corrections.append({
            "timestamp": datetime.now().isoformat(),
            "user_message": user_msg, "wrong_action": wrong_action,
            "correct_action": correct_action, "reason": reason
        })
        self._save(CORRECTIONS_FILE, corrections)
        self.save_knowledge(
            f"correccion:{user_msg[:50]}",
            f"Cuando el usuario dice '{user_msg}', NO hacer '{wrong_action}'. "
            f"Hacer '{correct_action}'. Razon: {reason}",
            source="user_correction"
        )

    def get_lessons(self):
        knowledge = self._load(KNOWLEDGE_FILE, [])
        return [k["content"] for k in knowledge if k["topic"].startswith("leccion:")]

    def get_corrections_for(self, user_msg: str) -> list:
        corrections = self._load(CORRECTIONS_FILE, [])
        msg_lower = user_msg.lower()
        relevant = []
        for c in corrections:
            if any(w in msg_lower for w in c["user_message"].lower().split() if len(w) > 3):
                relevant.append(c)
        return relevant[-5:]

    def get_stats(self):
        corrections = self._load(CORRECTIONS_FILE, [])
        return {
            "knowledge": len(self._load(KNOWLEDGE_FILE, [])),
            "corrections": len(corrections),
            "patterns": len(self._load(PATTERNS_FILE, [])),
            "feedback": len(self._load(FEEDBACK_FILE, [])),
        }

learning = LearningSystem()


# ============================================================
# TRIPLE MEMORIA - Fase 2
# ============================================================
# 1. Corto Plazo: Conversacion actual (ya en ReactAgent)
# 2. Largo Plazo: Conocimiento con busqueda semantica (embeddings)
# 3. Trabajo: Scratchpad para la tarea actual

# --- Embeddings via Ollama (sin dependencias extras) ---

# Cache global de embeddings para evitar llamadas repetidas a Ollama
_EMBED_CACHE = {}
_EMBED_CACHE_MAX = 200  # Maximo de entradas en cache

def _get_embedding(text: str) -> list:
    """Obtiene el embedding de un texto usando Ollama. Con cache para velocidad."""
    global _EMBED_CACHE

    # Cache hit
    cache_key = hashlib.md5(text[:500].encode()).hexdigest()[:16]
    if cache_key in _EMBED_CACHE:
        return _EMBED_CACHE[cache_key]

    # Detectar modelo de embeddings (solo la primera vez)
    embed_model = _detect_embed_model()

    try:
        import urllib.request
        data = json.dumps({
            "model": embed_model,
            "prompt": text[:2000]
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:11434/api/embeddings",
            data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            embedding = result.get("embedding", [])
            if embedding:
                # Guardar en cache con LRU
                if len(_EMBED_CACHE) >= _EMBED_CACHE_MAX:
                    # Eliminar las entradas mas viejas
                    oldest_keys = list(_EMBED_CACHE.keys())[:_EMBED_CACHE_MAX // 2]
                    for k in oldest_keys:
                        del _EMBED_CACHE[k]
                _EMBED_CACHE[cache_key] = embedding
                return embedding
    except Exception as e:
        logger.warning(f"Error obteniendo embedding: {e}")
    return []


def _cosine_similarity(vec1: list, vec2: list) -> float:
    """Calcula similitud coseno entre dos vectores. Sin numpy."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)


class VectorStore:
    """
    Vector store ligero usando embeddings de Ollama.
    Sin Qdrant, sin ChromaDB, sin dependencias extras.
    Persiste en JSON + archivo de vectores.

    v13: Cache de vectores en memoria, carga lazy, TTL para entradas viejas.
    """

    def __init__(self, store_dir: str = None):
        self.store_dir = store_dir or os.path.join(LEARN_DIR, "vectors")
        os.makedirs(self.store_dir, exist_ok=True)
        self.index_file = os.path.join(self.store_dir, "index.json")
        self.vectors_file = os.path.join(self.store_dir, "vectors.json")
        self.index = self._load_index()
        self._vectors_cache = None  # Cache en memoria de vectores
        self._dirty = False  # Marca si hay cambios sin guardar

    def _load_index(self) -> list:
        """Carga el indice de entradas."""
        try:
            if os.path.exists(self.index_file):
                with open(self.index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return []

    def _save_index(self):
        """Guarda el indice."""
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self.index, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _get_vectors(self) -> dict:
        """Carga los vectores con cache en memoria."""
        if self._vectors_cache is not None:
            return self._vectors_cache
        try:
            if os.path.exists(self.vectors_file):
                with open(self.vectors_file, "r", encoding="utf-8") as f:
                    self._vectors_cache = json.load(f)
                    return self._vectors_cache
        except:
            pass
        self._vectors_cache = {}
        return self._vectors_cache

    def _save_vectors(self, vectors: dict):
        """Guarda los vectores y actualiza cache."""
        try:
            with open(self.vectors_file, "w", encoding="utf-8") as f:
                json.dump(vectors, f)
            self._vectors_cache = vectors  # Actualizar cache
        except:
            pass

    def _flush(self):
        """Guarda cambios pendientes si hay."""
        if self._dirty:
            self._save_index()
            self._dirty = False

    def add(self, text: str, metadata: dict = None, entry_id: str = None) -> str:
        """Agrega un texto al vector store con su embedding."""
        if not entry_id:
            entry_id = hashlib.md5(text.encode()).hexdigest()[:12]

        # Verificar si ya existe
        for entry in self.index:
            if entry["id"] == entry_id:
                return entry_id

        # Obtener embedding
        embedding = _get_embedding(text)
        if not embedding:
            # Si no hay embeddings, guardar sin vector (busqueda por texto)
            self.index.append({
                "id": entry_id,
                "text": text[:500],
                "metadata": metadata or {},
                "has_vector": False,
                "created": datetime.now().isoformat()
            })
            self._dirty = True
            self._flush()
            return entry_id

        # Guardar vector por separado
        vectors = self._get_vectors()
        vectors[entry_id] = embedding
        self._save_vectors(vectors)

        self.index.append({
            "id": entry_id,
            "text": text[:500],
            "metadata": metadata or {},
            "has_vector": True,
            "created": datetime.now().isoformat()
        })
        self._dirty = True
        self._flush()
        return entry_id

    def search(self, query: str, limit: int = 5, min_similarity: float = 0.3) -> list:
        """Busca entradas semanticamente similares al query."""
        if not self.index:
            return []

        query_embedding = _get_embedding(query)
        if not query_embedding:
            # Fallback: busqueda por texto si no hay embeddings
            query_lower = query.lower()
            query_words = [w for w in query_lower.split() if len(w) > 3]
            results = []
            for entry in self.index:
                text_lower = entry["text"].lower()
                # Score basado en cuantas palabras del query estan en el texto
                matches = sum(1 for w in query_words if w in text_lower)
                if matches > 0:
                    score = matches / max(len(query_words), 1)
                    results.append({**entry, "score": round(score, 3)})
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]

        # Busqueda semantica
        vectors = self._get_vectors()
        scored = []
        for entry in self.index:
            if not entry.get("has_vector") or entry["id"] not in vectors:
                continue
            vec = vectors[entry["id"]]
            score = _cosine_similarity(query_embedding, vec)
            if score >= min_similarity:
                scored.append({**entry, "score": round(score, 3)})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def count(self) -> int:
        return len(self.index)

    def cleanup(self, max_entries: int = 1000):
        """Limpia entradas viejas si hay demasiadas."""
        if len(self.index) <= max_entries:
            return
        # Mantener las mas recientes
        self.index.sort(key=lambda x: x.get("created", ""), reverse=True)
        removed = self.index[max_entries:]
        self.index = self.index[:max_entries]
        # Limpiar vectores huerfanos
        vectors = self._get_vectors()
        valid_ids = {e["id"] for e in self.index}
        orphan_ids = [vid for vid in vectors if vid not in valid_ids]
        for oid in orphan_ids:
            del vectors[oid]
        if orphan_ids:
            self._save_vectors(vectors)
        self._dirty = True
        self._flush()


class TripleMemory:
    """
    Sistema de Triple Memoria v13:
    1. Corto Plazo: Ultimos mensajes de conversacion
    2. Largo Plazo: Conocimiento con busqueda semantica (VectorStore)
    3. Trabajo: Scratchpad para la tarea actual

    Mejoras v13:
    - Persistencia de sesion (save/load)
    - Resumen LLM cuando la conversacion es larga
    - Contexto inteligente: solo inyecta lo relevante, con budget de tokens
    - Auto-limpieza de memoria vieja
    """

    # Budget de tokens para contexto (aproximado, 1 token ~ 4 chars)
    MAX_CONTEXT_CHARS = 3000

    def __init__(self):
        self.short_term = []  # Memoria a corto plazo (conversacion)
        self.long_term = VectorStore()  # Memoria a largo plazo (semantica)
        self.working = {  # Memoria de trabajo (scratchpad)
            "current_task": "",
            "task_steps": [],
            "notes": [],
            "context_files": [],
            "last_error": "",
            "last_success": "",
        }
        self._summary_cache = None
        self._summary_last_update = None
        # Persistencia
        self._session_file = os.path.join(LEARN_DIR, "session.json")
        self._auto_save_counter = 0

    def add_conversation(self, role: str, content: str):
        """Agrega un mensaje a la memoria a corto plazo."""
        self.short_term.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        # Mantener ventana deslizante
        if len(self.short_term) > MAX_CONVERSATION_MEMORY * 2:
            # Antes de recortar, guardar lo importante en largo plazo
            removed = self.short_term[:len(self.short_term) - MAX_CONVERSATION_MEMORY * 2]
            for msg in removed:
                if msg["role"] == "assistant" and len(msg["content"]) > 50:
                    # Las respuestas largas del asistente valen guardar
                    self.long_term.add(
                        msg["content"][:500],
                        metadata={"type": "conversation", "role": msg["role"]}
                    )
            self.short_term = self.short_term[-(MAX_CONVERSATION_MEMORY * 2):]

        # Auto-save cada 5 mensajes
        self._auto_save_counter += 1
        if self._auto_save_counter >= 5:
            self._auto_save_counter = 0
            self.save_session()

    def remember(self, text: str, metadata: dict = None):
        """Guarda algo en la memoria a largo plazo."""
        return self.long_term.add(text, metadata=metadata)

    def recall(self, query: str, limit: int = 5) -> list:
        """Recupera recuerdos relevantes de la memoria a largo plazo."""
        return self.long_term.search(query, limit=limit)

    def set_task(self, task: str):
        """Establece la tarea actual en la memoria de trabajo."""
        self.working["current_task"] = task
        self.working["task_steps"] = []
        self.working["notes"] = []

    def add_step(self, step: str, result: str = ""):
        """Agrega un paso a la memoria de trabajo."""
        self.working["task_steps"].append({
            "step": step,
            "result": result[:200],
            "timestamp": datetime.now().isoformat()
        })

    def add_note(self, note: str):
        """Agrega una nota al scratchpad."""
        self.working["notes"].append(note)

    def set_error(self, error: str):
        """Registra el ultimo error."""
        self.working["last_error"] = error

    def set_success(self, success: str):
        """Registra el ultimo exito."""
        self.working["last_success"] = success

    def get_context_for(self, query: str) -> str:
        """
        Construye contexto enriquecido para una query.
        Combina las 3 memorias en un texto coherente.
        Respetando budget de tokens para no saturar el prompt.
        """
        context_parts = []
        budget_remaining = self.MAX_CONTEXT_CHARS

        # 1. Memoria de Trabajo (si hay tarea activa) - max 800 chars
        if self.working["current_task"]:
            work_context = f"TAREA ACTUAL: {self.working['current_task']}"
            if self.working["task_steps"]:
                steps_text = "\n".join([
                    f"  - {s['step']}: {s['result']}"
                    for s in self.working["task_steps"][-5:]
                ])
                work_context += f"\nPASOS REALIZADOS:\n{steps_text}"
            if self.working["last_error"]:
                work_context += f"\nULTIMO ERROR: {self.working['last_error']}"
            if self.working["notes"]:
                work_context += f"\nNOTAS: {'; '.join(self.working['notes'][-3:])}"

            if len(work_context) <= 800:
                context_parts.append(work_context)
                budget_remaining -= len(work_context)
            else:
                context_parts.append(work_context[:800])
                budget_remaining -= 800

        # 2. Correcciones aprendidas - max 400 chars
        corrections = learning.get_corrections_for(query)
        if corrections and budget_remaining > 200:
            corr_text = "\n".join([
                f"  - NO hagas '{c['wrong_action']}'. Haz '{c['correct_action']}'"
                for c in corrections[-3:]
            ])
            corr_full = f"CORRECCIONES:\n{corr_text}"
            if len(corr_full) <= 400:
                context_parts.append(corr_full)
                budget_remaining -= len(corr_full)
            else:
                context_parts.append(corr_full[:400])
                budget_remaining -= 400

        # 3. Memoria a Largo Plazo (busqueda semantica) - budget restante
        if budget_remaining > 200:
            recall_results = self.recall(query, limit=3)
            if recall_results:
                knowledge_text = "\n".join([
                    f"  - [{r.get('score', 0):.2f}] {r['text'][:150]}"
                    for r in recall_results
                ])
                knowledge_full = f"CONOCIMIENTO RELEVANTE:\n{knowledge_text}"
                if len(knowledge_full) <= budget_remaining:
                    context_parts.append(knowledge_full)
                else:
                    context_parts.append(knowledge_full[:budget_remaining])

        # 4. Resumen de conversacion si es larga
        if len(self.short_term) > 10:
            summary = self._get_conversation_summary()
            if summary:
                # El resumen es compacto, agregar si hay espacio
                summary_text = f"RESUMEN: {summary}"
                if len(summary_text) <= 300:
                    context_parts.append(summary_text)

        return "\n\n".join(context_parts) if context_parts else ""

    def _get_conversation_summary(self) -> str:
        """Genera un resumen de la conversacion si es larga."""
        if self._summary_cache and self._summary_last_update:
            # Refrescar resumen cada 5 mensajes nuevos
            msgs_since = len(self.short_term) - self._summary_last_update
            if msgs_since < 5:
                return self._summary_cache

        # Resumen simple: temas recientes
        user_msgs = [m["content"][:80] for m in self.short_term if m["role"] == "user"]
        if not user_msgs:
            return ""

        summary = "Temas recientes: " + "; ".join(user_msgs[-5:])
        self._summary_cache = summary
        self._summary_last_update = len(self.short_term)
        return summary

    def _generate_llm_summary(self) -> str:
        """Genera un resumen de la conversacion usando el LLM.
        Solo se llama cuando la conversacion es muy larga (>30 mensajes).
        """
        if len(self.short_term) < 30:
            return self._get_conversation_summary()

        # Construir texto de la conversacion para resumir
        conv_text = ""
        for msg in self.short_term[-20:]:
            role = "Usuario" if msg["role"] == "user" else "Asistente"
            conv_text += f"{role}: {msg['content'][:100]}\n"

        summary_prompt = [
            {"role": "system", "content": "Resume esta conversacion en 2-3 lineas. Solo los temas principales."},
            {"role": "user", "content": conv_text[:1500]}
        ]

        summary = _llm_generate(summary_prompt)
        if summary and len(summary) > 10:
            self._summary_cache = summary[:300]
            self._summary_last_update = len(self.short_term)
            return self._summary_cache
        return self._get_conversation_summary()

    def save_session(self):
        """Guarda la sesion actual para persistencia."""
        try:
            session_data = {
                "short_term": self.short_term[-MAX_CONVERSATION_MEMORY:],
                "working": self.working,
                "saved_at": datetime.now().isoformat()
            }
            with open(self._session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
        except:
            pass

    def load_session(self):
        """Carga la sesion anterior si existe."""
        try:
            if os.path.exists(self._session_file):
                with open(self._session_file, "r", encoding="utf-8") as f:
                    session_data = json.load(f)
                # Solo cargar si es reciente (< 24 horas)
                saved_at = session_data.get("saved_at", "")
                if saved_at:
                    saved_time = datetime.fromisoformat(saved_at)
                    hours_ago = (datetime.now() - saved_time).total_seconds() / 3600
                    if hours_ago < 24:
                        self.short_term = session_data.get("short_term", [])
                        self.working = session_data.get("working", self.working)
                        return True
                # Sesion vieja, no cargar conversacion pero si working memory
                self.working = session_data.get("working", self.working)
        except:
            pass
        return False

    def clear_session(self):
        """Limpia la sesion actual."""
        self.short_term = []
        self.working = {
            "current_task": "",
            "task_steps": [],
            "notes": [],
            "context_files": [],
            "last_error": "",
            "last_success": "",
        }
        self._summary_cache = None
        self._summary_last_update = None

    def get_stats(self) -> dict:
        return {
            "short_term_messages": len(self.short_term),
            "long_term_entries": self.long_term.count(),
            "working_task": bool(self.working["current_task"]),
            "working_steps": len(self.working["task_steps"]),
            "corrections": len(learning.get_corrections_for("")),
            "embed_cache_size": len(_EMBED_CACHE),
        }


memory = TripleMemory()
# Cargar sesion anterior al iniciar
memory.load_session()


# ============================================================
# LLM - Conexion a Ollama con 4 metodos
# ============================================================

def _get_available_models() -> list:
    """Obtiene la lista de modelos disponibles en Ollama."""
    global _detected_models_list
    if _detected_models_list:
        return _detected_models_list
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            _detected_models_list = [m["name"] for m in data.get("models", [])]
            return _detected_models_list
    except:
        return []


def _detect_best_model() -> str:
    """Detecta el mejor modelo disponible. Se ejecuta UNA vez al inicio."""
    global AGENT_MODEL, FALLBACK_MODEL, CHAT_MODEL, _detected_model

    if _detected_model:
        return _detected_model

    available = _get_available_models()

    if not available:
        # No hay Ollama o no hay modelos
        AGENT_MODEL = "qwen2.5:14b"
        FALLBACK_MODEL = "llama3.1:8b"
        CHAT_MODEL = "llama3.1:8b"
        _detected_model = AGENT_MODEL
        return AGENT_MODEL

    # Buscar el mejor modelo en orden de preferencia
    for preferred in PREFERRED_MODELS:
        for avail in available:
            if preferred in avail or avail.startswith(preferred.split(":")[0]):
                AGENT_MODEL = avail
                _detected_model = avail
                # El fallback es el segundo mejor
                for fb in PREFERRED_MODELS:
                    if fb != preferred:
                        for avail2 in available:
                            if fb in avail2 or avail2.startswith(fb.split(":")[0]):
                                FALLBACK_MODEL = avail2
                                CHAT_MODEL = avail2
                                return AGENT_MODEL
                FALLBACK_MODEL = available[0] if len(available) > 1 else AGENT_MODEL
                CHAT_MODEL = FALLBACK_MODEL
                return AGENT_MODEL

    # Si ningun modelo preferido esta, usar el primero disponible
    AGENT_MODEL = available[0]
    FALLBACK_MODEL = available[1] if len(available) > 1 else available[0]
    CHAT_MODEL = FALLBACK_MODEL
    _detected_model = AGENT_MODEL
    return AGENT_MODEL


# Cache de conexion Ollama exitosa - evita probar 12+ combinaciones cada vez
_ollama_client = None
_ollama_working_host = None
_ollama_working_method = None  # "client", "global", "http"
_ollama_embed_model = None  # Modelo de embeddings detectado


def _get_ollama_client():
    """Obtiene o crea un Ollama Client singleton."""
    global _ollama_client
    if _ollama_client is None:
        try:
            import ollama
            host = _ollama_working_host or 'http://localhost:11434'
            _ollama_client = ollama.Client(host=host)
        except Exception:
            pass
    return _ollama_client


def _detect_embed_model() -> str:
    """Detecta que modelo de embeddings esta disponible. Se ejecuta UNA vez."""
    global _ollama_embed_model
    if _ollama_embed_model:
        return _ollama_embed_model

    embed_models = ["nomic-embed-text", "mxbai-embed-large", "all-minilm"]
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            available = [m["name"].lower() for m in data.get("models", [])]
            for candidate in embed_models:
                for avail in available:
                    if candidate in avail:
                        _ollama_embed_model = candidate
                        logger.info(f"Modelo de embeddings detectado: {candidate}")
                        return candidate
    except Exception as e:
        logger.warning(f"No se pudo detectar modelo de embeddings: {e}")

    _ollama_embed_model = "nomic-embed-text"  # Default
    return _ollama_embed_model


def _llm_generate(messages: list, tools: list = None) -> str:
    """Consulta al LLM local. Usa cache de conexion exitosa para velocidad.
    Retorna: str (texto del LLM) o dict (respuesta completa con tool_calls).
    Retorna "" si todo falla.
    """
    global _ollama_working_host, _ollama_working_method, _ollama_client

    # Asegurar que tenemos modelo detectado
    _detect_best_model()

    # Modelos a probar en orden
    models_to_try = [m for m in [AGENT_MODEL, FALLBACK_MODEL] if m and m != AGENT_MODEL]
    models_to_try.insert(0, AGENT_MODEL)
    models_to_try = list(dict.fromkeys(models_to_try))  # Eliminar duplicados manteniendo orden

    if not models_to_try:
        return ""

    # Timeout adaptativo: modelos grandes necesitan mas tiempo
    def _get_timeout(model_name: str) -> int:
        if any(x in model_name.lower() for x in ["14b", "30b", "70b", "32b"]):
            return 180
        return 120

    errors = []

    # ---- ESTRATEGIA 1: Probar conexion exitosa previa primero ----
    if _ollama_working_host and _ollama_working_method and AGENT_MODEL:
        try:
            import ollama
            if _ollama_working_method == "client":
                client = _get_ollama_client() or ollama.Client(host=_ollama_working_host)
                if tools:
                    response = client.chat(model=AGENT_MODEL, messages=messages, tools=tools)
                    msg = response.get("message", response)
                    if msg.get("content") or msg.get("tool_calls"):
                        return response
                else:
                    response = client.chat(model=AGENT_MODEL, messages=messages)
                    content = response.get("message", {}).get("content", "")
                    if content:
                        return content
            elif _ollama_working_method == "http":
                import urllib.request
                data = json.dumps({
                    "model": AGENT_MODEL, "messages": messages, "stream": False
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"{_ollama_working_host}/api/chat",
                    data=data, headers={"Content-Type": "application/json"}
                )
                timeout = _get_timeout(AGENT_MODEL)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    content = result.get("message", {}).get("content", "")
                    if content:
                        return content
        except Exception as e:
            errors.append(f"cached method failed: {str(e)[:60]}")
            # Resetear cache y probar de nuevo
            _ollama_working_method = None

    # ---- ESTRATEGIA 2: Buscar conexion que funcione ----
    try:
        import ollama
        hosts = ['http://localhost:11434', 'http://127.0.0.1:11434']

        # Con function calling nativo si hay tools
        if tools:
            for model in models_to_try:
                for host in hosts:
                    try:
                        client = ollama.Client(host=host)
                        response = client.chat(model=model, messages=messages, tools=tools)
                        msg = response.get("message", response)
                        if msg.get("content") or msg.get("tool_calls"):
                            # Guardar como conexion exitosa
                            _ollama_working_host = host
                            _ollama_working_method = "client"
                            _ollama_client = client
                            logger.info(f"LLM conectado: {model}@{host} con tools")
                            return response
                        errors.append(f"{model}@{host}: respuesta vacia con tools")
                    except Exception as e:
                        errors.append(f"{model}@{host} tools: {str(e)[:60]}")
                        continue

        # Sin tools - Intentar con Client
        for model in models_to_try:
            for host in hosts:
                try:
                    client = ollama.Client(host=host)
                    response = client.chat(model=model, messages=messages)
                    content = response.get("message", {}).get("content", "")
                    if content:
                        _ollama_working_host = host
                        _ollama_working_method = "client"
                        _ollama_client = client
                        return content
                    errors.append(f"{model}@{host}: respuesta vacia")
                except Exception as e:
                    errors.append(f"{model}@{host}: {str(e)[:60]}")
                    continue

    except ImportError:
        errors.append("ollama no instalado, usando HTTP directo")

    # ---- ESTRATEGIA 3: HTTP directo (sin lib ollama) ----
    for model in models_to_try:
        timeout = _get_timeout(model)
        try:
            import urllib.request
            data = json.dumps({
                "model": model, "messages": messages, "stream": False
            }).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:11434/api/chat",
                data=data, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result.get("message", {}).get("content", "")
                if content:
                    _ollama_working_host = "http://localhost:11434"
                    _ollama_working_method = "http"
                    return content
                errors.append(f"{model} HTTP: respuesta vacia")
        except Exception as e:
            errors.append(f"{model} HTTP: {str(e)[:60]}")
            continue

    # Si llegamos aqui, todo fallo - guardar diagnostico
    if errors:
        # Guardar en log para debug
        try:
            log_path = os.path.join(LEARN_DIR, "llm_errors.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now().isoformat()} ---\n")
                for err in errors[-5:]:
                    f.write(f"  {err}\n")
        except:
            pass

    return ""


# ============================================================
# CEREBRO ReAct - El motor principal v11
# ============================================================

SYSTEM_PROMPT = """Eres un agente autonomo INTELIGENTE que vive en la computadora del usuario.

Tu trabajo es ayudarlo con CUALQUIER cosa. Tienes herramientas para:
- Abrir aplicaciones de escritorio, abrir paginas web/URLs en el navegador
- Ejecutar comandos, leer/escribir archivos
- Generar codigo completo (juegos, paginas web, scripts)
- Clonar repos, instalar dependencias, analizar proyectos
- Buscar en archivos, ver procesos, buscar en internet
- Matar procesos que se cuelgan

REGLAS:
1. PIENSA antes de actuar. Analiza que quiere el usuario.
2. Si pide CREAR algo (juego, pagina, script) → usa generar_codigo
3. Si pide ABRIR un programa de escritorio → usa abrir_aplicacion
4. Si pide ABRIR un sitio web o URL (YouTube, Google, etc.) → usa abrir_url
5. Si pide BUSCAR o VER algo en YouTube → usa buscar_youtube
6. Si algo falla → intenta un enfoque diferente
7. Si no sabes algo → busca en internet
8. NUNCA inventes rutas o comandos — usa las herramientas para verificar
9. Habla en espanol, de forma natural y concisa

CONTEXTO DEL SISTEMA:
- SO: {so}
- Directorio de trabajo: {repos_dir}
- Modelos disponibles: {models}

CORRECCIONES APRENDIDAS (NO repitas estos errores):
{corrections}
"""

# Prompt para cuando usamos JSON fallback (modelos sin tool calling)
JSON_TOOLS_PROMPT = """

HERRAMIENTAS DISPONIBLES:
- ejecutar_comando(comando, confirmar_peligroso=false) - Ejecuta un comando
- abrir_aplicacion(app) - Abre una app de escritorio por nombre (NO para paginas web)
- abrir_url(url) - Abre una pagina web o sitio en el navegador (YouTube, Google, etc.)
- buscar_youtube(consulta) - Busca un video en YouTube y abre los resultados
- generar_codigo(descripcion, tipo, ruta?) - Genera codigo completo y lo guarda
- leer_archivo(ruta) - Lee un archivo
- escribir_archivo(ruta, contenido) - Escribe un archivo
- listar_archivos(ruta?) - Lista archivos de un directorio
- analizar_proyecto(ruta) - Analiza estructura de proyecto
- clonar_repositorio(url) - Clona un repo de GitHub
- instalar_dependencias(ruta, gestor?) - Instala dependencias
- buscar_en_archivos(ruta, patron) - Busca texto en archivos
- procesos_activos(filtro?) - Lista procesos corriendo
- matar_proceso(pid_o_nombre) - Termina un proceso
- buscar_web(consulta) - Busca en internet

IMPORTANTE:
- Si el usuario pide abrir un SITIO WEB (YouTube, Google, Netflix, etc.), usa abrir_url, NO abrir_aplicacion.
- abrir_aplicacion es solo para programas de escritorio (Chrome, Word, WhatsApp, etc.).
- Si pide BUSCAR algo en YouTube, usa buscar_youtube.
- Si pide ABRIR YouTube (la pagina principal), usa abrir_url.

Responde SOLO con JSON:
{{"pensamiento": "que piensas", "accion": "nombre_herramienta", "params": {{...}}, "respuesta_final": ""}}
Si ya tienes la respuesta final (no necesitas herramientas), ponla en "respuesta_final" y deja accion vacio.
"""


class ReactAgent:
    """Motor ReAct: Piensa → Actua → Observa → Piensa de nuevo."""

    def __init__(self):
        self.thinking_log = []
        self.conversation_history = []
        self.supports_tool_calling = None  # Se detecta automaticamente

    def _log(self, message: str, category: str = "info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.thinking_log.append(f"[{timestamp}] [{category.upper()}] {message}")

    def run(self, user_message: str) -> tuple:
        """
        Bucle ReAct principal. Retorna (respuesta, thinking_log).
        """
        self.thinking_log = []
        self._log(f"Mensaje del usuario: {user_message}", "input")

        # Construir mensajes con memoria conversacional
        messages = self._build_messages(user_message)

        # Detectar si el modelo soporta tool calling (primera vez)
        if self.supports_tool_calling is None:
            self.supports_tool_calling = self._detect_tool_calling_support()
            self._log(f"Tool calling nativo: {'SI' if self.supports_tool_calling else 'NO (usando JSON fallback)'}", "info")

        # BUCLE ReAct
        for iteration in range(MAX_REACT_ITERATIONS):
            self._log(f"--- Iteracion {iteration + 1}/{MAX_REACT_ITERATIONS} ---", "react")

            if self.supports_tool_calling:
                action_result = self._react_with_tools(messages, iteration)
            else:
                action_result = self._react_with_json(messages, iteration)

            # action_result puede ser:
            # ("respond", final_response) → Terminar, responder al usuario
            # ("tool_call", tool_name, tool_params) → Ejecutar herramienta
            # ("error", error_msg) → Error, intentar de nuevo

            if action_result[0] == "respond":
                final_response = action_result[1]
                self._log("Respuesta final generada", "success")
                # Guardar en Triple Memoria
                memory.add_conversation("user", user_message)
                memory.add_conversation("assistant", final_response)
                # Tambien guardar en conversation_history vieja (compatibilidad)
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "assistant", "content": final_response})
                if len(self.conversation_history) > MAX_CONVERSATION_MEMORY * 2:
                    self.conversation_history = self.conversation_history[-(MAX_CONVERSATION_MEMORY * 2):]
                # Aprender de la interaccion (largo plazo)
                memory.remember(
                    f"Usuario pregunto: {user_message[:100]} → Respuesta: {final_response[:200]}",
                    metadata={"type": "interaction", "user_msg": user_message[:50]}
                )
                memory.set_success(final_response[:100])
                return final_response, self.thinking_log

            elif action_result[0] == "tool_call":
                tool_name = action_result[1]
                tool_params = action_result[2]

                # Ejecutar la herramienta
                self._log(f"Ejecutando: {tool_name}({tool_params})", "execution")
                tool_result = self._execute_tool(tool_name, tool_params)
                self._log(f"Resultado: {tool_result[:150]}...", "observation")

                # Alimentar memoria de trabajo
                memory.add_step(f"{tool_name}({tool_params})", tool_result[:200])
                if "ERROR" in tool_result:
                    memory.set_error(f"{tool_name}: {tool_result[:100]}")
                # Guardar resultado importante en largo plazo
                if len(tool_result) > 50 and "ERROR" not in tool_result:
                    memory.remember(
                        f"Resultado de {tool_name}: {tool_result[:300]}",
                        metadata={"type": "tool_result", "tool": tool_name}
                    )

                # Alimentar el resultado de vuelta al agente
                if self.supports_tool_calling:
                    # Formato tool calling nativo
                    messages.append({"role": "tool", "content": tool_result})
                else:
                    # Formato JSON
                    messages.append({"role": "assistant",
                                     "content": json.dumps({"pensamiento": f"Ejecute {tool_name}", "accion": tool_name, "params": tool_params})})
                    messages.append({"role": "user",
                                     "content": f"Resultado de {tool_name}: {tool_result}\n\nQue hago ahora? Responde con JSON."})

            elif action_result[0] == "error":
                self._log(f"Error: {action_result[1]}", "error")
                if iteration >= MAX_REACT_ITERATIONS - 1:
                    return ("Tuve problemas para procesar tu solicitud. Puedes reformularla?", self.thinking_log)

        self._log("Alcanzado limite de iteraciones", "warning")
        return ("Alcance el limite de iteraciones. Puede que necesites ser mas especifico.", self.thinking_log)

    def _react_with_tools(self, messages: list, iteration: int) -> tuple:
        """ReAct usando function calling nativo."""
        try:
            response = _llm_generate(messages, tools=TOOL_SCHEMAS)

            if isinstance(response, str):
                # El modelo no soporto tools, devolver como respuesta
                return ("respond", response)

            # Ver si hay tool calls
            message = response.get("message", response)
            tool_calls = message.get("tool_calls", [])

            if tool_calls:
                # Hay tool calls - ejecutar el primero
                tc = tool_calls[0]
                tool_name = tc.get("function", {}).get("name", "")
                tool_params = tc.get("function", {}).get("arguments", {})
                self._log(f"Tool call: {tool_name}({tool_params})", "thinking")

                # Agregar el mensaje del asistente al historial
                messages.append({"role": "assistant", "content": message.get("content", ""),
                                "tool_calls": tool_calls})
                return ("tool_call", tool_name, tool_params)

            # No hay tool calls - es la respuesta final
            content = message.get("content", "")
            if content:
                return ("respond", content)

            return ("error", "Respuesta vacia del modelo")

        except Exception as e:
            self._log(f"Error en tool calling: {e}", "error")
            # Fallback a JSON
            self.supports_tool_calling = False
            return ("error", str(e))

    def _react_with_json(self, messages: list, iteration: int) -> tuple:
        """ReAct usando JSON parsing (fallback para modelos sin tool calling)."""
        # Agregar el prompt de herramientas si no esta
        if not any("HERRAMIENTAS DISPONIBLES" in str(m.get("content", "")) for m in messages):
            # Insertar instrucciones de JSON antes del ultimo mensaje
            system_msg_idx = next((i for i, m in enumerate(messages) if m["role"] == "system"), -1)
            if system_msg_idx >= 0:
                messages[system_msg_idx]["content"] += JSON_TOOLS_PROMPT

        try:
            response = _llm_generate(messages)
            if not response:
                return ("error", "El LLM no respondio")

            # Intentar parsear como JSON
            parsed = self._parse_json(response)
            if not parsed:
                # No es JSON, probablemente es una respuesta directa
                return ("respond", response)

            # Tiene respuesta final?
            if parsed.get("respuesta_final"):
                return ("respond", parsed["respuesta_final"])

            # Tiene accion?
            accion = parsed.get("accion", "")
            params = parsed.get("params", {})
            pensamiento = parsed.get("pensamiento", "")

            if pensamiento:
                self._log(f"Pensamiento: {pensamiento}", "thinking")

            if accion and accion in TOOL_FUNCTIONS:
                return ("tool_call", accion, params)

            # No se que hacer con esto, responder como texto
            return ("respond", response)

        except Exception as e:
            return ("error", str(e))

    def _build_messages(self, new_message: str) -> list:
        """Construye la lista de mensajes con CONTEXTO ENRIQUECIDO (Triple Memoria)."""
        # System prompt base
        models = self._get_available_models()
        system_content = SYSTEM_PROMPT.format(
            so=platform.system(),
            repos_dir=REPOS_DIR,
            models=", ".join(models) if models else (AGENT_MODEL or "desconocido"),
            corrections="Ver correcciones abajo"
        )

        # CONTEXTO ENRIQUECIDO desde Triple Memoria
        enriched_context = memory.get_context_for(new_message)
        if enriched_context:
            system_content += f"\n\n--- CONTEXTO DE MEMORIA ---\n{enriched_context}"

        # Conocimiento relevante (sistema antiguo como backup)
        relevant_knowledge = learning.get_knowledge(new_message)
        if relevant_knowledge:
            knowledge_text = "\n".join([f"- {k['content']}" for k in relevant_knowledge[:3]])
            system_content += f"\n\nConocimiento adicional:\n{knowledge_text}"

        messages = [{"role": "system", "content": system_content}]

        # Historial de conversacion desde TripleMemory (fuente principal)
        recent_history = memory.short_term[-MAX_CONVERSATION_MEMORY:]
        for msg in recent_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Fallback: tambien usar conversation_history vieja si existe
        if not recent_history and self.conversation_history:
            for msg in self.conversation_history[-MAX_CONVERSATION_MEMORY:]:
                messages.append(msg)

        # Mensaje actual
        messages.append({"role": "user", "content": new_message})

        return messages

    def _execute_tool(self, tool_name: str, params: dict) -> str:
        """Ejecuta una herramienta por nombre."""
        if tool_name in TOOL_FUNCTIONS:
            try:
                # Resolver variables especiales
                params = self._resolve_params(params)
                return TOOL_FUNCTIONS[tool_name](**params)
            except Exception as e:
                return f"ERROR ejecutando {tool_name}: {e}"
        return f"Herramienta no encontrada: {tool_name}"

    def _resolve_params(self, params: dict) -> dict:
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                value = value.replace("REPOS_DIR", REPOS_DIR)
                value = value.replace("RUTA_DEL_REPO", self._find_repo_path())
            resolved[key] = value
        return resolved

    def _find_repo_path(self) -> str:
        try:
            dirs = [d for d in os.listdir(REPOS_DIR)
                    if os.path.isdir(os.path.join(REPOS_DIR, d)) and not d.startswith(".")]
            if dirs:
                latest = max(dirs, key=lambda d: os.path.getmtime(os.path.join(REPOS_DIR, d)))
                return os.path.join(REPOS_DIR, latest)
        except:
            pass
        return REPOS_DIR

    def _parse_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except:
            pass
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'(\{[\s\S]*\})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except:
                    continue
        return None

    def _detect_tool_calling_support(self) -> bool:
        """Detecta si el modelo soporta function calling nativo.
        Metodo rapido: envia un mensaje minimo con tools para ver si el modelo
        lo acepta sin error. Modelos qwen3 soportan, qwen2.5 no.
        """
        _detect_best_model()  # Asegurar modelo detectado

        # Heuristica rapida: qwen3 soporta tool calling, qwen2.5 no
        if AGENT_MODEL:
            model_lower = AGENT_MODEL.lower()
            # Modelos que SI soportan tool calling nativo
            if any(x in model_lower for x in ["qwen3", "qwen2.5:7b", "llama3.1", "llama3.2", "mistral", "command-r"]):
                if "qwen3" in model_lower:
                    return True
            # Modelos que probablemente NO soportan tool calling
            if any(x in model_lower for x in ["qwen2.5:14b", "qwen2.5:32b"]):
                return False

        # Si no podemos determinar por nombre, hacer test rapido
        try:
            import ollama
            for host in ['http://localhost:11434', 'http://127.0.0.1:11434']:
                try:
                    client = ollama.Client(host=host)
                    # Test ultra-corto: 1 mensaje minimo, 1 tool simple
                    response = client.chat(
                        model=AGENT_MODEL,
                        messages=[{"role": "user", "content": "hi"}],
                        tools=[TOOL_SCHEMAS[0]]
                    )
                    # Si no crashea, soporta tool calling
                    return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def _get_available_models(self) -> list:
        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except:
            return []


# ============================================================
# MOTOR PRINCIPAL
# ============================================================

agent = ReactAgent()

def procesar_mensaje(user_message: str) -> tuple:
    respuesta, thinking_log = agent.run(user_message)
    return respuesta, thinking_log


# ============================================================
# INTERFAZ STREAMLIT
# ============================================================

def main():
    st.set_page_config(
        page_title="Agente Autonomo v13",
        page_icon="🧠",
        layout="wide"
    )

    st.markdown("""
    <style>
    .stApp { max-width: 1200px; margin: 0 auto; }

    .main-title {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.2rem; font-weight: 800; text-align: center; margin-bottom: 0.3rem;
    }
    .main-subtitle {
        text-align: center; color: #888; font-size: 0.9rem; margin-bottom: 1.5rem;
    }

    .thinking-box {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        color: #00ff88; padding: 16px; border-radius: 12px;
        font-family: 'Consolas', 'Monaco', monospace; font-size: 11px;
        max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;
        border: 1px solid rgba(100, 100, 255, 0.2); box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
    }
    .thinking-box .thinking { color: #88aaff; }
    .thinking-box .plan { color: #ffaa44; }
    .thinking-box .execution { color: #00ff88; }
    .thinking-box .observation { color: #44ddaa; }
    .thinking-box .evaluation { color: #aa88ff; }
    .thinking-box .warning { color: #ffaa00; }
    .thinking-box .error { color: #ff4444; }
    .thinking-box .cloud { color: #44aaff; }
    .thinking-box .input { color: #88ff88; }
    .thinking-box .react { color: #ff88ff; font-weight: bold; }
    .thinking-box .success { color: #44ff88; font-weight: bold; }

    [data-testid="stChatMessage"] { border-radius: 12px; padding: 12px 16px; margin: 4px 0; }

    .stButton > button { border-radius: 8px; transition: all 0.2s; }
    .stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(100, 100, 255, 0.3); }

    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.1); border-radius: 3px; }
    ::-webkit-scrollbar-thumb { background: rgba(100, 100, 255, 0.3); border-radius: 3px; }
    </style>
    """, unsafe_allow_html=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "thinking_history" not in st.session_state:
        st.session_state.thinking_history = []

    st.markdown('<div class="main-title">Agente Autonomo v13</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">ReAct + Triple Memoria + URL Tools: Piensa → Actua → Observa → Aprende</div>', unsafe_allow_html=True)

    # === SIDEBAR ===
    with st.sidebar:
        st.header("Config")
        # Mostrar modelo detectado
        _detect_best_model()
        st.write(f"**Modelo agente:** {AGENT_MODEL or 'No detectado'}")
        st.write(f"**Modelo fallback:** {FALLBACK_MODEL or 'No detectado'}")
        st.write(f"**Directorio:** {REPOS_DIR}")
        tc_status = 'Nativo' if agent.supports_tool_calling else ('JSON fallback' if agent.supports_tool_calling is False else 'Sin detectar')
        st.write(f"**Tool calling:** {tc_status}")

        st.header("Ollama Status")
        if st.button("Test conexion Ollama", use_container_width=True):
            with st.spinner("Probando..."):
                try:
                    import urllib.request
                    req = urllib.request.Request("http://localhost:11434/api/tags")
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        models = [m["name"] for m in data.get("models", [])]
                        st.success(f"Ollama OK - {len(models)} modelos")
                        for m in models:
                            st.write(f"  - {m}")
                except Exception as e:
                    st.error(f"Ollama NO conecta: {e}")

        # Status rapido
        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m["name"] for m in data.get("models", [])]
                st.success(f"Ollama OK - {len(models)} modelos")
                _detect_best_model()
                if AGENT_MODEL:
                    st.info(f"Usando: {AGENT_MODEL}")
                else:
                    st.warning(f"Ningun modelo preferido. Disponibles: {', '.join(models[:5])}")
        except:
            st.error("Ollama NO conecta")

        stats = learning.get_stats()
        mem_stats = memory.get_stats()
        st.header("Triple Memoria")
        col1, col2, col3 = st.columns(3)
        col1.metric("Corto plazo", mem_stats["short_term_messages"])
        col2.metric("Largo plazo", mem_stats["long_term_entries"])
        col3.metric("Pasos", mem_stats["working_steps"])

        # Embed cache info
        if mem_stats.get("embed_cache_size", 0) > 0:
            st.caption(f"Embed cache: {mem_stats['embed_cache_size']} entradas")

        st.header("Aprendizaje")
        col1, col2 = st.columns(2)
        col1.metric("Conocimiento", stats["knowledge"])
        col2.metric("Correcciones", stats["corrections"])

        st.header("Corregir agente")
        st.caption("Si se equivoco, ensenale para que no repita el error")
        correction_msg = st.text_input("Que dijiste?", key="corr_msg")
        correction_wrong = st.text_input("Que hizo mal?", key="corr_wrong")
        correction_right = st.text_input("Que debia hacer?", key="corr_right")
        if st.button("Guardar correccion", use_container_width=True):
            if correction_msg and correction_wrong and correction_right:
                learning.save_correction(correction_msg, correction_wrong, correction_right)
                st.success("Correccion guardada! No repetira este error.")
            else:
                st.warning("Completa los 3 campos")

        st.header("IA Cloud")
        groq_key = os.environ.get("GROQ_API_KEY", "")
        if groq_key:
            st.success("Groq API configurada")
        else:
            st.warning("Sin API key cloud")
            groq_input = st.text_input("Groq API Key:", type="password", key="groq_key_input")
            if groq_input:
                os.environ["GROQ_API_KEY"] = groq_input
                st.success("Key guardada para esta sesion")

        if st.button("Limpiar historial", use_container_width=True):
            st.session_state.messages = []
            st.session_state.thinking_history = []
            agent.conversation_history = []
            memory.clear_session()
            st.rerun()

        st.header("Repos")
        try:
            repos = [d for d in os.listdir(REPOS_DIR)
                     if os.path.isdir(os.path.join(REPOS_DIR, d)) and not d.startswith(".")]
            for repo in repos:
                st.write(f" 📁 {repo}")
        except:
            st.write("Sin repos")

        st.header("Historial de pensamiento")
        if st.session_state.thinking_history:
            for i, th in enumerate(st.session_state.thinking_history[-5:]):
                with st.expander(f"Pensamiento #{i+1}", expanded=False):
                    st.markdown(f'<div class="thinking-box">{th}</div>', unsafe_allow_html=True)

    # === MOSTRAR HISTORIAL ===
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # === INPUT ===
    if prompt := st.chat_input("Dime que necesitas..."):
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                try:
                    respuesta, thinking_log = procesar_mensaje(prompt)

                    if thinking_log:
                        thinking_text = "\n".join(thinking_log)
                        st.session_state.thinking_history.append(thinking_text)
                        with st.expander("Proceso de pensamiento ReAct (click para ver)", expanded=False):
                            st.markdown(f'<div class="thinking-box">{thinking_text}</div>',
                                       unsafe_allow_html=True)

                    st.markdown(respuesta)

                except Exception as e:
                    respuesta = f"**ERROR:** {e}"
                    st.error(respuesta)

        st.session_state.messages.append({"role": "assistant", "content": respuesta})


if __name__ == "__main__":
    main()
