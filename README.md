# Agente Local Autonomo v15

Agente de IA autonomo que vive en tu computadora. Usa Ollama localmente (sin API keys, sin cloud) con arquitectura modular ReAct + Triple Memory + Visibilidad de Pensamiento.

## Que hace

- Ejecuta comandos, lee y escribe archivos
- Abre aplicaciones de escritorio y paginas web
- Genera codigo completo (juegos, paginas web, scripts)
- Clona repos, instala dependencias, analiza proyectos
- Busca en archivos y en internet
- Aprende de correcciones y memoriza interacciones
- **Muestra su proceso de pensamiento en tiempo real** (v15)
- **Terminal de ejecucion visible** — ves todo lo que ejecuta (v15)

## Novedades v15

### 💭 Panel de Proceso de Pensamiento
Ahora puedes ver COMO piensa el agente paso a paso:
- Recibiendo pregunta
- Buscando en memoria
- Decidiendo usar herramientas
- Observando resultados
- Generando respuesta final
- Nivel de confianza en cada paso

### 💻 Terminal de Ejecucion
Panel tipo terminal que muestra:
- Que herramienta se ejecuta y con que parametros
- Resultados de cada ejecucion
- Errores en rojo, exitos en verde

### Arquitectura completa

```
Usuario pregunta
       ↓
  1. ¿Ya se la respuesta? ← Memoria Triple (corto/largo plazo + trabajo)
     └─ Si → Responde directo
     └─ No → Paso 2
  2. 💭 PENSAR ← Modelo (Qwen/Ollama)
     "Necesito buscar X..."
  3. 🔧 ACTUAR ← Herramientas (19 herramientas)
     buscar_web("X")
     ejecutar_comando("...")
     leer_archivo("/ruta")
  4. 👁 OBSERVAR + METACOGNICION
     ¿Es suficiente? ¿Confianza baja? → Buscar mas
     ¿Bucle detectado? → Cambiar estrategia
     └─ No → Volver a paso 2
     └─ Si → Paso 5
  5. ✅ RESPONDER + APRENDER ← Guardar en memoria
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
  start.bat            # Script de inicio Windows
  start.sh             # Script de inicio Linux/Mac
  requirements.txt     # Dependencias Python
  agent/
    react.py           # Motor ReAct (piensa-actua-observa)
    schemas.py         # System prompt y tool schemas
  tools/
    sistema.py         # ejecutar_comando, procesos_activos, matar_proceso
    archivos.py        # leer, escribir, listar, buscar en archivos
    apps.py            # abrir_aplicacion, abrir_url, buscar_youtube
    proyecto.py        # analizar_proyecto, clonar_repositorio, instalar_dependencias
    codigo.py          # generar_codigo (usa LLM)
    web.py             # buscar_web (DuckDuckGo)
    schemas.py         # Esquemas de function calling
  memory/
    triple_memory.py   # Triple memoria (corto/largo plazo + trabajo)
    vectorstore.py     # Vector store con embeddings Ollama
    learning.py        # Sistema de aprendizaje y correcciones
  utils/
    security.py        # Validacion de comandos peligrosos, path traversal
    helpers.py         # Funciones utilitarias compartidas
```

## Herramientas disponibles

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

## Opciones del script de inicio

```
start.bat           # Inicio completo con verificacion
start.bat --skip    # Inicio rapido (sin verificar)
start.bat --check   # Solo verificar, no iniciar
start.bat --install # Instalar/actualizar dependencias
```

## Seguridad

- Validacion de comandos peligrosos (rm -rf, format, etc.)
- Proteccion contra path traversal
- Confirmacion requerida para comandos destructivos
- Solo acceso a archivos dentro de directorios permitidos

## Modelos recomendados

| Modelo | Uso | RAM |
|---|---|---|
| `qwen3:4b` | General (recomendado) | ~3 GB |
| `qwen3-coder` | Codigo | ~4 GB |
| `qwen2.5:14b` | Calidad alta | ~8 GB |
| `llama3.1:8b` | Chat rapido | ~5 GB |

## Licencia

MIT
