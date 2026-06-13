const { Document, Packer, Paragraph, TextRun, Header, Footer,
        AlignmentType, HeadingLevel, PageNumber, Table, TableRow, TableCell,
        WidthType, BorderStyle, ShadingType, TableOfContents,
        PageOrientation } = require("docx");
const fs = require("fs");

// Palette - Tech/Analysis theme (Cool + Light + Active)
const P = {
  primary: "#0A1628",
  body: "#1A2B40",
  secondary: "#6878A0",
  accent: "#5B8DB8",
  surface: "#F4F8FC",
  white: "#FFFFFF",
  lightGray: "#E8EDF2",
  warning: "#D4853A",
  danger: "#C0392B",
  success: "#27AE60"
};
const c = (hex) => hex.replace("#", "");

// Helper: heading
function heading(text, level = HeadingLevel.HEADING_1) {
  const sizes = { [HeadingLevel.HEADING_1]: 32, [HeadingLevel.HEADING_2]: 30, [HeadingLevel.HEADING_3]: 28 };
  return new Paragraph({
    heading: level,
    spacing: { before: level === HeadingLevel.HEADING_1 ? 360 : 240, after: 120 },
    children: [new TextRun({ text, bold: true, color: c(P.primary), size: sizes[level] || 28, font: { ascii: "Calibri", eastAsia: "SimHei" } })]
  });
}

// Helper: body paragraph
function body(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: 480 },
    spacing: { line: 312 },
    children: [new TextRun({ text, size: 24, color: c(P.body), font: { ascii: "Times New Roman", eastAsia: "SimSun" } })]
  });
}

// Helper: body paragraph without indent
function bodyNoIndent(text) {
  return new Paragraph({
    spacing: { line: 312 },
    children: [new TextRun({ text, size: 24, color: c(P.body), font: { ascii: "Times New Roman", eastAsia: "SimSun" } })]
  });
}

// Helper: bold+normal mixed paragraph
function mixedParagraph(parts) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: 480 },
    spacing: { line: 312 },
    children: parts.map(p => new TextRun({
      text: p.text,
      bold: p.bold || false,
      size: 24,
      color: c(p.color || P.body),
      font: { ascii: "Times New Roman", eastAsia: "SimSun" }
    }))
  });
}

// Helper: bullet item
function bullet(text, level = 0) {
  return new Paragraph({
    spacing: { line: 312 },
    indent: { left: 480 + level * 360, hanging: 240 },
    children: [new TextRun({ text: `\u2022 ${text}`, size: 24, color: c(P.body), font: { ascii: "Times New Roman", eastAsia: "SimSun" } })]
  });
}

// Helper: code block
function codeBlock(lines) {
  return lines.map(line => new Paragraph({
    spacing: { line: 276 },
    indent: { left: 480 },
    shading: { type: ShadingType.CLEAR, fill: c(P.lightGray) },
    children: [new TextRun({ text: line, size: 20, font: { ascii: "Consolas", eastAsia: "Consolas" }, color: c(P.primary) })]
  }));
}

// Helper: table
function makeTable(headers, rows) {
  const headerCells = headers.map(h => new TableCell({
    shading: { type: ShadingType.CLEAR, fill: c(P.accent) },
    margins: { top: 60, bottom: 60, left: 120, right: 120 },
    children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: h, bold: true, size: 22, color: c(P.white), font: { ascii: "Calibri", eastAsia: "SimHei" } })] })]
  }));

  const dataRows = rows.map((row, ri) => {
    const cells = row.map(cell => new TableCell({
      shading: { type: ShadingType.CLEAR, fill: ri % 2 === 0 ? c(P.surface) : c(P.white) },
      margins: { top: 40, bottom: 40, left: 120, right: 120 },
      children: [new Paragraph({ children: [new TextRun({ text: String(cell), size: 20, color: c(P.body), font: { ascii: "Calibri", eastAsia: "SimSun" } })] })]
    }));
    return new TableRow({ children: cells });
  });

  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: [new TableRow({ children: headerCells, tableHeader: true }), ...dataRows]
  });
}

