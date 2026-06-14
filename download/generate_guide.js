const docx = require("docx");
const fs = require("fs");

const {
  Document, Packer, Paragraph, TextRun, HeadingLevel,
  AlignmentType, BorderStyle, TabStopPosition, TabStopType,
  Table, TableRow, TableCell, WidthType, ShadingType,
  PageBreak, Header, Footer, PageNumber, NumberFormat
} = docx;

// Colors
const CYAN = "00D4FF";
const GREEN = "00FF88";
const WHITE = "E8E8E8";
const GRAY = "888888";
const BLACK = "0A0A0A";
const DARK = "111111";

function heading(text, level = HeadingLevel.HEADING_1) {
  return new Paragraph({
    heading: level,
    spacing: { before: 300, after: 150 },
    children: [
      new TextRun({ text, color: CYAN, bold: true, size: level === HeadingLevel.HEADING_1 ? 32 : level === HeadingLevel.HEADING_2 ? 26 : 22 }),
    ],
  });
}

function body(text, opts = {}) {
  return new Paragraph({
    spacing: { before: 80, after: 80, line: 276 },
    children: [
      new TextRun({ text, color: opts.color || WHITE, size: 21, font: "Consolas", bold: opts.bold || false }),
    ],
  });
}

function codeBlock(lines) {
  return lines.map((line, i) =>
    new Paragraph({
      spacing: { before: i === 0 ? 120 : 0, after: i === lines.length - 1 ? 120 : 0, line: 260 },
      shading: { type: ShadingType.CLEAR, fill: "1A1A1A" },
      indent: { left: 400 },
      children: [
        new TextRun({ text: line, color: GREEN, size: 19, font: "Consolas" }),
      ],
    })
  );
}

function stepHeader(num, title) {
  return new Paragraph({
    spacing: { before: 250, after: 100 },
    children: [
      new TextRun({ text: `PASO ${num}: `, color: CYAN, bold: true, size: 24, font: "Consolas" }),
      new TextRun({ text: title, color: WHITE, bold: true, size: 24, font: "Consolas" }),
    ],
  });
}

function tipBox(text) {
  return new Paragraph({
    spacing: { before: 100, after: 100 },
    shading: { type: ShadingType.CLEAR, fill: "0D2137" },
    indent: { left: 400, right: 400 },
    border: { left: { style: BorderStyle.SINGLE, size: 6, color: CYAN } },
    children: [
      new TextRun({ text: "TIP: ", color: CYAN, bold: true, size: 19, font: "Consolas" }),
      new TextRun({ text, color: "AAAAAA", size: 19, font: "Consolas" }),
    ],
  });
}

function warningBox(text) {
  return new Paragraph({
    spacing: { before: 100, after: 100 },
    shading: { type: ShadingType.CLEAR, fill: "2A1515" },
    indent: { left: 400, right: 400 },
    border: { left: { style: BorderStyle.SINGLE, size: 6, color: "FF3333" } },
    children: [
      new TextRun({ text: "AVISO: ", color: "FF3333", bold: true, size: 19, font: "Consolas" }),
      new TextRun({ text, color: "CC8888", size: 19, font: "Consolas" }),
    ],
  });
}

function divider() {
  return new Paragraph({
    spacing: { before: 200, after: 200 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 1, color: "333333" } },
    children: [],
  });
}

