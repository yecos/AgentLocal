"""
=============================================================
 AGENTE LOCAL AUTÓNOMO v4 - EJECUCIÓN GARANTIZADA
 Enfoque híbrido: Detección de intención + Ejecución directa
=============================================================

ESTA VERSIÓN ES DIFERENTE:
- Detecta la intención del usuario ANTES de enviar al LLM
- Si la intención es clara (ej: URL de GitHub), EJECUTA directamente
- El LLM solo se usa para análisis y decisiones complejas
- NUNCA da instrucciones - SIEMPRE ejecuta

Modelo: qwen2.5:14b (agente con herramientas)
Puerto: 8501
=============================================================
"""

import streamlit as st
import ollama
import subprocess
import os
import re
import json
import shutil
import platform
from datetime import datetime
from pathlib import Path

# ============================================================
# CONFIGURACIÓN
# ============================================================

AGENT_MODEL = "qwen2.5:14b"
CHAT_MODEL = "llama3.1:8b"
MAX_ITERATIONS = 8
HISTORY_FILE = "chat_history.json"

# Directorio base para operaciones
if platform.system() == "Windows":
    BASE_DIR = os.path.expanduser("~")
    REPOS_DIR = os.path.join(BASE_DIR, "Documents")
else:
    BASE_DIR = os.path.expanduser("~")
    REPOS_DIR = os.path.join(BASE_DIR, "repos")

# Asegurar que el directorio de repos existe
os.makedirs(REPOS_DIR, exist_ok=True)

# ============================================================
# HERRAMIENTAS REALES - Funciones que EJECUTAN
# ============================================================

def ejecutar_comando(comando: str) -> str:
    """Ejecuta un comando en la terminal y devuelve la salida."""
    try:
        # Detectar si es Windows
        is_windows = platform.system() == "Windows"
        if is_windows:
            result = subprocess.run(
                comando, shell=True, capture_output=True, text=True,
                timeout=120, cwd=REPOS_DIR
            )
        else:
            result = subprocess.run(
                comando, shell=True, capture_output=True, text=True,
                timeout=120, cwd=REPOS_DIR
            )
        output = ""
        if result.stdout:
            output += result.stdout.strip()
        if result.stderr:
            output += ("\n--- STDERR ---\n" + result.stderr.strip()) if output else result.stderr.strip()
        if not output:
            output = "Comando ejecutado (sin salida)."
        return output
    except subprocess.TimeoutExpired:
        return "Error: El comando tardó demasiado (>120s). Se canceló."
    except Exception as e:
        return f"Error ejecutando comando: {e}"


def clonar_repositorio(url: str) -> str:
    """Clona un repositorio Git y devuelve el resultado."""
    # Extraer nombre del repo de la URL
    repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
    target_dir = os.path.join(REPOS_DIR, repo_name)

    # Verificar si ya existe
    if os.path.exists(target_dir):
        return f"El repositorio ya existe en: {target_dir}\nPara actualizar, primero elimínalo o usa 'git pull' dentro del directorio."

    # Ejecutar git clone
    comando = f'git clone {url} "{target_dir}"'
    resultado = ejecutar_comando(comando)

    # Verificar que se clonó correctamente
    if os.path.exists(target_dir):
        # Listar contenido para confirmar
        try:
            contenido = os.listdir(target_dir)
            archivos = [f for f in contenido if os.path.isfile(os.path.join(target_dir, f))]
            carpetas = [f for f in contenido if os.path.isdir(os.path.join(target_dir, f))]
            resumen = f"Repositorio clonado exitosamente en: {target_dir}\n\n"
            resumen += f"Carpetas: {', '.join(carpetas)}\n"
            resumen += f"Archivos: {', '.join(archivos)}"
            return resumen
        except Exception:
            return f"Repositorio clonado en: {target_dir}\n{resultado}"
    else:
        return f"Error al clonar. Salida del comando:\n{resultado}"


