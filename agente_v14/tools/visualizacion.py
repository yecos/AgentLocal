"""
=============================================================
AGENTE v15 - Herramientas de Visualizacion Avanzada
=============================================================
15+ tipos de graficos y dashboards:
- Bar, Line, Pie, Scatter, Histogram, Area (existentes, mejorados)
- Heatmap, Radar, Candlestick, Boxplot, Waterfall
- Regression, Distribution, Violin, Stem
- Dashboards multi-grafico
- Exportacion PNG/SVG con calidad profesional

Dependencias: matplotlib, numpy (opcionales pero recomendadas)
=============================================================
"""

import os
import json
import logging
from config import REPOS_DIR, logger
from utils.security import validate_path


# ============================================================
# CONFIGURACION DE VISUALIZACION
# ============================================================

# Paleta de colores profesional
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
    "#E74C3C", "#2ECC71", "#3498DB", "#F39C12", "#8E44AD",
]

# Tipos de grafico soportados
SUPPORTED_CHART_TYPES = [
    "bar", "line", "pie", "scatter", "histogram", "area",
    "heatmap", "radar", "candlestick", "boxplot", "waterfall",
    "regression", "distribution", "violin", "stem",
]


def crear_grafico_avanzado(
    ruta: str,
    tipo: str = "bar",
    datos: str = "",
    titulo: str = "",
    xlabel: str = "",
    ylabel: str = "",
    opciones: str = "{}",
) -> str:
    """Crea un grafico avanzado y lo guarda como imagen PNG/SVG.
    Soporta 15+ tipos: bar, line, pie, scatter, histogram, area,
    heatmap, radar, candlestick, boxplot, waterfall, regression,
    distribution, violin, stem.

    Args:
        ruta: Ruta donde guardar la imagen (PNG o SVG)
        tipo: Tipo de grafico (ver lista arriba)
        datos: Datos en formato JSON o CSV
        titulo: Titulo del grafico
        xlabel: Etiqueta del eje X
        ylabel: Etiqueta del eje Y
        opciones: Opciones extra en JSON (colores, leyenda, grid, etc.)
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    tipo = tipo.lower().strip()
    if tipo not in SUPPORTED_CHART_TYPES:
        return (f"ERROR: Tipo '{tipo}' no soportado. "
                f"Usar: {', '.join(SUPPORTED_CHART_TYPES)}")

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        import numpy as np

        # Configurar fuentes
        _setup_fonts()

        # Parsear datos y opciones
        parsed_data = _parse_chart_data(datos)
        opts = _parse_options(opciones)

        # Crear grafico
        fig, ax = plt.subplots(figsize=opts.get("figsize", (10, 6)))
        fig.patch.set_facecolor(opts.get("bg_color", "white"))

        # Dispatch por tipo
        handler = _CHART_HANDLERS.get(tipo)
        if handler:
            handler(ax, parsed_data, opts, title=titulo, xlabel=xlabel, ylabel=ylabel)
        else:
            plt.close()
            return f"ERROR: Handler no implementado para tipo '{tipo}'"

        # Aplicar estilo comun
        _apply_common_style(ax, titulo, xlabel, ylabel, opts)

        # Guardar
        dir_name = os.path.dirname(ruta)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        dpi = opts.get("dpi", 150)
        bbox = opts.get("bbox_inches", "tight")
        plt.tight_layout()
        plt.savefig(ruta, dpi=dpi, bbox_inches=bbox,
                    facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close()

        size_kb = os.path.getsize(ruta) / 1024
        return f"Grafico [{tipo}] creado: {ruta} ({size_kb:.0f} KB)"

    except ImportError as e:
        return (f"ERROR: Faltan dependencias para visualizacion: {e}\n"
                "Instala: pip install matplotlib numpy")
    except Exception as e:
        logger.error(f"Error creando grafico: {e}")
        return f"ERROR creando grafico: {e}"


def crear_dashboard(
    ruta: str,
    graficos: str = "[]",
    titulo: str = "Dashboard",
    layout: str = "auto",
    opciones: str = "{}",
) -> str:
    """Crea un dashboard con multiples graficos en una sola imagen.
    Cada grafico se define como un objeto JSON con tipo, datos y opciones.

    Args:
        ruta: Ruta donde guardar el dashboard (PNG o SVG)
        graficos: Lista JSON de graficos, cada uno con: tipo, datos, titulo, opciones
        titulo: Titulo del dashboard
        layout: Layout del grid: 'auto', '2x2', '3x2', '2x3', '1x3', '3x1'
        opciones: Opciones globales en JSON
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        import numpy as np

        _setup_fonts()
        opts = _parse_options(opciones)

        # Parsear lista de graficos
        charts = _parse_dashboard_charts(graficos)
        if not charts:
            return "ERROR: No se proporcionaron graficos. Formato: [{tipo, datos, titulo}, ...]"

        n = len(charts)

        # Calcular layout
        rows, cols = _calc_layout(n, layout)

        # Crear figura
        fig_width = cols * 5
        fig_height = rows * 4 + 1.5  # Extra para titulo
        fig, axes = plt.subplots(rows, cols, figsize=(fig_width, fig_height))
        fig.suptitle(titulo, fontsize=16, fontweight='bold', y=0.98)

        # Aplanar axes para iteracion
        if rows == 1 and cols == 1:
            axes = [[axes]]
        elif rows == 1:
            axes = [axes]
        elif cols == 1:
            axes = [[ax] for ax in axes]

        # Renderizar cada grafico
        for idx, chart in enumerate(charts):
            row = idx // cols
            col = idx % cols
            if row < rows and col < cols:
                ax = axes[row][col]
                chart_type = chart.get("tipo", "bar")
                chart_data = _parse_chart_data(chart.get("datos", ""))
                chart_opts = _parse_options(chart.get("opciones", "{}"))
                chart_title = chart.get("titulo", "")

                handler = _CHART_HANDLERS.get(chart_type)
                if handler:
                    handler(ax, chart_data, chart_opts)
                    _apply_common_style(ax, chart_title, "", "", chart_opts)
                else:
                    ax.text(0.5, 0.5, f"Tipo '{chart_type}' no soportado",
                            ha='center', va='center', transform=ax.transAxes)
                    ax.set_title(chart_title)

        # Ocultar axes vacios
        for idx in range(n, rows * cols):
            row = idx // cols
            col = idx % cols
            if row < rows and col < cols:
                axes[row][col].set_visible(False)

        # Guardar
        dir_name = os.path.dirname(ruta)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        plt.savefig(ruta, dpi=150, bbox_inches="tight",
                    facecolor='white', edgecolor='none')
        plt.close()

        size_kb = os.path.getsize(ruta) / 1024
        return f"Dashboard creado: {ruta} ({size_kb:.0f} KB, {n} graficos, layout {rows}x{cols})"

    except ImportError:
        return "ERROR: Instala matplotlib y numpy: pip install matplotlib numpy"
    except Exception as e:
        logger.error(f"Error creando dashboard: {e}")
        return f"ERROR creando dashboard: {e}"


