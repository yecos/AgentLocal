const {
  Document, Packer, Paragraph, TextRun, Table, TableCell, TableRow,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  PageBreak, TableOfContents, Header, Footer, PageNumber, NumberFormat,
  TabStopType, TabStopPosition
} = require("docx");
const fs = require("fs");

// ============================================================
// PALETTE: Dawn Mist Tech (Cool+Light+Active) — ideal for dev docs
// ============================================================
const palette = {
  primary: "1B2A4A",    // Deep navy
  body: "2D3748",       // Dark slate
  secondary: "4A5568",  // Medium gray
  accent: "3182CE",     // Bright blue
  surface: "EBF4FF",    // Very light blue
  accentLight: "BEE3F8",
  white: "FFFFFF",
  codeBg: "F7FAFC",
  codeText: "2D3748",
  warn: "DD6B20",
  success: "38A169",
};

// ============================================================
// HELPER FUNCTIONS
// ============================================================

function heading1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 200, line: 312 },
    children: [new TextRun({ text, font: "SimHei", size: 32, color: palette.primary, bold: true })],
  });
}

function heading2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 160, line: 312 },
    children: [new TextRun({ text, font: "SimHei", size: 28, color: palette.accent, bold: true })],
  });
}

function heading3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 120, line: 312 },
    children: [new TextRun({ text, font: "SimHei", size: 24, color: palette.primary, bold: true })],
  });
}

function bodyText(text) {
  return new Paragraph({
    spacing: { after: 120, line: 312 },
    indent: { firstLine: 420 },
    children: [new TextRun({ text, font: "Microsoft YaHei", size: 21, color: palette.body })],
  });
}

function bodyTextNoIndent(text) {
  return new Paragraph({
    spacing: { after: 120, line: 312 },
    children: [new TextRun({ text, font: "Microsoft YaHei", size: 21, color: palette.body })],
  });
}

function boldBodyText(text) {
  return new Paragraph({
    spacing: { after: 120, line: 312 },
    children: [new TextRun({ text, font: "Microsoft YaHei", size: 21, color: palette.primary, bold: true })],
  });
}

function codeBlock(lines) {
  return lines.map(line => new Paragraph({
    spacing: { after: 0, line: 276 },
    shading: { type: ShadingType.CLEAR, fill: palette.codeBg },
    indent: { left: 360 },
    children: [new TextRun({
      text: line,
      font: "Consolas",
      size: 18,
      color: palette.codeText,
    })],
  }));
}

function bulletItem(text, level = 0) {
  return new Paragraph({
    spacing: { after: 80, line: 312 },
    indent: { left: 420 + level * 360 },
    bullet: { level },
    children: [new TextRun({ text, font: "Microsoft YaHei", size: 21, color: palette.body })],
  });
}

function bulletItemBold(boldText, normalText, level = 0) {
  return new Paragraph({
    spacing: { after: 80, line: 312 },
    indent: { left: 420 + level * 360 },
    bullet: { level },
    children: [
      new TextRun({ text: boldText, font: "Microsoft YaHei", size: 21, color: palette.primary, bold: true }),
      new TextRun({ text: normalText, font: "Microsoft YaHei", size: 21, color: palette.body }),
    ],
  });
}

function warnBox(text) {
  return new Paragraph({
    spacing: { before: 120, after: 120, line: 312 },
    indent: { left: 360, right: 360 },
    shading: { type: ShadingType.CLEAR, fill: "FFFBEB" },
    border: { left: { style: BorderStyle.SINGLE, size: 12, color: palette.warn } },
    children: [
      new TextRun({ text: "\u26A0 ", font: "Microsoft YaHei", size: 21, color: palette.warn, bold: true }),
      new TextRun({ text, font: "Microsoft YaHei", size: 21, color: palette.body }),
    ],
  });
}

function tipBox(text) {
  return new Paragraph({
    spacing: { before: 120, after: 120, line: 312 },
    indent: { left: 360, right: 360 },
    shading: { type: ShadingType.CLEAR, fill: "F0FFF4" },
    border: { left: { style: BorderStyle.SINGLE, size: 12, color: palette.success } },
    children: [
      new TextRun({ text: "\u2713 ", font: "Microsoft YaHei", size: 21, color: palette.success, bold: true }),
      new TextRun({ text, font: "Microsoft YaHei", size: 21, color: palette.body }),
    ],
  });
}

function spacer(h = 120) {
  return new Paragraph({ spacing: { before: h, after: 0 }, children: [] });
}

function makeInfoTable(rows) {
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: rows.map((row, idx) =>
      new TableRow({
        tableHeader: idx === 0,
        children: row.map(cell =>
          new TableCell({
            shading: idx === 0
              ? { type: ShadingType.CLEAR, fill: palette.primary }
              : { type: ShadingType.CLEAR, fill: idx % 2 === 0 ? palette.surface : palette.white },
            margins: { top: 60, bottom: 60, left: 120, right: 120 },
            children: [new Paragraph({
              spacing: { after: 0, line: 276 },
              children: [new TextRun({
                text: cell,
                font: "Microsoft YaHei",
                size: 18,
                color: idx === 0 ? palette.white : palette.body,
                bold: idx === 0,
              })],
            })],
          })
        ),
      })
    ),
  });
}

// ============================================================
// DOCUMENT CONTENT
// ============================================================

const coverSection = {
  properties: {
    page: {
      size: { width: 11906, height: 16838 },
      margin: { top: 0, bottom: 0, left: 0, right: 0 },
    },
  },
  children: [
    // Full-page wrapper table
    new Table({
      width: { size: 100, type: WidthType.PERCENTAGE },
      rows: [new TableRow({
        height: { value: 16838, rule: "exact" },
        children: [new TableCell({
          width: { size: 100, type: WidthType.PERCENTAGE },
          shading: { type: ShadingType.CLEAR, fill: palette.primary },
          verticalAlign: "center",
          margins: { top: 0, bottom: 0, left: 1200, right: 1200 },
          borders: {
            top: { style: BorderStyle.NONE, size: 0 },
            bottom: { style: BorderStyle.NONE, size: 0 },
            left: { style: BorderStyle.NONE, size: 0 },
            right: { style: BorderStyle.NONE, size: 0 },
          },
          children: [
            spacer(2400),
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({
                text: "AGENTE LOCAL AUTONOMO",
                font: "SimHei",
                size: 52,
                color: palette.white,
                bold: true,
              })],
            }),
            spacer(120),
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({
                text: "Guia de Refactoring + Optimizacion v14",
                font: "Microsoft YaHei",
                size: 32,
                color: palette.accentLight,
              })],
            }),
            spacer(200),
            new Paragraph({
              alignment: AlignmentType.CENTER,
              border: { top: { style: BorderStyle.SINGLE, size: 6, color: palette.accent } },
              spacing: { before: 200, after: 200 },
              children: [],
            }),
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({
                text: "De 2240 lineas monoliticas a una arquitectura modular,",
                font: "Microsoft YaHei",
                size: 22,
                color: palette.accentLight,
              })],
            }),
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({
                text: "optimizada para RTX 3060 12GB + 16GB RAM",
                font: "Microsoft YaHei",
                size: 22,
                color: palette.accentLight,
              })],
            }),
            spacer(1600),
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({
                text: "Fase 2 completacion | Roadmap Fase 3-5",
                font: "Microsoft YaHei",
                size: 20,
                color: "A0AEC0",
              })],
            }),
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({
                text: "Junio 2026",
                font: "Microsoft YaHei",
                size: 20,
                color: "A0AEC0",
              })],
            }),
          ],
        })],
      })],
    }),
  ],
};

