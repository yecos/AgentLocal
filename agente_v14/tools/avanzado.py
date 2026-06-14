"""
=============================================================
AGENTE v15.2 - Herramientas Avanzadas del Super Agente
=============================================================
Herramientas avanzadas que completan las capacidades de Super Z:
- Busqueda profunda (deep search multi-ronda)
- Edicion multiple de archivos (multi-edit)
- Generacion batch de archivos
- Busqueda con patrones (grep-like)
- Listado con glob patterns
- Creacion de proyectos web (Next.js/React scaffolding)
- Resumen de URL (web reader)

Dependencias: requests, beautifulsoup4 (opcionales)
=============================================================
"""

import os
import re
import json
import glob as glob_module
import logging
import subprocess
import tempfile
import time
from config import REPOS_DIR, LEARN_DIR, MAX_TOOL_OUTPUT, logger
from utils.security import validate_path, sanitize_input, validate_url


# ============================================================
# BUSQUEDA PROFUNDA (DEEP SEARCH)
# ============================================================

def busqueda_profunda(
    tema: str,
    profundidad: int = 3,
    idioma: str = "es",
    guardar: bool = True,
) -> str:
    """Realiza una busqueda profunda multi-ronda sobre un tema. Busca en multiples
    fuentes, sigue enlaces relevantes y sintetiza un informe completo.

    Es como un investigador que busca en Google, abre los mejores resultados,
    lee el contenido y compila un resumen exhaustivo.

    Args:
        tema: Tema a investigar en profundidad
        profundidad: Nivel de profundidad (1=rapido, 2=medio, 3=profundo)
        idioma: Idioma preferido para resultados (es, en, fr, de, pt)
        guardar: Si True, guarda el informe en un archivo
    """
    profundidad = min(max(profundidad, 1), 3)
    tema = sanitize_input(tema)

    logger.info(f"Busqueda profunda: '{tema}' (profundidad={profundidad})")

    max_rounds = profundidad * 2  # 2, 4, 6 busquedas
    max_urls_per_round = profundidad + 1  # 2, 3, 4 URLs
    all_findings = []
    visited_urls = set()

    # Ronda 1: Busqueda principal
    search_queries = [tema]

    # Generar queries derivados segun profundidad
    if profundidad >= 2:
        search_queries.append(f"{tema} que es definicion")
        search_queries.append(f"{tema} ultimas novedades")

    if profundidad >= 3:
        search_queries.append(f"{tema} estudios cientificos")
        search_queries.append(f"{tema} opinion expertos")
        search_queries.append(f"{tema} estadisticas datos")

    for round_num in range(min(max_rounds, len(search_queries))):
        query = search_queries[round_num]

        # Buscar en web
        try:
            from tools.web import buscar_web
            search_result = buscar_web(query, use_cache=False)
        except Exception:
            search_result = _fallback_search(query)

        if not search_result or "No se encontraron" in search_result:
            continue

        all_findings.append(f"--- Busqueda: {query} ---\n{search_result}")

        # Extraer URLs de los resultados
        urls = _extract_urls(search_result)
        urls_to_visit = [u for u in urls if u not in visited_urls][:max_urls_per_round]

        # Visitar las URLs mas relevantes
        for url in urls_to_visit:
            if url in visited_urls:
                continue
            visited_urls.add(url)

            try:
                content = _fetch_url_content(url, max_chars=3000)
                if content and len(content) > 100:
                    all_findings.append(f"--- Fuente: {url} ---\n{content}")
            except Exception as e:
                logger.debug(f"Error leyendo {url}: {e}")

        # No hacer demasiadas busquedas seguidas
        if round_num < min(max_rounds, len(search_queries)) - 1:
            time.sleep(1)

    if not all_findings:
        return f"No se encontraron resultados para '{tema}'. Intenta con otro termino."

    # Compilar informe
    report = _compile_deep_report(tema, all_findings, profundidad)

    # Guardar si se solicita
    if guardar:
        safe_name = re.sub(r'[^\w\s-]', '', tema)[:40].strip().replace(' ', '_')
        report_file = os.path.join(LEARN_DIR, f"deep_search_{safe_name}.md")
        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(report)
            report += f"\n\nInforme guardado en: {report_file}"
        except Exception as e:
            report += f"\n\nNo se pudo guardar: {e}"

    return report


def _fallback_search(query: str) -> str:
    """Busqueda fallback cuando buscar_web no esta disponible."""
    try:
        import urllib.request
        import urllib.parse

        encoded = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        parts = []
        if data.get("AbstractText"):
            parts.append(f"Resumen: {data['AbstractText']}")
            if data.get("AbstractURL"):
                parts.append(f"Fuente: {data['AbstractURL']}")
        if data.get("Answer"):
            parts.append(f"Respuesta: {data['Answer']}")
        for r in data.get("RelatedTopics", [])[:5]:
            if isinstance(r, dict) and r.get("Text"):
                parts.append(f"- {r['Text']}")
                if r.get("FirstURL"):
                    parts.append(f"  Link: {r['FirstURL']}")

        return "\n".join(parts) if parts else ""
    except Exception:
        return ""


