"""
=============================================================
AGENTE v15 - Herramientas de Diagramas (Professional Rendering)
=============================================================
13+ tipos de diagramas:
- Flowchart (diagrama de flujo)
- Mind map (mapa mental)
- Tree diagram (diagrama de arbol)
- Org chart (organigrama)
- Architecture diagram (diagrama de arquitectura)
- Network/relationship graph (grafo de red)
- ER diagram (diagrama entidad-relacion)
- Class diagram (diagrama de clases)
- Gantt chart (diagrama de Gantt)
- Swimlane diagram (diagrama de carriles)
- Sequence diagram (diagrama de secuencia)
- Topology/route map (topologia/ruta)
- Knowledge graph (grafo de conocimiento)
- Mermaid (genera codigo Mermaid y renderiza)

Rendering pipeline (en orden de prioridad):
  1. Mermaid CLI (mmdc) — profesional, layouts optimos
  2. Playwright + CSS — HTML renderizado a PNG
  3. matplotlib + networkx — ultimo recurso
=============================================================
"""

import os
import json
import re
import shutil
import subprocess
import tempfile
import logging
from config import REPOS_DIR, logger
from utils.security import validate_path


# ============================================================
# PALETA Y CONSTANTES
# ============================================================

PALETTE = {
    "primary": "#4472C4",
    "secondary": "#ED7D31",
    "tertiary": "#A5A5A5",
    "success": "#70AD47",
    "warning": "#FFC000",
    "danger": "#FF6B6B",
    "info": "#5B9BD5",
    "purple": "#9B59B6",
    "dark_blue": "#264478",
    "teal": "#1ABC9C",
}

CHART_COLORS = [
    "#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#5B9BD5",
    "#70AD47", "#264478", "#9B59B6", "#1ABC9C", "#FF6B6B",
]

MERMAID_THEME_VARS = """%%{init: {'theme': 'base', 'themeVariables': {
  'primaryColor': '#4472C4',
  'primaryTextColor': '#fff',
  'primaryBorderColor': '#264478',
  'lineColor': '#5B9BD5',
  'secondaryColor': '#ED7D31',
  'tertiaryColor': '#F0F4FA',
  'fontSize': '14px',
  'fontFamily': 'system-ui, -apple-system, sans-serif'
}}}%%"""

SUPPORTED_DIAGRAM_TYPES = [
    "flowchart", "mindmap", "tree", "org", "architecture",
    "network", "er", "class", "gantt", "swimlane", "sequence",
    "topology", "knowledge_graph", "state", "mermaid",
]


# ============================================================
# API PUBLICA
# ============================================================

def crear_diagrama(
    ruta: str,
    tipo: str = "flowchart",
    datos: str = "{}",
    titulo: str = "",
    opciones: str = "{}",
) -> str:
    """Crea un diagrama y lo guarda como imagen PNG o como codigo Mermaid.
    Soporta 13+ tipos: flowchart, mindmap, tree, org, architecture,
    network, er, class, gantt, swimlane, sequence, topology,
    knowledge_graph, mermaid.

    Pipeline de renderizado:
      1. Mermaid CLI (mmdc) — mejor calidad
      2. Playwright + CSS HTML — segunda opcion
      3. matplotlib + networkx — ultimo recurso

    Args:
        ruta: Ruta donde guardar (.png, .svg, o .md para Mermaid)
        tipo: Tipo de diagrama (ver lista arriba)
        datos: Datos del diagrama en formato JSON
        titulo: Titulo del diagrama
        opciones: Opciones extra en JSON
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    tipo = tipo.lower().strip().replace("-", "_").replace(" ", "_")

    # Mapear aliases
    aliases = {
        "mind_map": "mindmap", "mapa_mental": "mindmap",
        "arbol": "tree", "tree_diagram": "tree",
        "organigrama": "org", "org_chart": "org",
        "arquitectura": "architecture",
        "red": "network", "grafo": "network", "relationship": "network",
        "entidad_relacion": "er", "er_diagram": "er",
        "diagrama_clases": "class", "class_diagram": "class",
        "gantt_chart": "gantt",
        "carriles": "swimlane", "swimlane_diagram": "swimlane",
        "secuencia": "sequence", "sequence_diagram": "sequence",
        "topologia": "topology", "route_map": "topology",
        "conocimiento": "knowledge_graph", "knowledge": "knowledge_graph",
        "state": "state", "state_diagram": "state",
    }
    tipo = aliases.get(tipo, tipo)

    if tipo not in SUPPORTED_DIAGRAM_TYPES:
        return (f"ERROR: Tipo '{tipo}' no soportado. "
                f"Usar: {', '.join(SUPPORTED_DIAGRAM_TYPES)}")

    # Si es Mermaid directo, generar codigo y renderizar
    if tipo == "mermaid":
        return _crear_mermaid(ruta, datos, titulo, opciones)

    # ── Pipeline de renderizado ──────────────────────────────
    # 1) Generar codigo Mermaid para este tipo de diagrama
    mermaid_code = _to_mermaid(tipo, datos, titulo)

    # 2) Intentar Mermaid CLI (mmdc) — PRIMARY
    result = _render_mermaid_cli(ruta, mermaid_code)
    if result is not None:
        return result

    # 3) Intentar Playwright + CSS — SECONDARY
    result = _render_playwright_css(ruta, tipo, datos, titulo, mermaid_code)
    if result is not None:
        return result

    # 4) Fallback matplotlib + networkx — TERTIARY
    try:
        return _render_matplotlib(ruta, tipo, datos, titulo, opciones)
    except Exception as e:
        logger.debug(f"Renderizado matplotlib fallo: {e}")
        # Ultimo recurso: guardar .md con codigo Mermaid
        return _save_mermaid_md(ruta, mermaid_code)


def generar_mermaid(
    tipo: str = "flowchart",
    datos: str = "{}",
    titulo: str = "",
) -> str:
    """Genera codigo Mermaid para un diagrama. No renderiza, solo genera el codigo.

    Args:
        tipo: Tipo de diagrama
        datos: Datos del diagrama en JSON
        titulo: Titulo (opcional)
    """
    tipo = tipo.lower().strip().replace("-", "_").replace(" ", "_")
    aliases = {
        "mind_map": "mindmap", "mapa_mental": "mindmap",
        "arbol": "tree", "organigrama": "org",
        "arquitectura": "architecture", "red": "network",
        "entidad_relacion": "er", "diagrama_clases": "class",
        "carriles": "swimlane", "secuencia": "sequence",
        "topologia": "topology", "conocimiento": "knowledge_graph",
        "state": "state", "state_diagram": "state",
    }
    tipo = aliases.get(tipo, tipo)

    try:
        return _to_mermaid(tipo, datos, titulo)
    except Exception as e:
        return f"ERROR generando Mermaid: {e}"


# ============================================================
# RENDERIZADO PATH 1: Mermaid CLI (mmdc) — PRIMARY
# ============================================================

def _check_mmdc() -> bool:
    """Verifica si mmdc (Mermaid CLI) esta disponible."""
    try:
        result = subprocess.run(
            ["mmdc", "--version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _find_puppeteer_chrome() -> str | None:
    """Busca un chrome-headless-shell compatible para puppeteer/mmdc."""
    # 1) PUPPETEER_EXECUTABLE_PATH ya configurado
    env_path = os.environ.get("PUPPETEER_EXECUTABLE_PATH", "")
    if env_path and os.path.isfile(env_path):
        return env_path

    # 2) Buscar en cache de puppeteer
    puppeteer_cache = os.path.expanduser("~/.cache/puppeteer")
    if os.path.isdir(puppeteer_cache):
        for subdir in ("chrome-headless-shell", "chrome"):
            base = os.path.join(puppeteer_cache, subdir)
            if not os.path.isdir(base):
                continue
            # Buscar el binario mas reciente
            candidates = []
            for version_dir in sorted(os.listdir(base), reverse=True):
                exe_path = os.path.join(base, version_dir, "chrome-headless-shell-linux64", "chrome-headless-shell")
                if os.path.isfile(exe_path):
                    candidates.append(exe_path)
                exe_path2 = os.path.join(base, version_dir, "chrome-linux64", "chrome")
                if os.path.isfile(exe_path2):
                    candidates.append(exe_path2)
            if candidates:
                return candidates[0]

    # 3) Buscar chromium en PATH
    for name in ("chromium-browser", "chromium", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found

    return None


def _render_mermaid_cli(ruta: str, mermaid_code: str) -> str | None:
    """Renderiza un diagrama usando Mermaid CLI (mmdc).

    Returns:
        Mensaje de exito o None si mmdc no esta disponible/falla.
    """
    if not _check_mmdc():
        return None

    dir_name = os.path.dirname(ruta)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    # Escribir archivo .mmd temporal
    tmp_mmd = ruta + ".tmp.mmd"
    try:
        with open(tmp_mmd, 'w', encoding='utf-8') as f:
            f.write(mermaid_code)

        # Construir entorno con PUPPETEER_EXECUTABLE_PATH si es necesario
        env = os.environ.copy()
        chrome_path = _find_puppeteer_chrome()
        if chrome_path:
            env["PUPPETEER_EXECUTABLE_PATH"] = chrome_path

        cmd = [
            "mmdc",
            "-i", tmp_mmd,
            "-o", ruta,
            "-b", "white",
            "-w", "1600",
            "-s", "2",
        ]

        render_result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, env=env
        )

        if render_result.returncode == 0 and os.path.exists(ruta):
            size_kb = os.path.getsize(ruta) / 1024
            return f"Diagrama Mermaid renderizado (mmdc): {ruta} ({size_kb:.0f} KB)"

        # Si falla, log y devolver None para probar siguiente path
        logger.debug(f"mmdc fallo: {render_result.stderr}")
        return None

    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug(f"mmdc timeout/error: {e}")
        return None
    finally:
        if os.path.exists(tmp_mmd):
            os.remove(tmp_mmd)


# ============================================================
# RENDERIZADO PATH 2: Playwright + CSS — SECONDARY
# ============================================================

def _render_playwright_css(
    ruta: str,
    tipo: str,
    datos: dict,
    titulo: str,
    mermaid_code: str,
) -> str | None:
    """Renderiza diagrama generando HTML con CSS y usando Playwright para screenshot.

    Returns:
        Mensaje de exito o None si Playwright no esta disponible/falla.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    dir_name = os.path.dirname(ruta)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    # Generar HTML segun tipo de diagrama
    html_content = _generate_html(tipo, datos, titulo, mermaid_code)

    tmp_html = ruta + ".tmp.html"
    try:
        with open(tmp_html, 'w', encoding='utf-8') as f:
            f.write(html_content)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 1600, "height": 1000},
                device_scale_factor=2,
            )
            page.goto(f"file://{os.path.abspath(tmp_html)}")
            page.wait_for_timeout(500)  # Esperar render CSS

            # Auto-size: medir contenido y ajustar
            body = page.query_selector("body")
            if body:
                box = body.bounding_box()
                if box:
                    # Padding
                    clip = {
                        "x": 0,
                        "y": 0,
                        "width": max(box["x"] + box["width"] + 40, 400),
                        "height": max(box["y"] + box["height"] + 40, 300),
                    }
                    page.screenshot(path=ruta, clip=clip, full_page=False)
                else:
                    page.screenshot(path=ruta, full_page=True)
            else:
                page.screenshot(path=ruta, full_page=True)

            browser.close()

        if os.path.exists(ruta):
            size_kb = os.path.getsize(ruta) / 1024
            return f"Diagrama renderizado (Playwright+CSS): {ruta} ({size_kb:.0f} KB)"
        return None

    except Exception as e:
        logger.debug(f"Playwright render fallo: {e}")
        return None
    finally:
        if os.path.exists(tmp_html):
            os.remove(tmp_html)


