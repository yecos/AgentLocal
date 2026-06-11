#!/usr/bin/env python3
"""
Genera PDF: Analisis de Optimizacion y Refactorizacion - Agente Autonomo AI v13
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
import hashlib

# ============================================================
# PALETTE (auto-generated)
# ============================================================
ACCENT       = colors.HexColor('#d72c48')
TEXT_PRIMARY  = colors.HexColor('#252422')
TEXT_MUTED    = colors.HexColor('#918c85')
BG_SURFACE   = colors.HexColor('#e6e4e0')
BG_PAGE      = colors.HexColor('#f0efee')

TABLE_HEADER_COLOR = ACCENT
TABLE_HEADER_TEXT  = colors.white
TABLE_ROW_EVEN     = colors.white
TABLE_ROW_ODD      = BG_SURFACE

# ============================================================
# FONTS
# ============================================================
pdfmetrics.registerFont(TTFont('LiberationSerif', '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf'))
pdfmetrics.registerFont(TTFont('LiberationSans', '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'))

registerFontFamily('LiberationSerif', normal='LiberationSerif', bold='LiberationSerif')
registerFontFamily('LiberationSans', normal='LiberationSans', bold='LiberationSans')
registerFontFamily('DejaVuSans', normal='DejaVuSans', bold='DejaVuSans-Bold')

# ============================================================
# STYLES
# ============================================================
PAGE_W, PAGE_H = A4
LEFT_M = 1.0 * inch
RIGHT_M = 1.0 * inch
TOP_M = 0.8 * inch
BOT_M = 0.8 * inch
AVAILABLE_W = PAGE_W - LEFT_M - RIGHT_M

styles = {}

styles['title'] = ParagraphStyle(
    name='Title', fontName='LiberationSerif', fontSize=28, leading=34,
    alignment=TA_CENTER, textColor=ACCENT, spaceAfter=6
)
styles['subtitle'] = ParagraphStyle(
    name='Subtitle', fontName='LiberationSerif', fontSize=14, leading=20,
    alignment=TA_CENTER, textColor=TEXT_MUTED, spaceAfter=24
)
styles['h1'] = ParagraphStyle(
    name='H1', fontName='LiberationSerif', fontSize=20, leading=26,
    textColor=ACCENT, spaceBefore=18, spaceAfter=10
)
styles['h2'] = ParagraphStyle(
    name='H2', fontName='LiberationSerif', fontSize=16, leading=22,
    textColor=TEXT_PRIMARY, spaceBefore=14, spaceAfter=8
)
styles['h3'] = ParagraphStyle(
    name='H3', fontName='LiberationSerif', fontSize=13, leading=18,
    textColor=TEXT_PRIMARY, spaceBefore=10, spaceAfter=6
)
styles['body'] = ParagraphStyle(
    name='Body', fontName='LiberationSerif', fontSize=10.5, leading=17,
    alignment=TA_JUSTIFY, textColor=TEXT_PRIMARY, spaceAfter=6,
    firstLineIndent=0
)
styles['body_indent'] = ParagraphStyle(
    name='BodyIndent', fontName='LiberationSerif', fontSize=10.5, leading=17,
    alignment=TA_JUSTIFY, textColor=TEXT_PRIMARY, spaceAfter=6,
    leftIndent=18
)
styles['bullet'] = ParagraphStyle(
    name='Bullet', fontName='LiberationSerif', fontSize=10.5, leading=17,
    alignment=TA_LEFT, textColor=TEXT_PRIMARY, spaceAfter=4,
    leftIndent=24, bulletIndent=12
)
styles['code'] = ParagraphStyle(
    name='Code', fontName='DejaVuSans', fontSize=9, leading=14,
    alignment=TA_LEFT, textColor=colors.HexColor('#1a1a2e'),
    backColor=colors.HexColor('#f4f4f8'), spaceAfter=6,
    leftIndent=12, rightIndent=12, borderPadding=6
)
styles['callout'] = ParagraphStyle(
    name='Callout', fontName='LiberationSerif', fontSize=11, leading=17,
    alignment=TA_LEFT, textColor=ACCENT, spaceAfter=8,
    leftIndent=24, borderPadding=8, borderColor=ACCENT,
    borderWidth=0, backColor=colors.HexColor('#fdf2f4')
)
styles['caption'] = ParagraphStyle(
    name='Caption', fontName='LiberationSerif', fontSize=9, leading=13,
    alignment=TA_CENTER, textColor=TEXT_MUTED, spaceAfter=12
)
styles['toc_h1'] = ParagraphStyle(
    name='TOCHeading1', fontSize=12, leftIndent=20, fontName='LiberationSerif',
    textColor=TEXT_PRIMARY
)
styles['toc_h2'] = ParagraphStyle(
    name='TOCHeading2', fontSize=10, leftIndent=40, fontName='LiberationSerif',
    textColor=TEXT_MUTED
)

# Table styles
header_style = ParagraphStyle(
    name='TableHeader', fontName='LiberationSerif', fontSize=10,
    textColor=colors.white, alignment=TA_CENTER
)
cell_style = ParagraphStyle(
    name='TableCell', fontName='LiberationSerif', fontSize=9.5,
    textColor=TEXT_PRIMARY, alignment=TA_CENTER, leading=14
)
cell_left = ParagraphStyle(
    name='TableCellLeft', fontName='LiberationSerif', fontSize=9.5,
    textColor=TEXT_PRIMARY, alignment=TA_LEFT, leading=14
)
cell_left_small = ParagraphStyle(
    name='TableCellLeftSmall', fontName='LiberationSerif', fontSize=8.5,
    textColor=TEXT_PRIMARY, alignment=TA_LEFT, leading=12
)

# ============================================================
# HELPERS
# ============================================================

def P(text, style_key='body'):
    return Paragraph(text, styles[style_key])

def heading(text, level=1, style_key=None):
    key = style_key or f'h{level}'
    bookmark_key = 'h_' + hashlib.md5(text.encode()).hexdigest()[:8]
    p = Paragraph(f'<a name="{bookmark_key}"/><b>{text}</b>', styles[key])
    p.bookmark_name = text
    p.bookmark_level = level - 1
    p.bookmark_text = text
    p.bookmark_key = bookmark_key
    return p

def make_table(data, col_widths=None):
    if col_widths is None:
        col_widths = [AVAILABLE_W / len(data[0])] * len(data[0])
    t = Table(data, colWidths=col_widths, hAlign='CENTER')
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, 0), TABLE_HEADER_TEXT),
        ('GRID', (0, 0), (-1, -1), 0.5, TEXT_MUTED),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(data)):
        bg = TABLE_ROW_EVEN if i % 2 == 1 else TABLE_ROW_ODD
        style_cmds.append(('BACKGROUND', (0, i), (-1, i), bg))
    t.setStyle(TableStyle(style_cmds))
    return t

def callout_box(text):
    return Paragraph(text, styles['callout'])

# ============================================================
# TOC TEMPLATE
# ============================================================
from reportlab.platypus import SimpleDocTemplate

class TocDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if hasattr(flowable, 'bookmark_name'):
            level = getattr(flowable, 'bookmark_level', 0)
            text = getattr(flowable, 'bookmark_text', '')
            key = getattr(flowable, 'bookmark_key', '')
            self.notify('TOCEntry', (level, text, self.page, key))

# ============================================================
# BUILD DOCUMENT
# ============================================================
output_path = '/home/z/my-project/download/analisis_optimizacion_agente.pdf'

doc = TocDocTemplate(
    output_path, pagesize=A4,
    leftMargin=LEFT_M, rightMargin=RIGHT_M,
    topMargin=TOP_M, bottomMargin=BOT_M,
    title='Analisis de Optimizacion y Refactorizacion - Agente Autonomo AI',
    author='Z.ai', creator='Z.ai'
)

story = []

# --- COVER ---
story.append(Spacer(1, 120))
story.append(Paragraph('<b>ANALISIS DE OPTIMIZACION</b>', styles['title']))
story.append(Paragraph('<b>Y REFACTORIZACION</b>', styles['title']))
story.append(Spacer(1, 16))
story.append(Paragraph('Agente Autonomo Local v13', styles['subtitle']))
story.append(Paragraph('ReAct + Triple Memoria + Ollama', styles['subtitle']))
story.append(Spacer(1, 40))

cover_data = [
    [Paragraph('<b>Hardware</b>', header_style), Paragraph('<b>Software</b>', header_style), Paragraph('<b>Estado</b>', header_style)],
    [Paragraph('RTX 3060 12GB', cell_style), Paragraph('Ollama v0.30.7 + CUDA', cell_style), Paragraph('v13 Produccion', cell_style)],
    [Paragraph('16GB RAM', cell_style), Paragraph('qwen2.5:14b + llama3.1:8b', cell_style), Paragraph('2397 lineas', cell_style)],
    [Paragraph('Windows 10/11', cell_style), Paragraph('Python + Streamlit', cell_style), Paragraph('15 herramientas', cell_style)],
]
story.append(make_table(cover_data, [AVAILABLE_W*0.30, AVAILABLE_W*0.40, AVAILABLE_W*0.30]))

story.append(Spacer(1, 60))
story.append(Paragraph('Documento generado el 11 de junio de 2026', ParagraphStyle(
    name='DateLine', fontName='LiberationSerif', fontSize=10, leading=14,
    alignment=TA_CENTER, textColor=TEXT_MUTED
)))
story.append(PageBreak())

# --- TOC ---
toc = TableOfContents()
toc.levelStyles = [styles['toc_h1'], styles['toc_h2']]
story.append(Paragraph('<b>Tabla de Contenidos</b>', styles['h1']))
story.append(toc)
story.append(PageBreak())

# ============================================================
# 1. DIAGNOSTICO ACTUAL
# ============================================================
story.append(heading('1. Diagnostico del Estado Actual'))

story.append(P(
    'El agente autónomo local v13 es un sistema funcional que ha evolucionado significativamente desde sus primeras versiones. '
    'Sin embargo, después de 13 iteraciones acumuladas en un único archivo de 2397 líneas, el proyecto presenta múltiples '
    'oportunidades de optimización que impactan tanto el rendimiento en producción como la mantenibilidad a largo plazo. '
    'Este análisis identifica los cuellos de botella más críticos, las redundancias de código, y las oportunidades de '
    'refactorización arquitectónica que permitirán al proyecto escalar hacia las Fases 3-5 del roadmap sin colapsar '
    'bajo su propio peso técnico.'
))

story.append(heading('1.1 Estructura del Archivo Actual', 2))

story.append(P(
    'El archivo <font name="DejaVuSans" size="9">app_auto_pro.py</font> contiene 2397 líneas que mezclan '
    'seis responsabilidades distintas sin separación de concerns: configuración global, definición de herramientas, '
    'sistema de aprendizaje, triple memoria, motor ReAct con LLM, e interfaz Streamlit. Esta estructura monolítica '
    'dificulta las pruebas unitarias, impide la reutilización de componentes, y hace que cualquier cambio en una '
    'sección pueda introducir regresiones inesperadas en otra. A continuación se detalla la distribución actual:'
))

struct_data = [
    [Paragraph('<b>Seccion</b>', header_style), Paragraph('<b>Lineas</b>', header_style),
     Paragraph('<b>Porcentaje</b>', header_style), Paragraph('<b>Responsabilidad</b>', header_style)],
    [Paragraph('Configuracion', cell_left), Paragraph('1-141', cell_style),
     Paragraph('6%', cell_style), Paragraph('Constantes, modelos, sitios web', cell_left_small)],
    [Paragraph('Herramientas', cell_left), Paragraph('142-722', cell_style),
     Paragraph('24%', cell_style), Paragraph('15 tools + busqueda de apps', cell_left_small)],
    [Paragraph('Tool Schemas', cell_left), Paragraph('723-965', cell_style),
     Paragraph('10%', cell_style), Paragraph('Esquemas JSON + mapa de funciones', cell_left_small)],
    [Paragraph('Learning System', cell_left), Paragraph('968-1050', cell_style),
     Paragraph('4%', cell_style), Paragraph('Correcciones y conocimiento', cell_left_small)],
    [Paragraph('Triple Memoria', cell_left), Paragraph('1050-1547', cell_style),
     Paragraph('21%', cell_style), Paragraph('Embeddings, VectorStore, TripleMemory', cell_left_small)],
    [Paragraph('LLM + ReAct', cell_left), Paragraph('1548-2184', cell_style),
     Paragraph('27%', cell_style), Paragraph('Ollama, _llm_generate, ReactAgent', cell_left_small)],
    [Paragraph('Streamlit UI', cell_left), Paragraph('2185-2397', cell_style),
     Paragraph('9%', cell_style), Paragraph('Interfaz grafica completa', cell_left_small)],
]
story.append(make_table(struct_data, [AVAILABLE_W*0.20, AVAILABLE_W*0.15, AVAILABLE_W*0.15, AVAILABLE_W*0.50]))
story.append(P('Tabla 1: Distribucion de lineas por seccion en app_auto_pro.py v13', 'caption'))

# ============================================================
# 2. PROBLEMAS CRITICOS DE RECURSOS
# ============================================================
story.append(heading('2. Problemas Criticos de Recursos'))

story.append(heading('2.1 Consumo de Memoria por Embeddings', 2))

story.append(P(
    'El sistema de embeddings actual presenta tres problemas de recursos que se agravan con el uso prolongado. '
    'Primero, el cache global <font name="DejaVuSans" size="9">_EMBED_CACHE</font> almacena vectores completos '
    '(768 dimensiones en nomic-embed-text) como listas de Python, lo cual consume aproximadamente 6KB por entrada. '
    'Con el limite actual de 200 entradas, esto representa 1.2MB en vectores, pero el overhead de las listas de Python '
    'es 3-4x mayor que los datos reales, elevando el consumo real a 4-5MB. Segundo, la eviction FIFO actual elimina '
    'la mitad del cache cuando se alcanza el limite, lo cual causa picos de llamadas a Ollama tras cada limpieza. '
    'Tercero, el VectorStore carga todos los vectores en memoria al primer acceso y nunca los libera.'
))

story.append(callout_box(
    '<b>Impacto:</b> Con 1000 entradas en VectorStore (max_entries), los vectores consumen ~25MB de RAM '
    'solo en datos de embeddings, mas el overhead de Python. En un sistema con 16GB RAM compartido con '
    'Ollama (que ya usa 8-10GB para qwen2.5:14b), esto reduce el margen disponible.'
))

story.append(heading('2.2 Llamadas Redundantes al LLM', 2))

story.append(P(
    'Cada iteracion del bucle ReAct invoca <font name="DejaVuSans" size="9">_llm_generate()</font>, '
    'que internamente construye los mensajes desde cero incluyendo todo el contexto de Triple Memoria. '
    'Esto significa que en una conversacion tipica de 8 iteraciones, el sistema realiza 8 llamadas completas '
    'al LLM donde cada una incluye: el system prompt completo, el historial de conversacion, el contexto '
    'de memoria, y las definiciones de herramientas. No existe ningun mecanismo de cacheo de respuestas '
    'para consultas identicas, ni un sistema de "context window" que evite reenviar informacion que el '
    'modelo ya procesó en iteraciones anteriores. En terminos practicos, esto significa que cada mensaje '
    'del usuario puede generar entre 8 y 16 llamadas HTTP a Ollama, con latencias de 2-5 segundos cada una.'
))

story.append(heading('2.3 VectorStore: Carga y Persistencia Ineficiente', 2))

story.append(P(
    'El VectorStore actual guarda vectores en un archivo JSON (<font name="DejaVuSans" size="9">vectors.json</font>) '
    'que se carga completamente en memoria al primer acceso. Cada operacion <font name="DejaVuSans" size="9">add()</font> '
    'escribe el archivo completo al disco, y cada <font name="DejaVuSans" size="9">search()</font> calcula similitud '
    'coseno contra TODOS los vectores almacenados, lo cual es O(n) en el numero de entradas. Con 500 entradas de 768 '
    'dimensiones, una busqueda requiere 384,000 multiplicaciones punto, lo cual toma ~50ms en Python puro pero podria '
    'reducirse a ~5ms con numpy optimizado o a menos de 1ms con un indice ANN (Approximate Nearest Neighbor). '
    'Ademas, el metodo <font name="DejaVuSans" size="9">_save_vectors()</font> escribe todo el diccionario como JSON '
    'en cada insercion, lo cual es extremadamente lento para stores grandes.'
))

# ============================================================
# 3. PLAN DE REFACTORIZACION ARQUITECTONICA
# ============================================================
story.append(heading('3. Plan de Refactorizacion Arquitectonica'))

story.append(P(
    'La refactorización propuesta divide el archivo monolítico en un paquete Python modular que sigue '
    'el principio de responsabilidad única. Cada módulo encapsula una funcionalidad coherente y expone '
    'una API limpia, lo cual facilita las pruebas, el mantenimiento y la extensión del sistema. La nueva '
    'estructura tambien prepara el terreno para la Fase 3 (MCP) y la Fase 5 (Multi-Agente), que requieren '
    'componentes desacoplados que puedan ejecutarse de forma independiente.'
))

story.append(heading('3.1 Estructura de Modulos Propuesta', 2))

tree_data = [
    [Paragraph('<b>Archivo</b>', header_style), Paragraph('<b>Lineas Est.</b>', header_style),
     Paragraph('<b>Contenido</b>', header_style)],
    [Paragraph('<font name="DejaVuSans" size="8">__init__.py</font>', cell_left), Paragraph('5', cell_style),
     Paragraph('Importaciones publicas del paquete', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">config.py</font>', cell_left), Paragraph('120', cell_style),
     Paragraph('Constantes, modelos, paths, sitios web', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">tools/</font>', cell_left), Paragraph('-', cell_style),
     Paragraph('Paquete de herramientas', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  commands.py</font>', cell_left), Paragraph('180', cell_style),
     Paragraph('ejecutar_comando, seguridad, validacion', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  files.py</font>', cell_left), Paragraph('120', cell_style),
     Paragraph('leer, escribir, listar, buscar en archivos', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  apps.py</font>', cell_left), Paragraph('200', cell_style),
     Paragraph('abrir_aplicacion, buscar_exe, start_menu', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  web.py</font>', cell_left), Paragraph('80', cell_style),
     Paragraph('abrir_url, buscar_youtube, buscar_web', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  dev.py</font>', cell_left), Paragraph('150', cell_style),
     Paragraph('generar_codigo, clonar_repo, instalar_dep', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  system.py</font>', cell_left), Paragraph('80', cell_style),
     Paragraph('procesos_activos, matar_proceso', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  schemas.py</font>', cell_left), Paragraph('250', cell_style),
     Paragraph('TOOL_SCHEMAS + TOOL_FUNCTIONS registry', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">memory/</font>', cell_left), Paragraph('-', cell_style),
     Paragraph('Paquete de memoria', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  embeddings.py</font>', cell_left), Paragraph('80', cell_style),
     Paragraph('Cache de embeddings, _get_embedding', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  vectorstore.py</font>', cell_left), Paragraph('200', cell_style),
     Paragraph('VectorStore con binary format', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  triple.py</font>', cell_left), Paragraph('250', cell_style),
     Paragraph('TripleMemory + session persistence', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  learning.py</font>', cell_left), Paragraph('100', cell_style),
     Paragraph('LearningSystem (correcciones, conocimiento)', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">agent/</font>', cell_left), Paragraph('-', cell_style),
     Paragraph('Paquete del motor de agente', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  llm.py</font>', cell_left), Paragraph('200', cell_style),
     Paragraph('Ollama client, _llm_generate, fallbacks', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  react.py</font>', cell_left), Paragraph('250', cell_style),
     Paragraph('ReactAgent, JSON fallback, tool execution', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  prompts.py</font>', cell_left), Paragraph('100', cell_style),
     Paragraph('SYSTEM_PROMPT, JSON_TOOLS_PROMPT', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">ui/</font>', cell_left), Paragraph('-', cell_style),
     Paragraph('Paquete de interfaz', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">  streamlit_app.py</font>', cell_left), Paragraph('200', cell_style),
     Paragraph('Interfaz Streamlit completa', cell_left_small)],
    [Paragraph('<font name="DejaVuSans" size="8">main.py</font>', cell_left), Paragraph('15', cell_style),
     Paragraph('Entry point: from ui.streamlit_app import main', cell_left_small)],
]
story.append(make_table(tree_data, [AVAILABLE_W*0.28, AVAILABLE_W*0.12, AVAILABLE_W*0.60]))
story.append(P('Tabla 2: Estructura modular propuesta (de 1 archivo a 15+ modulos)', 'caption'))

# ============================================================
# 4. OPTIMIZACIONES POR COMPONENTE
# ============================================================
story.append(heading('4. Optimizaciones Detalladas por Componente'))

story.append(heading('4.1 Optimizacion de Embeddings y VectorStore', 2))

story.append(P(
    'La optimización del subsistema de memoria vectorial es la de mayor impacto inmediato en rendimiento. '
    'Actualmente, cada busqueda semántica realiza un escaneo lineal O(n) contra todos los vectores almacenados, '
    'y cada inserción escribe el store completo a disco como JSON. Las tres optimizaciones propuestas a continuacion '
    'reducen la latencia de busqueda en 10x y el consumo de memoria en 3x sin cambiar la interfaz publica.'
))

story.append(heading('4.1.1 Formato Binario para Vectores (pickle/numpy)', 3))

story.append(P(
    'Reemplazar el almacenamiento JSON de vectores por numpy arrays serializados con pickle. Un vector de 768 '
    'float32 ocupa 3072 bytes en binario, pero 5000+ bytes en JSON (por los separadores y decimales). '
    'Con 1000 entradas, el archivo pasa de 5MB (JSON) a 3MB (pickle). Mas importante aun, cargar un numpy '
    'array desde pickle es 50x mas rapido que parsear JSON, y las operaciones de similitud coseno pueden '
    'vectorizarse con operaciones de matriz numpy en lugar de bucles Python. La implementacion requiere '
    'unicamente cambiar los metodos <font name="DejaVuSans" size="8">_save_vectors()</font> y '
    '<font name="DejaVuSans" size="8">_get_vectors()</font> del VectorStore, manteniendo la misma interfaz.'
))

story.append(heading('4.1.2 Cache LRU con OrderedDict', 3))

story.append(P(
    'El cache de embeddings actual usa un diccionario simple con eviction FIFO que elimina la mitad de las '
    'entradas cuando se llena. Esto causa picos de miss rate tras cada limpieza. Reemplazar por '
    '<font name="DejaVuSans" size="8">collections.OrderedDict</font> con eviction LRU (Least Recently Used) '
    'elimina una entrada por vez, manteniendo las mas utilizadas. Ademas, aumentar el limite de 200 a 500 '
    'entradas es seguro: 500 vectores x 6KB = 3MB, insignificante frente a los 8GB que usa Ollama. '
    'Esta optimizacion reduce las llamadas repetidas a Ollama /api/embeddings en un 40-60% durante '
    'conversaciones largas donde se buscan temas recurrentes.'
))

story.append(heading('4.1.3 Busqueda Vectorizada con numpy', 3))

story.append(P(
    'La funcion <font name="DejaVuSans" size="8">_cosine_similarity()</font> actual calcula la similitud '
    'entre dos vectores con un bucle Python, lo cual es extremadamente lento para busquedas contra stores '
    'grandes. La optimizacion consiste en almacenar todos los vectores como una matriz numpy '
    '(shape: n_entries x 768) y usar operaciones de algebra lineal vectorizadas para calcular todas las '
    'similitudes en una sola operacion. Con numpy, la busqueda en 1000 vectores pasa de ~50ms a ~3ms, '
    'un speedup de 15x. La implementacion es directa: pre-normalizar los vectores al insertarlos, y '
    'usar dot product para la busqueda (equivalente a cosine similarity cuando los vectores estan normalizados).'
))

story.append(heading('4.2 Optimizacion del Motor LLM', 2))

story.append(heading('4.2.1 Conexion Ollama Persistente', 3))

story.append(P(
    'El sistema actual intenta reconectar a Ollama en cada llamada a <font name="DejaVuSans" size="8">_llm_generate()</font> '
    'si la conexion cacheada falla, probando multiples hosts y metodos. Esto agrega 2-3 segundos de latencia en cada '
    'reconexion. La optimizacion consiste en establecer la conexion una vez al iniciar la aplicacion y mantenerla viva '
    'con un heartbeat periodico (ping a /api/tags cada 30 segundos). Si la conexion se pierde, se reintenta con '
    'backoff exponencial (1s, 2s, 4s, 8s) en lugar de probar todas las combinaciones inmediatamente. '
    'Ademas, el client singleton actual (<font name="DejaVuSans" size="8">_ollama_client</font>) no se recrea '
    'nunca una vez creado, lo cual es correcto para eficiencia pero problematico si Ollama se reinicia, ya que '
    'el client queda en un estado invalido sin mecanismo de recuperacion.'
))

story.append(heading('4.2.2 Compresion de Contexto Inteligente', 3))

story.append(P(
    'Cada llamada al LLM envia el system prompt completo, todo el historial de conversacion, el contexto de '
    'memoria, y las definiciones de herramientas. Para qwen2.5:14b con contexto de 32K tokens, esto es '
    'aceptable al inicio pero se degrada rapidamente en conversaciones largas. La optimizacion propuesta '
    'implementa tres niveles de compresion: primero, truncar respuestas anteriores del asistente a un resumen '
    'de 100 caracteres en lugar de enviar el texto completo; segundo, reemplazar las 15 definiciones de '
    'TOOL_SCHEMAS por una version comprimida que omite descripciones detalladas cuando se usa JSON fallback; '
    'tercero, implementar un cache de contexto que evite recalcular el contexto de memoria si el mensaje '
    'del usuario es similar al anterior (usando similitud coseno del embedding del mensaje). '
    'Esta optimizacion puede reducir el uso de tokens en un 30-50% en conversaciones de mas de 10 intercambios.'
))

story.append(heading('4.2.3 Timeout Inteligente y Retry Adaptativo', 3))

story.append(P(
    'El timeout actual es fijo: 180s para modelos de 14b+ y 120s para el resto. Sin embargo, el tiempo '
    'de respuesta de Ollama varia dramaticamente segun la carga del sistema y la longitud del prompt. '
    'La optimizacion implementa un timeout adaptativo basado en el historial de respuestas: se mantiene '
    'un promedio movil de los ultimos 10 tiempos de respuesta, y el timeout se configura como '
    '2x el promedio + 30s. Ademas, se implementa retry con backoff exponencial para errores transitorios '
    '(timeout, connection reset), evitando el patron actual de probar todas las combinaciones de '
    'host/metodo/modelo en cada fallo.'
))

story.append(heading('4.3 Optimizacion del Sistema de Herramientas', 2))

story.append(heading('4.3.1 Registry Dinamico de Herramientas', 3))

story.append(P(
    'Actualmente, las 15 herramientas estan divididas en tres secciones del codigo (herramientas basicas, '
    'herramientas v11, y busqueda de aplicaciones) con sus esquemas JSON definidos en una lista separada '
    'y un diccionario de funciones que las mapea. Este patron hace que agregar una nueva herramienta '
    'requiera tocar tres archivos: la funcion, el esquema, y el diccionario. La refactorizacion propone '
    'un decorador <font name="DejaVuSans" size="8">@tool</font> que registra automaticamente la funcion '
    'y su esquema en un registry centralizado. Esto reduce el boilerplate de agregar herramientas de '
    '3 puntos de edicion a 1, y permite cargar herramientas dinamicamente desde plugins en la Fase 3.'
))

story.append(heading('4.3.2 Ejecucion Paralela de Herramientas Independientes', 3))

story.append(P(
    'El bucle ReAct actual ejecuta herramientas secuencialmente, una por iteracion. Sin embargo, en muchos '
    'casos el agente podria ejecutar multiples herramientas independientes en paralelo (por ejemplo, '
    'leer un archivo Y buscar en web simultaneamente). La optimizacion implementa deteccion de independencia: '
    'si el LLM devuelve multiples tool calls en una respuesta, se ejecutan en paralelo usando '
    '<font name="DejaVuSans" size="8">concurrent.futures.ThreadPoolExecutor</font>. Esto reduce la latencia '
    'total de 2 llamadas secuenciales de 5s cada una a 5s en paralelo, un speedup de 2x. '
    'Es importante notar que el soporte para multiples tool calls ya existe parcialmente en el codigo '
    'actual, pero solo se ejecuta el primer tool call de la lista.'
))

# ============================================================
# 5. PLAN POR FASES
# ============================================================
story.append(heading('5. Plan de Implementacion por Fases del Roadmap'))

story.append(P(
    'A continuacion se detalla como integrar las optimizaciones y refactorizaciones propuestas con el '
    'roadmap de 5 fases del proyecto. Cada fase incluye las optimizaciones de recursos que corresponden, '
    'la refactorizacion necesaria para soportar las nuevas funcionalidades, y las dependencias entre fases. '
    'El enfoque es incremental: cada fase deja el proyecto en un estado estable y funcional, sin romper '
    'las funcionalidades existentes.'
))

story.append(heading('5.1 Fase 1: ReAct + Function Calling (Completada)', 2))

phase1_data = [
    [Paragraph('<b>Aspecto</b>', header_style), Paragraph('<b>Estado</b>', header_style),
     Paragraph('<b>Notas</b>', header_style)],
    [Paragraph('ReAct Loop', cell_left), Paragraph('Completo', cell_style),
     Paragraph('8 iteraciones max, think-act-observe', cell_left_small)],
    [Paragraph('Function Calling', cell_left), Paragraph('Completo', cell_style),
     Paragraph('Nativo (qwen3) + JSON fallback (qwen2.5)', cell_left_small)],
    [Paragraph('15 Herramientas', cell_left), Paragraph('Completo', cell_style),
     Paragraph('Incluye abrir_url, buscar_youtube', cell_left_small)],
    [Paragraph('Multi-modelo', cell_left), Paragraph('Completo', cell_style),
     Paragraph('Auto-deteccion, fallback automatico', cell_left_small)],
    [Paragraph('Seguridad', cell_left), Paragraph('Completo', cell_style),
     Paragraph('COMANDOS_PELIGROSOS + path traversal', cell_left_small)],
]
story.append(make_table(phase1_data, [AVAILABLE_W*0.25, AVAILABLE_W*0.15, AVAILABLE_W*0.60]))

story.append(heading('5.2 Fase 2: Triple Memoria + Contexto Enriquecido (80% Completada)', 2))

story.append(P(
    'La Fase 2 esta funcionalmente completa al 80%. Las funcionalidades implementadas incluyen: VectorStore '
    'casero con embeddings de Ollama, cache de embeddings con eviction FIFO, TripleMemory con budget de '
    'contexto (3000 chars), persistencia de sesion con TTL de 24 horas, y resumen de conversacion (simple y LLM). '
    'Sin embargo, quedan pendientes optimizaciones criticas que afectan el rendimiento en produccion y que son '
    'prerrequisito para las fases posteriores.'
))

f2_pending = [
    [Paragraph('<b>Optimizacion Pendiente</b>', header_style), Paragraph('<b>Impacto</b>', header_style),
     Paragraph('<b>Tiempo</b>', header_style), Paragraph('<b>Prioridad</b>', header_style)],
    [Paragraph('VectorStore: formato binario (pickle/numpy)', cell_left_small),
     Paragraph('3x menos RAM, 50x carga mas rapida', cell_left_small),
     Paragraph('2h', cell_style), Paragraph('Alta', cell_style)],
    [Paragraph('Embedding cache: LRU con OrderedDict', cell_left_small),
     Paragraph('40-60% menos llamadas a Ollama', cell_left_small),
     Paragraph('1h', cell_style), Paragraph('Alta', cell_style)],
    [Paragraph('Busqueda vectorizada con numpy', cell_left_small),
     Paragraph('15x mas rapido en stores grandes', cell_left_small),
     Paragraph('2h', cell_style), Paragraph('Alta', cell_style)],
    [Paragraph('VectorStore: append-only (no reescribir todo)', cell_left_small),
     Paragraph('Escritura instantanea vs 100ms+', cell_left_small),
     Paragraph('1.5h', cell_style), Paragraph('Media', cell_style)],
    [Paragraph('TripleMemory: compresion de contexto inteligente', cell_left_small),
     Paragraph('30-50% menos tokens por llamada LLM', cell_left_small),
     Paragraph('3h', cell_style), Paragraph('Media', cell_style)],
    [Paragraph('Qdrant integration (opcional, upgrade futuro)', cell_left_small),
     Paragraph('Busqueda ANN sub-millisecond', cell_left_small),
     Paragraph('4h', cell_style), Paragraph('Baja', cell_style)],
]
story.append(make_table(f2_pending, [AVAILABLE_W*0.35, AVAILABLE_W*0.30, AVAILABLE_W*0.10, AVAILABLE_W*0.12]))
story.append(P('Tabla 3: Optimizaciones pendientes de Fase 2 con estimaciones', 'caption'))

story.append(heading('5.3 Fase 3: MCP + Metacognicion', 2))

story.append(P(
    'La Fase 3 introduce dos capacidades transformadoras. Primero, el protocolo MCP (Model Context Protocol) '
    'permite que el agente se comunique con servidores de herramientas externas, exactamente como lo hace '
    'Open Design con su comando <font name="DejaVuSans" size="8">od mcp install</font>. Esto transforma el '
    'agente de un sistema cerrado con 15 herramientas hardcodeadas a una plataforma extensible donde cualquier '
    'servicio puede exponer capacidades al agente. Segundo, la metacognicion permite que el agente evalúe '
    'su propia confianza en las respuestas, decida cuando necesita mas informacion, y detecte cuando esta '
    'entrando en un bucle improductivo en el ReAct loop.'
))

story.append(P(
    'La refactorizacion modular propuesta en la Seccion 3 es un prerrequisito critico para esta fase. '
    'Sin ella, implementar MCP requeriria modificaciones en al menos 8 puntos diferentes del archivo '
    'monolitico, con alto riesgo de regresiones. Con la estructura modular, MCP se implementa como un '
    'nuevo modulo <font name="DejaVuSans" size="8">agent/mcp_client.py</font> que se integra al '
    'ReactAgent a traves del registry de herramientas, sin modificar el codigo existente. '
    'La metacognicion se implementa como un decorador que envuelve las llamadas al LLM, evaluando la '
    'confianza de la respuesta y decidiendo si se necesita una iteracion adicional.'
))

f3_data = [
    [Paragraph('<b>Componente</b>', header_style), Paragraph('<b>Descripcion</b>', header_style),
     Paragraph('<b>Tiempo</b>', header_style)],
    [Paragraph('Refactor: monolito a modulos', cell_left_small),
     Paragraph('Separar en paquetes tools/, memory/, agent/, ui/', cell_left_small),
     Paragraph('4-6h', cell_style)],
    [Paragraph('MCP Client', cell_left_small),
     Paragraph('Conexion a servidores MCP externos, discovery de tools', cell_left_small),
     Paragraph('3-4h', cell_style)],
    [Paragraph('MCP Tool Registry', cell_left_small),
     Paragraph('Fusionar tools locales + MCP en un registry unificado', cell_left_small),
     Paragraph('2h', cell_style)],
    [Paragraph('Metacognicion: confianza', cell_left_small),
     Paragraph('Auto-evaluacion de certeza en respuestas', cell_left_small),
     Paragraph('2h', cell_style)],
    [Paragraph('Metacognicion: loop detection', cell_left_small),
     Paragraph('Detectar iteraciones ReAct improductivas', cell_left_small),
     Paragraph('1.5h', cell_style)],
    [Paragraph('Testing integrado', cell_left_small),
     Paragraph('Tests unitarios por modulo + tests de integracion', cell_left_small),
     Paragraph('2h', cell_style)],
]
story.append(make_table(f3_data, [AVAILABLE_W*0.25, AVAILABLE_W*0.55, AVAILABLE_W*0.12]))

story.append(heading('5.4 Fase 4: Multimodal + Guardrails', 2))

story.append(P(
    'La Fase 4 anade capacidades de vision (analisis de imagenes, capturas de pantalla) y guardrails '
    '(limites de seguridad para prevenir comportamientos peligrosos o indeseados). La vision se implementa '
    'usando modelos multimodales de Ollama como llava o qwen2.5-vl, que pueden procesar imagenes junto '
    'con texto. Los guardrails incluyen: validacion de salida (evitar que el agente genere codigo peligroso), '
    'limites de accion (maximo de comandos ejecutados por sesion), y filtros de contenido (detectar '
    'instrucciones de inyeccion de prompt). Esta fase requiere la estructura modular para poder agregar '
    'un modulo <font name="DejaVuSans" size="8">agent/guardrails.py</font> sin modificar el motor ReAct.'
))

story.append(heading('5.5 Fase 5: Multi-Agente + Workflow Engine', 2))

story.append(P(
    'La Fase 5 es la mas ambiciosa: transforma el agente unico en un sistema multi-agente donde diferentes '
    'agentes especializados colaboran en tareas complejas. Un workflow engine orquesta la comunicacion entre '
    'agentes, asigna subtareas, y fusiona resultados. Esta fase se beneficia enormemente de la refactorizacion '
    'modular, ya que cada agente es esencialmente una instancia del ReactAgent con su propio system prompt, '
    'herramientas y memoria. Sin la separacion de concerns, implementar multi-agente en un archivo de 2400+ '
    'lineas seria practicamente imposible de mantener. El workflow engine se implementa como un modulo '
    'independiente <font name="DejaVuSans" size="8">agent/workflow.py</font> que coordina agentes '
    'a traves de una cola de mensajes compartida.'
))

# ============================================================
# 6. RESUMEN DE IMPACTO
# ============================================================
story.append(heading('6. Resumen de Impacto Estimado'))

impact_data = [
    [Paragraph('<b>Optimizacion</b>', header_style), Paragraph('<b>Antes</b>', header_style),
     Paragraph('<b>Despues</b>', header_style), Paragraph('<b>Mejora</b>', header_style)],
    [Paragraph('Busqueda vectorial (1000 entradas)', cell_left_small),
     Paragraph('50ms', cell_style), Paragraph('3ms', cell_style), Paragraph('15x', cell_style)],
    [Paragraph('Carga de VectorStore desde disco', cell_left_small),
     Paragraph('200ms', cell_style), Paragraph('4ms', cell_style), Paragraph('50x', cell_style)],
    [Paragraph('RAM de vectores (1000 entries)', cell_left_small),
     Paragraph('25MB', cell_style), Paragraph('8MB', cell_style), Paragraph('3x', cell_style)],
    [Paragraph('Cache miss rate en embeddings', cell_left_small),
     Paragraph('40%', cell_style), Paragraph('15%', cell_style), Paragraph('2.7x', cell_style)],
    [Paragraph('Tokens por llamada LLM (conv. larga)', cell_left_small),
     Paragraph('4000', cell_style), Paragraph('2500', cell_style), Paragraph('1.6x', cell_style)],
    [Paragraph('Tiempo para agregar herramienta nueva', cell_left_small),
     Paragraph('3 archivos', cell_style), Paragraph('1 decorador', cell_style), Paragraph('3x', cell_style)],
    [Paragraph('Tests unitarios posibles', cell_left_small),
     Paragraph('0', cell_style), Paragraph('Por modulo', cell_style), Paragraph('Infinito', cell_style)],
    [Paragraph('Preparacion para MCP (Fase 3)', cell_left_small),
     Paragraph('8 puntos de edicion', cell_style), Paragraph('1 modulo nuevo', cell_style), Paragraph('8x', cell_style)],
]
story.append(make_table(impact_data, [AVAILABLE_W*0.30, AVAILABLE_W*0.18, AVAILABLE_W*0.20, AVAILABLE_W*0.15]))
story.append(P('Tabla 4: Resumen de impacto cuantitativo de las optimizaciones propuestas', 'caption'))

story.append(Spacer(1, 24))
story.append(callout_box(
    '<b>Recomendacion principal:</b> Completar las optimizaciones de Fase 2 (5-8 horas) ANTES de iniciar '
    'la refactorizacion modular. Esto permite validar las mejoras de rendimiento en la arquitectura actual '
    'y tener una baseline clara antes de reestructurar el codigo. La refactorizacion modular (Fase 3) '
    'es el prerrequisito critico para las Fases 4 y 5.'
))

# ============================================================
# BUILD
# ============================================================
doc.multiBuild(story)
print(f"PDF generado: {output_path}")
