"""
=============================================================
AGENTE LOCAL AUTONOMO v10 - INTELIGENCIA CREATIVA
Piensa → Planifica → Genera → Ejecuta → Evalua → Aprende
Consulta IA cloud si necesita ayuda
=============================================================

FILOSOFIA v10:
  El agente no solo EJECUTA acciones, tambien GENERA contenido.
  Cuando el usuario pide crear algo (juego, pagina, script),
  el agente usa el LLM para GENERAR el contenido completo,
  no solo decidir que herramienta usar.

DIFERENCIA vs v9:
  v9:  Elige acciones → ejecuta. Pero escribir_archivo recibe contenido vacio.
  v10: Detecta solicitudes CREATIVAS → usa generar_contenido() para que
       el LLM genere el codigo/texto completo → luego lo escribe al archivo.
       El agente ahora puede CREAR, no solo EJECUTAR.

ARQUITECTURA v10:
  Usuario → LLM piensa (SIEMPRE)
                ↓
         Es conversacion? → Responde natural
         Es accion simple? → Planifica → Ejecuta → Evalua
         Es solicitud CREATIVA? → generar_contenido() → escribir_archivo() → abrir
                ↓
         Si falla → Busca alternativas → Consulta cloud
         Si acierta → Aprende el patron
=============================================================
"""

import streamlit as st
import subprocess
import os
import re
import json
import platform
from datetime import datetime
from pathlib import Path

# ============================================================
# CONFIGURACION
# ============================================================

AGENT_MODEL = "qwen2.5:14b"
CHAT_MODEL = "llama3.1:8b"
MAX_THINKING_ROUNDS = 5
MAX_EXECUTION_RETRIES = 3

if platform.system() == "Windows":
    REPOS_DIR = os.path.join(os.path.expanduser("~"), "Documents")
    LEARN_DIR = os.path.join(os.path.expanduser("~"), ".ia-local", "learning")
else:
    REPOS_DIR = os.path.join(os.path.expanduser("~"), "repos")
    LEARN_DIR = os.path.join(os.path.expanduser("~"), ".ia-local", "learning")

os.makedirs(REPOS_DIR, exist_ok=True)
os.makedirs(LEARN_DIR, exist_ok=True)

# Archivos de aprendizaje
CORRECTIONS_FILE = os.path.join(LEARN_DIR, "corrections.json")
FEEDBACK_FILE = os.path.join(LEARN_DIR, "feedback.json")
PATTERNS_FILE = os.path.join(LEARN_DIR, "patterns.json")
KNOWLEDGE_FILE = os.path.join(LEARN_DIR, "knowledge.json")


# ============================================================
# HERRAMIENTAS - Funciones que EJECUTAN de verdad
# ============================================================

def ejecutar_comando(comando: str, cwd: str = None) -> str:
    try:
        result = subprocess.run(
            comando, shell=True, capture_output=True, text=True,
            timeout=120, cwd=cwd or REPOS_DIR
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
        return "ERROR_TIMEOUT: Comando cancelado (>120s)"
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
    else:
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

    pkg_path = os.path.join(ruta, "package.json")
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            resultado += f"\npackage.json: {pkg.get('name', 'N/A')} v{pkg.get('version', 'N/A')}\n"
            resultado += f"  Descripcion: {pkg.get('description', 'N/A')}\n"
            deps = pkg.get("dependencies", {})
            if deps:
                resultado += f"  Deps: {', '.join(list(deps.keys())[:15])}\n"
            scripts = pkg.get("scripts", {})
            if scripts:
                resultado += f"  Scripts: {', '.join(scripts.keys())}\n"
        except:
            pass

    readme_path = os.path.join(ruta, "README.md")
    if os.path.exists(readme_path):
        try:
            with open(readme_path, "r", encoding="utf-8") as f:
                readme = f.read()
            if len(readme) > 1500:
                readme = readme[:1500] + "\n... [truncado]"
            resultado += f"\nREADME.md:\n{readme}\n"
        except:
            pass

    return resultado


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


# ============================================================
# BUSQUEDA INTELIGENTE DE APLICACIONES
# Usa el Start Menu de Windows (la forma NATIVA como Windows busca apps)
# ============================================================

def buscar_en_start_menu(nombre: str) -> str:
    """
    Busca en los accesos directos del Start Menu de Windows.
    Esta es la forma mas confiable de encontrar apps instaladas,
    porque es exactamente como funciona el buscador de Windows.
    """
    nombre_lower = nombre.lower().strip()
    # Quitar "abre", "abrir", etc. si vienen en el nombre
    for prefix in ["abre ", "abrir ", "open ", "inicia ", "lanza ", "mi "]:
        if nombre_lower.startswith(prefix):
            nombre_lower = nombre_lower[len(prefix):]
            break

    # Directorios del Start Menu donde Windows guarda los accesos directos
    start_menu_dirs = []
    if platform.system() == "Windows":
        # Start Menu global (todas las apps instaladas para todos los usuarios)
        start_menu_dirs.append(os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"),
                                            "Microsoft", "Windows", "Start Menu", "Programs"))
        # Start Menu del usuario (apps instaladas solo para este usuario)
        start_menu_dirs.append(os.path.join(os.environ.get("AppData", ""),
                                            "Microsoft", "Windows", "Start Menu", "Programs"))

    matches = []
    for sm_dir in start_menu_dirs:
        if not os.path.exists(sm_dir):
            continue
        for root, dirs, files in os.walk(sm_dir):
            for f in files:
                f_lower = f.lower()
                # Los accesos directos son .lnk
                if f_lower.endswith(".lnk"):
                    # Quitar .lnk para comparar
                    name_no_ext = f_lower[:-4]
                    # Buscar coincidencia parcial
                    if nombre_lower in name_no_ext or name_no_ext in nombre_lower:
                        matches.append((os.path.join(root, f), name_no_ext))

    if not matches:
        return ""

    # Preferir la coincidencia mas exacta
    for path, name in matches:
        if nombre_lower == name:
            return path

    # Si no hay exacta, la primera parcial
    return matches[0][0]