def _generate_html(tipo: str, datos: dict, titulo: str, mermaid_code: str) -> str:
    """Genera HTML profesional con CSS para el diagrama."""

    # Tipos que se renderizan mejor como Mermaid embebido en HTML
    mermaid_native_types = {"flowchart", "sequence", "er", "class", "gantt", "state", "mindmap"}

    if tipo in mermaid_native_types:
        return _html_mermaid_embed(mermaid_code, titulo)
    elif tipo == "network" or tipo == "knowledge_graph" or tipo == "topology":
        return _html_graph_css(datos, titulo, tipo)
    elif tipo == "tree" or tipo == "org":
        return _html_hierarchy_css(datos, titulo, tipo)
    elif tipo == "architecture":
        return _html_architecture_css(datos, titulo)
    elif tipo == "swimlane":
        return _html_swimlane_css(datos, titulo)
    else:
        return _html_mermaid_embed(mermaid_code, titulo)


def _html_mermaid_embed(mermaid_code: str, titulo: str) -> str:
    """Genera HTML que embebe Mermaid JS para renderizar en el navegador."""
    title_html = f'<h1 class="diagram-title">{_esc(titulo)}</h1>' if titulo else ''
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: white;
    padding: 30px;
    display: inline-block;
  }}
  .diagram-title {{
    font-size: 22px;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 20px;
    padding-bottom: 10px;
    border-bottom: 3px solid #4472C4;
  }}
  .mermaid {{
    font-family: 'Segoe UI', system-ui, sans-serif;
  }}
</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
</head>
<body>
{title_html}
<pre class="mermaid">
{_esc(mermaid_code)}
</pre>
<script>
  mermaid.initialize({{
    startOnLoad: true,
    theme: 'base',
    themeVariables: {{
      primaryColor: '#4472C4',
      primaryTextColor: '#fff',
      primaryBorderColor: '#264478',
      lineColor: '#5B9BD5',
      secondaryColor: '#ED7D31',
      tertiaryColor: '#F0F4FA',
      fontSize: '14px',
      fontFamily: 'system-ui, sans-serif'
    }}
  }});
</script>
</body>
</html>"""


def _html_graph_css(datos: dict, titulo: str, tipo: str) -> str:
    """Genera HTML con CSS para grafos de red / conocimiento / topologia."""
    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))

    # Recoger nodos desde aristas si no hay nodos explicitos
    node_set = {}
    for node in nodes:
        if isinstance(node, str):
            node_set[node] = {"id": node, "label": node}
        elif isinstance(node, dict):
            nid = node.get("id", node.get("nombre", ""))
            label = node.get("label", node.get("nombre", node.get("name", nid)))
            node_set[nid] = {"id": nid, "label": label}

    edge_list = []
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            src, dst = str(edge[0]), str(edge[1])
            label = str(edge[2]) if len(edge) > 2 else ""
            edge_list.append({"src": src, "dst": dst, "label": label})
            if src not in node_set:
                node_set[src] = {"id": src, "label": src}
            if dst not in node_set:
                node_set[dst] = {"id": dst, "label": dst}
        elif isinstance(edge, dict):
            src = edge.get("from", edge.get("source", ""))
            dst = edge.get("to", edge.get("target", ""))
            label = edge.get("label", edge.get("etiqueta", ""))
            edge_list.append({"src": src, "dst": dst, "label": label})
            if src not in node_set:
                node_set[src] = {"id": src, "label": src}
            if dst not in node_set:
                node_set[dst] = {"id": dst, "label": dst}

    # Posicionar nodos en layout force-directed simplificado (circular con jitter)
    import math
    n = len(node_set)
    positions = {}
    for i, nid in enumerate(node_set):
        angle = 2 * math.pi * i / max(n, 1) - math.pi / 2
        cx, cy = 400, 350
        radius = min(300, 80 * n ** 0.5)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        positions[nid] = (x, y)

    title_html = f'<h1 class="diagram-title">{_esc(titulo)}</h1>' if titulo else ''

    # SVG
    svg_nodes = ""
    colors = CHART_COLORS
    for i, (nid, info) in enumerate(node_set.items()):
        x, y = positions[nid]
        color = colors[i % len(colors)]
        label = info["label"]
        svg_nodes += f'''
      <g class="node" transform="translate({x},{y})">
        <circle r="28" fill="{color}" stroke="#264478" stroke-width="2"/>
        <text text-anchor="middle" dy="0.35em" fill="white"
              font-size="11" font-weight="600" font-family="system-ui,sans-serif">
          {_esc(label[:14])}
        </text>
      </g>'''

    svg_edges = ""
    for edge in edge_list:
        src, dst = edge["src"], edge["dst"]
        if src in positions and dst in positions:
            x1, y1 = positions[src]
            x2, y2 = positions[dst]
            svg_edges += f'''
      <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"
            stroke="#5B9BD5" stroke-width="2" marker-end="url(#arrowhead)"/>'''
            if edge["label"]:
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                svg_edges += f'''
      <text x="{mx}" y="{my - 8}" text-anchor="middle" fill="#555"
            font-size="10" font-family="system-ui,sans-serif">{_esc(edge["label"])}</text>'''

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: white;
    padding: 30px;
  }}
  .diagram-title {{
    font-size: 22px; font-weight: 700; color: #1a1a2e;
    margin-bottom: 20px; padding-bottom: 10px;
    border-bottom: 3px solid #4472C4;
  }}
  svg {{ overflow: visible; }}
  .node {{ cursor: default; }}
  .node:hover circle {{ filter: brightness(1.15); }}
</style>
</head>
<body>
{title_html}
<svg width="800" height="700" viewBox="0 0 800 700">
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="7"
            refX="32" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#5B9BD5"/>
    </marker>
  </defs>
  <rect width="800" height="700" fill="white"/>
{svg_edges}
{svg_nodes}
</svg>
</body>
</html>"""


def _html_hierarchy_css(datos: dict, titulo: str, tipo: str) -> str:
    """Genera HTML con CSS para diagramas jerarquicos (tree, org)."""
    hierarchy = datos.get("hierarchy", datos.get("jerarquia", {}))
    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))

    # Construir jerarquia desde datos
    if not hierarchy:
        hierarchy = _build_hierarchy_from_edges(nodes, edges)

    title_html = f'<h1 class="diagram-title">{_esc(titulo)}</h1>' if titulo else ''
    is_org = tipo == "org"

    tree_css = """
    .tree ul {
      padding-top: 20px; position: relative;
      transition: all 0.5s;
    }
    .tree li {
      float: left; text-align: center;
      list-style-type: none; position: relative;
      padding: 20px 8px 0 8px;
      transition: all 0.5s;
    }
    .tree li::before, .tree li::after {
      content: ''; position: absolute; top: 0;
      right: 50%; border-top: 2px solid #5B9BD5;
      width: 50%; height: 20px;
    }
    .tree li::after {
      right: auto; left: 50%;
      border-left: 2px solid #5B9BD5;
    }
    .tree li:only-child::after, .tree li:only-child::before {
      display: none;
    }
    .tree li:only-child { padding-top: 0; }
    .tree li:first-child::before, .tree li:last-child::after {
      border: 0 none;
    }
    .tree li:last-child::before {
      border-right: 2px solid #5B9BD5;
      border-radius: 0 5px 0 0;
    }
    .tree li:first-child::after {
      border-radius: 5px 0 0 0;
    }
    .tree ul ul::before {
      content: ''; position: absolute; top: 0;
      left: 50%; border-left: 2px solid #5B9BD5;
      width: 0; height: 20px;
    }
    .tree .node-box {
      border: 2px solid #264478;
      padding: 10px 16px;
      display: inline-block;
      color: white; font-weight: 600;
      font-size: 13px; font-family: 'Segoe UI', system-ui, sans-serif;
      text-decoration: none;
      border-radius: 8px;
      background: linear-gradient(135deg, #4472C4, #264478);
      min-width: 80px;
    }
    """

    org_css = """
    .tree .node-box {
      border-radius: 50px;
      background: linear-gradient(135deg, #4472C4, #5B9BD5);
      padding: 12px 20px;
      min-width: 100px;
    }
    .tree .node-box .role {
      display: block; font-size: 10px;
      font-weight: 400; opacity: 0.85; margin-top: 2px;
    }
    """

    def render_hierarchy(data, is_root=False):
        if isinstance(data, dict):
            items = []
            for key, children in data.items():
                child_html = render_hierarchy(children) if children else ""
                css_class = "node-box"
                items.append(
                    f'<li><span class="{css_class}">{_esc(key)}</span>'
                    f'{f"<ul>{child_html}</ul>" if child_html else ""}</li>'
                )
            return "".join(items)
        elif isinstance(data, list):
            items = []
            for item in data:
                if isinstance(item, str):
                    items.append(f'<li><span class="node-box">{_esc(item)}</span></li>')
                elif isinstance(item, dict):
                    items.append(render_hierarchy(item))
            return "".join(items)
        return ""

    tree_content = render_hierarchy(hierarchy)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: white; padding: 30px;
  }}
  .diagram-title {{
    font-size: 22px; font-weight: 700; color: #1a1a2e;
    margin-bottom: 20px; padding-bottom: 10px;
    border-bottom: 3px solid #4472C4;
  }}
  .tree {{
    display: flex; justify-content: center;
    overflow-x: auto;
  }}
  {tree_css}
  {"org_css" if is_org else ""}