// TOC Section
const tocSection = {
  properties: {
    page: {
      size: { width: 11906, height: 16838 },
      margin: { top: 1440, bottom: 1440, left: 1701, right: 1417 },
    },
  },
  children: [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 400, after: 300, line: 312 },
      children: [new TextRun({ text: "CONTENIDO", font: "SimHei", size: 32, color: palette.primary, bold: true })],
    }),
    new TableOfContents("Tabla de Contenido", {
      hyperlink: true,
      headingStyleRange: "1-3",
    }),
    new Paragraph({
      children: [new PageBreak()],
    }),
  ],
};

// Body content
const bodyChildren = [
  // ===========================
  // SECTION 1: DIAGNOSTICO
  // ===========================
  heading1("1. Diagnostico del Estado Actual (v13)"),
  bodyText("El agente autonomo v13 es un archivo monolitico de 2240 lineas que combina 7 dominios funcionales diferentes en un solo archivo. Esto funciono para iterar rapido en las fases 1-2, pero ahora se convierte en un obstaculo para escalar hacia las fases 3-5 del roadmap. A continuacion se detalla el diagnostico completo de problemas y oportunidades."),

  heading2("1.1 Problemas Estructurales"),
  bodyText("El archivo app_auto_pro.py mezcla responsabilidades que deberian estar separadas: la logica de herramientas (15 funciones), el sistema de memoria (3 clases), la conexion con el LLM (3 estrategias de fallback), el motor ReAct (1 clase), el sistema de aprendizaje (1 clase) y la interfaz Streamlit (1 funcion). Modificar cualquier componente requiere entender todo el archivo, y un error en cualquier parte puede romper todo el sistema."),
  bulletItemBold("Acoplamiento total: ", "generar_codigo() llama a _llm_generate() directamente, creando una dependencia circular entre herramientas y el LLM. Las herramientas deberian ser funciones puras que reciben resultados del LLM, no que lo invocan."),
  bulletItemBold("Variables globales mutables: ", "_EMBED_CACHE, _exe_cache, _ollama_client, _detected_model, AGENT_MODEL, FALLBACK_MODEL son mutados desde multiples funciones sin control. Esto hace imposible testing unitario y causa race conditions en Streamlit."),
  bulletItemBold("Duplicacion: ", "Leer_archivo() y generar_codigo() ambos leen/escriben archivos con la misma logica de validacion. _get_available_models() esta definida como funcion global Y como metodo de ReactAgent con el mismo codigo exacto."),

  heading2("1.2 Problemas de Recursos"),
  bodyText("Con una RTX 3060 de 12GB VRAM y 16GB RAM, cada byte cuenta. El sistema actual tiene varias ineficiencias que consumen memoria innecesariamente y ralentizan la inferencia del LLM."),
  makeInfoTable([
    ["Problema", "Impacto", "Solucion Propuesta"],
    ["VectorStore carga TODO en memoria", "Con 1000+ entradas, vectors.json puede pesar 50MB+", "Carga lazy por pagina, solo los indices en RAM"],
    ["_EMBED_CACHE FIFO ineficiente", "Borra la mitad del cache de golpe", "Usar OrderedDict con LRU real (moviendo al final)"],
    ["Embeddings se calculan 2 veces", "En add() y search() de VectorStore", "Verificar cache ANTES de llamar a Ollama"],
    ["_llm_generate prueba 2-4 combinaciones", "Cada intento bloquea el hilo 10-180s", "Cache permanente de conexion exitosa + timeout agresivo"],
    ["conversation_history + short_term", "2 copias de la misma conversacion", "Eliminar conversation_history, usar solo TripleMemory"],
    ["subprocess.run shell=True", "Inicia cmd.exe completo por comando", "Para comandos simples, usar subprocess sin shell"],
    ["leer_archivo() escanea REPOS_DIR", "os.listdir() en cada llamada de lectura", "Cache de directorio con TTL corto"],
  ]),

  heading2("1.3 Problema Critico: analizar_proyecto()"),
  bodyText("La funcion analizar_proyecto() es el ejemplo perfecto de por que el agente no puede entender repositorios. Solo hace 8 checks de existencia de archivos (package.json = Node.js, requirements.txt = Python, etc.) sin leer NINGUN contenido. Cuando el usuario pidio analizar nexu-io/open-design, el agente solo detecto 'Node.js + Git + README' en vez de entender que es un monorepo pnpm con MCP server, 259+ skills y arquitectura de plugins."),
  bodyText("La solucion es una funcion que realmente LEA los archivos clave del proyecto: package.json para dependencias, README.md para descripcion, pyproject.toml para configuracion, y cualquier archivo de configuracion que revele la arquitectura real del proyecto. Esto transforma la herramienta de un listado superficial a un analisis significativo."),

  // ===========================
  // SECTION 2: ARQUITECTURA MODULAR
  // ===========================
  heading1("2. Arquitectura Modular Propuesta"),
  bodyText("La refactorizacion divide el monolito en 6 modulos con responsabilidades claras. Cada modulo puede testearse independientemente y la interfaz Streamlit se convierte en un cliente ligero que importa los modulos que necesita."),

  heading2("2.1 Estructura de Directorios"),
  ...codeBlock([
    "agente_v14/",
    "\u251C\u2500\u2500 app.py                  # Entry point Streamlit (50 lineas)",
    "\u251C\u2500\u2500 config.py               # Configuracion centralizada",
    "\u251C\u2500\u2500 llm.py                  # Conexion Ollama + cache",
    "\u251C\u2500\u2500 memory/",
    "\u2502   \u251C\u2500\u2500 __init__.py",
    "\u2502   \u251C\u2500\u2500 vectorstore.py      # VectorStore casero",
    "\u2502   \u251C\u2500\u2500 triple_memory.py    # TripleMemory",
    "\u2502   \u2514\u2500\u2500 learning.py         # LearningSystem",
    "\u251C\u2500\u2500 tools/",
    "\u2502   \u251C\u2500\u2500 __init__.py          # Registro de herramientas",
    "\u2502   \u251C\u2500\u2500 sistema.py           # ejecutar_comando, procesos, etc.",
    "\u2502   \u251C\u2500\u2500 archivos.py          # leer, escribir, listar, buscar",
    "\u2502   \u251C\u2500\u2500 apps.py              # abrir_aplicacion, abrir_url, youtube",
    "\u2502   \u251C\u2500\u2500 proyecto.py          # analizar_proyecto MEJORADO",
    "\u2502   \u251C\u2500\u2500 codigo.py            # generar_codigo",
    "\u2502   \u2514\u2500\u2500 web.py               # buscar_web",
    "\u251C\u2500\u2500 agent/",
    "\u2502   \u251C\u2500\u2500 __init__.py",
    "\u2502   \u251C\u2500\u2500 react.py             # ReactAgent (bucle principal)",
    "\u2502   \u2514\u2500\u2500 schemas.py           # TOOL_SCHEMAS + TOOL_FUNCTIONS",
    "\u2514\u2500\u2500 utils/",
    "    \u251C\u2500\u2500 __init__.py",
    "    \u251C\u2500\u2500 security.py           # COMANDOS_PELIGROSOS, validar, sanitizar",
    "    \u2514\u2500\u2500 helpers.py            # _strip_prefixes, _open_browser, etc.",
  ]),

  heading2("2.2 Diagrama de Dependencias"),
  bodyText("Las dependencias fluyen en una sola direccion: app.py importa de agent/, agent/ importa de tools/ y memory/, y estos importan de config.py y utils/. Nunca hay dependencias circulares. El modulo llm.py es la unica conexion con Ollama y es importado por agent/ y tools/codigo.py."),
  ...codeBlock([
    "app.py (UI)",
    "  \u2192 agent/react.py",
    "      \u2192 tools/* (funciones)",
    "      \u2192 memory/triple_memory.py",
    "      \u2192 llm.py",
    "  \u2192 config.py (constantes)",
    "  \u2192 utils/* (helpers)",
  ]),
  tipBox("Regla de oro: Si el modulo A importa al modulo B, entonces B NUNCA debe importar A. Si necesitas comunicacion inversa, usa callbacks o inyeccion de dependencias."),

  heading2("2.3 config.py - Configuracion Centralizada"),
  bodyText("Actualmente las constantes estan esparcidas por todo el archivo. Al centralizarlas, cualquier cambio (como agregar un nuevo directorio permitido o cambiar el modelo preferido) se hace en un solo lugar. Ademas, se puede cargar configuracion desde un archivo JSON externo para personalizacion sin tocar codigo."),
  ...codeBlock([
    "# config.py",
    "import os, platform",
    "from pathlib import Path",
    "",
    "# Deteccion de SO",
    "IS_WINDOWS = platform.system() == 'Windows'",
    "",
    "# Directorios",
    "REPOS_DIR = os.path.join(os.path.expanduser('~'), 'Documents' if IS_WINDOWS else 'repos')",
    "LEARN_DIR = os.path.join(os.path.expanduser('~'), '.ia-local', 'learning')",
    "os.makedirs(REPOS_DIR, exist_ok=True)",
    "os.makedirs(LEARN_DIR, exist_ok=True)",
    "",
    "# Modelos",
    "PREFERRED_MODELS = ['qwen3:4b', 'qwen3-coder', 'qwen3:30b-a3b', 'qwen2.5:14b', 'llama3.1:8b']",
    "",
    "# Limites",
    "MAX_REACT_ITERATIONS = 8",
    "MAX_CONVERSATION_MEMORY = 20",
    "MAX_CONTEXT_CHARS = 3000",
    "MAX_FILE_READ = 8000",
    "MAX_TOOL_OUTPUT = 3000",
    "",
    "# Archivos de datos",
    "CORRECTIONS_FILE = os.path.join(LEARN_DIR, 'corrections.json')",
    "FEEDBACK_FILE = os.path.join(LEARN_DIR, 'feedback.json')",
    "PATTERNS_FILE = os.path.join(LEARN_DIR, 'patterns.json')",
    "KNOWLEDGE_FILE = os.path.join(LEARN_DIR, 'knowledge.json')",
  ]),

  heading2("2.4 llm.py - Conexion Ollama Optimizada"),
  bodyText("El modulo llm.py es el mas critico para la optimizacion de recursos. Actualmente _llm_generate() intenta multiples combinaciones de modelo/host/metodo en cada llamada fallida, lo cual puede tardar minutos. La version optimizada usa un cache permanente de conexion exitosa, un timeout agresivo con un solo reintento, y elimina la variable global mutable _ollama_client en favor de un patron singleton limpio."),
  ...codeBlock([
    "# llm.py",
    "import json, logging, os",
    "from datetime import datetime",
    "from config import PREFERRED_MODELS, LEARN_DIR",
    "",
    "logger = logging.getLogger('agente.llm')",
    "",
    "class OllamaClient:",
    "    \"\"\"Singleton que cachea la conexion exitosa.\"\"\"",
    "    _instance = None",
    "    ",
    "    def __init__(self):",
    "        self.model = None",
    "        self.fallback_model = None",
    "        self.host = None",
    "        self.method = None  # 'client' or 'http'",
    "        self.embed_model = None",
    "        self._models_list = None",
    "        self._detected = False",
    "    ",
    "    @classmethod",
    "    def get(cls):",
    "        if cls._instance is None:",
    "            cls._instance = cls()",
    "        return cls._instance",
    "    ",
    "    def detect_models(self):",
    "        \"\"\"Detecta modelos disponibles. Se ejecuta 1 vez.\"\"\"",
    "        if self._detected:",
    "            return",
    "        available = self._fetch_available()",
    "        # ... logica de seleccion (igual que antes) ...",
    "        self._detected = True",
    "    ",
    "    def generate(self, messages, tools=None, timeout_overwrite=None):",
    "        \"\"\"Genera respuesta. Usa cache de conexion. 1 reintento max.\"\"\"",
    "        self.detect_models()",
    "        # 1. Probar conexion cacheada (rapido)",
    "        result = self._try_cached(messages, tools, timeout_overwrite)",
    "        if result is not None:",
    "            return result",
    "        # 2. Buscar nueva conexion (1 intento)",
    "        result = self._try_fresh(messages, tools)",
    "        return result or ''",
    "",
    "ollama = OllamaClient.get()  # Singleton global",
  ]),
  warnBox("No elimines las 3 estrategias de fallback (client, global, http). Son necesarias porque la libreria ollama de Python no siempre esta instalada o no siempre soporta tools. Lo que SI debes eliminar es el bucle que prueba TODAS las combinaciones en cada llamada fallida."),

  // ===========================
  // SECTION 3: MEJORAR analizar_proyecto
  // ===========================
  heading1("3. Mejorar analizar_proyecto() - La Herramienta Clave"),
  bodyText("Esta es la mejora con mayor impacto en la calidad del agente. La version actual solo detecta la presencia de archivos; la nueva version lee los archivos clave y extrae informacion significativa. La funcion pasa de 35 lineas superficiales a ~150 lineas que realmente entienden el proyecto."),

  heading2("3.1 Analisis Actual vs Propuesto"),
  makeInfoTable([
    ["Aspecto", "v13 (Actual)", "v14 (Propuesto)"],
    ["Estructura", "Arbol de archivos plano", "Arbol + estadisticas (archivos por tipo, tamaño total)"],
    ["Deteccion", "8 checks de existencia", "20+ patrones con lectura de contenido"],
    ["package.json", "Solo detecta que existe", "Lee nombre, version, dependencias, scripts"],
    ["README.md", "Solo detecta que existe", "Lee primeros 500 chars como descripcion"],
    ["Monorepo", "No detecta", "Detecta workspaces, pnpm-workspace, lerna"],
    ["Framework", "Solo Next.js", "React, Vue, Angular, FastAPI, Django, Flask, Express"],
    ["Testing", "No detecta", "Detecta jest, pytest, vitest, mocha"],
    ["CI/CD", "No detecta", "Detecta .github/workflows, Dockerfile, docker-compose"],
    ["Lenguajes", "Node.js/Python binario", "Conteo real por extension de archivo"],
  ]),

  heading2("3.2 Codigo Completo de la Nueva Funcion"),
  bodyText("El siguiente codigo reemplaza completamente la funcion analizar_proyecto() actual. Se divide en 3 fases: (1) escaneo de estructura con estadisticas, (2) lectura inteligente de archivos clave, y (3) resumen con detecciones. El resultado es un texto rico que el LLM puede usar para entender realmente el proyecto."),
  ...codeBlock([
    "# tools/proyecto.py",
    "import os, json, re",
    "from config import REPOS_DIR",
    "",
    "# Extensiones reconocidas por lenguaje",
    "LANG_EXTENSIONS = {",
    "    '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',",
    "    '.jsx': 'React JSX', '.tsx': 'React TSX', '.vue': 'Vue',",
    "    '.html': 'HTML', '.css': 'CSS', '.scss': 'SCSS',",
    "    '.json': 'JSON', '.md': 'Markdown', '.yaml': 'YAML',",
    "    '.yml': 'YAML', '.toml': 'TOML', '.rs': 'Rust',",
    "    '.go': 'Go', '.java': 'Java', '.rb': 'Ruby',",
    "}",
    "",
    "def _resolve_path(ruta):",
    "    \"\"\"Resuelve una ruta relativa dentro de REPOS_DIR.\"\"\"",
    "    if not os.path.exists(ruta):",
    "        alt = os.path.join(REPOS_DIR, ruta) if not os.path.isabs(ruta) else ruta",
    "        if os.path.exists(alt):",
    "            return alt",
    "        return None",
    "    return ruta",
    "",
    "def _safe_read(filepath, max_chars=2000):",
    "    \"\"\"Lee un archivo de forma segura, truncando si es necesario.\"\"\"",
    "    try:",
    "        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:",
    "            content = f.read(max_chars)",
    "        return content",
    "    except (OSError, UnicodeDecodeError):",
    "        return ''",
    "",
    "def _analyze_package_json(ruta):",
    "    \"\"\"Lee y analiza package.json del proyecto.\"\"\"",
    "    pj_path = os.path.join(ruta, 'package.json')",
    "    content = _safe_read(pj_path, 3000)",
    "    if not content:",
    "        return ''",
    "    try:",
    "        data = json.loads(content)",
    "    except json.JSONDecodeError:",
    "        return f'  package.json existe pero no es JSON valido\\n'",
    "    ",
    "    result = ''",
    "    result += f'  Nombre: {data.get(\"name\", \"desconocido\")}\\n'",
    "    result += f'  Version: {data.get(\"version\", \"?\")}\\n'",
    "    if data.get('description'):",
    "        result += f'  Descripcion: {data[\"description\"][:200]}\\n'",
    "    if data.get('scripts'):",
    "        scripts = ', '.join(list(data['scripts'].keys())[:8])",
    "        result += f'  Scripts: {scripts}\\n'",
    "    deps = {**data.get('dependencies', {}), **data.get('devDependencies', {})}",
    "    if deps:",
    "        # Detectar frameworks clave",
    "        frameworks = []",
    "        fw_map = {'next': 'Next.js', 'react': 'React', 'vue': 'Vue',",
    "                  'express': 'Express', 'fastify': 'Fastify',",
    "                  'typescript': 'TypeScript', 'tailwindcss': 'Tailwind',",
    "                  'eslint': 'ESLint', 'jest': 'Jest', 'vitest': 'Vitest'}",
    "        for dep, fw_name in fw_map.items():",
    "            if dep in deps:",
    "                frameworks.append(f'{fw_name}({deps[dep]})')",
    "        if frameworks:",
    "            result += f'  Frameworks: {\", \".join(frameworks)}\\n'",
    "        result += f'  Dependencias: {len(data.get(\"dependencies\", {}))} prod, {len(data.get(\"devDependencies\", {}))} dev\\n'",
    "    if data.get('workspaces'):",
    "        result += f'  MONOREPO con workspaces: {data[\"workspaces\"]}\\n'",
    "    return result",
    "",
    "def _analyze_readme(ruta):",
    "    \"\"\"Lee los primeros 500 chars del README como descripcion.\"\"\"",
    "    for name in ['README.md', 'readme.md', 'README.MD']:",
    "        readme_path = os.path.join(ruta, name)",
    "        content = _safe_read(readme_path, 1500)",
    "        if content:",
    "            # Limpiar markdown para texto legible",
    "            clean = re.sub(r'[#*`>\\-]', '', content[:500])",
    "            clean = re.sub(r'\\n{2,}', '\\n', clean).strip()",
    "            return f'  Descripcion del proyecto: {clean[:400]}\\n'",
    "    return ''",
    "",
    "def _detect_monorepo(ruta):",
    "    \"\"\"Detecta si es un monorepo.\"\"\"",
    "    indicators = [",
    "        'pnpm-workspace.yaml', 'lerna.json', 'turbo.json',",
    "        '.nx', 'bazel-workspace',",
    "    ]",
    "    found = []",
    "    for ind in indicators:",
    "        if os.path.exists(os.path.join(ruta, ind)):",
    "            found.append(ind)",
    "    # Tambien verificar workspaces en package.json",
    "    pj_path = os.path.join(ruta, 'package.json')",
    "    content = _safe_read(pj_path, 3000)",
    "    if content:",
    "        try:",
    "            if json.loads(content).get('workspaces'):",
    "                found.append('package.json workspaces')",
    "        except: pass",
    "    if found:",
    "        return f'  MONOREPO detectado: {\", \".join(found)}\\n'",
    "    return ''",
    "",
    "def _count_languages(ruta, max_depth=3):",
    "    \"\"\"Cuenta archivos por lenguaje.\"\"\"",
    "    counts = {}",
    "    for root, dirs, files in os.walk(ruta):",
    "        depth = root.replace(ruta, '').count(os.sep)",
    "        if depth > max_depth:",
    "            dirs.clear()",
    "            continue",
    "        # Saltar node_modules, .git, etc.",
    "        dirs[:] = [d for d in dirs if d not in",
    "                   ['node_modules', '.git', '__pycache__', '.next', 'dist', 'build', '.venv']]",
    "        for f in files:",
    "            ext = os.path.splitext(f)[1].lower()",
    "            lang = LANG_EXTENSIONS.get(ext, 'Otro')",
    "            counts[lang] = counts.get(lang, 0) + 1",
    "    return counts",
    "",
    "def analizar_proyecto(ruta: str) -> str:",
    "    \"\"\"Analisis profundo de un proyecto. Lee archivos clave.\"\"\"",
    "    ruta = _resolve_path(ruta)",
    "    if ruta is None:",
    "        return f'Directorio no existe: {ruta}'",
    "    ",
    "    result = f'=== ANALISIS DE PROYECTO ===\\n'",
    "    result += f'Ruta: {ruta}\\n\\n'",
    "    ",
    "    # 1. Estructura (igual que antes pero con stats)",
    "    file_count = 0",
    "    for root, dirs, files in os.walk(ruta):",
    "        depth = root.replace(ruta, '').count(os.sep)",
    "        if depth > 3:",
    "            dirs.clear()",
    "            continue",
    "        dirs[:] = [d for d in dirs if d not in",
    "                   ['node_modules', '.git', '__pycache__', '.next', 'dist', 'build']]",
    "        indent = '  ' * depth",
    "        result += f'{indent}{os.path.basename(root)}/\\n'",
    "        subindent = '  ' * (depth + 1)",
    "        for f in sorted(files)[:15]:",
    "            result += f'{subindent}{f}\\n'",
    "            file_count += 1",
    "        if len(files) > 15:",
    "            result += f'{subindent}... y {len(files)-15} mas\\n'",
    "    result += f'\\nTotal archivos visibles: ~{file_count}\\n\\n'",
    "    ",
    "    # 2. Lenguajes",
    "    lang_counts = _count_languages(ruta)",
    "    if lang_counts:",
    "        sorted_langs = sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)",
    "        lang_str = ', '.join(f'{lang}({cnt})' for lang, cnt in sorted_langs[:8])",
    "        result += f'LENGUAJES: {lang_str}\\n\\n'",
    "    ",
    "    # 3. Analisis de archivos clave",
    "    result += 'DETALLES DEL PROYECTO:\\n'",
    "    result += _analyze_package_json(ruta)",
    "    result += _analyze_readme(ruta)",
    "    result += _detect_monorepo(ruta)",
    "    ",
    "    # 4. Deteccion por patrones",
    "    result += '\\nTECNOLOGIAS DETECTADAS:\\n'",
    "    tech_patterns = {",
    "        'Dockerfile': 'Docker', 'docker-compose.yml': 'Docker Compose',",
    "        'docker-compose.yaml': 'Docker Compose',",
    "        '.github/workflows': 'GitHub Actions CI/CD',",
    "        '.gitlab-ci.yml': 'GitLab CI',",
    "        'Jenkinsfile': 'Jenkins CI',",
    "        'requirements.txt': 'Python (pip)', 'pyproject.toml': 'Python (modern)',",
    "        'Pipfile': 'Python (pipenv)', 'poetry.lock': 'Python (poetry)',",
    "        'Cargo.toml': 'Rust', 'go.mod': 'Go', 'Gemfile': 'Ruby',",
    "        '.eslintrc.js': 'ESLint', '.eslintrc.json': 'ESLint',",
    "        'jest.config.js': 'Jest', 'vitest.config.ts': 'Vitest',",
    "        'pytest.ini': 'pytest', 'conftest.py': 'pytest',",
    "        'tsconfig.json': 'TypeScript',",
    "        'next.config.js': 'Next.js', 'next.config.ts': 'Next.js',",
    "        'nuxt.config.ts': 'Nuxt', 'vite.config.ts': 'Vite',",
    "        '.env': 'Variables de entorno', '.env.example': 'Env template',",
    "        'mcp.json': 'MCP Server', 'mcp-config.json': 'MCP Config',",
    "        '.git': 'Git',",
    "    }",
    "    for pattern, tech in tech_patterns.items():",
    "        if os.path.exists(os.path.join(ruta, pattern)):",
    "            result += f'  - {tech}\\n'",
    "    ",
    "    # 5. Subproyectos (si es monorepo)",
    "    packages_dir = os.path.join(ruta, 'packages')",
    "    apps_dir = os.path.join(ruta, 'apps')",
    "    sub_dirs = []",
    "    for d in [packages_dir, apps_dir]:",
    "        if os.path.exists(d):",
    "            for sub in os.listdir(d)[:5]:",
    "                sub_path = os.path.join(d, sub)",
    "                if os.path.isdir(sub_path):",
    "                    sub_dirs.append(sub)",
    "    if sub_dirs:",
    "        result += f'\\nSUBPROYECTOS: {\", \".join(sub_dirs)}\\n'",
    "    ",
    "    return result",
  ]),

  heading2("3.3 Resultado Esperado"),
  bodyText("Con esta mejora, cuando el agente analice nexu-io/open-design, el resultado sera algo como: 'LENGUAJES: TypeScript(45), JSON(12), MD(8), CSS(3). DETALLES: Nombre @anthropic/open-design, Monorepo con pnpm-workspace. TECNOLOGIAS: Next.js, Vite, MCP Server, ESLint, Vitest, Docker, GitHub Actions. SUBPROYECTOS: core, cli, server, sdk'. Este nivel de detalle permite al LLM tomar decisiones informadas sobre como trabajar con el proyecto."),

  // ===========================
  // SECTION 4: OPTIMIZACION DE RECURSOS
  // ===========================
  heading1("4. Optimizacion de Recursos para RTX 3060"),
  bodyText("La optimizacion de recursos no es solo usar menos memoria: es usarla de forma inteligente para que el LLM tenga mas espacio para inferencia y las respuestas sean mas rapidas. A continuacion se detallan las 7 optimizaciones con mayor impacto, ordenadas por prioridad de implementacion."),

  heading2("4.1 Eliminar Duplicacion de Historial"),
  bodyText("Actualmente existen DOS copias de la conversacion: ReactAgent.conversation_history y TripleMemory.short_term. Ambas almacenan los mismos mensajes. La solucion es eliminar conversation_history y usar exclusivamente TripleMemory como fuente de verdad. Esto ahorra RAM y elimina inconsistencias."),
  ...codeBlock([
    "# ANTES (en ReactAgent.__init__):",
    "self.conversation_history = []  # DUPLICADO",
    "",
    "# DESPUES:",
    "# Eliminar self.conversation_history completamente",
    "# Usar memory.short_term directamente en _build_messages()",
    "",
    "# ANTES (en _build_messages):",
    "recent_history = memory.short_term[-MAX_CONVERSATION_MEMORY:]",
    "if not recent_history and self.conversation_history:",
    "    for msg in self.conversation_history[-MAX_CONVERSATION_MEMORY:]:",
    "        messages.append(msg)  # FALLBACK A DUPLICADO",
    "",
    "# DESPUES:",
    "recent_history = memory.short_term[-MAX_CONVERSATION_MEMORY:]",
    "for msg in recent_history:",
    "    messages.append({'role': msg['role'], 'content': msg['content']})",
  ]),

  heading2("4.2 LRU Cache Real para Embeddings"),
  bodyText("El cache actual de embeddings (_EMBED_CACHE) usa un FIFO primitivo que borra la mitad del cache cuando se llena. Esto es ineficiente porque puede borrar entradas que se usan frecuentemente. La solucion es usar collections.OrderedDict con move_to_end() para implementar un LRU real que preserve las entradas mas usadas."),
  ...codeBlock([
    "# ANTES:",
    "_EMBED_CACHE = {}",
    "_EMBED_CACHE_MAX = 200",
    "# Al llenarse: borra la mitad (incluyendo las mas usadas!)",
    "",
    "# DESPUES:",
    "from collections import OrderedDict",
    "",
    "class LRUCache:",
    "    def __init__(self, maxsize=200):",
    "        self._cache = OrderedDict()",
    "        self._maxsize = maxsize",
    "    ",
    "    def get(self, key):",
    "        if key in self._cache:",
    "            self._cache.move_to_end(key)  # Mas reciente = al final",
    "            return self._cache[key]",
    "        return None",
    "    ",
    "    def put(self, key, value):",
    "        if key in self._cache:",
    "            self._cache.move_to_end(key)",
    "        else:",
    "            if len(self._cache) >= self._maxsize:",
    "                self._cache.popitem(last=False)  # Elimina el mas viejo",
    "            self._cache[key] = value",
    "",
    "embed_cache = LRUCache(maxsize=200)",
  ]),

  heading2("4.3 VectorStore con Carga Lazy"),
  bodyText("Actualmente VectorStore._get_vectors() carga TODOS los vectores en memoria al primer acceso. Con 1000+ entradas de embeddings de 768 dimensiones, esto puede consumir 50MB+ de RAM. La solucion es cargar solo los indices en memoria y leer los vectores del archivo solo cuando se necesitan para una busqueda."),
  ...codeBlock([
    "# ANTES: _get_vectors() carga todo en self._vectors_cache",
    "# Con 1000 entradas x 768 floats x 8 bytes = ~6MB solo vectores",
    "",
    "# DESPUES: Solo cargar vectores de candidatos filtrados",
    "def search(self, query, limit=5, min_similarity=0.3):",
    "    query_embedding = _get_embedding(query)",
    "    if not query_embedding:",
    "        return self._text_search(query, limit)",
    "    ",
    "    # Primero: filtrar por texto (rapido, sin cargar vectores)",
    "    candidates = self._pre_filter(query, max_candidates=50)",
    "    ",
    "    # Luego: cargar solo los vectores de los candidatos",
    "    vectors = self._load_vectors_for([c['id'] for c in candidates])",
    "    ",
    "    # Scoring solo sobre candidatos",
    "    scored = []",
    "    for entry in candidates:",
    "        vec = vectors.get(entry['id'])",
    "        if vec:",
    "            score = _cosine_similarity(query_embedding, vec)",
    "            if score >= min_similarity:",
    "                scored.append({**entry, 'score': round(score, 3)})",
    "    ",
    "    scored.sort(key=lambda x: x['score'], reverse=True)",
    "    return scored[:limit]",
  ]),

  heading2("4.4 Cache de Conexion Ollama Persistente"),
  bodyText("El mayor cuello de botella en la primera inferencia es que _llm_generate prueba multiples combinaciones de modelo/host/metodo. La solucion es guardar la conexion exitosa en un archivo JSON persistente. Si Ollama esta corriendo en el mismo host, la conexion cacheada funciona inmediatamente sin timeouts."),
  ...codeBlock([
    "# llm.py - Metodo de cache persistente",
    "CONNECTION_CACHE = os.path.join(LEARN_DIR, 'ollama_connection.json')",
    "",
    "def _load_connection_cache():",
    "    try:",
    "        if os.path.exists(CONNECTION_CACHE):",
    "            with open(CONNECTION_CACHE, 'r') as f:",
    "                data = json.load(f)",
    "            # Verificar que el cache no sea muy viejo (<7 dias)",
    "            saved = datetime.fromisoformat(data.get('saved_at', ''))",
    "            if (datetime.now() - saved).days < 7:",
    "                return data",
    "    except: pass",
    "    return None",
    "",
    "def _save_connection_cache(host, method, model):",
    "    try:",
    "        with open(CONNECTION_CACHE, 'w') as f:",
    "            json.dump({",
    "                'host': host, 'method': method,",
    "                'model': model,",
    "                'saved_at': datetime.now().isoformat()",
    "            }, f)",
    "    except: pass",
  ]),

  heading2("4.5 subprocess sin shell=True cuando sea posible"),
  bodyText("ejecutar_comando() usa shell=True por defecto, lo cual inicia cmd.exe completo en Windows. Para comandos simples (git status, dir, etc.), se puede usar subprocess sin shell, lo cual es mas rapido y seguro. La estrategia es detectar si el comando es simple (sin pipes, sin redirecciones) y usar la forma lista en ese caso."),
  ...codeBlock([
    "def ejecutar_comando(comando, cwd=None, confirmar_peligroso=False):",
    "    # ... validacion de seguridad (igual) ...",
    "    ",
    "    # Detectar si es un comando simple (sin pipes/redirecciones)",
    "    is_simple = not any(c in comando for c in '|&><`')",
    "    ",
    "    try:",
    "        if is_simple:",
    "            # Mas rapido y seguro: sin shell",
    "            parts = comando.split(maxsplit=1)",
    "            cmd = parts if len(parts) > 1 else [comando]",
    "            result = subprocess.run(",
    "                cmd, capture_output=True, text=True,",
    "                timeout=timeout, cwd=cwd or REPOS_DIR",
    "            )",
    "        else:",
    "            # Comando complejo: requiere shell",
    "            result = subprocess.run(",
    "                comando, shell=True, capture_output=True, text=True,",
    "                timeout=timeout, cwd=cwd or REPOS_DIR",
    "            )",
    "        # ... procesar resultado (igual) ...",
  ]),

  heading2("4.6 Estimacion de VRAM y Optimizacion"),
  bodyText("Con una RTX 3060 de 12GB, el uso de VRAM es critico. Un modelo qwen2.5:14b cuantizado Q4 ocupa ~8GB, dejando ~4GB para contexto. Las optimizaciones de contexto impactan directamente en la calidad de las respuestas del LLM."),
  makeInfoTable([
    ["Componente", "VRAM/RAM", "Optimizacion"],
    ["qwen2.5:14b Q4", "~8GB VRAM", "Usar qwen3:4b para tareas simples"],
    ["Context window", "~4GB VRAM restante", "MAX_CONTEXT_CHARS=3000 es correcto, NO aumentar"],
    ["Embedding cache", "~50MB RAM", "LRU real con maxsize=200 es correcto"],
    ["VectorStore vectores", "~6MB RAM por 1000 entradas", "Carga lazy, solo candidatos"],
    ["Streamlit", "~100MB RAM", "Conservar, no hay alternativa ligera"],
    ["Ollama service", "~200MB RAM", "Ya optimizado por Ollama"],
  ]),

  heading2("4.7 Modelo Dual: Rutas de Inferencia"),
  bodyText("La optimizacion mas significativa es usar modelos diferentes para tareas diferentes. Actualmente se usa el mismo modelo (qwen2.5:14b) para todo: conversacion, generacion de codigo y analisis. Pero las tareas de conversacion son mas simples y podrian usar un modelo mas rapido, reservando el modelo grande solo para generacion de codigo y analisis profundo."),
  ...codeBlock([
    "# Estrategia de modelo dual",
    "TASK_MODEL_MAP = {",
    "    'chat': None,           # Modelo rapido (llama3.1:8b o qwen3:4b)",
    "    'code': None,           # Modelo grande (qwen2.5:14b)",
    "    'embedding': None,      # Modelo de embeddings (nomic-embed-text)",
    "}",
    "",
    "# Uso: en ReactAgent, seleccionar modelo segun tipo de tarea",
    "def _select_model_for_task(self, task_type):",
    "    if task_type in ['generar_codigo', 'analizar']:",
    "        return TASK_MODEL_MAP['code']  # 14b para codigo",
    "    return TASK_MODEL_MAP['chat']       # 8b para chat",
    "",
    "# Ahorro estimado: 40-60% mas rapido en conversacion simple",
    "# El modelo 8b responde en ~3s vs ~8s del 14b",
  ]),

  // ===========================
  // SECTION 5: PLAN DE IMPLEMENTACION
  // ===========================
  heading1("5. Plan de Implementacion Paso a Paso"),
  bodyText("La implementacion se divide en 3 fases de 1-2 dias cada una, priorizando los cambios con mayor impacto primero. Cada paso es independiente y el sistema debe funcionar al terminar cada fase."),

  heading2("5.1 Fase A: Modularizacion (Dias 1-2)"),
  bodyText("La meta de esta fase es dividir el monolito en modulos sin cambiar la funcionalidad. Todo debe seguir funcionando exactamente igual, pero en archivos separados."),
  makeInfoTable([
    ["Paso", "Accion", "Archivo(s)", "Lineas estimadas"],
    ["A1", "Crear estructura de directorios", "agente_v14/*", "0"],
    ["A2", "Extraer config.py", "config.py", "~60"],
    ["A3", "Extraer utils/security.py + helpers.py", "utils/*", "~80"],
    ["A4", "Extraer tools/* (6 archivos)", "tools/*", "~450"],
    ["A5", "Extraer memory/* (3 archivos)", "memory/*", "~500"],
    ["A6", "Extraer llm.py", "llm.py", "~200"],
    ["A7", "Extraer agent/react.py + schemas.py", "agent/*", "~350"],
    ["A8", "Crear app.py (entry point)", "app.py", "~50"],
    ["A9", "Probar: streamlit run app.py", "-", "-"],
  ]),
  bodyText("El paso A9 es critico: despues de la extraccion, el sistema DEBE funcionar igual que antes. Si algo falla, el problema es un import olvidado o una variable global que no se paso correctamente. La forma mas segura es hacer los pasos A2-A8 uno por uno, probando despues de cada uno."),

  heading3("Paso A1: Crear estructura"),
  ...codeBlock([
    "mkdir -p agente_v14/{tools,memory,agent,utils}",
    "touch agente_v14/__init__.py",
    "touch agente_v14/tools/__init__.py",
    "touch agente_v14/memory/__init__.py",
    "touch agente_v14/agent/__init__.py",
    "touch agente_v14/utils/__init__.py",
  ]),

  heading3("Paso A2: Extraer config.py"),
  bodyText("Copiar todas las constantes del bloque CONFIGURACION (lineas 56-96 del v13) mas SITIOS_CONOCIDOS (lineas 108-140) a config.py. Eliminar los valores hardcoded y reemplazarlos con importaciones desde config. Esto es mecanico y seguro."),
  ...codeBlock([
    "# En cada archivo que use estas constantes, agregar al inicio:",
    "from config import REPOS_DIR, LEARN_DIR, COMANDOS_PELIGROSOS, ...",
  ]),

  heading3("Paso A4: Extraer herramientas"),
  bodyText("Este es el paso mas largo. Las 15 herramientas se dividen en 6 archivos por dominio funcional. Cada archivo importa lo que necesita de config y utils. El archivo tools/__init__.py centraliza el registro TOOL_FUNCTIONS y TOOL_SCHEMAS para que el agente solo necesite un import."),
  ...codeBlock([
    "# tools/__init__.py",
    "from .sistema import ejecutar_comando, procesos_activos, matar_proceso",
    "from .archivos import leer_archivo, escribir_archivo, listar_archivos, buscar_en_archivos",
    "from .apps import abrir_aplicacion, abrir_url, buscar_youtube",
    "from .proyecto import analizar_proyecto",
    "from .codigo import generar_codigo",
    "from .web import buscar_web",
    "from .schemas import TOOL_SCHEMAS",
    "",
    "TOOL_FUNCTIONS = {",
    "    'ejecutar_comando': ejecutar_comando,",
    "    'abrir_aplicacion': abrir_aplicacion,",
    "    # ... etc",
    "}",
  ]),

  heading2("5.2 Fase B: Optimizacion (Dias 3-4)"),
  bodyText("Una vez modularizado, se aplican las optimizaciones de recursos. Cada optimizacion es independiente y se puede probar por separado."),
  makeInfoTable([
    ["Paso", "Accion", "Impacto", "Dificultad"],
    ["B1", "Eliminar conversation_history duplicado", "~2MB RAM", "Facil"],
    ["B2", "LRU cache real para embeddings", "Velocidad +2x cache hits", "Facil"],
    ["B3", "Cache persistente de conexion Ollama", "Elimina 30s+ de timeout en inicio", "Medio"],
    ["B4", "subprocess sin shell para comandos simples", "Velocidad +20% por comando", "Facil"],
    ["B5", "VectorStore carga lazy", "~50MB RAM menos", "Medio"],
    ["B6", "Modelo dual (chat vs code)", "Respuestas 2-3x mas rapidas en chat", "Avanzado"],
  ]),

  heading3("Paso B1: Eliminar historial duplicado"),
  bodyText("En agent/react.py, eliminar self.conversation_history y reemplazar todas las referencias con memory.short_term. Esto requiere que el agente tenga acceso a la instancia de TripleMemory, lo cual se logra pasandola como parametro al constructor."),
  ...codeBlock([
    "# agent/react.py",
    "class ReactAgent:",
    "    def __init__(self, memory):",
    "        self.memory = memory  # Inyeccion de dependencia",
    "        self.thinking_log = []",
    "        # Ya NO hay self.conversation_history",
    "    ",
    "    def _build_messages(self, new_message):",
    "        # ... system prompt ...",
    "        # Usar self.memory.short_term directamente",
    "        recent = self.memory.short_term[-MAX_CONVERSATION_MEMORY:]",
    "        for msg in recent:",
    "            messages.append({'role': msg['role'], 'content': msg['content']})",
    "        messages.append({'role': 'user', 'content': new_message})",
    "        return messages",
  ]),

  heading3("Paso B6: Modelo dual"),
  bodyText("Esta es la optimizacion con mayor impacto en velocidad percibida. La idea es simple: usar el modelo de 8b para chat y el de 14b para codigo. El modelo de 8b responde en ~3 segundos vs ~8 segundos del 14b, lo cual cambia drasticamente la experiencia de conversacion."),
  ...codeBlock([
    "# config.py - agregar",
    "CHAT_MODEL_PATTERNS = ['llama3.1:8b', 'qwen3:4b']  # Modelos rapidos",
    "CODE_MODEL_PATTERNS = ['qwen2.5:14b', 'qwen3-coder']  # Modelos potentes",
    "",
    "# llm.py - agregar metodo",
    "class OllamaClient:",
    "    def generate_chat(self, messages):",
    "        \"\"\"Para conversacion: usa modelo rapido.\"\"\"",
    "        return self.generate(messages, model_override=self.chat_model)",
    "    ",
    "    def generate_code(self, messages):",
    "        \"\"\"Para codigo: usa modelo grande.\"\"\"",
    "        return self.generate(messages, model_override=self.code_model)",
  ]),
  warnBox("El modelo dual requiere que tengas AMBOS modelos instalados en Ollama. Si solo tienes qwen2.5:14b, el sistema usara ese para todo. Ejecuta 'ollama pull llama3.1:8b' para instalar el modelo rapido de chat."),

  heading2("5.3 Fase C: Mejora de analizar_proyecto (Dia 5)"),
  bodyText("La mejora de analizar_proyecto es la ultima fase porque depende de que la modularizacion este completa (la funcion necesita importar helpers de utils/). El codigo completo de la nueva funcion ya se mostro en la seccion 3.2. Los pasos son:"),
  bulletItem("Copiar el codigo de la seccion 3.2 a tools/proyecto.py"),
  bulletItem("Agregar los imports necesarios (os, json, re desde la libreria estandar)"),
  bulletItem("Actualizar tools/__init__.py para importar la nueva version"),
  bulletItem("Probar con un repositorio real: analizar_proyecto('/path/to/repo')"),
  bulletItem("Verificar que el LLM ahora recibe informacion significativa del proyecto"),

  // ===========================
  // SECTION 6: TESTING
  // ===========================
  heading1("6. Estrategia de Testing y Validacion"),
  bodyText("Cada fase debe validarse antes de pasar a la siguiente. La estrategia es simple: si el agente puede ejecutar el mismo conjunto de tareas que antes de la refactorizacion, entonces la refactorizacion fue exitosa. No se agregan nuevas features hasta que las existentes funcionen."),

  heading2("6.1 Checklist de Regresion"),
  bodyText("Despues de cada paso de la fase A (modularizacion), ejecutar estas pruebas manuales:"),
  bulletItem("Streamlit arranca sin errores: streamlit run app.py"),
  bulletItem("Chat simple funciona: 'hola, como estas?'"),
  bulletItem("Abrir aplicacion: 'abre notepad' o 'abre chrome'"),
  bulletItem("Abrir URL: 'abre youtube' o 'abre google'"),
  bulletItem("Buscar en YouTube: 'busca tutorial python en youtube'"),
  bulletItem("Leer archivo: 'lee el archivo README.md'"),
  bulletItem("Ejecutar comando: 'muestra los procesos activos'"),
  bulletItem("Analizar proyecto: 'analiza el proyecto en Documents/open-design'"),
  bulletItem("Generar codigo: 'crea un juego de snake en html'"),
  bulletItem("Memoria funciona: preguntar algo, cambiar de tema, volver al tema original"),

  heading2("6.2 Benchmark de Recursos"),
  bodyText("Antes y despues de las optimizaciones (fase B), medir estos indicadores para cuantificar la mejora:"),
  makeInfoTable([
    ["Metrica", "Como medir", "Objetivo"],
    ["Tiempo de inicio", "Cronometro desde streamlit run hasta UI lista", "<10s"],
    ["Tiempo primera respuesta", "Enviar 'hola' y medir hasta respuesta", "<5s con cache"],
    ["RAM en reposo", "tasklist /fi 'imagename eq python.exe'", "<500MB"],
    ["VRAM en uso", "nvidia-smi mientras Ollama corre", "<10GB"],
    ["Cache hit rate embeddings", "Contar hits vs misses en log", ">60% despues de calentamiento"],
    ["Tiempo analizar_proyecto", "Cronometro sobre repo grande", "<5s"],
  ]),

  // ===========================
  // SECTION 7: ROADMAP INTEGRATION
  // ===========================
  heading1("7. Integracion con el Roadmap Fase 3-5"),
  bodyText("La refactorizacion no es un paso aparte del roadmap: es la base que habilita las fases 3-5. Sin modularizacion, agregar MCP o multi-agente al monolito lo haria inmanejable. Con la arquitectura modular, cada nueva fase se agrega como un nuevo modulo sin tocar los existentes."),

  heading2("7.1 Fase 3: MCP + Metacognicion"),
  bodyText("El protocolo MCP (Model Context Protocol) se integra naturalmente en la arquitectura modular. Se agrega un nuevo modulo mcp/ que implementa el cliente MCP y registra las herramientas MCP en el mismo TOOL_FUNCTIONS que las herramientas locales. El agente no necesita saber si una herramienta es local o remota: simplemente la ejecuta."),
  ...codeBlock([
    "# mcp/__init__.py",
    "from .client import MCPClient",
    "from .registry import register_mcp_tools",
    "",
    "# Al iniciar el agente:",
    "mcp = MCPClient(config_path='~/.ia-local/mcp.json')",
    "mcp_tools = register_mcp_tools(mcp)  # Registra en TOOL_FUNCTIONS",
    "# El agente ahora tiene acceso a todas las herramientas MCP",
  ]),
  bodyText("La metacognicion (el agente reflexionando sobre su propio proceso de pensamiento) se implementa como un decorador en el motor ReAct que analiza el historial de iteraciones y decide si cambiar de estrategia. Esto es posible porque el motor esta aislado en agent/react.py."),

  heading2("7.2 Fase 4: Multimodal + Guardrails"),
  bodyText("La multimodalidad (vision) requiere un nuevo modulo vision/ que procese imagenes y las convierta en texto descriptivo antes de enviarlas al LLM. Los guardrails (limites de seguridad) se implementan como un middleware en el motor ReAct que valida las acciones antes de ejecutarlas."),
  ...codeBlock([
    "# vision/__init__.py",
    "from .processor import describe_image, analyze_screenshot",
    "",
    "# Guardrails como middleware",
    "class GuardrailMiddleware:",
    "    def validate_action(self, tool_name, params):",
    "        # Verificar que la accion es segura",
    "        # Verificar que no excede limites",
    "        # Verificar que no viola politicas",
    "        return True, params  # (aprobado, params modificados)",
  ]),

  heading2("7.3 Fase 5: Multi-Agente + Workflow Engine"),
  bodyText("El multi-agente es la fase mas ambiciosa y la que mas se beneficia de la modularizacion. Cada agente especializado es una instancia de ReactAgent con su propio system prompt y subconjunto de herramientas. El Workflow Engine coordina los agentes como una cadena de montaje."),
  ...codeBlock([
    "# multiagent/__init__.py",
    "from .orchestrator import Orchestrator",
    "from .agents import CoderAgent, ResearcherAgent, ReviewerAgent",
    "",
    "orchestrator = Orchestrator()",
    "orchestrator.register('coder', CoderAgent(tools=[generar_codigo, leer_archivo]))",
    "orchestrator.register('researcher', ResearcherAgent(tools=[buscar_web, analizar_proyecto]))",
    "orchestrator.register('reviewer', ReviewerAgent(tools=[leer_archivo, buscar_en_archivos]))",
    "",
    "# Workflow: research → code → review",
    "result = orchestrator.execute(",
    "    workflow=['researcher', 'coder', 'reviewer'],",
    "    task='Crea un API REST para gestion de tareas'",
    ")",
  ]),

  // ===========================
  // SECTION 8: RESUMEN
  // ===========================
  heading1("8. Resumen y Proximos Pasos"),
  bodyText("La refactorizacion del agente v13 a v14 no es solo una mejora tecnica: es la diferencia entre un proyecto que se estanca en la fase 2 y uno que escala hacia un sistema multi-agente completo. Los 5 dias de trabajo propuestos se traducen en una base solida que permite agregar MCP, vision, guardrails y multi-agente sin reescribir codigo existente."),

  heading2("8.1 Orden de Prioridad"),
  makeInfoTable([
    ["Prioridad", "Tarea", "Impacto", "Tiempo"],
    ["1", "Modularizar (Fase A)", "Base para todo lo demas", "2 dias"],
    ["2", "Mejorar analizar_proyecto (Fase C)", "Calidad de respuestas +3x", "1 dia"],
    ["3", "Cache de conexion Ollama (B3)", "Elimina timeouts al inicio", "0.5 dias"],
    ["4", "Eliminar historial duplicado (B1)", "Limpieza arquitectonica", "0.5 dias"],
    ["5", "LRU cache real (B2)", "Velocidad en busquedas", "0.5 dias"],
    ["6", "VectorStore lazy (B5)", "Ahorro de RAM", "0.5 dias"],
    ["7", "Modelo dual (B6)", "Velocidad percibida +2x", "1 dia"],
    ["8", "subprocess sin shell (B4)", "Micro-optimizacion", "0.5 dias"],
  ]),

  heading2("8.2 Comando de Inicio"),
  bodyText("Para comenzar la implementacion, ejecuta estos comandos en tu terminal de Windows:"),
  ...codeBlock([
    "# 1. Crear backup del v13",
    "copy app_auto_pro.py app_auto_pro_v13_backup.py",
    "",
    "# 2. Crear estructura de directorios",
    "mkdir agente_v14",
    "cd agente_v14",
    "mkdir tools memory agent utils",
    "",
    "# 3. Crear __init__.py en cada directorio",
    "type nul > __init__.py",
    "type nul > tools\\__init__.py",
    "type nul > memory\\__init__.py",
    "type nul > agent\\__init__.py",
    "type nul > utils\\__init__.py",
    "",
    "# 4. Empezar extrayendo config.py",
    "# Copiar las constantes de las lineas 56-140 del v13",
    "",
    "# 5. Despues de cada archivo extraido, probar:",
    "streamlit run app.py",
  ]),

  tipBox("Recuerda: el objetivo de la Fase A es que todo funcione IGUAL que antes, solo que en archivos separados. No cambies la funcionalidad, solo la estructura. Las mejoras de funcionalidad vienen en las Fases B y C."),
];