def buscar_exe(nombre: str) -> str:
    """
    Busca un ejecutable de forma inteligente:
    1. Start Menu (lo mas confiable en Windows)
    2. Registro de desinstalacion (InstallLocation)
    3. where /r en Program Files
    4. Busqueda en directorios comunes
    """
    nombre_lower = nombre.lower().strip()
    for prefix in ["abre ", "abrir ", "open ", "inicia ", "lanza ", "mi "]:
        if nombre_lower.startswith(prefix):
            nombre_lower = nombre_lower[len(prefix):]
            break

    # 1. Start Menu (MEJOR METODO - funciona como Windows)
    shortcut = buscar_en_start_menu(nombre)
    if shortcut:
        return shortcut  # Windows abre .lnk directamente con start

    # 2. Registro de Windows (InstallLocation)
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

    # 3. where /r en directorios comunes
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
    """
    Abre una aplicacion de forma inteligente:
    1. Buscar en el Start Menu (como hace Windows)
    2. Buscar el .exe en el sistema
    3. Intentar con 'start nombre' como ultimo recurso
    Si falla, sugerir al usuario que instale la app.
    """
    app_clean = app.lower().strip()
    for prefix in ["abre ", "abrir ", "open ", "inicia ", "lanza ", "mi "]:
        if app_clean.startswith(prefix):
            app_clean = app_clean[len(prefix):]
            break

    # Alias comunes para que el LLM no tenga que adivinar el comando exacto
    aliases = {
        "chrome": "google chrome", "vscode": "visual studio code",
        "autocad": "autocad", "revit": "revit",
        "whatsapp": "whatsapp", "telegram": "telegram desktop",
        "word": "word", "excel": "excel", "powerpoint": "powerpoint",
        "photoshop": "adobe photoshop", "illustrator": "adobe illustrator",
        "figma": "figma", "blender": "blender", "sketchup": "sketchup",
    }
    search_name = aliases.get(app_clean, app_clean)

    # 1. Buscar en Start Menu
    shortcut_path = buscar_en_start_menu(search_name)
    if shortcut_path:
        resultado = ejecutar_comando(f'start "" "{shortcut_path}"')
        if not resultado or resultado == "(sin salida)":
            return f"Aplicacion {app} abierta (via Start Menu)"
        if "error" not in resultado.lower():
            return f"Aplicacion {app} abierta (via Start Menu)"

    # 2. Buscar .exe directamente
    exe_path = buscar_exe(search_name)
    if exe_path:
        resultado = ejecutar_comando(f'start "" "{exe_path}"')
        if not resultado or resultado == "(sin salida)":
            return f"Aplicacion {app} abierta (encontrada en: {exe_path})"
        if "error" not in resultado.lower():
            return f"Aplicacion {app} abierta (encontrada en: {exe_path})"

    # 3. Intento directo con start (Windows a veces resuelve el nombre)
    resultado = ejecutar_comando(f"start {app_clean}")
    if not resultado or resultado == "(sin salida)":
        return f"Aplicacion {app} abierta"

    # 4. No se encontro
    if "no se puede" in resultado.lower() or "no encuentra" in resultado.lower():
        return (f"No encontre '{app}' en tu computadora. "
                f"Puede que no este instalada o tenga otro nombre. "
                f"Quieres que busque en los programas instalados?")
    return resultado


# Mapeo de todas las herramientas disponibles
TOOL_FUNCTIONS = {
    "ejecutar_comando": ejecutar_comando,
    "clonar_repositorio": clonar_repositorio,
    "instalar_dependencias": instalar_dependencias,
    "leer_archivo": leer_archivo,
    "listar_archivos": listar_archivos,
    "analizar_proyecto": analizar_proyecto,
    "escribir_archivo": escribir_archivo,
    "abrir_aplicacion": abrir_aplicacion,
}

TOOL_DESCRIPTIONS = """
- conversar(mensaje) - Para SALUDOS, preguntas generales, charla. NUNCA para abrir apps.
- generar_contenido(descripcion, tipo, ruta) - GENERA contenido creativo usando el LLM. Para cuando el usuario pide CREAR algo: juegos, paginas web, scripts, documentos, etc. El LLM genera el contenido COMPLETO y lo guarda en el archivo. tipo puede ser: "html", "python", "javascript", "css", "json", "markdown", "texto". descripcion es que quiere crear.
- ejecutar_comando(comando) - Ejecuta CUALQUIER comando en la terminal.
- clonar_repositorio(url) - Clona un repo de GitHub.
- instalar_dependencias(ruta, gestor="auto") - Instala deps. Detecta npm/pip/poetry.
- leer_archivo(ruta) - Lee el contenido de un archivo.
- listar_archivos(ruta) - Lista archivos y carpetas de un directorio.
- analizar_proyecto(ruta) - Analiza la estructura completa de un proyecto.
- escribir_archivo(ruta, contenido) - Crea o modifica un archivo. SOLO usar cuando ya tienes el contenido exacto. Para generar contenido, usar generar_contenido.
- abrir_aplicacion(app) - Abre CUALQUIER aplicacion por nombre. Busca automaticamente en el Start Menu, registro y disco. No necesita saber el .exe exacto.
"""


# ============================================================
# SISTEMA DE APRENDIZAJE - El agente aprende de sus errores
# ============================================================

class LearningSystem:
    @staticmethod
    def _load(filepath, default=None):
        if default is None: default = []
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
        except: pass
        return default

    @staticmethod
    def _save(filepath, data):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

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
        """Guarda una correccion del usuario. El agente NUNCA repetira este error."""
        corrections = self._load(CORRECTIONS_FILE, [])
        corrections.append({
            "timestamp": datetime.now().isoformat(),
            "user_message": user_msg, "wrong_action": wrong_action,
            "correct_action": correct_action, "reason": reason
        })
        self._save(CORRECTIONS_FILE, corrections)
        # Tambien guardar como conocimiento para que el LLM lo use
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
        """Busca correcciones previas relacionadas con un mensaje del usuario."""
        corrections = self._load(CORRECTIONS_FILE, [])
        msg_lower = user_msg.lower()
        relevant = []
        for c in corrections:
            if any(w in msg_lower for w in c["user_message"].lower().split() if len(w) > 3):
                relevant.append(c)
        return relevant[-5:]  # Ultimas 5 relevantes

    def get_stats(self):
        return {
            "knowledge": len(self._load(KNOWLEDGE_FILE, [])),
            "corrections": len(self._load(CORRECTIONS_FILE, [])),
            "patterns": len(self._load(PATTERNS_FILE, [])),
            "feedback": len(self._load(FEEDBACK_FILE, [])),
        }

