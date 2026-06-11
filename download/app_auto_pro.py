"""
=============================================================
 AGENTE LOCAL AUTONOMO v5 - CON DEBUG VISIBLE
 Detecta intencion + Ejecuta directamente + Muestra cada paso
=============================================================
"""

import streamlit as st
import subprocess
import os
import re
import json
import platform
from datetime import datetime

# ============================================================
# CONFIGURACION
# ============================================================

AGENT_MODEL = "qwen2.5:14b"
MAX_ITERATIONS = 6

if platform.system() == "Windows":
    REPOS_DIR = os.path.join(os.path.expanduser("~"), "Documents")
else:
    REPOS_DIR = os.path.join(os.path.expanduser("~"), "repos")

os.makedirs(REPOS_DIR, exist_ok=True)

# ============================================================
# HERRAMIENTAS - Funciones que EJECUTAN de verdad
# ============================================================

def ejecutar_comando(comando: str) -> str:
    try:
        result = subprocess.run(
            comando, shell=True, capture_output=True, text=True,
            timeout=120, cwd=REPOS_DIR
        )
        output = ""
        if result.stdout:
            output += result.stdout.strip()
        if result.stderr:
            output += ("\n[STDERR] " + result.stderr.strip()) if output else result.stderr.strip()
        if not output:
            output = "(Comando ejecutado sin salida)"
        return output
    except subprocess.TimeoutExpired:
        return "ERROR: Comando cancelado por timeout (>120s)"
    except Exception as e:
        return f"ERROR: {e}"


def clonar_repositorio(url: str) -> str:
    repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
    target_dir = os.path.join(REPOS_DIR, repo_name)

    if os.path.exists(target_dir):
        # Verificar si el repo esta completo (tiene .git y al menos algunos archivos)
        git_dir = os.path.join(target_dir, ".git")
        contenido = os.listdir(target_dir) if os.path.isdir(target_dir) else []
        archivos_reales = [f for f in contenido if f != ".git"]

        if os.path.exists(git_dir) and len(archivos_reales) > 1:
            return f"Repositorio ya existe y esta completo en: {target_dir}\nCarpetas: {[f for f in contenido if os.path.isdir(os.path.join(target_dir, f))]}\nArchivos: {archivos_reales[:10]}..."
        else:
            # Carpeta vacia o incompleta - borrar y clonar de nuevo
            import shutil
            try:
                shutil.rmtree(target_dir)
            except Exception as e:
                return f"La carpeta existe pero esta vacia/incompleta y no se pudo borrar: {e}\nBorrala manualmente: Remove-Item -Recurse -Force \"{target_dir}\""

    comando = f'git clone {url} "{target_dir}"'
    resultado = ejecutar_comando(comando)

    if os.path.exists(target_dir):
        contenido = os.listdir(target_dir)
        carpetas = [f for f in contenido if os.path.isdir(os.path.join(target_dir, f))]
        archivos = [f for f in contenido if os.path.isfile(os.path.join(target_dir, f))]
        if len(carpetas) > 0 or len(archivos) > 1:
            return f"CLONADO OK en: {target_dir}\nCarpetas: {carpetas}\nArchivos: {archivos[:10]}"
        else:
            return f"Clonado pero parece vacio. Salida de git:\n{resultado}"
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
        "yarn": f'cd "{ruta}" && yarn install',
    }

    comando = comandos.get(gestor, f'cd "{ruta}" && {gestor} install')
    return ejecutar_comando(comando)


