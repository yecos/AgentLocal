"""
=============================================================
AGENTE v14 - Esquemas de Function Calling para Ollama
=============================================================
Esquemas para function calling nativo de Ollama/qwen3.
=============================================================
"""

TOOL_SCHEMAS = [
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
            "description": "Abre una aplicacion de escritorio por nombre. Busca automaticamente en Start Menu, registro y disco. NO usar para abrir paginas web o sitios como YouTube, Google, etc. Para eso usar abrir_url.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "Nombre de la aplicacion de escritorio (ej: whatsapp, chrome, autocad, vscode)"}
                },
                "required": ["app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_url",
            "description": "Abre una pagina web o sitio en el navegador. Usar cuando el usuario pide abrir sitios web como YouTube, Google, Gmail, Netflix, etc. Tambien acepta URLs completas. Reconoce nombres de sitios populares automaticamente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL o nombre del sitio web (ej: youtube, https://google.com, netflix)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_youtube",
            "description": "Busca un video en YouTube y abre los resultados en el navegador. Usar cuando el usuario quiere BUSCAR o VER algo en YouTube (no solo abrir la pagina principal).",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Que buscar en YouTube (ej: tutorial python, musica relax, receta pasta)"}
                },
                "required": ["consulta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generar_codigo",
            "description": "Genera codigo/texto COMPLETO usando el LLM y lo guarda en un archivo. Usar cuando el usuario pide CREAR algo: juegos, paginas web, scripts, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "descripcion": {"type": "string", "description": "Que crear (detallado)"},
                    "tipo": {"type": "string", "enum": ["html", "python", "javascript", "css", "json", "markdown", "texto"], "description": "Tipo de archivo"},
                    "ruta": {"type": "string", "description": "Ruta donde guardar (opcional, se genera automaticamente)"}
                },
                "required": ["descripcion", "tipo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leer_archivo",
            "description": "Lee el contenido de un archivo.",
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
            "description": "Crea o modifica un archivo con contenido especifico. Solo usar cuando ya tienes el contenido exacto.",
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
                    "ruta": {"type": "string", "description": "Ruta del directorio (por defecto el directorio de trabajo)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analizar_proyecto",
            "description": "Analiza la estructura completa de un proyecto. Lee archivos clave como package.json y README para entender la arquitectura real.",
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
            "description": "Instala dependencias de un proyecto. Detecta automaticamente npm/pip/poetry.",
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
                    "filtro": {"type": "string", "description": "Filtro por nombre de proceso (opcional)"}
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
            "description": "Analiza una imagen usando vision AI. Describe lo que ve, lee texto de la imagen, o responde preguntas sobre ella. Necesita un modelo de vision instalado (llava, llama3.2-vision, etc).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta de la imagen a analizar"},
                    "pregunta": {"type": "string", "description": "Pregunta sobre la imagen (por defecto: describela)"}
                },
                "required": ["ruta"]
            }
        }
    },
]
