"""
=============================================================
AGENTE LOCAL AUTONOMO v11 - ReAct + Function Calling
Piensa → Actua → Observa → Piensa de nuevo → Repite
=============================================================

FILOSOFIA v11:
  Bucle ReAct real: el agente piensa, actua, observa el resultado,
  y vuelve a pensar. No ejecuta ciegamente un plan fijo.

CAMBIOS vs v10:
  v10: Pensar → Ejecutar plan completo → Evaluar (ciego)
  v11: ReAct loop (pensar→actuar→observar→repetir)
       + Function Calling nativo (si el modelo lo soporta)
       + Fallback inteligente a JSON parsing
       + Memoria conversacional (ventana deslizante)
       + Sin _conversar hardcodeado (todo por LLM)
       + Seguridad en comandos
       + Herramientas nuevas (grep, procesos, web)

MODELOS RECOMENDADOS:
  - qwen3:4b          → 4GB VRAM, tool calling nativo, rapido
  - qwen3-coder       → optimizado para codigo
  - qwen2.5:14b       → fallback si no tienes qwen3
  - qwen3:30b-a3b     → 3B activos de 30B, mejor razonamiento (12GB)

ARQUITECTURA:
  Usuario → Mensaje + Memoria → ReAct Loop
                                    ↓
                              LLM piensa con herramientas
                                    ↓
                         ¿Llama herramienta? → Ejecuta → Observa → Vuelve a pensar
                         ¿Responde? → Devuelve al usuario
                                    ↓
                         Si falla → Reintenta con enfoque diferente
                         Si se atasca → Consulta cloud
                                    ↓
                         Evaluación → Aprendizaje
=============================================================
"""

import streamlit as st
import subprocess
import os
import re
import json
import platform
import hashlib
from datetime import datetime
from pathlib import Path

# ============================================================
# CONFIGURACION
# ============================================================

# MODELO: qwen3 tiene tool calling nativo y es mas inteligente
# Si no tienes qwen3, usa qwen2.5:14b como fallback
AGENT_MODEL = "qwen3:4b"       # Cambiar a tu modelo disponible
FALLBACK_MODEL = "qwen2.5:14b"  # Si el principal no esta
CHAT_MODEL = "llama3.1:8b"

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
    "rd /s /q", "taskkill /f /pid system"
]


# ============================================================
# HERRAMIENTAS - Funciones que EJECUTAN de verdad
# ============================================================

def ejecutar_comando(comando: str, cwd: str = None, confirmar_peligroso: bool = False) -> str:
    """Ejecuta un comando en la terminal con VALIDACION de seguridad."""
    cmd_lower = comando.lower()

    # Validar comandos peligrosos
    for peligro in COMANDOS_PELIGROSOS:
        if peligro in cmd_lower:
            if not confirmar_peligroso:
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
    rutas_posibles = [ruta]
    if not os.path.isabs(ruta):
        rutas_posibles.append(os.path.join(REPOS_DIR, ruta))
        try:
            for d in os.listdir(REPOS_DIR):
                rutas_posibles.append(os.path.join(REPOS_DIR, d, ruta))
        except:
            pass

    for r in rutas_posibles:
        if os.path.exists(r) and os.path.isfile(r):
            try:
                with open(r, "r", encoding="utf-8", errors="replace") as f:
                    contenido = f.read()
                if len(contenido) > 8000:
                    contenido = contenido[:8000] + "\n... [truncado]"
                return contenido
            except Exception as e:
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
    except Exception as e:
        return f"ERROR: {e}"


def escribir_archivo(ruta: str, contenido: str) -> str:
    try:
        dir_name = os.path.dirname(ruta)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        return f"Archivo escrito: {ruta}"
    except Exception as e:
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
    nombre_lower = nombre.lower().strip()
    for prefix in ["abre ", "abrir ", "open ", "inicia ", "lanza ", "mi "]:
        if nombre_lower.startswith(prefix):
            nombre_lower = nombre_lower[len(prefix):]
            break

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


