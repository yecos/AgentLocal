# AgentLocal - Agente de IA Autonomo Local

Agente de IA que vive en tu computadora. Usa Ollama localmente (sin API keys, sin cloud) con arquitectura ReAct + Triple Memory + Metacognicion + Interfaz Web.

## Que hace

- Ejecuta comandos, lee y escribe archivos
- Abre aplicaciones de escritorio y paginas web
- Genera codigo completo (juegos, paginas web, scripts)
- Clona repos, instala dependencias, analiza proyectos
- Busca en archivos y en internet (DuckDuckGo)
- Aprende de correcciones y memoriza interacciones
- Muestra su proceso de pensamiento en tiempo real
- Interfaz web moderna con markdown, syntax highlighting, tool cards

## Arquitectura

```
Usuario pregunta
       |
  1. Memoria Triple (corto/largo plazo + trabajo)
     |- Si ya sabe -> Responde directo
     |- No -> Paso 2
  2. PENSAR (Modelo Qwen/Ollama)
  3. ACTUAR (41 herramientas disponibles)
  4. OBSERVAR + METACOGNICION
     |- Confianza baja? -> Buscar mas
     |- Bucle detectado? -> Cambiar estrategia
     |- Suficiente? -> Paso 5
  5. RESPONDER + APRENDER (guardar en memoria)
```

## Interfaces

| Interfaz | Comando | Puerto | Descripcion |
|---|---|---|---|
| **Web (Next.js)** | `npm run dev` | 3000 | Interfaz web completa con markdown, tools, voz |
| **Bridge API** | `python bridge_api.py` | 8000 | API REST 14 endpoints para la web |
| **Streamlit** | `streamlit run app.py` | 8501 | Interfaz standalone alternativa |

## Requisitos

