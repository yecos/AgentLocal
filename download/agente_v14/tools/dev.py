"""
tools/dev.py - Herramientas de desarrollo: generar_codigo, analizar_proyecto (PROFUNDO), clonar, instalar
"""
import os
import re
import json
import logging
import platform
import subprocess
from . import tool
from ..config import REPOS_DIR
from ..security import validate_path, is_dangerous_command

logger = logging.getLogger("agente.tools.dev")


@tool(
    name="analizar_proyecto",
    description="Analisis PROFUNDO de un proyecto: lee archivos, detecta frameworks, dependencias, arquitectura y genera reporte completo.",
    params={"ruta": {"type": "string", "description": "Ruta del proyecto"}},
    required=["ruta"]
)
def analizar_proyecto(ruta: str) -> str:
    """Analisis PROFUNDO de un proyecto. Lee archivos, detecta
    frameworks, dependencias, arquitectura y genera reporte completo."""
    
    # Resolver ruta
    if not os.path.exists(ruta):
        alt = os.path.join(REPOS_DIR, ruta) if not os.path.isabs(ruta) else ruta
        if os.path.exists(alt):
            ruta = alt
        else:
            return f"Directorio no existe: {ruta}"
    
    resultado = []
    resultado.append(f"ANALISIS PROFUNDO: {ruta}")
    resultado.append("=" * 50)
    
    # ── FASE 1: Estructura de directorios ──
    dir_info = _scan_directory(ruta, max_depth=4)
    resultado.append(f"\nESTRUCTURA ({dir_info['dirs']} dirs, {dir_info['files']} archivos):")
    resultado.append(dir_info['tree'][:2000])
    
    # ── FASE 2: Lectura e interpretacion de archivos clave ──
    tech_stack = []
    frameworks = []
    deps = {}
    arch_patterns = []
    
    # 2a. package.json -> Node.js ecosystem
    pkg_path = _find_file(ruta, "package.json")
    if pkg_path:
        try:
            with open(pkg_path, "r", encoding="utf-8", errors="replace") as f:
                pkg = json.load(f)
            tech_stack.append("Node.js")
            deps["dependencies"] = list(pkg.get("dependencies", {}).keys())
            deps["devDependencies"] = list(pkg.get("devDependencies", {}).keys())
            
            all_deps = list(pkg.get("dependencies", {}).keys()) + list(pkg.get("devDependencies", {}).keys())
            fw_map = {
                "next": "Next.js", "react": "React", "vue": "Vue",
                "svelte": "Svelte", "express": "Express", "fastify": "Fastify",
                "astro": "Astro", "nuxt": "Nuxt", "angular": "Angular",
            }
            for dep, name in fw_map.items():
                if dep in all_deps:
                    frameworks.append(name)
            
            # Detectar monorepo
            workspaces = pkg.get("workspaces", [])
            if workspaces or os.path.exists(os.path.join(ruta, "pnpm-workspace.yaml")):
                arch_patterns.append("Monorepo")
                if os.path.exists(os.path.join(ruta, "pnpm-workspace.yaml")):
                    arch_patterns.append("pnpm workspace")
            
            if "tslib" in all_deps or "typescript" in all_deps:
                tech_stack.append("TypeScript")
            if pkg.get("type") == "module":
                tech_stack.append("ESM")
            
            scripts = pkg.get("scripts", {})
            if scripts:
                resultado.append(f"\nSCRIPTS: {', '.join(scripts.keys())}")
        except (json.JSONDecodeError, OSError) as e:
            resultado.append(f"  [WARN] Error leyendo package.json: {e}")
    
    # 2b. pnpm-workspace.yaml
    pnpm_ws = _find_file(ruta, "pnpm-workspace.yaml")
    if pnpm_ws:
        content = _safe_read(pnpm_ws, max_chars=2000)
        if content:
            arch_patterns.append("pnpm monorepo")
            resultado.append(f"\nWORKSPACE pnpm:\n{content[:500]}")
    
    # 2c. requirements.txt / pyproject.toml -> Python ecosystem
    req_path = _find_file(ruta, "requirements.txt")
    if req_path:
        content = _safe_read(req_path, max_chars=3000)
        if content:
            tech_stack.append("Python")
            pip_deps = [l.strip().split("==")[0].split(">=")[0] 
                       for l in content.split("\n") if l.strip() and not l.startswith("#")]
            deps["pip"] = pip_deps
            fw_py = {"django": "Django", "flask": "Flask", "fastapi": "FastAPI",
                     "streamlit": "Streamlit", "pydantic": "Pydantic"}
            for dep, name in fw_py.items():
                if any(dep in d.lower() for d in pip_deps):
                    frameworks.append(name)
    
    pyproject = _find_file(ruta, "pyproject.toml")
    if pyproject:
        tech_stack.append("Python (pyproject)")
        content = _safe_read(pyproject, max_chars=2000)
        if content and "[tool.poetry]" in content:
            arch_patterns.append("Poetry")
    
    # 2d. README.md -> Descripcion del proyecto
    readme = _find_file(ruta, "README.md")
    if readme:
        content = _safe_read(readme, max_chars=4000)
        if content:
            lines = content.split("\n")
            title = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), "")
            if title:
                resultado.append(f"\nPROYECTO: {title}")
            desc_lines = [l.strip() for l in lines[1:10] 
                         if l.strip() and not l.startswith("#") 
                         and not l.startswith("![") and not l.startswith("[!")
                         and len(l.strip()) > 20]
            if desc_lines:
                resultado.append(f"DESCRIPCION: {desc_lines[0][:300]}")
    
    # 2e. Docker / CI/CD
    if _find_file(ruta, "Dockerfile"):
        tech_stack.append("Docker")
    if _find_file(ruta, "docker-compose.yml"):
        arch_patterns.append("Docker Compose")
    if os.path.isdir(os.path.join(ruta, ".github", "workflows")):
        arch_patterns.append("GitHub Actions CI/CD")
    
    # 2f. MCP / Skills / Plugins (patrones avanzados)
    skills_dir = os.path.join(ruta, "skills")
    if os.path.isdir(skills_dir):
        n_skills = len(os.listdir(skills_dir))
        arch_patterns.append(f"Skills system ({n_skills}+ skills)")
    plugins_dir = os.path.join(ruta, "plugins")
    if os.path.isdir(plugins_dir):
        n_plugins = len(os.listdir(plugins_dir))
        arch_patterns.append(f"Plugins ({n_plugins}+ plugins)")
    packages_dir = os.path.join(ruta, "packages")
    if os.path.isdir(packages_dir):
        n_pkgs = len([d for d in os.listdir(packages_dir) 
                     if os.path.isdir(os.path.join(packages_dir, d))])
        arch_patterns.append(f"Multi-paquetes ({n_pkgs} packages)")
    
    # ── FASE 3: Sintesis del reporte ──
    if tech_stack:
        resultado.append(f"\nTECNOLOGIAS: {', '.join(set(tech_stack))}")
    if frameworks:
        resultado.append(f"FRAMEWORKS: {', '.join(set(frameworks))}")
    if arch_patterns:
        resultado.append(f"ARQUITECTURA: {', '.join(arch_patterns)}")
    
    for dep_type, dep_list in deps.items():
        if dep_list:
            shown = dep_list[:15]
            extra = f" +{len(dep_list)-15} mas" if len(dep_list) > 15 else ""
            resultado.append(f"\n{dep_type.upper()}: {', '.join(shown)}{extra}")
    
    top_dirs = [d for d in os.listdir(ruta) 
               if os.path.isdir(os.path.join(ruta, d)) and not d.startswith(".")]
    if top_dirs:
        resultado.append(f"\nDIRECTORIOS PRINCIPALES: {', '.join(sorted(top_dirs)[:15])}")
    
    return "\n".join(resultado)


