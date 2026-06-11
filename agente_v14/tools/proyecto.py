"""
=============================================================
AGENTE v14 - Herramientas de Proyectos (MEJORADO v14.2)
=============================================================
analizar_proyecto: Analisis profundo en 3 fases
  Fase 1 - Estructura: arbol, lenguajes, estadisticas
  Fase 2 - Lectura profunda: configs, README, Docker, CI/CD
  Fase 3 - Sintesis: arquitectura, tipo, stack, riesgos
clonar_repositorio, instalar_dependencias
=============================================================
"""

import os
import json
import re
import shutil
import glob as glob_mod

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


# ============================================================
# FASE 2: LECTURA PROFUNDA - Helpers
# ============================================================

def _deep_read_configs(ruta):
    """Lee y parsea todos los archivos de configuracion del proyecto.
    
    Returns:
        dict con claves: package_json, pyproject_toml, requirements_txt,
                         cargo_toml, go_mod, dockerfile, cicd, env_vars,
                         readme_full, entry_points
    """
    config_data = {
        "package_json": None,
        "pyproject_toml": None,
        "requirements_txt": None,
        "cargo_toml": None,
        "go_mod": None,
        "dockerfile": None,
        "cicd": [],
        "env_vars": [],
        "readme_full": None,
        "entry_points": [],
    }

    # --- package.json ---
    pj_path = os.path.join(ruta, "package.json")
    content = safe_read_file(pj_path, 5000)
    if content:
        try:
            data = json.loads(content)
            config_data["package_json"] = data
            # Entry points
            if data.get("main"):
                config_data["entry_points"].append(f"main: {data['main']}")
            if data.get("bin"):
                if isinstance(data["bin"], str):
                    config_data["entry_points"].append(f"bin: {data['bin']}")
                elif isinstance(data["bin"], dict):
                    for name, path in data["bin"].items():
                        config_data["entry_points"].append(f"bin({name}): {path}")
            if data.get("exports"):
                config_data["entry_points"].append(f"exports: {json.dumps(data['exports'])[:100]}")
        except json.JSONDecodeError:
            pass

    # --- pyproject.toml ---
    pp_path = os.path.join(ruta, "pyproject.toml")
    pp_content = safe_read_file(pp_path, 5000)
    if pp_content:
        config_data["pyproject_toml"] = pp_content
        # Parse basic info from TOML (simple regex-based, no tomllib dependency)
        name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', pp_content)
        if name_match:
            config_data["entry_points"].append(f"pyproject.name: {name_match.group(1)}")
        # Detect entry points: scripts, console_scripts
        scripts_match = re.search(r'scripts\s*=\s*\{([^}]+)\}', pp_content)
        if scripts_match:
            config_data["entry_points"].append(f"pyproject.scripts: {scripts_match.group(1)[:100]}")

    # --- requirements.txt ---
    req_path = os.path.join(ruta, "requirements.txt")
    req_content = safe_read_file(req_path, 5000)
    if req_content:
        config_data["requirements_txt"] = req_content

    # --- Cargo.toml ---
    cargo_path = os.path.join(ruta, "Cargo.toml")
    cargo_content = safe_read_file(cargo_path, 3000)
    if cargo_content:
        config_data["cargo_toml"] = cargo_content
        name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', cargo_content)
        if name_match:
            config_data["entry_points"].append(f"cargo.name: {name_match.group(1)}")

    # --- go.mod ---
    gomod_path = os.path.join(ruta, "go.mod")
    gomod_content = safe_read_file(gomod_path, 3000)
    if gomod_content:
        config_data["go_mod"] = gomod_content
        module_match = re.search(r'module\s+(\S+)', gomod_content)
        if module_match:
            config_data["entry_points"].append(f"go.module: {module_match.group(1)}")

    # --- Dockerfile ---
    dockerfile_path = os.path.join(ruta, "Dockerfile")
    df_content = safe_read_file(dockerfile_path, 5000)
    if df_content:
        config_data["dockerfile"] = df_content

    # --- CI/CD configs ---
    # GitHub Actions
    gh_dir = os.path.join(ruta, ".github", "workflows")
    if os.path.isdir(gh_dir):
        for yml_file in sorted(os.listdir(gh_dir))[:5]:
            if yml_file.endswith((".yml", ".yaml")):
                yml_path = os.path.join(gh_dir, yml_file)
                yml_content = safe_read_file(yml_path, 3000)
                if yml_content:
                    config_data["cicd"].append({
                        "type": "GitHub Actions",
                        "file": yml_file,
                        "content": yml_content,
                    })
    # GitLab CI
    gitlab_path = os.path.join(ruta, ".gitlab-ci.yml")
    gitlab_content = safe_read_file(gitlab_path, 3000)
    if gitlab_content:
        config_data["cicd"].append({
            "type": "GitLab CI",
            "file": ".gitlab-ci.yml",
            "content": gitlab_content,
        })
    # Jenkins
    jenkins_path = os.path.join(ruta, "Jenkinsfile")
    jenkins_content = safe_read_file(jenkins_path, 3000)
    if jenkins_content:
        config_data["cicd"].append({
            "type": "Jenkins",
            "file": "Jenkinsfile",
            "content": jenkins_content,
        })

    # --- .env.example ---
    env_example_path = os.path.join(ruta, ".env.example")
    env_content = safe_read_file(env_example_path, 5000)
    if env_content:
        for line in env_content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                var_name = line.split("=")[0].strip()
                config_data["env_vars"].append(var_name)

    # --- README completo ---
    for name in ["README.md", "readme.md", "README.MD", "README.rst", "README"]:
        readme_path = os.path.join(ruta, name)
        readme_content = safe_read_file(readme_path, 10000)
        if readme_content:
            config_data["readme_full"] = readme_content
            break

    return config_data