# ============================================================
# HANDLERS DE GRAFICOS
# ============================================================

def _chart_bar(ax, data, opts, **kwargs):
    """Grafico de barras (horizontal/vertical, agrupado, apilado)."""
    labels = data.get("labels", [])
    values = data.get("values", [])
    if not values:
        return

    horizontal = opts.get("horizontal", False)
    stacked = opts.get("stacked", False)

    # Multiple series?
    if isinstance(values[0], list):
        # Datos multi-serie
        x = np.arange(len(labels))
        width = 0.8 / len(values)
        colors = opts.get("colors", CHART_COLORS)
        series_names = opts.get("series_names", [f"Serie {i+1}" for i in range(len(values))])

        for i, serie in enumerate(values):
            offset = (i - len(values)/2 + 0.5) * width
            if stacked:
                if i == 0:
                    bottom = np.zeros(len(labels))
                else:
                    bottom = np.array(values[i-1]) if i == 1 else np.add.reduce(values[:i])
                ax.bar(x, serie, width, label=series_names[i],
                       color=colors[i % len(colors)], bottom=bottom)
            else:
                if horizontal:
                    ax.barh(x + offset, serie, width, label=series_names[i],
                            color=colors[i % len(colors)])
                else:
                    ax.bar(x + offset, serie, width, label=series_names[i],
                           color=colors[i % len(colors)])
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha='right')
        ax.legend(loc='best', fontsize=8)
    else:
        color = opts.get("color", PALETTE["primary"])
        if horizontal:
            ax.barh(labels, values, color=color)
        else:
            ax.bar(labels, values, color=color)
            plt.xticks(rotation=45, ha='right')


