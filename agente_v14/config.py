"""
=============================================================
AGENTE LOCAL AUTONOMO v14 - Configuracion Centralizada
=============================================================
Todas las constantes y configuracion en un solo lugar.
Los demas modulos importan desde aqui.

v14.8: validate_config(), env var overrides, get_config_summary()
=============================================================
"""

import os
import platform
import logging

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
    _DEFAULT_REPOS_DIR = os.path.join(os.path.expanduser("~"), "Documents")
else:
    _DEFAULT_REPOS_DIR = os.path.join(os.path.expanduser("~"), "repos")

_DEFAULT_LEARN_DIR = os.path.join(os.path.expanduser("~"), ".ia-local", "learning")

# Environment variable overrides for directories
REPOS_DIR = os.environ.get("AGENT_REPOS_DIR", _DEFAULT_REPOS_DIR)
LEARN_DIR = os.environ.get("AGENT_LEARN_DIR", _DEFAULT_LEARN_DIR)

os.makedirs(REPOS_DIR, exist_ok=True)
os.makedirs(LEARN_DIR, exist_ok=True)

# ============================================================
# MODELOS
# ============================================================
PREFERRED_MODELS = ["llama3.1:8b", "qwen2.5-coder:7b", "qwen2.5:14b", "qwen3:4b", "qwen3-coder", "qwen3:30b-a3b"]
CHAT_MODEL_PATTERNS = ["llama3.1:8b", "qwen2.5-coder:7b", "qwen3:4b", "mistral:7b"]  # Modelos rapidos para chat
CODE_MODEL_PATTERNS = ["qwen2.5:14b", "qwen2.5-coder:7b", "qwen3-coder", "qwen3:30b-a3b"]  # Modelos potentes para codigo
EMBED_MODEL_CANDIDATES = ["nomic-embed-text", "mxbai-embed-large", "all-minilm"]

# Environment variable override for model
AGENT_MODEL = os.environ.get("AGENT_MODEL", "")  # Empty = auto-detect

# ============================================================
# LIMITES
# ============================================================
MAX_REACT_ITERATIONS = 6         # Max vueltas del bucle ReAct (reducido de 8 para velocidad)
ADAPTIVE_ITERATIONS = True       # Iteraciones adaptativas segun complejidad (M2.2)
MAX_CONVERSATION_MEMORY = 15     # Mensajes de contexto que recuerda (reducido de 20)
MAX_CONTEXT_CHARS = 2000         # Budget de chars para contexto enriquecido (reducido de 3000)
MAX_FILE_READ = 8000             # Max chars al leer un archivo
MAX_TOOL_OUTPUT = 3000           # Max chars en salida de herramienta
MAX_EMBED_CACHE = 200            # Maximo entradas en cache de embeddings
MAX_VECTORS_IN_MEMORY = 500      # Maximo vectores cargados en RAM
CONNECTION_CACHE_DAYS = 7        # Dias que se guarda la conexion Ollama cacheada

# ============================================================
# LLM PARAMETERS (with env var overrides)
# ============================================================
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 4096
CONTEXT_WINDOW_TOKENS = 8192     # Approximate context window for token management
SUMMARIZATION_THRESHOLD = 0.8   # Fraction of context window before summarizing