def _detect_architecture(ruta, lang_counts, config_data):
    """Detecta el patron de arquitectura del proyecto.
    
    Returns:
        str: Descripcion del patron detectado (MVC, microservices, monolith, 
             serverless, monorepo, library, etc.)
    """
    patterns = []

    # Monorepo detection
    for indicator in ["packages/", "apps/", "libs/"]:
        if os.path.isdir(os.path.join(ruta, indicator.rstrip("/"))):
            patterns.append("Monorepo")
            break
    pj = config_data.get("package_json") or {}
    if pj.get("workspaces"):
        patterns.append("Monorepo")
    if os.path.exists(os.path.join(ruta, "lerna.json")) or os.path.exists(os.path.join(ruta, "turbo.json")):
        patterns.append("Monorepo")

    # Microservices indicators
    has_docker_compose = os.path.exists(os.path.join(ruta, "docker-compose.yml")) or \
                         os.path.exists(os.path.join(ruta, "docker-compose.yaml"))
    has_dockerfile = os.path.exists(os.path.join(ruta, "Dockerfile"))
    multiple_dockerfiles = []
    for root, dirs, files in os.walk(ruta):
        depth = root.replace(ruta, "").count(os.sep)
        if depth > 2:
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f == "Dockerfile":
                multiple_dockerfiles.append(root)
    if has_docker_compose and len(multiple_dockerfiles) > 1:
        patterns.append("Microservicios")
    elif has_docker_compose:
        patterns.append("Contenerizado")

    # MVC / Web framework patterns
    has_controllers = os.path.isdir(os.path.join(ruta, "controllers")) or \
                      os.path.isdir(os.path.join(ruta, "src", "controllers"))
    has_views = os.path.isdir(os.path.join(ruta, "views")) or \
                os.path.isdir(os.path.join(ruta, "templates")) or \
                os.path.isdir(os.path.join(ruta, "src", "views"))
    has_models = os.path.isdir(os.path.join(ruta, "models")) or \
                 os.path.isdir(os.path.join(ruta, "src", "models"))
    if has_controllers and has_views and has_models:
        patterns.append("MVC")
    elif has_controllers and has_models:
        patterns.append("API/Backend")

    # Next.js app router pattern
    has_app_dir = os.path.isdir(os.path.join(ruta, "app")) or \
                  os.path.isdir(os.path.join(ruta, "src", "app"))
    has_pages_dir = os.path.isdir(os.path.join(ruta, "pages")) or \
                    os.path.isdir(os.path.join(ruta, "src", "pages"))
    pj = config_data.get("package_json") or {}
    deps = {**pj.get("dependencies", {}), **pj.get("devDependencies", {})}
    if "next" in deps:
        if has_app_dir:
            patterns.append("Next.js App Router")
        elif has_pages_dir:
            patterns.append("Next.js Pages Router")

    # Serverless indicators
    has_serverless = os.path.exists(os.path.join(ruta, "serverless.yml")) or \
                     os.path.exists(os.path.join(ruta, "serverless.yaml"))
    has_vercel = os.path.exists(os.path.join(ruta, "vercel.json"))
    has_netlify = os.path.exists(os.path.join(ruta, "netlify.toml"))
    if has_serverless or has_vercel or has_netlify:
        patterns.append("Serverless")

    # Monolith fallback
    if not patterns:
        has_src = os.path.isdir(os.path.join(ruta, "src"))
        has_lib = os.path.isdir(os.path.join(ruta, "lib"))
        py_count = lang_counts.get("Python", 0)
        js_count = lang_counts.get("JavaScript", 0) + lang_counts.get("TypeScript", 0)
        if has_dockerfile or (py_count + js_count > 10):
            patterns.append("Monolito")
        elif has_src or has_lib:
            patterns.append("Libreria/Modulo")

    return " + ".join(patterns) if patterns else "No determinado"


