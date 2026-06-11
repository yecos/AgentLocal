"""
=============================================================
AGENTE LOCAL AUTONOMO v8 - AGENTE QUE PIENSA DE VERDAD
Piensa → Planifica → Ejecuta → Evalua → Ajusta
Consulta IA cloud si necesita ayuda
=============================================================

ARQUITECTURA:
  Usuario → Pre-filtro (conversacion?) → Si: responder directamente
                                  → No: Agente PIENSA (LLM) → Plan → Ejecuta → Evalua
                ↑                                                              |
                └── Si falla, ajusta y reintenta ←────────────────────────────┘
                └── Si se atasca, consulta IA cloud ←─────────────────────────┘

DIFERENCIA vs v7:
  v7: "Todo va al LLM, incluso los saludos → elige escribir_archivo para 'hola'"
  v8: "Detecta conversacion ANTES del LLM → responde natural → solo usa herramientas cuando hace falta"
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
            # Algunos stderr son solo warnings, no errores reales
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


def abrir_aplicacion(app: str) -> str:
    app_map = {
        "chrome": "start chrome", "google chrome": "start chrome",
        "firefox": "start firefox", "edge": "start msedge",
        "explorador": "start explorer", "file explorer": "start explorer",
        "vscode": "start code", "visual studio code": "start code",
        "notepad": "start notepad", "bloc de notas": "start notepad",
        "calculadora": "start calc", "calculator": "start calc",
        "paint": "start mspaint", "word": "start winword",
        "excel": "start excel", "powerpoint": "start powerpnt",
        "spotify": "start spotify", "discord": "start discord",
        "terminal": "start cmd", "powershell": "start powershell",
        "configuracion": "start ms-settings:",
    }
    comando = app_map.get(app.lower().strip(), f"start {app}")
    resultado = ejecutar_comando(comando)
    if not resultado or resultado == "(sin salida)":
        return f"Aplicacion {app} abierta"
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

# Descripcion de herramientas para el LLM
TOOL_DESCRIPTIONS = """
- conversar(mensaje) - Para SALUDOS, preguntas generales, charla. Usa esta cuando NO necesitas ejecutar nada.
- ejecutar_comando(comando) - Ejecuta CUALQUIER comando en la terminal. Use para todo lo que no tenga herramienta especifica.
- clonar_repositorio(url) - Clona un repo de GitHub.
- instalar_dependencias(ruta, gestor="auto") - Instala deps. Detecta npm/pip/poetry automaticamente.
- leer_archivo(ruta) - Lee el contenido de un archivo de texto.
- listar_archivos(ruta) - Lista archivos y carpetas de un directorio.
- analizar_proyecto(ruta) - Analiza la estructura completa de un proyecto.
- escribir_archivo(ruta, contenido) - Crea o modifica un archivo.
- abrir_aplicacion(app) - Abre una aplicacion (chrome, vscode, notepad, etc.)
"""


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
        corrections = self._load(CORRECTIONS_FILE, [])
        corrections.append({
            "timestamp": datetime.now().isoformat(),
            "user_message": user_msg, "wrong_action": wrong_action,
            "correct_action": correct_action, "reason": reason
        })
        self._save(CORRECTIONS_FILE, corrections)

    def get_lessons(self):
        knowledge = self._load(KNOWLEDGE_FILE, [])
        return [k["content"] for k in knowledge if k["topic"].startswith("leccion:")]

    def get_stats(self):
        return {
            "knowledge": len(self._load(KNOWLEDGE_FILE, [])),
            "corrections": len(self._load(CORRECTIONS_FILE, [])),
            "patterns": len(self._load(PATTERNS_FILE, [])),
            "feedback": len(self._load(FEEDBACK_FILE, [])),
        }

learning = LearningSystem()


# ============================================================
# DETECTOR DE CONVERSACION (pre-filtro rapido, SIN LLM)
# ============================================================

def es_conversacion(mensaje: str) -> bool:
    """
    Detecta rapidamente si un mensaje es conversacional (saludos, preguntas genericas, etc.)
    ANTES de enviar al LLM. Esto ahorra tokens y evita planes absurdos como
    escribir_archivo para un simple 'hola'.
    """
    msg = mensaje.lower().strip()

    # Patrones de saludo
    saludos = ["hola", "hi", "hello", "hey", "buenos dias", "buenas", "que tal",
               "que onda", "saludos", "buen dia", "buenas noches", "buenas tardes"]
    if any(msg.startswith(s) for s in saludos):
        return True

    # Preguntas personales / estado
    estado = ["como estas", "como te va", "como andas", "todo bien", "que haces",
              "que tal tu", "como estas tu", "como te encuentras"]
    if any(e in msg for e in estado):
        return True

    # Identidad
    identidad = ["quien eres", "que eres", "que haces", "para que sirves",
                 "que puedes hacer", "como funcionas", "que sabes hacer"]
    if any(i in msg for i in identidad):
        return True

    # Agradecimientos
    gracias = ["gracias", "thanks", "genial", "perfecto", "excelente", "muy bien", "cool"]
    if any(msg.startswith(g) for g in gracias):
        return True

    # Confirmaciones cortas sin contexto de accion
    confirmaciones = ["si", "no", "ok", "vale", "bien", "ya", "ahora", "enterado", "entendido"]
    if msg in confirmaciones:
        return True

    # Mensajes muy cortos sin verbos de accion
    verbos_accion = ["clona", "abre", "instal", "ejecuta", "analiz", "leer", "listar",
                     "busca", "crea", "borra", "elimina", "modifica", "escribe", "corre",
                     "compila", "despliega", "descarga", "sube", "mueve"]
    if len(msg.split()) <= 3 and not any(v in msg for v in verbos_accion):
        return True

    return False


# ============================================================
# CEREBRO DEL AGENTE - Piensa, Planifica, Decide
# ============================================================

THINKING_PROMPT = """Eres un agente autonomo que PIENSA antes de actuar.