// ============================================================
// BUILD DOCUMENT
// ============================================================

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { font: { ascii: "Calibri", eastAsia: "Microsoft YaHei" }, size: 24, color: c(P.body) },
        paragraph: { spacing: { line: 312 } }
      }
    }
  },
  sections: [
    // ===================== COVER PAGE =====================
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838, orientation: PageOrientation.PORTRAIT },
          margin: { top: 0, bottom: 0, left: 0, right: 0 }
        }
      },
      children: [
        new Paragraph({ spacing: { before: 4000 } }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 },
          children: [new TextRun({ text: "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", size: 24, color: c(P.accent), font: { ascii: "Calibri" } })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 120 },
          children: [new TextRun({ text: "AGENTE LOCAL AUT\u00d3NOMO v14", size: 28, color: c(P.secondary), font: { ascii: "Calibri", eastAsia: "SimHei" } })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 },
          children: [new TextRun({ text: "An\u00e1lisis de M\u00e9todos de B\u00fasqueda", size: 52, bold: true, color: c(P.primary), font: { ascii: "Calibri", eastAsia: "SimHei" } })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 120 },
          children: [new TextRun({ text: "Diagn\u00f3stico, Mejores Pr\u00e1cticas y Propuestas de Mejora", size: 26, color: c(P.secondary), font: { ascii: "Calibri", eastAsia: "SimHei" } })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 400 },
          children: [new TextRun({ text: "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", size: 24, color: c(P.accent), font: { ascii: "Calibri" } })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 600 },
          children: [new TextRun({ text: "Junio 2026", size: 24, color: c(P.secondary), font: { ascii: "Calibri" } })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 100 },
          children: [new TextRun({ text: "Documento T\u00e9cnico Interno", size: 22, color: c(P.secondary), font: { ascii: "Calibri" } })]
        }),
      ]
    },

    // ===================== TOC + BODY =====================
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838, orientation: PageOrientation.PORTRAIT },
          margin: { top: 1440, bottom: 1440, left: 1701, right: 1417 },
          pageNumbers: { start: 1 }
        }
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({ text: "P\u00e1gina ", size: 18, color: c(P.secondary), font: { ascii: "Calibri" } }),
              new TextRun({ children: [PageNumber.CURRENT], size: 18, color: c(P.secondary), font: { ascii: "Calibri" } }),
              new TextRun({ text: " de ", size: 18, color: c(P.secondary), font: { ascii: "Calibri" } }),
              new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, color: c(P.secondary), font: { ascii: "Calibri" } })
            ]
          })]
        })
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: "Agente v14 \u2014 An\u00e1lisis de B\u00fasqueda", size: 18, color: c(P.secondary), italics: true, font: { ascii: "Calibri" } })]
          })]
        })
      },
      children: [
        // TOC
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 300 },
          children: [new TextRun({ text: "\u00cdndice", size: 36, bold: true, color: c(P.primary), font: { ascii: "Calibri", eastAsia: "SimHei" } })]
        }),
        new TableOfContents("TOC", {
          hyperlink: true,
          headingStyleRange: "1-3"
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 200, after: 200 },
          children: [new TextRun({ text: "(Clic derecho sobre el \u00edndice \u2192 \u201cActualizar campo\u201d para refrescar n\u00fameros de p\u00e1gina)", size: 18, italics: true, color: c(P.secondary), font: { ascii: "Calibri" } })]
        }),
        new Paragraph({ children: [new TextRun({ break: 1 })] }),

        // ============================================================
        // SECTION 1: RESUMEN EJECUTIVO
        // ============================================================
        heading("1. Resumen Ejecutivo"),

        body("El Agente Local Aut\u00f3nomo v14 implementa un sistema de b\u00fasqueda compuesto por cinco subsistemas interconectados que abarcan desde la recuperaci\u00f3n sem\u00e1ntica en memoria vectorial hasta la b\u00fasqueda web en tiempo real. Este documento presenta un an\u00e1lisis exhaustivo de cada m\u00e9todo de b\u00fasqueda, identifica los problemas cr\u00edticos de rendimiento y precisi\u00f3n, y propone las mejoras m\u00e1s impactantes basadas en las mejores pr\u00e1cticas de la industria de Retrieval-Augmented Generation (RAG) y sistemas de b\u00fasqueda sem\u00e1ntica moderna."),

        body("El an\u00e1lisis revela que la arquitectura actual tiene una base s\u00f3lida con su Triple Memory y f\u00e1brica de vector stores, pero presenta deficiencias significativas en tres \u00e1reas clave: (1) la b\u00fasqueda por texto (fallback) utiliza un algoritmo de coincidencia de palabras excesivamente simple que ignora sinonimia y variaciones morfol\u00f3gicas, (2) la b\u00fasqueda web depende de scraping HTML fr\u00e1gil de DuckDuckGo que falla frecuentemente y no maneja reintentos, y (3) no existe un mecanismo de re-ranking que combine m\u00faltiples se\u00f1ales de relevancia para mejorar la calidad de los resultados."),

        body("Las mejoras propuestas se priorizan por impacto esperado vs. esfuerzo de implementaci\u00f3n. La mejora de mayor impacto es la implementaci\u00f3n de b\u00fasqueda h\u00edbrida BM25 + Vectorial, que combina la precisi\u00f3n de la b\u00fasqueda por palabras clave con la comprensi\u00f3n sem\u00e1ntica de los embeddings. Le sigue la migraci\u00f3n de la b\u00fasqueda web a una API robusta con l\u00f3gica de reintentos, y finalmente la adici\u00f3n de un pipeline de re-ranking cross-encoder que reordene los resultados candidatos para maximizar la relevancia final."),

        makeTable(
          ["Prioridad", "Mejora", "Impacto Esperado", "Esfuerzo"],
          [
            ["\u2605\u2605\u2605", "B\u00fasqueda H\u00edbrida BM25 + Vectorial", "+40-60% precisi\u00f3n recall", "Medio"],
            ["\u2605\u2605\u2605", "Web Search con API robusta + Retry", "+80% fiabilidad b\u00fasqueda web", "Bajo"],
            ["\u2605\u2605", "Pipeline de Re-ranking Cross-Encoder", "+20-30% precisi\u00f3n top-k", "Medio"],
            ["\u2605\u2605", "Pre-filtro mejorado con stemming/stopwords", "+15-25% recall texto", "Bajo"],
            ["\u2605", "B\u00fasqueda en archivos con ripgrep", "+10x velocidad grep", "Muy bajo"],
            ["\u2605", "Cache de consultas frecuentes", "-50% llamadas embedding", "Bajo"],
          ]
        ),

        // ============================================================
        // SECTION 2: ARQUITECTURA ACTUAL
        // ============================================================
        heading("2. Arquitectura Actual de B\u00fasqueda"),

        body("El agente v14 implementa b\u00fasqueda a trav\u00e9s de cinco subsistemas principales que se combinan en un pipeline de recuperaci\u00f3n de contexto. Cada subsistema opera de forma independiente pero converge en la funci\u00f3n TripleMemory.get_context_for() que ensambla el contexto enriquecido antes de cada llamada al LLM. La arquitectura sigue el patr\u00f3n cl\u00e1sico de memoria triple: corto plazo (conversaci\u00f3n), largo plazo (vector store sem\u00e1ntico), y trabajo (scratchpad de tarea actual)."),

        heading("2.1 VectorStore Casero (vectorstore.py)", HeadingLevel.HEADING_2),

        body("El VectorStore casero es la implementaci\u00f3n base de almacenamiento vectorial. Utiliza un \u00edndice JSON para metadatos y archivos Pickle para los vectores de embeddings. El m\u00e9todo search() implementa un enfoque de dos fases: primero pre-filtra candidatos por coincidencia de texto usando _pre_filter(), luego ejecuta b\u00fasqueda sem\u00e1ntica con cosine_similarity_batch() usando numpy. Si no hay vectores disponibles, recurre a _text_search() que realiza coincidencia simple de palabras. El pre-filtro extrae palabras de m\u00e1s de 3 caracteres de la consulta y cuenta cu\u00e1ntas coinciden en cada documento, seleccionando los 50 mejores candidatos antes de la fase sem\u00e1ntica."),

        body("El sistema incluye optimizaciones como skip_embedding para interacciones r\u00e1pidas (almacena solo texto sin vector), migraci\u00f3n autom\u00e1tica de JSON a Pickle, y lazy loading de vectores. El umbral de similitud m\u00ednima por defecto es 0.3, y la funci\u00f3n de limpieza elimina entradas viejas cuando se supera el l\u00edmite de 1000 entradas, removiendo tambi\u00e9n vectores hu\u00e9rfanos."),

        heading("2.2 ChromaVectorStore (chroma_store.py)", HeadingLevel.HEADING_2),

        body("ChromaVectorStore es la implementaci\u00f3n profesional que utiliza ChromaDB como backend. A\u00f1ade tres caracter\u00edsticas cr\u00edticas sobre el VectorStore casero: decaimiento temporal exponencial (half-life de 30 d\u00edas), deduplicaci\u00f3n sem\u00e1ntica (umbral 0.95), y manejo robusto de errores de dimensi\u00f3n de embeddings. El decaimiento temporal aplica un factor exp(-0.693 * dias / 30) al score de similitud, con un m\u00ednimo del 10% de relevancia para recuerdos muy antiguos. La deduplicaci\u00f3n sem\u00e1ntica verifica si un texto nuevo tiene similitud >= 0.95 con alg\u00fan documento existente antes de insertarlo, evitando almacenar contenido pr\u00e1cticamente id\u00e9ntico."),

        body("El sistema incluye auto-detecci\u00f3n de dimensiones de embeddings, recreaci\u00f3n autom\u00e1tica de la colecci\u00f3n cuando se detecta un mismatch de dimensiones (m\u00e1ximo 2 reintentos), y validaci\u00f3n post-inicializaci\u00f3n con una consulta de prueba. El m\u00e9todo search() recupera 3x m\u00e1s candidatos que el l\u00edmite solicitado (n_candidates = limit * 3) para re-rankear con decaimiento temporal, usando un umbral reducido (min_similarity * 0.5) tras aplicar el factor de decaimiento."),

        heading("2.3 SimpleVectorStore (chroma_store.py)", HeadingLevel.HEADING_2),

        body("SimpleVectorStore hereda de VectorStore y a\u00f1ade decaimiento temporal y deduplicaci\u00f3n b\u00e1sica por texto similar. Es el fallback cuando ChromaDB no est\u00e1 instalado. La deduplicaci\u00f3n compara los primeros 100 caracteres en min\u00fasculas de cada entrada para detectar duplicados aproximados. Sobreescribe search() para agregar decaimiento temporal al scoring, multiplicando la similitud coseno por el factor de decaimiento, y _text_search() para aplicar decaimiento tambi\u00e9n a la b\u00fasqueda por texto."),

        heading("2.4 B\u00fasqueda Web (tools/web.py)", HeadingLevel.HEADING_2),

        body("La herramienta buscar_web implementa b\u00fasqueda web en dos fases: primero consulta la DuckDuckGo Instant Answer API (resumen + temas relacionados), luego realiza scraping HTML de DuckDuckGo Lite para obtener links reales con t\u00edtulos y snippets. El scraping usa expresiones regulares para extraer enlaces y descripciones del HTML. Las URLs de redireccionamiento de DuckDuckGo se procesan extrayendo el par\u00e1metro uddg= para obtener la URL real. El timeout es de 10 segundos (WEB_TIMEOUT) y no hay l\u00f3gica de reintentos."),

        heading("2.5 B\u00fasqueda en Archivos (tools/archivos.py)", HeadingLevel.HEADING_2),

        body("La herramienta buscar_en_archivos delega al sistema operativo: usa grep -rn en Linux/Mac y findstr /s /i /n en Windows. La b\u00fasqueda se limita a extensiones .py, .js, .html, .ts, .json con un m\u00e1ximo de 50 resultados. El patr\u00f3n de b\u00fasqueda pasa por sanitize_input() para prevenir inyecci\u00f3n de comandos, pero esta sanitizaci\u00f3n puede alterar patrones de b\u00fasqueda v\u00e1lidos que contengan caracteres especiales de regex."),

        heading("2.6 TripleMemory y Context Enrichment", HeadingLevel.HEADING_2),

        body("TripleMemory.get_context_for() es el orquestador central que ensambla contexto de las tres memorias con un presupuesto de 2000 caracteres (MAX_CONTEXT_CHARS). La distribuci\u00f3n es: memoria de trabajo (800 chars m\u00e1ximo), correcciones aprendidas (400 chars m\u00e1ximo), y conocimiento a largo plazo (budget restante, m\u00e1ximo 3 resultados de recall). Si la conversaci\u00f3n tiene m\u00e1s de 10 mensajes, genera un resumen (LLM si >20 mensajes, simple si <=20). El sistema de correcciones (LearningSystem) usa coincidencia de palabras clave con longitud >3 para encontrar correcciones relevantes."),

        // ============================================================
        // SECTION 3: AN\u00c1LISIS CR\u00cdTICO
        // ============================================================
        heading("3. An\u00e1lisis Cr\u00edtico por Componente"),

        heading("3.1 Problemas del Pre-filtro de Texto", HeadingLevel.HEADING_2),

        body("El m\u00e9todo _pre_filter() en VectorStore presenta m\u00faltiples deficiencias que reducen significativamente la calidad del recall. Primero, el filtro de longitud m\u00ednima de 3 caracteres elimina palabras cruciales en espa\u00f1ol como preposiciones, art\u00edculos y conectores que pueden ser sem\u00e1nticamente importantes en contextos espec\u00edficos. Por ejemplo, en la consulta 'c\u00f3mo usar la API de Ollama', el t\u00e9rmino 'API' tiene exactamente 3 caracteres y ser\u00eda filtrado, a pesar de ser el t\u00e9rmino m\u00e1s discriminativo de la consulta."),

        body("Segundo, el pre-filtro realiza coincidencia exacta de subcadenas sin normalizaci\u00f3n morfol\u00f3gica. En espa\u00f1ol, esto es particularmente problem\u00e1tico porque las conjugaciones verbales y variaciones de g\u00e9nero/n\u00famero generan formas superficiales diferentes para el mismo concepto. Una b\u00fasqueda de 'configurar' no encontrar\u00e1 documentos que contienen 'configuraci\u00f3n', 'configurado', o 'configuraciones'. Tercero, no hay eliminaci\u00f3n de stopwords, lo que significa que palabras muy frecuentes como 'que', 'del', 'para' pueden generar falsos positivos masivos, inflando los scores de documentos irrelevantes que casualmente contienen estas palabras comunes."),

        body("Cuarto, el l\u00edmite de 50 candidatos es arbitrario y podr\u00eda ser demasiado peque\u00f1o para colecciones grandes. Si el vector store tiene 500+ entradas, es posible que documentos altamente relevantes sem\u00e1nticamente pero con poco solapamiento textual queden excluidos del pre-filtro, nunca llegando a la fase de b\u00fasqueda vectorial donde s\u00ed ser\u00edan encontrados."),

        heading("3.2 Problemas de la B\u00fasqueda por Texto (Fallback)", HeadingLevel.HEADING_2),

        body("El m\u00e9todo _text_search() es el fallback cuando no hay embeddings disponibles, pero su algoritmo de scoring es extremadamente rudimentario. El score se calcula como matches / len(query_words), que es esencialmente un ratio de cobertura de palabras de la consulta. Este enfoque tiene problemas graves: no considera la frecuencia inversa de documento (IDF), lo que significa que palabras muy comunes como 'sistema', 'agente', 'memoria' aportan el mismo peso que palabras raras y discriminativas como 'ChromaDB', 'ReAct', 'embeddings'."),

        body("Adem\u00e1s, el algoritmo no maneja sin\u00f3nimos ni variaciones l\u00e9xicas. Una b\u00fasqueda de 'buscar informaci\u00f3n' no encontrar\u00e1 documentos que contienen 'encontrar datos' o 'recuperar conocimiento', a pesar de ser sem\u00e1nticamente equivalentes. La longitud m\u00ednima de 3 caracteres tambi\u00e9n filtra t\u00e9rminos importantes de dos letras en espa\u00f1ol como 'un', 'el', 'al' que pueden ser parte de expresiones compuestas relevantes. En el caso de ChromaVectorStore._text_search(), el m\u00e9todo obtiene TODOS los documentos de la colecci\u00f3n antes de filtrar, lo que es extremadamente ineficiente para colecciones grandes."),

        heading("3.3 Problemas de la B\u00fasqueda Web", HeadingLevel.HEADING_2),

        body("La implementaci\u00f3n actual de buscar_web tiene tres problemas cr\u00edticos de fiabilidad. Primero, el scraping HTML de DuckDuckGo Lite es inherentemente fr\u00e1gil: cualquier cambio en la estructura HTML de DuckDuckGo rompe las expresiones regulares que extraen los resultados. Los patrones link_pattern y snippet_pattern asumen clases CSS espec\u00edficas ('result__a', 'result__snippet') que pueden cambiar sin previo aviso."),

        body("Segundo, no existe l\u00f3gica de reintentos. Si la primera petici\u00f3n falla por un timeout de red temporal o un error 503 del servidor, la funci\u00f3n simplemente devuelve 'No se encontraron resultados' sin intentar nuevamente. Esto es particularmente problem\u00e1tico porque el timeout de 10 segundos es relativamente corto para conexiones lentas. Tercero, no hay rotaci\u00f3n de user agents ni manejo de rate limiting. DuckDuckGo puede bloquear peticiones repetidas del mismo user agent, y la implementaci\u00f3n actual no tiene mecanismo para manejar esto."),

        body("Cuarto, la funci\u00f3n no extrae metadatos valiosos como la fecha de publicaci\u00f3n, el idioma del resultado, o el tipo de contenido (art\u00edculo, video, PDF). Estos metadatos podr\u00edan usarse para filtrar y priorizar resultados. Quinto, no hay cach\u00e9 de resultados: si el agente busca lo mismo dos veces en la misma conversaci\u00f3n, realiza dos peticiones HTTP completas."),

        heading("3.4 Problemas del Sistema de Decaimiento Temporal", HeadingLevel.HEADING_2),

        body("El decaimiento temporal con half-life de 30 d\u00edas es un buen punto de partida, pero tiene limitaciones importantes. El factor de decaimiento se aplica uniformemente a todos los tipos de recuerdos, sin distinguir entre conocimiento factual (que no deber\u00eda decaer) y conversaci\u00f3n casual (que s\u00ed deber\u00eda decaer r\u00e1pidamente). Un conocimiento como 'el usuario prefiere respuestas en espa\u00f1ol' deber\u00eda mantener su relevancia indefinidamente, mientras que una nota sobre 'estuve buscando recetas ayer' deber\u00eda decaer en horas, no d\u00edas."),

        body("Adem\u00e1s, el umbral reducido (min_similarity * 0.5) tras aplicar decaimiento puede hacer pasar documentos con similitud sem\u00e1ntica muy baja (0.15 en el peor caso con min_similarity=0.3). Esto introduce ruido en los resultados, especialmente para recuerdos antiguos que ya no son relevantes pero que a\u00fan superan el umbral reducido. El sistema tampoco tiene en cuenta la frecuencia de acceso: un recuerdo que se recupera frecuentemente deber\u00eda tener su reloj de decaimiento reiniciado o ralentizado."),

        heading("3.5 Problemas de la B\u00fasqueda en Archivos", HeadingLevel.HEADING_2),

        body("La implementaci\u00f3n de buscar_en_archivos delega directamente a grep/findstr del sistema operativo, lo que limita severamente sus capacidades. Primero, el conjunto de extensiones est\u00e1 hardcodeado (.py, .js, .html, .ts, .json) y no incluye extensiones comunes como .md, .yaml, .yml, .toml, .cfg, .ini, .sh, .bat, .sql, .csv, .tsx, .jsx, .vue, .svelte. Segundo, el sanitizado de entrada puede alterar patrones regex v\u00e1lidos: si el usuario quiere buscar un patr\u00f3n como 'def\\s+test_', sanitize_input() puede eliminar o modificar los caracteres especiales."),

        body("Tercero, no hay b\u00fasqueda recursiva configurada expl\u00edcitamente (grep -r ya es recursivo, pero no hay control de profundidad ni exclusi\u00f3n de directorios como node_modules, .git, __pycache__). Esto puede resultar en b\u00fasquedas lentas y resultados irrelevantes de directorios de dependencias. Cuarto, el l\u00edmite de 50 resultados puede ser insuficiente para proyectos grandes, y no hay paginaci\u00f3n ni mecanismo para obtener m\u00e1s resultados."),

        // ============================================================
        // SECTION 4: MEJORAS PRIORITARIAS
        // ============================================================
        heading("4. Mejoras Prioritarias"),

        body("A continuaci\u00f3n se detallan las mejoras priorizadas por el ratio impacto/esfuerzo. Cada mejora incluye una descripci\u00f3n t\u00e9cnica, justificaci\u00f3n, y estimaci\u00f3n de impacto esperado."),

        heading("4.1 B\u00fasqueda H\u00edbrida BM25 + Vectorial [Prioridad M\u00e1xima]", HeadingLevel.HEADING_2),

        body("La b\u00fasqueda h\u00edbrida combina dos se\u00f1ales de recuperaci\u00f3n complementarias: BM25 captura coincidencias exactas de t\u00e9rminos con ponderaci\u00f3n estad\u00edstica (TF-IDF), mientras que la b\u00fasqueda vectorial captura similitud sem\u00e1ntica m\u00e1s all\u00e1 de las palabras exactas. La combinaci\u00f3n de ambas se\u00f1ales produce resultados superiores a cualquiera de las dos por separado, especialmente en consultas donde el usuario usa terminolog\u00eda diferente a la del documento almacenado."),

        body("BM25 es el algoritmo est\u00e1ndar de la industria para b\u00fasqueda por palabras clave. A diferencia del simple conteo de coincidencias actual, BM25 considera: (1) la frecuencia del t\u00e9rmino en el documento (TF), (2) la frecuencia inversa de documento (IDF) que penaliza t\u00e9rminos muy comunes, y (3) la longitud del documento relativa a la longitud promedio. La f\u00f3rmula de scoring de BM25 est\u00e1 parametrizada por k1 (controla la saturaci\u00f3n de TF, t\u00edpicamente 1.2-2.0) y b (controla la normalizaci\u00f3n por longitud, t\u00edpicamente 0.75)."),

        body("La implementaci\u00f3n propuesta reemplaza _pre_filter() y _text_search() con un motor BM25 integrado que ejecuta b\u00fasqueda por palabras clave en paralelo con la b\u00fasqueda vectorial, y combina los scores usando Reciprocal Rank Fusion (RRF). RRF es un m\u00e9todo simple pero efectivo que suma los rec\u00edprocos de las posiciones en cada ranking: score_rrf = sum(1 / (k + rank_i)) para cada lista de ranking i, donde k t\u00edpicamente vale 60. Este m\u00e9todo no requiere normalizaci\u00f3n de scores entre sistemas diferentes y funciona bien en la pr\u00e1ctica."),

        ...codeBlock([
          "# Implementaci\u00f3n propuesta de BM25 + RRF",
          "import math",
          "from collections import Counter",
          "",
          "class BM25:",
          "    def __init__(self, documents, k1=1.5, b=0.75):",
          "        self.k1 = k1",
          "        self.b = b",
          "        self.doc_count = len(documents)",
          "        self.avgdl = sum(len(d.split()) for d in documents) / max(self.doc_count, 1)",
          "        self.doc_freqs = []",
          "        self.idf = {}",
          "        corpus_counts = Counter()",
          "        for doc in documents:",
          "            tokens = doc.lower().split()",
          "            freq = Counter(tokens)",
          "            self.doc_freqs.append(freq)",
          "            corpus_counts.update(freq.keys())",
          "        for term, df in corpus_counts.items():",
          "            self.idf[term] = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1)",
          "",
          "    def search(self, query, limit=10):",
          "        query_tokens = query.lower().split()",
          "        scores = []",
          "        for i, freq in enumerate(self.doc_freqs):",
          "            score = 0.0",
          "            dl = sum(freq.values())",
          "            for term in query_tokens:",
          "                if term in freq:",
          "                    tf = freq[term]",
          "                    idf = self.idf.get(term, 0)",
          "                    numerator = tf * (self.k1 + 1)",
          "                    denominator = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)",
          "                    score += idf * numerator / denominator",
          "            scores.append((i, score))",
          "        scores.sort(key=lambda x: x[1], reverse=True)",
          "        return scores[:limit]",
          "",
          "def reciprocal_rank_fusion(rankings, k=60):",
          "    scores = {}",
          "    for ranking in rankings:",
          "        for rank, doc_id in enumerate(ranking, start=1):",
          "            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)",
          "    return sorted(scores.items(), key=lambda x: x[1], reverse=True)",
        ]),

        body("El impacto esperado de esta mejora es un incremento del 40-60% en precisi\u00f3n de recall, especialmente para consultas que contienen t\u00e9rminos espec\u00edficos del dominio (como 'ChromaDB', 'embedding', 'ReAct') que el sistema vectorial actual puede no recuperar eficientemente debido al pre-filtro limitado. La implementaci\u00f3n no requiere dependencias externas adicionales y puede integrarse progresivamente sin romper la funcionalidad existente."),

        heading("4.2 B\u00fasqueda Web con API Robusta y Retry [Prioridad M\u00e1xima]", HeadingLevel.HEADING_2),

        body("La migraci\u00f3n de buscar_web a una API robusta es cr\u00edtica porque la b\u00fasqueda web es la herramienta m\u00e1s utilizada por el agente para obtener informaci\u00f3n actualizada. Se proponen dos opciones: (1) DuckDuckGo Search API oficial a trav\u00e9s de la librer\u00eda duckduckgo-search de Python, que maneja autom\u00e1ticamente rotaci\u00f3n de proxies, reintentos, y rate limiting, o (2) SearXNG, un metabuscador de c\u00f3digo abierto que agrega resultados de m\u00faltiples motores (Google, Bing, DuckDuckGo, Wikipedia) y se puede ejecutar localmente como instancia Docker."),

        body("La opci\u00f3n recomendada es duckduckgo-search porque no requiere infraestructura adicional y proporciona una API Python estable con manejo autom\u00e1tico de reintentos, rotaci\u00f3n de user agents, y parsing robusto. La implementaci\u00f3n propuesta a\u00f1ade: (1) retry con backoff exponencial (3 intentos m\u00e1ximo), (2) cach\u00e9 de resultados por consulta con TTL de 5 minutos, (3) extracci\u00f3n de metadatos enriquecidos (fecha, tipo de contenido), y (4) fallback autom\u00e1tico entre m\u00faltiples motores si el primario falla."),

        ...codeBlock([
          "# Implementaci\u00f3n propuesta: Web Search con retry y cache",
          "import time",
          "from functools import lru_cache",
          "",
          "class RobustWebSearch:",
          "    def __init__(self, max_retries=3, cache_ttl=300):",
          "        self.max_retries = max_retries",
          "        self.cache_ttl = cache_ttl",
          "        self._cache = {}  # {query: (results, timestamp)}",
          "",
          "    def search(self, query, limit=5):",
          "        # Check cache first",
          "        if query in self._cache:",
          "            results, ts = self._cache[query]",
          "            if time.time() - ts < self.cache_ttl:",
          "                return results",
          "",
          "        # Retry con backoff exponencial",
          "        for attempt in range(self.max_retries):",
          "            try:",
          "                results = self._search_ddg(query, limit)",
          "                self._cache[query] = (results, time.time())",
          "                return results",
          "            except Exception as e:",
          "                wait = 2 ** attempt + 0.5",
          "                logger.warning(f'Intento {attempt+1} fallo: {e}. Retry en {wait:.1f}s')",
          "                time.sleep(wait)",
          "",
          "        # Fallback: API Instant Answer",
          "        return self._search_ddg_instant(query)",
        ]),

        body("El impacto esperado es un incremento del 80% en fiabilidad de la b\u00fasqueda web, reduciendo significativamente los casos donde el agente no puede obtener informaci\u00f3n de internet. La cach\u00e9 reduce las llamadas HTTP repetidas en un 50% aproximadamente, mejorando tanto la velocidad como la resiliencia ante rate limiting. El esfuerzo de implementaci\u00f3n es bajo porque duckduckgo-search es una librer\u00eda madura con API simple."),

        heading("4.3 Pipeline de Re-ranking Cross-Encoder [Prioridad Alta]", HeadingLevel.HEADING_2),

        body("Un pipeline de re-ranking a\u00f1ade una segunda fase de evaluaci\u00f3n despu\u00e9s de la recuperaci\u00f3n inicial. El sistema actual devuelve resultados ordenados \u00fanicamente por similitud coseno, que es un modelo bi-encoder: calcula embeddings independientes para query y documento y mide la distancia. Un cross-encoder, en cambio, procesa query y documento conjuntamente, permitiendo capturar interacciones entre t\u00e9rminos que el bi-encoder no puede modelar. El resultado es un reordenamiento m\u00e1s preciso de los candidatos recuperados."),

        body("La implementaci\u00f3n propuesta no requiere un modelo neural adicional. En su lugar, implementa un re-ranker heur\u00edstico basado en m\u00faltiples se\u00f1ales que se combinan en un score final: (1) similitud coseno del vector store (se\u00f1al sem\u00e1ntica), (2) score BM25 (se\u00f1al l\u00e9xica), (3) decaimiento temporal (se\u00f1al de frescura), (4) cobertura de t\u00e9rminos de la consulta en el documento (se\u00f1al de exactitud), y (5) tipo de metadato (priorizar conocimiento sobre conversaci\u00f3n). Cada se\u00f1al se normaliza a [0,1] y se pondera con pesos configurables."),

        ...codeBlock([
          "# Re-ranker multi-se\u00f1al",
          "class MultiSignalReranker:",
          "    WEIGHTS = {",
          "        'semantic': 0.35,   # Similitud coseno",
          "        'lexical': 0.25,    # BM25 score normalizado",
          "        'freshness': 0.15,  # 1 - decaimiento temporal",
          "        'coverage': 0.15,   # % terminos query en doc",
          "        'type_bonus': 0.10, # Bonus por tipo de contenido",
          "    }",
          "",
          "    def rerank(self, query, candidates, limit=5):",
          "        query_terms = set(query.lower().split())",
          "        scored = []",
          "        for c in candidates:",
          "            signals = {",
          "                'semantic': c.get('raw_similarity', c.get('score', 0)),",
          "                'lexical': self._bm25_score(query, c['text']),",
          "                'freshness': c.get('decay', 0.5),",
          "                'coverage': self._term_coverage(query_terms, c['text']),",
          "                'type_bonus': self._type_bonus(c.get('metadata', {})),",
          "            }",
          "            final = sum(signals[k] * self.WEIGHTS[k] for k in self.WEIGHTS)",
          "            scored.append({**c, 'rerank_score': round(final, 4), 'signals': signals})",
          "        scored.sort(key=lambda x: x['rerank_score'], reverse=True)",
          "        return scored[:limit]",
        ]),

        body("El impacto esperado es un incremento del 20-30% en precisi\u00f3n top-k, particularmente notable en consultas ambiguas donde m\u00faltiples documentos tienen similitud coseno similar pero diferente relevancia pr\u00e1ctica. El re-ranker puede distinguir entre un documento que menciona un t\u00e9rmino de pasada y uno que lo trata en profundidad, algo que la similitud coseno por s\u00ed sola no puede hacer."),

        heading("4.4 Pre-filtro Mejorado con Stemming y Stopwords [Prioridad Alta]", HeadingLevel.HEADING_2),

        body("La mejora del pre-filtro a\u00f1ade normalizaci\u00f3n morfol\u00f3gica y eliminaci\u00f3n de stopwords al pipeline de pre-filtrado. Para espa\u00f1ol, se propone usar el stemmer Snowball Spanish de NLTK, que reduce las palabras a su ra\u00edz morfol\u00f3gica: 'configuraci\u00f3n', 'configurar', 'configurado' se reducen todas a 'configur'. Esto permite que el pre-filtro encuentre documentos que usan variaciones morfol\u00f3gicas de los t\u00e9rminos de la consulta, ampliando significativamente el recall sin sacrificar precisi\u00f3n."),

        body("La lista de stopwords en espa\u00f1ol elimina t\u00e9rminos funcionales como 'de', 'la', 'que', 'el', 'en', 'y', 'a', 'los', 'del', 'se', 'las', 'por', 'un', 'para', 'con', 'una', 'su', 'al', 'lo'. Estas palabras tienen IDF extremadamente bajo y no aportan informaci\u00f3n discriminativa. Su eliminaci\u00f3n reduce el ruido en el scoring y mejora la velocidad del pre-filtro al reducir el n\u00famero de comparaciones necesarias. Adem\u00e1s, se a\u00f1ade un mapeo de sin\u00f3nimos b\u00e1sico para t\u00e9rminos t\u00e9cnicos del dominio del agente: {'buscar': ['encontrar', 'recuperar', 'hallar'], 'memoria': ['recuerdo', 'conocimiento'], 'error': ['fallo', 'bug', 'problema']}."),

        heading("4.5 B\u00fasqueda en Archivos con ripgrep [Prioridad Media]", HeadingLevel.HEADING_2),

        body("ripgrep (rg) es un reemplazo moderno de grep que es 10-100x m\u00e1s r\u00e1pido, ignora autom\u00e1ticamente archivos en .gitignore y directorios como node_modules/.git/__pycache__, y soporta patrones Unicode nativamente. La implementaci\u00f3n propuesta reemplaza la llamada a grep con rg, manteniendo grep como fallback. Adem\u00e1s, se expande el conjunto de extensiones a un conjunto completo que incluye .md, .yaml, .yml, .toml, .cfg, .ini, .sh, .bat, .sql, .csv, .tsx, .jsx, .vue, .svelte, .rs, .go, .java, .rb, .php, .css, .scss, .less, .xml, .env, .log, .txt."),

        ...codeBlock([
          "def buscar_en_archivos(ruta: str, patron: str) -> str:",
          "    patron = sanitize_input(patron)",
          "    # Intentar ripgrep primero (10-100x mas rapido)",
          "    rg_cmd = (",
          "        f'rg --max-count 50 --line-number --color never'",
          "        f' --glob \"!.git/**\" --glob \"!node_modules/**\"'",
          "        f' --glob \"!__pycache__/**\" --max-depth 10'",
          "        f' \"{patron}\" \"{ruta}\" 2>/dev/null'",
          "    )",
          "    result = ejecutar_comando(rg_cmd)",
          "    if result and 'command not found' not in result:",
          "        return result",
          "    # Fallback a grep",
          "    return ejecutar_comando(",
          "        f'grep -rn \"{patron}\" \"{ruta}\" --include=\"*.py\" ... 2>/dev/null | head -50'",
          "    )",
        ]),

        heading("4.6 Cache de Consultas Frecuentes [Prioridad Media]", HeadingLevel.HEADING_2),

        body("La adici\u00f3n de una cach\u00e9 de consultas a nivel de VectorStore permite evitar llamadas repetidas de embedding para consultas id\u00e9nticas o muy similares. La implementaci\u00f3n propone un cache LRU con TTL que almacena los resultados de b\u00fasqueda indexados por el hash del query embedding. Cuando una consulta nueva tiene similitud coseno > 0.95 con una consulta cacheada, se reutilizan los resultados con un ajuste de score. Esto reduce las llamadas a Ollama en aproximadamente un 50% para sesiones de conversaci\u00f3n t\u00edpicas donde el usuario reformula la misma pregunta de manera ligeramente diferente."),

        // ============================================================
        // SECTION 5: B\u00daSQUEDA H\u00cdBRIDA
        // ============================================================
        heading("5. B\u00fasqueda H\u00edbrida BM25 + Vectorial: Dise\u00f1o Detallado"),

        body("La b\u00fasqueda h\u00edbrida es la mejora de mayor impacto porque aborda la limitaci\u00f3n fundamental del sistema actual: la dependencia exclusiva de la similitud coseno para la recuperaci\u00f3n. Mientras que la b\u00fasqueda vectorial es excelente para capturar similitud sem\u00e1ntica, es d\u00e9bil en coincidencias exactas de t\u00e9rminos espec\u00edficos como nombres propios, IDs, c\u00f3digos de error, o t\u00e9rminos t\u00e9cnicos precisos. BM25 complementa esta debilidad al ponderar estad\u00edsticamente la presencia de t\u00e9rminos exactos."),

        heading("5.1 Arquitectura del Sistema H\u00edbrido", HeadingLevel.HEADING_2),

        body("El sistema h\u00edbrido propuesto funciona en tres fases secuenciales. En la Fase 1 (Recuperaci\u00f3n Paralela), se ejecutan simult\u00e1neamente la b\u00fasqueda BM25 y la b\u00fasqueda vectorial, cada una retornando su propio ranking de candidatos con scores independientes. BM25 opera sobre el \u00edndice de textos completos mientras que la b\u00fasqueda vectorial opera sobre el \u00edndice de embeddings. Ambas fuentes recuperan limit * 2 candidatos para tener margen en la fusi\u00f3n."),

        body("En la Fase 2 (Fusi\u00f3n con Reciprocal Rank Fusion), se combinan los dos rankings usando RRF. Este m\u00e9todo es preferible a la combinaci\u00f3n lineal de scores porque: (1) no requiere normalizaci\u00f3n de scores entre sistemas con escalas diferentes, (2) es robusto ante outliers en los scores, y (3) es simple de implementar y calibrar. El par\u00e1metro k=60 es el valor est\u00e1ndar recomendado por la literatura acad\u00e9mica y funciona bien en pr\u00e1ctica."),

        body("En la Fase 3 (Re-ranking Opcional), se puede aplicar un re-ranker multi-se\u00f1al sobre los resultados fusionados para un refinamiento final. Esta fase es opcional y puede activarse cuando se requiere m\u00e1xima precisi\u00f3n a costa de mayor latencia."),

        makeTable(
          ["Par\u00e1metro", "Valor", "Descripci\u00f3n"],
          [
            ["BM25 k1", "1.5", "Saturaci\u00f3n de frecuencia de t\u00e9rmino"],
            ["BM25 b", "0.75", "Normalizaci\u00f3n por longitud de documento"],
            ["RRF k", "60", "Constante de suavizado de Reciprocal Rank Fusion"],
            ["Candidatos BM25", "limit * 2", "Sobre-recuperaci\u00f3n para fusi\u00f3n"],
            ["Candidatos Vectorial", "limit * 2", "Sobre-recuperaci\u00f3n para fusi\u00f3n"],
            ["min_similarity", "0.25", "Umbral reducido para h\u00edbrido (vs 0.3 actual)"],
          ]
        ),

        heading("5.2 Integraci\u00f3n con la Arquitectura Existente", HeadingLevel.HEADING_2),

        body("La integraci\u00f3n con la arquitectura existente se realiza a trav\u00e9s de una nueva clase HybridVectorStore que envuelve (wrapper pattern) el vector store existente y a\u00f1ade el \u00edndice BM25. El constructor recibe el vector store como dependencia y construye el \u00edndice BM25 a partir de los textos existentes. Cada vez que se a\u00f1ade un nuevo documento (add()), se actualiza tanto el vector store como el \u00edndice BM25. El m\u00e9todo search() ejecuta ambas b\u00fasquedas en paralelo y fusiona con RRF."),

        body("La f\u00e1brica create_vector_store() se modifica para retornar HybridVectorStore(envuelto) en lugar del vector store directamente. Esto mantiene la interfaz existente sin cambios, lo que significa que TripleMemory y ReactAgent no necesitan ninguna modificaci\u00f3n. La clase HybridVectorStore delega todos los m\u00e9todos que no son search() (add, count, cleanup, etc.) al vector store interno, a\u00f1adiendo solo la l\u00f3gica de mantenimiento del \u00edndice BM25."),

        ...codeBlock([
          "class HybridVectorStore:",
          "    def __init__(self, vector_store):",
          "        self._vs = vector_store",
          "        self._bm25 = None",
          "        self._rebuild_bm25_index()",
          "",
          "    def _rebuild_bm25_index(self):",
          "        docs = [e['text'] for e in self._vs.index]",
          "        self._bm25 = BM25(docs) if docs else None",
          "",
          "    def add(self, text, metadata=None, entry_id=None, skip_embedding=False):",
          "        result = self._vs.add(text, metadata, entry_id, skip_embedding)",
          "        if self._bm25:",
          "            self._bm25.add_document(text)",
          "        return result",
          "",
          "    def search(self, query, limit=5, min_similarity=0.25):",
          "        # Fase 1: Recuperaci\u00f3n paralela",
          "        vector_results = self._vs.search(query, limit=limit*2, min_similarity=0.2)",
          "        bm25_results = self._bm25.search(query, limit=limit*2) if self._bm25 else []",
          "        # Fase 2: Fusi\u00f3n RRF",
          "        v_ids = [r['id'] for r in vector_results]",
          "        b_ids = [self._vs.index[i]['id'] for i, _ in bm25_results]",
          "        fused = reciprocal_rank_fusion([v_ids, b_ids])",
          "        # Mapear de vuelta a resultados completos",
          "        id_to_result = {r['id']: r for r in vector_results}",
          "        return [id_to_result[doc_id] for doc_id, _ in fused[:limit] if doc_id in id_to_result]",
          "",
          "    # Delegar al vector store interno",
          "    def count(self): return self._vs.count()",
          "    def cleanup(self, max_entries=500):",
          "        result = self._vs.cleanup(max_entries)",
          "        self._rebuild_bm25_index()",
          "        return result",
        ]),

        // ============================================================
        // SECTION 6: MEJORAS WEB SEARCH
        // ============================================================
        heading("6. Mejoras de B\u00fasqueda Web: Dise\u00f1o Detallado"),

        heading("6.1 Migraci\u00f3n a duckduckgo-search", HeadingLevel.HEADING_2),

        body("La librer\u00eda duckduckgo-search (paquete DDG) proporciona una API Python estable y mantenida para interactuar con DuckDuckGo. A diferencia del scraping manual actual, esta librer\u00eda maneja autom\u00e1ticamente: rotaci\u00f3n de proxies, user agents aleatorios, reintentos con backoff, y parsing robusto de resultados. La API es simple: DDGS().text(query, max_results=5) retorna una lista de diccionarios con title, href, y body."),

        body("La migraci\u00f3n propuesta mantiene compatibilidad con el formato de salida actual del agente pero a\u00f1ade metadatos enriquecidos. Cada resultado incluye: t\u00edtulo, URL, snippet, fecha (si disponible), y tipo de contenido detectado (art\u00edculo, video, PDF, documentaci\u00f3n). Se a\u00f1ade un filtro de calidad que elimina resultados de baja calidad (spam, contenido duplicado, dominios conocidos de baja fiabilidad) antes de presentarlos al agente."),

        heading("6.2 Sistema de Cach\u00e9 con TTL", HeadingLevel.HEADING_2),

        body("El cach\u00e9 de b\u00fasqueda web almacena resultados por consulta con un TTL de 5 minutos. Esto es particularmente \u00fatil en conversaciones donde el agente puede buscar informaci\u00f3n complementaria sobre el mismo tema m\u00faltiples veces. La implementaci\u00f3n usa un diccionario simple con timestamps, sin dependencias externas como Redis, manteniendo la filosof\u00eda de cero dependencias extras del agente."),

        body("El cach\u00e9 tiene un tama\u00f1o m\u00e1ximo de 50 entradas con evicci\u00f3n LRU. Cuando se alcanza el l\u00edmite, se elimina la entrada menos recientemente usada. El TTL es configurable: 5 minutos para b\u00fasquedas generales, 1 minuto para b\u00fasquedas de noticias/actualidad, y 30 minutos para b\u00fasquedas de documentaci\u00f3n t\u00e9cnica que cambian poco."),

        heading("6.3 Fallback Multi-Engine", HeadingLevel.HEADING_2),

        body("El sistema propone un fallback en cascada entre m\u00faltiples fuentes de b\u00fasqueda. Si DuckDuckGo falla tras 3 reintentos, se intenta con la DuckDuckGo Instant Answer API (que usa un endpoint diferente), luego con Wikipedia API para consultas enciclop\u00e9dicas, y finalmente con un resultado de emergencia que indica al usuario que la b\u00fasqueda fall\u00f3 y sugiere t\u00e9rminos alternativos basados en la consulta original. Este fallback garantiza que el agente siempre pueda proporcionar alguna respuesta \u00fatil, incluso cuando los servicios web principales est\u00e9n ca\u00eddos."),

        makeTable(
          ["Prioridad", "Motor", "Tipo", "Casos de Uso"],
          [
            ["1", "DuckDuckGo (duckduckgo-search)", "General", "B\u00fasquedas generales, noticias, docs"],
            ["2", "DuckDuckGo Instant Answer API", "Resumen", "Definiciones, datos r\u00e1pidos"],
            ["3", "Wikipedia API", "Enciclop\u00e9dico", "Conceptos, historia, ciencia"],
            ["4", "SearXNG (si disponible)", "Meta-buscador", "Agrega Google, Bing, etc."],
          ]
        ),

        // ============================================================
        // SECTION 7: PIPELINE DE RE-RANKING
        // ============================================================
        heading("7. Pipeline de Re-ranking: Dise\u00f1o Detallado"),

        heading("7.1 Se\u00f1ales de Re-ranking", HeadingLevel.HEADING_2),

        body("El re-ranker multi-se\u00f1al propuesto combina cinco se\u00f1ales complementarias, cada una capturando un aspecto diferente de la relevancia. La se\u00f1al sem\u00e1ntica (similitud coseno) mide la cercan\u00eda conceptual entre query y documento. La se\u00f1al l\u00e9xica (BM25) mide la presencia de t\u00e9rminos exactos de la consulta. La se\u00f1al de frescura (decaimiento temporal) prioriza informaci\u00f3n reciente. La se\u00f1al de cobertura mide cu\u00e1ntos t\u00e9rminos de la consulta aparecen en el documento. La se\u00f1al de tipo prioriza conocimiento factual sobre conversaci\u00f3n casual."),

        makeTable(
          ["Se\u00f1al", "Peso", "Normalizaci\u00f3n", "Fuente"],
          [
            ["Sem\u00e1ntica (coseno)", "0.35", "Ya en [0,1]", "VectorStore.search()"],
            ["L\u00e9xica (BM25)", "0.25", "min-max sobre candidatos", "BM25.search()"],
            ["Frescura (temporal)", "0.15", "Ya en [0.1,1.0]", "_compute_decay()"],
            ["Cobertura de t\u00e9rminos", "0.15", "matches / total_terms", "C\u00e1lculo directo"],
            ["Bonus de tipo", "0.10", "0.0-1.0 por tipo", "metadata.type"],
          ]
        ),

        heading("7.2 Pesos Adaptativos por Tipo de Consulta", HeadingLevel.HEADING_2),

        body("Los pesos del re-ranker no son est\u00e1ticos sino que se adaptan seg\u00fan el tipo de consulta detectado. Para consultas factuales (\u00bfqu\u00e9 es X?, \u00bfc\u00f3mo funciona Y?), la se\u00f1al sem\u00e1ntica y el bonus de tipo conocimiento reciben mayor peso. Para consultas de b\u00fasqueda exacta (\u00bfd\u00f3nde dice 'error 404'?), la se\u00f1al l\u00e9xica y la cobertura reciben mayor peso. Para consultas recientes (\u00bfqu\u00e9 hablamos ayer?), la se\u00f1al de frescura recibe mayor peso."),

        body("La detecci\u00f3n del tipo de consulta se realiza con heur\u00edsticas simples basadas en patrones l\u00e9xicos: si la consulta contiene 'qu\u00e9 es' o 'c\u00f3mo' se clasifica como factual; si contiene comillas o t\u00e9rminos t\u00e9cnicos espec\u00edficos se clasifica como exacta; si contiene 'ayer', 'antes', 'anterior' se clasifica como temporal. Esta clasificaci\u00f3n no necesita ser perfecta; incluso una aproximaci\u00f3n burda mejora los resultados sobre el sistema actual que no distingue tipos de consulta."),

        heading("7.3 Integraci\u00f3n en el Pipeline Existente", HeadingLevel.HEADING_2),

        body("El re-ranker se inserta entre la fase de recuperaci\u00f3n (search()) y la fase de construcci\u00f3n de contexto (get_context_for()). En TripleMemory.recall(), despu\u00e9s de obtener los resultados del vector store, se pasan por el re-ranker antes de retornarlos. Esto asegura que los 3 resultados que se incluyen en el contexto enriquecido sean los m\u00e1s relevantes seg\u00fan m\u00faltiples se\u00f1ales, no solo seg\u00fan similitud coseno. La latencia adicional es m\u00ednima (menos de 1ms por consulta) porque el re-ranking opera sobre un conjunto peque\u00f1o de candidatos (t\u00edpicamente 10-15)."),

        // ============================================================
        // SECTION 8: PLAN DE IMPLEMENTACI\u00d3N
        // ============================================================
        heading("8. Plan de Implementaci\u00f3n"),

        body("El plan de implementaci\u00f3n se estructura en cuatro fases que permiten entregas incrementales con valor inmediato. Cada fase se puede implementar y probar de forma independiente, sin bloquear las dem\u00e1s. Las dependencias entre mejoras se han minimizado deliberadamente para permitir progreso paralelo."),

        heading("8.1 Fase 1: Fundamentos (Semana 1)", HeadingLevel.HEADING_2),

        makeTable(
          ["Tarea", "Archivos", "Esfuerzo", "Dependencias"],
          [
            ["Implementar BM25 con stemmer espa\u00f1ol", "memory/bm25.py (nuevo)", "4 horas", "Ninguna"],
            ["Mejorar pre-filtro con stemming + stopwords", "memory/vectorstore.py", "2 horas", "bm25.py"],
            ["Migrar web search a duckduckgo-search", "tools/web.py", "3 horas", "pip install duckduckgo-search"],
            ["A\u00f1adir cach\u00e9 y retry a web search", "tools/web.py", "2 horas", "Migraci\u00f3n DDG"],
            ["Reemplazar grep con ripgrep", "tools/archivos.py", "1 hora", "rg instalado"],
          ]
        ),

        heading("8.2 Fase 2: B\u00fasqueda H\u00edbrida (Semana 2)", HeadingLevel.HEADING_2),

        makeTable(
          ["Tarea", "Archivos", "Esfuerzo", "Dependencias"],
          [
            ["Implementar HybridVectorStore wrapper", "memory/hybrid.py (nuevo)", "4 horas", "bm25.py"],
            ["Implementar Reciprocal Rank Fusion", "memory/hybrid.py", "2 horas", "Ninguna"],
            ["Integrar en create_vector_store()", "memory/chroma_store.py", "1 hora", "hybrid.py"],
            ["Tests unitarios de b\u00fasqueda h\u00edbrida", "tests/test_hybrid.py (nuevo)", "3 horas", "hybrid.py"],
          ]
        ),

        heading("8.3 Fase 3: Re-ranking (Semana 3)", HeadingLevel.HEADING_2),

        makeTable(
          ["Tarea", "Archivos", "Esfuerzo", "Dependencias"],
          [
            ["Implementar MultiSignalReranker", "memory/reranker.py (nuevo)", "4 horas", "hybrid.py"],
            ["Clasificador de tipo de consulta", "memory/reranker.py", "2 horas", "Ninguna"],
            ["Pesos adaptativos por tipo de consulta", "memory/reranker.py", "2 horas", "Clasificador"],
            ["Integrar en TripleMemory.recall()", "memory/triple_memory.py", "1 hora", "reranker.py"],
            ["Tests de calidad de re-ranking", "tests/test_reranker.py (nuevo)", "2 horas", "reranker.py"],
          ]
        ),

        heading("8.4 Fase 4: Optimizaci\u00f3n y M\u00e9tricas (Semana 4)", HeadingLevel.HEADING_2),

        makeTable(
          ["Tarea", "Archivos", "Esfuerzo", "Dependencias"],
          [
            ["Cache de consultas frecuentes", "memory/vectorstore.py", "2 horas", "Ninguna"],
            ["Decaimiento diferenciado por tipo", "memory/chroma_store.py", "2 horas", "Ninguna"],
            ["Benchmark de precisi\u00f3n/recall", "tests/benchmark_search.py (nuevo)", "3 horas", "Todas"],
            ["Ajuste de hiperpar\u00e1metros", "config.py", "2 horas", "Benchmark"],
            ["Documentaci\u00f3n de API de b\u00fasqueda", "docs/search_api.md (nuevo)", "2 horas", "Todas"],
          ]
        ),

        body("El esfuerzo total estimado es de aproximadamente 41 horas de desarrollo, distribuidas en 4 semanas. La Fase 1 proporciona mejoras inmediatas con bajo riesgo, la Fase 2 es la de mayor impacto, la Fase 3 refina la calidad, y la Fase 4 optimiza y documenta. Cada fase incluye pruebas unitarias y de integraci\u00f3n para asegurar que las mejoras no introducen regresiones en la funcionalidad existente. Al finalizar las cuatro fases, el sistema de b\u00fasqueda del agente habr\u00e1 pasado de un sistema basado \u00fanicamente en similitud coseno a un pipeline de recuperaci\u00f3n moderno con b\u00fasqueda h\u00edbrida, re-ranking multi-se\u00f1al, y mecanismos robustos de fallback y cach\u00e9."),
      ]
    }
  ]
});

// Generate
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("/home/z/my-project/download/analisis_busqueda_agente_v14.docx", buf);
  console.log("Document generated: /home/z/my-project/download/analisis_busqueda_agente_v14.docx");
}).catch(err => {
  console.error("Error generating document:", err);
});