def _classify_project(config_data, lang_counts):
    """Clasifica el tipo de proyecto.
    
    Returns:
        str: Tipo de proyecto (web app, CLI tool, library, API, etc.)
    """
    pj = config_data.get("package_json") or {}
    deps = {**pj.get("dependencies", {}), **pj.get("devDependencies", {})}
    scripts = pj.get("scripts", {})

    py_count = lang_counts.get("Python", 0)
    js_count = lang_counts.get("JavaScript", 0) + lang_counts.get("TypeScript", 0)
    rs_count = lang_counts.get("Rust", 0)
    go_count = lang_counts.get("Go", 0)

    # Check for web app indicators
    web_frameworks = ["next", "react", "vue", "nuxt", "svelte", "angular",
                      "@angular/core", "vite", "gatsby", "remix"]
    if any(fw in deps for fw in web_frameworks):
        if "next" in deps:
            return "Web App (Next.js)"
        if "nuxt" in deps:
            return "Web App (Nuxt)"
        if "vue" in deps:
            return "Web App (Vue)"
        if "svelte" in deps:
            return "Web App (Svelte)"
        return "Web App (Frontend)"

    # Check for API/Backend indicators
    api_frameworks = ["express", "fastify", "koa", "hapi", "flask", "django",
                      "fastapi", "tornado", "starlette", "sanic"]
    if any(fw in deps for fw in api_frameworks):
        return "API/Backend"

    # Check for CLI tool indicators
    has_bin = pj.get("bin") is not None
    has_cli_deps = "commander" in deps or "yargs" in deps or "click" in deps or \
                   "typer" in deps or "argparse" in deps or "inquirer" in deps
    has_cli_script = "cli" in scripts or "start" in scripts
    if has_bin or has_cli_deps:
        return "CLI Tool"

    # Check for library indicators
    has_main = pj.get("main") is not None
    has_exports = pj.get("exports") is not None
    has_typings = pj.get("types") is not None or pj.get("typings") is not None
    has_pyproject = config_data.get("pyproject_toml") is not None
    has_setup_py = os.path.exists(os.path.join(
        os.path.dirname(config_data.get("pyproject_toml", "")), "setup.py"
    )) if config_data.get("pyproject_toml") else False

    if has_exports or has_typings:
        return "Libreria (NPM)"
    if has_pyproject and py_count > js_count:
        return "Libreria/Modulo (Python)"

    # Check for desktop/mobile
    if "electron" in deps:
        return "App Desktop (Electron)"
    if "react-native" in deps or "expo" in deps:
        return "App Mobile (React Native)"

    # Check for Rust/Go binary
    if config_data.get("cargo_toml"):
        return "Binario/Tool (Rust)"
    if config_data.get("go_mod"):
        return "Binario/Tool (Go)"

    # Fallback by language dominance
    if py_count > js_count and py_count > 5:
        return "Proyecto Python"
    if js_count > py_count and js_count > 5:
        return "Proyecto JavaScript/TypeScript"
    if rs_count > 3:
        return "Proyecto Rust"
    if go_count > 3:
        return "Proyecto Go"

    return "Proyecto generico"