Tu trabajo es ANALIZAR la solicitud del usuario y decidir que hacer.

REGLA MAS IMPORTANTE:
- Si el usuario esta SALUDANDO, PREGUNTANDO algo general, o CONVERSANDO, usa la accion "conversar".
- NUNCA uses escribir_archivo para responder a un saludo o pregunta.
- NUNCA uses herramientas de accion para mensajes conversacionales.
- Solo usa herramientas de accion (clonar, ejecutar, abrir, etc.) cuando el usuario pide HACER algo concreto.

CONTEXTO DEL SISTEMA:
- SO: {so}
- Directorio de trabajo: {repos_dir}
- Repos disponibles: {repos}
- Lecciones aprendidas: {lessons}

HERRAMIENTAS DISPONIBLES:
{tools}

REGLAS DE PENSAMIENTO:
1. ANALIZA: Que quiere realmente el usuario? Es una ACCION o una CONVERSACION?
2. Si es CONVERSACION (saludo, pregunta, charla) → usar "conversar"
3. Si es ACCION (clonar, abrir, ejecutar) → crear un plan con las herramientas necesarias
4. PLANIFICA: Cual es la mejor secuencia de acciones? Piensa paso a paso.
5. ANTICIPA: Que puede salir mal? Que informacion necesitas primero?
6. Si no estas seguro, INVESTIGA primero (lista archivos, lee configs, etc.)

FORMATO DE RESPUESTA - Responde SOLO con JSON valido:
{{
    "analisis": "Que entiendo que quiere el usuario",
    "plan": [
        {{
            "paso": 1,
            "accion": "nombre_de_herramienta",
            "params": {{"parametro": "valor"}},
            "razon": "por que hago esto primero"
        }}
    ],
    "riesgos": ["que puede salir mal"],
    "siguiente_paso_sugerido": "que hacer despues de ejecutar el plan"
}}

EJEMPLOS:

Usuario: "hola como estas?"
Respuesta:
{{
    "analisis": "El usuario esta saludando y preguntando como estoy. Es una conversacion, no una accion.",
    "plan": [
        {{"paso": 1, "accion": "conversar", "params": {{"mensaje": "hola como estas?"}}, "razon": "Es un saludo, responder de forma natural"}}
    ],
    "riesgos": [],
    "siguiente_paso_sugerido": ""
}}

Usuario: "que puedes hacer?"
Respuesta:
{{
    "analisis": "El usuario pregunta por mis capacidades. Es una conversacion.",
    "plan": [
        {{"paso": 1, "accion": "conversar", "params": {{"mensaje": "que puedes hacer?"}}, "razon": "Pregunta sobre capacidades, responder directamente"}}
    ],
    "riesgos": [],
    "siguiente_paso_sugerido": ""
}}

Usuario: "clona mi repo https://github.com/yecos/signalTrade"
Respuesta:
{{
    "analisis": "El usuario quiere clonar un repositorio de GitHub y analizarlo. La URL es clara.",
    "plan": [
        {{"paso": 1, "accion": "clonar_repositorio", "params": {{"url": "https://github.com/yecos/signalTrade"}}, "razon": "Clonar el repo primero"}},
        {{"paso": 2, "accion": "analizar_proyecto", "params": {{"ruta": "RUTA_DEL_REPO"}}, "razon": "Analizar estructura automaticamente"}},
        {{"paso": 3, "accion": "leer_archivo", "params": {{"ruta": "RUTA_DEL_REPO/README.md"}}, "razon": "Leer documentacion para entender el proyecto"}}
    ],
    "riesgos": ["El repo ya puede existir", "Puede estar vacio"],
    "siguiente_paso_sugerido": "Instalar dependencias si tiene package.json"
}}

Usuario: "abre chrome"
Respuesta:
{{
    "analisis": "El usuario quiere abrir el navegador Chrome.",
    "plan": [
        {{"paso": 1, "accion": "abrir_aplicacion", "params": {{"app": "chrome"}}, "razon": "Abrir Chrome directamente"}}
    ],
    "riesgos": ["Chrome puede no estar instalado"],
    "siguiente_paso_sugerido": "Si necesito abrir una URL especifica, usar chrome URL"
}}