def leer_archivo(ruta: str) -> str:
    # Buscar en múltiples ubicaciones
    rutas_posibles = [ruta]
    if not os.path.isabs(ruta):
        rutas_posibles.append(os.path.join(REPOS_DIR, ruta))
        # Buscar en subdirectorios de REPOS_DIR
        try:
            for d in os.listdir(REPOS_DIR):
                full = os.path.join(REPOS_DIR, d, ruta)
                rutas_posibles.append(full)
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
        carpetas = []
        archivos = []
        for item in sorted(items):
            full = os.path.join(ruta, item)
            if os.path.isdir(full):
                carpetas.append(item)
            else:
                archivos.append(item)
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

    resultado = f"Analisis de: {ruta}\n"
    resultado += "=" * 40 + "\n\n"

    # Estructura de directorios (3 niveles)
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

    # Detectar tipo
    resultado += "\nDeteccion:\n"
    checks = {
        "package.json": "Node.js",
        "tsconfig.json": "TypeScript",
        "next.config.js": "Next.js",
        "next.config.ts": "Next.js",
        "requirements.txt": "Python (pip)",
        "Dockerfile": "Docker",
        ".git": "Repositorio Git",
        "README.md": "Tiene README",
    }
    for fname, desc in checks.items():
        if os.path.exists(os.path.join(ruta, fname)):
            resultado += f"  - {desc} ({fname})\n"

    # Leer package.json
    pkg_path = os.path.join(ruta, "package.json")
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            resultado += f"\npackage.json:\n"
            resultado += f"  Nombre: {pkg.get('name', 'N/A')}\n"
            resultado += f"  Version: {pkg.get('version', 'N/A')}\n"
            resultado += f"  Descripcion: {pkg.get('description', 'N/A')}\n"
            deps = pkg.get("dependencies", {})
            if deps:
                resultado += f"  Deps: {', '.join(list(deps.keys())[:15])}\n"
            dev_deps = pkg.get("devDependencies", {})
            if dev_deps:
                resultado += f"  DevDeps: {', '.join(list(dev_deps.keys())[:15])}\n"
            scripts = pkg.get("scripts", {})
            if scripts:
                resultado += f"  Scripts: {', '.join(scripts.keys())}\n"
        except:
            pass

    # Leer README
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
# DETECCION DE INTENCION - El corazon de v5
# ============================================================

GITHUB_URL_PATTERN = re.compile(
    r'https?://github\.com/[\w\-]+/[\w\-\.]+(?:\.git)?',
    re.IGNORECASE
)


def detectar_intencion(mensaje: str) -> dict:
    """
    Detecta que quiere el usuario ANTES de enviar al LLM.
    Retorna: {"intencion": str, "params": dict, "confianza": float}
    """
    msg = mensaje.lower()
    params = {}

    # === PRIORIDAD 1: URL de GitHub ===
    urls = GITHUB_URL_PATTERN.findall(mensaje)
    if urls:
        url = urls[0].rstrip("/")
        repo_name = url.split("/")[-1].replace(".git", "")
        # Si tiene URL de GitHub + palabras de clonar/descargar/analizar
        return {
            "intencion": "clonar_y_analizar",
            "params": {"url": url, "repo_name": repo_name},
            "confianza": 0.95
        }

    # === PRIORIDAD 2: Patrones de intencion ===

    # Instalar
    if any(w in msg for w in ["instal", "npm install", "pip install", "dependencias", "dependencies"]):
        # Buscar nombre de proyecto
        for d in os.listdir(REPOS_DIR):
            if d.lower() in msg:
                params["repo_name"] = d
                break
        return {"intencion": "instalar", "params": params, "confianza": 0.85}

    # Analizar
    if any(w in msg for w in ["analiz", "revis", "examin", "que es", "que tiene", "estructura"]):
        for d in os.listdir(REPOS_DIR):
            if d.lower() in msg:
                params["repo_name"] = d
                break
        return {"intencion": "analizar", "params": params, "confianza": 0.80}

    # Leer archivo
    if any(w in msg for w in ["leer", "mostrar", "ver archivo", "contenido de", "que hay en"]):
        # Buscar nombre de archivo
        for d in os.listdir(REPOS_DIR):
            if d.lower() in msg:
                params["repo_name"] = d
                break
        file_match = re.search(r'[\w\-]+\.\w+', mensaje)
        if file_match:
            params["archivo"] = file_match.group(0)
        return {"intencion": "leer", "params": params, "confianza": 0.75}

    # Listar
    if any(w in msg for w in ["listar", "que hay", "mostrar archivos", "que archivos"]):
        return {"intencion": "listar", "params": params, "confianza": 0.75}

    # Ejecutar comando
    if any(w in msg for w in ["ejecuta", "correr", "run ", "npm run", "npm start"]):
        cmd_match = re.search(r'(?:ejecuta|correr|run)\s+(.+)', msg)
        if cmd_match:
            params["comando"] = cmd_match.group(1).strip()
        return {"intencion": "comando", "params": params, "confianza": 0.70}

    # No se detecto intencion clara
    return {"intencion": "conversar", "params": {}, "confianza": 0.0}


# ============================================================
# EJECUCION DIRECTA - Sin pasar por el LLM
# ============================================================