- **Python 3.10+**
- **Node.js 18+** (para la interfaz web)
- **Ollama** corriendo localmente ([ollama.com](https://ollama.com))
- Un modelo descargado: `ollama pull qwen3:4b` (recomendado)

## Instalacion rapida

```bash
# 1. Clonar el repo
git clone https://github.com/yecos/AgentLocal.git
cd AgentLocal

# 2. Ejecutar script de instalacion (Linux/Mac)
chmod +x setup.sh
./setup.sh

# En Windows:
# setup.bat
```

El script `setup.sh` / `setup.bat` hace todo automaticamente:
- Verifica prerrequisitos (Python, Node.js, Ollama)
- Limpia duplicados y archivos basura
- Crea .env y directorios de trabajo
- Instala dependencias Python y Node.js
- Verifica que todo funcione

## Iniciar el agente

Necesitas **2 terminales**:

### Terminal 1 - Backend (Bridge API)
```bash
cd agente_v14
python bridge_api.py
```
Esto levanta FastAPI en puerto 8000 con 14 endpoints REST.

### Terminal 2 - Frontend (Next.js)
```bash
npm run dev
```
Esto levanta la interfaz web en http://localhost:3000

### Alternativa: Solo agente (sin interfaz web)
```bash
cd agente_v14
./start.sh         # Linux/Mac
start.bat          # Windows
```

## Estructura del proyecto

```
AgentLocal/
  .env                  # Variables de entorno (crear desde .env.example)
  .env.example          # Template de configuracion
  package.json          # Dependencias Node.js / Next.js
  setup.sh              # Script instalacion Linux/Mac
  setup.bat             # Script instalacion Windows
  Caddyfile             # Reverse proxy config (opcional)
  src/                  # Frontend Next.js
    app/
      page.tsx          # Interfaz web principal (React)
      layout.tsx        # Layout con providers
      globals.css       # Estilos globales
      api/              # 15 API routes Next.js
        chat/           # Chat con streaming SSE
        models/         # Modelos Ollama
        status/         # Estado del sistema
        tools/          # Lista de herramientas
        upload/         # Subir archivos
        ...
    components/ui/      # Componentes shadcn/ui
  agente_v14/           # Backend Python
    bridge_api.py       # API REST v16 (14 endpoints)
    app.py              # Entry point Streamlit
    config.py           # Configuracion centralizada
    llm.py              # Cliente Ollama (streaming, cache, dual model)
    agent/
      react.py          # Motor ReAct (piensa-actua-observa)
      schemas.py        # System prompt y tool schemas
      metacognition.py  # Sistema de metacognicion
      deep_thinking.py  # Pensamiento profundo progresivo
      middlewares.py    # Middlewares de procesamiento
      circuit_breaker.py # Circuit breaker para tools
      orchestrator.py   # Orquestador de tareas
      auto_evolve.py    # Auto-evolucion del agente
    tools/              # 41 herramientas
      sistema.py        # ejecutar_comando, procesos, matar_proceso
      archivos.py       # leer, escribir, listar, buscar en archivos
      apps.py           # abrir_aplicacion, abrir_url, buscar_youtube
      proyecto.py       # analizar_proyecto, clonar_repositorio
      codigo.py         # generar_codigo (usa LLM)
      web.py            # buscar_web (DuckDuckGo)
      ...
    memory/
      triple_memory.py  # Triple memoria (corto/largo plazo + trabajo)
      chroma_store.py   # ChromaDB vector store
      bm25.py           # Busqueda BM25
      hybrid.py         # Busqueda hibrida BM25+Vectorial
      reranker.py       # Re-ranking multi-senal
      learning.py       # Sistema de aprendizaje
      vectorstore.py    # Vector store con embeddings Ollama
    utils/
      security.py       # Validacion de comandos peligrosos
      helpers.py        # Funciones utilitarias
    tests/              # Tests unitarios y e2e
    start.bat / .sh     # Scripts de inicio
```

## Bridge API Endpoints (v16)

| Metodo | Endpoint | Descripcion |
|---|---|---|
| GET | `/api/status` | Estado del sistema y modelos |
| GET | `/api/models` | Modelos Ollama disponibles |
| POST | `/api/models/switch` | Cambiar modelo activo |
| GET | `/api/tools` | Lista de herramientas del agente |
| GET | `/api/memory` | Stats de memoria |
| POST | `/api/memory/save` | Guardar sesion |
| POST | `/api/memory/clear` | Limpiar sesion |
| GET | `/api/config` | Configuracion actual |
| POST | `/api/execute` | Ejecutar herramienta directamente |
| POST | `/api/chat` | Chat completo con streaming SSE |
| POST | `/api/chat/simple` | Chat directo con Ollama |
| POST | `/api/upload` | Subir archivos |
| GET | `/api/history` | Historial de conversacion |
| GET | `/api/health` | Health check |

## Herramientas disponibles (41)

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
| + 26 herramientas mas | browser_automation, database, docker, git, etc. |

## Modelos recomendados

| Modelo | Uso | RAM |
|---|---|---|
| `qwen3:4b` | General (recomendado) | ~3 GB |
| `qwen3-coder` | Codigo | ~4 GB |
| `qwen2.5:14b` | Calidad alta | ~8 GB |
| `llama3.1:8b` | Chat rapido | ~5 GB |

## Seguridad

- Validacion de comandos peligrosos (rm -rf, format, etc.)
- Proteccion contra path traversal
- Confirmacion requerida para comandos destructivos
- Solo acceso a archivos dentro de directorios permitidos

## Solucion de problemas

### El agente no responde
1. Verifica que Ollama este corriendo: `ollama list`
2. Verifica que tengas un modelo: `ollama pull qwen3:4b`
3. Verifica el Bridge API: `curl http://localhost:8000/api/health`

### La interfaz web no conecta
1. Verifica que bridge_api.py este corriendo en puerto 8000
2. Verifica que Next.js este corriendo en puerto 3000
3. Revisa la consola del navegador (F12) para errores

### Error de dependencias Python
```bash
cd agente_v14
pip install -r requirements.txt --force-reinstall
```

### Error de dependencias Node.js
```bash
rm -rf node_modules package-lock.json
npm install --legacy-peer-deps
```

## Licencia

MIT