def _chart_line(ax, data, opts, **kwargs):
    """Grafico de lineas (simple, multi-serie, con marcadores)."""
    labels = data.get("labels", [])
    values = data.get("values", [])

    if isinstance(values[0], list):
        # Multi-serie
        colors = opts.get("colors", CHART_COLORS)
        series_names = opts.get("series_names", [f"Serie {i+1}" for i in range(len(values))])
        markers = opts.get("markers", ['o', 's', '^', 'D', 'v', '<', '>'])

        for i, serie in enumerate(values):
            marker = markers[i % len(markers)] if opts.get("show_markers", True) else None
            ax.plot(labels, serie, marker=marker, color=colors[i % len(colors)],
                    linewidth=2, label=series_names[i], markersize=5)
            if opts.get("fill", False):
                ax.fill_between(range(len(labels)), serie, alpha=0.1,
                                color=colors[i % len(colors)])
        ax.legend(loc='best', fontsize=8)
    else:
        color = opts.get("color", PALETTE["primary"])
        marker = 'o' if opts.get("show_markers", True) else None
        ax.plot(labels, values, marker=marker, color=color, linewidth=2, markersize=5)
        if opts.get("fill", False):
            ax.fill_between(range(len(labels)), values, alpha=0.1, color=color)

    plt.xticks(rotation=45, ha='right')


def _chart_pie(ax, data, opts, **kwargs):
    """Grafico de pie/donut."""
    labels = data.get("labels", [])
    values = data.get("values", [])

    colors = opts.get("colors", CHART_COLORS)
    explode = opts.get("explode", None)
    donut = opts.get("donut", False)

    if donut:
        # Crear donut
        wedges, texts, autotexts = ax.pie(
            values, labels=labels, autopct='%1.1f%%',
            colors=colors[:len(labels)], pctdistance=0.75,
            explode=explode, startangle=90
        )
        # Agujero central
        centre_circle = plt.Circle((0, 0), 0.50, fc='white')
        ax.add_artist(centre_circle)
    else:
        ax.pie(values, labels=labels, autopct='%1.1f%%',
               colors=colors[:len(labels)], explode=explode,
               startangle=90, shadow=opts.get("shadow", False))

    ax.axis('equal')


def _chart_scatter(ax, data, opts, **kwargs):
    """Grafico de dispersion con opcion de burbujas."""
    x_data = data.get("x", data.get("values", []))
    y_data = data.get("y", [])
    sizes = data.get("sizes", None)
    colors_data = data.get("colors", None)

    if not y_data and isinstance(x_data, list) and len(x_data) > 0:
        if isinstance(x_data[0], list) and len(x_data) >= 2:
            y_data = x_data[1]
            x_data = x_data[0]

    if not y_data:
        # Fallback: usar indices como X
        y_data = x_data
        x_data = list(range(len(y_data)))

    color = opts.get("color", PALETTE["primary"])
    size = opts.get("size", 50)

    if sizes:
        scatter = ax.scatter(x_data, y_data, s=sizes, c=colors_data or color,
                             alpha=0.6, edgecolors='white', linewidth=0.5)
    else:
        ax.scatter(x_data, y_data, s=size, c=color, alpha=0.7, edgecolors='white')

    if opts.get("trendline", False):
        _add_trendline(ax, x_data, y_data)


