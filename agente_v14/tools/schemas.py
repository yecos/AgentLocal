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
]
