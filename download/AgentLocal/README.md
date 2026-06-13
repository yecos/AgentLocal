# 🧠 Agente Inteligente Local

Un agente de IA local que **piensa, busca, ejecuta y aprende** — con visibilidad completa de su proceso.

## ¿Qué hace diferente a este agente?

| Característica | Antes | Ahora |
|---|---|---|
| **Pensamiento** | Caja negra | Ves CADA paso de razonamiento |
| **Búsqueda** | No puede buscar | Busca en internet cuando no sabe |
| **Ejecución** | Solo habla | Ejecuta código Python, lee/escribe archivos |
| **Memoria** | Olvida todo | Aprende y recuerda entre sesiones |
| **Bucle** | Una respuesta | Intenta múltiples veces hasta resolver |

## Arquitectura

```
Usuario pregunta
       ↓
┌─────────────────────────────────┐
│  1. ¿Ya sé la respuesta?       │ ← Memoria SQLite
│     └─ Sí → Responde directo   │
│     └─ No  → Paso 2            │
│                                 │
│  2. 💭 PENSAR                   │ ← Modelo (Qwen/Ollama)
│     "Necesito buscar X..."     │
│                                 │
│  3. 🔧 ACTUAR                   │ ← Herramientas
│     buscar_internet("X")       │
│     ejecutar_python("código")  │
│     leer_archivo("/ruta")      │
│                                 │
│  4. 👁 OBSERVAR                 │
│     ¿Es suficiente?            │
│     └─ No  → Volver a paso 2  │
│     └─ Sí → Paso 5            │
│                                 │
│  5. ✅ RESPONDER + APRENDER    │ ← Guardar en memoria
└─────────────────────────────────┘
```

## Instalación

### 1. Requisitos previos

```bash
# Ollama (el motor de IA local)
curl -fsSL https://ollama.com/install.sh | sh

# Descargar un modelo (recomendado: qwen2.5:32b)
ollama pull qwen2.5:32b

# Alternativa más ligera (si tu PC no tiene mucha RAM):
ollama pull qwen2.5:7b
```

### 2. Instalar dependencias de Python

```bash
pip install -r requirements.txt
```

### 3. Ejecutar

```bash
# Opción A: Terminal con paneles visuales (recomendado)
python main.py

# Opción B: Interfaz web (panel pensamiento + terminal)
python web_ui.py
# Abre http://localhost:7860 en tu navegador
```

## Archivos del Proyecto

| Archivo | Función |
|---|---|
| `config.py` | Configuración centralizada (modelo, memoria, búsqueda) |
| `tools.py` | Herramientas: búsqueda web, ejecutar código, leer/escribir archivos |
| `memory.py` | Memoria persistente con SQLite (aprende entre sesiones) |
| `agent.py` | Cerebro del agente: bucle pensar-actuar-observar |
| `main.py` | Interfaz terminal con paneles de pensamiento + ejecución |
| `web_ui.py` | Interfaz web (Gradio) con panel de pensamiento y terminal |

## Configuración

Puedes cambiar la configuración con variables de entorno:

```bash
# Usar un modelo diferente
export MODEL_NAME="qwen2.5:7b"

# Más iteraciones para problemas complejos
export MAX_ITERATIONS="10"

# Desactivar memoria
export MEMORY_ENABLED="false"

# Usar SearXNG en vez de DuckDuckGo
export SEARCH_ENGINE="searxng"
export SEARXNG_URL="http://localhost:8080/search"
```

## Cómo se ve en pantalla

### Terminal (con Rich)
```
╭─────────────── 💭 PENSAMIENTO [14:32:01] ────────────────╮
│ Buscando en memoria conocimiento relevante...             │
╰───────────────────────────────────────────────────────────╯

╭─────────────── 💭 PENSAMIENTO [14:32:02] ────────────────╮
│ Iteración 1/5 — No sé esto, necesito buscar...           │
╰───────────────────────────────────────────────────────────╯

╭────────── 🔧 TERMINAL — EJECUTANDO [14:32:03] ──────────╮
│ $ buscar_internet({"query": "python async await"})       │
╰───────────────────────────────────────────────────────────╯

╭────────────── 👁 OBSERVACIÓN [14:32:05] ─────────────────╮
│ Resultado: 3 resultados encontrados                       │
│ Estado: ✅ EXITOSO                                        │
╰───────────────────────────────────────────────────────────╯

╭──────────── ✅ RESPUESTA FINAL [14:32:07] ───────────────╮
│ Async/await en Python permite escribir código asíncrono  │
│ que se lee como código síncrono...                        │
╰───────────────────────────────────────────────────────────╯
```

### Web UI
```
┌─────────────────────────┬─────────────────────────┐
│ 💭 PROCESO DE PENSAMIENTO│ 💻 TERMINAL DE EJECUCIÓN│
│                          │                         │
│ 💭 Pensamiento:          │ $ buscar_internet       │
│ No sé esto, necesito     │   ("python async")      │
│ buscar información...    │                         │
│                          │ → Resultado: EXITOSO    │
│ 🔧 Acción: buscar        │   3 resultados          │
│                          │                         │
│ 👁 Observación:          │ $ ejecutar_python       │
│ Encontré 3 resultados   │   ("import asyncio...") │
│                          │                         │
│ ✅ Respuesta Final:      │ → 4                     │
│ Aquí está la respuesta   │                         │
└─────────────────────────┴─────────────────────────┘
```

## Comandos especiales (en terminal)

| Comando | Función |
|---|---|
| `stats` | Muestra estadísticas de conocimiento |
| `historial` | Muestra pasos de la última pregunta |
| `salir` / `exit` | Cierra el agente |

## Próximos pasos (cómo hacer que crezca)

1. **RAG local**: Agregar búsqueda en documentos locales con embeddings
2. **Más herramientas**: Git, Docker, API calls, base de datos
3. **Multi-agente**: Varios agentes especializados colaborando
4. **Auto-mejora**: El agente modifica su propio prompt basado en lo que funciona
5. **SearXNG**: Instalar instancia local de búsqueda para resultados más completos

## Dependencias

- **Ollama** + modelo Qwen (o cualquier modelo compatible)
- **Python 3.8+**
- **rich** (interfaz terminal bonita)
- **gradio** (interfaz web, opcional)
- **requests** (búsqueda web)
