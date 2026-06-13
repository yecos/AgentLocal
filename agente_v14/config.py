"""
=============================================================
AGENTE LOCAL AUTONOMO v14 - Configuracion Centralizada
=============================================================
Todas las constantes y configuracion en un solo lugar.
Los demas modulos importan desde aqui.
=============================================================
"""

import os
import platform
import logging
from pathlib import Path

# ============================================================
# LOGGING
# ============================================================
# Crear directorio de log antes de configurar logging
_LOG_DIR = os.path.join(os.path.expanduser("~"), ".ia-local", "learning")
os.makedirs(_LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(
            os.path.join(_LOG_DIR, "agent.log"),
            encoding="utf-8"
        ),
    ]
)
logger = logging.getLogger("agente")

# ============================================================
# SISTEMA
# ============================================================
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# ============================================================
# DIRECTORIOS
# ============================================================
if IS_WINDOWS:
    REPOS_DIR = os.path.join(os.path.expanduser("~"), "Documents")
else:
    REPOS_DIR = os.path.join(os.path.expanduser("~"), "repos")

LEARN_DIR = os.path.join(os.path.expanduser("~"), ".ia-local", "learning")

os.makedirs(REPOS_DIR, exist_ok=True)
os.makedirs(LEARN_DIR, exist_ok=True)

# ============================================================
# MODELOS
# ============================================================
PREFERRED_MODELS = ["llama3.1:8b", "qwen2.5-coder:7b", "qwen2.5:14b", "qwen3:4b", "qwen3-coder", "qwen3:30b-a3b"]
CHAT_MODEL_PATTERNS = ["llama3.1:8b", "qwen2.5-coder:7b", "qwen3:4b", "mistral:7b"]  # Modelos rapidos para chat
CODE_MODEL_PATTERNS = ["qwen2.5:14b", "qwen2.5-coder:7b", "qwen3-coder", "qwen3:30b-a3b"]  # Modelos potentes para codigo
EMBED_MODEL_CANDIDATES = ["nomic-embed-text", "mxbai-embed-large", "all-minilm"]

# ============================================================
# LIMITES
# ============================================================
MAX_REACT_ITERATIONS = 6         # Max vueltas del bucle ReAct (reducido de 8 para velocidad)
MAX_CONVERSATION_MEMORY = 15     # Mensajes de contexto que recuerda (reducido de 20)
MAX_CONTEXT_CHARS = 2000         # Budget de chars para contexto enriquecido (reducido de 3000)
MAX_FILE_READ = 8000             # Max chars al leer un archivo
MAX_TOOL_OUTPUT = 3000           # Max chars en salida de herramienta
MAX_EMBED_CACHE = 200            # Maximo entradas en cache de embeddings
MAX_VECTORS_IN_MEMORY = 500      # Maximo vectores cargados en RAM
CONNECTION_CACHE_DAYS = 7        # Dias que se guarda la conexion Ollama cacheada

# ============================================================
# RENDIMIENTO
# ============================================================
SKIP_EMBED_ON_INTERACTION = True  # Saltar embedding al guardar interacciones (mas rapido)
USE_STREAMING = True              # Usar streaming por defecto
GPU_CHECK_ON_START = True         # Verificar GPU al iniciar el agente

# ============================================================
# BUSQUEDA HIBRIDA (v14.5)
# ============================================================
USE_HYBRID_SEARCH = True          # Usar HybridVectorStore (BM25 + Vectorial + RRF)
USE_RERANKER = True               # Usar MultiSignalReranker en recall()
BM25_K1 = 1.5                     # Parametro k1 de BM25 (saturacion TF)
BM25_B = 0.75                     # Parametro b de BM25 (normalizacion longitud)
RRF_K = 60                        # Constante de suavizado Reciprocal Rank Fusion
HYBRID_MIN_SIMILARITY = 0.25      # Umbral minimo para busqueda hibrida (menor que solo vectorial)
RERANK_OVER_RETRIEVE = 2          # Over-retrieve factor para re-ranking (limit * 2)

# ============================================================
# BUSQUEDA WEB (v14.5)
# ============================================================
WEB_SEARCH_MAX_RETRIES = 3        # Max reintentos para busqueda web
WEB_SEARCH_CACHE_TTL = 300        # TTL del cache en segundos (5 min)
WEB_SEARCH_CACHE_MAX = 50         # Max entradas en cache de busqueda web
WEB_SEARCH_FALLBACK_WIKI = True   # Fallback a Wikipedia si DDG falla

# ============================================================
# BUSQUEDA EN ARCHIVOS (v14.5)
# ============================================================
USE_RIPGREP = True                # Usar ripgrep como motor primario (10-100x mas rapido)
FILE_SEARCH_MAX_DEPTH = 10        # Profundidad maxima de busqueda recursiva
FILE_SEARCH_MAX_RESULTS = 50      # Max resultados de busqueda en archivos

# ============================================================
# PENSAMIENTO PROFUNDO (v14.7)
# ============================================================
DEEP_THINKING_MODE = "full"        # "off", "native", "cot", "reflection", "full"
                                   # off: deshabilitado
                                   # native: solo usar <think> nativo del modelo (qwen3, deepseek-r1)
                                   # cot: solo Chain-of-Thought antes de actuar
                                   # reflection: solo post-reflexion de la respuesta
                                   # full: cot + native + reflection (recomendado)
DEEP_THINKING_MIN_COMPLEXITY = 0.3 # Umbral minimo de complejidad para activar (0-1)
DEEP_THINKING_MAX_THINKING_TOKENS = 1024  # Max tokens (palabras) para razonamiento interno
DEEP_THINKING_REFLECT_ON_ERRORS = True    # Siempre reflexionar si hubo errores
DEEP_THINKING_SHOW_THOUGHTS = True        # Mostrar pensamientos al usuario en UI