// Body section
const bodySection = {
  properties: {
    page: {
      size: { width: 11906, height: 16838 },
      margin: { top: 1440, bottom: 1440, left: 1701, right: 1417 },
      pageNumbers: { start: 1 },
    },
  },
  headers: {
    default: new Header({
      children: [new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [new TextRun({
          text: "Agente Autonomo v14 - Guia de Refactoring",
          font: "Microsoft YaHei",
          size: 16,
          color: "A0AEC0",
          italics: true,
        })],
      })],
    }),
  },
  footers: {
    default: new Footer({
      children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
        children: [
          new TextRun({ children: [PageNumber.CURRENT], font: "Microsoft YaHei", size: 16, color: "718096" }),
        ],
      })],
    }),
  },
  children: bodyChildren,
};

// Create document
const doc = new Document({
  styles: {
    default: {
      document: {
        run: {
          font: "Microsoft YaHei",
          size: 21,
          color: palette.body,
        },
        paragraph: {
          spacing: { line: 312 },
        },
      },
      heading1: {
        run: {
          font: "SimHei",
          size: 32,
          color: palette.primary,
          bold: true,
        },
        paragraph: {
          spacing: { before: 360, after: 200, line: 312 },
        },
      },
      heading2: {
        run: {
          font: "SimHei",
          size: 28,
          color: palette.accent,
          bold: true,
        },
        paragraph: {
          spacing: { before: 280, after: 160, line: 312 },
        },
      },
      heading3: {
        run: {
          font: "SimHei",
          size: 24,
          color: palette.primary,
          bold: true,
        },
        paragraph: {
          spacing: { before: 200, after: 120, line: 312 },
        },
      },
      listParagraph: {
        run: {
          font: "Microsoft YaHei",
          size: 21,
          color: palette.body,
        },
      },
    },
  },
  numbering: {
    config: [
      {
        reference: "default-bullet",
        levels: [
          {
            level: 0,
            format: "bullet",
            text: "\u2022",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 420, hanging: 260 } } },
          },
          {
            level: 1,
            format: "bullet",
            text: "\u25E6",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 780, hanging: 260 } } },
          },
        ],
      },
    ],
  },
  sections: [coverSection, tocSection, bodySection],
});

// Export
Packer.toBuffer(doc).then(buffer => {
  const outputPath = "/home/z/my-project/download/Agente_Autonomo_v14_Guia_Refactoring.docx";
  fs.writeFileSync(outputPath, buffer);
  console.log(`Document saved to: ${outputPath}`);
}).catch(err => {
  console.error("Error generating document:", err);
  process.exit(1);
});