# Environment variable overrides for LLM parameters
AGENT_TEMPERATURE = float(os.environ.get("AGENT_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
AGENT_MAX_TOKENS = int(os.environ.get("AGENT_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))

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
# SUB-AGENTES (v15)
# ============================================================
TOOL_CALLING_MODEL_CACHE = {}       # Cache model->bool para tool calling (M8.2)

SUBAGENT_MAX_PARALLEL = 4          # Max sub-agentes ejecutandose en paralelo
SUBAGENT_DEFAULT_TIMEOUT = 60      # Timeout por defecto para sub-agentes (segundos)
SUBAGENT_MAX_TASKS = 8             # Max tareas en una ejecucion paralela
ORCHESTRATOR_MAX_SUBAGENTS = 4     # Max sub-agentes que el orquestador puede crear
ORCHESTRATOR_AUTO_STRATEGY = True  # El orquestador elige estrategia automaticamente

# ============================================================
# MULTIMEDIA (v15)
# ============================================================
TTS_DEFAULT_VOICE = "es"           # Voz por defecto para TTS
TTS_DEFAULT_SPEED = 1.0            # Velocidad por defecto
TTS_MAX_TEXT_LENGTH = 5000         # Max caracteres para TTS
IMAGE_DEFAULT_SIZE = "512x512"     # Tamano por defecto para generacion de imagenes
IMAGE_TIMEOUT = 120                # Timeout para generacion de imagenes
VIDEO_FRAME_INTERVAL = 5           # Intervalo en segundos para extraccion de frames

# ============================================================
# TIMEOUTS
# ============================================================
DEFAULT_TIMEOUT = 90             # Segundos para comandos normales (reducido)
LONG_TIMEOUT = 300               # Segundos para install/build/docker
LLM_TIMEOUT_SMALL = 90           # Timeout para modelos <=8b (reducido de 120)
LLM_TIMEOUT_LARGE = 150          # Timeout para modelos >=14b (reducido de 180)
EMBED_TIMEOUT = 10               # Timeout para embeddings (reducido de 15)
WEB_TIMEOUT = 10                 # Timeout para busquedas web
TOOL_EXECUTION_TIMEOUT = 45       # M2.4: Timeout global para ejecucion paralela de tools (segundos)

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


# ============================================================
# CONFIGURATION VALIDATION
# ============================================================

def validate_config() -> dict:
    """
    Validate all configuration settings and return a report.
    
    Checks:
    - REPOS_DIR exists and is writable (creates if not)
    - LEARN_DIR exists and is writable
    - Numeric constants are in reasonable ranges
    
    Returns:
        dict of {setting_name: "ok" | "error: reason"} for each check
    """
    results = {}
    
    # --- Directory checks ---
    for dir_name, dir_path in [("REPOS_DIR", REPOS_DIR), ("LEARN_DIR", LEARN_DIR)]:
        try:
            os.makedirs(dir_path, exist_ok=True)
            # Test write permission
            test_file = os.path.join(dir_path, ".agent_write_test")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            results[dir_name] = "ok"
        except OSError as e:
            results[dir_name] = f"error: {e}"
    
    # --- Numeric range checks ---
    numeric_checks = [
        ("AGENT_TEMPERATURE", AGENT_TEMPERATURE, 0.0, 2.0),
        ("AGENT_MAX_TOKENS", AGENT_MAX_TOKENS, 1, None),
        ("MAX_REACT_ITERATIONS", MAX_REACT_ITERATIONS, 1, 50),
        ("MAX_CONVERSATION_MEMORY", MAX_CONVERSATION_MEMORY, 1, 100),
        ("MAX_CONTEXT_CHARS", MAX_CONTEXT_CHARS, 100, None),
        ("MAX_FILE_READ", MAX_FILE_READ, 100, None),
        ("MAX_TOOL_OUTPUT", MAX_TOOL_OUTPUT, 100, None),
        ("DEFAULT_TIMEOUT", DEFAULT_TIMEOUT, 1, 3600),
        ("LONG_TIMEOUT", LONG_TIMEOUT, 1, 3600),
        ("LLM_TIMEOUT_SMALL", LLM_TIMEOUT_SMALL, 1, 600),
        ("LLM_TIMEOUT_LARGE", LLM_TIMEOUT_LARGE, 1, 600),
        ("EMBED_TIMEOUT", EMBED_TIMEOUT, 1, 120),
        ("WEB_TIMEOUT", WEB_TIMEOUT, 1, 120),
        ("TOOL_EXECUTION_TIMEOUT", TOOL_EXECUTION_TIMEOUT, 1, 300),
        ("CONTEXT_WINDOW_TOKENS", CONTEXT_WINDOW_TOKENS, 100, None),
        ("SUMMARIZATION_THRESHOLD", SUMMARIZATION_THRESHOLD, 0.1, 1.0),
        ("SUBAGENT_MAX_PARALLEL", SUBAGENT_MAX_PARALLEL, 1, 16),
        ("SUBAGENT_DEFAULT_TIMEOUT", SUBAGENT_DEFAULT_TIMEOUT, 1, 600),
    ]
    
    for name, value, min_val, max_val in numeric_checks:
        if min_val is not None and value < min_val:
            results[name] = f"error: {value} is below minimum {min_val}"
        elif max_val is not None and value > max_val:
            results[name] = f"error: {value} is above maximum {max_val}"
        else:
            results[name] = "ok"
    
    # --- Model override check ---
    if AGENT_MODEL:
        results["AGENT_MODEL"] = f"ok (override: {AGENT_MODEL})"
    else:
        results["AGENT_MODEL"] = "ok (auto-detect)"
    
    return results


def get_config_summary() -> dict:
    """
    Return a dict of all non-sensitive config values.
    Used by /api/config endpoint to expose current configuration.
    
    Returns:
        dict of config_name -> config_value (excludes sensitive data)
    """
    return {
        # System
        "IS_WINDOWS": IS_WINDOWS,
        "IS_MAC": IS_MAC,
        "IS_LINUX": IS_LINUX,
        # Directories
        "REPOS_DIR": REPOS_DIR,
        "LEARN_DIR": LEARN_DIR,
        # Models
        "PREFERRED_MODELS": PREFERRED_MODELS,
        "CHAT_MODEL_PATTERNS": CHAT_MODEL_PATTERNS,
        "CODE_MODEL_PATTERNS": CODE_MODEL_PATTERNS,
        "EMBED_MODEL_CANDIDATES": EMBED_MODEL_CANDIDATES,
        "AGENT_MODEL": AGENT_MODEL or "(auto-detect)",
        # LLM Parameters
        "AGENT_TEMPERATURE": AGENT_TEMPERATURE,
        "AGENT_MAX_TOKENS": AGENT_MAX_TOKENS,
        "CONTEXT_WINDOW_TOKENS": CONTEXT_WINDOW_TOKENS,
        "SUMMARIZATION_THRESHOLD": SUMMARIZATION_THRESHOLD,
        # Limits
        "MAX_REACT_ITERATIONS": MAX_REACT_ITERATIONS,
        "ADAPTIVE_ITERATIONS": ADAPTIVE_ITERATIONS,
        "MAX_CONVERSATION_MEMORY": MAX_CONVERSATION_MEMORY,
        "MAX_CONTEXT_CHARS": MAX_CONTEXT_CHARS,
        "MAX_FILE_READ": MAX_FILE_READ,
        "MAX_TOOL_OUTPUT": MAX_TOOL_OUTPUT,
        "MAX_EMBED_CACHE": MAX_EMBED_CACHE,
        "MAX_VECTORS_IN_MEMORY": MAX_VECTORS_IN_MEMORY,
        # Performance
        "SKIP_EMBED_ON_INTERACTION": SKIP_EMBED_ON_INTERACTION,
        "USE_STREAMING": USE_STREAMING,
        "GPU_CHECK_ON_START": GPU_CHECK_ON_START,
        # Hybrid Search
        "USE_HYBRID_SEARCH": USE_HYBRID_SEARCH,
        "USE_RERANKER": USE_RERANKER,
        "BM25_K1": BM25_K1,
        "BM25_B": BM25_B,
        "RRF_K": RRF_K,
        "HYBRID_MIN_SIMILARITY": HYBRID_MIN_SIMILARITY,
        # Web Search
        "WEB_SEARCH_MAX_RETRIES": WEB_SEARCH_MAX_RETRIES,
        "WEB_SEARCH_CACHE_TTL": WEB_SEARCH_CACHE_TTL,
        "WEB_SEARCH_FALLBACK_WIKI": WEB_SEARCH_FALLBACK_WIKI,
        # File Search
        "USE_RIPGREP": USE_RIPGREP,
        "FILE_SEARCH_MAX_DEPTH": FILE_SEARCH_MAX_DEPTH,
        "FILE_SEARCH_MAX_RESULTS": FILE_SEARCH_MAX_RESULTS,
        # Deep Thinking
        "DEEP_THINKING_MODE": DEEP_THINKING_MODE,
        "DEEP_THINKING_MIN_COMPLEXITY": DEEP_THINKING_MIN_COMPLEXITY,
        "DEEP_THINKING_MAX_THINKING_TOKENS": DEEP_THINKING_MAX_THINKING_TOKENS,
        "DEEP_THINKING_REFLECT_ON_ERRORS": DEEP_THINKING_REFLECT_ON_ERRORS,
        "DEEP_THINKING_SHOW_THOUGHTS": DEEP_THINKING_SHOW_THOUGHTS,
        # Sub-agents
        "SUBAGENT_MAX_PARALLEL": SUBAGENT_MAX_PARALLEL,
        "SUBAGENT_DEFAULT_TIMEOUT": SUBAGENT_DEFAULT_TIMEOUT,
        "SUBAGENT_MAX_TASKS": SUBAGENT_MAX_TASKS,
        "ORCHESTRATOR_MAX_SUBAGENTS": ORCHESTRATOR_MAX_SUBAGENTS,
        "ORCHESTRATOR_AUTO_STRATEGY": ORCHESTRATOR_AUTO_STRATEGY,
        # Timeouts
        "DEFAULT_TIMEOUT": DEFAULT_TIMEOUT,
        "LONG_TIMEOUT": LONG_TIMEOUT,
        "LLM_TIMEOUT_SMALL": LLM_TIMEOUT_SMALL,
        "LLM_TIMEOUT_LARGE": LLM_TIMEOUT_LARGE,
        "EMBED_TIMEOUT": EMBED_TIMEOUT,
        "WEB_TIMEOUT": WEB_TIMEOUT,
        "TOOL_EXECUTION_TIMEOUT": TOOL_EXECUTION_TIMEOUT,
        # Multimedia
        "TTS_DEFAULT_VOICE": TTS_DEFAULT_VOICE,
        "TTS_DEFAULT_SPEED": TTS_DEFAULT_SPEED,
        "TTS_MAX_TEXT_LENGTH": TTS_MAX_TEXT_LENGTH,
        "IMAGE_DEFAULT_SIZE": IMAGE_DEFAULT_SIZE,
        "VIDEO_FRAME_INTERVAL": VIDEO_FRAME_INTERVAL,
    }


# ============================================================
# AUTO-VALIDATE AT IMPORT TIME
# ============================================================
_validation_results = validate_config()
_errors = [k for k, v in _validation_results.items() if v != "ok"]
if _errors:
    for _setting, _result in _validation_results.items():
        if _result != "ok":
            logger.warning(f"Config validation: {_setting} -> {_result}")
else:
    logger.info("Config validation: all settings OK")