learning = LearningSystem()


# ============================================================
# CEREBRO DEL AGENTE - Piensa, Planifica, Decide
# ============================================================

THINKING_PROMPT = """Eres un agente autonomo INTELIGENTE que PIENSA antes de actuar.

Tu trabajo es ANALIZAR la solicitud del usuario y decidir que hacer.

REGLAS FUNDAMENTALES:
1. Si el usuario SALUDA o HABLA contigo → usa "conversar"
2. Si el usuario pide ABRIR algo → usa "abrir_aplicacion" (busca automaticamente, no necesitas saber el .exe)
3. Si el usuario pide CREAR algo (juego, pagina, script, codigo, documento) → usa "generar_contenido" NUNCA escribir_archivo con contenido vacio
4. Si el usuario pide HACER algo concreto → crea un plan con las herramientas necesarias
5. NUNCA uses escribir_archivo para responder preguntas o saludos
6. NUNCA uses escribir_archivo con contenido generico como "codigo HTML" — usa generar_contenido
7. NUNCA digas que algo "no existe" solo por el nombre — deja que las herramientas lo busquen

PIENSA ASI:
- "hola como estas?" → Es un saludo, usar conversar
- "whatsapp" → Quiere abrir WhatsApp, usar abrir_aplicacion
- "autocad 2025" → Quiere abrir AutoCAD, usar abrir_aplicacion
- "haz un juego en html" → Quiere CREAR un juego, usar generar_contenido
- "crea una pagina web" → Quiere CREAR una pagina, usar generar_contenido
- "escribe un script de python" → Quiere CREAR un script, usar generar_contenido
- "clona https://github.com/..." → Quiere clonar un repo, crear plan
- "que es Python?" → Es una pregunta, usar conversar
- "no funciona" → Algo fallo, diagnosticar con herramientas

CORRECCIONES APRENDIDAS (NO repitas estos errores):
{corrections}

CONTEXTO DEL SISTEMA:
- SO: {so}
- Directorio de trabajo: {repos_dir}
- Repos disponibles: {repos}
- Lecciones aprendidas: {lessons}

HERRAMIENTAS DISPONIBLES:
{tools}

FORMATO DE RESPUESTA - Responde SOLO con JSON valido:
{{
    "analisis": "Que entiendo que quiere el usuario y por que",
    "plan": [
        {{
            "paso": 1,
            "accion": "nombre_de_herramienta",
            "params": {{"parametro": "valor"}},
            "razon": "por que hago esto"
        }}
    ],
    "riesgos": ["que puede salir mal"],
    "siguiente_paso_sugerido": "que hacer despues"
}}

EJEMPLOS:

Usuario: "hola como estas?"
Respuesta:
{{
    "analisis": "El usuario esta saludando. Es conversacion, no accion.",
    "plan": [
        {{"paso": 1, "accion": "conversar", "params": {{"mensaje": "hola como estas?"}}, "razon": "Es un saludo"}}
    ],
    "riesgos": [],
    "siguiente_paso_sugerido": ""
}}

Usuario: "abre mi whatsapp"
Respuesta:
{{
    "analisis": "El usuario quiere abrir WhatsApp. abrir_aplicacion lo buscara automaticamente.",
    "plan": [
        {{"paso": 1, "accion": "abrir_aplicacion", "params": {{"app": "whatsapp"}}, "razon": "Abrir WhatsApp"}}
    ],
    "riesgos": ["Puede no estar instalado como app desktop"],
    "siguiente_paso_sugerido": ""
}}

Usuario: "vamos hacer un juego en html"
Respuesta:
{{
    "analisis": "El usuario quiere CREAR un juego en HTML. Necesito GENERAR el contenido completo del juego, no solo abrir notepad.",
    "plan": [
        {{"paso": 1, "accion": "generar_contenido", "params": {{"descripcion": "un juego interactivo en HTML5 Canvas con naves espaciales, disparos, enemigos, puntuacion y efectos visuales", "tipo": "html", "ruta": "REPOS_DIR/juego_espacial.html"}}, "razon": "Generar el juego HTML completo con Canvas y JavaScript"}},
        {{"paso": 2, "accion": "abrir_aplicacion", "params": {{"app": "chrome"}}, "razon": "Abrir el navegador para que el usuario vea el juego"}}
    ],
    "riesgos": ["El LLM puede generar codigo con errores"],
    "siguiente_paso_sugerido": "Si el juego no funciona, puedo revisar y corregir el codigo"
}}

Usuario: "crea una pagina web para mi portafolio"
Respuesta:
{{
    "analisis": "El usuario quiere CREAR una pagina web de portafolio. Necesito generar el HTML/CSS/JS completo.",
    "plan": [
        {{"paso": 1, "accion": "generar_contenido", "params": {{"descripcion": "pagina web de portafolio profesional con secciones: hero, sobre mi, proyectos, contacto. Diseño moderno con CSS gradientes, animaciones y responsive", "tipo": "html", "ruta": "REPOS_DIR/portafolio.html"}}, "razon": "Generar la pagina web completa"}},
        {{"paso": 2, "accion": "abrir_aplicacion", "params": {{"app": "chrome"}}, "razon": "Abrir el navegador para ver el resultado"}}
    ],
    "riesgos": [],
    "siguiente_paso_sugerido": "Puedo agregar mas secciones o modificar el diseno"
}}

Usuario: "escribe un script de python para automatizar backups"
Respuesta:
{{
    "analisis": "El usuario quiere CREAR un script de Python. Necesito generar el codigo completo.",
    "plan": [
        {{"paso": 1, "accion": "generar_contenido", "params": {{"descripcion": "script de Python para automatizar backups de carpetas, con compresion zip, logging y programacion de tareas", "tipo": "python", "ruta": "REPOS_DIR/backup_auto.py"}}, "razon": "Generar el script completo"}}
    ],
    "riesgos": ["Las rutas de carpetas pueden necesitar ajuste"],
    "siguiente_paso_sugerido": "Ejecutar el script para probarlo"
}}

Usuario: "clona mi repo https://github.com/yecos/signalTrade"
Respuesta:
{{
    "analisis": "El usuario quiere clonar un repositorio y analizarlo.",
    "plan": [
        {{"paso": 1, "accion": "clonar_repositorio", "params": {{"url": "https://github.com/yecos/signalTrade"}}, "razon": "Clonar el repo primero"}},
        {{"paso": 2, "accion": "analizar_proyecto", "params": {{"ruta": "RUTA_DEL_REPO"}}, "razon": "Analizar estructura"}},
        {{"paso": 3, "accion": "leer_archivo", "params": {{"ruta": "RUTA_DEL_REPO/README.md"}}, "razon": "Leer documentacion"}}
    ],
    "riesgos": ["El repo ya puede existir"],
    "siguiente_paso_sugerido": "Instalar dependencias si tiene package.json"
}}
"""