def buscar_exe(nombre: str) -> str:
    nombre_lower = nombre.lower().strip()
    for prefix in ["abre ", "abrir ", "open ", "inicia ", "lanza ", "mi "]:
        if nombre_lower.startswith(prefix):
            nombre_lower = nombre_lower[len(prefix):]
            break

    shortcut = buscar_en_start_menu(nombre)
    if shortcut:
        return shortcut

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


def abrir_aplicacion(app: str) -> str:
    app_clean = app.lower().strip()
    for prefix in ["abre ", "abrir ", "open ", "inicia ", "lanza ", "mi "]:
        if app_clean.startswith(prefix):
            app_clean = app_clean[len(prefix):]
            break

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


def generar_codigo(descripcion: str, tipo: str, ruta: str) -> str:
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
            "description": "Abre una aplicacion por nombre. Busca automaticamente en Start Menu, registro y disco. No necesitas saber el .exe exacto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "Nombre de la aplicacion (ej: whatsapp, chrome, autocad)"}
                },
                "required": ["app"]
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
        msg_lower = user_message.lower() if False else user_msg.lower()
        relevant = []
        for c in corrections:
            if any(w in msg_lower for w in c["user_message"].lower().split() if len(w) > 3):
                relevant.append(c)
        return relevant[-5:]

    def get_stats(self):
        return {
            "knowledge": len(self._load(KNOWLEDGE_FILE, [])),
            "corrections": len(self._load(CORRECTIONS_FILE, [])),
            "patterns": len(self._load(PATTERNS_FILE, [])),
            "feedback": len(self._load(FEEDBACK_FILE, [])),
        }

learning = LearningSystem()


# ============================================================
# LLM - Conexion a Ollama con 4 metodos
# ============================================================

def _llm_generate(messages: list, tools: list = None) -> str:
    """Consulta al LLM local. Funcion modular, usada por todo el agente."""
    try:
        import ollama

        # Intentar con function calling nativo si hay tools
        if tools:
            for host in ['http://localhost:11434', 'http://127.0.0.1:11434']:
                try:
                    client = ollama.Client(host=host)
                    response = client.chat(model=AGENT_MODEL, messages=messages, tools=tools)
                    return response  # Retorna el objeto completo (con tool_calls)
                except Exception:
                    continue

        # Sin tools, o fallback sin function calling
        for host in ['http://localhost:11434', 'http://127.0.0.1:11434']:
            try:
                client = ollama.Client(host=host)
                response = client.chat(model=AGENT_MODEL, messages=messages)
                return response.get("message", {}).get("content", "")
            except Exception:
                continue

        try:
            response = ollama.chat(model=AGENT_MODEL, messages=messages)
            return response.get("message", {}).get("content", "")
        except Exception:
            pass

        # HTTP directo como ultimo recurso
        try:
            import urllib.request
            data = json.dumps({
                "model": AGENT_MODEL, "messages": messages, "stream": False
            }).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:11434/api/chat",
                data=data, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("message", {}).get("content", "")
        except Exception:
            pass

        return ""

    except ImportError:
        return ""


# ============================================================
# CEREBRO ReAct - El motor principal v11
# ============================================================