# Niveles de profundidad progresivos (v14.7)
DEEP_THINKING_DEPTH_QUICK_THRESHOLD = 0.3   # >= 0.3: analisis rapido
DEEP_THINKING_DEPTH_FULL_THRESHOLD = 0.5    # >= 0.5: CoT completo + plan
DEEP_THINKING_DEPTH_DEEP_THRESHOLD = 0.75   # >= 0.75: razonamiento multi-vuelta
DEEP_THINKING_MAX_CRITIQUE_ROUNDS = 2       # Max rondas de auto-critica
DEEP_THINKING_LLM_COMPLEXITY = True         # Usar LLM para evaluar complejidad en casos ambiguos
DEEP_THINKING_PERSIST_THOUGHTS = True       # Guardar pensamientos en archivo para futuro
DEEP_THINKING_MAX_PERSISTED = 100           # Max pensamientos guardados

# ============================================================
# TIMEOUTS
# ============================================================
DEFAULT_TIMEOUT = 90             # Segundos para comandos normales (reducido)
LONG_TIMEOUT = 300               # Segundos para install/build/docker
LLM_TIMEOUT_SMALL = 90           # Timeout para modelos <=8b (reducido de 120)
LLM_TIMEOUT_LARGE = 150          # Timeout para modelos >=14b (reducido de 180)
EMBED_TIMEOUT = 10               # Timeout para embeddings (reducido de 15)
WEB_TIMEOUT = 10                 # Timeout para busquedas web

# ============================================================
# ARCHIVOS DE DATOS
# ============================================================
CORRECTIONS_FILE = os.path.join(LEARN_DIR, "corrections.json")
FEEDBACK_FILE = os.path.join(LEARN_DIR, "feedback.json")
PATTERNS_FILE = os.path.join(LEARN_DIR, "patterns.json")
KNOWLEDGE_FILE = os.path.join(LEARN_DIR, "knowledge.json")
CONNECTION_CACHE_FILE = os.path.join(LEARN_DIR, "ollama_connection.json")
USER_PROFILE_FILE = os.path.join(LEARN_DIR, "user_profile.json")

# ============================================================
# SITIOS WEB CONOCIDOS
# ============================================================
SITIOS_CONOCIDOS = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "reddit": "https://www.reddit.com",
    "whatsapp web": "https://web.whatsapp.com",
    "whatsappweb": "https://web.whatsapp.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "twitch": "https://www.twitch.tv",
    "amazon": "https://www.amazon.com",
    "wikipedia": "https://es.wikipedia.org",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "translate": "https://translate.google.com",
    "google translate": "https://translate.google.com",
    "chatgpt": "https://chat.openai.com",
    "copilot": "https://copilot.microsoft.com",
    "outlook": "https://outlook.live.com",
    "notion": "https://www.notion.so",
    "figma": "https://www.figma.com",
    "canva": "https://www.canva.com",
    "trello": "https://trello.com",
}

# ============================================================
# ALIAS DE APLICACIONES
# ============================================================
APP_ALIASES = {
    "chrome": "google chrome",
    "vscode": "visual studio code",
    "autocad": "autocad",
    "revit": "revit",
    "whatsapp": "whatsapp",
    "telegram": "telegram desktop",
    "word": "word",
    "excel": "excel",
    "powerpoint": "powerpoint",
    "photoshop": "adobe photoshop",
    "illustrator": "adobe illustrator",
    "figma": "figma",
    "blender": "blender",
    "sketchup": "sketchup",
    "notepad": "notepad",
    "bloc de notas": "notepad",
}

# ============================================================
# PROMPTS DE GENERACION POR TIPO
# ============================================================
CODE_GEN_PROMPTS = {
    "html": (
        "Eres un desarrollador web EXPERTO. Genera una pagina web HTML COMPLETA y FUNCIONAL.\n"
        "REGLAS:\n"
        "- TODO debe estar en un SOLO archivo HTML (HTML + CSS inline + JavaScript inline)\n"
        "- CSS moderno con gradientes, sombras, animaciones\n"
        "- JavaScript funcional, no pseudocodigo\n"
        "- Si es un juego: HTML5 Canvas, game loop, controles, colisiones, puntuacion\n"
        "- Si es una pagina: responsive, secciones completas\n"
        "- NO uses placeholders, TODO debe funcionar\n"
        "- Responde SOLO con el codigo HTML, sin explicaciones, sin markdown"
    ),
    "python": (
        "Eres un desarrollador Python EXPERTO. Genera un script COMPLETO y FUNCIONAL.\n"
        "- Codigo ejecutable directamente\n"
        "- Incluye imports, funciones, manejo de errores\n"
        "- Responde SOLO con el codigo Python, sin explicaciones"
    ),
    "javascript": (
        "Eres un desarrollador JavaScript EXPERTO. Genera codigo COMPLETO.\n"
        "- Codigo funcional y ejecutable\n"
        "- Responde SOLO con el codigo, sin explicaciones"
    ),
    "css": "Eres un disenador CSS EXPERTO. Responde SOLO con el codigo CSS.",
    "json": "Genera un JSON valido y bien estructurado. Responde SOLO con el JSON.",
    "markdown": "Genera un documento Markdown bien formateado. Responde SOLO con Markdown.",
}

# ============================================================
# EXTENSION DE ARCHIVO POR TIPO
# ============================================================
CODE_EXT_MAP = {
    "html": ".html",
    "python": ".py",
    "javascript": ".js",
    "css": ".css",
    "json": ".json",
    "markdown": ".md",
    "texto": ".txt",
}
