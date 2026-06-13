"""
=============================================================
AGENTE v15 - Herramientas de Diagramas
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

Renderizado: matplotlib + networkx / graphviz / Mermaid CLI
=============================================================
"""

import os
import json
import logging
from config import REPOS_DIR, logger
from utils.security import validate_path


# ============================================================
# DIAPOSITIVO PRINCIPAL - CREAR DIAGRAMA
# ============================================================

SUPPORTED_DIAGRAM_TYPES = [
    "flowchart", "mindmap", "tree", "org", "architecture",
    "network", "er", "class", "gantt", "swimlane", "sequence",
    "topology", "knowledge_graph", "mermaid",
]


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
    }
    tipo = aliases.get(tipo, tipo)

    if tipo not in SUPPORTED_DIAGRAM_TYPES:
        return (f"ERROR: Tipo '{tipo}' no soportado. "
                f"Usar: {', '.join(SUPPORTED_DIAGRAM_TYPES)}")

    # Si es Mermaid, generar codigo y opcionalmente renderizar
    if tipo == "mermaid":
        return _crear_mermaid(ruta, datos, titulo, opciones)

    # Intentar renderizar con matplotlib/graphviz
    try:
        return _render_diagram(ruta, tipo, datos, titulo, opciones)
    except Exception as e:
        logger.debug(f"Renderizado grafico fallo: {e}")
        # Fallback: generar Mermaid y renderizar
        try:
            mermaid_code = _to_mermaid(tipo, datos, titulo)
            return _crear_mermaid(ruta, json.dumps({"code": mermaid_code}), titulo, opciones)
        except Exception as e2:
            return f"ERROR creando diagrama: {e}. Fallback Mermaid tambien fallo: {e2}"


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
    }
    tipo = aliases.get(tipo, tipo)

    try:
        return _to_mermaid(tipo, datos, titulo)
    except Exception as e:
        return f"ERROR generando Mermaid: {e}"


# ============================================================
# RENDERIZADO DE DIAGRAMAS
# ============================================================