def ejecutar_intencion(intencion_data: dict) -> list:
    """
    Ejecuta la intencion detectada DIRECTAMENTE.
    Retorna una lista de pasos ejecutados para mostrar al usuario.
    """
    pasos = []
    intencion = intencion_data["intencion"]
    params = intencion_data["params"]

    if intencion == "clonar_y_analizar":
        url = params.get("url", "")
        repo_name = params.get("repo_name", "")
        repo_path = os.path.join(REPOS_DIR, repo_name)

        # Paso 1: Clonar
        pasos.append({
            "accion": "clonar_repositorio",
            "detalle": f"git clone {url}",
            "resultado": clonar_repositorio(url)
        })

        # Paso 2: Analizar (auto)
        if os.path.exists(repo_path):
            pasos.append({
                "accion": "analizar_proyecto",
                "detalle": f"Analizando {repo_path}",
                "resultado": analizar_proyecto(repo_path)
            })

        # Paso 3: Si tiene package.json, sugerir instalar
        if os.path.exists(os.path.join(repo_path, "package.json")):
            pasos.append({
                "accion": "sugerencia",
                "detalle": "Dependencias Node.js detectadas",
                "resultado": f"Se detecto package.json. Escribe 'instalar dependencias {repo_name}' para instalarlas."
            })

    elif intencion == "instalar":
        repo_name = params.get("repo_name", "")
        if repo_name:
            repo_path = os.path.join(REPOS_DIR, repo_name)
        else:
            # Buscar primer repo con package.json o requirements.txt
            for d in os.listdir(REPOS_DIR):
                full = os.path.join(REPOS_DIR, d)
                if os.path.isdir(full):
                    if os.path.exists(os.path.join(full, "package.json")) or os.path.exists(os.path.join(full, "requirements.txt")):
                        repo_name = d
                        repo_path = full
                        break
            else:
                repo_path = REPOS_DIR

        pasos.append({
            "accion": "instalar_dependencias",
            "detalle": f"Instalando en {repo_path}",
            "resultado": instalar_dependencias(repo_path)
        })

    elif intencion == "analizar":
        repo_name = params.get("repo_name", "")
        if repo_name:
            repo_path = os.path.join(REPOS_DIR, repo_name)
        else:
            repo_path = REPOS_DIR
        pasos.append({
            "accion": "analizar_proyecto",
            "detalle": f"Analizando {repo_path}",
            "resultado": analizar_proyecto(repo_path)
        })

    elif intencion == "leer":
        repo_name = params.get("repo_name", "")
        archivo = params.get("archivo", "")
        if repo_name and archivo:
            ruta = os.path.join(REPOS_DIR, repo_name, archivo)
        elif archivo:
            ruta = archivo
        else:
            ruta = ""
        if ruta:
            pasos.append({
                "accion": "leer_archivo",
                "detalle": f"Leyendo {ruta}",
                "resultado": leer_archivo(ruta)
            })
        else:
            pasos.append({
                "accion": "error",
                "detalle": "Falta archivo",
                "resultado": "Especifica que archivo quieres leer, ej: 'leer README.md de signalTrade'"
            })

    elif intencion == "listar":
        pasos.append({
            "accion": "listar_archivos",
            "detalle": f"Listando {REPOS_DIR}",
            "resultado": listar_archivos(REPOS_DIR)
        })

    elif intencion == "comando":
        comando = params.get("comando", "")
        if comando:
            pasos.append({
                "accion": "ejecutar_comando",
                "detalle": f"Ejecutando: {comando}",
                "resultado": ejecutar_comando(comando)
            })
        else:
            pasos.append({
                "accion": "error",
                "detalle": "Falta comando",
                "resultado": "Especifica el comando, ej: 'ejecuta git status'"
            })

    return pasos


# ============================================================
# LLM - Solo para conversacion y analisis complejo
# ============================================================

SYSTEM_PROMPT = """Eres un agente autonomo que EJECUTA acciones reales.

REGLAS:
1. NUNCA des instrucciones. EJECUTA.
2. NUNCA digas "puedes hacer..." o "ejecuta el comando..."
3. Habla en español.
4. Se conciso.
5. Si ya se ejecuto una accion, reporta el resultado.

Herramientas disponibles:
- ejecutar_comando(comando) - Ejecuta en terminal
- clonar_repositorio(url) - Clona un repo de GitHub
- instalar_dependencias(ruta) - Instala deps (npm, pip, etc.)
- leer_archivo(ruta) - Lee un archivo
- listar_archivos(ruta) - Lista directorio
- analizar_proyecto(ruta) - Analiza un proyecto
- escribir_archivo(ruta, contenido) - Crea/modifica archivo
"""


def preguntar_llm(mensaje: str, historial: list = None) -> str:
    """Usa el LLM solo para conversacion o analisis complejo."""
    try:
        import ollama
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if historial:
            for h in historial[-4:]:
                messages.append(h)

        messages.append({"role": "user", "content": mensaje})

        response = ollama.chat(model=AGENT_MODEL, messages=messages)
        return response.get("message", {}).get("content", "Sin respuesta.")
    except Exception as e:
        return f"Error del modelo: {e}"