EVALUATION_PROMPT = """Eres el evaluador de un agente autonomo. Analiza el resultado de una accion.

ACCION EJECUTADA: {action}
PARAMETROS: {params}
RESULTADO: {result}

Responde SOLO con JSON:
{{
    "exitoso": true/false,
    "leccion": "que aprendimos de esto (si aplica)",
    "problema": "que salio mal (si aplica)",
    "solucion_alternativa": "que intentar si fallo (si aplica)",
    "proximo_paso": "que hacer ahora"
}}
"""

CLOUD_CONSULT_PROMPT = """Soy un agente local autonomo. Estoy trabajando en la computadora del usuario y me he atascado.

CONTEXTO:
- Tarea del usuario: {user_task}
- Lo que he hecho hasta ahora: {actions_taken}
- El problema: {problem}

Por favor ayudame a encontrar una solucion. Se especifico y practico. Si sugieres comandos, que sean para Windows.
"""


class AgentBrain:
    """El cerebro del agente - Piensa, planifica, evalua, aprende."""

    def __init__(self):
        self.thinking_log = []
        self.actions_taken = []

    def think(self, user_message: str, context: str = "") -> dict:
        """
        El agente PIENSA sobre el mensaje del usuario y genera un plan.
        v9: SIEMPRE usa el LLM cuando esta disponible. Sin pre-filtros hardcoded.
        """
        self.thinking_log = []
        self._log("Pensando...", "thinking")

        # Recopilar contexto
        repos = self._get_repos()
        lessons = learning.get_lessons()
        lessons_text = "\n".join([f"- {l}" for l in lessons[-5:]]) if lessons else "Ninguna aun"

        # Obtener correcciones relevantes para este mensaje
        corrections = learning.get_corrections_for(user_message)
        corrections_text = ""
        if corrections:
            corrections_text = "\n".join([
                f"- NO hagas '{c['wrong_action']}' cuando el usuario dice '{c['user_message']}'. "
                f"Haz '{c['correct_action']}' en su lugar."
                for c in corrections
            ])
        else:
            corrections_text = "Ninguna aun"

        prompt = THINKING_PROMPT.format(
            so=platform.system(),
            repos_dir=REPOS_DIR,
            repos=", ".join(repos) if repos else "Ninguno",
            lessons=lessons_text,
            tools=TOOL_DESCRIPTIONS,
            corrections=corrections_text
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message}
        ]

        if context:
            messages.append({"role": "user", "content": f"Contexto adicional: {context}"})

        # Pensar con el LLM
        self._log("Enviando al modelo para planificar...", "thinking")
        plan = self._ask_llm(messages)

        if not plan:
            self._log("El LLM no respondio, usando fallback", "warning")
            return self._fallback_plan(user_message)

        # Parsear la respuesta como JSON
        parsed = self._parse_json(plan)
        if parsed and "plan" in parsed:
            self._log(f"Analisis: {parsed.get('analisis', 'N/A')}", "thinking")
            self._log(f"Plan: {len(parsed['plan'])} pasos", "thinking")
            for step in parsed["plan"]:
                self._log(f"  Paso {step.get('paso', '?')}: {step.get('accion', '?')} - {step.get('razon', '')}", "plan")
            return parsed

        # Si no se pudo parsear, usar fallback
        self._log("No se pudo parsear el plan, usando fallback", "warning")
        return self._fallback_plan(user_message)

    def execute_plan(self, plan: dict) -> list:
        """Ejecuta el plan paso a paso, evaluando cada resultado."""
        results = []
        steps = plan.get("plan", [])

        if not steps:
            analisis = plan.get("analisis", "")
            self._log(f"Plan vacio — es conversacion: {analisis}", "thinking")
            result = self._conversar(st.session_state.messages[-1]["content"] if st.session_state.messages else "hola")
            results.append({
                "action": "conversar", "params": {}, "reason": analisis,
                "result": result, "evaluation": {"exitoso": True}
            })
            return results

        for step in steps:
            action = step.get("accion", "")
            params = step.get("params", {})
            reason = step.get("razon", "")

            self._log(f"Ejecutando: {action}({params}) — {reason}", "execution")
            params = self._resolve_params(params)
            result = self._execute_tool(action, params)
            evaluation = self.evaluate(action, params, result)

            results.append({
                "action": action, "params": params, "reason": reason,
                "result": result, "evaluation": evaluation
            })

            self.actions_taken.append(f"{action}({params}) -> {result[:100]}")

            # Si fallo, intentar alternativa
            if not evaluation.get("exitoso", True) and evaluation.get("solucion_alternativa"):
                self._log(f"Fallo detectado, intentando alternativa...", "warning")
                alt_result = self._try_alternative(evaluation["solucion_alternativa"], action, params)
                if alt_result:
                    results[-1]["result"] = alt_result
                    results[-1]["evaluation"] = {"exitoso": True, "leccion": "Alternativa funciono"}

            # Aprender de la evaluacion
            if evaluation.get("leccion"):
                learning.save_knowledge(f"leccion:{action}", evaluation["leccion"], source="auto_evaluation")

        return results

    def evaluate(self, action: str, params: dict, result: str) -> dict:
        """Evalua si una accion fue exitosa."""
        if "ERROR" in result or "Error" in result:
            prompt = EVALUATION_PROMPT.format(
                action=action, params=json.dumps(params), result=result[:500]
            )
            eval_result = self._ask_llm([{"role": "user", "content": prompt}])
            parsed = self._parse_json(eval_result)
            if parsed:
                self._log(f"Evaluacion: fallo - {parsed.get('problema', 'desconocido')}", "evaluation")
                return parsed
            return {"exitoso": False, "problema": result[:200], "solucion_alternativa": ""}

        self._log(f"Evaluacion: exitoso", "evaluation")
        return {"exitoso": True, "leccion": "", "proximo_paso": "continuar"}

    def consult_cloud(self, user_task: str, problem: str) -> str:
        """Consulta IA cloud cuando se atasca."""
        self._log("Consultando IA cloud...", "cloud")

        prompt = CLOUD_CONSULT_PROMPT.format(
            user_task=user_task,
            actions_taken="\n".join(self.actions_taken[-5:]),
            problem=problem
        )

        bridge_path = os.path.join(os.path.dirname(__file__), "ia_bridge.py")
        if os.path.exists(bridge_path):
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("ia_bridge", bridge_path)
                bridge = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(bridge)
                if hasattr(bridge, 'consultar_ia'):
                    return bridge.consultar_ia(prompt)
            except Exception as e:
                self._log(f"Error con ia_bridge: {e}", "warning")

        try:
            import urllib.request
            api_key = os.environ.get("GROQ_API_KEY", "")
            if not api_key:
                config_path = os.path.join(os.path.dirname(__file__), "..", "config", "api_keys.json")
                if os.path.exists(config_path):
                    with open(config_path, "r") as f:
                        config = json.load(f)
                        api_key = config.get("groq", "")

            if api_key:
                data = json.dumps({
                    "messages": [
                        {"role": "system", "content": "Eres un experto en desarrollo de software. Responde de forma concisa y practica."},
                        {"role": "user", "content": prompt}
                    ],
                    "model": "llama-3.3-70b-versatile",
                    "max_tokens": 500
                }).encode("utf-8")

                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=data,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    response = json.loads(resp.read().decode("utf-8"))
                    return response["choices"][0]["message"]["content"]
        except Exception as e:
            self._log(f"Error con API cloud: {e}", "warning")

        return "No se pudo consultar IA cloud. Verifica la conexion o configura una API key."

    # --- Metodos internos ---

    def _log(self, message: str, category: str = "info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.thinking_log.append(f"[{timestamp}] [{category.upper()}] {message}")

    def _ask_llm(self, messages: list) -> str:
        """Consulta al LLM local (Ollama). 4 metodos de conexion."""
        try:
            import ollama

            try:
                client = ollama.Client(host='http://localhost:11434')
                response = client.chat(model=AGENT_MODEL, messages=messages)
                return response.get("message", {}).get("content", "")
            except Exception as e:
                self._log(f"Client(localhost) fallo: {e}", "warning")

            try:
                client = ollama.Client(host='http://127.0.0.1:11434')
                response = client.chat(model=AGENT_MODEL, messages=messages)
                return response.get("message", {}).get("content", "")
            except Exception as e:
                self._log(f"Client(127.0.0.1) fallo: {e}", "warning")

            try:
                response = ollama.chat(model=AGENT_MODEL, messages=messages)
                return response.get("message", {}).get("content", "")
            except Exception:
                pass

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
            except Exception as e2:
                self._log(f"HTTP directo fallo: {e2}", "error")

            self._log("Todos los metodos de conexion a Ollama fallaron", "error")
            return ""

        except ImportError:
            self._log("Libreria ollama no instalada", "error")
            return ""
        except Exception as e:
            self._log(f"Error LLM: {e}", "error")
            return ""

    def _parse_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except:
            pass

        json_patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'(\{[\s\S]*\})',
        ]
        for pattern in json_patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except:
                    continue
        return None

    def _resolve_params(self, params: dict) -> dict:
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                value = value.replace("RUTA_DEL_REPO", self._find_repo_path())
                value = value.replace("REPOS_DIR", REPOS_DIR)
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

    def _execute_tool(self, action: str, params: dict) -> str:
        if action == "conversar":
            return self._conversar(params.get("mensaje", ""))

        if action == "generar_contenido":
            return self._generar_contenido(
                params.get("descripcion", ""),
                params.get("tipo", "html"),
                params.get("ruta", "")
            )

        if action in TOOL_FUNCTIONS:
            try:
                return TOOL_FUNCTIONS[action](**params)
            except Exception as e:
                return f"ERROR ejecutando {action}: {e}"
        elif action == "ejecutar_comando" or action == "comando":
            return ejecutar_comando(params.get("comando", ""))
        else:
            return f"Herramienta no encontrada: {action}"

    def _generar_contenido(self, descripcion: str, tipo: str, ruta: str) -> str:
        """
        El superpoder del agente: GENERAR contenido usando el LLM.
        Esto es lo que diferencia v10 de versiones anteriores.
        El LLM genera codigo/texto completo, no solo decide que hacer.
        """
        self._log(f"Generando contenido: {descripcion} ({tipo})", "creative")

        # Resolver ruta
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

        # Crear el prompt especializado para generar contenido
        tipo_prompts = {
            "html": (
                "Eres un desarrollador web EXPERTO. Genera una pagina web HTML COMPLETA y FUNCIONAL.\n"
                "REGLAS:\n"
                "- TODO debe estar en un SOLO archivo HTML (HTML + CSS inline en <style> + JavaScript en <script>)\n"
                "- El CSS debe ser moderno, con gradientes, sombras, animaciones\n"
                "- El JavaScript debe ser funcional, no pseudocodigo\n"
                "- Si es un juego: usa HTML5 Canvas, con game loop, controles, colisiones, puntuacion\n"
                "- Si es una pagina: responsive, con secciones completas, no vacias\n"
                "- NO uses placeholder, TODO debe funcionar al abrir en el navegador\n"
                "- Responde SOLO con el codigo HTML, sin explicaciones, sin markdown"
            ),
            "python": (
                "Eres un desarrollador Python EXPERTO. Genera un script Python COMPLETO y FUNCIONAL.\n"
                "REGLAS:\n"
                "- El codigo debe ser ejecutable directamente\n"
                "- Incluye imports, funciones, manejo de errores\n"
                "- Si necesita dependencias, incluyelas en un comentario al inicio\n"
                "- NO uses pseudocodigo ni placeholders\n"
                "- Responde SOLO con el codigo Python, sin explicaciones"
            ),
            "javascript": (
                "Eres un desarrollador JavaScript EXPERTO. Genera codigo JavaScript COMPLETO.\n"
                "REGLAS:\n"
                "- El codigo debe ser funcional y ejecutable\n"
                "- Incluye manejo de errores\n"
                "- Responde SOLO con el codigo, sin explicaciones"
            ),
            "css": (
                "Eres un diseador CSS EXPERTO. Genera estilos CSS modernos y completos.\n"
                "- Responde SOLO con el codigo CSS"
            ),
            "json": (
                "Genera un JSON valido y bien estructurado.\n"
                "- Responde SOLO con el JSON, sin explicaciones"
            ),
            "markdown": (
                "Genera un documento Markdown bien formateado y completo.\n"
                "- Responde SOLO con el Markdown"
            ),
        }

        system_prompt = tipo_prompts.get(tipo, (
            "Genera contenido completo y funcional. "
            "Responde SOLO con el contenido, sin explicaciones ni markdown."
        ))

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Crea: {descripcion}"}
        ]

        self._log(f"Llamando al LLM para generar {tipo}...", "creative")
        contenido = self._ask_llm(messages)

        if not contenido:
            return "ERROR: No se pudo generar contenido (Ollama no responde)"

        # Limpiar el contenido: quitar markdown code blocks si el LLM los puso
        contenido = contenido.strip()
        if contenido.startswith("```"):
            # Quitar ```html, ```python, ```javascript, etc.
            contenido = re.sub(r'^```[a-z]*\n?', '', contenido)
            contenido = re.sub(r'\n?```$', '', contenido)
            contenido = contenido.strip()

        # Escribir el archivo
        resultado = escribir_archivo(ruta, contenido)

        if "ERROR" in resultado:
            return resultado

        # Si es HTML, abrir en el navegador automaticamente
        if tipo == "html" and platform.system() == "Windows":
            abrir_result = ejecutar_comando(f'start "" "{ruta}"')
            if not abrir_result or abrir_result == "(sin salida)":
                return f"Contenido generado y guardado en: {ruta}\nAbierto en el navegador automaticamente!"
            return f"Contenido generado y guardado en: {ruta}\nAbrelo en tu navegador para verlo."

        size_kb = len(contenido) / 1024
        self._log(f"Contenido generado: {size_kb:.1f}KB", "creative")

        return f"Contenido generado ({size_kb:.1f}KB) y guardado en: {ruta}"

    def _conversar(self, mensaje: str) -> str:
        """Responde de forma conversacional. Usa LLM para respuestas ricas."""
        msg = mensaje.lower().strip()

        # Respuestas rapidas para patrones obvios (sin LLM)
        saludos = ["hola", "hi", "hello", "hey", "buenos dias", "buenas", "que tal", "que onda", "saludos"]
        if any(msg.startswith(s) for s in saludos):
            return ("Hola! Soy tu agente autonomo local. Puedo hacer cosas como:\n"
                    "- **CREAR cosas**: juegos HTML, paginas web, scripts (genero el codigo completo!)\n"
                    "- Abrir CUALQUIER aplicacion (busca automaticamente)\n"
                    "- Clonar y analizar repos de GitHub\n"
                    "- Ejecutar comandos en la terminal\n"
                    "- Leer y escribir archivos\n"
                    "- Consultar IA cloud si necesito ayuda\n\n"
                    "Dime que necesitas!")

        if any(w in msg for w in ["como estas", "como te va", "como andas", "todo bien"]):
            return "Listo para trabajar! Tengo acceso a tu terminal. Dime que necesitas."

        if any(w in msg for w in ["quien eres", "que eres", "que haces"]):
            return ("Soy un agente autonomo que PIENSA antes de actuar y ahora tambien CREA.\n"
                    "- Analizo tu solicitud y creo un plan\n"
                    "- **Genero codigo completo** (juegos, paginas web, scripts)\n"
                    "- Busco automaticamente apps y archivos\n"
                    "- Si algo falla, busco alternativas\n"
                    "- Si me equivoco, aprendo y no repito el error\n"
                    "Todo corre localmente con Ollama (qwen2.5:14b).")

        if any(w in msg for w in ["gracias", "thanks", "genial", "perfecto"]):
            return "De nada! Aqui estoy para lo que necesites."

        if any(w in msg for w in ["ayuda", "help", "que puedes hacer"]):
            return ("Puedo hacer muchas cosas:\n\n"
                    "**Crear cosas:** 'haz un juego en html', 'crea una pagina web', 'escribe un script'\n"
                    "**Abrir apps:** 'abre whatsapp', 'autocad', 'chrome'\n"
                    "**Repos:** 'clona https://github.com/usuario/repo'\n"
                    "**Archivos:** 'leer README.md', 'listar archivos'\n"
                    "**Terminal:** 'ejecuta git status', 'npm run dev'\n\n"
                    "**Lo especial:** Genero codigo completo, busco apps automaticamente, aprendo de mis errores, y consulto IA cloud si me atasco.")

        # Para todo lo demas, usar el LLM
        respuesta_llm = self._ask_llm([
            {"role": "system", "content": "Eres un asistente amigable que habla espanol. Responde de forma concisa y natural."},
            {"role": "user", "content": mensaje}
        ])
        if respuesta_llm:
            return respuesta_llm

        return ("No puedo pensar bien ahora (Ollama no esta corriendo). "
                "Pero puedo ejecutar acciones! Prueba: 'abre chrome', 'clona https://github.com/...'")

    def _try_alternative(self, alternative: str, original_action: str, params: dict) -> str:
        self._log(f"Intentando alternativa: {alternative}", "execution")

        if alternative and len(alternative) > 3:
            alt_lower = alternative.lower()

            if any(w in alt_lower for w in ["ejecuta", "corre", "run", "usa", "usa el comando"]):
                cmd = re.sub(r'(?:ejecuta|corre|run|usa|usa el comando)\s+', '', alternative, flags=re.IGNORECASE)
                return ejecutar_comando(cmd.strip())

            for tool_name in TOOL_FUNCTIONS:
                if tool_name in alt_lower:
                    return self._execute_tool(tool_name, params)

            if "lista" in alt_lower or "verifica" in alt_lower or "revisa" in alt_lower:
                if "ruta" in params:
                    return listar_archivos(params.get("ruta", REPOS_DIR))

        return ""

    def _fallback_plan(self, user_message: str) -> dict:
        """Plan de emergencia cuando el LLM no responde. Usa heuristicas simples."""
        msg = user_message.lower().strip()

        # Saludos obvios
        saludos = ["hola", "hi", "hello", "hey", "buenos dias", "buenas", "que tal", "que onda", "saludos"]
        if any(msg.startswith(s) for s in saludos) and len(msg.split()) <= 4:
            return {
                "analisis": "El usuario esta saludando",
                "plan": [{"paso": 1, "accion": "conversar", "params": {"mensaje": user_message}, "razon": "Es un saludo"}],
                "riesgos": [], "siguiente_paso_sugerido": ""
            }

        # ========================================
        # DETECCION DE SOLICITUDES CREATIVAS (v10)
        # ========================================
        creative_keywords = [
            "juego", "game", "crear", "crea", "haz", "hacer", "genera", "generar",
            "pagina web", "webpage", "website", "sitio web", "portafolio", "portfolio",
            "script", "programa", "aplicacion", "app", "calculator", "calculadora",
            "formulario", "form", "dashboard", "landing", "blog", "tienda",
            "escribir codigo", "escribe un", "code ", "programar", "desarrollar",
            "dise\u00f1ar", "dise\u00f1o", "animacion", "canvas", "jugar"
        ]
        is_creative = any(kw in msg for kw in creative_keywords)

        # Detectar tipo de archivo por extension o contexto
        tipo_detectado = "texto"
        ext_detectada = ".txt"
        if "html" in msg or "web" in msg or "pagina" in msg or "juego" in msg or "game" in msg:
            tipo_detectado = "html"
            ext_detectada = ".html"
        elif "python" in msg or ".py" in msg:
            tipo_detectado = "python"
            ext_detectada = ".py"
        elif "javascript" in msg or ".js" in msg or "js " in msg:
            tipo_detectado = "javascript"
            ext_detectada = ".js"
        elif "css" in msg or "estilo" in msg:
            tipo_detectado = "css"
            ext_detectada = ".css"
        elif "json" in msg:
            tipo_detectado = "json"
            ext_detectada = ".json"

        if is_creative:
            safe_name = re.sub(r'[^a-z0-9]', '_', msg[:30].lower()).strip('_')
            ruta = os.path.join(REPOS_DIR, f"{safe_name}{ext_detectada}")
            plan_steps = [
                {"paso": 1, "accion": "generar_contenido",
                 "params": {"descripcion": user_message, "tipo": tipo_detectado, "ruta": ruta},
                 "razon": "El usuario quiere crear algo - generar contenido completo"}
            ]
            # Si es HTML, abrir navegador despues
            if tipo_detectado == "html":
                plan_steps.append(
                    {"paso": 2, "accion": "abrir_aplicacion",
                     "params": {"app": "chrome"},
                     "razon": "Abrir navegador para ver el resultado"}
                )
            return {
                "analisis": f"Solicitud creativa detectada: {user_message}",
                "plan": plan_steps,
                "riesgos": ["El contenido generado puede necesitar ajustes"],
                "siguiente_paso_sugerido": "Revisar y ajustar el contenido si es necesario"
            }

        # URLs de GitHub
        github_urls = re.findall(r'https?://github\.com/[\w\-]+/[\w\-\.]+', user_message, re.IGNORECASE)
        if github_urls:
            url = github_urls[0].rstrip("/")
            repo_name = url.split("/")[-1].replace(".git", "")
            repo_path = os.path.join(REPOS_DIR, repo_name)
            return {
                "analisis": f"Clonar y analizar repo: {url}",
                "plan": [
                    {"paso": 1, "accion": "clonar_repositorio", "params": {"url": url}, "razon": "Clonar el repo"},
                    {"paso": 2, "accion": "analizar_proyecto", "params": {"ruta": repo_path}, "razon": "Analizar estructura"},
                ],
                "riesgos": [], "siguiente_paso_sugerido": "Instalar dependencias si necesita"
            }

        # Acciones con verbos
        if any(w in msg for w in ["abre", "abrir", "open", "inicia", "lanza"]):
            app_match = re.search(r'(?:abre|abrir|open|inicia|lanza)\s+(.+)', msg, re.IGNORECASE)
            app = app_match.group(1).strip() if app_match else ""
            if app:
                return {
                    "analisis": f"Abrir aplicacion: {app}",
                    "plan": [{"paso": 1, "accion": "abrir_aplicacion", "params": {"app": app}, "razon": "Abrir la app"}],
                    "riesgos": ["Puede no estar instalada"], "siguiente_paso_sugerido": ""
                }

        if any(w in msg for w in ["instal", "dependencias"]):
            for d in os.listdir(REPOS_DIR):
                if d.lower() in msg:
                    return {
                        "analisis": f"Instalar dependencias de {d}",
                        "plan": [{"paso": 1, "accion": "instalar_dependencias", "params": {"ruta": os.path.join(REPOS_DIR, d)}, "razon": "Instalar deps"}],
                        "riesgos": [], "siguiente_paso_sugerido": ""
                    }

        if any(w in msg for w in ["analiz", "analiza"]):
            for d in os.listdir(REPOS_DIR):
                if d.lower() in msg:
                    return {
                        "analisis": f"Analizar proyecto {d}",
                        "plan": [{"paso": 1, "accion": "analizar_proyecto", "params": {"ruta": os.path.join(REPOS_DIR, d)}, "razon": "Analizar"}],
                        "riesgos": [], "siguiente_paso_sugerido": ""
                    }

        if any(w in msg for w in ["ejecuta", "corre", "run", "comando"]):
            cmd_match = re.search(r'(?:ejecuta|corre|run|comando)\s+(.+)', msg, re.IGNORECASE)
            cmd = cmd_match.group(1).strip() if cmd_match else ""
            if cmd:
                return {
                    "analisis": f"Ejecutar: {cmd}",
                    "plan": [{"paso": 1, "accion": "ejecutar_comando", "params": {"comando": cmd}, "razon": "Ejecutar comando"}],
                    "riesgos": ["Puede fallar"], "siguiente_paso_sugerido": ""
                }

        # Si contiene algo que podria ser un nombre de app, intentar abrirlo
        words = msg.split()
        has_version = any(re.match(r'\d{4}', w) for w in words)
        if has_version or (len(words) <= 3 and len(words[0]) > 2):
            return {
                "analisis": f"Posible solicitud de abrir app: {user_message}",
                "plan": [{"paso": 1, "accion": "abrir_aplicacion", "params": {"app": user_message.strip()}, "razon": "Parece una app, intentar abrirla"}],
                "riesgos": ["Puede no ser una app"], "siguiente_paso_sugerido": ""
            }

        # Default: conversar
        return {
            "analisis": "No se detecto una accion clara",
            "plan": [{"paso": 1, "accion": "conversar", "params": {"mensaje": user_message}, "razon": "Responder conversacionalmente"}],
            "riesgos": [], "siguiente_paso_sugerido": ""
        }

    def _get_repos(self) -> list:
        try:
            return [d for d in os.listdir(REPOS_DIR)
                    if os.path.isdir(os.path.join(REPOS_DIR, d)) and not d.startswith(".")]
        except:
            return []