async function main() {
  const doc = new Document({
    creator: "ZAI",
    title: "Guia de Instalacion - Agente Local Autonomo",
    description: "Instrucciones completas para clonar y ejecutar el agente local",
    styles: {
      default: {
        document: {
          run: { color: WHITE, font: "Consolas", size: 21 },
        },
      },
    },
    sections: [{
      properties: {
        page: {
          margin: { top: 1000, bottom: 1000, left: 1200, right: 1200 },
          size: { width: 11906, height: 16838 },
        },
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: "ZAI Agent - Guia de Instalacion", color: "444444", size: 16, font: "Consolas" })],
          })],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({ text: "Pagina ", color: "444444", size: 16, font: "Consolas" }),
              new TextRun({ children: [PageNumber.CURRENT], color: "444444", size: 16, font: "Consolas" }),
            ],
          })],
        }),
      },
      children: [
        // COVER
        new Paragraph({ spacing: { before: 3000 }, children: [] }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "ZAI", color: CYAN, bold: true, size: 72, font: "Consolas" }),
          ],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 200 },
          children: [
            new TextRun({ text: "Agente Local Autonomo", color: WHITE, size: 36, font: "Consolas" }),
          ],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 100 },
          children: [
            new TextRun({ text: "Guia Completa de Instalacion y Configuracion", color: GRAY, size: 24, font: "Consolas" }),
          ],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 400 },
          border: { top: { style: BorderStyle.SINGLE, size: 1, color: CYAN } },
          children: [],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 200 },
          children: [
            new TextRun({ text: "Repositorio: github.com/yecos/AgentLocal", color: CYAN, size: 20, font: "Consolas" }),
          ],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 100 },
          children: [
            new TextRun({ text: "v16.4 | ReAct + TripleMemory + 77+ Herramientas", color: "555555", size: 18, font: "Consolas" }),
          ],
        }),

        // PAGE BREAK
        new Paragraph({ children: [new PageBreak()] }),

        // ARQUITECTURA
        heading("ARQUITECTURA DEL SISTEMA", HeadingLevel.HEADING_1),
        body("El agente local se compone de 3 servicios que deben estar corriendo simultaneamente:"),
        new Paragraph({ spacing: { before: 150 }, children: [] }),
        
        new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          rows: [
            new TableRow({
              tableHeader: true,
              children: [
                new TableCell({ width: { size: 20, type: WidthType.PERCENTAGE }, shading: { type: ShadingType.CLEAR, fill: DARK }, children: [new Paragraph({ children: [new TextRun({ text: "Servicio", bold: true, color: CYAN, size: 19, font: "Consolas" })] })] }),
                new TableCell({ width: { size: 15, type: WidthType.PERCENTAGE }, shading: { type: ShadingType.CLEAR, fill: DARK }, children: [new Paragraph({ children: [new TextRun({ text: "Puerto", bold: true, color: CYAN, size: 19, font: "Consolas" })] })] }),
                new TableCell({ width: { size: 65, type: WidthType.PERCENTAGE }, shading: { type: ShadingType.CLEAR, fill: DARK }, children: [new Paragraph({ children: [new TextRun({ text: "Descripcion", bold: true, color: CYAN, size: 19, font: "Consolas" })] })] }),
              ],
            }),
            ...([
              ["Ollama", "11434", "Motor LLM - Inferencia de modelos de lenguaje"],
              ["Bridge API", "8000", "FastAPI - Puente entre el agente ReAct y la web"],
              ["Next.js Web UI", "3000", "Interfaz web React - Chat con el agente"],
            ].map(([s, p, d]) =>
              new TableRow({
                children: [
                  new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: s, color: GREEN, size: 19, font: "Consolas" })] })] }),
                  new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: p, color: WHITE, size: 19, font: "Consolas" })] })] }),
                  new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: d, color: "AAAAAA", size: 19, font: "Consolas" })] })] }),
                ],
              })
            )),
          ],
        }),

        tipBox("La interfaz web tiene 2 modos: AGENT (con herramientas via Bridge) y CHAT (directo con Ollama, sin herramientas)"),

        divider(),

        // PRERREQUISITOS
        heading("PRERREQUISITOS", HeadingLevel.HEADING_1),
        
        stepHeader(1, "Instalar Ollama"),
        body("Descarga e instala Ollama desde https://ollama.com"),
        ...codeBlock([
          "# Windows: descarga el installer de ollama.com",
          "# Linux:",
          "curl -fsSL https://ollama.com/install.sh | sh",
          "# Mac:",
          "brew install ollama",
        ]),
        body("Despues de instalar, inicia Ollama:"),
        ...codeBlock(["ollama serve"]),
        body("Descarga al menos un modelo (recomendado para empezar):"),
        ...codeBlock([
          "ollama pull qwen3:4b          # 3 GB - Rapido, buen equilibrio",
          "ollama pull qwen2.5:14b       # 8 GB - Mejor calidad",
          "ollama pull llama3.1:8b       # 5 GB - Chat rapido",
          "ollama pull qwen3-coder       # 4 GB - Especializado en codigo",
        ]),
        tipBox("Para GPU: NVIDIA con CUDA o Apple Silicon. Sin GPU, los modelos corren en CPU (mas lento)."),
        
        divider(),

        stepHeader(2, "Instalar Python 3.10+"),
        body("Descarga desde https://www.python.org/downloads/"),
        warningBox("En Windows: marca la casilla 'Add Python to PATH' durante la instalacion."),
        ...codeBlock([
          "# Verificar instalacion:",
          "python --version    # Debe ser 3.10+",
          "pip --version       # Debe funcionar",
        ]),

        divider(),

        stepHeader(3, "Instalar Node.js 18+"),
        body("Descarga desde https://nodejs.org/ (version LTS recomendada)"),
        ...codeBlock([
          "# Verificar instalacion:",
          "node --version      # Debe ser 18+",
          "npm --version       # Debe funcionar",
        ]),
        tipBox("Alternativa: usa Bun como runtime de JavaScript (mas rapido). Instala desde https://bun.sh"),

        divider(),
        new Paragraph({ children: [new PageBreak()] }),

        // CLONAR EL REPO
        heading("CLONAR EL REPOSITORIO", HeadingLevel.HEADING_1),
        
        stepHeader(4, "Clonar desde GitHub"),
        body("Abre una terminal y ejecuta:"),
        ...codeBlock([
          "# Clonar el repositorio",
          "git clone https://github.com/yecos/AgentLocal.git",
          "",
          "# Entrar al directorio",
          "cd AgentLocal",
        ]),
        body("Estructura del proyecto:"),
        ...codeBlock([
          "AgentLocal/",
          "  agente_v14/           # Motor del agente (Python)",
          "    agent/              # ReAct, schemas, metacognicion",
          "    tools/              # 77+ herramientas",
          "    memory/             # TripleMemory (corto/largo/plazo)",
          "    utils/              # Seguridad, metricas, tokens",
          "    bridge_api.py       # API FastAPI (puerto 8000)",
          "    app.py              # UI Streamlit alternativa",
          "    config.py           # Configuracion centralizada",
          "    requirements.txt    # Dependencias Python",
          "  src/                  # Frontend Next.js",
          "    app/                # Paginas y API routes",
          "    components/ui/      # Componentes shadcn/ui",
          "  package.json          # Dependencias Node.js",
          "  start_all.bat         # Inicio unificado (Windows)",
          "  start.bat             # Inicio agente solo (Windows)",
        ]),

        divider(),

        // INSTALAR DEPENDENCIAS
        heading("INSTALAR DEPENDENCIAS", HeadingLevel.HEADING_1),
        
        stepHeader(5, "Instalar dependencias Python"),
        ...codeBlock([
          "# Entrar al directorio del agente",
          "cd agente_v14",
          "",
          "# Crear entorno virtual (recomendado)",
          "python -m venv venv",
          "",
          "# Activar entorno virtual:",
          "# Windows:",
          "venv\\Scripts\\activate",
          "# Linux/Mac:",
          "source venv/bin/activate",
          "",
          "# Instalar dependencias",
          "pip install -r requirements.txt",
        ]),
        body("Dependencias principales que se instalan:"),
        ...codeBlock([
          "streamlit       - UI alternativa",
          "ollama          - Cliente Ollama",
          "chromadb        - Base de datos vectorial",
          "fastapi         - API REST",
          "uvicorn         - Servidor ASGI",
          "fpdf2           - Crear PDFs",
          "python-docx     - Crear DOCX",
          "openpyxl        - Crear XLSX",
          "matplotlib      - Graficos",
          "pandas          - Analisis de datos",
          "playwright      - Navegador headless",
          "duckduckgo-search - Busqueda web",
        ]),

        divider(),

        stepHeader(6, "Instalar dependencias Node.js"),
        ...codeBlock([
          "# Volver a la raiz del proyecto",
          "cd ..",
          "",
          "# Instalar dependencias",
          "npm install",
          "# O con Bun (mas rapido):",
          "bun install",
        ]),
        body("Esto instala: Next.js 16, React 19, Tailwind CSS 4, shadcn/ui, react-markdown, react-syntax-highlighter, y mas."),

        divider(),
        new Paragraph({ children: [new PageBreak()] }),

        // INICIAR SERVICIOS
        heading("INICIAR LOS SERVICIOS", HeadingLevel.HEADING_1),
        
        body("Necesitas 3 terminales abiertas simultaneamente.", { bold: true }),

        stepHeader(7, "Terminal 1 - Iniciar Ollama"),
        ...codeBlock([
          "# Si no esta corriendo, iniciarlo:",
          "ollama serve",
          "",
          "# Verificar que funciona:",
          "ollama list    # Lista modelos instalados",
        ]),

        divider(),

        stepHeader(8, "Terminal 2 - Iniciar Bridge API"),
        ...codeBlock([
          "# Desde la raiz del proyecto:",
          "cd agente_v14",
          "python bridge_api.py",
        ]),
        body("Deberias ver:"),
        ...codeBlock([
          "============================================================",
          "  ZAI Agent Bridge API v16.4",
          "  Puerto: 8000",
          "  Agente: DISPONIBLE",
          "  Threading: ACTIVADO",
          "============================================================",
        ]),
        warningBox("Si dice 'Agente: NO DISPONIBLE', verifica que Ollama este corriendo y tengas modelos instalados."),
        body("Verificar que el bridge responde:"),
        ...codeBlock([
          "# En otra terminal o navegador:",
          "curl http://localhost:8000/api/health",
          '# Respuesta: {"status":"ok","agent":true,"busy":false}',
        ]),

        divider(),

        stepHeader(9, "Terminal 3 - Iniciar Interfaz Web"),
        ...codeBlock([
          "# Desde la raiz del proyecto:",
          "npm run dev",
          "# O con Bun:",
          "bun run dev",
        ]),
        body("Deberias ver:"),
        ...codeBlock([
          "  ▲ Next.js 16.x.x",
          "  - Local:    http://localhost:3000",
          "  - Network:  http://192.168.x.x:3000",
        ]),
        tipBox("Abre http://localhost:3000 en tu navegador. Veras la interfaz ZAI."),

        divider(),

        // OPCION RAPIDA WINDOWS
        heading("OPCION RAPIDA (SOLO WINDOWS)", HeadingLevel.HEADING_1),
        body("Si estas en Windows, puedes usar el script de inicio unificado:"),
        ...codeBlock([
          "# Doble clic en:",
          "start_all.bat",
          "",
          "# O desde la terminal:",
          "start_all.bat",
        ]),
        body("Este script hace todo automaticamente:"),
        ...codeBlock([
          "1. Verifica Python y Node.js",
          "2. Inicia Ollama si no esta corriendo",
          "3. Instala dependencias faltantes",
          "4. Inicia Bridge API en puerto 8000",
          "5. Inicia Next.js en puerto 3000",
          "6. Abre el navegador",
        ]),
        tipBox("Para modo agente solo (sin web UI): ejecuta start.bat. Abre Streamlit en puerto 8501."),

        divider(),
        new Paragraph({ children: [new PageBreak()] }),

        // VERIFICAR
        heading("VERIFICAR QUE TODO FUNCIONA", HeadingLevel.HEADING_1),
        
        stepHeader(10, "Checklist de verificacion"),
        body("Abre http://localhost:3000 en tu navegador y verifica:"),

        new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          rows: [
            new TableRow({
              tableHeader: true,
              children: [
                new TableCell({ width: { size: 5, type: WidthType.PERCENTAGE }, shading: { type: ShadingType.CLEAR, fill: DARK }, children: [new Paragraph({ children: [new TextRun({ text: "#", bold: true, color: CYAN, size: 19, font: "Consolas" })] })] }),
                new TableCell({ width: { size: 50, type: WidthType.PERCENTAGE }, shading: { type: ShadingType.CLEAR, fill: DARK }, children: [new Paragraph({ children: [new TextRun({ text: "Verificacion", bold: true, color: CYAN, size: 19, font: "Consolas" })] })] }),
                new TableCell({ width: { size: 45, type: WidthType.PERCENTAGE }, shading: { type: ShadingType.CLEAR, fill: DARK }, children: [new Paragraph({ children: [new TextRun({ text: "Esperado", bold: true, color: CYAN, size: 19, font: "Consolas" })] })] }),
              ],
            }),
            ...([
              ["1", "Indicador de conexion", "Punto verde 'CONNECTED'"],
              ["2", "Modelo seleccionado", "Aparece tu modelo en el sidebar"],
              ["3", "Bridge activo", "Bridge: Active (verde) en sidebar"],
              ["4", "Modo AGENT", "Boton cyan 'AGENT' en top bar"],
              ["5", "Enviar mensaje", "Respuesta del agente con streaming"],
              ["6", "Tool cards", "Si usas herramientas, cards con estado"],
            ].map(([n, v, e]) =>
              new TableRow({
                children: [
                  new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: n, color: GRAY, size: 19, font: "Consolas" })] })] }),
                  new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: v, color: WHITE, size: 19, font: "Consolas" })] })] }),
                  new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: e, color: GREEN, size: 19, font: "Consolas" })] })] }),
                ],
              })
            )),
          ],
        }),

        divider(),

        // CONFIGURACION AVANZADA
        heading("CONFIGURACION AVANZADA", HeadingLevel.HEADING_1),
        
        body("Archivo: agente_v14/config.py", { bold: true }),
        ...codeBlock([
          "# Directorio de trabajo (donde el agente crea/busca archivos)",
          'REPOS_DIR = "~/Documents"     # Windows',
          'REPOS_DIR = "~/repos"        # Linux/Mac',
          "",
          "# Modelo por defecto",
          "PREFERRED_MODELS = [",
          '    "llama3.1:8b",',
          '    "qwen2.5-coder:7b",',
          '    "qwen2.5:14b",',
          '    "qwen3:4b",',
          '    "qwen3-coder",',
          "]",
          "",
          "# Iteraciones ReAct (cuantas veces piensa+actua)",
          "MAX_REACT_ITERATIONS = 6",
          "",
          "# Timeout (segundos)",
          "DEFAULT_TIMEOUT = 90        # Normal",
          "LLM_TIMEOUT_LARGE = 300     # Tareas largas",
          "",
          "# Pensamiento profundo",
          'DEEP_THINKING_MODE = "full"  # CoT + nativo + reflexion',
          "",
          "# Busqueda hibrida en memoria",
          "USE_HYBRID_SEARCH = True    # BM25 + Vectorial + RRF",
        ]),

        divider(),

        // MODELOS RECOMENDADOS
        heading("MODELOS RECOMENDADOS", HeadingLevel.HEADING_1),
        
        new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          rows: [
            new TableRow({
              tableHeader: true,
              children: [
                new TableCell({ width: { size: 25, type: WidthType.PERCENTAGE }, shading: { type: ShadingType.CLEAR, fill: DARK }, children: [new Paragraph({ children: [new TextRun({ text: "Modelo", bold: true, color: CYAN, size: 19, font: "Consolas" })] })] }),
                new TableCell({ width: { size: 15, type: WidthType.PERCENTAGE }, shading: { type: ShadingType.CLEAR, fill: DARK }, children: [new Paragraph({ children: [new TextRun({ text: "RAM", bold: true, color: CYAN, size: 19, font: "Consolas" })] })] }),
                new TableCell({ width: { size: 30, type: WidthType.PERCENTAGE }, shading: { type: ShadingType.CLEAR, fill: DARK }, children: [new Paragraph({ children: [new TextRun({ text: "Uso", bold: true, color: CYAN, size: 19, font: "Consolas" })] })] }),
                new TableCell({ width: { size: 30, type: WidthType.PERCENTAGE }, shading: { type: ShadingType.CLEAR, fill: DARK }, children: [new Paragraph({ children: [new TextRun({ text: "Nota", bold: true, color: CYAN, size: 19, font: "Consolas" })] })] }),
              ],
            }),
            ...([
              ["qwen3:4b", "~3 GB", "General / Inicio", "Recomendado para empezar"],
              ["qwen3-coder", "~4 GB", "Codigo", "Especializado programacion"],
              ["llama3.1:8b", "~5 GB", "Chat rapido", "Bueno para conversacion"],
              ["qwen2.5:14b", "~8 GB", "Alta calidad", "Mejor razonamiento"],
              ["qwen3:30b-a3b", "~17 GB", "Max calidad", "Requiere GPU potente"],
            ].map(([m, r, u, n]) =>
              new TableRow({
                children: [
                  new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: m, color: GREEN, size: 19, font: "Consolas" })] })] }),
                  new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: r, color: WHITE, size: 19, font: "Consolas" })] })] }),
                  new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: u, color: "AAAAAA", size: 19, font: "Consolas" })] })] }),
                  new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: n, color: "888888", size: 19, font: "Consolas" })] })] }),
                ],
              })
            )),
          ],
        }),

        divider(),

        // SOLUCION DE PROBLEMAS
        heading("SOLUCION DE PROBLEMAS", HeadingLevel.HEADING_1),
        
        body("Problema: 'Ollama not connected'", { bold: true }),
        ...codeBlock([
          "# Verificar que Ollama esta corriendo:",
          "curl http://localhost:11434/api/tags",
          "# Si no responde, iniciar:",
          "ollama serve",
        ]),

        body("Problema: 'Bridge not running'", { bold: true }),
        ...codeBlock([
          "# Verificar que el Bridge esta corriendo:",
          "curl http://localhost:8000/api/health",
          "# Si no responde, iniciar:",
          "cd agente_v14 && python bridge_api.py",
        ]),

        body("Problema: 'No models found'", { bold: true }),
        ...codeBlock([
          "# Descargar un modelo:",
          "ollama pull qwen3:4b",
          "# Verificar:",
          "ollama list",
        ]),

        body("Problema: Respuesta lenta (60+ segundos)", { bold: true }),
        body("El agente usa ReAct (piensa + actua + observa en bucle). Cada iteracion llama al LLM. Con modelos grandes o sin GPU, es lento. Soluciones:"),
        ...codeBlock([
          "# 1. Usar modelo mas pequeno:",
          "ollama pull qwen3:4b    # 3 GB, rapido",
          "# 2. Cambiar modo a CHAT (sin herramientas, mas rapido)",
          "# 3. Tener GPU (NVIDIA CUDA o Apple Silicon)",
        ]),

        body("Problema: Error al instalar dependencias Python", { bold: true }),
        ...codeBlock([
          "# Instalar solo las esenciales primero:",
          "pip install fastapi uvicorn ollama chromadb",
          "# Luego las demas:",
          "pip install -r requirements.txt",
        ]),

        body("Problema: El agente muestra JSON al usuario", { bold: true }),
        body("El sistema ya tiene limpieza automatica de JSON. Si aun aparece JSON en la respuesta, es probable que el modelo no esta usando function calling nativo. Soluciones:"),
        ...codeBlock([
          "# 1. Usar modelos que soporten function calling:",
          "ollama pull qwen3:4b    # Soporta tool calling nativo",
          "# 2. El sistema detecta y limpia JSON automaticamente",
          "# 3. Si persiste, cambiar a modo CHAT para conversacion simple",
        ]),

        divider(),

        // FLUJO DE DATOS
        heading("FLUJO DE DATOS (COMO FUNCIONA)", HeadingLevel.HEADING_1),
        ...codeBlock([
          "Usuario escribe mensaje",
          "    |",
          "    v",
          "Next.js (puerto 3000) -> /api/chat",
          "    |",
          "    +-- Modo CHAT -> Ollama directo (puerto 11434)",
          "    |                   Respuesta simple sin herramientas",
          "    |",
          "    +-- Modo AGENT -> Bridge API (puerto 8000)",
          "                        |",
          "                        v",
          "                    ReactAgent.run_stream()",
          "                        |",
          "                        +-- Deep Thinking (analiza complejidad)",
          "                        |",
          "                        +-- Bucle ReAct (max 6 iteraciones):",
          "                        |     1. Pensar (LLM genera respuesta/herramienta)",
          "                        |     2. Actuar (ejecutar herramienta si aplica)",
          "                        |     3. Observar (resultado de la herramienta)",
          "                        |     4. Metacognicion (evaluar progreso)",
          "                        |     5. Repetir si necesario",
          "                        |",
          "                        +-- Respuesta final -> SSE stream -> Next.js",
          "",
          "Eventos SSE: text | tool_start | tool_result | thinking | meta | done",
        ]),

        divider(),

        // RESUMEN COMANDOS
        heading("RESUMEN DE COMANDOS", HeadingLevel.HEADING_1),
        body("Instrucciones completas en orden:", { bold: true }),
        ...codeBlock([
          "# 1. Clonar repo",
          "git clone https://github.com/yecos/AgentLocal.git",
          "cd AgentLocal",
          "",
          "# 2. Instalar dependencias Python",
          "cd agente_v14",
          "pip install -r requirements.txt",
          "cd ..",
          "",
          "# 3. Instalar dependencias Node.js",
          "npm install",
          "",
          "# 4. Descargar modelo",
          "ollama pull qwen3:4b",
          "",
          "# 5. Terminal 1: Iniciar Ollama",
          "ollama serve",
          "",
          "# 6. Terminal 2: Iniciar Bridge",
          "cd agente_v14 && python bridge_api.py",
          "",
          "# 7. Terminal 3: Iniciar Web UI",
          "npm run dev",
          "",
          "# 8. Abrir navegador",
          "http://localhost:3000",
          "",
          "# ALTERNATIVA Windows (todo en uno):",
          "start_all.bat",
        ]),
      ],
    }],
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync("/home/z/my-project/download/Guia_Instalacion_Agente_Local.docx", buffer);
  console.log("DOCX generado exitosamente!");
}

main().catch(console.error);