def _chart_histogram(ax, data, opts, **kwargs):
    """Histograma con opciones de bins y KDE."""
    values = data.get("values", [])

    bins = opts.get("bins", min(30, max(5, len(values) // 5)))
    color = opts.get("color", PALETTE["primary"])
    edgecolor = opts.get("edgecolor", "white")

    ax.hist(values, bins=bins, color=color, edgecolor=edgecolor, alpha=0.8)

    if opts.get("kde", False):
        try:
            from scipy.stats import gaussian_kde
            import numpy as np
            kde = gaussian_kde(values)
            x_range = np.linspace(min(values), max(values), 200)
            ax.plot(x_range, kde(x_range) * len(values) * (max(values) - min(values)) / bins,
                    color='red', linewidth=2, label='KDE')
            ax.legend(loc='best')
        except ImportError:
            pass


def _chart_area(ax, data, opts, **kwargs):
    """Grafico de area (simple o apilado)."""
    labels = data.get("labels", [])
    values = data.get("values", [])
    colors = opts.get("colors", CHART_COLORS)

    if isinstance(values[0], list):
        # Multi-serie apilada
        series_names = opts.get("series_names", [f"Serie {i+1}" for i in range(len(values))])
        ax.stackplot(range(len(labels)), *values, labels=series_names,
                     colors=colors[:len(values)], alpha=0.8)
        ax.legend(loc='best', fontsize=8)
    else:
        ax.fill_between(range(len(labels)), values, alpha=0.3, color=colors[0])
        ax.plot(range(len(labels)), values, color=colors[0], linewidth=2)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha='right')


def _chart_heatmap(ax, data, opts, **kwargs):
    """Mapa de calor (heatmap) con anotaciones."""
    matrix = data.get("matrix", data.get("values", []))
    row_labels = data.get("row_labels", data.get("labels", []))
    col_labels = data.get("col_labels", [])

    if not matrix:
        return

    import numpy as np
    mat = np.array(matrix, dtype=float)

    cmap = opts.get("cmap", "YlOrRd")
    annot = opts.get("annot", True)
    fmt = opts.get("fmt", ".1f")

    im = ax.imshow(mat, cmap=cmap, aspect='auto')

    if annot:
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                val = mat[i, j]
                text_color = "white" if val > np.max(mat) * 0.7 else "black"
                ax.text(j, i, f"{val:{fmt}}", ha="center", va="center",
                        color=text_color, fontsize=8)

    if col_labels:
        ax.set_xticks(range(len(col_labels)))
        ax.set_xticklabels(col_labels, rotation=45, ha='right')
    if row_labels:
        ax.set_yticks(range(len(row_labels)))
        ax.set_yticklabels(row_labels)

    plt.colorbar(im, ax=ax, shrink=0.8)


def _chart_radar(ax, data, opts, **kwargs):
    """Grafico radar/spider."""
    labels = data.get("labels", [])
    values = data.get("values", [])

    if not labels or not values:
        return

    import numpy as np

    # Multi-serie?
    if isinstance(values[0], list):
        series = values
        series_names = opts.get("series_names", [f"Serie {i+1}" for i in range(len(series))])
        colors = opts.get("colors", CHART_COLORS)
    else:
        series = [values]
        series_names = ["Valores"]
        colors = [opts.get("color", PALETTE["primary"])]

    N = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]  # Cerrar

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_rlabel_position(0)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels)

    for i, serie in enumerate(series):
        values_closed = serie + serie[:1]
        ax.plot(angles, values_closed, 'o-', linewidth=2,
                color=colors[i % len(colors)], label=series_names[i], markersize=5)
        ax.fill(angles, values_closed, alpha=0.15, color=colors[i % len(colors)])

    ax.legend(loc='upper right', bbox_to_anchor=(0.1, 0.1), fontsize=8)


def _chart_candlestick(ax, data, opts, **kwargs):
    """Grafico de velas (candlestick) para datos financieros."""
    import numpy as np

    candles = data.get("candles", data.get("values", []))
    labels = data.get("labels", [])

    if not candles:
        return

    # Parsear: cada vela = [open, high, low, close] o dict
    parsed = []
    for c in candles:
        if isinstance(c, dict):
            parsed.append([c.get("open", 0), c.get("high", 0),
                           c.get("low", 0), c.get("close", 0)])
        elif isinstance(c, (list, tuple)) and len(c) >= 4:
            parsed.append(list(c[:4]))

    if not parsed:
        return

    width = opts.get("width", 0.6)
    x_range = range(len(parsed))

    for i, (o, h, l, cl) in enumerate(parsed):
        # Color: verde si cierra por encima de apertura, rojo si no
        color = PALETTE["success"] if cl >= o else PALETTE["danger"]
        # Sombra (mecha)
        ax.plot([i, i], [l, h], color=color, linewidth=1)
        # Cuerpo
        body_bottom = min(o, cl)
        body_height = abs(cl - o) or 0.01  # Minimo para velas doji
        ax.bar(i, body_height, bottom=body_bottom, width=width,
               color=color, edgecolor=color)

    if labels:
        ax.set_xticks(list(x_range))
        ax.set_xticklabels(labels, rotation=45, ha='right')