# ============================================================
# MOTOR PRINCIPAL
# ============================================================

brain = AgentBrain()

def procesar_mensaje(user_message: str) -> tuple:
    brain.actions_taken = []
    brain._log(f"Mensaje del usuario: {user_message}", "input")
    plan = brain.think(user_message)
    results = brain.execute_plan(plan)

    respuesta = ""
    for i, r in enumerate(results, 1):
        action = r["action"]
        reason = r.get("reason", "")
        result = r["result"]
        evaluation = r.get("evaluation", {})

        if evaluation.get("exitoso", True):
            if action == "conversar":
                respuesta += f"{result}\n\n"
            else:
                respuesta += f"**Paso {i}: {action}** — {reason}\n```\n{result}\n```\n\n"
        else:
            respuesta += f"**Paso {i}: {action}** — {reason}\n```\n{result}\n```\n"
            if evaluation.get("solucion_alternativa"):
                respuesta += f"Intentando: {evaluation['solucion_alternativa']}\n\n"

    is_conversation = any(r.get("action") == "conversar" for r in results)
    if plan.get("siguiente_paso_sugerido") and not is_conversation:
        respuesta += f"**Siguiente paso sugerido:** {plan['siguiente_paso_sugerido']}"

    if not is_conversation and (not results or all(not r.get("evaluation", {}).get("exitoso", True) for r in results)):
        respuesta += "\n\nTuve problemas. Quieres que consulte una IA cloud?"

    return respuesta, brain.thinking_log