def _render_diagram(ruta, tipo, datos_str, titulo, opciones_str):
    """Renderiza un diagrama usando matplotlib + networkx."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import numpy as np

    _setup_fonts()

    datos = _parse_json(datos_str, {})
    opts = _parse_json(opciones_str, {})

    fig_width = opts.get("fig_width", 12)
    fig_height = opts.get("fig_height", 8)

    if tipo == "gantt":
        return _render_gantt(ruta, datos, titulo, opts)

    if tipo == "sequence":
        return _render_sequence(ruta, datos, titulo, opts)

    if tipo == "swimlane":
        return _render_swimlane(ruta, datos, titulo, opts)

    # Para grafos: usar networkx si esta disponible
    try:
        return _render_graph(ruta, tipo, datos, titulo, opts)
    except ImportError:
        # Fallback sin networkx
        return _render_simple(ruta, tipo, datos, titulo, opts)


def _render_graph(ruta, tipo, datos, titulo, opts):
    """Renderiza diagramas de grafo usando networkx + matplotlib."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import networkx as nx
    import numpy as np

    _setup_fonts()

    # Construir grafo desde datos
    G = _build_graph(tipo, datos)

    fig, ax = plt.subplots(figsize=(opts.get("fig_width", 12),
                                     opts.get("fig_height", 8)))

    # Layout segun tipo
    if tipo == "tree" or tipo == "org":
        pos = nx.drawing.nx_agraph.graphviz_layout(G, prog='dot') if _has_graphviz() \
              else _hierarchy_pos(G)
    elif tipo == "mindmap":
        pos = nx.drawing.nx_agraph.graphviz_layout(G, prog='twopi') if _has_graphviz() \
              else nx.spring_layout(G, k=2, iterations=50)
    elif tipo == "architecture" or tipo == "topology":
        pos = nx.drawing.nx_agraph.graphviz_layout(G, prog='fdp') if _has_graphviz() \
              else nx.spring_layout(G, k=1.5, iterations=50)
    elif tipo == "network" or tipo == "knowledge_graph":
        pos = nx.spring_layout(G, k=1.5, iterations=50, seed=42)
    elif tipo == "er":
        pos = nx.circular_layout(G)
    elif tipo == "class":
        pos = nx.drawing.nx_agraph.graphviz_layout(G, prog='dot') if _has_graphviz() \
              else nx.spring_layout(G, k=2, iterations=50)
    else:
        pos = nx.spring_layout(G, seed=42)

    # Colores y estilos por tipo
    node_colors = opts.get("node_colors", None)
    edge_colors = opts.get("edge_colors", "#888888")

    # Dibujar nodos
    node_size = opts.get("node_size", 1500)
    node_color = node_colors or PALETTE["primary"]

    labels = nx.get_node_attributes(G, 'label')
    if not labels:
        labels = {n: str(n) for n in G.nodes()}

    # Escalar fontsize segun longitud del label
    max_label_len = max(len(str(l)) for l in labels.values()) if labels else 1
    font_size = max(6, min(10, 14 - max_label_len))

    nx.draw_networkx_nodes(G, pos, ax=ax, node_size=node_size,
                           node_color=node_color, alpha=0.8)
    nx.draw_networkx_labels(G, pos, labels, ax=ax, font_size=font_size,
                            font_color='white', font_weight='bold')

    # Dibujar aristas
    edge_labels = nx.get_edge_attributes(G, 'label')
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color=edge_colors,
                           arrows=True, arrowsize=15,
                           connectionstyle='arc3,rad=0.1')
    if edge_labels:
        nx.draw_networkx_edge_labels(G, pos, edge_labels, ax=ax,
                                      font_size=7, font_color='#555555')

    # Titulo
    if titulo:
        ax.set_title(titulo, fontsize=14, fontweight='bold', pad=15)

    ax.axis('off')
    plt.tight_layout()

    # Guardar
    dir_name = os.path.dirname(ruta)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    plt.savefig(ruta, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    size_kb = os.path.getsize(ruta) / 1024
    return f"Diagrama [{tipo}] creado: {ruta} ({size_kb:.0f} KB, {G.number_of_nodes()} nodos, {G.number_of_edges()} aristas)"


def _build_graph(tipo, datos):
    """Construye un grafo networkx desde los datos JSON."""
    import networkx as nx

    G = nx.DiGraph() if tipo in ("tree", "org", "flowchart", "class", "sequence") else nx.Graph()

    # Nodos
    nodes = datos.get("nodes", datos.get("nodos", []))
    for node in nodes:
        if isinstance(node, str):
            G.add_node(node, label=node)
        elif isinstance(node, dict):
            nid = node.get("id", node.get("nombre", ""))
            label = node.get("label", node.get("nombre", node.get("name", nid)))
            G.add_node(nid, label=label, **{k: v for k, v in node.items()
                                            if k not in ("id", "label", "nombre", "name")})

    # Aristas
    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            G.add_edge(edge[0], edge[1], label=str(edge[2]) if len(edge) > 2 else "")
        elif isinstance(edge, dict):
            src = edge.get("from", edge.get("source", edge.get("desde", "")))
            dst = edge.get("to", edge.get("target", edge.get("hasta", "")))
            label = edge.get("label", edge.get("etiqueta", ""))
            G.add_edge(src, dst, label=label)

    # Si no hay nodos explicitos, generar desde aristas
    if not nodes and not edges:
        # Intentar formato simple: jerarquia
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


def _render_gantt(ruta, datos, titulo, opts):
    """Renderiza un diagrama de Gantt."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from datetime import datetime, timedelta

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

        # Parsear inicio
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
        ax.text(start_num + duration/2, i, name, ha='center', va='center',
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
    return f"Diagrama [gantt] creado: {ruta} ({size_kb:.0f} KB, {len(tasks)} tareas)"


def _render_sequence(ruta, datos, titulo, opts):
    """Renderiza un diagrama de secuencia simplificado."""
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

    # Dibujar participantes
    x_positions = np.linspace(0.1, 0.9, n)
    for i, p in enumerate(participants):
        ax.plot([x_positions[i]], [0.95], 's', markersize=20, color=PALETTE["primary"])
        ax.text(x_positions[i], 0.98, p, ha='center', va='bottom', fontsize=10, fontweight='bold')
        # Linea vertical
        ax.axvline(x=x_positions[i], ymin=0, ymax=0.9, color='#CCCCCC', linewidth=1, linestyle='--')

    # Dibujar mensajes
    y_start = 0.88
    y_step = min(0.05, 0.8 / max(len(messages), 1))

    for i, msg in enumerate(messages):
        src = msg.get("from", msg.get("desde", ""))
        dst = msg.get("to", msg.get("hasta", ""))
        text = msg.get("text", msg.get("texto", ""))

        src_idx = participants.index(src) if src in participants else 0
        dst_idx = participants.index(dst) if dst in participants else min(1, n-1)

        y = y_start - i * y_step

        # Flecha
        color = PALETTE["success"] if src_idx < dst_idx else PALETTE["danger"]
        ax.annotate("", xy=(x_positions[dst_idx], y), xytext=(x_positions[src_idx], y),
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.5))
        # Texto
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
    return f"Diagrama [sequence] creado: {ruta} ({size_kb:.0f} KB)"


def _render_swimlane(ruta, datos, titulo, opts):
    """Renderiza un diagrama de swimlane (carriles)."""
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

    # Dibujar carriles horizontales
    lane_height = 1.0 / n_lanes
    colors = CHART_COLORS[:n_lanes]

    for i, lane in enumerate(lanes):
        y_bottom = 1.0 - (i + 1) * lane_height
        ax.axhspan(y_bottom, y_bottom + lane_height, alpha=0.1, color=colors[i])
        ax.text(-0.02, y_bottom + lane_height/2, lane, ha='right', va='center',
                fontsize=10, fontweight='bold', color=colors[i])

    # Dibujar pasos
    step_width = 0.8 / max(len(steps), 1)
    for i, step in enumerate(steps):
        lane_name = step.get("lane", step.get("carril", lanes[0]))
        text = step.get("texto", step.get("text", f"Paso {i+1}"))
        order = step.get("orden", step.get("order", i))

        lane_idx = lanes.index(lane_name) if lane_name in lanes else 0
        x = 0.05 + (order * step_width) + step_width/2
        y = 1.0 - (lane_idx + 0.5) * lane_height

        # Caja
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
    return f"Diagrama [swimlane] creado: {ruta} ({size_kb:.0f} KB)"


def _render_simple(ruta, tipo, datos, titulo, opts):
    """Renderizado simple sin networkx (fallback)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    _setup_fonts()

    fig, ax = plt.subplots(figsize=(10, 8))

    # Generar representacion visual simple
    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", []))

    if not nodes and not edges:
        ax.text(0.5, 0.5, f"Diagrama: {tipo}\n(sin datos)", ha='center', va='center',
                fontsize=16, transform=ax.transAxes)
    else:
        # Posicionar nodos en circulo
        import math
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

        # Dibujar aristas
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
    return f"Diagrama [{tipo}] creado: {ruta} ({size_kb:.0f} KB)"


# ============================================================
# MERMAID
# ============================================================

def _crear_mermaid(ruta, datos_str, titulo, opciones_str):
    """Genera codigo Mermaid y opcionalmente renderiza a imagen."""
    datos = _parse_json(datos_str, {})

    # Si ya viene codigo Mermaid
    code = datos.get("code", datos.get("codigo", ""))
    if not code:
        # Generar desde tipo y datos
        tipo = datos.get("tipo", "flowchart")
        code = _to_mermaid(tipo, datos_str, titulo)

    # Guardar como .md o .mermaid
    if ruta.endswith(('.md', '.mermaid', '.mmd')):
        dir_name = os.path.dirname(ruta)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(f"```mermaid\n{code}\n```\n")
        return f"Codigo Mermaid guardado: {ruta}"

    # Intentar renderizar a imagen con mmdc (mermaid-cli)
    import subprocess
    try:
        result = subprocess.run(
            ["mmdc", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            # Guardar temporal y renderizar
            tmp_mmd = ruta + ".mmd"
            with open(tmp_mmd, 'w') as f:
                f.write(code)

            render_result = subprocess.run(
                ["mmdc", "-i", tmp_mmd, "-o", ruta, "-b", "white"],
                capture_output=True, text=True, timeout=30
            )
            os.remove(tmp_mmd)

            if render_result.returncode == 0 and os.path.exists(ruta):
                size_kb = os.path.getsize(ruta) / 1024
                return f"Diagrama Mermaid renderizado: {ruta} ({size_kb:.0f} KB)"

    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: guardar como .md con codigo Mermaid
    md_path = ruta.rsplit('.', 1)[0] + '.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(f"```mermaid\n{code}\n```\n")
    return (f"Mermaid CLI no disponible. Codigo guardado en: {md_path}\n"
            f"Para renderizar instala: npm install -g @mermaid-js/mermaid-cli\n\n"
            f"Codigo generado:\n```\n{code}\n```")


def _to_mermaid(tipo, datos_str, titulo=""):
    """Convierte datos JSON a codigo Mermaid."""
    datos = _parse_json(datos_str, {})

    generators = {
        "flowchart": _mermaid_flowchart,
        "mindmap": _mermaid_mindmap,
        "tree": _mermaid_flowchart,  # Mismo que flowchart con direccion TD
        "org": _mermaid_flowchart,
        "architecture": _mermaid_flowchart,
        "network": _mermaid_graph,
        "er": _mermaid_er,
        "class": _mermaid_class,
        "gantt": _mermaid_gantt,
        "sequence": _mermaid_sequence,
        "swimlane": _mermaid_flowchart,
        "topology": _mermaid_graph,
        "knowledge_graph": _mermaid_graph,
    }

    gen = generators.get(tipo, _mermaid_flowchart)
    code = gen(datos, titulo)

    return code


def _mermaid_flowchart(datos, titulo=""):
    """Genera Mermaid flowchart."""
    direction = datos.get("direction", datos.get("direccion", "TD"))
    lines = [f"flowchart {direction}"]

    if titulo:
        lines.append(f"    %% {titulo}")

    nodes = datos.get("nodes", datos.get("nodos", []))
    edges = datos.get("edges", datos.get("aristas", datos.get("conexiones", [])))

    # Nodos
    for node in nodes:
        if isinstance(node, str):
            safe_id = _mermaid_id(node)
            lines.append(f"    {safe_id}[\"{node}\"]")
        elif isinstance(node, dict):
            nid = _mermaid_id(node.get("id", node.get("nombre", "")))
            label = node.get("label", node.get("nombre", node.get("id", "")))
            shape = node.get("shape", "rect")
            if shape == "diamond":
                lines.append(f"    {nid}{{\"{label}\"}}")
            elif shape == "rounded":
                lines.append(f"    {nid}(\"{label}\")")
            elif shape == "circle":
                lines.append(f"    {nid}((\"{label}\"))")
            elif shape == "stadium":
                lines.append(f"    {nid}([\"{label}\"])")
            else:
                lines.append(f"    {nid}[\"{label}\"]")

    # Aristas
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            src = _mermaid_id(str(edge[0]))
            dst = _mermaid_id(str(edge[1]))
            label = str(edge[2]) if len(edge) > 2 else ""
            arrow = "-->" + f"|{label}|" if label else "-->"
            lines.append(f"    {src} {arrow} {dst}")
        elif isinstance(edge, dict):
            src = _mermaid_id(edge.get("from", edge.get("source", "")))
            dst = _mermaid_id(edge.get("to", edge.get("target", "")))
            label = edge.get("label", edge.get("etiqueta", ""))
            arrow = "-->" + f"|{label}|" if label else "-->"
            lines.append(f"    {src} {arrow} {dst}")

    # Jerarquia
    hierarchy = datos.get("hierarchy", datos.get("jerarquia", {}))
    if hierarchy and not nodes and not edges:
        _add_hierarchy_mermaid(lines, hierarchy, indent=4)

    return "\n".join(lines)


def _mermaid_mindmap(datos, titulo=""):
    """Genera Mermaid mindmap."""
    lines = ["mindmap"]

    hierarchy = datos.get("hierarchy", datos.get("jerarquia", {}))
    if hierarchy:
        _add_mindmap_mermaid(lines, hierarchy, indent=4)
    else:
        # Convertir nodos a mindmap
        root = datos.get("root", datos.get("raiz", "Root"))
        nodes = datos.get("nodes", datos.get("nodos", []))
        lines.append(f"  {root}")
        for node in nodes:
            label = node if isinstance(node, str) else node.get("label", node.get("id", ""))
            lines.append(f"    {label}")

    return "\n".join(lines)


def _mermaid_graph(datos, titulo=""):
    """Genera Mermaid graph (no dirigido)."""
    lines = ["graph LR"]
    if titulo:
        lines.append(f"    %% {titulo}")

    edges = datos.get("edges", datos.get("aristas", []))
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            src = _mermaid_id(str(edge[0]))
            dst = _mermaid_id(str(edge[1]))
            label = str(edge[2]) if len(edge) > 2 else ""
            link = f"---|{label}|" if label else "---"
            lines.append(f"    {src} {link} {dst}")
        elif isinstance(edge, dict):
            src = _mermaid_id(edge.get("from", edge.get("source", "")))
            dst = _mermaid_id(edge.get("to", edge.get("target", "")))
            label = edge.get("label", "")
            link = f"---|{label}|" if label else "---"
            lines.append(f"    {src} {link} {dst}")

    return "\n".join(lines)


def _mermaid_er(datos, titulo=""):
    """Genera Mermaid ER diagram."""
    lines = ["erDiagram"]
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
                    lines.append(f"        {atype} {aname}")
            lines.append(f"    }}")

    for rel in relationships:
        if isinstance(rel, dict):
            e1 = rel.get("from", rel.get("entity1", ""))
            e2 = rel.get("to", rel.get("entity2", ""))
            label = rel.get("label", rel.get("nombre", ""))
            card1 = rel.get("cardinality1", "||")
            card2 = rel.get("cardinality2", "o{")
            lines.append(f"    {e1} {card1}--{card2} {e2} : \"{label}\"")

    return "\n".join(lines)


def _mermaid_class(datos, titulo=""):
    """Genera Mermaid class diagram."""
    lines = ["classDiagram"]
    if titulo:
        lines.append(f"    %% {titulo}")

    classes = datos.get("classes", datos.get("clases", []))
    for cls in classes:
        name = cls.get("name", cls.get("nombre", ""))
        attrs = cls.get("attributes", cls.get("atributos", []))
        methods = cls.get("methods", cls.get("metodos", []))

        lines.append(f"    class {name} {{")
        for attr in attrs:
            lines.append(f"        {attr}")
        for method in methods:
            lines.append(f"        {method}")
        lines.append(f"    }}")

    # Relaciones
    relationships = datos.get("relationships", datos.get("relaciones", []))
    for rel in relationships:
        if isinstance(rel, dict):
            e1 = rel.get("from", "")
            e2 = rel.get("to", "")
            rtype = rel.get("type", "-->")
            lines.append(f"    {e1} {rtype} {e2}")

    return "\n".join(lines)


def _mermaid_gantt(datos, titulo=""):
    """Genera Mermaid Gantt chart."""
    lines = ["gantt"]
    if titulo:
        lines.append(f"    title {titulo}")

    date_format = datos.get("dateFormat", "YYYY-MM-DD")
    lines.append(f"    dateFormat {date_format}")

    tasks = datos.get("tasks", datos.get("tareas", []))
    sections = {}

    for task in tasks:
        section = task.get("section", "Default")
        name = task.get("nombre", task.get("name", ""))
        start = task.get("inicio", task.get("start", ""))
        duration = task.get("duracion", task.get("duration", "1d"))
        status = task.get("status", "")

        if section not in sections:
            sections[section] = []
        status_prefix = "active " if status == "active" else "done " if status == "done" else ""
        sections[section].append(f"{status_prefix}{name} : {start}, {duration}")

    for section, task_lines in sections.items():
        lines.append(f"    section {section}")
        for tl in task_lines:
            lines.append(f"    {tl}")

    return "\n".join(lines)


def _mermaid_sequence(datos, titulo=""):
    """Genera Mermaid sequence diagram."""
    lines = ["sequenceDiagram"]
    if titulo:
        lines.append(f"    title {titulo}")

    participants = datos.get("participants", datos.get("participantes", []))
    for p in participants:
        lines.append(f"    participant {p}")

    messages = datos.get("messages", datos.get("mensajes", []))
    for msg in messages:
        src = msg.get("from", msg.get("desde", ""))
        dst = msg.get("to", msg.get("hasta", ""))
        text = msg.get("text", msg.get("texto", ""))
        mtype = msg.get("type", "")

        if mtype == "dashed":
            lines.append(f"    {src}-->>{dst}: {text}")
        elif mtype == "note":
            lines.append(f"    Note right of {dst}: {text}")
        else:
            lines.append(f"    {src}->>{dst}: {text}")

    return "\n".join(lines)


def _add_hierarchy_mermaid(lines, data, indent=4):
    """Agrega jerarquia a codigo Mermaid."""
    spaces = " " * indent
    if isinstance(data, dict):
        for key, children in data.items():
            safe_key = _mermaid_id(key)
            lines.append(f"{spaces}{safe_key}[\"{key}\"]")
            if isinstance(children, dict):
                for child_key in children:
                    safe_child = _mermaid_id(child_key)
                    lines.append(f"{spaces}{safe_key} --> {safe_child}")
                _add_hierarchy_mermaid(lines, children, indent)
            elif isinstance(children, list):
                for child in children:
                    if isinstance(child, str):
                        safe_child = _mermaid_id(child)
                        lines.append(f"{spaces}{safe_child}[\"{child}\"]")
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


def _mermaid_id(text: str) -> str:
    """Convierte texto a ID valido para Mermaid."""
    import re
    # Reemplazar caracteres no alfanumericos
    safe = re.sub(r'[^a-zA-Z0-9_]', '_', text)
    # Asegurar que empieza con letra
    if safe and safe[0].isdigit():
        safe = "n" + safe
    return safe or "node"


# ============================================================
# UTILIDADES COMUNES
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
        import subprocess
        result = subprocess.run(["dot", "-V"], capture_output=True, timeout=3)
        return result.returncode == 0
    except Exception:
        return False


def _hierarchy_pos(G, root=None, width=1., vert_gap=0.2, vert_loc=0, xcenter=0.5):
    """Calcula posiciones jerarquicas para un grafo sin graphviz."""
    import networkx as nx

    if root is None:
        roots = [n for n in G.nodes() if G.in_degree(n) == 0] if G.is_directed() else [list(G.nodes())[0]]
        root = roots[0] if roots else list(G.nodes())[0]

    pos = {root: (xcenter, vert_loc)}
    children = list(G.successors(root)) if G.is_directed() else list(G.neighbors(root))

    if children:
        dx = width / len(children)
        nextx = xcenter - width/2 - dx/2
        for child in children:
            nextx += dx
            pos.update(_hierarchy_pos(G, root=child, width=dx, vert_gap=vert_gap,
                                       vert_loc=vert_loc - vert_gap, xcenter=nextx))
    return pos