def _extract_urls(text: str) -> list:
    """Extrae URLs de un texto."""
    url_pattern = r'https?://[^\s<>"\')\]]+'
    urls = re.findall(url_pattern, text)
    # Filtrar URLs no utiles
    skip_domains = ['duckduckgo.com', 'google.com', 'bing.com']
    filtered = []
    for url in urls:
        if not any(d in url for d in skip_domains):
            filtered.append(url.rstrip('.,;:'))
    return filtered[:10]


def _fetch_url_content(url: str, max_chars: int = 3000) -> str:
    """Obtiene el contenido textual de una URL."""
    try:
        validate_url(url)
    except Exception:
        return ""

    try:
        import urllib.request

        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Intentar con BeautifulSoup si esta disponible
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe']):
                tag.decompose()
            main = soup.find('main') or soup.find('article') or soup.find(class_='content')
            text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)
        except ImportError:
            # Fallback basico
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()

        # Limpiar
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        text = '\n'.join(lines)

        if len(text) > max_chars:
            text = text[:max_chars] + "... [truncado]"

        return text

    except Exception as e:
        logger.debug(f"Error fetching {url}: {e}")
        return ""


def _compile_deep_report(tema: str, findings: list, profundidad: int) -> str:
    """Compila los hallazgos en un informe estructurado."""
    from datetime import datetime

    parts = [
        f"# Busqueda Profunda: {tema}",
        f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Profundidad: {profundidad}/3",
        f"Fuentes consultadas: {len(findings)}",
        "",
    ]

    # Intentar sintetizar con LLM si esta disponible
    try:
        from llm import ollama
        all_text = "\n\n".join(findings)[:6000]
        prompt = (
            f"Sintetiza la siguiente informacion sobre '{tema}' en un informe "
            f"estructurado con secciones: Resumen, Puntos Clave, Contexto, "
            f"Detalles, y Conclusiones. Usa formato Markdown.\n\n"
            f"INFORMACION RECOPILADA:\n{all_text}"
        )

        if hasattr(ollama, 'generate'):
            synthesis = ollama.generate(prompt)
            if synthesis and len(synthesis) > 100:
                parts.append(synthesis)
                return "\n".join(parts)
    except Exception:
        pass

    # Fallback: compilacion directa
    parts.append("## Resultados de la Investigacion\n")
    for i, finding in enumerate(findings, 1):
        parts.append(finding)
        parts.append("")

    return "\n".join(parts)


# ============================================================
# EDICION MULTIPLE DE ARCHIVOS (MULTI-EDIT)
# ============================================================

def editar_multiples(ediciones: str, crear_archivos: bool = True) -> str:
    """Realiza multiples ediciones en uno o varios archivos en una sola operacion.
    Cada edicion especifica: archivo, texto_a_buscar, texto_nuevo. Si crear_archivos
    es True, los archivos que no existen se crean automaticamente.

    Args:
        ediciones: Lista JSON de ediciones: [{"archivo": "ruta", "buscar": "texto viejo", "reemplazar": "texto nuevo"}, ...]
        crear_archivos: Si True, crea archivos que no existen (usa "buscar" vacio para archivos nuevos)
    """
    try:
        edits = json.loads(ediciones)
    except json.JSONDecodeError as e:
        return f"ERROR: Formato JSON invalido: {e}. Usa: [{{archivo, buscar, reemplazar}}, ...]"

    if not edits:
        return "ERROR: Lista de ediciones vacia."

    if len(edits) > 50:
        return "ERROR: Maximo 50 ediciones por operacion."

    results = []
    success_count = 0
    error_count = 0

    for i, edit in enumerate(edits):
        archivo = edit.get("archivo", edit.get("file", ""))
        buscar = edit.get("buscar", edit.get("find", edit.get("old", "")))
        reemplazar = edit.get("reemplazar", edit.get("replace", edit.get("new", "")))

        if not archivo:
            results.append(f"  [{i+1}] ERROR: No se especifico archivo")
            error_count += 1
            continue

        # Resolver ruta
        ruta = _resolve_file_path(archivo)

        # Si el archivo no existe
        if not os.path.exists(ruta):
            if crear_archivos:
                try:
                    os.makedirs(os.path.dirname(ruta) if os.path.dirname(ruta) else ".", exist_ok=True)
                    with open(ruta, "w", encoding="utf-8") as f:
                        f.write(reemplazar)
                    results.append(f"  [{i+1}] CREADO: {archivo} ({len(reemplazar)} chars)")
                    success_count += 1
                except Exception as e:
                    results.append(f"  [{i+1}] ERROR creando {archivo}: {e}")
                    error_count += 1
                continue
            else:
                results.append(f"  [{i+1}] ERROR: {archivo} no existe")
                error_count += 1
                continue

        # Leer archivo actual
        try:
            with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            results.append(f"  [{i+1}] ERROR leyendo {archivo}: {e}")
            error_count += 1
            continue

        # Realizar reemplazo
        if buscar:
            if buscar not in content:
                results.append(f"  [{i+1}] NO ENCONTRADO: '{buscar[:50]}...' en {archivo}")
                error_count += 1
                continue

            count = content.count(buscar)
            replace_all = edit.get("reemplazar_todo", edit.get("replaceAll", False))
            if replace_all:
                content = content.replace(buscar, reemplazar)
                results.append(f"  [{i+1}] OK: {archivo} ({count} reemplazos)")
            else:
                content = content.replace(buscar, reemplazar, 1)
                results.append(f"  [{i+1}] OK: {archivo} (1 de {count} reemplazos)")
        else:
            # Si no hay texto a buscar, agregar al final
            content += reemplazar
            results.append(f"  [{i+1}] OK: {archivo} (agregado al final)")

        # Escribir archivo
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(content)
            success_count += 1
        except Exception as e:
            results.append(f"  [{i+1}] ERROR escribiendo {archivo}: {e}")
            error_count += 1

    summary = f"Ediciones: {success_count} exitosas, {error_count} errores de {len(edits)} totales\n"
    return summary + "\n".join(results)