# ============================================================
# INTERFAZ STREAMLIT
# ============================================================

def main():
    st.set_page_config(
        page_title="Agente Autonomo v10",
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
    .thinking-box .evaluation { color: #aa88ff; }
    .thinking-box .warning { color: #ffaa00; }
    .thinking-box .error { color: #ff4444; }
    .thinking-box .cloud { color: #44aaff; }
    .thinking-box .input { color: #88ff88; }
    .thinking-box .creative { color: #ff88ff; font-weight: bold; }

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

    st.markdown('<div class="main-title">Agente Autonomo v10</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">Piensa → Planifica → Genera → Ejecuta → Evalua → Aprende</div>', unsafe_allow_html=True)

    # === SIDEBAR ===
    with st.sidebar:
        st.header("Config")
        st.write(f"**Modelo:** {AGENT_MODEL}")
        st.write(f"**Repos:** {REPOS_DIR}")

        st.header("Ollama Status")
        if st.button("Test conexion Ollama", use_container_width=True):
            with st.spinner("Probando..."):
                try:
                    import ollama
                    try:
                        r = ollama.list()
                        st.success("ollama.chat() - CONECTA")
                    except:
                        st.error("ollama.chat() - FALLA")
                    try:
                        client = ollama.Client(host='http://localhost:11434')
                        r = client.list()
                        st.success("Client(localhost) - CONECTA")
                    except Exception as e:
                        st.error(f"Client(localhost) - FALLA")
                    try:
                        client = ollama.Client(host='http://127.0.0.1:11434')
                        r = client.list()
                        st.success("Client(127.0.0.1) - CONECTA")
                    except:
                        st.error("Client(127.0.0.1) - FALLA")
                except ImportError:
                    st.error("Libreria ollama no instalada")
                try:
                    import urllib.request
                    req = urllib.request.Request("http://localhost:11434/api/tags")
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        models = [m["name"] for m in data.get("models", [])]
                        st.success(f"HTTP directo - Modelos: {models}")
                except Exception as e:
                    st.error(f"HTTP directo - FALLA")

        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m["name"] for m in data.get("models", [])]
                st.success(f"Ollama OK - {len(models)} modelos")
        except:
            st.error("Ollama NO conecta")

        stats = learning.get_stats()
        st.header("Aprendizaje")
        col1, col2 = st.columns(2)
        col1.metric("Conocimiento", stats["knowledge"])
        col2.metric("Correcciones", stats["corrections"])

        # === CORRECCIONES ===
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
            st.rerun()

        st.header("Repos")
        try:
            repos = [d for d in os.listdir(REPOS_DIR)
                     if os.path.isdir(os.path.join(REPOS_DIR, d)) and not d.startswith(".")]
            for repo in repos:
                st.write(f" {repo}")
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
                        with st.expander("Proceso de pensamiento (click para ver)", expanded=False):
                            st.markdown(f'<div class="thinking-box">{thinking_text}</div>',
                                       unsafe_allow_html=True)

                    st.markdown(respuesta)

                except Exception as e:
                    respuesta = f"**ERROR:** {e}"
                    st.error(respuesta)

        st.session_state.messages.append({"role": "assistant", "content": respuesta})


if __name__ == "__main__":
    main()
