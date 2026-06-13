# config.py - Configuración Centralizada del Agente Inteligente Local
import os


class Config:
    """Configuración del agente. Todas las variables se pueden
    sobreescribir con variables de entorno."""

    # ── Modelo ──────────────────────────────────────────────
    MODEL_NAME = os.getenv("MODEL_NAME", "qwen2.5:32b")
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))

    # ── Bucle Agéntico ──────────────────────────────────────
    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "5"))
    # Cuántas veces puede pensar-actuar-observar antes de responder

    # ── Búsqueda Web ────────────────────────────────────────
    SEARCH_ENGINE = os.getenv("SEARCH_ENGINE", "duckduckgo")
    SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080/search")

    # ── Memoria ─────────────────────────────────────────────
    MEMORY_DB = os.getenv("MEMORY_DB", "memoria_agente.db")
    MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "true").lower() == "true"

    # ── Documentos locales (RAG futuro) ─────────────────────
    DOCS_DIR = os.getenv("DOCS_DIR", "./documentos")

    # ── Seguridad ───────────────────────────────────────────
    ALLOWED_DIRS = ["/tmp", os.path.expanduser("~/proyectos")]
    CODE_TIMEOUT = int(os.getenv("CODE_TIMEOUT", "30"))

    # ── Logging ─────────────────────────────────────────────
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def resumen(cls) -> str:
        """Devuelve un resumen legible de la configuración actual."""
        return (
            f"Modelo: {cls.MODEL_NAME}\n"
            f"Ollama: {cls.OLLAMA_URL}\n"
            f"Iteraciones máx: {cls.MAX_ITERATIONS}\n"
            f"Temperatura: {cls.TEMPERATURE}\n"
            f"Buscador: {cls.SEARCH_ENGINE}\n"
            f"Memoria: {cls.MEMORY_DB} ({'activada' if cls.MEMORY_ENABLED else 'desactivada'})\n"
            f"Documentos: {cls.DOCS_DIR}"
        )