def _resolve_file_path(ruta: str) -> str:
    """Resuelve la ruta de un archivo."""
    if os.path.isabs(ruta):
        return ruta
    if os.path.exists(ruta):
        return os.path.abspath(ruta)
    alt = os.path.join(REPOS_DIR, ruta)
    if os.path.exists(os.path.dirname(alt)):
        return alt
    return os.path.abspath(ruta)


# ============================================================
# GENERACION BATCH DE ARCHIVOS
# ============================================================

def generacion_batch(archivos: str) -> str:
    """Genera multiples archivos en una sola operacion. Ideal para crear
    estructuras de proyecto, templates, o conjuntos de archivos relacionados.

    Args:
        archivos: Lista JSON de archivos: [{"ruta": "dir/archivo.py", "contenido": "..."}, ...]
    """
    try:
        file_list = json.loads(archivos)
    except json.JSONDecodeError as e:
        return f"ERROR: Formato JSON invalido: {e}"

    if not file_list:
        return "ERROR: Lista de archivos vacia."

    if len(file_list) > 30:
        return "ERROR: Maximo 30 archivos por operacion batch."

    results = []
    created = 0
    skipped = 0

    for i, file_info in enumerate(file_list):
        ruta = file_info.get("ruta", file_info.get("path", file_info.get("file", "")))
        contenido = file_info.get("contenido", file_info.get("content", ""))
        sobreescribir = file_info.get("sobreescribir", file_info.get("overwrite", True))

        if not ruta:
            results.append(f"  [{i+1}] ERROR: No se especifico ruta")
            continue

        # Resolver ruta
        full_path = _resolve_file_path(ruta)

        # Verificar si ya existe
        if os.path.exists(full_path) and not sobreescribir:
            results.append(f"  [{i+1}] SKIP: {ruta} (ya existe)")
            skipped += 1
            continue

        # Crear directorios necesarios
        dir_path = os.path.dirname(full_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # Escribir archivo
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(contenido)
            size = len(contenido)
            results.append(f"  [{i+1}] OK: {ruta} ({size} chars)")
            created += 1
        except Exception as e:
            results.append(f"  [{i+1}] ERROR: {ruta}: {e}")

    summary = f"Generacion batch: {created} creados, {skipped} omitidos de {len(file_list)} totales\n"
    return summary + "\n".join(results)


# ============================================================
# BUSQUEDA CON PATRONES (GREP-LIKE)
# ============================================================

def buscar_patron(
    patron: str,
    directorio: str = ".",
    tipo_archivo: str = "",
    max_resultados: int = 30,
    ignorar_case: bool = True,
    contexto: int = 2,
) -> str:
    """Busca un patron de texto o regex en archivos (como grep). Busca en el
    contenido de los archivos del directorio especificado.

    Args:
        patron: Patron de texto o expresion regular a buscar
        directorio: Directorio donde buscar (default: directorio actual)
        tipo_archivo: Filtrar por extension (ej: .py, .js, .txt, .md)
        max_resultados: Maximo resultados a mostrar (default 30)
        ignorar_case: Ignorar mayusculas/minusculas (default True)
        contexto: Lineas de contexto antes/despues (default 2)
    """
    directorio = _resolve_file_path(directorio)
    if not os.path.isdir(directorio):
        return f"ERROR: Directorio no encontrado: {directorio}"

    # Intentar con ripgrep primero (mucho mas rapido)
    rg_result = _search_ripgrep(patron, directorio, tipo_archivo, max_resultados, ignorar_case, contexto)
    if rg_result is not None:
        return rg_result

    # Fallback: busqueda Python pura
    return _search_python(patron, directorio, tipo_archivo, max_resultados, ignorar_case, contexto)


def _search_ripgrep(patron, directorio, tipo_archivo, max_resultados, ignorar_case, contexto):
    """Busqueda usando ripgrep (rg)."""
    try:
        cmd = ["rg"]
        if ignorar_case:
            cmd.append("-i")
        cmd.extend(["-n", "--max-count", str(max_resultados)])
        if contexto > 0:
            cmd.extend(["-C", str(contexto)])
        if tipo_archivo:
            cmd.extend(["--glob", f"*{tipo_archivo}"])
        cmd.extend([patron, directorio])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            if len(lines) > max_resultados:
                lines = lines[:max_resultados]
                lines.append(f"... ({len(result.stdout.strip().split(chr(10)))} resultados totales, mostrando {max_resultados})")

            output = "\n".join(lines)
            if len(output) > MAX_TOOL_OUTPUT:
                output = output[:MAX_TOOL_OUTPUT] + "\n... [truncado]"
            return f"Resultados de busqueda '{patron}':\n{output}"
        elif result.returncode == 1:
            return f"No se encontraron coincidencias para '{patron}' en {directorio}"
        else:
            return None  # rg fallo, usar fallback

    except FileNotFoundError:
        return None  # rg no instalado
    except subprocess.TimeoutExpired:
        return "ERROR: Busqueda excedio el timeout."
    except Exception:
        return None


def _search_python(patron, directorio, tipo_archivo, max_resultados, ignorar_case, contexto):
    """Busqueda fallback usando Python puro."""
    flags = re.IGNORECASE if ignorar_case else 0
    try:
        pattern = re.compile(patron, flags)
    except re.error as e:
        return f"ERROR: Patron regex invalido: {e}"

    # Directorios a ignorar
    skip_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build', '.next', '.cache'}

    results = []
    count = 0

    for root, dirs, files in os.walk(directorio):
        # Filtrar directorios
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for fname in files:
            # Filtrar por extension
            if tipo_archivo and not fname.endswith(tipo_archivo):
                continue

            fpath = os.path.join(root, fname)

            # Solo leer archivos de texto
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except Exception:
                continue

            for line_num, line in enumerate(lines, 1):
                if pattern.search(line):
                    # Mostrar con contexto
                    context_lines = []
                    start = max(0, line_num - 1 - contexto)
                    end = min(len(lines), line_num + contexto)

                    for ctx_i in range(start, end):
                        prefix = ">>>" if ctx_i == line_num - 1 else "   "
                        context_lines.append(f"{prefix} {fpath}:{ctx_i+1}: {lines[ctx_i].rstrip()}")

                    results.append("\n".join(context_lines))
                    count += 1

                    if count >= max_resultados:
                        break

            if count >= max_resultados:
                break

        if count >= max_resultados:
            break

    if not results:
        return f"No se encontraron coincidencias para '{patron}' en {directorio}"

    output = "\n\n".join(results)
    if len(output) > MAX_TOOL_OUTPUT:
        output = output[:MAX_TOOL_OUTPUT] + "\n... [truncado]"

    return f"Resultados de busqueda '{patron}' ({count} encontrados):\n{output}"


# ============================================================
# LISTADO CON GLOB PATTERNS
# ============================================================

def listar_glob(
    patron: str = "**/*",
    directorio: str = ".",
    solo_tipo: str = "todos",
    max_resultados: int = 100,
) -> str:
    """Lista archivos usando glob patterns (como **/*.py, **/test_*.js, etc.).
    Permite busqueda flexible de archivos por nombre, extension o patron.

    Args:
        patron: Patron glob (ej: **/*.py, src/**/*.ts, **/test_*.js, *.md)
        directorio: Directorio base para la busqueda (default: actual)
        solo_tipo: Filtrar: todos, archivos, directorios
        max_resultados: Maximo resultados (default 100)
    """
    directorio = _resolve_file_path(directorio)
    if not os.path.isdir(directorio):
        return f"ERROR: Directorio no encontrado: {directorio}"

    try:
        matches = glob_module.glob(os.path.join(directorio, patron), recursive=True)
    except Exception as e:
        return f"ERROR: Patron glob invalido: {e}"

    # Filtrar por tipo
    if solo_tipo == "archivos":
        matches = [m for m in matches if os.path.isfile(m)]
    elif solo_tipo == "directorios":
        matches = [m for m in matches if os.path.isdir(m)]

    # Ordenar por modificacion (mas recientes primero)
    try:
        matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    except Exception:
        matches.sort()

    if not matches:
        return f"No se encontraron archivos con patron '{patron}' en {directorio}"

    # Limitar resultados
    total = len(matches)
    if len(matches) > max_resultados:
        matches = matches[:max_resultados]

    # Formatear resultados
    results = [f"Archivos encontrados: {total} (mostrando {len(matches)})\n"]

    for match in matches:
        rel_path = os.path.relpath(match, directorio)
        if os.path.isfile(match):
            try:
                size = os.path.getsize(match)
                size_str = f"{size:,} bytes" if size < 1024 else f"{size/1024:.1f} KB"
            except Exception:
                size_str = ""
            results.append(f"  {rel_path}  ({size_str})")
        else:
            results.append(f"  {rel_path}/")

    output = "\n".join(results)
    if len(output) > MAX_TOOL_OUTPUT:
        output = output[:MAX_TOOL_OUTPUT] + "\n... [truncado]"

    return output


# ============================================================
# CREACION DE PROYECTOS WEB (Next.js / React)
# ============================================================

def crear_proyecto_web(
    nombre: str,
    tipo: str = "nextjs",
    directorio: str = "",
    opciones: str = "{}",
) -> str:
    """Crea un proyecto web con scaffolding completo. Soporta Next.js, React,
    Vue, y mas. Genera la estructura de archivos, configuracion y codigo base.

    Args:
        nombre: Nombre del proyecto
        tipo: Tipo de proyecto: nextjs, react, vue, express, static
        directorio: Directorio donde crear el proyecto (default: REPOS_DIR)
        opciones: Opciones adicionales como JSON: {"typescript": true, "tailwind": true, "prisma": true}
    """
    tipo = tipo.lower().strip()
    supported_types = ["nextjs", "react", "vue", "express", "static"]

    if tipo not in supported_types:
        return f"ERROR: Tipo '{tipo}' no soportado. Usar: {', '.join(supported_types)}"

    # Parsear opciones
    try:
        opts = json.loads(opciones) if opciones else {}
    except json.JSONDecodeError:
        opts = {}

    use_typescript = opts.get("typescript", True)
    use_tailwind = opts.get("tailwind", True)
    use_prisma = opts.get("prisma", False)

    # Directorio del proyecto
    base_dir = directorio or REPOS_DIR
    project_dir = os.path.join(base_dir, nombre)

    if os.path.exists(project_dir):
        return f"ERROR: El directorio {project_dir} ya existe. Elige otro nombre o elimina el existente."

    ext = ".ts" if use_typescript else ".js"
    extx = ".tsx" if use_typescript else ".jsx"

    # Generar archivos segun tipo
    files = {}

    if tipo == "nextjs":
        files = _generate_nextjs_project(nombre, ext, extx, use_typescript, use_tailwind, use_prisma)
    elif tipo == "react":
        files = _generate_react_project(nombre, ext, extx, use_typescript, use_tailwind)
    elif tipo == "vue":
        files = _generate_vue_project(nombre, use_typescript, use_tailwind)
    elif tipo == "express":
        files = _generate_express_project(nombre, ext, use_typescript)
    elif tipo == "static":
        files = _generate_static_project(nombre, use_tailwind)

    # Crear todos los archivos
    results = []
    created = 0

    for rel_path, content in files.items():
        full_path = os.path.join(project_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            results.append(f"  OK: {rel_path}")
            created += 1
        except Exception as e:
            results.append(f"  ERROR: {rel_path}: {e}")

    # Intentar instalar dependencias
    install_msg = ""
    if os.path.exists(os.path.join(project_dir, "package.json")):
        results.append("\nDependencias por instalar:")
        results.append(f"  cd {project_dir} && npm install")

        if use_prisma and tipo == "nextjs":
            results.append("  npx prisma init")

        install_msg = (
            f"\n\nPara completar la instalacion:\n"
            f"  cd {project_dir}\n"
            f"  npm install\n"
        )
        if use_prisma:
            install_msg += "  npx prisma init\n  npx prisma generate\n"

    summary = f"Proyecto {tipo} '{nombre}' creado: {created} archivos\n"
    return summary + "\n".join(results) + install_msg


def _generate_nextjs_project(nombre, ext, extx, ts, tailwind, prisma):
    """Genera estructura de proyecto Next.js."""
    files = {
        "package.json": json.dumps({
            "name": nombre,
            "version": "0.1.0",
            "private": True,
            "scripts": {
                "dev": "next dev",
                "build": "next build",
                "start": "next start",
                "lint": "next lint"
            },
            "dependencies": {
                "next": "^15.0.0",
                "react": "^19.0.0",
                "react-dom": "^19.0.0",
                **({"@prisma/client": "^6.0.0"} if prisma else {})
            },
            "devDependencies": {
                **({"typescript": "^5.0.0", "@types/node": "^20.0.0", "@types/react": "^19.0.0"} if ts else {}),
                **({"tailwindcss": "^4.0.0", "@tailwindcss/postcss": "^4.0.0"} if tailwind else {}),
            }
        }, indent=2),

        f"app/layout{extx}": (
            f"{'import type { Metadata } from \"next\";' + chr(10) if ts else ''}"
            f"import './globals.css';\n\n"
            f"{'export const metadata: Metadata = ' if ts else 'export const metadata = '}"
            f"{{\n  title: '{nombre}',\n  description: 'Created with Agente Local',\n}};\n\n"
            f"export default function RootLayout({{ children }}: "
            f"{{' children: React.ReactNode' if ts else ' children'}}) {{\n"
            f"  return (\n    <html lang=\"es\">\n      <body>{{children}}</body>\n"
            f"    </html>\n  );\n}}\n"
        ),

        f"app/page{extx}": (
            f"export default function Home() {{\n"
            f"  return (\n    <main{' className=\"min-h-screen p-8\"' if tailwind else ''}>\n"
            f"      <h1{' className=\"text-4xl font-bold\"' if tailwind else ''}>"
            f"{nombre}</h1>\n"
            f"      <p>Bienvenido a {nombre}</p>\n"
            f"    </main>\n  );\n}}\n"
        ),

        "app/globals.css": (
            f"@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\n"
            f"body {{\n  font-family: system-ui, sans-serif;\n}}\n"
            if tailwind else
            "body { font-family: system-ui, sans-serif; margin: 0; padding: 20px; }\n"
        ),

        "next.config.mjs": (
            "/** @type {import('next').NextConfig} */\n"
            "const nextConfig = {};\nexport default nextConfig;\n"
        ),

        "tsconfig.json": (
            json.dumps({
                "compilerOptions": {
                    "target": "ES2017", "lib": ["dom", "dom.iterable", "esnext"],
                    "allowJs": True, "skipLibCheck": True, "strict": True,
                    "noEmit": True, "esModuleInterop": True, "module": "esnext",
                    "moduleResolution": "bundler", "resolveJsonModule": True,
                    "isolatedModules": True, "jsx": "preserve", "incremental": True,
                    "plugins": [{"name": "next"}], "paths": {"@/*": ["./*"]}
                },
                "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
                "exclude": ["node_modules"]
            }, indent=2)
        ) if ts else None,

        ".gitignore": (
            "node_modules/\n.next/\nout/\nbuild/\n.env*\n*.tsbuildinfo\n"
            "next-env.d.ts\n.DS_Store\n"
        ),

        "README.md": f"# {nombre}\n\nProyecto Next.js creado con Agente Local.\n\n## Getting Started\n\n```bash\nnpm install\nnpm run dev\n```\n\nOpen [http://localhost:3000](http://localhost:3000)\n",
    }

    if prisma:
        files["prisma/schema.prisma"] = (
            'generator client {\n  provider = "prisma-client-js"\n}\n\n'
            'datasource db {\n  provider = "sqlite"\n  url      = "file:./dev.db"\n}\n\n'
            'model Example {\n  id        Int      @id @default(autoincrement())\n'
            '  name      String\n  createdAt DateTime @default(now())\n}\n'
        )
        files[f"lib/db{ext}"] = (
            "import { PrismaClient } from '@prisma/client';\n\n"
            "const prisma = new PrismaClient();\nexport default prisma;\n"
        )

    # Filtrar None values
    return {k: v for k, v in files.items() if v is not None}


def _generate_react_project(nombre, ext, extx, ts, tailwind):
    """Genera estructura de proyecto React (Vite)."""
    return {
        "package.json": json.dumps({
            "name": nombre, "version": "0.1.0", "type": "module",
            "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
            "dependencies": {"react": "^19.0.0", "react-dom": "^19.0.0"},
            "devDependencies": {
                "@vitejs/plugin-react": "^4.0.0", "vite": "^6.0.0",
                **({"typescript": "^5.0.0"} if ts else {}),
                **({"tailwindcss": "^4.0.0"} if tailwind else {}),
            }
        }, indent=2),
        "index.html": (
            f'<!DOCTYPE html>\n<html lang="es">\n<head>\n'
            f'  <meta charset="UTF-8" />\n  <title>{nombre}</title>\n'
            f'</head>\n<body>\n  <div id="root"></div>\n'
            f'  <script type="module" src="/src/main{extx}"></script>\n'
            f'</body>\n</html>\n'
        ),
        f"src/main{extx}": (
            f"import React from 'react';\nimport ReactDOM from 'react-dom/client';\n"
            f"import App from './App{extx}';\nimport './index.css';\n\n"
            f"ReactDOM.createRoot(document.getElementById('root')!).render(\n"
            f"  <React.StrictMode><App /></React.StrictMode>\n);\n"
        ),
        f"src/App{extx}": (
            f"export default function App() {{\n"
            f"  return (\n    <div{' className=\"min-h-screen p-8\"' if tailwind else ''}>\n"
            f"      <h1{' className=\"text-4xl font-bold\"' if tailwind else ''}>"
            f"{nombre}</h1>\n"
            f"      <p>Aplicacion React creada con Agente Local</p>\n"
            f"    </div>\n  );\n}}\n"
        ),
        "src/index.css": "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n" if tailwind else "body { font-family: system-ui; }\n",
        "vite.config.ts": (
            "import { defineConfig } from 'vite';\nimport react from '@vitejs/plugin-react';\n\n"
            "export default defineConfig({ plugins: [react()] });\n"
        ),
        ".gitignore": "node_modules/\ndist/\n.env*\n",
        "README.md": f"# {nombre}\n\nProyecto React creado con Agente Local.\n\n```bash\nnpm install\nnpm run dev\n```\n",
    }


def _generate_vue_project(nombre, ts, tailwind):
    """Genera estructura de proyecto Vue."""
    return {
        "package.json": json.dumps({
            "name": nombre, "version": "0.1.0", "type": "module",
            "scripts": {"dev": "vite", "build": "vite build"},
            "dependencies": {"vue": "^3.5.0"},
            "devDependencies": {
                "@vitejs/plugin-vue": "^5.0.0", "vite": "^6.0.0",
                **({"typescript": "^5.0.0"} if ts else {}),
            }
        }, indent=2),
        "index.html": (
            f'<!DOCTYPE html>\n<html lang="es">\n<head>\n'
            f'  <meta charset="UTF-8" />\n  <title>{nombre}</title>\n'
            f'</head>\n<body>\n  <div id="app"></div>\n'
            f'  <script type="module" src="/src/main.{"ts" if ts else "js"}"></script>\n'
            f'</body>\n</html>\n'
        ),
        "src/main.ts" if ts else "src/main.js": (
            "import { createApp } from 'vue';\nimport App from './App.vue';\n"
            "createApp(App).mount('#app');\n"
        ),
        "src/App.vue": (
            '<template>\n  <div class="app">\n'
            f'    <h1>{nombre}</h1>\n'
            '    <p>Aplicacion Vue creada con Agente Local</p>\n'
            '  </div>\n</template>\n\n'
            '<style scoped>\n.app { padding: 2rem; }\n</style>\n'
        ),
        "vite.config.ts": (
            "import { defineConfig } from 'vite';\nimport vue from '@vitejs/plugin-vue';\n\n"
            "export default defineConfig({ plugins: [vue()] });\n"
        ),
        ".gitignore": "node_modules/\ndist/\n.env*\n",
        "README.md": f"# {nombre}\n\nProyecto Vue creado con Agente Local.\n\n```bash\nnpm install\nnpm run dev\n```\n",
    }


def _generate_express_project(nombre, ext, ts):
    """Genera estructura de proyecto Express API."""
    return {
        "package.json": json.dumps({
            "name": nombre, "version": "0.1.0",
            "scripts": {"dev": "tsx watch src/index.ts" if ts else "node --watch src/index.js", "start": "node dist/index.js"},
            "dependencies": {"express": "^4.21.0", "cors": "^2.8.5"},
            "devDependencies": {"@types/express": "^5.0.0", "@types/cors": "^2.8.0", "tsx": "^4.0.0"} if ts else {},
        }, indent=2),
        f"src/index{ext}": (
            "import express from 'express';\nimport cors from 'cors';\n\n"
            "const app = express();\nconst PORT = process.env.PORT || 3001;\n\n"
            "app.use(cors());\napp.use(express.json());\n\n"
            "// Routes\napp.get('/api/health', (req, res) => {\n"
            "  res.json({ status: 'ok', timestamp: new Date().toISOString() });\n"
            "});\n\n"
            "app.listen(PORT, () => {\n  console.log(`Server running on port ${PORT}`);\n"
            "});\n"
        ),
        ".env.example": "PORT=3001\n",
        ".gitignore": "node_modules/\ndist/\n.env\n",
        "README.md": f"# {nombre}\n\nAPI Express creada con Agente Local.\n\n```bash\nnpm install\nnpm run dev\n```\n",
    }


def _generate_static_project(nombre, tailwind):
    """Genera estructura de sitio estatico."""
    return {
        "index.html": (
            f'<!DOCTYPE html>\n<html lang="es">\n<head>\n'
            f'  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
            f'  <title>{nombre}</title>\n'
            f'  <link rel="stylesheet" href="styles.css" />\n'
            f'</head>\n<body>\n'
            f'  <h1>{nombre}</h1>\n'
            f'  <p>Sitio creado con Agente Local</p>\n'
            f'  <script src="script.js"></script>\n'
            f'</body>\n</html>\n'
        ),
        "styles.css": (
            "* { margin: 0; padding: 0; box-sizing: border-box; }\n"
            "body { font-family: system-ui, sans-serif; padding: 2rem; max-width: 800px; margin: 0 auto; }\n"
            "h1 { font-size: 2rem; margin-bottom: 1rem; }\n"
        ),
        "script.js": "// JavaScript principal\nconsole.log('App loaded');\n",
        "README.md": f"# {nombre}\n\nSitio estatico creado con Agente Local.\n",
    }


# ============================================================
# RESUMEN DE URL (WEB READER)
# ============================================================

def resumir_url(
    url: str,
    max_caracteres: int = 5000,
    extraer: str = "texto",
) -> str:
    """Lee y extrae contenido de una URL web. Puede extraer texto limpio,
    metadatos (titulo, descripcion, fecha) o el HTML crudo.

    Args:
        url: URL de la pagina web a leer
        max_caracteres: Maximo de caracteres a extraer (default 5000)
        extraer: Que extraer: texto, metadatos, html, links, imagenes
    """
    try:
        validate_url(url)
    except Exception as e:
        return f"ERROR: URL invalida: {e}"

    # Obtener HTML
    html = None
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: No se pudo acceder a {url}: {e}"

    if not html:
        return f"ERROR: Respuesta vacia de {url}"

    # Procesar segun tipo
    if extraer == "html":
        if len(html) > max_caracteres:
            html = html[:max_caracteres] + "... [truncado]"
        return f"HTML de {url}:\n{html}"

    if extraer == "links":
        return _extract_links(html, url)

    if extraer == "imagenes" or extraer == "images":
        return _extract_images(html, url)

    if extraer == "metadatos" or extraer == "metadata":
        return _extract_metadata(html, url)

    # Default: extraer texto
    return _extract_text(html, url, max_caracteres)


def _extract_text(html, url, max_chars):
    """Extrae texto limpio del HTML."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe']):
            tag.decompose()

        title = soup.find('title')
        title_text = title.get_text(strip=True) if title else ""

        main = soup.find('main') or soup.find('article') or soup.find(class_='content')
        if main:
            text = main.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        lines = [l for l in text.split('\n') if l.strip()]
        text = '\n'.join(lines)

        header = f"URL: {url}"
        if title_text:
            header += f"\nTitulo: {title_text}"
        header += "\n"

        full = header + "\n" + text
        if len(full) > max_chars:
            full = full[:max_chars] + "\n... [truncado]"

        return full

    except ImportError:
        # Fallback basico
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "... [truncado]"
        return f"URL: {url}\n\n{text}"


def _extract_metadata(html, url):
    """Extrae metadatos de la pagina."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
    except ImportError:
        soup = None

    meta = {"url": url}

    # Titulo
    if soup:
        title = soup.find('title')
        if title:
            meta["titulo"] = title.get_text(strip=True)

        # Meta tags
        for tag in soup.find_all('meta'):
            name = tag.get('name', tag.get('property', ''))
            content = tag.get('content', '')
            if name and content:
                meta[name] = content

        # Links
        links = [a.get('href') for a in soup.find_all('a', href=True)]
        meta["total_links"] = len(links)

        # Imagenes
        images = [img.get('src') for img in soup.find_all('img', src=True)]
        meta["total_imagenes"] = len(images)

        # Headings
        headings = []
        for h in soup.find_all(['h1', 'h2', 'h3']):
            headings.append(f"  {h.name}: {h.get_text(strip=True)[:80]}")
        meta["encabezados"] = headings[:10]

    return json.dumps(meta, ensure_ascii=False, indent=2)


def _extract_links(html, url):
    """Extrae todos los links de la pagina."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        links = []

        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)[:80]
            links.append({"texto": text, "url": href})

        result = f"Links en {url} ({len(links)} encontrados):\n"
        for i, link in enumerate(links[:50], 1):
            result += f"  {i}. {link['texto']}\n     {link['url']}\n"

        return result

    except ImportError:
        # Fallback regex
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
        result = f"Links en {url} ({len(hrefs)} encontrados):\n"
        for i, href in enumerate(hrefs[:50], 1):
            result += f"  {i}. {href}\n"
        return result


def _extract_images(html, url):
    """Extrae todas las imagenes de la pagina."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        images = []

        for img in soup.find_all('img'):
            images.append({
                "src": img.get('src', ''),
                "alt": img.get('alt', ''),
                "width": img.get('width', ''),
                "height": img.get('height', ''),
            })

        result = f"Imagenes en {url} ({len(images)} encontradas):\n"
        for i, img in enumerate(images[:30], 1):
            result += f"  {i}. {img.get('alt', 'Sin alt text')}\n     {img.get('src', '')}\n"

        return result

    except ImportError:
        srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)
        alts = re.findall(r'<img[^>]+alt=["\']([^"\']*)["\']', html)
        result = f"Imagenes en {url} ({len(srcs)} encontradas):\n"
        for i, src in enumerate(srcs[:30], 1):
            alt = alts[i-1] if i-1 < len(alts) else ""
            result += f"  {i}. {alt or 'Sin alt'}\n     {src}\n"
        return result
