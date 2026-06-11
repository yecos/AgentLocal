"""
=============================================================
 AGENTE LOCAL AUTONOMO v6 - AUTO-MEJORABLE
 Detecta intencion + Ejecuta directamente + Aprende de errores
 + Feedback de usuario + Auto-reflexion + Patrones aprendidos
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
MAX_ITERATIONS = 6

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
CONVERSATIONS_FILE = os.path.join(LEARN_DIR, "conversations.json")


# ============================================================
# SISTEMA DE APRENDIZAJE - Auto-mejora
# ============================================================

class LearningSystem:
    """Sistema de auto-mejora del agente."""

    @staticmethod
    def _load_json(filepath: str, default=None):
        if default is None:
            default = []
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return default

    @staticmethod
    def _save_json(filepath: str, data):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error guardando {filepath}: {e}")

    # --- CORRECCIONES ---

    def save_correction(self, user_message: str, wrong_action: str, correct_action: str, reason: str = ""):
        """Guarda una correccion del usuario para no repetir el error."""
        corrections = self._load_json(CORRECTIONS_FILE, [])
        corrections.append({
            "timestamp": datetime.now().isoformat(),
            "user_message": user_message,
            "wrong_action": wrong_action,
            "correct_action": correct_action,
            "reason": reason
        })
        self._save_json(CORRECTIONS_FILE, corrections)

    def get_corrections(self) -> list:
        """Obtiene todas las correcciones guardadas."""
        return self._load_json(CORRECTIONS_FILE, [])

    def check_corrections(self, user_message: str, proposed_action: str) -> dict:
        """Verifica si una accion propuesta fue corregida antes."""
        corrections = self.get_corrections()
        msg_lower = user_message.lower()

        for corr in corrections:
            # Buscar correcciones para mensajes similares
            if any(w in msg_lower for w in corr["user_message"].lower().split()):
                if corr["wrong_action"] == proposed_action:
                    return {
                        "corrected": True,
                        "correct_action": corr["correct_action"],
                        "reason": corr.get("reason", "")
                    }
        return {"corrected": False}

    # --- FEEDBACK ---

    def save_feedback(self, user_message: str, agent_response: str, action_taken: str, rating: str, comment: str = ""):
        """Guarda el feedback del usuario (positivo/negativo)."""
        feedback = self._load_json(FEEDBACK_FILE, [])
        feedback.append({
            "timestamp": datetime.now().isoformat(),
            "user_message": user_message,
            "agent_response": agent_response[:200],
            "action_taken": action_taken,
            "rating": rating,  # "positive" or "negative"
            "comment": comment
        })
        self._save_json(FEEDBACK_FILE, feedback)

    def get_feedback_stats(self) -> dict:
        """Obtiene estadisticas de feedback."""
        feedback = self._load_json(FEEDBACK_FILE, [])
        if not feedback:
            return {"total": 0, "positive": 0, "negative": 0, "best_actions": [], "worst_actions": []}

        positive = [f for f in feedback if f["rating"] == "positive"]
        negative = [f for f in feedback if f["rating"] == "negative"]

        # Encontrar las acciones mas exitosas y las que fallan
        action_counts = {}
        for f in feedback:
            action = f.get("action_taken", "unknown")
            if action not in action_counts:
                action_counts[action] = {"positive": 0, "negative": 0}
            action_counts[action][f["rating"]] += 1

        best = sorted(action_counts.items(), key=lambda x: x[1]["positive"], reverse=True)[:5]
        worst = sorted(action_counts.items(), key=lambda x: x[1]["negative"], reverse=True)[:5]

        return {
            "total": len(feedback),
            "positive": len(positive),
            "negative": len(negative),
            "best_actions": [(a, c) for a, c in best],
            "worst_actions": [(a, c) for a, c in worst]
        }

    # --- PATRONES APRENDIDOS ---

    def save_pattern(self, trigger: str, actions: list, context: str = ""):
        """Guarda un patron de acciones que el usuario repite."""
        patterns = self._load_json(PATTERNS_FILE, [])
        # Verificar si ya existe un patron similar
        for p in patterns:
            if p["trigger"].lower() == trigger.lower():
                p["actions"] = actions
                p["last_used"] = datetime.now().isoformat()
                p["use_count"] = p.get("use_count", 0) + 1
                self._save_json(PATTERNS_FILE, patterns)
                return

        patterns.append({
            "trigger": trigger,
            "actions": actions,
            "context": context,
            "created": datetime.now().isoformat(),
            "last_used": datetime.now().isoformat(),
            "use_count": 1
        })
        self._save_json(PATTERNS_FILE, patterns)

    def get_patterns(self) -> list:
        """Obtiene los patrones aprendidos."""
        return self._load_json(PATTERNS_FILE, [])

    def match_pattern(self, user_message: str) -> list:
        """Busca si el mensaje coincide con un patron aprendido."""
        patterns = self.get_patterns()
        msg_lower = user_message.lower()

        matched = []
        for p in patterns:
            # Coincidencia simple por palabras clave
            trigger_words = p["trigger"].lower().split()
            match_count = sum(1 for w in trigger_words if w in msg_lower)
            if match_count >= len(trigger_words) * 0.6:  # 60% de coincidencia
                matched.append(p)

        # Ordenar por uso (los mas usados primero)
        matched.sort(key=lambda x: x.get("use_count", 0), reverse=True)
        return matched

    # --- CONOCIMIENTO ---

    def save_knowledge(self, topic: str, content: str, source: str = "conversation"):
        """Guarda conocimiento adquirido para uso futuro."""
        knowledge = self._load_json(KNOWLEDGE_FILE, [])

        # Verificar si ya existe
        for k in knowledge:
            if k["topic"].lower() == topic.lower():
                k["content"] = content
                k["updated"] = datetime.now().isoformat()
                self._save_json(KNOWLEDGE_FILE, knowledge)
                return

        knowledge.append({
            "topic": topic,
            "content": content,
            "source": source,
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat()
        })
        self._save_json(KNOWLEDGE_FILE, knowledge)

    def get_knowledge(self, topic: str = None) -> list:
        """Obtiene conocimiento guardado."""
        knowledge = self._load_json(KNOWLEDGE_FILE, [])
        if topic:
            return [k for k in knowledge if topic.lower() in k["topic"].lower()]
        return knowledge

    # --- AUTO-REFLEXION ---

    def self_reflect(self, action: str, result: str, user_message: str) -> dict:
        """El agente reflexiona sobre si su accion fue correcta."""
        reflection = {
            "action": action,
            "success": True,
            "lesson": "",
            "improvement": ""
        }

        # Detectar fallos comunes
        if "ERROR" in result or "Error" in result:
            reflection["success"] = False

            if "no existe" in result.lower() or "not found" in result.lower():
                reflection["lesson"] = "Verificar que la ruta existe antes de intentar leer/ejecutar"
                reflection["improvement"] = "listar_archivos primero para confirmar rutas"

            elif "timeout" in result.lower():
                reflection["lesson"] = "El comando tardo demasiado"
                reflection["improvement"] = "Usar comandos mas especificos o aumentar timeout"

            elif "permission" in result.lower() or "denegado" in result.lower():
                reflection["lesson"] = "Sin permisos para ejecutar"
                reflection["improvement"] = "Sugerir ejecutar como administrador"

            elif "already exists" in result.lower() or "ya existe" in result.lower():
                reflection["success"] = True  # No es realmente un error
                reflection["lesson"] = "El recurso ya existe, usarlo en vez de recrear"

        # Guardar la reflexion como conocimiento
        if reflection["lesson"]:
            self.save_knowledge(
                f"leccion:{action}",
                reflection["lesson"],
                source="auto_reflection"
            )

        return reflection

    # --- ESTADISTICAS ---

    def get_stats(self) -> dict:
        """Obtiene estadisticas generales del sistema de aprendizaje."""
        corrections = self.get_corrections()
        patterns = self.get_patterns()
        knowledge = self.get_knowledge()
        feedback_stats = self.get_feedback_stats()

        return {
            "corrections_count": len(corrections),
            "patterns_count": len(patterns),
            "knowledge_count": len(knowledge),
            "feedback": feedback_stats,
            "total_learning_items": len(corrections) + len(patterns) + len(knowledge)
        }


# Instancia global del sistema de aprendizaje
learning = LearningSystem()


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
        git_dir = os.path.join(target_dir, ".git")
        contenido = os.listdir(target_dir) if os.path.isdir(target_dir) else []
        archivos_reales = [f for f in contenido if f != ".git"]

        if os.path.exists(git_dir) and len(archivos_reales) > 1:
            return f"Repositorio ya existe y esta completo en: {target_dir}\nCarpetas: {[f for f in contenido if os.path.isdir(os.path.join(target_dir, f))]}\nArchivos: {archivos_reales[:10]}..."
        else:
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
            # Guardar conocimiento sobre este repo
            learning.save_knowledge(f"repo:{repo_name}", f"Clonado desde {url} en {target_dir}")
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
        "bun": f'cd "{ruta}" && bun install',
    }

    comando = comandos.get(gestor, f'cd "{ruta}" && {gestor} install')
    resultado = ejecutar_comando(comando)

    # Guardar conocimiento
    if "ERROR" not in resultado:
        repo_name = os.path.basename(ruta)
        learning.save_knowledge(f"deps:{repo_name}", f"Dependencias instaladas con {gestor}")

    return resultado


def leer_archivo(ruta: str) -> str:
    rutas_posibles = [ruta]
    if not os.path.isabs(ruta):
        rutas_posibles.append(os.path.join(REPOS_DIR, ruta))
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

    # Guardar conocimiento del proyecto
    repo_name = os.path.basename(ruta)
    learning.save_knowledge(f"proyecto:{repo_name}", f"Analizado: {ruta}. Tipo: Next.js/TypeScript")

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
# DETECCION DE INTENCION - Con aprendizaje integrado
# ============================================================

GITHUB_URL_PATTERN = re.compile(
    r'https?://github\.com/[\w\-]+/[\w\-\.]+(?:\.git)?',
    re.IGNORECASE
)


def detectar_intencion(mensaje: str) -> dict:
    """
    Detecta que quiere el usuario, CON aprendizaje previo.
    Primero consulta correcciones y patrones aprendidos.
    """
    msg = mensaje.lower()
    params = {}

    # === PASO 0: Consultar patrones aprendidos ===
    matched_patterns = learning.match_pattern(mensaje)
    if matched_patterns:
        best = matched_patterns[0]
        # Actualizar uso del patron
        best["last_used"] = datetime.now().isoformat()
        best["use_count"] = best.get("use_count", 0) + 1
        # Guardar patron actualizado
        patterns = learning.get_patterns()
        for p in patterns:
            if p["trigger"] == best["trigger"]:
                p["use_count"] = best["use_count"]
                p["last_used"] = best["last_used"]
        learning._save_json(PATTERNS_FILE, patterns)

        # Retornar las acciones del patron
        return {
            "intencion": "patron_aprendido",
            "params": {"actions": best["actions"], "pattern_name": best["trigger"]},
            "confianza": 0.90
        }

    # === PRIORIDAD 1: URL de GitHub ===
    urls = GITHUB_URL_PATTERN.findall(mensaje)
    if urls:
        url = urls[0].rstrip("/")
        repo_name = url.split("/")[-1].replace(".git", "")
        return {
            "intencion": "clonar_y_analizar",
            "params": {"url": url, "repo_name": repo_name},
            "confianza": 0.95
        }

    # === PRIORIDAD 2: Patrones de intencion ===

    # Instalar
    if any(w in msg for w in ["instal", "npm install", "pip install", "dependencias", "dependencies"]):
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
# EJECUCION DIRECTA - Con auto-reflexion
# ============================================================

def ejecutar_intencion(intencion_data: dict) -> list:
    """
    Ejecuta la intencion detectada DIRECTAMENTE.
    Incluye auto-reflexion despues de cada accion.
    """
    pasos = []
    intencion = intencion_data["intencion"]
    params = intencion_data["params"]

    if intencion == "patron_aprendido":
        # Ejecutar secuencia de acciones aprendidas
        actions = params.get("actions", [])
        for action in actions:
            action_type = action.get("type", "")
            action_params = action.get("params", {})

            if action_type == "clonar_repositorio":
                result = clonar_repositorio(action_params.get("url", ""))
            elif action_type == "analizar_proyecto":
                result = analizar_proyecto(action_params.get("ruta", ""))
            elif action_type == "instalar_dependencias":
                result = instalar_dependencias(action_params.get("ruta", ""))
            elif action_type == "leer_archivo":
                result = leer_archivo(action_params.get("ruta", ""))
            elif action_type == "listar_archivos":
                result = listar_archivos(action_params.get("ruta"))
            elif action_type == "ejecutar_comando":
                result = ejecutar_comando(action_params.get("comando", ""))
            else:
                result = f"Accion desconocida: {action_type}"

            # Auto-reflexion
            reflection = learning.self_reflect(action_type, result, "")

            pasos.append({
                "accion": action_type,
                "detalle": f"Patron aprendido: {params.get('pattern_name', '')}",
                "resultado": result,
                "reflection": reflection
            })

        return pasos

    if intencion == "clonar_y_analizar":
        url = params.get("url", "")
        repo_name = params.get("repo_name", "")
        repo_path = os.path.join(REPOS_DIR, repo_name)

        # Paso 1: Clonar
        result = clonar_repositorio(url)
        reflection = learning.self_reflect("clonar_repositorio", result, url)
        pasos.append({
            "accion": "clonar_repositorio",
            "detalle": f"git clone {url}",
            "resultado": result,
            "reflection": reflection
        })

        # Paso 2: Analizar (auto)
        if os.path.exists(repo_path):
            result = analizar_proyecto(repo_path)
            reflection = learning.self_reflect("analizar_proyecto", result, repo_path)
            pasos.append({
                "accion": "analizar_proyecto",
                "detalle": f"Analizando {repo_path}",
                "resultado": result,
                "reflection": reflection
            })

        # Paso 3: Si tiene package.json, sugerir instalar
        if os.path.exists(os.path.join(repo_path, "package.json")):
            pasos.append({
                "accion": "sugerencia",
                "detalle": "Dependencias Node.js detectadas",
                "resultado": f"Se detecto package.json. Escribe 'instalar dependencias {repo_name}' para instalarlas."
            })

        # APRENDER: Guardar patron "clonar + analizar"
        learning.save_pattern(
            trigger=f"clona analiza {repo_name}",
            actions=[
                {"type": "clonar_repositorio", "params": {"url": url}},
                {"type": "analizar_proyecto", "params": {"ruta": repo_path}}
            ],
            context=f"Usuario pidio clonar y analizar {repo_name}"
        )

    elif intencion == "instalar":
        repo_name = params.get("repo_name", "")
        if repo_name:
            repo_path = os.path.join(REPOS_DIR, repo_name)
        else:
            for d in os.listdir(REPOS_DIR):
                full = os.path.join(REPOS_DIR, d)
                if os.path.isdir(full):
                    if os.path.exists(os.path.join(full, "package.json")) or os.path.exists(os.path.join(full, "requirements.txt")):
                        repo_name = d
                        repo_path = full
                        break
            else:
                repo_path = REPOS_DIR

        result = instalar_dependencias(repo_path)
        reflection = learning.self_reflect("instalar_dependencias", result, repo_path)
        pasos.append({
            "accion": "instalar_dependencias",
            "detalle": f"Instalando en {repo_path}",
            "resultado": result,
            "reflection": reflection
        })

    elif intencion == "analizar":
        repo_name = params.get("repo_name", "")
        if repo_name:
            repo_path = os.path.join(REPOS_DIR, repo_name)
        else:
            repo_path = REPOS_DIR
        result = analizar_proyecto(repo_path)
        reflection = learning.self_reflect("analizar_proyecto", result, repo_path)
        pasos.append({
            "accion": "analizar_proyecto",
            "detalle": f"Analizando {repo_path}",
            "resultado": result,
            "reflection": reflection
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
            result = leer_archivo(ruta)
            reflection = learning.self_reflect("leer_archivo", result, ruta)
            pasos.append({
                "accion": "leer_archivo",
                "detalle": f"Leyendo {ruta}",
                "resultado": result,
                "reflection": reflection
            })
        else:
            pasos.append({
                "accion": "error",
                "detalle": "Falta archivo",
                "resultado": "Especifica que archivo quieres leer, ej: 'leer README.md de signalTrade'"
            })

    elif intencion == "listar":
        result = listar_archivos(REPOS_DIR)
        pasos.append({
            "accion": "listar_archivos",
            "detalle": f"Listando {REPOS_DIR}",
            "resultado": result
        })

    elif intencion == "comando":
        comando = params.get("comando", "")
        if comando:
            result = ejecutar_comando(comando)
            reflection = learning.self_reflect("ejecutar_comando", result, comando)
            pasos.append({
                "accion": "ejecutar_comando",
                "detalle": f"Ejecutando: {comando}",
                "resultado": result,
                "reflection": reflection
            })
        else:
            pasos.append({
                "accion": "error",
                "detalle": "Falta comando",
                "resultado": "Especifica el comando, ej: 'ejecuta git status'"
            })

    return pasos


# ============================================================
# DETECCION DE CORRECCIONES DEL USUARIO
# ============================================================

def detectar_correccion(mensaje: str, last_action: str = "") -> dict:
    """
    Detecta si el usuario esta corrigiendo al agente.
    Ej: "no, clona el repo" o "eso esta mal, instala las deps"
    """
    msg = mensaje.lower()

    correction_patterns = [
        r'no[,!]\s*(.+)',           # "no, clona el repo"
        r'eso esta mal[,]\s*(.+)',  # "eso esta mal, instala las deps"
        r'no hiciste\s+(.+)',       # "no hiciste lo que pedi"
        r'te equivocaste[,]\s*(.+)',# "te equivocaste, usa clonar"
        r' Mejor\s+(.+)',           # "mejor clona el repo"
        r'en vez de\s+.+\s+haz\s+(.+)', # "en vez de listar haz clonar"
        r'queria\s+que\s+(.+)',     # "queria que clonaras"
        r'sigue sin funcionar',     # "sigue sin funcionar"
    ]

    for pattern in correction_patterns:
        match = re.search(pattern, msg)
        if match:
            return {
                "is_correction": True,
                "correction_text": match.group(1) if match.lastindex else mensaje,
                "original_action": last_action,
                "full_message": mensaje
            }

    return {"is_correction": False}


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
6. Si el usuario corrige algo, aprende y no repitas el error.

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
    try:
        import ollama

        # Incluir lecciones aprendidas en el system prompt
        knowledge = learning.get_knowledge()
        lessons = [k for k in knowledge if k["topic"].startswith("leccion:")]
        lessons_text = ""
        if lessons:
            lessons_text = "\n\nLecciones aprendidas:\n"
            for l in lessons[-5:]:
                lessons_text += f"- {l['content']}\n"

        enhanced_prompt = SYSTEM_PROMPT + lessons_text

        messages = [{"role": "system", "content": enhanced_prompt}]

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
    Procesa un mensaje del usuario con auto-mejora.
    Retorna: (respuesta_html, pasos_debug)
    """
    pasos_debug = []

    # 0. Detectar si es una correccion
    last_action = st.session_state.get("last_action", "")
    correction = detectar_correccion(user_message, last_action)

    if correction["is_correction"]:
        pasos_debug.append(f">> CORRECCION detectada: {correction['correction_text']}")

        # Guardar la correccion
        learning.save_correction(
            user_message=correction["full_message"],
            wrong_action=last_action,
            correct_action=correction["correction_text"],
            reason=correction.get("full_message", "")
        )
        pasos_debug.append(f">> Correccion guardada para aprendizaje")

        # Re-procesar con el mensaje corregido
        intencion = detectar_intencion(correction["correction_text"])
        pasos_debug.append(f"Intencion corregida: {intencion['intencion']} (confianza: {intencion['confianza']:.0%})")

    else:
        # 1. Detectar intencion normalmente
        intencion = detectar_intencion(user_message)
        pasos_debug.append(f"Intencion: {intencion['intencion']} (confianza: {intencion['confianza']:.0%})")
        pasos_debug.append(f"Params: {intencion['params']}")

    # 2. Si la intencion es clara, ejecutar directamente
    if intencion["confianza"] >= 0.7 and intencion["intencion"] != "conversar":
        pasos_debug.append(">> EJECUCION DIRECTA (sin LLM)")

        pasos = ejecutar_intencion(intencion)

        # Guardar ultima accion para correcciones
        if pasos:
            st.session_state["last_action"] = pasos[0].get("accion", "")

        # Construir respuesta visual
        respuesta = ""
        for i, paso in enumerate(pasos, 1):
            accion = paso["accion"]
            detalle = paso["detalle"]
            resultado = paso["resultado"]
            reflection = paso.get("reflection", {})

            pasos_debug.append(f"  Paso {i}: {accion} -> {detalle}")

            # Mostrar auto-reflexion si hay leccion
            if reflection and reflection.get("lesson"):
                pasos_debug.append(f"  Reflexion: {reflection['lesson']}")

            if accion == "sugerencia":
                respuesta += f"💡 **{detalle}**\n\n{resultado}\n\n"
            elif "ERROR" in resultado or "Error" in resultado:
                respuesta += f"❌ **Paso {i}: {accion}** — {detalle}\n```\n{resultado}\n```\n\n"
                # Si hay mejora sugerida, mostrarla
                if reflection and reflection.get("improvement"):
                    respuesta += f"🔧 Auto-mejora: {reflection['improvement']}\n\n"
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

        # Incluir lecciones aprendidas en el prompt
        knowledge = learning.get_knowledge()
        lessons = [k for k in knowledge if k["topic"].startswith("leccion:")]
        lessons_text = ""
        if lessons:
            lessons_text = "\n\nLecciones aprendidas de errores previos:\n"
            for l in lessons[-5:]:
                lessons_text += f"- {l['content']}\n"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + lessons_text},
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

            if not msg.get("tool_calls"):
                respuesta_final = msg.get("content", "")
                break

            for tool_call in msg.get("tool_calls", []):
                func_name = tool_call.get("function", {}).get("name")
                func_args = tool_call.get("function", {}).get("arguments", {})

                # Verificar correcciones antes de ejecutar
                correction_check = learning.check_corrections(user_message, func_name)
                if correction_check["corrected"]:
                    pasos_debug.append(f"  CORRECCION APLICADA: {func_name} -> {correction_check['correct_action']}")
                    func_name = correction_check["correct_action"]

                pasos_debug.append(f"  Tool call: {func_name}({func_args})")

                if func_name in function_map:
                    try:
                        result = function_map[func_name](**func_args)
                    except Exception as e:
                        result = f"Error: {e}"
                else:
                    result = f"Funcion no encontrada: {func_name}"

                # Auto-reflexion
                reflection = learning.self_reflect(func_name, result, user_message)
                if reflection.get("lesson"):
                    pasos_debug.append(f"  Reflexion: {reflection['lesson']}")

                tool_results.append({
                    "tool": func_name,
                    "args": func_args,
                    "result": result
                })

                pasos_debug.append(f"  Resultado: {result[:100]}...")

                messages.append({"role": "assistant", "content": f"[Ejecutando {func_name}({func_args})]"})
                messages.append({"role": "user", "content": f"Resultado de {func_name}:\n{result}\n\nContinua."})

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
        page_title="Agente Autonomo Local v6",
        page_icon="🧠",
        layout="wide"
    )

    st.markdown("""
    <style>
    .stApp { max-width: 1200px; margin: 0 auto; }
    .debug-box { background: #1a1a2e; color: #00ff88; padding: 10px; border-radius: 5px;
                font-family: monospace; font-size: 11px; max-height: 300px; overflow-y: auto;
                white-space: pre-wrap; word-break: break-all; }
    .learning-box { background: #1a2e1a; color: #88ff88; padding: 10px; border-radius: 5px;
                   font-family: monospace; font-size: 11px; max-height: 250px; overflow-y: auto; }
    .feedback-positive { color: #00ff88; }
    .feedback-negative { color: #ff4444; }
    </style>
    """, unsafe_allow_html=True)

    # Inicializar session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "debug_log" not in st.session_state:
        st.session_state.debug_log = []
    if "last_action" not in st.session_state:
        st.session_state["last_action"] = ""
    if "feedback_pending" not in st.session_state:
        st.session_state.feedback_pending = None

    st.title("🧠 Agente Autonomo Local v6")
    st.caption("Auto-mejorable — Aprende de correcciones, feedback y auto-reflexion")

    # === SIDEBAR ===
    with st.sidebar:
        st.header("⚙️ Config")
        st.write(f"**Modelo:** {AGENT_MODEL}")
        st.write(f"**Repos dir:** {REPOS_DIR}")
        st.write(f"**Aprendizaje:** {LEARN_DIR}")
        st.write(f"**SO:** {platform.system()}")

        if st.button("🗑️ Limpiar historial", use_container_width=True):
            st.session_state.messages = []
            st.session_state.debug_log = []
            st.rerun()

        # === ESTADISTICAS DE APRENDIZAJE ===
        st.header("📊 Aprendizaje")
        stats = learning.get_stats()
        st.metric("Correcciones", stats["corrections_count"])
        st.metric("Patrones", stats["patterns_count"])
        st.metric("Conocimiento", stats["knowledge_count"])
        fb = stats["feedback"]
        st.metric("Feedback", f"👍{fb['positive']} 👎{fb['negative']}")

        # Ver datos de aprendizaje
        with st.expander("📚 Ver datos de aprendizaje"):
            tab1, tab2, tab3 = st.tabs(["Correcciones", "Patrones", "Conocimiento"])

            with tab1:
                corrections = learning.get_corrections()
                if corrections:
                    for c in corrections[-5:]:
                        st.markdown(f"**❌ {c['wrong_action']}** → **✅ {c['correct_action']}**")
                        st.caption(f"_{c['user_message']}_ — {c['timestamp'][:16]}")
                        st.divider()
                else:
                    st.info("Sin correcciones aun")

            with tab2:
                patterns = learning.get_patterns()
                if patterns:
                    for p in patterns:
                        st.markdown(f"**🔄 {p['trigger']}** (usado {p.get('use_count', 1)}x)")
                        for a in p["actions"]:
                            st.write(f"  → {a['type']}({a.get('params', {})})")
                        st.divider()
                else:
                    st.info("Sin patrones aprendidos")

            with tab3:
                knowledge = learning.get_knowledge()
                if knowledge:
                    for k in knowledge[-10:]:
                        st.markdown(f"**📖 {k['topic']}**")
                        st.write(k['content'][:100])
                        st.caption(f"Fuente: {k.get('source', 'N/A')} — {k['updated'][:16]}")
                        st.divider()
                else:
                    st.info("Sin conocimiento guardado")

        if st.button("🗑️ Borrar todo el aprendizaje", type="secondary", use_container_width=True):
            for f in [CORRECTIONS_FILE, FEEDBACK_FILE, PATTERNS_FILE, KNOWLEDGE_FILE]:
                if os.path.exists(f):
                    os.remove(f)
            st.success("Aprendizaje borrado")
            st.rerun()

        # === TESTS ===
        st.header("🧪 Tests")
        if st.button("Test: git clone", use_container_width=True):
            resultado = clonar_repositorio("https://github.com/yecos/signalTrade")
            st.code(resultado)

        if st.button("Test: analizar signalTrade", use_container_width=True):
            repo_path = os.path.join(REPOS_DIR, "signalTrade")
            if os.path.exists(repo_path):
                resultado = analizar_proyecto(repo_path)
                st.code(resultado)

        # === DEBUG LOG ===
        st.header("🐛 Debug Log")
        if st.session_state.debug_log:
            log_text = "\n".join(st.session_state.debug_log[-30:])
            st.markdown(f'<div class="debug-box">{log_text}</div>', unsafe_allow_html=True)

        # === REPOS ===
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

    # === FEEDBACK (si hay pendiente) ===
    if st.session_state.feedback_pending:
        with st.container():
            st.markdown("---")
            cols = st.columns([1, 1, 3])
            with cols[0]:
                if st.button("👍 Bueno", key="fb_pos"):
                    learning.save_feedback(
                        st.session_state.feedback_pending["user_message"],
                        st.session_state.feedback_pending["response"],
                        st.session_state.feedback_pending["action"],
                        "positive"
                    )
                    st.session_state.feedback_pending = None
                    st.rerun()
            with cols[1]:
                if st.button("👎 Malo", key="fb_neg"):
                    learning.save_feedback(
                        st.session_state.feedback_pending["user_message"],
                        st.session_state.feedback_pending["response"],
                        st.session_state.feedback_pending["action"],
                        "negative"
                    )
                    st.session_state.feedback_pending = None
                    st.rerun()
            with cols[2]:
                st.caption("Como estuvo la respuesta? Tu feedback ayuda al agente a mejorar.")

    # === INPUT ===
    if prompt := st.chat_input("Escribe tu mensaje..."):
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("Procesando..."):
                try:
                    respuesta, pasos_debug = procesar_mensaje(prompt)

                    if pasos_debug:
                        debug_text = "\n".join(pasos_debug)
                        st.session_state.debug_log.extend(pasos_debug)
                        with st.expander("🔍 Debug", expanded=False):
                            st.markdown(f'<div class="debug-box">{debug_text}</div>', unsafe_allow_html=True)

                    st.markdown(respuesta)

                    # Preparar feedback pendiente
                    last_action = st.session_state.get("last_action", "")
                    if last_action:
                        st.session_state.feedback_pending = {
                            "user_message": prompt,
                            "response": respuesta[:200],
                            "action": last_action
                        }

                except Exception as e:
                    respuesta = f"**ERROR:** {e}\n\nRevisa la consola de Streamlit para mas detalles."
                    st.error(respuesta)
                    st.session_state.debug_log.append(f"ERROR GLOBAL: {e}")

        st.session_state.messages.append({"role": "assistant", "content": respuesta})


if __name__ == "__main__":
    main()
