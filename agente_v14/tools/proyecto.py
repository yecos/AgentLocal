"""
=============================================================
AGENTE v14 - Herramientas de Proyectos (MEJORADO v14)
=============================================================
analizar_proyecto: Lee archivos clave, detecta frameworks, monorepos
clonar_repositorio, instalar_dependencias
=============================================================
"""

import os
import json
import re
import shutil

from config import REPOS_DIR, logger
from utils.helpers import safe_read_file
from utils.security import sanitize_input
from tools.sistema import ejecutar_comando

# Extensiones reconocidas por lenguaje
LANG_EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".jsx": "React JSX", ".tsx": "React TSX", ".vue": "Vue",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".json": "JSON", ".md": "Markdown", ".yaml": "YAML",
    ".yml": "YAML", ".toml": "TOML", ".rs": "Rust",
    ".go": "Go", ".java": "Java", ".rb": "Ruby",
    ".c": "C", ".cpp": "C++", ".h": "C/C++ Header",
    ".sh": "Shell", ".bat": "Batch", ".ps1": "PowerShell",
    ".sql": "SQL", ".graphql": "GraphQL",
}

# Directorios a ignorar al escanear
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".next", "dist", "build", ".venv", "venv", ".cache", ".tox"}


def _analyze_package_json(ruta):
    """Lee y analiza package.json del proyecto."""
    pj_path = os.path.join(ruta, "package.json")
    content = safe_read_file(pj_path, 3000)
    if not content:
        return ""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return "  package.json existe pero no es JSON valido\n"

    result = ""
    result += f"  Nombre: {data.get('name', 'desconocido')}\n"
    result += f"  Version: {data.get('version', '?')}\n"
    if data.get("description"):
        result += f"  Descripcion: {data['description'][:200]}\n"
    if data.get("scripts"):
        scripts = ", ".join(list(data["scripts"].keys())[:8])
        result += f"  Scripts: {scripts}\n"
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    if deps:
        frameworks = []
        fw_map = {
            "next": "Next.js", "react": "React", "vue": "Vue",
            "express": "Express", "fastify": "Fastify",
            "typescript": "TypeScript", "tailwindcss": "Tailwind",
            "eslint": "ESLint", "jest": "Jest", "vitest": "Vitest",
            "vite": "Vite", "nuxt": "Nuxt", "svelte": "Svelte",
            "@anthropic-ai/sdk": "Anthropic SDK", "openai": "OpenAI SDK",
        }
        for dep, fw_name in fw_map.items():
            if dep in deps:
                frameworks.append(f"{fw_name}({deps[dep]})")
        if frameworks:
            result += f"  Frameworks: {', '.join(frameworks)}\n"
        result += f"  Dependencias: {len(data.get('dependencies', {}))} prod, {len(data.get('devDependencies', {}))} dev\n"
    if data.get("workspaces"):
        result += f"  MONOREPO con workspaces: {data['workspaces']}\n"
    return result


def _analyze_readme(ruta):
    """Lee los primeros 500 chars del README como descripcion."""
    for name in ["README.md", "readme.md", "README.MD"]:
        readme_path = os.path.join(ruta, name)
        content = safe_read_file(readme_path, 1500)
        if content:
            clean = re.sub(r'[#*`>\-]', '', content[:500])
            clean = re.sub(r'\n{2,}', '\n', clean).strip()
            return f"  Descripcion del proyecto: {clean[:400]}\n"
    return ""


def _detect_monorepo(ruta):
    """Detecta si es un monorepo."""
    indicators = ["pnpm-workspace.yaml", "lerna.json", "turbo.json", ".nx"]
    found = []
    for ind in indicators:
        if os.path.exists(os.path.join(ruta, ind)):
            found.append(ind)
    # Verificar workspaces en package.json
    pj_path = os.path.join(ruta, "package.json")
    content = safe_read_file(pj_path, 3000)
    if content:
        try:
            if json.loads(content).get("workspaces"):
                found.append("package.json workspaces")
        except Exception:
            pass
    if found:
        return f"  MONOREPO detectado: {', '.join(found)}\n"
    return ""


def _count_languages(ruta, max_depth=3):
    """Cuenta archivos por lenguaje."""
    counts = {}
    for root, dirs, files in os.walk(ruta):
        depth = root.replace(ruta, "").count(os.sep)
        if depth > max_depth:
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            lang = LANG_EXTENSIONS.get(ext, "Otro")
            counts[lang] = counts.get(lang, 0) + 1
    return counts