SYSTEM_PROMPT = """Eres un agente autonomo INTELIGENTE que vive en la computadora del usuario.

Tu trabajo es ayudarlo con CUALQUIER cosa. Tienes herramientas para:
- Abrir aplicaciones, ejecutar comandos, leer/escribir archivos
- Generar codigo completo (juegos, paginas web, scripts)
- Clonar repos, instalar dependencias, analizar proyectos
- Buscar en archivos, ver procesos, buscar en internet
- Matar procesos que se cuelgan

REGLAS:
1. PIENSA antes de actuar. Analiza que quiere el usuario.
2. Si pide CREAR algo (juego, pagina, script) → usa generar_codigo
3. Si pide ABRIR algo → usa abrir_aplicacion
4. Si algo falla → intenta un enfoque diferente
5. Si no sabes algo → busca en internet
6. NUNCA inventes rutas o comandos — usa las herramientas para verificar
7. Habla en espanol, de forma natural y concisa

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
- abrir_aplicacion(app) - Abre una app por nombre
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
                # Guardar en memoria
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "assistant", "content": final_response})
                # Mantener ventana deslizante
                if len(self.conversation_history) > MAX_CONVERSATION_MEMORY * 2:
                    self.conversation_history = self.conversation_history[-(MAX_CONVERSATION_MEMORY * 2):]
                return final_response, self.thinking_log

            elif action_result[0] == "tool_call":
                tool_name = action_result[1]
                tool_params = action_result[2]

                # Ejecutar la herramienta
                self._log(f"Ejecutando: {tool_name}({tool_params})", "execution")
                tool_result = self._execute_tool(tool_name, tool_params)
                self._log(f"Resultado: {tool_result[:150]}...", "observation")

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
        """Construye la lista de mensajes con memoria conversacional."""
        # System prompt con contexto
        models = self._get_available_models()
        corrections = learning.get_corrections_for(new_message)
        corrections_text = ""
        if corrections:
            corrections_text = "\n".join([
                f"- NO hagas '{c['wrong_action']}' cuando el usuario dice '{c['user_message']}'. "
                f"Haz '{c['correct_action']}' en su lugar."
                for c in corrections
            ])
        else:
            corrections_text = "Ninguna aun"

        system_content = SYSTEM_PROMPT.format(
            so=platform.system(),
            repos_dir=REPOS_DIR,
            models=", ".join(models) if models else AGENT_MODEL,
            corrections=corrections_text
        )

        # Inyectar conocimiento relevante
        relevant_knowledge = learning.get_knowledge(new_message)
        if relevant_knowledge:
            knowledge_text = "\n".join([f"- {k['content']}" for k in relevant_knowledge[:5]])
            system_content += f"\n\nConocimiento relevante:\n{knowledge_text}"

        messages = [{"role": "system", "content": system_content}]

        # Agregar historial de conversacion (ventana deslizante)
        recent_history = self.conversation_history[-MAX_CONVERSATION_MEMORY:]
        for msg in recent_history:
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
        """Detecta si el modelo soporta function calling nativo."""
        try:
            import ollama
            client = ollama.Client(host='http://localhost:11434')
            # Test simple con tools
            response = client.chat(
                model=AGENT_MODEL,
                messages=[{"role": "user", "content": "test"}],
                tools=[TOOL_SCHEMAS[0]]  # Solo 1 tool para test
            )
            # Si no crashea, soporta tool calling
            return True
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
        page_title="Agente Autonomo v11",
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

    st.markdown('<div class="main-title">Agente Autonomo v11</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">ReAct: Piensa → Actua → Observa → Piensa de nuevo</div>', unsafe_allow_html=True)

    # === SIDEBAR ===
    with st.sidebar:
        st.header("Config")
        st.write(f"**Modelo agente:** {AGENT_MODEL}")
        st.write(f"**Modelo fallback:** {FALLBACK_MODEL}")
        st.write(f"**Directorio:** {REPOS_DIR}")
        st.write(f"**Tool calling:** {'Nativo' if agent.supports_tool_calling else 'JSON fallback' if agent.supports_tool_calling is False else 'Sin detectar'}")

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
                # Verificar si el modelo configurado esta disponible
                if AGENT_MODEL not in models and not any(AGENT_MODEL in m for m in models):
                    st.warning(f"Modelo '{AGENT_MODEL}' no encontrado. Disponibles: {', '.join(models[:5])}")
        except:
            st.error("Ollama NO conecta")

        stats = learning.get_stats()
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