def instalar_dependencias(ruta: str = None, gestor: str = "auto") -> str:
    """Instala dependencias de un proyecto (npm, pip, etc.)."""
    if ruta is None:
        ruta = REPOS_DIR

    if not os.path.exists(ruta):
        return f"La ruta no existe: {ruta}"

    # Detectar gestor de paquetes
    if gestor == "auto":
        if os.path.exists(os.path.join(ruta, "package.json")):
            gestor = "npm"
        elif os.path.exists(os.path.join(ruta, "requirements.txt")):
            gestor = "pip"
        elif os.path.exists(os.path.join(ruta, "Pipfile")):
            gestor = "pipenv"
        elif os.path.exists(os.path.join(ruta, "pyproject.toml")):
            gestor = "poetry"
        else:
            return "No se detectó gestor de paquetes (package.json, requirements.txt, etc.)"

    comandos = {
        "npm": f'cd "{ruta}" && npm install',
        "yarn": f'cd "{ruta}" && yarn install',
        "pip": f'cd "{ruta}" && pip install -r requirements.txt',
        "pipenv": f'cd "{ruta}" && pipenv install',
        "poetry": f'cd "{ruta}" && poetry install',
    }

    comando = comandos.get(gestor, f'cd "{ruta}" && {gestor} install')
    return ejecutar_comando(comando)


def leer_archivo(ruta: str) -> str:
    """Lee el contenido de un archivo de texto."""
    if not os.path.exists(ruta):
        # Intentar buscar en directorios comunes
        posibles = [
            ruta,
            os.path.join(REPOS_DIR, ruta),
        ]
        # Si es una ruta relativa, buscar en subdirectorios
        for repo_dir in os.listdir(REPOS_DIR):
            full_path = os.path.join(REPOS_DIR, repo_dir, ruta)
            if os.path.exists(full_path):
                ruta = full_path
                break
        else:
            # Último intento con búsqueda
            if not os.path.exists(ruta):
                return f"El archivo no existe: {ruta}"

    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            contenido = f.read()
        # Limitar tamaño
        if len(contenido) > 10000:
            contenido = contenido[:10000] + "\n\n... [Archivo truncado - muy largo] ..."
        return contenido
    except Exception as e:
        return f"Error leyendo archivo: {e}"


def listar_archivos(ruta: str = None) -> str:
    """Lista archivos y carpetas en un directorio."""
    if ruta is None:
        ruta = REPOS_DIR

    # Intentar encontrar la ruta
    if not os.path.exists(ruta):
        # Buscar en REPOS_DIR
        alt = os.path.join(REPOS_DIR, ruta)
        if os.path.exists(alt):
            ruta = alt
        else:
            return f"El directorio no existe: {ruta}"

    try:
        items = os.listdir(ruta)
        carpetas = []
        archivos = []
        for item in sorted(items):
            full = os.path.join(ruta, item)
            if os.path.isdir(full):
                carpetas.append(item)
            else:
                archivos.append(item)

        resultado = f"Contenido de {ruta}:\n\n"
        for c in carpetas:
            resultado += f"  [CARPETA] {c}\n"
        for a in archivos:
            size = os.path.getsize(os.path.join(ruta, a))
            resultado += f"  [ARCHIVO] {a} ({size} bytes)\n"
        resultado += f"\nTotal: {len(carpetas)} carpetas, {len(archivos)} archivos"
        return resultado
    except Exception as e:
        return f"Error listando directorio: {e}"


