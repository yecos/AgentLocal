# Agente Local Autonomo v16

Agente de IA autonomo que vive en tu computadora. Usa Ollama localmente (sin API keys, sin cloud) con arquitectura modular ReAct + Triple Memory + Planificacion + Ejecucion + Edicion Incremental.

## Que hace

- **Planifica** tareas complejas y las descompone en subtareas
- **Ejecuta codigo** y tests para verificar que funciona
- **Construye apps** completas paso a paso
- **Edita archivos** de forma incremental (no reescribe todo)
- **Opera Git** de forma estructurada (status, commit, push, etc.)
- **Consulta bases de datos** (SQLite, PostgreSQL, MySQL)
- **Diagnostica errores** y se autocorrige
- Ejecuta comandos, lee y escribe archivos
- Abre aplicaciones de escritorio y paginas web
- Genera codigo completo (juegos, paginas web, scripts)
- Clona repos, instala dependencias, analiza proyectos
- Busca en archivos y en internet
- Aprende de correcciones y memoriza interacciones
- **30+ Skills** conectados (imagenes, documentos, voz, etc.)
- Muestra su proceso de pensamiento en tiempo real

## Novedades v16

### 🧠 Planificador de Tareas
Descompone tareas complejas en subtareas con dependencias:
- Templates para: web_app, script, automation, analysis, project_setup
- Progreso tracking y avance automatico
- Re-planificacion cuando algo falla

### ⚡ Ejecucion y Testing de Codigo
- Ejecuta Python, JavaScript, TypeScript, Bash en sandbox
- Captura stdout/stderr con timeout
- Auto-detecta y ejecuta tests (pytest, jest, vitest)
- Loop: generar → ejecutar → diagnosticar → corregir → verificar

### ✏️ Edicion Incremental de Archivos
- `buscar_reemplazar`: search-and-replace sin reescribir todo
- `editar_lineas`: reemplazar rango de lineas especificas
- `insertar_en_linea`: insertar antes/despues de una linea
- Preview de diffs y backup automatico

### 🔧 Git como Herramienta de Primera Clase
- `git_operacion`: status, diff, add, commit, branch, log, push, pull, stash
- Parseo estructurado de salida
- Auto-commit con mensajes generados

### 💾 Base de Datos como Herramienta
- SQLite, PostgreSQL, MySQL
- Conectar, consultar, listar tablas, describir estructura
- Crear tablas, exportar datos (JSON/CSV)

### 🔗 Skill Loader (30+ Skills Conectados)
- web-search, web-reader, image-generation, image-search
- LLM, VLM, TTS, ASR, image-edit, video-understand
- docx, pdf, pptx, xlsx, charts
- agent-browser (navegacion headless)

### 🛡️ Error Recovery Chain
- Diagnostico automatico de errores
- Clasificacion (timeout, permisos, dependencia, sintaxis, etc.)
- Correcciones automaticas cuando es posible
- Historial de errores para aprendizaje

### Arquitectura completa

```
Usuario pregunta
       ↓
  1. ¿Tarea compleja? → PLANIFICAR (planificar_tarea)
     └─ Si → Crear plan con subtareas → Ejecutar paso a paso
     └─ No → Paso 2
  2. ¿Ya se la respuesta? ← Memoria Triple (corto/largo plazo + trabajo)
     └─ Si → Responde directo
     └─ No → Paso 3
  3. 💭 PENSAR ← Modelo (Qwen/Ollama)
     "Necesito buscar X..."
  4. 🔧 ACTUAR ← Herramientas (30+ herramientas)
     buscar_web("X") / ejecutar_codigo("...") / buscar_reemplazar("...")
  5. 👁 OBSERVAR + METACOGNICION
     ¿Funciono? ¿Error? → diagnosticar_error → corregir → reintentar
     ¿Es suficiente? → Si, responder
     └─ No → Volver a paso 3
  6. ✅ RESPONDER + APRENDER ← Guardar en memoria
```

## Interfaces

| Interfaz | Comando | Descripcion |
|---|---|---|
| **Web (Next.js)** | `npm run dev` | Interfaz web con paneles de pensamiento + terminal |
| **Bridge API** | `python bridge_api.py` | API REST para conectar el agente con la web |
| **Streamlit** | `streamlit run app.py` | Interfaz standalone alternativa |

## Requisitos