Usuario: "ayudame con mi proyecto signalTrade"
Respuesta:
{{
    "analisis": "El usuario quiere ayuda con su proyecto. Necesito entender primero de que trata.",
    "plan": [
        {{"paso": 1, "accion": "analizar_proyecto", "params": {{"ruta": "C:\\Users\\yecos\\Documents\\signalTrade"}}, "razon": "Entender la estructura del proyecto primero"}},
        {{"paso": 2, "accion": "leer_archivo", "params": {{"ruta": "C:\\Users\\yecos\\Documents\\signalTrade/README.md"}}, "razon": "Leer documentacion para entender que hace"}}
    ],
    "riesgos": ["Puede no tener README", "Puede necesitar dependencias instaladas"],
    "siguiente_paso_sugerido": "Preguntar al usuario que aspecto especifico necesita ayuda"
}}

Usuario: "no funciona, sigue sin hacer nada"
Respuesta:
{{
    "analisis": "El usuario esta frustrado. Algo fallo antes. Necesito diagnosticar.",
    "plan": [
        {{"paso": 1, "accion": "listar_archivos", "params": {{"ruta": "C:\\Users\\yecos\\Documents"}}, "razon": "Verificar que existe el directorio y los archivos"}},
        {{"paso": 2, "accion": "ejecutar_comando", "params": {{"comando": "ollama list"}}, "razon": "Verificar que Ollama esta corriendo y los modelos disponibles"}}
    ],
    "riesgos": ["Ollama puede no estar corriendo"],
    "siguiente_paso_sugerido": "Diagnosticar el problema especifico y buscar solucion"
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
    """El cerebro del agente - Piensa, planifica, evalua."""

    def __init__(self):
        self.thinking_log = []
        self.actions_taken = []

    def think(self, user_message: str, context: str = "") -> dict:
        """
        El agente PIENSA sobre el mensaje del usuario y genera un plan.

        FLUJO v8:
        1. Pre-filtro: Si es conversacion, responder directamente (SIN LLM)
        2. Si es accion: enviar al LLM para planificar
        3. Si el LLM no responde: usar fallback
        """
        self.thinking_log = []
        self._log("Pensando...", "thinking")

        # === PRE-FILTRO v8: Detectar conversacion ANTES del LLM ===
        if es_conversacion(user_message):
            self._log("Detectado como CONVERSACION (pre-filtro)", "thinking")
            respuesta = self._conversar(user_message)
            return {
                "analisis": "Conversacion detectada por pre-filtro",
                "plan": [{"paso": 1, "accion": "conversar", "params": {"mensaje": user_message}, "razon": "Responder al usuario"}],
                "riesgos": [],
                "siguiente_paso_sugerido": "",
                "_respuesta_directa": respuesta  # Ya tenemos la respuesta, no ejecutar de nuevo
            }

        # Recopilar contexto
        repos = self._get_repos()
        lessons = learning.get_lessons()
        lessons_text = "\n".join([f"- {l}" for l in lessons[-5:]]) if lessons else "Ninguna aun"

        prompt = THINKING_PROMPT.format(
            so=platform.system(),
            repos_dir=REPOS_DIR,
            repos=", ".join(repos) if repos else "Ninguno",
            lessons=lessons_text,
            tools=TOOL_DESCRIPTIONS
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message}
        ]

        # Agregar contexto de acciones previas si hay
        if context:
            messages.append({"role": "user", "content": f"Contexto adicional: {context}"})

        # Pensar con el LLM
        self._log("Enviando al modelo para planificar...", "thinking")
        plan = self._ask_llm(messages)

        if not plan:
            self._log("El LLM no respondio, usando ejecucion directa", "warning")
            return self._fallback_plan(user_message)

        # Parsear la respuesta como JSON
        parsed = self._parse_json(plan)
        if parsed and "plan" in parsed:
            self._log(f"Analisis: {parsed.get('analisis', 'N/A')}", "thinking")
            self._log(f"Plan: {len(parsed['plan'])} pasos", "thinking")
            for step in parsed["plan"]:
                self._log(f"  Paso {step.get('paso', '?')}: {step.get('accion', '?')} - {step.get('razon', '')}", "plan")
            return parsed

        # Si no se pudo parsear, intentar ejecucion directa
        self._log("No se pudo parsear el plan, usando ejecucion directa", "warning")
        return self._fallback_plan(user_message)

    def execute_plan(self, plan: dict) -> list:
        """
        Ejecuta el plan paso a paso, evaluando cada resultado.
        Si algo falla, busca alternativas.
        Si el plan esta vacio (conversacion), responde directamente.
        """
        results = []

        # === v8: Si ya tenemos respuesta directa del pre-filtro, usarla ===
        if "_respuesta_directa" in plan:
            respuesta = plan["_respuesta_directa"]
            results.append({
                "action": "conversar",
                "params": {"mensaje": plan.get("plan", [{}])[0].get("params", {}).get("mensaje", "")},
                "reason": "Conversacion (pre-filtro)",
                "result": respuesta,
                "evaluation": {"exitoso": True}
            })
            return results

        steps = plan.get("plan", [])

        # Si el plan esta vacio, es una conversacion — responder directamente
        if not steps:
            analisis = plan.get("analisis", "")
            self._log(f"Plan vacio — es conversacion: {analisis}", "thinking")
            result = self._conversar(st.session_state.messages[-1]["content"] if st.session_state.messages else "hola")
            results.append({
                "action": "conversar",
                "params": {},
                "reason": analisis,
                "result": result,
                "evaluation": {"exitoso": True}
            })
            return results

        for step in steps:
            action = step.get("accion", "")
            params = step.get("params", {})
            reason = step.get("razon", "")

            self._log(f"Ejecutando paso: {action}({params}) — {reason}", "execution")

            # Resolver parametros dinamicos (como RUTA_DEL_REPO)
            params = self._resolve_params(params)

            # Ejecutar la herramienta
            result = self._execute_tool(action, params)

            # Evaluar el resultado
            evaluation = self.evaluate(action, params, result)

            results.append({
                "action": action,
                "params": params,
                "reason": reason,
                "result": result,
                "evaluation": evaluation
            })

            self.actions_taken.append(f"{action}({params}) -> {result[:100]}")

            # Si fallo, intentar solucion alternativa
            if not evaluation.get("exitoso", True) and evaluation.get("solucion_alternativa"):
                self._log(f"Fallo detectado, intentando alternativa...", "warning")
                alt_result = self._try_alternative(evaluation["solucion_alternativa"], action, params)
                if alt_result:
                    results[-1]["result"] = alt_result
                    results[-1]["evaluation"] = {"exitoso": True, "leccion": "Solucion alternativa funciono"}

            # Si la evaluacion dice que hay que hacer algo mas, agregarlo
            if evaluation.get("leccion"):
                learning.save_knowledge(
                    f"leccion:{action}",
                    evaluation["leccion"],
                    source="auto_evaluation"
                )

        return results

    def evaluate(self, action: str, params: dict, result: str) -> dict:
        """Evalua si una accion fue exitosa y que aprendemos de ella."""
        # Evaluacion rapida basada en patrones (sin LLM para velocidad)
        if "ERROR" in result or "Error" in result:
            # Evaluar con LLM para entender el problema
            prompt = EVALUATION_PROMPT.format(
                action=action,
                params=json.dumps(params),
                result=result[:500]
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
        """
        Consulta a una IA cloud cuando el agente local se atasca.
        Usa APIs de Groq, OpenRouter, o DeepSeek.
        """
        self._log("Consultando IA cloud para ayuda...", "cloud")

        prompt = CLOUD_CONSULT_PROMPT.format(
            user_task=user_task,
            actions_taken="\n".join(self.actions_taken[-5:]),
            problem=problem
        )

        # Intentar con ia_bridge.py si existe
        bridge_path = os.path.join(os.path.dirname(__file__), "ia_bridge.py")
        if os.path.exists(bridge_path):
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("ia_bridge", bridge_path)
                bridge = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(bridge)
                if hasattr(bridge, 'consultar_ia'):
                    result = bridge.consultar_ia(prompt)
                    self._log("Respuesta cloud recibida", "cloud")
                    return result
            except Exception as e:
                self._log(f"Error con ia_bridge: {e}", "warning")

        # Intentar con API directa (Groq - gratis y rapido)
        try:
            import urllib.request
            api_key = os.environ.get("GROQ_API_KEY", "")
            if not api_key:
                # Buscar en archivo de config
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
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                )

                with urllib.request.urlopen(req, timeout=15) as resp:
                    response = json.loads(resp.read().decode("utf-8"))
                    result = response["choices"][0]["message"]["content"]
                    self._log("Respuesta de Groq recibida", "cloud")
                    return result
        except Exception as e:
            self._log(f"Error con API cloud: {e}", "warning")

        return "No se pudo consultar IA cloud. Verifica la conexion o configura una API key."

    # --- Metodos internos ---

    def _log(self, message: str, category: str = "info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.thinking_log.append(f"[{timestamp}] [{category.upper()}] {message}")

    def _ask_llm(self, messages: list) -> str:
        """Consulta al LLM local (Ollama). Usa Client explicito que SI conecta."""
        try:
            import ollama

            # Metodo principal: Client explicito con localhost (EL QUE FUNCIONA)
            try:
                client = ollama.Client(host='http://localhost:11434')
                response = client.chat(model=AGENT_MODEL, messages=messages)
                return response.get("message", {}).get("content", "")
            except Exception as e:
                self._log(f"Client(localhost) fallo: {e}", "warning")

            # Metodo alternativo: Client con 127.0.0.1
            try:
                client = ollama.Client(host='http://127.0.0.1:11434')
                response = client.chat(model=AGENT_MODEL, messages=messages)
                return response.get("message", {}).get("content", "")
            except Exception as e:
                self._log(f"Client(127.0.0.1) fallo: {e}", "warning")

            # Metodo 3: Default (a veces funciona)
            try:
                response = ollama.chat(model=AGENT_MODEL, messages=messages)
                return response.get("message", {}).get("content", "")
            except Exception:
                pass

            # Metodo 4: HTTP directo con urllib (sin depender de la lib ollama)
            try:
                import urllib.request
                data = json.dumps({
                    "model": AGENT_MODEL,
                    "messages": messages,
                    "stream": False
                }).encode("utf-8")

                req = urllib.request.Request(
                    "http://localhost:11434/api/chat",
                    data=data,
                    headers={"Content-Type": "application/json"}
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
        """Intenta extraer JSON de la respuesta del LLM."""
        # Intentar parsear directamente
        try:
            return json.loads(text)
        except:
            pass

        # Buscar JSON en la respuesta (entre ``` o llaves)
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
        """Resuelve parametros dinamicos como RUTA_DEL_REPO."""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                # Reemplazar marcadores
                value = value.replace("RUTA_DEL_REPO", self._find_repo_path())
                value = value.replace("REPOS_DIR", REPOS_DIR)
            resolved[key] = value
        return resolved

    def _find_repo_path(self) -> str:
        """Busca el path de un repositorio reciente."""
        try:
            dirs = [d for d in os.listdir(REPOS_DIR)
                    if os.path.isdir(os.path.join(REPOS_DIR, d)) and not d.startswith(".")]
            if dirs:
                # Retornar el mas reciente
                latest = max(dirs, key=lambda d: os.path.getmtime(os.path.join(REPOS_DIR, d)))
                return os.path.join(REPOS_DIR, latest)
        except:
            pass
        return REPOS_DIR

    def _execute_tool(self, action: str, params: dict) -> str:
        """Ejecuta una herramienta por nombre."""
        # Accion especial: conversar (no es una herramienta real)
        if action == "conversar":
            return self._conversar(params.get("mensaje", ""))

        if action in TOOL_FUNCTIONS:
            try:
                return TOOL_FUNCTIONS[action](**params)
            except Exception as e:
                return f"ERROR ejecutando {action}: {e}"
        elif action == "ejecutar_comando" or action == "comando":
            return ejecutar_comando(params.get("comando", ""))
        else:
            return f"Herramienta no encontrada: {action}"

    def _conversar(self, mensaje: str) -> str:
        """Responde al usuario de forma conversacional. Usa LLM para respuestas ricas."""
        msg = mensaje.lower().strip()

        # Respuestas predefinidas rapidas (sin necesidad de LLM)
        saludos = ["hola", "hi", "hello", "hey", "buenos dias", "buenas", "que tal", "que onda", "saludos"]
        if any(msg.startswith(s) for s in saludos):
            return ("Hola! Soy tu agente autonomo local. Puedo hacer cosas como:\n"
                    "- Clonar y analizar repos de GitHub\n"
                    "- Instalar dependencias\n"
                    "- Abrir aplicaciones\n"
                    "- Leer y escribir archivos\n"
                    "- Ejecutar comandos en la terminal\n"
                    "- Consultar IA cloud si necesito ayuda\n\n"
                    "Dime que necesitas y yo me encargo!")

        if any(w in msg for w in ["como estas", "como te va", "como andas", "todo bien"]):
            return ("Estoy listo para trabajar! Tengo acceso a tu terminal y puedo ejecutar comandos. "
                    "Solo dime que necesitas.")

        if any(w in msg for w in ["quien eres", "que eres", "que haces"]):
            return ("Soy un agente autonomo local que PIENSA antes de actuar.\n"
                    "- Analizo tu solicitud y creo un plan\n"
                    "- Ejecuto paso a paso y evaluo los resultados\n"
                    "- Si algo falla, busco alternativas\n"
                    "- Si me atasco, consulto IA cloud\n"
                    "- Aprendo de mis errores\n\n"
                    "Todo corre localmente en tu PC con Ollama (qwen2.5:14b).")

        if any(w in msg for w in ["gracias", "thanks", "genial", "perfecto"]):
            return "De nada! Estoy aqui para lo que necesites."

        if any(w in msg for w in ["ayuda", "help", "que puedes hacer"]):
            return ("Puedo hacer muchas cosas:\n\n"
                    "**Repositorios:**\n"
                    "- 'clona https://github.com/usuario/repo'\n"
                    "- 'analiza signalTrade'\n"
                    "- 'instalar dependencias signalTrade'\n\n"
                    "**Aplicaciones:**\n"
                    "- 'abre chrome'\n"
                    "- 'abre vscode'\n"
                    "- 'abre notepad'\n\n"
                    "**Archivos:**\n"
                    "- 'leer README.md de signalTrade'\n"
                    "- 'listar archivos'\n\n"
                    "**Terminal:**\n"
                    "- 'ejecuta git status'\n"
                    "- 'ejecuta npm run dev'\n\n"
                    "**Lo especial:** Yo PIENSO antes de actuar y busco soluciones si algo falla.")

        # Si no es un patron conocido, intentar con el LLM para respuesta mas inteligente
        respuesta_llm = self._ask_llm([
            {"role": "system", "content": "Eres un asistente amigable que habla espanol. Responde de forma concisa y natural. No uses markdown, solo texto plano."},
            {"role": "user", "content": mensaje}
        ])
        if respuesta_llm:
            return respuesta_llm

        # Si el LLM tampoco responde (Ollama caido)
        return ("No puedo pensar bien ahora porque Ollama no esta corriendo. "
                "Pero puedo ejecutar acciones! Prueba con:\n"
                "- 'clona https://github.com/...'\n"
                "- 'abre chrome'\n"
                "- 'analiza signalTrade'\n"
                "Para que piense, ejecuta 'ollama serve' en otra terminal.")

    def _try_alternative(self, alternative: str, original_action: str, params: dict) -> str:
        """Intenta una solucion alternativa cuando algo falla."""
        self._log(f"Intentando alternativa: {alternative}", "execution")

        # Si la alternativa es un comando, ejecutarlo
        if alternative and len(alternative) > 3:
            # Intentar parsear como instruccion
            alt_lower = alternative.lower()

            # Si sugiere otro comando
            if any(w in alt_lower for w in ["ejecuta", "corre", "run", "usa", "usa el comando"]):
                cmd = re.sub(r'(?:ejecuta|corre|run|usa|usa el comando)\s+', '', alternative, flags=re.IGNORECASE)
                return ejecutar_comando(cmd.strip())

            # Si sugiere otra herramienta
            for tool_name in TOOL_FUNCTIONS:
                if tool_name in alt_lower:
                    return self._execute_tool(tool_name, params)

            # Si sugiere listar o investigar
            if "lista" in alt_lower or "verifica" in alt_lower or "revisa" in alt_lower:
                if "ruta" in params:
                    return listar_archivos(params.get("ruta", REPOS_DIR))

        return ""

    def _fallback_plan(self, user_message: str) -> dict:
        """Plan de emergencia cuando el LLM no responde."""
        msg = user_message.lower().strip()

        # === PRIMERO: Detectar si es CONVERSACION (saludos, preguntas, etc.) ===
        conversacion_patterns = [
            r'^(hola|hi|hello|hey|buenos dias|buenas|que tal|que onda|saludos)',
            r'^(como estas|como te va|como andas|todo bien|que haces)',
            r'^(gracias|thanks|genial|perfecto|ok|vale|bien|excelente)',
            r'^(quien eres|que eres|que haces|para que sirves|que puedes hacer)',
            r'^(ayuda|help|que puedes hacer|como funcionas)',
            r'^(si|no|ok|vale|bien|ahora|ya)',
        ]
        for pattern in conversacion_patterns:
            if re.match(pattern, msg):
                return {
                    "analisis": "El usuario esta conversando",
                    "plan": [{"paso": 1, "accion": "conversar", "params": {"mensaje": user_message}, "razon": "Responder al usuario"}],
                    "riesgos": [],
                    "siguiente_paso_sugerido": ""
                }

        # Si es solo "hola?" o algo corto sin intencion de accion
        if len(msg.split()) <= 2 and not any(w in msg for w in ["clona", "abre", "instal", "ejecuta", "analiz", "leer", "listar"]):
            return {
                "analisis": "El usuario esta conversando o preguntando algo simple",
                "plan": [{"paso": 1, "accion": "conversar", "params": {"mensaje": user_message}, "razon": "Responder al usuario"}],
                "riesgos": [],
                "siguiente_paso_sugerido": ""
            }

        # === SEGUNDO: Deteccion rapida de intenciones de accion ===
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
                "riesgos": [],
                "siguiente_paso_sugerido": "Instalar dependencias si necesita"
            }

        if any(w in msg for w in ["abre", "abrir", "open", "inicia", "lanza"]):
            app_match = re.search(r'(?:abre|abrir|open|inicia|lanza)\s+(.+)', msg, re.IGNORECASE)
            app = app_match.group(1).strip() if app_match else ""
            if app:
                return {
                    "analisis": f"Abrir aplicacion: {app}",
                    "plan": [{"paso": 1, "accion": "abrir_aplicacion", "params": {"app": app}, "razon": "Abrir la app"}],
                    "riesgos": ["Puede no estar instalada"],
                    "siguiente_paso_sugerido": ""
                }

        if any(w in msg for w in ["instal", "dependencias", "npm install"]):
            for d in os.listdir(REPOS_DIR):
                if d.lower() in msg:
                    return {
                        "analisis": f"Instalar dependencias de {d}",
                        "plan": [{"paso": 1, "accion": "instalar_dependencias", "params": {"ruta": os.path.join(REPOS_DIR, d)}, "razon": "Instalar deps"}],
                        "riesgos": ["Pueden faltar herramientas"],
                        "siguiente_paso_sugerido": ""
                    }

        if any(w in msg for w in ["analiz", "analiza", "analizar"]):
            for d in os.listdir(REPOS_DIR):
                if d.lower() in msg:
                    return {
                        "analisis": f"Analizar proyecto {d}",
                        "plan": [
                            {"paso": 1, "accion": "analizar_proyecto", "params": {"ruta": os.path.join(REPOS_DIR, d)}, "razon": "Analizar estructura"},
                            {"paso": 2, "accion": "leer_archivo", "params": {"ruta": os.path.join(REPOS_DIR, d, "README.md")}, "razon": "Leer documentacion"},
                        ],
                        "riesgos": [],
                        "siguiente_paso_sugerido": "Instalar dependencias o revisar archivos especificos"
                    }

        if any(w in msg for w in ["leer", "muestra", "ver"]):
            archivo_match = re.search(r'(?:leer|muestra|ver)\s+(.+)', msg, re.IGNORECASE)
            archivo = archivo_match.group(1).strip() if archivo_match else ""
            if archivo:
                return {
                    "analisis": f"Leer archivo: {archivo}",
                    "plan": [{"paso": 1, "accion": "leer_archivo", "params": {"ruta": archivo}, "razon": "Mostrar contenido"}],
                    "riesgos": ["Archivo puede no existir"],
                    "siguiente_paso_sugerido": ""
                }

        if any(w in msg for w in ["listar", "lista", "archivos", "carpetas"]):
            return {
                "analisis": "Listar archivos del directorio de trabajo",
                "plan": [{"paso": 1, "accion": "listar_archivos", "params": {"ruta": REPOS_DIR}, "razon": "Mostrar contenido del directorio"}],
                "riesgos": [],
                "siguiente_paso_sugerido": ""
            }

        if any(w in msg for w in ["ejecuta", "corre", "run", "comando"]):
            cmd_match = re.search(r'(?:ejecuta|corre|run|comando)\s+(.+)', msg, re.IGNORECASE)
            cmd = cmd_match.group(1).strip() if cmd_match else ""
            if cmd:
                return {
                    "analisis": f"Ejecutar comando: {cmd}",
                    "plan": [{"paso": 1, "accion": "ejecutar_comando", "params": {"comando": cmd}, "razon": "Ejecutar el comando solicitado"}],
                    "riesgos": ["El comando puede fallar"],
                    "siguiente_paso_sugerido": ""
                }

        if any(w in msg for w in ["busca", "buscar", "encuentra", "search"]):
            # Busqueda web o en archivos
            busqueda = re.sub(r'(?:busca|buscar|encuentra|search)\s+', '', msg, flags=re.IGNORECASE).strip()
            return {
                "analisis": f"Busqueda: {busqueda}",
                "plan": [{"paso": 1, "accion": "conversar", "params": {"mensaje": user_message}, "razon": "Responder sobre la busqueda"}],
                "riesgos": [],
                "siguiente_paso_sugerido": "Si necesito buscar en internet, requeriria API de busqueda"
            }

        # Si no se detecta nada claro, usar conversacion con LLM
        return {
            "analisis": "No se detecto una accion clara, conversar con el usuario",
            "plan": [{"paso": 1, "accion": "conversar", "params": {"mensaje": user_message}, "razon": "No es una accion clara, responder conversacionalmente"}],
            "riesgos": [],
            "siguiente_paso_sugerido": ""
        }

    def _get_repos(self) -> list:
        try:
            return [d for d in os.listdir(REPOS_DIR)
                    if os.path.isdir(os.path.join(REPOS_DIR, d)) and not d.startswith(".")]
        except:
            return []


# ============================================================
# MOTOR PRINCIPAL - Orquesta el pensamiento y la ejecucion
# ============================================================

brain = AgentBrain()

def procesar_mensaje(user_message: str) -> tuple:
    """
    Procesamiento principal: PIENSA → PLANIFICA → EJECUTA → EVALUA
    """
    brain.actions_taken = []

    # === PASO 1: PENSAR ===
    brain._log(f"Mensaje del usuario: {user_message}", "input")
    plan = brain.think(user_message)

    # === PASO 2: EJECUTAR ===
    results = brain.execute_plan(plan)

    # === PASO 3: CONSTRUIR RESPUESTA ===
    respuesta = ""
    for i, r in enumerate(results, 1):
        action = r["action"]
        reason = r.get("reason", "")
        result = r["result"]
        evaluation = r.get("evaluation", {})

        if evaluation.get("exitoso", True):
            # Conversacion: mostrar directamente sin caja de codigo
            if action == "conversar":
                respuesta += f"{result}\n\n"
            else:
                respuesta += f"**Paso {i}: {action}** — {reason}\n```\n{result}\n```\n\n"
        else:
            respuesta += f"**Paso {i}: {action}** — {reason}\n```\n{result}\n```\n"
            if evaluation.get("solucion_alternativa"):
                respuesta += f"Intentando: {evaluation['solucion_alternativa']}\n\n"

    # Agregar sugerencia de siguiente paso (solo si no es conversacion)
    is_conversation = any(r.get("action") == "conversar" for r in results)
    if plan.get("siguiente_paso_sugerido") and not is_conversation:
        respuesta += f"**Siguiente paso sugerido:** {plan['siguiente_paso_sugerido']}"

    # Si no hubo resultados utiles Y no es conversacion, ofrecer consulta cloud
    if not is_conversation and (not results or all(not r.get("evaluation", {}).get("exitoso", True) for r in results)):
        respuesta += "\n\nTuve problemas con la ejecucion. Quieres que consulte una IA cloud para encontrar una solucion?"

    return respuesta, brain.thinking_log


# ============================================================
# INTERFAZ STREAMLIT - Mejorada visualmente
# ============================================================

def main():
    st.set_page_config(
        page_title="Agente Autonomo v8",
        page_icon="🧠",
        layout="wide"
    )

    # === ESTILOS CSS MEJORADOS ===
    st.markdown("""
    <style>
    /* Fondo general */
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
    }

    /* Titulo principal */
    .main-title {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.2rem;
        font-weight: 800;
        text-align: center;
        margin-bottom: 0.3rem;
    }

    .main-subtitle {
        text-align: center;
        color: #888;
        font-size: 0.9rem;
        margin-bottom: 1.5rem;
    }

    /* Caja de pensamiento */
    .thinking-box {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        color: #00ff88;
        padding: 16px;
        border-radius: 12px;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        font-size: 11px;
        max-height: 400px;
        overflow-y: auto;
        white-space: pre-wrap;
        word-break: break-all;
        border: 1px solid rgba(100, 100, 255, 0.2);
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
    }
    .thinking-box .thinking { color: #88aaff; }
    .thinking-box .plan { color: #ffaa44; }
    .thinking-box .execution { color: #00ff88; }
    .thinking-box .evaluation { color: #aa88ff; }
    .thinking-box .warning { color: #ffaa00; }
    .thinking-box .error { color: #ff4444; }
    .thinking-box .cloud { color: #44aaff; }
    .thinking-box .input { color: #88ff88; }

    /* Mensajes del chat mejorados */
    [data-testid="stChatMessage"] {
        border-radius: 12px;
        padding: 12px 16px;
        margin: 4px 0;
    }

    /* Mensaje del usuario */
    [data-testid="stChatMessage"][data-testid="stChatMessage-user"] {
        background: linear-gradient(135deg, #1a1a3e 0%, #2d2d5e 100%);
        border: 1px solid rgba(100, 100, 255, 0.15);
    }

    /* Mensaje del asistente */
    [data-testid="stChatMessage"][data-testid="stChatMessage-assistant"] {
        background: linear-gradient(135deg, #1a2e1a 0%, #1a3e2d 100%);
        border: 1px solid rgba(0, 255, 136, 0.1);
    }

    /* Input del chat */
    [data-testid="stChatInput"] {
        border-radius: 16px;
    }

    /* Botones del sidebar */
    .stButton > button {
        border-radius: 8px;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(100, 100, 255, 0.3);
    }

    /* Metricas */
    [data-testid="stMetricValue"] {
        font-size: 1.5rem;
        font-weight: 700;
    }

    /* Scrollbar personalizada */
    ::-webkit-scrollbar {
        width: 6px;
    }
    ::-webkit-scrollbar-track {
        background: rgba(0, 0, 0, 0.1);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb {
        background: rgba(100, 100, 255, 0.3);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: rgba(100, 100, 255, 0.5);
    }

    /* Expander de pensamiento */
    .streamlit-expanderHeader {
        background: linear-gradient(135deg, #1a1a3e 0%, #2d2d5e 100%) !important;
        border-radius: 8px !important;
        border: 1px solid rgba(100, 100, 255, 0.15) !important;
    }

    /* Status indicators */
    .status-ok {
        color: #00ff88;
        font-weight: 600;
    }
    .status-fail {
        color: #ff4444;
        font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)

    # Session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "thinking_history" not in st.session_state:
        st.session_state.thinking_history = []

    # Titulo con estilo
    st.markdown('<div class="main-title">Agente Autonomo v8</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">Piensa → Planifica → Ejecuta → Evalua → Aprende — Consulta IA cloud si se atasca</div>', unsafe_allow_html=True)

    # === SIDEBAR ===
    with st.sidebar:
        st.header("Config")
        st.write(f"**Modelo:** {AGENT_MODEL}")
        st.write(f"**Repos:** {REPOS_DIR}")

        # === TEST DE CONEXION OLLAMA ===
        st.header("Ollama Status")
        if st.button("Test conexion Ollama", use_container_width=True):
            with st.spinner("Probando conexion..."):
                # Probar conexion de 4 formas
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
                        st.success("Client(localhost:11434) - CONECTA")
                    except Exception as e:
                        st.error(f"Client(localhost) - FALLA: {e}")

                    try:
                        client = ollama.Client(host='http://127.0.0.1:11434')
                        r = client.list()
                        st.success("Client(127.0.0.1) - CONECTA")
                    except Exception as e:
                        st.error(f"Client(127.0.0.1) - FALLA: {e}")
                except ImportError:
                    st.error("Libreria ollama no instalada")

                # Test HTTP directo
                try:
                    import urllib.request
                    req = urllib.request.Request("http://localhost:11434/api/tags")
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        models = [m["name"] for m in data.get("models", [])]
                        st.success(f"HTTP directo - CONECTA. Modelos: {models}")
                except Exception as e:
                    st.error(f"HTTP directo - FALLA: {e}")

        # Mostrar estado rapido
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

        # Ver pensamiento historico
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

                    # Mostrar proceso de pensamiento
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