def escribir_archivo(ruta: str, contenido: str) -> str:
    """Escribe contenido en un archivo."""
    try:
        os.makedirs(os.path.dirname(ruta) if os.path.dirname(ruta) else ".", exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        return f"Archivo escrito exitosamente: {ruta}"
    except Exception as e:
        return f"Error escribiendo archivo: {e}"


def buscar_texto(patron: str, ruta: str = None) -> str:
    """Busca un patrón de texto en archivos."""
    if ruta is None:
        ruta = REPOS_DIR
    if not os.path.exists(ruta):
        ruta = os.path.join(REPOS_DIR, ruta) if not os.path.isabs(ruta) else ruta

    comando = f'findstr /S /I /N "{patron}" "{ruta}\\*" 2>nul' if platform.system() == "Windows" else f'grep -r -n "{patron}" "{ruta}" 2>/dev/null'
    return ejecutar_comando(comando)


def analizar_proyecto(ruta: str = None) -> str:
    """Analiza la estructura de un proyecto y devuelve un resumen."""
    if ruta is None:
        ruta = REPOS_DIR

    if not os.path.exists(ruta):
        alt = os.path.join(REPOS_DIR, ruta) if not os.path.isabs(ruta) else ruta
        if os.path.exists(alt):
            ruta = alt
        else:
            return f"El directorio no existe: {ruta}"

    resultado = f"Análisis del proyecto en: {ruta}\n"
    resultado += "=" * 50 + "\n\n"

    # Listar estructura de directorios (2 niveles)
    for root, dirs, files in os.walk(ruta):
        level = root.replace(ruta, "").count(os.sep)
        if level > 2:  # Limitar profundidad
            continue
        indent = "  " * level
        resultado += f"{indent}{os.path.basename(root)}/\n"
        subindent = "  " * (level + 1)
        for f in sorted(files)[:15]:  # Limitar archivos por carpeta
            resultado += f"{subindent}{f}\n"
        if len(files) > 15:
            resultado += f"{subindent}... y {len(files) - 15} archivos más\n"

    # Detectar tipo de proyecto
    resultado += "\n" + "=" * 50 + "\nDetección automática:\n"

    checks = {
        "package.json": "Proyecto Node.js/JavaScript",
        "tsconfig.json": "Proyecto TypeScript",
        "next.config.js": "Proyecto Next.js",
        "next.config.ts": "Proyecto Next.js",
        "requirements.txt": "Proyecto Python (pip)",
        "pyproject.toml": "Proyecto Python (poetry/pyproject)",
        "Dockerfile": "Proyecto con Docker",
        "docker-compose.yml": "Proyecto con Docker Compose",
        ".git": "Repositorio Git",
        "README.md": "Tiene documentación README",
        ".env.example": "Tiene variables de entorno de ejemplo",
    }

    for filename, desc in checks.items():
        if os.path.exists(os.path.join(ruta, filename)):
            resultado += f"  - {desc} ({filename})\n"

    # Leer package.json si existe
    pkg_path = os.path.join(ruta, "package.json")
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            resultado += f"\npackage.json:\n"
            resultado += f"  Nombre: {pkg.get('name', 'N/A')}\n"
            resultado += f"  Versión: {pkg.get('version', 'N/A')}\n"
            resultado += f"  Descripción: {pkg.get('description', 'N/A')}\n"
            deps = pkg.get("dependencies", {})
            dev_deps = pkg.get("devDependencies", {})
            if deps:
                resultado += f"  Dependencias: {', '.join(deps.keys())}\n"
            if dev_deps:
                resultado += f"  Dev Dependencies: {', '.join(dev_deps.keys())}\n"
            scripts = pkg.get("scripts", {})
            if scripts:
                resultado += f"  Scripts: {', '.join(scripts.keys())}\n"
        except Exception:
            pass

    # Leer README.md si existe
    readme_path = os.path.join(ruta, "README.md")
    if os.path.exists(readme_path):
        try:
            with open(readme_path, "r", encoding="utf-8") as f:
                readme = f.read()
            if len(readme) > 2000:
                readme = readme[:2000] + "\n... [truncado]"
            resultado += f"\nREADME.md:\n{readme}\n"
        except Exception:
            pass

    return resultado


def ejecutar_proyecto(ruta: str = None, comando: str = None) -> str:
    """Ejecuta un proyecto (npm run dev, python main.py, etc.)."""
    if ruta is None:
        ruta = REPOS_DIR
    if not os.path.exists(ruta):
        alt = os.path.join(REPOS_DIR, ruta) if not os.path.isabs(ruta) else ruta
        if os.path.exists(alt):
            ruta = alt

    if comando:
        return ejecutar_comando(f'cd "{ruta}" && {comando}')

    # Auto-detectar
    if os.path.exists(os.path.join(ruta, "package.json")):
        return ejecutar_comando(f'cd "{ruta}" && npm run dev')
    elif os.path.exists(os.path.join(ruta, "main.py")):
        return ejecutar_comando(f'cd "{ruta}" && python main.py')
    elif os.path.exists(os.path.join(ruta, "app.py")):
        return ejecutar_comando(f'cd "{ruta}" && python app.py')
    else:
        return "No se pudo detectar cómo ejecutar el proyecto. Especifica el comando."


# ============================================================
# DETECCIÓN DE INTENCIÓN - El corazón de v4
# ============================================================

class IntentDetector:
    """
    Detecta la intención del usuario ANTES de enviar al LLM.
    Si la intención es clara, ejecuta directamente.
    """

    # Patrones de URL de GitHub
    GITHUB_PATTERN = re.compile(
        r'https?://github\.com/[\w\-]+/[\w\-\.]+(?:\.git)?',
        re.IGNORECASE
    )

    # Patrones de intención
    INTENT_PATTERNS = {
        "clonar": [
            r'\b(clon[aá]r?|clone|descarg[aá]r?|download|bajar)\b.*\b(repo|repositorio|proyecto|c[oó]digo)\b',
            r'\b(repo|repositorio)\b.*\b(clon[aá]r?|descarg[aá]r?|download)\b',
            r'github\.com/[\w\-]+/[\w\-\.]+',  # Cualquier URL de GitHub
        ],
        "instalar": [
            r'\b(instal[aá]r?|install|configur[aá]r?|setup|dependencias|dependencies)\b',
            r'\bnpm\s+install\b',
            r'\bpip\s+install\b',
        ],
        "leer": [
            r'\b(le[eé]r?|read|mostr[aá]r?|show|ver|conteni?do|c[oó]digo)\b.*\b(archivo|file|c[oó]digo|fuente|source)\b',
            r'\b(qu[eé]|what)\b.*\b(hay|contiene|tiene|inside)\b.*\b(archivo|file|repo|proyecto)\b',
        ],
        "listar": [
            r'\b(list[aá]r?|ls|dir|mostr[aá]r?)\b.*\b(archivo|files|carpeta|folder|directorio|directory|contenido)\b',
            r'\b(qu[eé]\s+hay)\b.*\b(carpeta|directorio|folder|dentro)\b',
        ],
        "analizar": [
            r'\b(analiz[aá]r?|analyze|revis[aá]r?|review|examin[aá]r?|examine|estudi[aá]r?)\b.*\b(proyecto|repo|c[oó]digo|code)\b',
            r'\b(qu[eé]\s+(es|hace|tiene))\b.*\b(proyecto|repo|esto)\b',
        ],
        "ejecutar": [
            r'\b(ejecut[aá]r?|run|correr|inici[aá]r?|start|levant[aá]r?)\b.*\b(proyecto|app|servidor|server|c[oó]digo)\b',
            r'\bnpm\s+run\b',
            r'\bnpm\s+start\b',
            r'\bnpm\s+dev\b',
        ],
        "comando": [
            r'\b(ejecut[aá]r?|run|correr)\b.*\b(comando|command|terminal|consola|cmd|shell)\b',
        ],
        "buscar": [
            r'\b(busc[aá]r?|search|encontr[aá]r?|find|buscar)\b.*\b(texto|cadena|string|patr[oó]n|pattern|archivo|file)\b',
        ],
        "escribir": [
            r'\b(cre[aá]r?|create|escrib[aá]r?|write|modific[aá]r?|modify|edit[aá]r?)\b.*\b(archivo|file|fichero)\b',
        ],
    }

    @classmethod
    def detect(cls, message: str) -> dict:
        """
        Detecta la intención del usuario.
        Retorna: {"intent": str, "params": dict, "confidence": float}
        """
        message_lower = message.lower()

        # 1. Detectar URLs de GitHub - PRIORIDAD MÁXIMA
        github_urls = cls.GITHUB_PATTERN.findall(message)
        if github_urls:
            url = github_urls[0]
            # Si hay URL de GitHub, casi siempre quieren clonar
            return {
                "intent": "clonar",
                "params": {"url": url},
                "confidence": 0.95
            }

        # 2. Detectar otras intenciones por patrones
        best_intent = None
        best_confidence = 0.0

        for intent, patterns in cls.INTENT_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, message_lower)
                if match:
                    confidence = 0.7 + (0.1 * len(match.group()) / max(len(message), 1))
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_intent = intent

        # 3. Extraer parámetros según la intención
        params = {}
        if best_intent:
            params = cls._extract_params(message, best_intent)

        if best_intent and best_confidence >= 0.6:
            return {
                "intent": best_intent,
                "params": params,
                "confidence": best_confidence
            }

        # 4. No se detectó intención clara
        return {
            "intent": "conversar",
            "params": {},
            "confidence": 0.0
        }

    @classmethod
    def _extract_params(cls, message: str, intent: str) -> dict:
        """Extrae parámetros del mensaje según la intención."""
        params = {}

        if intent == "clonar":
            urls = cls.GITHUB_PATTERN.findall(message)
            if urls:
                params["url"] = urls[0]

        elif intent == "leer":
            # Buscar rutas de archivo
            file_patterns = [
                r'[\w\\/:]+\.\w+',  # Rutas con extensión
                r'"([^"]+)"',  # Entre comillas
                r"'([^']+)'",
            ]
            for pattern in file_patterns:
                match = re.search(pattern, message)
                if match:
                    params["ruta"] = match.group(1) if match.lastindex else match.group(0)
                    break

        elif intent == "listar":
            # Buscar ruta de directorio
            dir_match = re.search(r'(?:en|de|del|in)\s+([\w\\:]+)', message)
            if dir_match:
                params["ruta"] = dir_match.group(1)

        elif intent == "analizar":
            # Buscar nombre de proyecto o ruta
            repo_match = cls.GITHUB_PATTERN.findall(message)
            if repo_match:
                params["url"] = repo_match[0]
                params["repo_name"] = repo_match[0].rstrip("/").split("/")[-1].replace(".git", "")

        elif intent == "ejecutar":
            # Buscar comando específico
            cmd_match = re.search(r'(?:comando|cmd|run)\s+[:=]?\s*([^\.,]+)', message, re.IGNORECASE)
            if cmd_match:
                params["comando"] = cmd_match.group(1).strip()

        elif intent == "comando":
            # Extraer el comando a ejecutar
            cmd_match = re.search(r'(?:ejecutar|run|correr)\s+["\']?([^"\']+?)["\']?\s*$', message, re.IGNORECASE)
            if cmd_match:
                params["comando"] = cmd_match.group(1).strip()
            else:
                # Buscar comandos comunes
                for cmd_prefix in ["git ", "npm ", "pip ", "python ", "node ", "cd "]:
                    if cmd_prefix in message.lower():
                        idx = message.lower().find(cmd_prefix)
                        params["comando"] = message[idx:].strip()
                        break

        return params