# ============================================================
# PROCESAMIENTO PRINCIPAL
# ============================================================

def procesar_mensaje(user_message: str) -> tuple:
    """
    Procesa un mensaje del usuario.
    Retorna: (respuesta_html, pasos_debug)
    """
    pasos_debug = []

    # 1. Detectar intencion
    intencion = detectar_intencion(user_message)
    pasos_debug.append(f"Intencion: {intencion['intencion']} (confianza: {intencion['confianza']:.0%})")
    pasos_debug.append(f"Params: {intencion['params']}")

    # 2. Si la intencion es clara, ejecutar directamente
    if intencion["confianza"] >= 0.7 and intencion["intencion"] != "conversar":
        pasos_debug.append(">> EJECUCION DIRECTA (sin LLM)")

        pasos = ejecutar_intencion(intencion)

        # Construir respuesta visual
        respuesta = ""
        for i, paso in enumerate(pasos, 1):
            accion = paso["accion"]
            detalle = paso["detalle"]
            resultado = paso["resultado"]

            pasos_debug.append(f"  Paso {i}: {accion} -> {detalle}")

            if accion == "sugerencia":
                respuesta += f"💡 **{detalle}**\n\n{resultado}\n\n"
            elif "ERROR" in resultado or "Error" in resultado:
                respuesta += f"❌ **Paso {i}: {accion}** — {detalle}\n```\n{resultado}\n```\n\n"
            else:
                respuesta += f"✅ **Paso {i}: {accion}** — {detalle}\n```\n{resultado}\n```\n\n"

        return respuesta, pasos_debug

    # 3. Si no es clara, usar LLM con tool calling
    else:
        pasos_debug.append(">> Usando LLM (intencion no clara)")

        try:
            import ollama
        except ImportError:
            return "Error: ollama no esta instalado. Ejecuta: pip install ollama", pasos_debug

        # Definir herramientas para Ollama
        ollama_tools = [
            {
                "type": "function",
                "function": {
                    "name": "ejecutar_comando",
                    "description": "Ejecuta un comando en la terminal del sistema.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "comando": {"type": "string", "description": "Comando a ejecutar"}
                        },
                        "required": ["comando"]
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
                    "description": "Instala dependencias de un proyecto.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ruta": {"type": "string", "description": "Ruta del proyecto"},
                            "gestor": {"type": "string", "description": "npm, pip, auto"}
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
                    "name": "listar_archivos",
                    "description": "Lista archivos de un directorio.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ruta": {"type": "string", "description": "Ruta del directorio"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analizar_proyecto",
                    "description": "Analiza la estructura de un proyecto.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ruta": {"type": "string", "description": "Ruta del proyecto"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "escribir_archivo",
                    "description": "Crea o modifica un archivo.",
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
        ]

        function_map = {
            "ejecutar_comando": ejecutar_comando,
            "clonar_repositorio": clonar_repositorio,
            "instalar_dependencias": lambda ruta, gestor="auto": instalar_dependencias(ruta, gestor),
            "leer_archivo": leer_archivo,
            "listar_archivos": listar_archivos,
            "analizar_proyecto": analizar_proyecto,
            "escribir_archivo": escribir_archivo,
        }

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]

        respuesta_final = ""
        tool_results = []

        for iteration in range(MAX_ITERATIONS):
            pasos_debug.append(f"  LLM iteracion {iteration + 1}")

            try:
                response = ollama.chat(
                    model=AGENT_MODEL,
                    messages=messages,
                    tools=ollama_tools
                )
            except Exception as e:
                pasos_debug.append(f"  ERROR LLM: {e}")
                respuesta_final = f"Error del modelo: {e}"
                break

            msg = response.get("message", {})

            # Si no hay tool calls, es la respuesta final
            if not msg.get("tool_calls"):
                respuesta_final = msg.get("content", "")
                break

            # Procesar tool calls
            for tool_call in msg.get("tool_calls", []):
                func_name = tool_call.get("function", {}).get("name")
                func_args = tool_call.get("function", {}).get("arguments", {})

                pasos_debug.append(f"  Tool call: {func_name}({func_args})")

                if func_name in function_map:
                    try:
                        result = function_map[func_name](**func_args)
                    except Exception as e:
                        result = f"Error: {e}"
                else:
                    result = f"Funcion no encontrada: {func_name}"

                tool_results.append({
                    "tool": func_name,
                    "args": func_args,
                    "result": result
                })

                pasos_debug.append(f"  Resultado: {result[:100]}...")

                messages.append({"role": "assistant", "content": f"[Ejecutando {func_name}({func_args})]"})
                messages.append({"role": "user", "content": f"Resultado de {func_name}:\n{result}\n\nContinua."})

        # Construir respuesta
        if tool_results and not respuesta_final:
            respuesta_final = "**Acciones ejecutadas:**\n\n"
            for tr in tool_results:
                respuesta_final += f"- **{tr['tool']}**({tr['args']}):\n```\n{tr['result']}\n```\n\n"

        return respuesta_final, pasos_debug


# ============================================================
# INTERFAZ STREAMLIT
# ============================================================

def main():
    st.set_page_config(
        page_title="Agente Autonomo Local v5",
        page_icon="🤖",
        layout="wide"
    )

    st.markdown("""
    <style>
    .stApp { max-width: 1200px; margin: 0 auto; }
    .debug-box { background: #1a1a2e; color: #00ff88; padding: 10px; border-radius: 5px;
                font-family: monospace; font-size: 11px; max-height: 300px; overflow-y: auto;
                white-space: pre-wrap; word-break: break-all; }
    .step-ok { background: #0d2818; border-left: 4px solid #00ff88; padding: 8px; margin: 5px 0; border-radius: 3px; }
    .step-err { background: #2d0d0d; border-left: 4px solid #ff4444; padding: 8px; margin: 5px 0; border-radius: 3px; }
    .step-info { background: #0d1a2d; border-left: 4px solid #4488ff; padding: 8px; margin: 5px 0; border-radius: 3px; }
    </style>
    """, unsafe_allow_html=True)

    # Inicializar session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "debug_log" not in st.session_state:
        st.session_state.debug_log = []

    st.title("🤖 Agente Autonomo Local v5")
    st.caption("Ejecucion directa con debug visible — Detecta intencion y ejecuta SIN pasar por el LLM")

    # === SIDEBAR ===
    with st.sidebar:
        st.header("⚙️ Config")
        st.write(f"**Modelo:** {AGENT_MODEL}")
        st.write(f"**Repos dir:** {REPOS_DIR}")
        st.write(f"**SO:** {platform.system()}")

        if st.button("🗑️ Limpiar historial", use_container_width=True):
            st.session_state.messages = []
            st.session_state.debug_log = []
            st.rerun()

        if st.button("🧪 Test: git clone", use_container_width=True):
            resultado = clonar_repositorio("https://github.com/yecos/signalTrade")
            st.code(resultado)

        if st.button("🧪 Test: listar repos", use_container_width=True):
            resultado = listar_archivos(REPOS_DIR)
            st.code(resultado)

        if st.button("🧪 Test: analizar signalTrade", use_container_width=True):
            repo_path = os.path.join(REPOS_DIR, "signalTrade")
            if os.path.exists(repo_path):
                resultado = analizar_proyecto(repo_path)
                st.code(resultado)
            else:
                st.error("signalTrade no encontrado. Clona primero.")

        st.header("🐛 Debug Log")
        if st.session_state.debug_log:
            log_text = "\n".join(st.session_state.debug_log[-30:])
            st.markdown(f'<div class="debug-box">{log_text}</div>', unsafe_allow_html=True)

        st.header("📁 Repos")
        try:
            repos = [d for d in os.listdir(REPOS_DIR)
                     if os.path.isdir(os.path.join(REPOS_DIR, d)) and not d.startswith(".")]
            for repo in repos:
                st.write(f"📂 {repo}")
        except:
            st.write("Sin repos")

    # === MOSTRAR HISTORIAL ===
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # === INPUT ===
    if prompt := st.chat_input("Escribe tu mensaje..."):
        # Mostrar mensaje del usuario
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Procesar
        with st.chat_message("assistant"):
            with st.spinner("Procesando..."):
                try:
                    respuesta, pasos_debug = procesar_mensaje(prompt)

                    # Mostrar debug de intencion detectada
                    if pasos_debug:
                        debug_text = "\n".join(pasos_debug)
                        st.session_state.debug_log.extend(pasos_debug)
                        with st.expander("🔍 Debug (click para ver)", expanded=False):
                            st.markdown(f'<div class="debug-box">{debug_text}</div>', unsafe_allow_html=True)

                    st.markdown(respuesta)
                except Exception as e:
                    respuesta = f"**ERROR:** {e}\n\nRevisa la consola de Streamlit para mas detalles."
                    st.error(respuesta)
                    st.session_state.debug_log.append(f"ERROR GLOBAL: {e}")

        st.session_state.messages.append({"role": "assistant", "content": respuesta})


if __name__ == "__main__":
    main()