def _assess_dependencies(config_data):
    """Analiza las dependencias del proyecto y evalua riesgos.
    
    Returns:
        dict con: total_deps, prod_deps, dev_deps, outdated_patterns, 
                  risk_notes, stack_versions
    """
    result = {
        "total_deps": 0,
        "prod_deps": 0,
        "dev_deps": 0,
        "outdated_patterns": [],
        "risk_notes": [],
        "stack_versions": {},
    }

    pj = config_data.get("package_json")
    if pj:
        prod = pj.get("dependencies", {})
        dev = pj.get("devDependencies", {})
        result["prod_deps"] = len(prod)
        result["dev_deps"] = len(dev)
        result["total_deps"] = len(prod) + len(dev)

        # Extract versions
        for name, version in {**prod, **dev}.items():
            # Clean version string
            ver = re.sub(r'[\^~>=<]', '', version)
            result["stack_versions"][name] = ver

        # Check for potentially outdated/vulnerable patterns
        risk_deps = {
            "node-uuid": "Usa 'uuid' en vez de 'node-uuid' (deprecado)",
            "request": "'request' esta deprecado, usa 'node-fetch' o 'axios'",
            "express@3": "Express v3 es muy antiguo, actualizar a v4+",
            "lodash": "Considera usar funciones nativas de ES6+ en vez de lodash",
            "moment": "Moment.js esta en mantenimiento, considera 'date-fns' o 'dayjs'",
            "jquery": "jQuery puede no ser necesario en apps modernas",
            "babel-core": "Usa @babel/core en vez de babel-core (Babel 7+)",
            "@types/react": "Verifica que la version de @types/react coincida con react",
        }
        for dep, note in risk_deps.items():
            dep_name = dep.split("@")[0] if "@" in dep and not dep.startswith("@") else dep
            if dep_name in prod or dep_name in dev:
                result["outdated_patterns"].append(f"{dep_name}: {note}")

        # General risk notes
        if len(prod) > 50:
            result["risk_notes"].append("Muchas dependencias de produccion (>50). Considera reducir.")
        if len(prod) > 0 and len(dev) == 0:
            result["risk_notes"].append("Sin devDependencies. Las herramientas de desarrollo deberian estar en devDeps.")

    # Python dependency analysis
    req = config_data.get("requirements_txt")
    if req:
        req_lines = [l.strip() for l in req.splitlines() if l.strip() and not l.startswith("#")]
        result["prod_deps"] = len(req_lines)
        result["total_deps"] = len(req_lines)

        # Check for unpinned deps
        unpinned = [l for l in req_lines if "==" not in l and ">=" not in l and "<=" not in l and "~=" not in l]
        if unpinned:
            result["risk_notes"].append(f"{len(unpinned)} dependencias sin version fija en requirements.txt")
            result["outdated_patterns"].append(f"Unpinned: {', '.join(unpinned[:5])}")

        # Check for risky patterns
        py_risk_deps = {
            "pickle": "pickle es inseguro para datos no confiables",
            "subprocess.call": "subprocess.call sin shell=False es riesgoso",
            "flask<1": "Flask <1.0 es muy antiguo",
            "django<2": "Django <2.0 tiene vulnerabilidades conocidas",
        }
        for pattern, note in py_risk_deps.items():
            if any(pattern in l.lower() for l in req_lines):
                result["outdated_patterns"].append(note)

    # Go dependency analysis
    gomod = config_data.get("go_mod")
    if gomod:
        # Count indirect dependencies
        indirect_count = gomod.count("// indirect")
        direct_lines = [l for l in gomod.splitlines() if l.strip().startswith("require") or 
                       (l.strip() and not l.strip().startswith("//") and not l.strip().startswith("module") and 
                        not l.strip().startswith("go ") and l.strip() not in ("require (", ")"))]
        result["total_deps"] = len(direct_lines)
        result["prod_deps"] = len(direct_lines) - indirect_count

    # Rust dependency analysis  
    cargo = config_data.get("cargo_toml")
    if cargo:
        dep_count = cargo.count('version =')
        result["total_deps"] = dep_count
        result["prod_deps"] = dep_count

    if not result["risk_notes"]:
        result["risk_notes"].append("No se detectaron riesgos obvios en las dependencias.")

    return result