# ============================================================
# EJECUTOR DIRECTO - Ejecuta sin pasar por el LLM
# ============================================================

class DirectExecutor:
    """
    Ejecuta acciones directamente basándose en la intención detectada.
    NO necesita el LLM para acciones obvias.
    """

    @staticmethod
    def execute(intent_data: dict) -> dict:
        """
        Ejecuta una acción directamente.
        Retorna: {"success": bool, "tool": str, "result": str, "details": dict}
        """
        intent = intent_data["intent"]
        params = intent_data["params"]

        if intent == "clonar":
            url = params.get("url")
            if url:
                result = clonar_repositorio(url)
                repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
                return {
                    "success": True,
                    "tool": "clonar_repositorio",
                    "result": result,
                    "details": {"url": url, "repo_name": repo_name, "path": os.path.join(REPOS_DIR, repo_name)}
                }
            return {"success": False, "tool": "clonar_repositorio", "result": "No se encontró URL de GitHub", "details": {}}

        elif intent == "instalar":
            ruta = params.get("ruta", REPOS_DIR)
            # Si params tiene repo_name, buscar esa carpeta
            if "repo_name" in params:
                ruta = os.path.join(REPOS_DIR, params["repo_name"])
            gestor = params.get("gestor", "auto")
            result = instalar_dependencias(ruta, gestor)
            return {"success": True, "tool": "instalar_dependencias", "result": result, "details": {"ruta": ruta}}

        elif intent == "leer":
            ruta = params.get("ruta", "")
            if ruta:
                result = leer_archivo(ruta)
                return {"success": True, "tool": "leer_archivo", "result": result, "details": {"ruta": ruta}}
            return {"success": False, "tool": "leer_archivo", "result": "No se especificó archivo", "details": {}}

        elif intent == "listar":
            ruta = params.get("ruta", REPOS_DIR)
            result = listar_archivos(ruta)
            return {"success": True, "tool": "listar_archivos", "result": result, "details": {"ruta": ruta}}

        elif intent == "analizar":
            repo_name = params.get("repo_name")
            ruta = os.path.join(REPOS_DIR, repo_name) if repo_name else REPOS_DIR
            result = analizar_proyecto(ruta)
            return {"success": True, "tool": "analizar_proyecto", "result": result, "details": {"ruta": ruta}}

        elif intent == "ejecutar":
            ruta = params.get("ruta", REPOS_DIR)
            comando = params.get("comando")
            result = ejecutar_proyecto(ruta, comando)
            return {"success": True, "tool": "ejecutar_proyecto", "result": result, "details": {"ruta": ruta}}

        elif intent == "comando":
            comando = params.get("comando")
            if comando:
                result = ejecutar_comando(comando)
                return {"success": True, "tool": "ejecutar_comando", "result": result, "details": {"comando": comando}}
            return {"success": False, "tool": "ejecutar_comando", "result": "No se especificó comando", "details": {}}

        elif intent == "buscar":
            patron = params.get("patron", "")
            ruta = params.get("ruta", REPOS_DIR)
            if patron:
                result = buscar_texto(patron, ruta)
                return {"success": True, "tool": "buscar_texto", "result": result, "details": {"patron": patron}}
            return {"success": False, "tool": "buscar_texto", "result": "No se especificó patrón de búsqueda", "details": {}}

        elif intent == "escribir":
            ruta = params.get("ruta", "")
            contenido = params.get("contenido", "")
            if ruta:
                result = escribir_archivo(ruta, contenido)
                return {"success": True, "tool": "escribir_archivo", "result": result, "details": {"ruta": ruta}}
            return {"success": False, "tool": "escribir_archivo", "result": "No se especificó ruta", "details": {}}

        return {"success": False, "tool": "none", "result": "Intención no reconocida", "details": {}}