def _chart_boxplot(ax, data, opts, **kwargs):
    """Diagrama de caja (boxplot) para distribucion de datos."""
    import numpy as np

    values = data.get("values", [])
    labels = data.get("labels", [])

    if isinstance(values[0], list):
        # Multi-serie
        ax.boxplot(values, labels=labels if labels else
                   [f"Grupo {i+1}" for i in range(len(values))],
                   patch_artist=True,
                   boxprops=dict(facecolor=PALETTE["primary"], alpha=0.7),
                   medianprops=dict(color='red', linewidth=2))
    else:
        ax.boxplot([values], labels=labels if labels else ["Datos"],
                   patch_artist=True,
                   boxprops=dict(facecolor=PALETTE["primary"], alpha=0.7),
                   medianprops=dict(color='red', linewidth=2))

    if opts.get("showfliers", True) is False:
        ax.boxplot(values if isinstance(values[0], list) else [values],
                   showfliers=False)


def _chart_waterfall(ax, data, opts, **kwargs):
    """Grafico de cascada (waterfall) para analisis incremental."""
    import numpy as np

    labels = data.get("labels", [])
    values = data.get("values", [])

    if not labels or not values:
        return

    cumulative = [0]
    for v in values[:-1] if len(values) > 1 else values:
        cumulative.append(cumulative[-1] + v)

    # Agregar total al final si no existe
    has_total = opts.get("show_total", True)
    if has_total and len(values) > 1:
        labels.append("Total")
        values.append(cumulative[-1] + values[-1] if len(values) > 1 else values[0])
        cumulative.append(0)

    bottoms = []
    heights = []
    colors = []

    for i, v in enumerate(values):
        if labels[i] == "Total":
            bottoms.append(0)
            heights.append(v)
            colors.append(PALETTE["primary"])
        elif v >= 0:
            bottoms.append(cumulative[i])
            heights.append(v)
            colors.append(PALETTE["success"])
        else:
            bottoms.append(cumulative[i] + v)
            heights.append(abs(v))
            colors.append(PALETTE["danger"])

    ax.bar(labels, heights, bottom=bottoms, color=colors)

    # Anotaciones
    for i, (b, h, v) in enumerate(zip(bottoms, heights, values)):
        y_pos = b + h if v >= 0 or labels[i] == "Total" else b
        prefix = "+" if v > 0 and labels[i] != "Total" else ""
        ax.text(i, y_pos + 0.02 * max(abs(v) for v in values),
                f"{prefix}{v:.1f}", ha='center', va='bottom', fontsize=9)

    plt.xticks(rotation=45, ha='right')