</style>
</head>
<body>
{title_html}
<div class="tree">
  <ul>{tree_content}</ul>
</div>
</body>
</html>"""


def _html_architecture_css(datos: dict, titulo: str) -> str:
    """Genera HTML con CSS para diagramas de arquitectura (cajas y flechas)."""
    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))

    # Construir componentes
    components = []
    for node in nodes:
        if isinstance(node, str):
            components.append({"id": node, "label": node, "type": "service"})
        elif isinstance(node, dict):
            nid = node.get("id", node.get("nombre", ""))
            label = node.get("label", node.get("nombre", node.get("name", nid)))
            ctype = node.get("type", node.get("tipo", "service"))
            components.append({"id": nid, "label": label, "type": ctype})

    if not components:
        components = [{"id": "app", "label": "Application", "type": "service"}]

    # Posicionar en grid
    cols = min(4, len(components))
    rows = (len(components) + cols - 1) // cols

    box_width = 180
    box_height = 70
    gap_x = 40
    gap_y = 50
    svg_width = cols * (box_width + gap_x) + gap_x
    svg_height = rows * (box_height + gap_y) + gap_y + 100

    positions = {}
    for i, comp in enumerate(components):
        row = i // cols
        col = i % cols
        x = gap_x + col * (box_width + gap_x) + box_width // 2
        y = 60 + row * (box_height + gap_y)
        positions[comp["id"]] = (x, y, box_width, box_height)

    type_colors = {
        "service": "#4472C4",
        "database": "#ED7D31",
        "queue": "#70AD47",
        "cache": "#FFC000",
        "client": "#9B59B6",
        "api": "#5B9BD5",
        "external": "#A5A5A5",
    }

    title_html = f'<h1 class="diagram-title">{_esc(titulo)}</h1>' if titulo else ''

    svg_content = ""
    # Draw edges
    for edge in edges:
        if isinstance(edge, dict):
            src = edge.get("from", edge.get("source", ""))
            dst = edge.get("to", edge.get("target", ""))
            label = edge.get("label", edge.get("etiqueta", ""))
        elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
            src, dst = str(edge[0]), str(edge[1])
            label = str(edge[2]) if len(edge) > 2 else ""
        else:
            continue

        if src in positions and dst in positions:
            sx, sy, sw, sh = positions[src]
            dx, dy, dw, dh = positions[dst]
            # Centro inferior de src -> centro superior de dst
            x1 = sx
            y1 = sy + sh
            x2 = dx
            y2 = dy
            svg_content += f'''
      <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"
            stroke="#5B9BD5" stroke-width="2" stroke-dasharray="6,3"
            marker-end="url(#arch-arrow)"/>'''
            if label:
                mx = (x1 + x2) / 2
                my = (y1 + y2) / 2
                svg_content += f'''
      <rect x="{mx - 30}" y="{my - 10}" width="60" height="18" rx="4"
            fill="#F0F4FA" stroke="#5B9BD5" stroke-width="1"/>
      <text x="{mx}" y="{my + 3}" text-anchor="middle" fill="#264478"
            font-size="9" font-family="system-ui,sans-serif">{_esc(label)}</text>'''

    # Draw nodes
    for comp in components:
        if comp["id"] in positions:
            x, y, w, h = positions[comp["id"]]
            color = type_colors.get(comp["type"], "#4472C4")
            is_db = comp["type"] == "database"
            if is_db:
                # Database shape (cylinder-ish)
                svg_content += f'''
      <g>
        <rect x="{x - w//2}" y="{y}" width="{w}" height="{h}" rx="8"
              fill="{color}" stroke="#264478" stroke-width="2"/>
        <ellipse cx="{x}" cy="{y + 6}" rx="{w//2}" ry="8" fill="{color}"
                 stroke="#264478" stroke-width="2"/>
        <text x="{x}" y="{y + h//2 + 6}" text-anchor="middle" fill="white"
              font-size="12" font-weight="600" font-family="system-ui,sans-serif">
          {_esc(comp["label"][:16])}
        </text>
      </g>'''
            else:
                svg_content += f'''
      <rect x="{x - w//2}" y="{y}" width="{w}" height="{h}" rx="8"
            fill="{color}" stroke="#264478" stroke-width="2"/>
      <text x="{x}" y="{y + h//2 + 5}" text-anchor="middle" fill="white"
            font-size="12" font-weight="600" font-family="system-ui,sans-serif">
        {_esc(comp["label"][:16])}
      </text>'''

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: white; padding: 30px;
  }}
  .diagram-title {{
    font-size: 22px; font-weight: 700; color: #1a1a2e;
    margin-bottom: 20px; padding-bottom: 10px;
    border-bottom: 3px solid #4472C4;
  }}
  svg {{ overflow: visible; }}
</style>
</head>
<body>
{title_html}
<svg width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}">
  <defs>
    <marker id="arch-arrow" markerWidth="10" markerHeight="7"
            refX="10" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#5B9BD5"/>
    </marker>
  </defs>
  <rect width="{svg_width}" height="{svg_height}" fill="white"/>
{svg_content}
</svg>
</body>
</html>"""