# ============================================================
# AGENTE LLM - Para análisis y decisiones complejas
# ============================================================

SYSTEM_PROMPT = """Eres un agente autónomo que EJECUTA acciones reales en la computadora del usuario.

REGLAS CRÍTICAS:
1. NUNCA des instrucciones al usuario. NUNCA digas "puedes hacer..." o "ejecuta el comando..."
2. TÚ ejecutas los comandos. TÚ clonas repos. TÚ lees archivos. TÚ instalas dependencias.
3. Si el usuario pide algo, lo HACES, no lo explicas.
4. Cuando ejecutes una herramienta, reporta el RESULTADO de la ejecución.
5. Habla en español siempre.
6. Sé conciso y directo. No repitas lo que ya se hizo.

HERRAMIENTAS DISPONIBLES:
- ejecutar_comando: Ejecuta cualquier comando en la terminal
- clonar_repositorio: Clona un repo de GitHub
- instalar_dependencias: Instala dependencias (npm, pip, etc.)
- leer_archivo: Lee el contenido de un archivo
- listar_archivos: Lista archivos en un directorio
- escribir_archivo: Crea o modifica un archivo
- buscar_texto: Busca texto en archivos
- analizar_proyecto: Analiza estructura de un proyecto
- ejecutar_proyecto: Ejecuta un proyecto

FORMATO DE RESPUESTA:
- Reporta qué hiciste y el resultado
- Si algo falló, explica por qué y qué intentarías después
- NO digas "puedes hacer X" - DI "voy a hacer X" o "hecho: X"
"""