def analizar_proyecto(ruta: str) -> str:
    """Analisis profundo de un proyecto. Lee archivos clave y detecta tecnologias."""
    # Resolver ruta
    if not os.path.exists(ruta):
        alt = os.path.join(REPOS_DIR, ruta) if not os.path.isabs(ruta) else ruta
        if os.path.exists(alt):
            ruta = alt
        else:
            return f"Directorio no existe: {ruta}"

    result = f"=== ANALISIS DE PROYECTO ===\n"
    result += f"Ruta: {ruta}\n\n"

    # 1. Estructura con estadisticas
    file_count = 0
    for root, dirs, files in os.walk(ruta):
        depth = root.replace(ruta, "").count(os.sep)
        if depth > 3:
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        indent = "  " * depth
        result += f"{indent}{os.path.basename(root)}/\n"
        subindent = "  " * (depth + 1)
        for f in sorted(files)[:15]:
            result += f"{subindent}{f}\n"
            file_count += 1
        if len(files) > 15:
            result += f"{subindent}... y {len(files)-15} mas\n"
    result += f"\nTotal archivos visibles: ~{file_count}\n\n"

    # 2. Lenguajes
    lang_counts = _count_languages(ruta)
    if lang_counts:
        sorted_langs = sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)
        lang_str = ", ".join(f"{lang}({cnt})" for lang, cnt in sorted_langs[:8])
        result += f"LENGUAJES: {lang_str}\n\n"

    # 3. Analisis de archivos clave
    result += "DETALLES DEL PROYECTO:\n"
    result += _analyze_package_json(ruta)
    result += _analyze_readme(ruta)
    result += _detect_monorepo(ruta)

    # 4. Deteccion por patrones
    result += "\nTECNOLOGIAS DETECTADAS:\n"
    tech_patterns = {
        "Dockerfile": "Docker", "docker-compose.yml": "Docker Compose",
        "docker-compose.yaml": "Docker Compose",
        ".github/workflows": "GitHub Actions CI/CD",
        ".gitlab-ci.yml": "GitLab CI", "Jenkinsfile": "Jenkins CI",
        "requirements.txt": "Python (pip)", "pyproject.toml": "Python (modern)",
        "Pipfile": "Python (pipenv)", "poetry.lock": "Python (poetry)",
        "Cargo.toml": "Rust", "go.mod": "Go", "Gemfile": "Ruby",
        ".eslintrc.js": "ESLint", ".eslintrc.json": "ESLint",
        "jest.config.js": "Jest", "vitest.config.ts": "Vitest",
        "pytest.ini": "pytest", "conftest.py": "pytest",
        "tsconfig.json": "TypeScript",
        "next.config.js": "Next.js", "next.config.ts": "Next.js",
        "nuxt.config.ts": "Nuxt", "vite.config.ts": "Vite",
        ".env": "Variables de entorno", ".env.example": "Env template",
        "mcp.json": "MCP Server", "mcp-config.json": "MCP Config",
        ".git": "Git",
    }
    for pattern, tech in tech_patterns.items():
        if os.path.exists(os.path.join(ruta, pattern)):
            result += f"  - {tech}\n"

    # 5. Subproyectos (si es monorepo)
    packages_dir = os.path.join(ruta, "packages")
    apps_dir = os.path.join(ruta, "apps")
    sub_dirs = []
    for d in [packages_dir, apps_dir]:
        if os.path.exists(d):
            for sub in os.listdir(d)[:5]:
                sub_path = os.path.join(d, sub)
                if os.path.isdir(sub_path):
                    sub_dirs.append(sub)
    if sub_dirs:
        result += f"\nSUBPROYECTOS: {', '.join(sub_dirs)}\n"

    return result


def clonar_repositorio(url: str) -> str:
    """Clona un repositorio de GitHub."""
    # Validar que la URL sea un repo Git legitimo
    url = url.strip()
    if not re.match(r'^https?://github\.com/[\w\-\.]+/[\w\-\.]+(?:\.git)?$', url):
        if not re.match(r'^git@github\.com:[\w\-\.]+/[\w\-\.]+(?:\.git)?$', url):
            # Sanitizar si no es URL git estandar
            url = sanitize_input(url)

    repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
    target_dir = os.path.join(REPOS_DIR, repo_name)

    if os.path.exists(target_dir):
        git_dir = os.path.join(target_dir, ".git")
        contenido = os.listdir(target_dir) if os.path.isdir(target_dir) else []
        archivos_reales = [f for f in contenido if f != ".git"]
        if os.path.exists(git_dir) and len(archivos_reales) > 1:
            return f"Ya existe en: {target_dir}"
        else:
            try:
                shutil.rmtree(target_dir)
            except Exception as e:
                return f"Carpeta vacia, no se pudo borrar: {e}"

    resultado = ejecutar_comando(f'git clone {url} "{target_dir}"')
    if os.path.exists(target_dir) and len(os.listdir(target_dir)) > 1:
        return f"CLONADO OK en: {target_dir}"
    return f"ERROR al clonar:\n{resultado}"


def instalar_dependencias(ruta: str, gestor: str = "auto") -> str:
    """Instala dependencias de un proyecto. Detecta automaticamente npm/pip/poetry."""
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