- **Python 3.8+**
- **Node.js 18+** (para la interfaz web)
- **Ollama** corriendo localmente ([ollama.com](https://ollama.com))
- Un modelo descargado: `ollama pull qwen3:4b` (recomendado)

## Instalacion rapida

```bash
# 1. Clonar
git clone https://github.com/yecos/AgentLocal.git
cd AgentLocal

# 2. Instalar dependencias Python
cd agente_v14
pip install -r requirements.txt

# 3. Iniciar Bridge API (conecta agente con web)
python bridge_api.py

# 4. En otra terminal, iniciar interfaz web
cd ..
npm install
npm run dev

# 5. Abrir http://localhost:3000
```

### Inicio rapido (solo agente, sin web)

```bash
cd agente_v14
start.bat          # Windows
./start.sh         # Linux/Mac
```

## Estructura del proyecto

```
agente_v14/
  app.py               # Entry point Streamlit
  config.py            # Configuracion centralizada
  llm.py               # Cliente Ollama (singleton, cache, dual model)
  bridge_api.py        # FastAPI REST bridge para Next.js
  agent/
    react.py           # Motor ReAct (piensa-actua-observa)
    schemas.py         # System prompt y tool schemas (v16)
    metacognition.py   # Auto-evaluacion + loop detection
  tools/
    sistema.py         # ejecutar_comando, procesos_activos, matar_proceso
    archivos.py        # leer, escribir, listar, buscar en archivos
    apps.py            # abrir_aplicacion, abrir_url, buscar_youtube
    proyecto.py        # analizar_proyecto, clonar_repositorio, instalar_dependencias
    codigo.py          # generar_codigo (usa LLM)
    web.py             # buscar_web (DuckDuckGo), leer_web
    registry.py        # @tool decorator para registro automatico
    skill_loader.py    # 🆕 Carga skills como herramientas (30+)
    task_planner.py    # 🆕 Planificador de tareas jerarquico
    code_executor.py   # 🆕 Sandbox de ejecucion + testing
    file_editor.py     # 🆕 Edicion incremental (buscar_reemplazar, editar_lineas)
    git_tool.py        # 🆕 Git como herramienta de primera clase
    database_tool.py   # 🆕 Operaciones de base de datos
    error_recovery.py  # 🆕 Diagnostico y correccion de errores
  memory/
    triple_memory.py   # Triple memoria (corto/largo plazo + trabajo)
    vectorstore.py     # Vector store con embeddings Ollama
    learning.py        # Sistema de aprendizaje y correcciones
  utils/
    security.py        # Validacion de comandos peligrosos, path traversal
    helpers.py         # Funciones utilitarias compartidas
    metrics.py         # Metricas de rendimiento
skills/                # 🆕 30+ skills conectados via Skill Loader
  web-search/          # Busqueda web via API
  image-generation/    # Generacion de imagenes con IA
  docx/                # Creacion de documentos Word
  pdf/                 # Creacion de PDFs
  pptx/                # Presentaciones PowerPoint
  xlsx/                # Hojas de calculo Excel
  charts/              # Graficos y diagramas
  agent-browser/       # Navegador headless
  TTS/                 # Texto a voz
  ASR/                 # Voz a texto
  VLM/                 # Vision AI
  ... y mas
```

## Herramientas disponibles (30+)

### Basicas (v14)
| Herramienta | Descripcion |
|---|---|
| `ejecutar_comando` | Ejecuta comandos en la terminal |
| `abrir_aplicacion` | Abre apps de escritorio por nombre |
| `abrir_url` | Abre paginas web en el navegador |
| `buscar_youtube` | Busca videos en YouTube |
| `generar_codigo` | Genera codigo con el LLM y lo guarda |
| `leer_archivo` | Lee contenido de archivos |
| `escribir_archivo` | Crea o modifica archivos |
| `listar_archivos` | Lista contenido de directorios |
| `analizar_proyecto` | Analisis profundo de proyectos |
| `clonar_repositorio` | Clona repos de GitHub |
| `instalar_dependencias` | Instala deps (detecta npm/pip/poetry) |
| `buscar_en_archivos` | Busca texto en archivos (grep) |
| `procesos_activos` | Lista procesos corriendo |
| `matar_proceso` | Termina un proceso por PID o nombre |
| `buscar_web` | Busca en internet (DuckDuckGo) |
| `leer_web` | Lee contenido de paginas web |
| `buscar_web_profundo` | Busqueda profunda con lectura auto |

### Nuevas v16 - Planificacion y Ejecucion
| Herramienta | Descripcion |
|---|---|
| `planificar_tarea` | Descompone tareas complejas en subtareas |
| `ejecutar_codigo` | Ejecuta Python/JS/TS/Bash en sandbox |
| `ejecutar_archivo` | Ejecuta un archivo existente |
| `ejecutar_tests` | Ejecuta tests (pytest, jest, vitest) |

### Nuevas v16 - Edicion
| Herramienta | Descripcion |
|---|---|
| `buscar_reemplazar` | Search-and-replace sin reescribir todo |
| `editar_lineas` | Reemplazar rango de lineas |
| `insertar_en_linea` | Insertar antes/despues de una linea |

### Nuevas v16 - Git y DB
| Herramienta | Descripcion |
|---|---|
| `git_operacion` | Git estructurado (status, commit, push, etc.) |
| `base_de_datos` | SQLite/Postgres/MySQL operaciones |

### Nuevas v16 - Diagnostico
| Herramienta | Descripcion |
|---|---|
| `diagnosticar_error` | Diagnostica errores y sugiere correcciones |

### Nuevas v16 - Skills (via z-ai-web-dev-sdk)
| Herramienta | Descripcion |
|---|---|
| `buscar_web_api` | Busqueda web via API |
| `generar_imagen` | Genera imagenes con IA |
| `buscar_imagen` | Busca imagenes en internet |
| `consultar_llm` | Consulta LLM externo |
| `analizar_imagen_api` | Vision AI |
| `texto_a_voz` | TTS |
| `voz_a_texto` | STT |
| `crear_documento` | Word (.docx) |
| `crear_pdf` | PDF |
| `crear_presentacion` | PowerPoint (.pptx) |
| `crear_hoja_calculo` | Excel (.xlsx) |
| `crear_grafico` | Graficos y diagramas |
| `navegar_web` | Navegador headless |

## Seguridad

- Validacion de comandos peligrosos (rm -rf, format, etc.)
- Proteccion contra path traversal
- Confirmacion requerida para comandos destructivos
- Solo acceso a archivos dentro de directorios permitidos
- Sandboxed code execution con timeout
- Backup automatico antes de editar archivos

## Modelos recomendados

| Modelo | Uso | RAM |
|---|---|---|
| `qwen3:4b` | General (recomendado) | ~3 GB |
| `qwen3-coder` | Codigo | ~4 GB |
| `qwen2.5:14b` | Calidad alta | ~8 GB |
| `llama3.1:8b` | Chat rapido | ~5 GB |

## Licencia

MIT