def llm_chat(messages: list, tools: list = None) -> dict:
    """Envía un mensaje al LLM y obtiene la respuesta."""
    try:
        if tools:
            response = ollama.chat(
                model=AGENT_MODEL,
                messages=messages,
                tools=tools
            )
        else:
            response = ollama.chat(
                model=AGENT_MODEL,
                messages=messages
            )
        return response
    except Exception as e:
        return {"error": str(e)}


def llm_analyze(context: str, question: str) -> str:
    """Usa el LLM solo para análisis, no para ejecución."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Contexto:\n{context}\n\nPregunta: {question}"}
    ]
    try:
        response = ollama.chat(model=AGENT_MODEL, messages=messages)
        return response.get("message", {}).get("content", "Sin respuesta del modelo.")
    except Exception as e:
        return f"Error del modelo: {e}"


# ============================================================
# MOTOR PRINCIPAL - Orquesta todo
# ============================================================

def process_message(user_message: str, chat_history: list) -> str:
    """
    Procesa un mensaje del usuario con el enfoque híbrido:
    1. Detectar intención
    2. Si es clara → ejecutar directamente
    3. Si es ambigua → usar LLM con herramientas
    """

    # === PASO 1: Detectar intención ===
    intent_data = IntentDetector.detect(user_message)

    log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] Intención detectada: {intent_data['intent']} (confianza: {intent_data['confidence']:.0%})"

    # === PASO 2: Si la intención es clara, ejecutar directamente ===
    if intent_data["confidence"] >= 0.7 and intent_data["intent"] != "conversar":

        # Ejecutar la acción directamente
        exec_result = DirectExecutor.execute(intent_data)

        # Construir respuesta
        response = f"**Acción ejecutada: {exec_result['tool']}**\n\n"

        if exec_result["success"]:
            response += f"Resultado:\n```\n{exec_result['result']}\n```"

            # Si fue clonar, preguntar si quiere analizar
            if intent_data["intent"] == "clonar" and exec_result["details"].get("repo_name"):
                repo_name = exec_result["details"]["repo_name"]
                repo_path = exec_result["details"].get("path", os.path.join(REPOS_DIR, repo_name))
                # Auto-analizar después de clonar
                analysis = analizar_proyecto(repo_path)
                response += f"\n\n---\n**Análisis automático del proyecto:**\n```\n{analysis}\n```"

            # Si fue analizar, ofrecer siguiente paso
            elif intent_data["intent"] == "analizar":
                response += "\n\n¿Quieres que instale las dependencias o revise algún archivo específico?"
        else:
            response += f"Error: {exec_result['result']}"

        return response, log_entry

    # === PASO 3: Si la intención NO es clara, usar LLM con herramientas ===
    else:

        # Definir herramientas para Ollama native tool calling
        ollama_tools = [
            {
                "type": "function",
                "function": {
                    "name": "ejecutar_comando",
                    "description": "Ejecuta un comando en la terminal del sistema. Úsalo para cualquier operación que requiera la consola.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "comando": {
                                "type": "string",
                                "description": "El comando exacto a ejecutar en la terminal (ej: 'git status', 'npm install', 'dir')"
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
                    "description": "Clona un repositorio de GitHub a la computadora local. Úsalo cuando el usuario quiera descargar un repo.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "La URL del repositorio de GitHub (ej: 'https://github.com/usuario/repo')"
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
                    "description": "Instala las dependencias de un proyecto. Detecta automáticamente npm, pip, etc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ruta": {
                                "type": "string",
                                "description": "Ruta al directorio del proyecto"
                            },
                            "gestor": {
                                "type": "string",
                                "description": "Gestor de paquetes: npm, pip, yarn, pipenv, poetry, o auto"
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
                    "description": "Lee y muestra el contenido de un archivo de texto.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ruta": {
                                "type": "string",
                                "description": "Ruta al archivo que se quiere leer"
                            }
                        },
                        "required": ["ruta"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "listar_archivos",
                    "description": "Lista los archivos y carpetas en un directorio.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ruta": {
                                "type": "string",
                                "description": "Ruta del directorio a listar"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analizar_proyecto",
                    "description": "Analiza la estructura completa de un proyecto y muestra un resumen detallado.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ruta": {
                                "type": "string",
                                "description": "Ruta al directorio del proyecto"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "escribir_archivo",
                    "description": "Crea o modifica un archivo con el contenido especificado.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ruta": {
                                "type": "string",
                                "description": "Ruta del archivo a crear o modificar"
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
                    "name": "buscar_texto",
                    "description": "Busca un patrón de texto en los archivos de un directorio.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "patron": {
                                "type": "string",
                                "description": "Patrón de texto a buscar"
                            },
                            "ruta": {
                                "type": "string",
                                "description": "Directorio donde buscar"
                            }
                        },
                        "required": ["patron"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "ejecutar_proyecto",
                    "description": "Ejecuta un proyecto (npm run dev, python main.py, etc.).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ruta": {
                                "type": "string",
                                "description": "Ruta al proyecto"
                            },
                            "comando": {
                                "type": "string",
                                "description": "Comando específico para ejecutar (opcional, se auto-detecta si no se especifica)"
                            }
                        },
                        "required": ["ruta"]
                    }
                }
            },
        ]

        # Mapeo de nombres a funciones
        function_map = {
            "ejecutar_comando": ejecutar_comando,
            "clonar_repositorio": clonar_repositorio,
            "instalar_dependencias": instalar_dependencias,
            "leer_archivo": leer_archivo,
            "listar_archivos": listar_archivos,
            "analizar_proyecto": analizar_proyecto,
            "escribir_archivo": escribir_archivo,
            "buscar_texto": buscar_texto,
            "ejecutar_proyecto": ejecutar_proyecto,
        }

        # Construir mensajes para el LLM
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Añadir historial reciente (últimos 6 mensajes)
        for msg in chat_history[-6:]:
            messages.append(msg)

        messages.append({"role": "user", "content": user_message})

        # Bucle de tool calling
        final_response = ""
        tool_results = []

        for iteration in range(MAX_ITERATIONS):
            try:
                response = ollama.chat(
                    model=AGENT_MODEL,
                    messages=messages,
                    tools=ollama_tools
                )
            except Exception as e:
                final_response = f"Error del modelo: {e}"
                break

            msg = response.get("message", {})

            # Si no hay tool calls, es la respuesta final
            if not msg.get("tool_calls"):
                final_response = msg.get("content", "")
                # Filtrar instrucciones del texto
                final_response = filter_instructions(final_response)
                break

            # Procesar tool calls
            for tool_call in msg.get("tool_calls", []):
                func_name = tool_call.get("function", {}).get("name")
                func_args = tool_call.get("function", {}).get("arguments", {})

                # Buscar y ejecutar la función
                if func_name in function_map:
                    try:
                        result = function_map[func_name](**func_args)
                    except Exception as e:
                        result = f"Error ejecutando {func_name}: {e}"
                else:
                    result = f"Función no encontrada: {func_name}"

                tool_results.append({
                    "tool": func_name,
                    "args": func_args,
                    "result": result
                })

                # Añadir al contexto del LLM
                messages.append({"role": "assistant", "content": f"[Ejecutando {func_name}({func_args})]"})
                messages.append({"role": "user", "content": f"Resultado de {func_name}:\n{result}\n\nContinúa con la siguiente acción o responde al usuario."})

        # Si no hubo respuesta final del LLM, construir una con los resultados
        if not final_response and tool_results:
            final_response = "**Acciones ejecutadas:**\n\n"
            for tr in tool_results:
                final_response += f"- **{tr['tool']}**({tr['args']}):\n```\n{tr['result']}\n```\n\n"

        return final_response, log_entry


def filter_instructions(text: str) -> str:
    """Filtra instrucciones del texto de respuesta del LLM."""
    # Patrones de instrucciones que NO debe dar
    instruction_patterns = [
        r'puedes\s+(ejecutar|correr|instalar|clonar|usar|hacer)',
        r'tienes\s+que\s+(ejecutar|correr|instalar|clonar)',
        r'deber[ií]as\s+(ejecutar|correr|instalar|clonar)',
        r'para\s+hacerlo\s+(puedes|debes|tienes)',
        r'ejecuta\s+el\s+siguiente\s+comando',
        r'usa\s+el\s+comando',
        r'git\s+clone\s+https?://',  # No debe sugerir comandos git
        r'npm\s+install',
        r'pip\s+install',
    ]

    filtered = text
    for pattern in instruction_patterns:
        filtered = re.sub(pattern, '', filtered, flags=re.IGNORECASE)

    # Limpiar líneas vacías múltiples
    filtered = re.sub(r'\n{3,}', '\n\n', filtered)

    return filtered.strip() if filtered.strip() else text


# ============================================================
# INTERFAZ STREAMLIT
# ============================================================

def init_session():
    """Inicializa variables de sesión."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "tool_log" not in st.session_state:
        st.session_state.tool_log = []