# ── Funciones auxiliares ──

def _find_file(root: str, filename: str) -> str:
    """Busca un archivo en el directorio raiz (no recursivo)."""
    path = os.path.join(root, filename)
    return path if os.path.exists(path) else ""


def _safe_read(path: str, max_chars: int = 4000) -> str:
    """Lee un archivo de forma segura con truncado."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)
        return content
    except OSError as e:
        logger.warning(f"Error leyendo {path}: {e}")
        return ""


def _scan_directory(ruta: str, max_depth: int = 4) -> dict:
    """Escanea estructura de directorios con profundidad limitada."""
    dirs_count = 0
    files_count = 0
    tree_lines = []
    
    for root, dirs, files in os.walk(ruta):
        level = root.replace(ruta, "").count(os.sep)
        if level >= max_depth:
            dirs.clear()
            continue
        indent = "  " * level
        dirname = os.path.basename(root) or root
        tree_lines.append(f"{indent}{dirname}/")
        dirs_count += 1
        subindent = "  " * (level + 1)
        for f in sorted(files)[:20]:
            tree_lines.append(f"{subindent}{f}")
            files_count += 1
        if len(files) > 20:
            tree_lines.append(f"{subindent}... +{len(files)-20} mas")
    
    return {
        "tree": "\n".join(tree_lines[:100]),
        "dirs": dirs_count,
        "files": files_count
    }


@tool(
    name="generar_codigo",
    description="Genera codigo/texto COMPLETO usando el LLM y lo guarda en un archivo.",
    params={
        "descripcion": {"type": "string", "description": "Que crear (detallado)"},
        "tipo": {"type": "string", "enum": ["html", "python", "javascript", "css", "json", "markdown", "texto"], "description": "Tipo de archivo"},
        "ruta": {"type": "string", "description": "Ruta donde guardar (opcional)"}
    },
    required=["descripcion", "tipo"]
)
def generar_codigo(descripcion: str, tipo: str, ruta: str = "") -> str:
    """Genera codigo/texto completo usando el LLM y lo guarda en un archivo."""
    # Esta funcion necesita acceso al LLM, se inyecta desde el agente
    # Por ahora usa un placeholder que sera reemplazado en la integracion
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
    
    # NOTA: La generacion real requiere _llm_generate que esta en ollama_client
    # Este es el esqueleto; la integracion completa se hace en main.py
    return f"Placeholder: generar_codigo({tipo}, {descripcion}) -> {ruta}"


@tool(
    name="clonar_repositorio",
    description="Clona un repositorio de GitHub.",
    params={"url": {"type": "string", "description": "URL del repositorio"}},
    required=["url"]
)
def clonar_repositorio(url: str) -> str:
    """Clona un repositorio de GitHub."""
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
            except OSError as e:
                return f"Carpeta vacia, no se pudo borrar: {e}"
    
    resultado = ejecutar_comando(f'git clone {url} "{target_dir}"')
    if os.path.exists(target_dir) and len(os.listdir(target_dir)) > 1:
        return f"CLONADO OK en: {target_dir}"
    return f"ERROR al clonar:\n{resultado}"


@tool(
    name="instalar_dependencias",
    description="Instala dependencias de un proyecto. Detecta automaticamente npm/pip/poetry.",
    params={
        "ruta": {"type": "string", "description": "Ruta del proyecto"},
        "gestor": {"type": "string", "description": "Gestor de paquetes (auto/npm/pip/poetry)"}
    },
    required=["ruta"]
)
def instalar_dependencias(ruta: str, gestor: str = "auto") -> str:
    """Instala dependencias de un proyecto."""
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
    from .system import ejecutar_comando
    return ejecutar_comando(comandos.get(gestor, f'cd "{ruta}" && {gestor} install'))


# Import diferido para evitar circular
from .system import ejecutar_comando
