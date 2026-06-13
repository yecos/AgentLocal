"""
=============================================================
AGENTE v14.7 - Esquemas de Function Calling para Ollama
=============================================================
Esquemas para function calling nativo de Ollama/qwen3.
v14.7: Incluye herramientas de Super Agente.
=============================================================
"""

TOOL_SCHEMAS = [
    # ============================================================
    # HERRAMIENTAS ORIGINALES
    # ============================================================
    {
        "type": "function",
        "function": {
            "name": "ejecutar_comando",
            "description": "Ejecuta un comando en la terminal. Peligrosos requieren confirmacion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comando": {"type": "string", "description": "Comando a ejecutar"},
                    "confirmar_peligroso": {"type": "boolean", "description": "True si el usuario confirmo un comando peligroso"}
                },
                "required": ["comando"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_aplicacion",
            "description": "Abre una aplicacion de escritorio por nombre. NO usar para abrir paginas web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "Nombre de la aplicacion (ej: whatsapp, chrome, vscode)"}
                },
                "required": ["app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_url",
            "description": "Abre una pagina web en el navegador. Reconoce nombres de sitios populares.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL o nombre del sitio (ej: youtube, https://google.com)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_youtube",
            "description": "Busca un video en YouTube y abre los resultados en el navegador.",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Que buscar en YouTube"}
                },
                "required": ["consulta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generar_codigo",
            "description": "Genera codigo COMPLETO usando el LLM y lo guarda en un archivo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "descripcion": {"type": "string", "description": "Que crear (detallado)"},
                    "tipo": {"type": "string", "enum": ["html", "python", "javascript", "css", "json", "markdown", "texto"], "description": "Tipo de archivo"},
                    "ruta": {"type": "string", "description": "Ruta donde guardar (opcional)"}
                },
                "required": ["descripcion", "tipo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leer_archivo",
            "description": "Lee el contenido de un archivo de texto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escribir_archivo",
            "description": "Crea o modifica un archivo de texto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo"},
                    "contenido": {"type": "string", "description": "Contenido a escribir"}
                },
                "required": ["ruta", "contenido"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_archivos",
            "description": "Lista archivos y carpetas de un directorio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del directorio"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analizar_proyecto",
            "description": "Analiza la estructura completa de un proyecto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del proyecto"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clonar_repositorio",
            "description": "Clona un repositorio de GitHub.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL del repositorio"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "instalar_dependencias",
            "description": "Instala dependencias de un proyecto. Detecta npm/pip/poetry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del proyecto"},
                    "gestor": {"type": "string", "description": "Gestor de paquetes (auto/npm/pip/poetry)"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_en_archivos",
            "description": "Busca texto dentro de archivos (como grep/findstr).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Directorio donde buscar"},
                    "patron": {"type": "string", "description": "Texto o patron a buscar"}
                },
                "required": ["ruta", "patron"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "procesos_activos",
            "description": "Lista procesos corriendo. Opcionalmente filtra por nombre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filtro": {"type": "string", "description": "Filtro por nombre de proceso"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "matar_proceso",
            "description": "Termina un proceso por PID o nombre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid_o_nombre": {"type": "string", "description": "PID numerico o nombre del proceso"}
                },
                "required": ["pid_o_nombre"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_web",
            "description": "Busca en internet cuando no sabes algo. Retorna resultados con links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Consulta de busqueda"}
                },
                "required": ["consulta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analizar_imagen",
            "description": "Analiza una imagen usando vision AI. Describe lo que ve o responde preguntas. Necesita modelo de vision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta de la imagen"},
                    "pregunta": {"type": "string", "description": "Pregunta sobre la imagen"}
                },
                "required": ["ruta"]
            }
        }
    },
    # ============================================================
    # v14.7 SUPER AGENTE - LECTURA DE DOCUMENTOS
    # ============================================================
    {
        "type": "function",
        "function": {
            "name": "leer_documento",
            "description": "Lee cualquier documento detectando el formato automaticamente. Soporta PDF, DOCX, XLSX, PPTX, CSV, ZIP, TAR, SQLite, ePub y texto plano. HERRAMIENTA PRINCIPAL para leer documentos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo a leer"},
                    "hoja": {"type": "string", "description": "Nombre de hoja (solo XLSX)"},
                    "consulta": {"type": "string", "description": "Consulta SQL SELECT (solo SQLite)"},
                    "tabla": {"type": "string", "description": "Tabla a ver (solo SQLite/XLSX)"},
                    "archivo_interno": {"type": "string", "description": "Archivo interno a extraer (solo ZIP/TAR)"},
                    "pagina_inicio": {"type": "integer", "description": "Pagina inicial (solo PDF, 1-indexed)"},
                    "pagina_fin": {"type": "integer", "description": "Pagina final (solo PDF)"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leer_pdf",
            "description": "Lee el contenido de un archivo PDF. Extrae texto, tablas e informacion de paginas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo PDF"},
                    "pagina_inicio": {"type": "integer", "description": "Pagina inicial (1-indexed)"},
                    "pagina_fin": {"type": "integer", "description": "Pagina final"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leer_docx",
            "description": "Lee un documento Word (.docx). Extrae texto, tablas y estilos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo .docx"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leer_xlsx",
            "description": "Lee un archivo Excel (.xlsx). Extrae datos de hojas con formato tabla.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo .xlsx"},
                    "hoja": {"type": "string", "description": "Nombre de la hoja (opcional)"},
                    "max_filas": {"type": "integer", "description": "Maximo filas a leer (default 50)"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leer_pptx",
            "description": "Lee una presentacion PowerPoint (.pptx). Extrae texto de diapositivas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo .pptx"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_sqlite",
            "description": "Consulta una base de datos SQLite. Lista tablas o ejecuta SELECT.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo .db o .sqlite"},
                    "consulta": {"type": "string", "description": "Consulta SQL SELECT (opcional)"},
                    "tabla": {"type": "string", "description": "Tabla para ver contenido (opcional)"},
                    "max_filas": {"type": "integer", "description": "Maximo filas (default 50)"}
                },
                "required": ["ruta"]
            }
        }
    },
    # ============================================================
    # v14.7 SUPER AGENTE - CREACION DE DOCUMENTOS
    # ============================================================
    {
        "type": "function",
        "function": {
            "name": "crear_pdf",
            "description": "Crea un documento PDF con texto formateado. Soporta titulos, headers, listas y parrafos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta donde guardar el PDF"},
                    "titulo": {"type": "string", "description": "Titulo del documento"},
                    "contenido": {"type": "string", "description": "Contenido del documento (soporta # headers, - listas, saltos de linea)"}
                },
                "required": ["ruta", "contenido"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crear_docx",
            "description": "Crea un documento Word (.docx) con formato. Soporta Markdown basico.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta donde guardar el .docx"},
                    "titulo": {"type": "string", "description": "Titulo del documento"},
                    "contenido": {"type": "string", "description": "Contenido (formato Markdown: # headers, - listas)"}
                },
                "required": ["ruta", "contenido"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crear_xlsx",
            "description": "Crea un archivo Excel (.xlsx) con datos. Los datos se pasan como CSV o JSON.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta donde guardar el .xlsx"},
                    "datos": {"type": "string", "description": "Datos en formato CSV (filas por newline, columnas por coma) o JSON"},
                    "hoja": {"type": "string", "description": "Nombre de la hoja (default: Hoja1)"}
                },
                "required": ["ruta", "datos"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crear_grafico",
            "description": "Crea un grafico o visualizacion y lo guarda como PNG. Tipos: bar, line, pie, scatter, histogram, area.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta donde guardar el PNG"},
                    "tipo": {"type": "string", "enum": ["bar", "line", "pie", "scatter", "histogram", "area"], "description": "Tipo de grafico"},
                    "datos": {"type": "string", "description": "Datos: etiqueta,valor por linea (CSV) o JSON"},
                    "titulo": {"type": "string", "description": "Titulo del grafico"},
                    "xlabel": {"type": "string", "description": "Etiqueta eje X"},
                    "ylabel": {"type": "string", "description": "Etiqueta eje Y"}
                },
                "required": ["ruta", "tipo", "datos"]
            }
        }
    },
    # ============================================================
    # v14.7 SUPER AGENTE - PERCEPCION
    # ============================================================
    {
        "type": "function",
        "function": {
            "name": "transcribir_audio",
            "description": "Transcribe un archivo de audio a texto. Soporta MP3, WAV, M4A, FLAC, OGG.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo de audio"},
                    "idioma": {"type": "string", "description": "Idioma (es=espanol, en=ingles, auto=deteccion)"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leer_imagen_ocr",
            "description": "Extrae texto de una imagen usando OCR. Para documentos escaneados, capturas de pantalla, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta de la imagen"},
                    "idioma": {"type": "string", "description": "Idioma OCR (spa=espanol, eng=ingles, spa+eng=ambos)"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrapear_web",
            "description": "Extrae el contenido textual de una pagina web. Lee HTML y extrae texto limpio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL de la pagina web"},
                    "selector": {"type": "string", "description": "Selector CSS para seccion especifica (opcional)"},
                    "max_caracteres": {"type": "integer", "description": "Maximo caracteres (default 5000)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "automatizar_web",
            "description": "Interactua con paginas web: screenshots, clicks, escribir texto, extraer contenido. Requiere Playwright.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL de la pagina"},
                    "accion": {"type": "string", "enum": ["screenshot", "click", "escribir", "extraer", "scroll"], "description": "Accion a realizar"},
                    "selector": {"type": "string", "description": "Selector CSS del elemento"},
                    "texto": {"type": "string", "description": "Texto a escribir (para accion escribir)"},
                    "esperar": {"type": "integer", "description": "Segundos a esperar (default 3)"}
                },
                "required": ["url", "accion"]
            }
        }
    },
    # ============================================================
    # v14.7 SUPER AGENTE - INTEGRACION
    # ============================================================
    {
        "type": "function",
        "function": {
            "name": "leer_email",
            "description": "Lee correos del inbox usando IMAP. Requiere configuracion previa con configurar_email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "carpeta": {"type": "string", "description": "Carpeta (INBOX, Sent, etc.)"},
                    "limite": {"type": "integer", "description": "Maximo correos (default 10)"},
                    "no_leidos": {"type": "boolean", "description": "Solo no leidos (default True)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "enviar_email",
            "description": "Envia un correo electronico. Requiere configuracion previa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "para": {"type": "string", "description": "Email del destinatario"},
                    "asunto": {"type": "string", "description": "Asunto del correo"},
                    "cuerpo": {"type": "string", "description": "Cuerpo del mensaje"},
                    "html": {"type": "boolean", "description": "Si el cuerpo es HTML (default False)"}
                },
                "required": ["para", "asunto", "cuerpo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "configurar_email",
            "description": "Configura la cuenta de email para leer y enviar. Para Gmail necesitas App Password.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host_imap": {"type": "string", "description": "Servidor IMAP (ej: imap.gmail.com)"},
                    "puerto_imap": {"type": "integer", "description": "Puerto IMAP (ej: 993)"},
                    "email_addr": {"type": "string", "description": "Direccion de email"},
                    "password": {"type": "string", "description": "Contrasena o App Password"},
                    "host_smtp": {"type": "string", "description": "Servidor SMTP (opcional)"},
                    "puerto_smtp": {"type": "integer", "description": "Puerto SMTP (default 587)"}
                },
                "required": ["host_imap", "puerto_imap", "email_addr", "password"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "llamar_api",
            "description": "Realiza una peticion HTTP a cualquier API REST. Soporta GET, POST, PUT, DELETE.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL de la API"},
                    "metodo": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"], "description": "Metodo HTTP"},
                    "headers": {"type": "string", "description": "Headers en JSON (opcional)"},
                    "body": {"type": "string", "description": "Cuerpo JSON (opcional)"},
                    "timeout": {"type": "integer", "description": "Timeout en segundos (default 30)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "programar_tarea",
            "description": "Programa una tarea para ejecutarse en el futuro.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre descriptivo"},
                    "comando": {"type": "string", "description": "Comando a ejecutar"},
                    "cuando": {"type": "string", "description": "Cuando ejecutar (ej: 'manana 8am', '2025-01-15 09:00')"},
                    "repetir": {"type": "string", "description": "Repeticion: 'diario', 'cada 2 horas', 'semanal' (vacio = una vez)"}
                },
                "required": ["nombre", "comando"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leer_portapapeles",
            "description": "Lee el contenido del portapapeles del sistema.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escribir_portapapeles",
            "description": "Escribe texto en el portapapeles del sistema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "Texto a copiar"}
                },
                "required": ["texto"]
            }
        }
    },
    # ============================================================
    # v15 SUPER AGENTE - VISUALIZACION AVANZADA
    # ============================================================
    {
        "type": "function",
        "function": {
            "name": "crear_grafico_avanzado",
            "description": "Crea un grafico avanzado (15+ tipos) y lo guarda como PNG/SVG. Tipos: bar, line, pie, scatter, histogram, area, heatmap, radar, candlestick, boxplot, waterfall, regression, distribution, violin, stem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta donde guardar (PNG o SVG)"},
                    "tipo": {"type": "string", "enum": ["bar", "line", "pie", "scatter", "histogram", "area", "heatmap", "radar", "candlestick", "boxplot", "waterfall", "regression", "distribution", "violin", "stem"], "description": "Tipo de grafico"},
                    "datos": {"type": "string", "description": "Datos en JSON o CSV"},
                    "titulo": {"type": "string", "description": "Titulo del grafico"},
                    "xlabel": {"type": "string", "description": "Etiqueta eje X"},
                    "ylabel": {"type": "string", "description": "Etiqueta eje Y"},
                    "opciones": {"type": "string", "description": "Opciones extra en JSON (colores, leyenda, grid, etc.)"}
                },
                "required": ["ruta", "tipo", "datos"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crear_dashboard",
            "description": "Crea un dashboard con multiples graficos en una sola imagen. Cada grafico se define como JSON con tipo, datos y opciones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta donde guardar el dashboard (PNG o SVG)"},
                    "graficos": {"type": "string", "description": "Lista JSON de graficos: [{tipo, datos, titulo}, ...]"},
                    "titulo": {"type": "string", "description": "Titulo del dashboard"},
                    "layout": {"type": "string", "description": "Layout: auto, 2x2, 3x2, 2x3, 1x3, 3x1"}
                },
                "required": ["ruta", "graficos"]
            }
        }
    },
    # ============================================================
    # v15 SUPER AGENTE - DIAGRAMAS
    # ============================================================
    {
        "type": "function",
        "function": {
            "name": "crear_diagrama",
            "description": "Crea un diagrama (13+ tipos) y lo guarda como imagen PNG. Tipos: flowchart, mindmap, tree, org, architecture, network, er, class, gantt, swimlane, sequence, topology, knowledge_graph, mermaid.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta donde guardar (PNG, SVG, o .md para Mermaid)"},
                    "tipo": {"type": "string", "description": "Tipo de diagrama"},
                    "datos": {"type": "string", "description": "Datos del diagrama en JSON (nodes, edges, hierarchy, etc.)"},
                    "titulo": {"type": "string", "description": "Titulo del diagrama"},
                    "opciones": {"type": "string", "description": "Opciones extra en JSON"}
                },
                "required": ["ruta", "tipo", "datos"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generar_mermaid",
            "description": "Genera codigo Mermaid para un diagrama sin renderizar. Retorna el codigo listo para usar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "description": "Tipo de diagrama"},
                    "datos": {"type": "string", "description": "Datos del diagrama en JSON"},
                    "titulo": {"type": "string", "description": "Titulo (opcional)"}
                },
                "required": ["tipo", "datos"]
            }
        }
    },
    # ============================================================
    # v15 SUPER AGENTE - PROCESAMIENTO DE DATOS
    # ============================================================
    {
        "type": "function",
        "function": {
            "name": "ejecutar_python",
            "description": "Ejecuta codigo Python en un subproceso aislado y retorna la salida.",
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {"type": "string", "description": "Codigo Python a ejecutar"},
                    "timeout": {"type": "integer", "description": "Timeout en segundos (default 60)"}
                },
                "required": ["codigo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ejecutar_bash",
            "description": "Ejecuta un comando Bash/Linux y retorna la salida.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comando": {"type": "string", "description": "Comando Bash a ejecutar"},
                    "timeout": {"type": "integer", "description": "Timeout en segundos (default 30)"}
                },
                "required": ["comando"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ejecutar_nodo",
            "description": "Ejecuta codigo JavaScript/Node.js y retorna la salida.",
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {"type": "string", "description": "Codigo JavaScript a ejecutar"},
                    "timeout": {"type": "integer", "description": "Timeout en segundos (default 30)"}
                },
                "required": ["codigo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "estadisticas",
            "description": "Calcula estadisticas descriptivas de un dataset: media, mediana, desv.est, percentiles, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "datos": {"type": "string", "description": "Datos en formato CSV o JSON"},
                    "columna": {"type": "string", "description": "Columna especifica (opcional)"}
                },
                "required": ["datos"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tabla_pivote",
            "description": "Crea una tabla pivote a partir de datos tabulares.",
            "parameters": {
                "type": "object",
                "properties": {
                    "datos": {"type": "string", "description": "Datos en CSV o JSON"},
                    "filas": {"type": "string", "description": "Columna para las filas"},
                    "columnas": {"type": "string", "description": "Columna para las columnas"},
                    "valores": {"type": "string", "description": "Columna de valores a agregar"},
                    "funcion": {"type": "string", "description": "Funcion: sum, mean, count, min, max"}
                },
                "required": ["datos", "filas"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "merge_datos",
            "description": "Combina dos datasets usando merge/join (como SQL JOIN).",
            "parameters": {
                "type": "object",
                "properties": {
                    "datos1": {"type": "string", "description": "Primer dataset (CSV o JSON)"},
                    "datos2": {"type": "string", "description": "Segundo dataset (CSV o JSON)"},
                    "clave": {"type": "string", "description": "Columna clave para el join"},
                    "tipo": {"type": "string", "description": "Tipo: inner, left, right, outer"}
                },
                "required": ["datos1", "datos2"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "limpiar_datos",
            "description": "Limpia un dataset: elimina duplicados, trata nulos, elimina outliers, normaliza.",
            "parameters": {
                "type": "object",
                "properties": {
                    "datos": {"type": "string", "description": "Datos en CSV o JSON"},
                    "operaciones": {"type": "string", "description": "Operaciones: duplicados, nulos, outliers, normalizar, tipos, todo"}
                },
                "required": ["datos"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "transformar_datos",
            "description": "Transforma datos: filtrar, ordenar, agrupar, seleccionar, renombrar columnas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "datos": {"type": "string", "description": "Datos en CSV o JSON"},
                    "operacion": {"type": "string", "description": "Operacion: filtrar, ordenar, agrupar, seleccionar, renombrar, agregar_columna, head, sample"},
                    "parametros": {"type": "string", "description": "Parametros en JSON"}
                },
                "required": ["datos", "operacion"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parsear_datos",
            "description": "Convierte datos entre formatos: CSV, JSON, TSV, YAML, XML.",
            "parameters": {
                "type": "object",
                "properties": {
                    "datos": {"type": "string", "description": "Datos en formato de origen"},
                    "formato_origen": {"type": "string", "description": "Formato: auto, csv, json, tsv, yaml, xml"},
                    "formato_destino": {"type": "string", "description": "Formato: json, csv, tsv, yaml, tabla"}
                },
                "required": ["datos"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "exportar_datos",
            "description": "Exporta datos a un archivo en formato CSV, JSON, XLSX o TSV.",
            "parameters": {
                "type": "object",
                "properties": {
                    "datos": {"type": "string", "description": "Datos en CSV o JSON"},
                    "ruta": {"type": "string", "description": "Ruta del archivo de salida"},
                    "formato": {"type": "string", "description": "Formato: csv, json, xlsx, tsv"}
                },
                "required": ["datos", "ruta"]
            }
        }
    },
    # ============================================================
    # v15 SUPER AGENTE - MULTIMEDIA
    # ============================================================
    {
        "type": "function",
        "function": {
            "name": "texto_a_voz",
            "description": "Convierte texto a voz (TTS). Genera un archivo de audio con el texto hablado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "Texto a convertir a voz"},
                    "ruta": {"type": "string", "description": "Ruta donde guardar el audio (opcional)"},
                    "voz": {"type": "string", "description": "Idioma/voz: es, en, fr, de, pt, it, ja, ko, zh"},
                    "velocidad": {"type": "number", "description": "Velocidad (0.5=lenta, 1.0=normal, 2.0=rapida)"},
                    "formato": {"type": "string", "description": "Formato: mp3, wav"}
                },
                "required": ["texto"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generar_imagen",
            "description": "Genera una imagen a partir de una descripcion usando IA (Stable Diffusion, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "descripcion": {"type": "string", "description": "Descripcion de la imagen (prompt)"},
                    "ruta": {"type": "string", "description": "Ruta donde guardar (opcional)"},
                    "tamano": {"type": "string", "description": "Tamano: 256x256, 512x512, 768x768"},
                    "estilo": {"type": "string", "description": "Estilo: realista, anime, pintura, etc."},
                    "negativo": {"type": "string", "description": "Prompt negativo (que NO incluir)"}
                },
                "required": ["descripcion"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "editar_imagen",
            "description": "Edita una imagen: redimensionar, recortar, rotar, convertir, grayscale, ajustar brillo/contraste.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta_entrada": {"type": "string", "description": "Ruta de la imagen"},
                    "accion": {"type": "string", "description": "Accion: info, redimensionar, recortar, rotar, convertir, espejo, grayscale, ajustar"},
                    "parametros": {"type": "string", "description": "Parametros en JSON segun la accion"},
                    "ruta_salida": {"type": "string", "description": "Ruta de salida (opcional, sobreescribe si vacio)"}
                },
                "required": ["ruta_entrada", "accion"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_imagenes",
            "description": "Busca imagenes en internet a partir de una consulta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Texto de busqueda"},
                    "cantidad": {"type": "integer", "description": "Cantidad de imagenes (max 10)"}
                },
                "required": ["consulta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analizar_video",
            "description": "Analiza un archivo de video: info, extraer frames, analizar con VLM, transcribir audio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del video"},
                    "accion": {"type": "string", "description": "Accion: info, frames, analizar, transcribir"},
                    "parametros": {"type": "string", "description": "Parametros extra en JSON"}
                },
                "required": ["ruta", "accion"]
            }
        }
    },
    # ============================================================
    # v15 SUPER AGENTE - SUB-AGENTES
    # ============================================================
    {
        "type": "function",
        "function": {
            "name": "ejecutar_subagente",
            "description": "Ejecuta un sub-agente especializado: researcher, coder, analyst, writer, reviewer, general.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "description": "Tipo: researcher, coder, analyst, writer, reviewer, general"},
                    "tarea": {"type": "string", "description": "Descripcion de la tarea"},
                    "contexto": {"type": "string", "description": "Contexto adicional (opcional)"},
                    "timeout": {"type": "integer", "description": "Timeout en segundos (default 60)"}
                },
                "required": ["tipo", "tarea"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ejecutar_paralelo",
            "description": "Ejecuta multiples sub-agentes en paralelo. Lista JSON de tareas con tipo y descripcion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tareas": {"type": "string", "description": "Lista JSON: [{tipo, tarea, contexto?}, ...]"},
                    "agregar_resultados": {"type": "boolean", "description": "Sintetizar resultados (default True)"}
                },
                "required": ["tareas"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "orquestar",
            "description": "Orquesta automaticamente sub-agentes para una tarea compleja. Divide, asigna y sintetiza.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tarea_principal": {"type": "string", "description": "Descripcion de la tarea compleja"},
                    "estrategia": {"type": "string", "description": "Estrategia: auto, secuencial, paralelo, mixto"},
                    "max_subagentes": {"type": "integer", "description": "Max sub-agentes (default 4)"}
                },
                "required": ["tarea_principal"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crear_pptx",
            "description": "Crea una presentacion PowerPoint (.pptx) con diapositivas formateadas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta donde guardar el .pptx"},
                    "titulo": {"type": "string", "description": "Titulo de la presentacion"},
                    "diapositivas": {"type": "string", "description": "Lista JSON: [{titulo, contenido, notas}, ...]"},
                    "autor": {"type": "string", "description": "Autor de la presentacion"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_subagentes",
            "description": "Lista los tipos de sub-agentes disponibles y sus capacidades.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    # ============================================================
    # v15.2 SUPER AGENTE - HERRAMIENTAS AVANZADAS
    # ============================================================
    {
        "type": "function",
        "function": {
            "name": "busqueda_profunda",
            "description": "Realiza una busqueda profunda multi-ronda sobre un tema. Busca en multiples fuentes, sigue enlaces relevantes y sintetiza un informe completo. Ideal para investigaciones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tema": {"type": "string", "description": "Tema a investigar en profundidad"},
                    "profundidad": {"type": "integer", "description": "Nivel de profundidad: 1=rapido, 2=medio, 3=profundo (default 3)"},
                    "idioma": {"type": "string", "description": "Idioma preferido: es, en, fr, de, pt (default es)"},
                    "guardar": {"type": "boolean", "description": "Guardar informe en archivo (default True)"}
                },
                "required": ["tema"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "editar_multiples",
            "description": "Realiza multiples ediciones en uno o varios archivos en una sola operacion. Cada edicion especifica archivo, texto a buscar y texto nuevo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ediciones": {"type": "string", "description": "Lista JSON: [{archivo, buscar, reemplazar, reemplazar_todo?}, ...]"},
                    "crear_archivos": {"type": "boolean", "description": "Crear archivos que no existen (default True)"}
                },
                "required": ["ediciones"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generacion_batch",
            "description": "Genera multiples archivos en una sola operacion. Ideal para crear estructuras de proyecto o templates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "archivos": {"type": "string", "description": "Lista JSON: [{ruta, contenido, sobreescribir?}, ...]"}
                },
                "required": ["archivos"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_patron",
            "description": "Busca un patron de texto o regex en archivos (como grep). Busca en el contenido de archivos del directorio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patron": {"type": "string", "description": "Patron de texto o expresion regular"},
                    "directorio": {"type": "string", "description": "Directorio donde buscar (default .)"},
                    "tipo_archivo": {"type": "string", "description": "Filtrar por extension: .py, .js, .txt, .md"},
                    "max_resultados": {"type": "integer", "description": "Max resultados (default 30)"},
                    "ignorar_case": {"type": "boolean", "description": "Ignorar mayusculas/minusculas (default True)"},
                    "contexto": {"type": "integer", "description": "Lineas de contexto antes/despues (default 2)"}
                },
                "required": ["patron"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_glob",
            "description": "Lista archivos usando glob patterns (ej: **/*.py, src/**/*.ts, **/test_*.js). Busqueda flexible por nombre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patron": {"type": "string", "description": "Patron glob: **/*.py, **/test_*.js, *.md (default **/*)"},
                    "directorio": {"type": "string", "description": "Directorio base (default actual)"},
                    "solo_tipo": {"type": "string", "description": "Filtrar: todos, archivos, directorios"},
                    "max_resultados": {"type": "integer", "description": "Max resultados (default 100)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crear_proyecto_web",
            "description": "Crea un proyecto web con scaffolding completo. Soporta Next.js, React, Vue, Express y sitios estaticos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre del proyecto"},
                    "tipo": {"type": "string", "description": "Tipo: nextjs, react, vue, express, static (default nextjs)"},
                    "directorio": {"type": "string", "description": "Directorio donde crear el proyecto (default REPOS_DIR)"},
                    "opciones": {"type": "string", "description": "Opciones JSON: {typescript, tailwind, prisma}"}
                },
                "required": ["nombre"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "resumir_url",
            "description": "Lee y extrae contenido de una URL web. Puede extraer texto, metadatos, links, imagenes o HTML crudo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL de la pagina web"},
                    "max_caracteres": {"type": "integer", "description": "Max caracteres a extraer (default 5000)"},
                    "extraer": {"type": "string", "description": "Que extraer: texto, metadatos, html, links, imagenes (default texto)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ver_contexto_compartido",
            "description": "Muestra el contenido del contexto compartido entre sub-agentes.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "limpiar_contexto",
            "description": "Limpia el contexto compartido entre sub-agentes.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]