def main():
    st.set_page_config(
        page_title="Agente Autónomo Local",
        page_icon="🤖",
        layout="wide"
    )

    # CSS personalizado
    st.markdown("""
    <style>
    .stApp { max-width: 1200px; margin: 0 auto; }
    .tool-log { background: #1a1a2e; color: #00ff88; padding: 10px; border-radius: 5px;
                font-family: monospace; font-size: 12px; max-height: 200px; overflow-y: auto; }
    .success-box { background: #0d2818; border-left: 4px solid #00ff88; padding: 10px; margin: 5px 0; border-radius: 3px; }
    .error-box { background: #2d0d0d; border-left: 4px solid #ff4444; padding: 10px; margin: 5px 0; border-radius: 3px; }
    </style>
    """, unsafe_allow_html=True)

    st.title("🤖 Agente Autónomo Local v4")
    st.caption("Ejecución garantizada - Detecta intención y actúa directamente")

    # Sidebar con info
    with st.sidebar:
        st.header("⚙️ Configuración")
        st.write(f"**Modelo agente:** {AGENT_MODEL}")
        st.write(f"**Dir. repos:** {REPOS_DIR}")
        st.write(f"**Máx. iteraciones:** {MAX_ITERATIONS}")

        if st.button("🗑️ Limpiar historial"):
            st.session_state.messages = []
            st.session_state.tool_log = []
            st.rerun()

        st.header("📋 Log de herramientas")
        if st.session_state.get("tool_log"):
            log_text = "\n".join(st.session_state.tool_log[-20:])
            st.markdown(f'<div class="tool-log">{log_text}</div>', unsafe_allow_html=True)

        st.header("📁 Repos disponibles")
        try:
            repos = [d for d in os.listdir(REPOS_DIR)
                     if os.path.isdir(os.path.join(REPOS_DIR, d)) and not d.startswith(".")]
            for repo in repos:
                st.write(f"- {repo}")
        except Exception:
            st.write("Sin repos aún")

    init_session()

    # Mostrar historial
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input del usuario
    if prompt := st.chat_input("Escribe tu mensaje..."):
        # Mostrar mensaje del usuario
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Procesar con el motor híbrido
        with st.chat_message("assistant"):
            with st.spinner("Procesando..."):
                response, log_entry = process_message(
                    prompt,
                    [{"role": m["role"], "content": m["content"]}
                     for m in st.session_state.messages[:-1]]
                )

            st.markdown(response)

        # Guardar en historial
        st.session_state.messages.append({"role": "assistant", "content": response})
        if log_entry:
            st.session_state.tool_log.append(log_entry)


if __name__ == "__main__":
    main()