def _chart_regression(ax, data, opts, **kwargs):
    """Grafico de dispersion con linea de regresion."""
    import numpy as np

    x_data = data.get("x", data.get("values", []))
    y_data = data.get("y", [])

    if not y_data:
        if isinstance(x_data[0], (list, tuple)) and len(x_data[0]) >= 2:
            y_data = [p[1] for p in x_data]
            x_data = [p[0] for p in x_data]
        else:
            y_data = x_data
            x_data = list(range(len(y_data)))

    x = np.array(x_data, dtype=float)
    y = np.array(y_data, dtype=float)

    # Scatter
    color = opts.get("color", PALETTE["primary"])
    ax.scatter(x, y, s=40, c=color, alpha=0.6, edgecolors='white')

    # Regresion lineal
    if len(x) > 1:
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        x_line = np.linspace(x.min(), x.max(), 100)
        ax.plot(x_line, p(x_line), color=PALETTE["danger"], linewidth=2,
                linestyle='--', label=f'y = {z[0]:.2f}x + {z[1]:.2f}')

        # R-squared
        y_pred = p(x)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        ax.text(0.05, 0.95, f'R² = {r_squared:.3f}',
                transform=ax.transAxes, fontsize=10, va='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        ax.legend(loc='best', fontsize=9)


def _chart_distribution(ax, data, opts, **kwargs):
    """Grafico de distribucion con histograma + curva normal."""
    import numpy as np

    values = data.get("values", [])
    if not values:
        return

    values = np.array(values, dtype=float)
    bins = opts.get("bins", min(30, max(5, len(values) // 5)))
    color = opts.get("color", PALETTE["primary"])

    # Histograma normalizado
    n, bins_edges, patches = ax.hist(values, bins=bins, density=True,
                                      color=color, alpha=0.6, edgecolor='white')

    # Curva normal
    mu = np.mean(values)
    sigma = np.std(values)
    x = np.linspace(mu - 4*sigma, mu + 4*sigma, 200)

    try:
        from scipy.stats import norm
        ax.plot(x, norm.pdf(x, mu, sigma), 'r-', linewidth=2, label='Normal')
    except ImportError:
        # Aproximacion sin scipy
        pdf = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mu) / sigma) ** 2)
        ax.plot(x, pdf, 'r-', linewidth=2, label='Normal')

    # Estadisticas
    stats_text = f'Media: {mu:.2f}\nDesv.Est: {sigma:.2f}\nN: {len(values)}'
    ax.text(0.95, 0.95, stats_text, transform=ax.transAxes, fontsize=9,
            va='top', ha='right', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    ax.legend(loc='best')


def _chart_violin(ax, data, opts, **kwargs):
    """Grafico de violin para distribucion de datos."""
    import numpy as np

    values = data.get("values", [])
    labels = data.get("labels", [])

    if isinstance(values[0], list):
        # Multi-serie
        parts = ax.violinplot(values, showmeans=True, showmedians=True)
        colors = opts.get("colors", CHART_COLORS)
        for i, pc in enumerate(parts['bodies']):
            pc.set_facecolor(colors[i % len(colors)])
            pc.set_alpha(0.7)

        if labels:
            ax.set_xticks(range(1, len(values) + 1))
            ax.set_xticklabels(labels)
    else:
        parts = ax.violinplot([values], showmeans=True, showmedians=True)
        for pc in parts['bodies']:
            pc.set_facecolor(PALETTE["primary"])
            pc.set_alpha(0.7)

        if labels:
            ax.set_xticks([1])
            ax.set_xticklabels(labels)


def _chart_stem(ax, data, opts, **kwargs):
    """Grafico de tallo (stem) para datos discretos."""
    import numpy as np

    labels = data.get("labels", [])
    values = data.get("values", [])

    if not values:
        return

    x = range(len(values)) if not labels else labels
    color = opts.get("color", PALETTE["primary"])

    markerline, stemlines, baseline = ax.stem(x, values, linefmt=color,
                                               markerfmt='o', basefmt='grey')
    markerline.set_markerfacecolor(color)
    stemlines.set_linewidth(1.5)

    if labels:
        ax.set_xticks(list(range(len(labels))))
        ax.set_xticklabels(labels, rotation=45, ha='right')


# ============================================================
# REGISTRO DE HANDLERS
# ============================================================

_CHART_HANDLERS = {
    "bar": _chart_bar,
    "line": _chart_line,
    "pie": _chart_pie,
    "scatter": _chart_scatter,
    "histogram": _chart_histogram,
    "area": _chart_area,
    "heatmap": _chart_heatmap,
    "radar": _chart_radar,
    "candlestick": _chart_candlestick,
    "boxplot": _chart_boxplot,
    "waterfall": _chart_waterfall,
    "regression": _chart_regression,
    "distribution": _chart_distribution,
    "violin": _chart_violin,
    "stem": _chart_stem,
}


# ============================================================
# UTILIDADES
# ============================================================

def _setup_fonts():
    """Configura fuentes para soporte Unicode/espanol."""
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


def _parse_chart_data(datos_str: str) -> dict:
    """Parsea datos de grafico desde JSON o CSV a estructura estandar.

    Formatos soportados:
    - JSON con keys: labels, values, x, y, matrix, candles, sizes, colors, row_labels, col_labels
    - CSV simple: etiqueta,valor por linea
    - Lista de puntos: x,y por linea
    """
    if not datos_str:
        return {"labels": [], "values": []}

    datos_str = datos_str.strip()

    # Intentar JSON
    if datos_str.startswith('{') or datos_str.startswith('['):
        try:
            parsed = json.loads(datos_str)
            if isinstance(parsed, dict):
                return parsed
            elif isinstance(parsed, list):
                if len(parsed) > 0 and isinstance(parsed[0], dict):
                    # Lista de dicts -> extraer labels y values
                    keys = list(parsed[0].keys())
                    return {
                        "labels": [str(d.get(keys[0], "")) for d in parsed],
                        "values": [d.get(keys[1], 0) if len(keys) > 1 else 0 for d in parsed],
                    }
                elif len(parsed) > 0 and isinstance(parsed[0], (list, tuple)):
                    return {"labels": [str(r[0]) for r in parsed],
                            "values": [r[1] if len(r) > 1 else 0 for r in parsed]}
                else:
                    return {"labels": [str(i) for i in range(len(parsed))],
                            "values": parsed}
        except json.JSONDecodeError:
            pass

    # Fallback: CSV
    result = {"labels": [], "values": []}
    for line in datos_str.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Intentar punto x,y
        if "," in line:
            parts = line.rsplit(",", 1)
            if len(parts) == 2:
                result["labels"].append(parts[0].strip())
                try:
                    result["values"].append(float(parts[1].strip()))
                except ValueError:
                    result["values"].append(0)
        else:
            try:
                result["values"].append(float(line))
            except ValueError:
                result["labels"].append(line)

    return result


def _parse_options(opts_str: str) -> dict:
    """Parsea opciones JSON del grafico."""
    if not opts_str or opts_str == "{}":
        return {}
    try:
        return json.loads(opts_str)
    except json.JSONDecodeError:
        return {}


def _parse_dashboard_charts(charts_str: str) -> list:
    """Parsea la lista de graficos para un dashboard."""
    if not charts_str or charts_str == "[]":
        return []
    try:
        return json.loads(charts_str)
    except json.JSONDecodeError:
        return []


def _calc_layout(n: int, layout: str = "auto") -> tuple:
    """Calcula filas y columnas para el dashboard."""
    if layout == "auto":
        if n <= 1: return (1, 1)
        if n <= 2: return (1, 2)
        if n <= 4: return (2, 2)
        if n <= 6: return (2, 3)
        if n <= 9: return (3, 3)
        return ((n + 3) // 4, 4)

    parts = layout.lower().split('x')
    if len(parts) == 2:
        try:
            return (int(parts[0]), int(parts[1]))
        except ValueError:
            pass

    return (2, 2)


def _apply_common_style(ax, title: str = "", xlabel: str = "", ylabel: str = "",
                        opts: dict = None):
    """Aplica estilo comun a todos los graficos."""
    if title:
        ax.set_title(title, fontsize=12, fontweight='bold', pad=10)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10)

    if opts:
        if opts.get("grid", True):
            ax.grid(True, alpha=0.3, linestyle='--')
        if opts.get("legend") and not ax.get_legend():
            ax.legend(loc='best')
        if "xlim" in opts:
            ax.set_xlim(opts["xlim"])
        if "ylim" in opts:
            ax.set_ylim(opts["ylim"])
    else:
        ax.grid(True, alpha=0.3, linestyle='--')


def _add_trendline(ax, x_data, y_data):
    """Agrega linea de tendencia a un scatter plot."""
    import numpy as np
    try:
        x = np.array(x_data, dtype=float)
        y = np.array(y_data, dtype=float)
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        x_line = np.linspace(x.min(), x.max(), 100)
        ax.plot(x_line, p(x_line), color='red', linewidth=1.5,
                linestyle='--', label='Tendencia')
        ax.legend(loc='best', fontsize=8)
    except Exception:
        pass