def analizar_proyecto(ruta: str) -> str:
    """Analisis profundo de un proyecto en 3 fases:
    Fase 1 - Estructura: arbol, lenguajes, estadisticas
    Fase 2 - Lectura profunda: configs, README, Docker, CI/CD
    Fase 3 - Sintesis: arquitectura, tipo, stack, riesgos
    """
    # Resolver ruta
    if not os.path.exists(ruta):
        alt = os.path.join(REPOS_DIR, ruta) if not os.path.isabs(ruta) else ruta
        if os.path.exists(alt):
            ruta = alt
        else:
            return f"Directorio no existe: {ruta}"

    result = f"=== ANALISIS DE PROYECTO (3 FASES) ===\n"
    result += f"Ruta: {ruta}\n\n"

    # ================================================================
    # FASE 1: ESTRUCTURA
    # ================================================================
    result += "--- FASE 1: ESTRUCTURA ---\n"

    # 1.1 Arbol de directorios con estadisticas
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

    # 1.2 Lenguajes
    lang_counts = _count_languages(ruta)
    if lang_counts:
        sorted_langs = sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)
        lang_str = ", ".join(f"{lang}({cnt})" for lang, cnt in sorted_langs[:8])
        result += f"LENGUAJES: {lang_str}\n\n"

    # 1.3 Analisis de archivos clave (keep existing)
    result += "DETALLES DEL PROYECTO:\n"
    result += _analyze_package_json(ruta)
    result += _analyze_readme(ruta)
    result += _detect_monorepo(ruta)

    # 1.4 Deteccion por patrones
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

    # 1.5 Subproyectos (si es monorepo)
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

    # ================================================================
    # FASE 2: LECTURA PROFUNDA
    # ================================================================
    result += "\n\n--- FASE 2: LECTURA PROFUNDA ---\n"

    config_data = _deep_read_configs(ruta)

    # 2.1 README completo
    readme = config_data.get("readme_full")
    if readme:
        # Extract key sections from README
        clean = re.sub(r'[#*`>\-]', '', readme[:2000])
        clean = re.sub(r'\n{2,}', '\n', clean).strip()
        result += f"README (completo):\n  {clean[:1500]}\n\n"
    else:
        result += "README: No encontrado\n\n"

    # 2.2 Config files
    pj = config_data.get("package_json")
    if pj:
        result += f"package.json:\n"
        result += f"  Nombre: {pj.get('name', '?')}\n"
        result += f"  Version: {pj.get('version', '?')}\n"
        if pj.get("description"):
            result += f"  Descripcion: {pj['description'][:300]}\n"
        if pj.get("scripts"):
            result += f"  Scripts:\n"
            for script_name, script_cmd in list(pj["scripts"].items())[:10]:
                result += f"    {script_name}: {script_cmd[:100]}\n"
        deps = pj.get("dependencies", {})
        dev_deps = pj.get("devDependencies", {})
        if deps:
            result += f"  Dependencias prod ({len(deps)}):\n"
            for name, ver in list(deps.items())[:15]:
                result += f"    {name}: {ver}\n"
            if len(deps) > 15:
                result += f"    ... y {len(deps)-15} mas\n"
        if dev_deps:
            result += f"  Dependencias dev ({len(dev_deps)}):\n"
            for name, ver in list(dev_deps.items())[:10]:
                result += f"    {name}: {ver}\n"
            if len(dev_deps) > 10:
                result += f"    ... y {len(dev_deps)-10} mas\n"
        result += "\n"

    pp = config_data.get("pyproject_toml")
    if pp:
        result += f"pyproject.toml:\n"
        # Extract key info
        for line in pp.splitlines()[:30]:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                result += f"  {stripped}\n"
        if len(pp.splitlines()) > 30:
            result += f"  ... ({len(pp.splitlines())-30} lineas mas)\n"
        result += "\n"

    req = config_data.get("requirements_txt")
    if req:
        result += f"requirements.txt:\n"
        req_lines = [l.strip() for l in req.splitlines() if l.strip() and not l.startswith("#")]
        for line in req_lines[:20]:
            result += f"  {line}\n"
        if len(req_lines) > 20:
            result += f"  ... y {len(req_lines)-20} mas\n"
        result += "\n"

    cargo = config_data.get("cargo_toml")
    if cargo:
        result += f"Cargo.toml:\n"
        for line in cargo.splitlines()[:20]:
            stripped = line.strip()
            if stripped:
                result += f"  {stripped}\n"
        result += "\n"

    gomod = config_data.get("go_mod")
    if gomod:
        result += f"go.mod:\n"
        for line in gomod.splitlines()[:20]:
            stripped = line.strip()
            if stripped:
                result += f"  {stripped}\n"
        result += "\n"

    # 2.3 Dockerfile
    dockerfile = config_data.get("dockerfile")
    if dockerfile:
        result += f"Dockerfile:\n"
        for line in dockerfile.splitlines()[:25]:
            result += f"  {line}\n"
        # Extract base image and exposed ports
        from_match = re.search(r'FROM\s+(\S+)', dockerfile)
        expose_match = re.findall(r'EXPOSE\s+(\d+)', dockerfile)
        if from_match:
            result += f"  [Imagen base: {from_match.group(1)}]\n"
        if expose_match:
            result += f"  [Puertos expuestos: {', '.join(expose_match)}]\n"
        result += "\n"

    # 2.4 CI/CD
    cicd_list = config_data.get("cicd", [])
    if cicd_list:
        result += f"CI/CD ({len(cicd_list)} config(s)):\n"
        for cicd in cicd_list:
            result += f"  {cicd['type']}: {cicd['file']}\n"
            # Extract key info (triggers, stages)
            content = cicd.get("content", "")
            # GitHub Actions: extract on.trigger
            if "GitHub Actions" in cicd["type"]:
                triggers = re.findall(r'(push|pull_request|workflow_dispatch|schedule):', content)
                if triggers:
                    result += f"    Triggers: {', '.join(set(triggers))}\n"
            # GitLab CI: extract stages
            stages_match = re.search(r'stages:\s*\n((\s+-\s+.+\n)+)', content)
            if stages_match:
                stages = re.findall(r'-\s+(\S+)', stages_match.group(0))
                if stages:
                    result += f"    Stages: {', '.join(stages[:10])}\n"
        result += "\n"

    # 2.5 Entry points
    entry_points = config_data.get("entry_points", [])
    if entry_points:
        result += f"ENTRY POINTS:\n"
        for ep in entry_points[:8]:
            result += f"  {ep}\n"
        result += "\n"

    # 2.6 Environment variables
    env_vars = config_data.get("env_vars", [])
    if env_vars:
        result += f"VARIABLES DE ENTORNO (.env.example):\n"
        for var in env_vars[:20]:
            result += f"  {var}\n"
        if len(env_vars) > 20:
            result += f"  ... y {len(env_vars)-20} mas\n"
        result += "\n"

    # ================================================================
    # FASE 3: SINTESIS
    # ================================================================
    result += "\n--- FASE 3: SINTESIS ---\n"

    # 3.1 Architecture pattern
    architecture = _detect_architecture(ruta, lang_counts, config_data)
    result += f"ARQUITECTURA: {architecture}\n"

    # 3.2 Project classification
    project_type = _classify_project(config_data, lang_counts)
    result += f"TIPO DE PROYECTO: {project_type}\n"

    # 3.3 Tech stack summary with versions
    dep_assessment = _assess_dependencies(config_data)
    result += f"STACK TECNOLOGICO:\n"
    result += f"  Dependencias: {dep_assessment['total_deps']} total ({dep_assessment['prod_deps']} prod, {dep_assessment['dev_deps']} dev)\n"

    # Show key stack versions
    stack_versions = dep_assessment.get("stack_versions", {})
    key_stack = {}
    # Highlight important deps
    important_deps = {"next", "react", "vue", "nuxt", "svelte", "express", "fastify",
                      "typescript", "tailwindcss", "vite", "webpack", "eslint",
                      "flask", "django", "fastapi", "python", "node",
                      "@prisma/client", "prisma", "drizzle-orm",
                      "trpc", "zod", "@tanstack/react-query"}
    for dep_name, version in stack_versions.items():
        dep_base = dep_name.split("/")[-1] if "/" in dep_name else dep_name
        if dep_base.lower() in important_deps or dep_name.lower() in important_deps:
            key_stack[dep_name] = version
    if key_stack:
        result += f"  Versiones clave:\n"
        for name, ver in key_stack.items():
            result += f"    {name}: {ver}\n"

    # Language versions from config files
    if config_data.get("pyproject_toml"):
        requires_python = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', config_data["pyproject_toml"])
        if requires_python:
            result += f"    Python: {requires_python.group(1)}\n"
    if config_data.get("package_json"):
        engines = config_data["package_json"].get("engines", {})
        if engines:
            for engine, ver in engines.items():
                result += f"    {engine}: {ver}\n"
    if config_data.get("go_mod"):
        go_version = re.search(r'^go\s+(\S+)', config_data["go_mod"], re.MULTILINE)
        if go_version:
            result += f"    Go: {go_version.group(1)}\n"
    result += "\n"

    # 3.4 Dependency risk assessment
    result += f"EVALUACION DE DEPENDENCIAS:\n"
    if dep_assessment["outdated_patterns"]:
        result += f"  Patrones potencialmente problematicos:\n"
        for pattern in dep_assessment["outdated_patterns"][:8]:
            result += f"    - {pattern}\n"
    else:
        result += f"  Sin patrones problematicos detectados.\n"
    if dep_assessment["risk_notes"]:
        result += f"  Notas de riesgo:\n"
        for note in dep_assessment["risk_notes"]:
            result += f"    - {note}\n"
    result += "\n"

    # 3.5 Key insights and recommendations
    result += f"INSIGHTS Y RECOMENDACIONES:\n"
    insights = []

    # Check for missing configs
    if not config_data.get("dockerfile") and dep_assessment["total_deps"] > 5:
        insights.append("Sin Dockerfile: considera contenerizar la aplicacion para despliegue consistente.")
    if not config_data.get("cicd"):
        insights.append("Sin CI/CD detectado: configura pipelines para testeo y despliegue automatico.")
    if not config_data.get("readme_full"):
        insights.append("Sin README: agrega documentacion basica del proyecto.")
    if config_data.get("env_vars") and not os.path.exists(os.path.join(ruta, ".gitignore")):
        insights.append("Variables de entorno detectadas pero sin .gitignore: asegurate de excluir .env del repositorio.")
    if pj:
        deps = pj.get("dependencies", {})
        dev_deps = pj.get("devDependencies", {})
        if "typescript" in deps and "typescript" not in dev_deps:
            insights.append("TypeScript esta en dependencies en vez de devDependencies.")
        test_frameworks = {"jest", "vitest", "mocha", "pytest"}
        all_deps = {**deps, **dev_deps}
        if not any(tf in all_deps for tf in test_frameworks) and dep_assessment["total_deps"] > 3:
            insights.append("Sin framework de testing detectado: considera agregar tests.")
        if "eslint" not in all_deps and (lang_counts.get("JavaScript", 0) + lang_counts.get("TypeScript", 0)) > 5:
            insights.append("Sin ESLint: considera agregar linting para mantener calidad de codigo.")
    if req and not config_data.get("pyproject_toml"):
        insights.append("Usa requirements.txt pero no pyproject.toml: considera migrar a pyproject para mejor gestion.")

    # Architecture insights
    if "Monorepo" in architecture:
        insights.append("Monorepo detectado: asegurate de tener configuracion de build incremental para velocidad.")
    if "Microservicios" in architecture:
        insights.append("Microservicios detectados: verifica la comunicacion entre servicios y el manejo de errores.")

    # Deployment readiness
    if config_data.get("dockerfile") and config_data.get("cicd"):
        insights.append("Proyecto listo para CI/CD con Docker: buen setup de despliegue.")
    if pj and "build" in pj.get("scripts", {}):
        insights.append("Script de build configurado: listo para produccion.")

    if insights:
        for i, insight in enumerate(insights[:10], 1):
            result += f"  {i}. {insight}\n"
    else:
        result += "  Proyecto bien configurado. No hay recomendaciones adicionales.\n"

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