def _html_swimlane_css(datos: dict, titulo: str) -> str:
    """Genera HTML con CSS para diagramas swimlane."""
    lanes = datos.get("lanes", datos.get("carriles", []))
    steps = datos.get("steps", datos.get("pasos", []))

    if not lanes:
        lanes = ["Lane 1", "Lane 2"]
    if not steps:
        # Fallback a mermaid
        return _html_mermaid_embed(_to_mermaid("swimlane", json.dumps(datos), titulo), titulo)

    title_html = f'<h1 class="diagram-title">{_esc(titulo)}</h1>' if titulo else ''

    lane_colors = CHART_COLORS[:len(lanes)]

    lanes_html = ""
    for i, lane in enumerate(lanes):
        color = lane_colors[i % len(lane_colors)]
        steps_in_lane = [s for s in steps if s.get("lane", s.get("carril", lanes[0])) == lane]
        steps_html = ""
        for step in steps_in_lane:
            text = step.get("texto", step.get("text", ""))
            steps_html += f'<div class="step" style="background:{color}">{_esc(text)}</div>\n'
        lanes_html += f'''
      <div class="lane">
        <div class="lane-header" style="background:{color}">{_esc(lane)}</div>
        <div class="lane-body">
          {steps_html}
        </div>
      </div>'''

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: white; padding: 30px;
  }}
  .diagram-title {{
    font-size: 22px; font-weight: 700; color: #1a1a2e;
    margin-bottom: 20px; padding-bottom: 10px;
    border-bottom: 3px solid #4472C4;
  }}
  .swimlane-container {{
    display: flex; border: 2px solid #264478;
    border-radius: 8px; overflow: hidden;
  }}
  .lane {{ flex: 1; border-right: 1px solid #ddd; }}
  .lane:last-child {{ border-right: none; }}
  .lane-header {{
    padding: 12px 16px; color: white;
    font-weight: 700; font-size: 14px;
    text-align: center;
  }}
  .lane-body {{
    padding: 16px; min-height: 200px;
    background: #FAFBFD;
    display: flex; flex-direction: column; gap: 10px;
  }}
  .step {{
    padding: 10px 14px; border-radius: 6px;
    color: white; font-weight: 600; font-size: 12px;
    text-align: center; min-width: 100px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.15);
  }}
</style>
</head>
<body>
{title_html}
<div class="swimlane-container">
{lanes_html}
</div>
</body>
</html>"""


# ============================================================
# RENDERIZADO PATH 3: matplotlib + networkx — TERTIARY FALLBACK
# ============================================================

def _render_matplotlib(ruta, tipo, datos_str, titulo, opciones_str):
    """Renderiza un diagrama usando matplotlib + networkx (ultimo recurso)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import numpy as np

    _setup_fonts()

    datos = _parse_json(datos_str, {})
    opts = _parse_json(opciones_str, {})

    if tipo == "gantt":
        return _mpl_gantt(ruta, datos, titulo, opts)
    if tipo == "sequence":
        return _mpl_sequence(ruta, datos, titulo, opts)
    if tipo == "swimlane":
        return _mpl_swimlane(ruta, datos, titulo, opts)

    try:
        return _mpl_graph(ruta, tipo, datos, titulo, opts)
    except ImportError:
        return _mpl_simple(ruta, tipo, datos, titulo, opts)


def _mpl_graph(ruta, tipo, datos, titulo, opts):
    """Renderiza diagramas de grafo usando networkx + matplotlib."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import networkx as nx
    import numpy as np

    _setup_fonts()
    G = _build_graph(tipo, datos)

    fig, ax = plt.subplots(figsize=(opts.get("fig_width", 14),
                                     opts.get("fig_height", 10)))

    # Layout segun tipo
    if tipo in ("tree", "org"):
        pos = (nx.drawing.nx_agraph.graphviz_layout(G, prog='dot')
               if _has_graphviz() else _hierarchy_pos(G))
    elif tipo == "mindmap":
        pos = (nx.drawing.nx_agraph.graphviz_layout(G, prog='twopi')
               if _has_graphviz() else nx.spring_layout(G, k=2, iterations=50))
    elif tipo in ("architecture", "topology"):
        pos = (nx.drawing.nx_agraph.graphviz_layout(G, prog='fdp')
               if _has_graphviz() else nx.spring_layout(G, k=1.5, iterations=50))
    elif tipo in ("network", "knowledge_graph"):
        pos = nx.spring_layout(G, k=1.5, iterations=50, seed=42)
    elif tipo == "er":
        pos = nx.circular_layout(G)
    elif tipo == "class":
        pos = (nx.drawing.nx_agraph.graphviz_layout(G, prog='dot')
               if _has_graphviz() else nx.spring_layout(G, k=2, iterations=50))
    else:
        pos = nx.spring_layout(G, seed=42)

    node_colors = opts.get("node_colors", None)
    edge_colors = opts.get("edge_colors", "#888888")
    node_size = opts.get("node_size", 1500)
    node_color = node_colors or PALETTE["primary"]

    labels = nx.get_node_attributes(G, 'label')
    if not labels:
        labels = {n: str(n) for n in G.nodes()}

    max_label_len = max(len(str(l)) for l in labels.values()) if labels else 1
    font_size = max(6, min(10, 14 - max_label_len))

    nx.draw_networkx_nodes(G, pos, ax=ax, node_size=node_size,
                           node_color=node_color, alpha=0.8)
    nx.draw_networkx_labels(G, pos, labels, ax=ax, font_size=font_size,
                            font_color='white', font_weight='bold')

    edge_labels = nx.get_edge_attributes(G, 'label')
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color=edge_colors,
                           arrows=True, arrowsize=15,
                           connectionstyle='arc3,rad=0.1')
    if edge_labels:
        nx.draw_networkx_edge_labels(G, pos, edge_labels, ax=ax,
                                      font_size=7, font_color='#555555')

    if titulo:
        ax.set_title(titulo, fontsize=14, fontweight='bold', pad=15)

    ax.axis('off')
    plt.tight_layout()

    dir_name = os.path.dirname(ruta)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    plt.savefig(ruta, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    size_kb = os.path.getsize(ruta) / 1024
    return (f"Diagrama [{tipo}] creado (matplotlib): {ruta} "
            f"({size_kb:.0f} KB, {G.number_of_nodes()} nodos, {G.number_of_edges()} aristas)")


def _build_graph(tipo, datos):
    """Construye un grafo networkx desde los datos JSON."""
    import networkx as nx

    G = nx.DiGraph() if tipo in ("tree", "org", "flowchart", "class", "sequence") else nx.Graph()

    nodes = datos.get("nodes", datos.get("nodos", []))
    for node in nodes:
        if isinstance(node, str):
            G.add_node(node, label=node)
        elif isinstance(node, dict):
            nid = node.get("id", node.get("nombre", ""))
            label = node.get("label", node.get("nombre", node.get("name", nid)))
            G.add_node(nid, label=label, **{k: v for k, v in node.items()
                                            if k not in ("id", "label", "nombre", "name")})

    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            G.add_edge(edge[0], edge[1], label=str(edge[2]) if len(edge) > 2 else "")
        elif isinstance(edge, dict):
            src = edge.get("from", edge.get("source", edge.get("desde", "")))
            dst = edge.get("to", edge.get("target", edge.get("hasta", "")))
            label = edge.get("label", edge.get("etiqueta", ""))
            G.add_edge(src, dst, label=label)

    if not nodes and not edges:
        hierarchy = datos.get("hierarchy", datos.get("jerarquia", {}))
        if hierarchy:
            _add_hierarchy(G, hierarchy, root=None)

    return G


def _add_hierarchy(G, data, root=None):
    """Agrega nodos y aristas desde una estructura jerarquica."""
    if isinstance(data, dict):
        for key, children in data.items():
            G.add_node(key, label=key)
            if root is not None:
                G.add_edge(root, key)
            if isinstance(children, dict):
                _add_hierarchy(G, children, root=key)
            elif isinstance(children, list):
                for child in children:
                    if isinstance(child, str):
                        G.add_node(child, label=child)
                        G.add_edge(key, child)
                    elif isinstance(child, dict):
                        _add_hierarchy(G, child, root=key)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                G.add_node(item, label=item)
                if root is not None:
                    G.add_edge(root, item)


def _mpl_gantt(ruta, datos, titulo, opts):
    """Renderiza un diagrama de Gantt con matplotlib."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from datetime import datetime

    _setup_fonts()
    tasks = datos.get("tasks", datos.get("tareas", []))
    if not tasks:
        return "ERROR: Diagrama de Gantt requiere 'tasks' con: nombre, inicio, duracion"

    fig, ax = plt.subplots(figsize=(opts.get("fig_width", 12),
                                     opts.get("fig_height", 6)))
    colors = opts.get("colors", CHART_COLORS)

    for i, task in enumerate(tasks):
        name = task.get("nombre", task.get("name", f"Tarea {i+1}"))
        start = task.get("inicio", task.get("start", 0))
        duration = task.get("duracion", task.get("duration", 1))
        color = task.get("color", colors[i % len(colors)])

        if isinstance(start, str):
            try:
                start_dt = datetime.strptime(start, "%Y-%m-%d")
                start_num = (start_dt - datetime(2000, 1, 1)).days
            except ValueError:
                start_num = float(start)
        else:
            start_num = float(start)

        ax.barh(i, duration, left=start_num, height=0.6,
                color=color, alpha=0.8, edgecolor='white')
        ax.text(start_num + duration / 2, i, name, ha='center', va='center',
                fontsize=8, fontweight='bold', color='white')

    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels([t.get("nombre", t.get("name", f"Tarea {i+1}"))
                         for i, t in enumerate(tasks)])
    ax.invert_yaxis()
    ax.set_xlabel("Tiempo")
    if titulo:
        ax.set_title(titulo, fontsize=14, fontweight='bold')
    ax.grid(True, axis='x', alpha=0.3)
    plt.tight_layout()

    dir_name = os.path.dirname(ruta)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    plt.savefig(ruta, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    size_kb = os.path.getsize(ruta) / 1024
    return f"Diagrama [gantt] creado (matplotlib): {ruta} ({size_kb:.0f} KB, {len(tasks)} tareas)"


def _mpl_sequence(ruta, datos, titulo, opts):
    """Renderiza un diagrama de secuencia con matplotlib."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    _setup_fonts()
    participants = datos.get("participants", datos.get("participantes", []))
    messages = datos.get("messages", datos.get("mensajes", []))
    if not participants:
        participants = ["A", "B"]
    if not messages:
        return "ERROR: Diagrama de secuencia requiere 'messages' con: from, to, text"

    n = len(participants)
    fig, ax = plt.subplots(figsize=(opts.get("fig_width", 12),
                                     opts.get("fig_height", 8)))
    x_positions = np.linspace(0.1, 0.9, n)
    for i, p in enumerate(participants):
        ax.plot([x_positions[i]], [0.95], 's', markersize=20, color=PALETTE["primary"])
        ax.text(x_positions[i], 0.98, p, ha='center', va='bottom', fontsize=10, fontweight='bold')
        ax.axvline(x=x_positions[i], ymin=0, ymax=0.9, color='#CCCCCC', linewidth=1, linestyle='--')

    y_start = 0.88
    y_step = min(0.05, 0.8 / max(len(messages), 1))
    for i, msg in enumerate(messages):
        src = msg.get("from", msg.get("desde", ""))
        dst = msg.get("to", msg.get("hasta", ""))
        text = msg.get("text", msg.get("texto", ""))
        src_idx = participants.index(src) if src in participants else 0
        dst_idx = participants.index(dst) if dst in participants else min(1, n - 1)
        y = y_start - i * y_step
        color = PALETTE["success"] if src_idx < dst_idx else PALETTE["danger"]
        ax.annotate("", xy=(x_positions[dst_idx], y), xytext=(x_positions[src_idx], y),
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.5))
        mid_x = (x_positions[src_idx] + x_positions[dst_idx]) / 2
        ax.text(mid_x, y + 0.01, text, ha='center', va='bottom', fontsize=8,
                bbox=dict(boxstyle='round,pad=0.2', facecolor='lightyellow', alpha=0.8))

    if titulo:
        ax.set_title(titulo, fontsize=14, fontweight='bold')
    ax.axis('off')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    plt.tight_layout()

    dir_name = os.path.dirname(ruta)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    plt.savefig(ruta, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    size_kb = os.path.getsize(ruta) / 1024
    return f"Diagrama [sequence] creado (matplotlib): {ruta} ({size_kb:.0f} KB)"


def _mpl_swimlane(ruta, datos, titulo, opts):
    """Renderiza un diagrama de swimlane con matplotlib."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    _setup_fonts()
    lanes = datos.get("lanes", datos.get("carriles", []))
    steps = datos.get("steps", datos.get("pasos", []))
    if not lanes:
        lanes = ["Lane 1", "Lane 2"]
    if not steps:
        return "ERROR: Diagrama swimlane requiere 'steps' con: lane, texto, orden"

    n_lanes = len(lanes)
    fig, ax = plt.subplots(figsize=(opts.get("fig_width", 14),
                                     opts.get("fig_height", max(4, 2 + len(steps) * 0.5))))
    lane_height = 1.0 / n_lanes
    colors = CHART_COLORS[:n_lanes]
    for i, lane in enumerate(lanes):
        y_bottom = 1.0 - (i + 1) * lane_height
        ax.axhspan(y_bottom, y_bottom + lane_height, alpha=0.1, color=colors[i])
        ax.text(-0.02, y_bottom + lane_height / 2, lane, ha='right', va='center',
                fontsize=10, fontweight='bold', color=colors[i])

    step_width = 0.8 / max(len(steps), 1)
    for i, step in enumerate(steps):
        lane_name = step.get("lane", step.get("carril", lanes[0]))
        text = step.get("texto", step.get("text", f"Paso {i+1}"))
        order = step.get("orden", step.get("order", i))
        lane_idx = lanes.index(lane_name) if lane_name in lanes else 0
        x = 0.05 + (order * step_width) + step_width / 2
        y = 1.0 - (lane_idx + 0.5) * lane_height
        bbox = dict(boxstyle='round,pad=0.3', facecolor=colors[lane_idx], alpha=0.7)
        ax.text(x, y, text, ha='center', va='center', fontsize=8,
                fontweight='bold', color='white', bbox=bbox)

    if titulo:
        ax.set_title(titulo, fontsize=14, fontweight='bold')
    ax.axis('off')
    ax.set_xlim(-0.15, 1.05)
    ax.set_ylim(0, 1.05)
    plt.tight_layout()

    dir_name = os.path.dirname(ruta)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    plt.savefig(ruta, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    size_kb = os.path.getsize(ruta) / 1024
    return f"Diagrama [swimlane] creado (matplotlib): {ruta} ({size_kb:.0f} KB)"


def _mpl_simple(ruta, tipo, datos, titulo, opts):
    """Renderizado simple sin networkx (fallback extremo)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import math

    _setup_fonts()
    fig, ax = plt.subplots(figsize=(10, 8))
    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", []))

    if not nodes and not edges:
        ax.text(0.5, 0.5, f"Diagrama: {tipo}\n(sin datos)", ha='center', va='center',
                fontsize=16, transform=ax.transAxes)
    else:
        n = len(nodes) if nodes else 0
        positions = {}
        for i, node in enumerate(nodes if nodes else []):
            angle = 2 * math.pi * i / max(n, 1)
            x = 0.5 + 0.35 * math.cos(angle)
            y = 0.5 + 0.35 * math.sin(angle)
            label = node if isinstance(node, str) else node.get("label", node.get("id", ""))
            positions[label] = (x, y)
            ax.plot(x, y, 'o', markersize=25, color=PALETTE["primary"], alpha=0.8)
            ax.text(x, y, label, ha='center', va='center', fontsize=8,
                    fontweight='bold', color='white')

        for edge in edges if edges else []:
            if isinstance(edge, (list, tuple)) and len(edge) >= 2:
                src, dst = str(edge[0]), str(edge[1])
                if src in positions and dst in positions:
                    ax.annotate("", xy=positions[dst], xytext=positions[src],
                                arrowprops=dict(arrowstyle="->", color=PALETTE["secondary"], lw=1.5))

    if titulo:
        ax.set_title(titulo, fontsize=14, fontweight='bold')
    ax.axis('off')
    plt.tight_layout()

    dir_name = os.path.dirname(ruta)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    plt.savefig(ruta, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    size_kb = os.path.getsize(ruta) / 1024
    return f"Diagrama [{tipo}] creado (matplotlib-simple): {ruta} ({size_kb:.0f} KB)"


# ============================================================
# MERMAID CODE GENERATION — Professional Templates
# ============================================================

def _crear_mermaid(ruta, datos_str, titulo, opciones_str):
    """Genera codigo Mermaid y renderiza a imagen usando el pipeline completo."""
    datos = _parse_json(datos_str, {})

    code = datos.get("code", datos.get("codigo", ""))
    if not code:
        tipo = datos.get("tipo", "flowchart")
        code = _to_mermaid(tipo, datos_str, titulo)

    # Si la ruta es .md/.mermaid/.mmd, solo guardar codigo
    if ruta.endswith(('.md', '.mermaid', '.mmd')):
        dir_name = os.path.dirname(ruta)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(f"```mermaid\n{code}\n```\n")
        return f"Codigo Mermaid guardado: {ruta}"

    # Pipeline de renderizado
    result = _render_mermaid_cli(ruta, code)
    if result is not None:
        return result

    result = _render_playwright_css(ruta, "mermaid", datos, titulo, code)
    if result is not None:
        return result

    # Fallback: guardar como .md
    return _save_mermaid_md(ruta, code)


def _save_mermaid_md(ruta: str, mermaid_code: str) -> str:
    """Guarda codigo Mermaid como archivo .md (ultimo recurso)."""
    md_path = ruta.rsplit('.', 1)[0] + '.md'
    dir_name = os.path.dirname(md_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(f"```mermaid\n{mermaid_code}\n```\n")
    return (f"Renderizado no disponible. Codigo Mermaid guardado en: {md_path}\n"
            f"Instala: npm install -g @mermaid-js/mermaid-cli\n\n"
            f"Codigo generado:\n```\n{mermaid_code}\n```")


def _to_mermaid(tipo, datos_str, titulo=""):
    """Convierte datos JSON a codigo Mermaid profesional."""
    datos = _parse_json(datos_str, {})

    generators = {
        "flowchart": _mermaid_flowchart,
        "mindmap": _mermaid_mindmap,
        "tree": _mermaid_tree,
        "org": _mermaid_org,
        "architecture": _mermaid_architecture,
        "network": _mermaid_graph,
        "er": _mermaid_er,
        "class": _mermaid_class,
        "gantt": _mermaid_gantt,
        "sequence": _mermaid_sequence,
        "state": _mermaid_state,
        "swimlane": _mermaid_swimlane,
        "topology": _mermaid_topology,
        "knowledge_graph": _mermaid_knowledge_graph,
    }

    gen = generators.get(tipo, _mermaid_flowchart)
    code = gen(datos, titulo)
    return code


# ── Flowchart ─────────────────────────────────────────────

def _mermaid_flowchart(datos, titulo=""):
    """Genera Mermaid flowchart profesional."""
    direction = datos.get("direction", datos.get("direccion", "TD"))
    lines = [MERMAID_THEME_VARS, f"flowchart {direction}"]

    if titulo:
        lines.append(f"    %% {titulo}")

    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))

    # Styling classes
    lines.append("")
    lines.append("    classDef default fill:#4472C4,stroke:#264478,color:#fff,font-weight:bold")
    lines.append("    classDef decision fill:#ED7D31,stroke:#C55A11,color:#fff,font-weight:bold")
    lines.append("    classDef startEnd fill:#70AD47,stroke:#507E32,color:#fff,font-weight:bold")
    lines.append("    classDef error fill:#FF6B6B,stroke:#CC4444,color:#fff,font-weight:bold")
    lines.append("    classDef io fill:#5B9BD5,stroke:#2E75B6,color:#fff,font-weight:bold")
    lines.append("")

    # Nodos
    for node in nodes:
        if isinstance(node, str):
            safe_id = _mermaid_id(node)
            lines.append(f'    {safe_id}["{node}"]:::default')
        elif isinstance(node, dict):
            nid = _mermaid_id(node.get("id", node.get("nombre", "")))
            label = node.get("label", node.get("nombre", node.get("id", "")))
            shape = node.get("shape", "rect")
            style = node.get("style", "default")
            if shape == "diamond" or style == "decision":
                lines.append(f'    {nid}{{"{label}"}}:::decision')
            elif shape == "rounded" or style in ("start", "end", "startEnd"):
                lines.append(f'    {nid}(["{label}"]):::startEnd')
            elif shape == "circle":
                lines.append(f'    {nid}(("{label}")):::default')
            elif shape == "stadium":
                lines.append(f'    {nid}(["{label}"]):::startEnd')
            elif shape == "parallelogram" or style == "io":
                lines.append(f'    {nid}["{label}"]:::io')
            elif style == "error":
                lines.append(f'    {nid}["{label}"]:::error')
            else:
                lines.append(f'    {nid}["{label}"]:::default')

    # Aristas
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            src = _mermaid_id(str(edge[0]))
            dst = _mermaid_id(str(edge[1]))
            label = str(edge[2]) if len(edge) > 2 else ""
            style = edge[3] if len(edge) > 3 else ""
            if style == "dotted":
                arrow = f'-. "{label}" .->' if label else "-.->"
            elif style == "thick":
                arrow = f'== "{label}" ==>' if label else "==>"
            else:
                arrow = f'-->|"{label}"|' if label else "-->"
            lines.append(f"    {src} {arrow} {dst}")
        elif isinstance(edge, dict):
            src = _mermaid_id(edge.get("from", edge.get("source", "")))
            dst = _mermaid_id(edge.get("to", edge.get("target", "")))
            label = edge.get("label", edge.get("etiqueta", ""))
            style = edge.get("style", "")
            if style == "dotted":
                arrow = f'-. "{label}" .->' if label else "-.->"
            elif style == "thick":
                arrow = f'== "{label}" ==>' if label else "==>"
            else:
                arrow = f'-->|"{label}"|' if label else "-->"
            lines.append(f"    {src} {arrow} {dst}")

    # Jerarquia alternativa
    hierarchy = datos.get("hierarchy", datos.get("jerarquia", {}))
    if hierarchy and not nodes and not edges:
        _add_hierarchy_mermaid(lines, hierarchy, indent=4)

    return "\n".join(lines)


# ── Mindmap ───────────────────────────────────────────────

def _mermaid_mindmap(datos, titulo=""):
    """Genera Mermaid mindmap profesional."""
    lines = [MERMAID_THEME_VARS, "mindmap"]

    if titulo:
        lines.append(f"    %% {titulo}")

    hierarchy = datos.get("hierarchy", datos.get("jerarquia", {}))
    root = datos.get("root", datos.get("raiz", None))

    if hierarchy:
        _add_mindmap_mermaid(lines, hierarchy, indent=4)
    elif root:
        lines.append(f"  {root}")
        nodes = datos.get("nodes", datos.get("nodos", []))
        for node in nodes:
            label = node if isinstance(node, str) else node.get("label", node.get("id", ""))
            lines.append(f"    {label}")
    else:
        # Generar mindmap basico desde nodos y aristas
        nodes = datos.get("nodes", datos.get("nodos", []))
        edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))
        if nodes:
            root_node = nodes[0] if isinstance(nodes[0], str) else nodes[0].get("id", "Root")
            lines.append(f"  {root_node}")
            for node in nodes[1:]:
                label = node if isinstance(node, str) else node.get("label", node.get("id", ""))
                lines.append(f"    {label}")
        else:
            lines.append("  Root")

    return "\n".join(lines)


# ── Tree ──────────────────────────────────────────────────

def _mermaid_tree(datos, titulo=""):
    """Genera Mermaid tree diagram (flowchart TD con subgraphs)."""
    direction = datos.get("direction", "TD")
    lines = [MERMAID_THEME_VARS, f"flowchart {direction}"]

    if titulo:
        lines.append(f"    %% {titulo}")

    lines.append("")
    lines.append("    classDef treeNode fill:#4472C4,stroke:#264478,color:#fff,font-weight:bold")
    lines.append("    classDef leafNode fill:#5B9BD5,stroke:#2E75B6,color:#fff")
    lines.append("")

    hierarchy = datos.get("hierarchy", datos.get("jerarquia", {}))
    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))

    if hierarchy:
        _add_tree_mermaid(lines, hierarchy, indent=4, is_root=True)
    elif nodes or edges:
        # Construir desde nodos/aristas
        for node in nodes:
            if isinstance(node, str):
                safe_id = _mermaid_id(node)
                lines.append(f'    {safe_id}["{node}"]:::treeNode')
            elif isinstance(node, dict):
                nid = _mermaid_id(node.get("id", ""))
                label = node.get("label", nid)
                lines.append(f'    {nid}["{label}"]:::treeNode')

        for edge in edges:
            if isinstance(edge, (list, tuple)) and len(edge) >= 2:
                src = _mermaid_id(str(edge[0]))
                dst = _mermaid_id(str(edge[1]))
                lines.append(f"    {src} --> {dst}")
            elif isinstance(edge, dict):
                src = _mermaid_id(edge.get("from", ""))
                dst = _mermaid_id(edge.get("to", ""))
                lines.append(f"    {src} --> {dst}")
    else:
        lines.append('    root["Root"]:::treeNode')

    return "\n".join(lines)


# ── Org Chart ─────────────────────────────────────────────

def _mermaid_org(datos, titulo=""):
    """Genera Mermaid org chart profesional."""
    lines = [MERMAID_THEME_VARS, "flowchart TD"]

    if titulo:
        lines.append(f"    %% {titulo}")

    lines.append("")
    lines.append("    classDef ceo fill:#264478,stroke:#1a2e50,color:#fff,font-weight:bold")
    lines.append("    classDef vp fill:#4472C4,stroke:#264478,color:#fff,font-weight:bold")
    lines.append("    classDef manager fill:#5B9BD5,stroke:#2E75B6,color:#fff")
    lines.append("    classDef team fill:#ED7D31,stroke:#C55A11,color:#fff")
    lines.append("")

    hierarchy = datos.get("hierarchy", datos.get("jerarquia", {}))
    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))

    if hierarchy:
        _add_org_mermaid(lines, hierarchy, indent=4, level=0)
    elif nodes or edges:
        for node in nodes:
            if isinstance(node, str):
                safe_id = _mermaid_id(node)
                lines.append(f'    {safe_id}["{node}"]:::vp')
            elif isinstance(node, dict):
                nid = _mermaid_id(node.get("id", ""))
                label = node.get("label", nid)
                role = node.get("role", node.get("tipo", "vp"))
                lines.append(f'    {nid}["{label}"]:::{role}')

        for edge in edges:
            if isinstance(edge, (list, tuple)) and len(edge) >= 2:
                src = _mermaid_id(str(edge[0]))
                dst = _mermaid_id(str(edge[1]))
                lines.append(f"    {src} --> {dst}")
            elif isinstance(edge, dict):
                src = _mermaid_id(edge.get("from", ""))
                dst = _mermaid_id(edge.get("to", ""))
                lines.append(f"    {src} --> {dst}")
    else:
        lines.append('    ceo["CEO"]:::ceo')

    return "\n".join(lines)


# ── Architecture ──────────────────────────────────────────

def _mermaid_architecture(datos, titulo=""):
    """Genera Mermaid architecture diagram con subgraphs."""
    lines = [MERMAID_THEME_VARS, "flowchart LR"]

    if titulo:
        lines.append(f"    %% {titulo}")

    lines.append("")
    lines.append("    classDef service fill:#4472C4,stroke:#264478,color:#fff,font-weight:bold")
    lines.append("    classDef database fill:#ED7D31,stroke:#C55A11,color:#fff,font-weight:bold")
    lines.append("    classDef queue fill:#70AD47,stroke:#507E32,color:#fff,font-weight:bold")
    lines.append("    classDef external fill:#A5A5A5,stroke:#888888,color:#fff")
    lines.append("    classDef cache fill:#FFC000,stroke:#CC9900,color:#333")
    lines.append("    classDef client fill:#9B59B6,stroke:#7D3C98,color:#fff")
    lines.append("")

    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))

    # Group nodes by type/layer
    layers = datos.get("layers", datos.get("capas", {}))
    if layers:
        for layer_name, layer_nodes in layers.items():
            lines.append(f"    subgraph {layer_name}")
            for node in layer_nodes:
                if isinstance(node, str):
                    safe_id = _mermaid_id(node)
                    lines.append(f'        {safe_id}["{node}"]:::service')
                elif isinstance(node, dict):
                    nid = _mermaid_id(node.get("id", ""))
                    label = node.get("label", nid)
                    ntype = node.get("type", "service")
                    lines.append(f'        {nid}["{label}"]:::{ntype}')
            lines.append("    end")
    elif nodes:
        for node in nodes:
            if isinstance(node, str):
                safe_id = _mermaid_id(node)
                lines.append(f'    {safe_id}["{node}"]:::service')
            elif isinstance(node, dict):
                nid = _mermaid_id(node.get("id", ""))
                label = node.get("label", nid)
                ntype = node.get("type", "service")
                lines.append(f'    {nid}["{label}"]:::{ntype}')

    # Aristas
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            src = _mermaid_id(str(edge[0]))
            dst = _mermaid_id(str(edge[1]))
            label = str(edge[2]) if len(edge) > 2 else ""
            style = edge[3] if len(edge) > 3 else ""
            if style == "dashed":
                arrow = f'-. "{label}" .->' if label else "-.->"
            elif style == "bidirectional":
                arrow = f'<-->|"{label}"|' if label else "<-->"
            else:
                arrow = f'-->|"{label}"|' if label else "-->"
            lines.append(f"    {src} {arrow} {dst}")
        elif isinstance(edge, dict):
            src = _mermaid_id(edge.get("from", ""))
            dst = _mermaid_id(edge.get("to", ""))
            label = edge.get("label", "")
            style = edge.get("style", "")
            if style == "dashed":
                arrow = f'-. "{label}" .->' if label else "-.->"
            elif style == "bidirectional":
                arrow = f'<-->|"{label}"|' if label else "<-->"
            else:
                arrow = f'-->|"{label}"|' if label else "-->"
            lines.append(f"    {src} {arrow} {dst}")

    return "\n".join(lines)


# ── Graph (Network) ───────────────────────────────────────

def _mermaid_graph(datos, titulo=""):
    """Genera Mermaid graph (no dirigido) profesional."""
    lines = [MERMAID_THEME_VARS, "graph LR"]

    if titulo:
        lines.append(f"    %% {titulo}")

    lines.append("")
    lines.append("    classDef nodeA fill:#4472C4,stroke:#264478,color:#fff,font-weight:bold")
    lines.append("    classDef nodeB fill:#ED7D31,stroke:#C55A11,color:#fff,font-weight:bold")
    lines.append("    classDef nodeC fill:#70AD47,stroke:#507E32,color:#fff,font-weight:bold")
    lines.append("")

    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))

    # Recoger nodos desde aristas si no hay explicitos
    node_ids = set()
    for node in nodes:
        if isinstance(node, str):
            node_ids.add(node)
        elif isinstance(node, dict):
            node_ids.add(node.get("id", ""))

    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            node_ids.add(str(edge[0]))
            node_ids.add(str(edge[1]))
        elif isinstance(edge, dict):
            node_ids.add(edge.get("from", ""))
            node_ids.add(edge.get("to", ""))

    # Declarar nodos
    style_cycle = ["nodeA", "nodeB", "nodeC"]
    for i, nid in enumerate(sorted(node_ids)):
        safe = _mermaid_id(nid)
        style = style_cycle[i % len(style_cycle)]
        lines.append(f'    {safe}["{nid}"]:::{style}')

    # Aristas
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            src = _mermaid_id(str(edge[0]))
            dst = _mermaid_id(str(edge[1]))
            label = str(edge[2]) if len(edge) > 2 else ""
            link = f'---|"{label}"|' if label else "---"
            lines.append(f"    {src} {link} {dst}")
        elif isinstance(edge, dict):
            src = _mermaid_id(edge.get("from", ""))
            dst = _mermaid_id(edge.get("to", ""))
            label = edge.get("label", "")
            link = f'---|"{label}"|' if label else "---"
            lines.append(f"    {src} {link} {dst}")

    return "\n".join(lines)


# ── ER Diagram ────────────────────────────────────────────

def _mermaid_er(datos, titulo=""):
    """Genera Mermaid ER diagram profesional."""
    lines = [MERMAID_THEME_VARS, "erDiagram"]

    if titulo:
        lines.append(f"    %% {titulo}")

    entities = datos.get("entities", datos.get("entidades", []))
    relationships = datos.get("relationships", datos.get("relaciones", []))

    for entity in entities:
        if isinstance(entity, dict):
            name = entity.get("name", entity.get("nombre", ""))
            attrs = entity.get("attributes", entity.get("atributos", []))
            lines.append(f"    {name} {{")
            for attr in attrs:
                if isinstance(attr, str):
                    lines.append(f"        string {attr}")
                elif isinstance(attr, dict):
                    atype = attr.get("type", "string")
                    aname = attr.get("name", "")
                    pk = " PK" if attr.get("pk", attr.get("primary_key", False)) else ""
                    fk = " FK" if attr.get("fk", attr.get("foreign_key", False)) else ""
                    uk = " UK" if attr.get("uk", attr.get("unique", False)) else ""
                    lines.append(f"        {atype} {aname}{pk}{fk}{uk}")
            lines.append(f"    }}")

    for rel in relationships:
        if isinstance(rel, dict):
            e1 = rel.get("from", rel.get("entity1", ""))
            e2 = rel.get("to", rel.get("entity2", ""))
            label = rel.get("label", rel.get("nombre", ""))
            card1 = rel.get("cardinality1", rel.get("card1", "||"))
            card2 = rel.get("cardinality2", rel.get("card2", "o{"))
            lines.append(f'    {e1} {card1}--{card2} {e2} : "{label}"')

    if not entities and not relationships:
        lines.append("    EMPTY_ENTITY {")
        lines.append("        string id PK")
        lines.append("    }")

    return "\n".join(lines)


# ── Class Diagram ─────────────────────────────────────────

def _mermaid_class(datos, titulo=""):
    """Genera Mermaid class diagram profesional."""
    lines = [MERMAID_THEME_VARS, "classDiagram"]

    if titulo:
        lines.append(f"    %% {titulo}")

    classes = datos.get("classes", datos.get("clases", []))
    for cls in classes:
        name = cls.get("name", cls.get("nombre", ""))
        attrs = cls.get("attributes", cls.get("atributos", []))
        methods = cls.get("methods", cls.get("metodos", []))
        stereotype = cls.get("stereotype", cls.get("estereotipo", ""))

        if stereotype:
            lines.append(f"    class {name} {{")
            lines.append(f"        <<{stereotype}>>")
        else:
            lines.append(f"    class {name} {{")

        for attr in attrs:
            if isinstance(attr, str):
                vis = "+" if not attr.startswith("-") and not attr.startswith("#") else ""
                lines.append(f"        {vis}{attr}")
            elif isinstance(attr, dict):
                vis = attr.get("visibility", "+")
                atype = attr.get("type", "string")
                aname = attr.get("name", "")
                lines.append(f"        {vis}{atype} {aname}")

        for method in methods:
            if isinstance(method, str):
                lines.append(f"        {method}")
            elif isinstance(method, dict):
                vis = method.get("visibility", "+")
                ret = method.get("return", "void")
                mname = method.get("name", "")
                params = method.get("params", "()")
                lines.append(f"        {vis}{mname}{params} {ret}")

        lines.append(f"    }}")

    # Relaciones
    relationships = datos.get("relationships", datos.get("relaciones", []))
    for rel in relationships:
        if isinstance(rel, dict):
            e1 = rel.get("from", "")
            e2 = rel.get("to", "")
            rtype = rel.get("type", "-->")
            label = rel.get("label", "")
            if label:
                lines.append(f'    {e1} {rtype} {e2} : "{label}"')
            else:
                lines.append(f"    {e1} {rtype} {e2}")

    if not classes and not relationships:
        lines.append("    class EmptyClass {")
        lines.append("        +String id")
        lines.append("    }")

    return "\n".join(lines)


# ── Gantt ─────────────────────────────────────────────────

def _mermaid_gantt(datos, titulo=""):
    """Genera Mermaid Gantt chart profesional."""
    lines = ["gantt"]

    if titulo:
        lines.append(f"    title {titulo}")

    date_format = datos.get("dateFormat", "YYYY-MM-DD")
    lines.append(f"    dateFormat {date_format}")
    axis_format = datos.get("axisFormat", "%Y-%m")
    lines.append(f"    axisFormat {axis_format}")

    tasks = datos.get("tasks", datos.get("tareas", []))
    sections = {}

    for task in tasks:
        section = task.get("section", "General")
        name = task.get("nombre", task.get("name", ""))
        start = task.get("inicio", task.get("start", ""))
        duration = task.get("duracion", task.get("duration", "1d"))
        status = task.get("status", "")
        task_id = task.get("id", task.get("codigo", f"task{len(sections)}"))

        if section not in sections:
            sections[section] = []

        status_prefix = ""
        if status == "active":
            status_prefix = "active "
        elif status == "done":
            status_prefix = "done "
        elif status == "crit":
            status_prefix = "crit "
        elif status == "milestone":
            status_prefix = "milestone "

        safe_id = _mermaid_id(task_id)
        sections[section].append(f"{status_prefix}{safe_id} : {name}, {start}, {duration}")

    for section, task_lines in sections.items():
        lines.append(f"    section {section}")
        for tl in task_lines:
            lines.append(f"    {tl}")

    if not tasks:
        lines.append("    section Plan")
        lines.append("    Sin datos : a1, 2024-01-01, 1d")

    return "\n".join(lines)


# ── Sequence Diagram ──────────────────────────────────────

def _mermaid_sequence(datos, titulo=""):
    """Genera Mermaid sequence diagram profesional."""
    lines = [MERMAID_THEME_VARS, "sequenceDiagram"]

    if titulo:
        lines.append(f"    title {titulo}")

    participants = datos.get("participants", datos.get("participantes", []))
    for p in participants:
        if isinstance(p, str):
            lines.append(f"    participant {p}")
        elif isinstance(p, dict):
            name = p.get("name", p.get("nombre", ""))
            alias = p.get("alias", "")
            color = p.get("color", "")
            if alias:
                lines.append(f"    participant {alias} as {name}")
            else:
                lines.append(f"    participant {name}")

    messages = datos.get("messages", datos.get("mensajes", []))
    for msg in messages:
        src = msg.get("from", msg.get("desde", ""))
        dst = msg.get("to", msg.get("hasta", ""))
        text = msg.get("text", msg.get("texto", ""))
        mtype = msg.get("type", "")
        activate = msg.get("activate", False)

        if mtype == "dashed" or mtype == "return":
            arrow = "-->>"
        elif mtype == "solid" or mtype == "call":
            arrow = "->>"
        elif mtype == "self":
            lines.append(f"    {src}->>{src}: {text}")
            continue
        else:
            arrow = "->>"

        line = f"    {src}{arrow}{dst}: {text}"
        lines.append(line)

        if activate:
            lines.append(f"    activate {dst}")

        # Notas
        note_pos = msg.get("note_position", "")
        note_text = msg.get("note", "")
        if note_text and note_pos:
            lines.append(f"    Note {note_pos} of {dst}: {note_text}")
        elif note_text:
            lines.append(f"    Note right of {dst}: {note_text}")

    # Alt/Opt/Loop blocks
    blocks = datos.get("blocks", datos.get("bloques", []))
    for block in blocks:
        btype = block.get("type", "alt")
        condition = block.get("condition", block.get("condicion", ""))
        bmessages = block.get("messages", [])
        else_condition = block.get("else", block.get("sino", None))

        lines.append(f"    {btype} {condition}")
        for bmsg in bmessages:
            bsrc = bmsg.get("from", "")
            bdst = bmsg.get("to", "")
            btext = bmsg.get("text", "")
            lines.append(f"        {bsrc}->>{bdst}: {btext}")
        if else_condition:
            lines.append(f"    else {else_condition}")
            else_msgs = block.get("else_messages", [])
            for bmsg in else_msgs:
                bsrc = bmsg.get("from", "")
                bdst = bmsg.get("to", "")
                btext = bmsg.get("text", "")
                lines.append(f"        {bsrc}->>{bdst}: {btext}")
        lines.append("    end")

    return "\n".join(lines)


# ── State Diagram ─────────────────────────────────────────

def _mermaid_state(datos, titulo=""):
    """Genera Mermaid state diagram profesional."""
    lines = [MERMAID_THEME_VARS, "stateDiagram-v2"]

    if titulo:
        lines.append(f"    %% {titulo}")

    states = datos.get("states", datos.get("estados", []))
    transitions = datos.get("transitions", datos.get("transiciones", []))

    for state in states:
        if isinstance(state, str):
            lines.append(f"    state {state}")
        elif isinstance(state, dict):
            name = state.get("name", "")
            stype = state.get("type", "")
            if stype == "composite" or stype == "compuesto":
                children = state.get("children", state.get("hijos", []))
                lines.append(f"    state {name} {{")
                for child in children:
                    if isinstance(child, str):
                        lines.append(f"        {child}")
                    elif isinstance(child, dict):
                        lines.append(f"        {child.get('name', '')}")
                lines.append("    }")
            elif stype == "fork":
                lines.append(f"    state {name} <<fork>>")
            elif stype == "join":
                lines.append(f"    state {name} <<join>>")
            elif stype == "choice":
                lines.append(f"    state {name} <<choice>>")
            else:
                desc = state.get("description", state.get("descripcion", ""))
                if desc:
                    lines.append(f'    state "{name}" as {name} {{')
                    lines.append(f'        {desc}')
                    lines.append(f'    }}')
                else:
                    lines.append(f"    state {name}")

    for trans in transitions:
        if isinstance(trans, dict):
            src = trans.get("from", "")
            dst = trans.get("to", "")
            label = trans.get("label", trans.get("evento", ""))
            if label:
                lines.append(f"    {src} --> {dst} : {label}")
            else:
                lines.append(f"    {src} --> {dst}")

    # Notas en estados
    notes = datos.get("notes", datos.get("notas", []))
    for note in notes:
        target = note.get("state", note.get("estado", ""))
        text = note.get("text", note.get("texto", ""))
        position = note.get("position", "right")
        lines.append(f"    note {position} of {target}: {text}")

    if not states and not transitions:
        lines.append("    [*] --> Idle")
        lines.append("    Idle --> Active : start")
        lines.append("    Active --> [*] : stop")

    return "\n".join(lines)


# ── Swimlane (Mermaid) ───────────────────────────────────

def _mermaid_swimlane(datos, titulo=""):
    """Genera Mermaid flowchart con subgraphs para simular swimlane."""
    lines = [MERMAID_THEME_VARS, "flowchart LR"]

    if titulo:
        lines.append(f"    %% {titulo}")

    lanes = datos.get("lanes", datos.get("carriles", []))
    steps = datos.get("steps", datos.get("pasos", []))

    if not lanes:
        lanes = ["Lane 1", "Lane 2"]

    # Colores para cada lane
    lane_colors = {
        0: "fill:#4472C4,stroke:#264478,color:#fff",
        1: "fill:#ED7D31,stroke:#C55A11,color:#fff",
        2: "fill:#70AD47,stroke:#507E32,color:#fff",
        3: "fill:#FFC000,stroke:#CC9900,color:#333",
        4: "fill:#9B59B6,stroke:#7D3C98,color:#fff",
    }

    # Crear subgraphs para cada lane
    for i, lane in enumerate(lanes):
        safe_lane = _mermaid_id(lane)
        lines.append(f"    subgraph {safe_lane}")
        lines.append(f'        direction LR')
        steps_in_lane = [s for s in steps
                         if s.get("lane", s.get("carril", lanes[0])) == lane]
        for j, step in enumerate(steps_in_lane):
            text = step.get("texto", step.get("text", f"Paso {j+1}"))
            step_id = f"{safe_lane}_s{j}"
            lines.append(f'        {step_id}["{text}"]')
        if not steps_in_lane:
            lines.append(f'        {safe_lane}_empty[" "]')
        lines.append("    end")
        # Style
        style_str = lane_colors.get(i, lane_colors[0])
        lines.append(f"    style {safe_lane} {style_str}")

    # Conectar pasos entre lanes
    for i, step in enumerate(steps):
        if i > 0:
            prev_step = steps[i - 1]
            prev_lane = prev_step.get("lane", prev_step.get("carril", lanes[0]))
            curr_lane = step.get("lane", step.get("carril", lanes[0]))
            prev_lane_idx = lanes.index(prev_lane) if prev_lane in lanes else 0
            curr_lane_idx = lanes.index(curr_lane) if curr_lane in lanes else 0
            prev_safe = _mermaid_id(prev_lane)
            curr_safe = _mermaid_id(curr_lane)

            # Encontrar step index within lane
            prev_steps_in_lane = [s for s in steps[:i]
                                   if s.get("lane", s.get("carril", lanes[0])) == prev_lane]
            curr_steps_in_lane = [s for s in steps[:i + 1]
                                   if s.get("lane", s.get("carril", lanes[0])) == curr_lane]
            prev_step_id = f"{prev_safe}_s{len(prev_steps_in_lane) - 1}"
            curr_step_id = f"{curr_safe}_s{len(curr_steps_in_lane) - 1}"
            lines.append(f"    {prev_step_id} --> {curr_step_id}")

    return "\n".join(lines)


# ── Topology ──────────────────────────────────────────────

def _mermaid_topology(datos, titulo=""):
    """Genera Mermaid topology/route diagram."""
    lines = [MERMAID_THEME_VARS, "flowchart LR"]

    if titulo:
        lines.append(f"    %% {titulo}")

    lines.append("")
    lines.append("    classDef node fill:#5B9BD5,stroke:#2E75B6,color:#fff,font-weight:bold")
    lines.append("    classDef hub fill:#4472C4,stroke:#264478,color:#fff,font-weight:bold")
    lines.append("    classDef endpoint fill:#70AD47,stroke:#507E32,color:#fff")
    lines.append("")

    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))

    for node in nodes:
        if isinstance(node, str):
            safe_id = _mermaid_id(node)
            lines.append(f'    {safe_id}["{node}"]:::node')
        elif isinstance(node, dict):
            nid = _mermaid_id(node.get("id", ""))
            label = node.get("label", nid)
            ntype = node.get("type", "node")
            lines.append(f'    {nid}["{label}"]:::{ntype}')

    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            src = _mermaid_id(str(edge[0]))
            dst = _mermaid_id(str(edge[1]))
            label = str(edge[2]) if len(edge) > 2 else ""
            weight = edge[3] if len(edge) > 3 else ""
            style = "thick" if weight == "high" else ""
            if style == "thick":
                arrow = f'== "{label}" ==>' if label else "==>"
            else:
                arrow = f'-->|"{label}"|' if label else "-->"
            lines.append(f"    {src} {arrow} {dst}")
        elif isinstance(edge, dict):
            src = _mermaid_id(edge.get("from", ""))
            dst = _mermaid_id(edge.get("to", ""))
            label = edge.get("label", "")
            weight = edge.get("weight", "")
            style = "thick" if weight == "high" else ""
            if style == "thick":
                arrow = f'== "{label}" ==>' if label else "==>"
            else:
                arrow = f'-->|"{label}"|' if label else "-->"
            lines.append(f"    {src} {arrow} {dst}")

    if not nodes and not edges:
        lines.append('    a["Node A"]:::node')
        lines.append('    b["Node B"]:::node')
        lines.append("    a --> b")

    return "\n".join(lines)


# ── Knowledge Graph ───────────────────────────────────────

def _mermaid_knowledge_graph(datos, titulo=""):
    """Genera Mermaid knowledge graph con estilos por tipo de entidad."""
    lines = [MERMAID_THEME_VARS, "graph TD"]

    if titulo:
        lines.append(f"    %% {titulo}")

    lines.append("")
    lines.append("    classDef concept fill:#4472C4,stroke:#264478,color:#fff,font-weight:bold")
    lines.append("    classDef person fill:#ED7D31,stroke:#C55A11,color:#fff,font-weight:bold")
    lines.append("    classDef event fill:#70AD47,stroke:#507E32,color:#fff,font-weight:bold")
    lines.append("    classDef location fill:#9B59B6,stroke:#7D3C98,color:#fff,font-weight:bold")
    lines.append("    classDef resource fill:#FFC000,stroke:#CC9900,color:#333")
    lines.append("")

    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))

    # Nodos
    for node in nodes:
        if isinstance(node, str):
            safe_id = _mermaid_id(node)
            lines.append(f'    {safe_id}["{node}"]:::concept')
        elif isinstance(node, dict):
            nid = _mermaid_id(node.get("id", ""))
            label = node.get("label", nid)
            ntype = node.get("type", "concept")
            lines.append(f'    {nid}["{label}"]:::{ntype}')

    # Aristas con etiquetas de relacion
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            src = _mermaid_id(str(edge[0]))
            dst = _mermaid_id(str(edge[1]))
            label = str(edge[2]) if len(edge) > 2 else ""
            arrow = f'-->|"{label}"|' if label else "-->"
            lines.append(f"    {src} {arrow} {dst}")
        elif isinstance(edge, dict):
            src = _mermaid_id(edge.get("from", ""))
            dst = _mermaid_id(edge.get("to", ""))
            label = edge.get("label", edge.get("relacion", ""))
            arrow = f'-->|"{label}"|' if label else "-->"
            lines.append(f"    {src} {arrow} {dst}")

    if not nodes and not edges:
        lines.append('    a["Concept A"]:::concept')
        lines.append('    b["Concept B"]:::concept')
        lines.append('    a -->|"related to"| b')

    return "\n".join(lines)


# ============================================================
# MERMAID HELPER FUNCTIONS
# ============================================================

def _add_hierarchy_mermaid(lines, data, indent=4):
    """Agrega jerarquia a codigo Mermaid flowchart."""
    spaces = " " * indent
    if isinstance(data, dict):
        for key, children in data.items():
            safe_key = _mermaid_id(key)
            lines.append(f'{spaces}{safe_key}["{key}"]:::default')
            if isinstance(children, dict):
                for child_key in children:
                    safe_child = _mermaid_id(child_key)
                    lines.append(f"{spaces}{safe_key} --> {safe_child}")
                _add_hierarchy_mermaid(lines, children, indent)
            elif isinstance(children, list):
                for child in children:
                    if isinstance(child, str):
                        safe_child = _mermaid_id(child)
                        lines.append(f'{spaces}{safe_child}["{child}"]:::default')
                        lines.append(f"{spaces}{safe_key} --> {safe_child}")


def _add_mindmap_mermaid(lines, data, indent=4):
    """Agrega estructura de mindmap a codigo Mermaid."""
    spaces = " " * indent
    if isinstance(data, dict):
        for key, children in data.items():
            lines.append(f"{spaces}{key}")
            if isinstance(children, dict):
                _add_mindmap_mermaid(lines, children, indent + 2)
            elif isinstance(children, list):
                for child in children:
                    if isinstance(child, str):
                        lines.append(f"{spaces}  {child}")
                    elif isinstance(child, dict):
                        _add_mindmap_mermaid(lines, child, indent + 2)


def _add_tree_mermaid(lines, data, indent=4, is_root=False):
    """Agrega estructura de arbol a codigo Mermaid."""
    spaces = " " * indent
    if isinstance(data, dict):
        for key, children in data.items():
            safe_key = _mermaid_id(key)
            style = "treeNode" if is_root else "leafNode"
            lines.append(f'{spaces}{safe_key}["{key}"]:::{style}')
            if isinstance(children, dict):
                for child_key, child_val in children.items():
                    safe_child = _mermaid_id(child_key)
                    lines.append(f"{spaces}{safe_key} --> {safe_child}")
                    if isinstance(child_val, (dict, list)) and child_val:
                        _add_tree_mermaid(lines, {child_key: child_val}, indent, is_root=False)
            elif isinstance(children, list):
                for child in children:
                    if isinstance(child, str):
                        safe_child = _mermaid_id(child)
                        lines.append(f'{spaces}{safe_child}["{child}"]:::leafNode')
                        lines.append(f"{spaces}{safe_key} --> {safe_child}")
                    elif isinstance(child, dict):
                        _add_tree_mermaid(lines, child, indent, is_root=False)
                        for ck in child:
                            safe_child = _mermaid_id(ck)
                            lines.append(f"{spaces}{safe_key} --> {safe_child}")


def _add_org_mermaid(lines, data, indent=4, level=0):
    """Agrega estructura organigrama a codigo Mermaid."""
    spaces = " " * indent
    styles = ["ceo", "vp", "manager", "team", "team"]
    if isinstance(data, dict):
        for key, children in data.items():
            safe_key = _mermaid_id(key)
            style = styles[min(level, len(styles) - 1)]
            lines.append(f'{spaces}{safe_key}["{key}"]:::{style}')
            if isinstance(children, dict):
                for child_key in children:
                    safe_child = _mermaid_id(child_key)
                    lines.append(f"{spaces}{safe_key} --> {safe_child}")
                _add_org_mermaid(lines, children, indent, level + 1)
            elif isinstance(children, list):
                for child in children:
                    if isinstance(child, str):
                        safe_child = _mermaid_id(child)
                        child_style = styles[min(level + 1, len(styles) - 1)]
                        lines.append(f'{spaces}{safe_child}["{child}"]:::{child_style}')
                        lines.append(f"{spaces}{safe_key} --> {safe_child}")


def _mermaid_id(text: str) -> str:
    """Convierte texto a ID valido para Mermaid."""
    if not text:
        return "node"
    safe = re.sub(r'[^a-zA-Z0-9_]', '_', str(text))
    # Eliminar underscores multiples
    safe = re.sub(r'_+', '_', safe)
    safe = safe.strip('_')
    if safe and safe[0].isdigit():
        safe = "n" + safe
    return safe or "node"


# ============================================================
# HTML/CSS HELPER FUNCTIONS
# ============================================================

def _esc(text: str) -> str:
    """Escape HTML special characters."""
    if not text:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def _build_hierarchy_from_edges(nodes, edges):
    """Construye una estructura jerarquica desde nodos y aristas."""
    children_map = {}
    all_nodes = set()
    child_nodes = set()

    for node in nodes:
        if isinstance(node, str):
            all_nodes.add(node)
        elif isinstance(node, dict):
            nid = node.get("id", node.get("nombre", ""))
            all_nodes.add(nid)

    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            src, dst = str(edge[0]), str(edge[1])
            all_nodes.add(src)
            all_nodes.add(dst)
            child_nodes.add(dst)
            children_map.setdefault(src, []).append(dst)
        elif isinstance(edge, dict):
            src = edge.get("from", edge.get("source", ""))
            dst = edge.get("to", edge.get("target", ""))
            all_nodes.add(src)
            all_nodes.add(dst)
            child_nodes.add(dst)
            children_map.setdefault(src, []).append(dst)

    # Find root(s) — nodes that are not children
    roots = all_nodes - child_nodes
    if not roots:
        roots = {next(iter(all_nodes))} if all_nodes else {"Root"}

    def build_tree(node):
        result = {}
        for child in children_map.get(node, []):
            result[child] = build_tree(child)
        return result if result else []

    hierarchy = {}
    for root in roots:
        hierarchy[root] = build_tree(root)

    return hierarchy


# ============================================================
# MATPLOTLIB UTILITY FUNCTIONS
# ============================================================

def _setup_fonts():
    """Configura fuentes para soporte Unicode."""
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt
    try:
        fm.fontManager.addfont('/usr/share/fonts/truetype/chinese/NotoSansSC[wght].ttf')
    except Exception:
        pass
    try:
        fm.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    except Exception:
        pass
    plt.rcParams['font.sans-serif'] = ['Noto Sans SC', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False


def _parse_json(s, default=None):
    """Parsea JSON de forma segura."""
    if not s or s in ("{}", "[]", ""):
        return default if default is not None else {}
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


def _has_graphviz():
    """Verifica si graphviz esta instalado."""
    try:
        result = subprocess.run(["dot", "-V"], capture_output=True, timeout=3)
        return result.returncode == 0
    except Exception:
        return False


def _hierarchy_pos(G, root=None, width=1., vert_gap=0.2, vert_loc=0, xcenter=0.5):
    """Calcula posiciones jerarquicas para un grafo sin graphviz."""
    import networkx as nx

    if root is None:
        roots = ([n for n in G.nodes() if G.in_degree(n) == 0]
                 if G.is_directed() else [list(G.nodes())[0]])
        root = roots[0] if roots else list(G.nodes())[0]

    pos = {root: (xcenter, vert_loc)}
    children = (list(G.successors(root)) if G.is_directed()
                else list(G.neighbors(root)))

    if children:
        dx = width / len(children)
        nextx = xcenter - width / 2 - dx / 2
        for child in children:
            nextx += dx
            pos.update(_hierarchy_pos(G, root=child, width=dx, vert_gap=vert_gap,
                                       vert_loc=vert_loc - vert_gap, xcenter=nextx))
    return pos
