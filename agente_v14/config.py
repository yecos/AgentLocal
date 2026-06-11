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
PREFERRED_MODELS = ["qwen3:4b", "qwen3-coder", "qwen3:30b-a3b", "qwen2.5:14b", "llama3.1:8b"]
CHAT_MODEL_PATTERNS = ["llama3.1:8b", "qwen3:4b", "mistral:7b"]  # Modelos rapidos para chat
CODE_MODEL_PATTERNS = ["qwen2.5:14b", "qwen3-coder", "qwen3:30b-a3b"]  # Modelos potentes para codigo
EMBED_MODEL_CANDIDATES = ["nomic-embed-text", "mxbai-embed-large", "all-minilm"]

# ============================================================
# LIMITES
# ============================================================
MAX_REACT_ITERATIONS = 8         # Max vueltas del bucle ReAct
MAX_CONVERSATION_MEMORY = 20     # Mensajes de contexto que recuerda
MAX_CONTEXT_CHARS = 3000         # Budget de chars para contexto enriquecido
MAX_FILE_READ = 8000             # Max chars al leer un archivo
MAX_TOOL_OUTPUT = 3000           # Max chars en salida de herramienta
MAX_EMBED_CACHE = 200            # Maximo entradas en cache de embeddings
MAX_VECTORS_IN_MEMORY = 500      # Maximo vectores cargados en RAM
CONNECTION_CACHE_DAYS = 7        # Dias que se guarda la conexion Ollama cacheada
MEMORY_DECAY_HALF_LIFE = 30      # Dias para decaimiento de recuerdos
MEMORY_CLEANUP_INTERVAL = 50     # Ops entre auto-cleanup
MEMORY_MAX_ENTRIES = 1000        # Maximo entradas en vector store
DEDUP_SIMILARITY_THRESHOLD = 0.95 # Umbral para deduplicacion semantica
SUMMARY_MIN_MESSAGES = 10        # Minimo mensajes para generar resumen LLM

# ============================================================
# TIMEOUTS
# ============================================================
DEFAULT_TIMEOUT = 120            # Segundos para comandos normales
LONG_TIMEOUT = 300               # Segundos para install/build/docker
LLM_TIMEOUT_SMALL = 120          # Timeout para modelos <=8b
LLM_TIMEOUT_LARGE = 180          # Timeout para modelos >=14b
LLM_SUMMARY_TIMEOUT = 30         # Timeout para resumen LLM
EMBED_TIMEOUT = 15               # Timeout para embeddings
WEB_TIMEOUT = 10                 # Timeout para busquedas web

# ============================================================
# ARCHIVOS DE DATOS
# ============================================================
CORRECTIONS_FILE = os.path.join(LEARN_DIR, "corrections.json")
FEEDBACK_FILE = os.path.join(LEARN_DIR, "feedback.json")
PATTERNS_FILE = os.path.join(LEARN_DIR, "patterns.json")
KNOWLEDGE_FILE = os.path.join(LEARN_DIR, "knowledge.json")
CONNECTION_CACHE_FILE = os.path.join(LEARN_DIR, "ollama_connection.json")

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
