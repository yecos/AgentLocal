"""
config.py - Configuracion centralizada del Agente v14
Extraido de app_auto_pro.py lineas 56-140
"""
import os
import platform
from pathlib import Path

# ── Modelos preferidos en orden de prioridad ──
PREFERRED_MODELS = [
    "qwen3:4b", "qwen3-coder", "qwen3-coder-next",
    "qwen3:30b-a3b", "qwen2.5:14b", "llama3.1:8b"
]

# ── Parametros del agente ──
MAX_REACT_ITERATIONS = 8
MAX_CONVERSATION_MEMORY = 20
CONTEXT_BUDGET_CHARS = 3000
AUTO_SAVE_INTERVAL = 5  # mensajes entre auto-saves
SESSION_TTL_HOURS = 24

# ── Directorios ──
if platform.system() == "Windows":
    REPOS_DIR = os.path.join(os.path.expanduser("~"), "Documents")
else:
    REPOS_DIR = os.path.join(os.path.expanduser("~"), "repos")

LEARN_DIR = os.path.join(os.path.expanduser("~"), ".ia-local", "learning")
os.makedirs(REPOS_DIR, exist_ok=True)
os.makedirs(LEARN_DIR, exist_ok=True)

# ── Archivos de persistencia ──
CORRECTIONS_FILE = os.path.join(LEARN_DIR, "corrections.json")
FEEDBACK_FILE = os.path.join(LEARN_DIR, "feedback.json")
PATTERNS_FILE = os.path.join(LEARN_DIR, "patterns.json")
KNOWLEDGE_FILE = os.path.join(LEARN_DIR, "knowledge.json")
SESSION_FILE = os.path.join(LEARN_DIR, "session.json")
EXE_CACHE_FILE = os.path.join(LEARN_DIR, "exe_cache.json")
LLM_ERRORS_LOG = os.path.join(LEARN_DIR, "llm_errors.log")
AGENT_LOG_FILE = os.path.join(LEARN_DIR, "agent.log")

# ── Seguridad ──
COMANDOS_PELIGROSOS = [
    "rm -rf", "del /f /s /q", "format", "fdisk",
    "reg delete", "net user", "shutdown", "rmdir /s /q",
    "mkfs", "dd if=", "> /dev/sd", "curl | bash", "curl | sh",
    "rd /s /q", "taskkill /f /pid system",
    "powershell -enc", "certutil", "bitsadmin", "mshta",
    "cipher /w", "diskpart", "reg add",
]

COMANDOS_SEGUROS = [
    "git", "npm", "pip", "python", "node", "dir", "ls",
    "cat", "echo", "cd", "type", "find", "where", "which",
    "tasklist", "start", "open", "xdg-open",
    "pipenv", "poetry", "bun", "yarn", "cargo",
    "docker ps", "docker images", "docker compose",
]

# ── Sitios web conocidos ──
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

# ── Aliases de aplicaciones ──
APP_ALIASES = {
    "chrome": "google chrome", "vscode": "visual studio code",
    "autocad": "autocad", "revit": "revit",
    "whatsapp": "whatsapp", "telegram": "telegram desktop",
    "word": "word", "excel": "excel", "powerpoint": "powerpoint",
    "photoshop": "adobe photoshop", "illustrator": "adobe illustrator",
    "figma": "figma", "blender": "blender", "sketchup": "sketchup",
    "notepad": "notepad", "bloc de notas": "notepad",
}

# ── Ollama ──
OLLAMA_HOSTS = ["http://localhost:11434", "http://127.0.0.1:11434"]
EMBED_MODELS = ["nomic-embed-text", "mxbai-embed-large", "all-minilm"]
EMBED_CACHE_MAX = 200
EXE_CACHE_TTL = 3600  # 1 hora

# ── Prefijos de voz/texto ──
STRIP_PREFIXES = [
    "abre ", "abrir ", "open ", "inicia ", "lanza ", "mi ",
    "ve a ", "ir a ", "navega a ", "busca ", "buscar ",
    "pon ", "ponme ", "reproduce "
]
