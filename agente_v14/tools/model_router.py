"""
=============================================================
AGENTE v14 - Multi-Model Router
=============================================================
Intelligent routing of requests to the best available LLM
model based on task type. Instead of using one model for
everything, it picks:
  - Small/fast model for routing decisions, simple chat, tool selection
  - Large/code model for code generation, complex reasoning
  - Vision model for image analysis
  - Embedding model for vector operations

Thread-safe with 5-minute cache to avoid re-scanning Ollama.
=============================================================
"""

import time
import threading
from typing import Optional

from config import logger

# ============================================================
# CONSTANTS
# ============================================================

# How long (seconds) to cache the model list before re-scanning
_CACHE_TTL = 300  # 5 minutes

# Keyword -> capability mappings for model classification
_CODE_KEYWORDS = {"coder", "code", "deepseek-coder", "codellama", "starcoder", "codeqwen"}
_VISION_KEYWORDS = {"llava", "vision", "bakllava", "llava-llama3", "moondream", "minicpm-v"}
_EMBEDDING_KEYWORDS = {"embed", "embedding", "e5", "bge"}
_CHAT_KEYWORDS = {
    "qwen", "llama", "mistral", "phi", "gemma", "falcon",
    "solar", "yi", "zephyr", "neural-chat", "orca",
    "dolphin", "nous-hermes", "openhermes", "wizardlm",
    "vicuna", "wizard-math", "deepseek", "command-r",
}

# Task type -> routing category
_ROUTING_TASKS = {"routing", "simple", "quick", "fast", "chat", "default"}
_CODE_TASKS = {"code", "coding", "programming", "debug", "refactor", "generate_code"}
_VISION_TASKS = {"vision", "image", "analyze_image", "imagen", "ver_imagen"}
_EMBEDDING_TASKS = {"embedding", "vector", "embed", "buscar_similar"}
_REASONING_TASKS = {"reasoning", "complex", "planning", "plan", "analizar", "diseñar", "architecture"}
_CREATIVE_TASKS = {"creative", "writing", "story", "escritura", "creativo"}

# Tool name keywords -> task type heuristics
_TOOL_CODE_KEYWORDS = {"codigo", "generar", "script", "code", "debug", "programar", "ejecutar_codigo"}
_TOOL_VISION_KEYWORDS = {"imagen", "vision", "analizar_imagen", "image", "ver_imagen", "captura"}
_TOOL_REASONING_KEYWORDS = {"plan", "analizar", "diseñar", "arquitectura", "investigar"}

# Prompt keywords -> task type heuristics
_PROMPT_CODE_KEYWORDS = {
    "funcion", "function", "codigo", "code", "script", "programa",
    "debug", "error", "bug", "fix", "refactor", "implementar",
    "clase", "class", "api", "endpoint", "sql", "query",
}
_PROMPT_REASONING_KEYWORDS = {
    "plan", "planificar", "analizar", "analyze", "diseñar", "design",
    "arquitectura", "architecture", "estrategia", "strategy",
    "evaluar", "evaluate", "comparar", "compare", "investigar",
}
_PROMPT_CREATIVE_KEYWORDS = {
    "escribir", "write", "historia", "story", "poema", "poem",
    "creativo", "creative", "redactar", "compose", "brainstorm",
}

# Recommended models per capability when missing
_RECOMMENDATIONS = {
    "code": "qwen2.5-coder:7b",
    "vision": "llava:7b",
    "embedding": "nomic-embed-text",
    "chat": "qwen2.5:7b",
}

# Sensible defaults when Ollama is unreachable
_DEFAULT_INVENTORY = {
    "chat": ["qwen2.5:7b"],
    "code": ["qwen2.5-coder:7b"],
    "vision": ["llava:7b"],
    "embedding": ["nomic-embed-text"],
}


# ============================================================
# HELPER: extract parameter size from model name
# ============================================================

def _extract_param_size(model_name: str) -> float:
    """Extract the parameter size in billions from a model name.

    Examples:
        "qwen2.5:7b"    -> 7.0
        "llama3.1:8b"   -> 8.0
        "qwen2.5:14b"   -> 14.0
        "qwen3:30b-a3b" -> 30.0
        "phi3:mini"     -> 3.8  (known aliases)
        "unknown"       -> 7.0  (safe default)

    Returns:
        float: estimated parameter count in billions
    """
    import re

    name_lower = model_name.lower()

    # Use regex to find the first occurrence of a number followed by 'b'
    # Handles: "7b", "14b", "30b-a3b", "0.5b", etc.
    match = re.search(r'(\d+(?:\.\d+)?)b', name_lower)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    # Known aliases
    known = {
        "mini": 3.8,
        "micro": 2.0,
        "tiny": 1.5,
        "small": 7.0,
        "medium": 14.0,
        "large": 30.0,
    }
    for alias, size in known.items():
        if alias in name_lower:
            return size

    return 7.0  # safe default


# ============================================================
# MODEL ROUTER CLASS
# ============================================================

class ModelRouter:
    """Intelligent multi-model router for AgentLocal.

    Detects available Ollama models, classifies them by capability,
    and routes each request to the most appropriate model based on
    task type, tool name, and prompt content.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._models_by_capability: dict[str, list[str]] = {
            "chat": [],
            "code": [],
            "vision": [],
            "embedding": [],
        }
        self._all_models: list[str] = []
        self._defaults: dict[str, Optional[str]] = {
            "chat": None,
            "code": None,
            "vision": None,
            "embedding": None,
        }
        self._last_scan: float = 0.0
        self._ollama_available: bool = True

        # Initial detection
        self._detect_available_models()

    # ----------------------------------------------------------
    # Model Detection
    # ----------------------------------------------------------

    def _detect_available_models(self) -> dict[str, list[str]]:
        """Scan Ollama for available models and classify them.

        Uses ``from llm import ollama`` when available, falling back
        to a direct HTTP call to the Ollama API.  If Ollama is
        completely unreachable, sensible defaults are used.

        Returns:
            dict mapping capability -> list of model names, e.g.
            {"chat": ["qwen2.5:7b"], "code": ["qwen2.5-coder:7b"], ...}
        """
        with self._lock:
            models = self._fetch_ollama_models()

            if not models:
                self._ollama_available = False
                logger.warning(
                    "Ollama no disponible o sin modelos. Usando defaults."
                )
                self._models_by_capability = {
                    k: list(v) for k, v in _DEFAULT_INVENTORY.items()
                }
                self._all_models = ["qwen2.5:7b", "qwen2.5-coder:7b"]
                self._set_defaults()
                self._last_scan = time.time()
                return dict(self._models_by_capability)

            self._ollama_available = True
            self._all_models = list(models)

            # Reset capability buckets
            self._models_by_capability = {
                "chat": [],
                "code": [],
                "vision": [],
                "embedding": [],
            }

            # Classify each model
            for model_name in models:
                capabilities = self._classify_model(model_name)
                for cap in capabilities:
                    if cap in self._models_by_capability:
                        self._models_by_capability[cap].append(model_name)

            # Any model that was only classified as "chat" and nothing else
            # is already in the chat bucket from _classify_model default.
            # Models with specialised caps are *also* added to chat if they
            # can serve as general-purpose (e.g. qwen2.5-coder can chat).

            self._set_defaults()
            self._last_scan = time.time()

            logger.debug(
                f"Modelos detectados: chat={self._models_by_capability['chat']}, "
                f"code={self._models_by_capability['code']}, "
                f"vision={self._models_by_capability['vision']}, "
                f"embedding={self._models_by_capability['embedding']}"
            )
            return dict(self._models_by_capability)

    def _fetch_ollama_models(self) -> list[str]:
        """Fetch the list of locally installed model names from Ollama.

        Tries the ``llm.ollama`` package first, then falls back to a
        direct HTTP request.  Returns an empty list on any failure.
        """
        # Attempt 1: llm.ollama package
        try:
            from llm import ollama as llm_ollama
            # The llm package exposes models via get_models() or similar
            if hasattr(llm_ollama, "get_models"):
                return [m.model_id for m in llm_ollama.get_models()]
        except Exception as exc:
            logger.debug(f"llm.ollama no disponible: {exc}")

        # Attempt 2: Direct HTTP to Ollama API
        try:
            import json
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            logger.debug(f"Ollama HTTP no disponible: {exc}")

        return []

    # ----------------------------------------------------------
    # Model Classification
    # ----------------------------------------------------------

    @staticmethod
    def _classify_model(model_name: str) -> list[str]:
        """Return a list of capabilities for the given model name.

        Uses keyword matching against known model families.
        Unknown models default to ``["chat"]``.

        Args:
            model_name: Ollama model identifier, e.g. "qwen2.5-coder:7b"

        Returns:
            List of capability strings, e.g. ["code", "chat"]
        """
        name_lower = model_name.lower()
        capabilities: list[str] = []

        # Check embedding first (most specific)
        if any(kw in name_lower for kw in _EMBEDDING_KEYWORDS):
            capabilities.append("embedding")
            # Embedding models are not useful for chat/code/vision
            return capabilities

        # Check vision
        if any(kw in name_lower for kw in _VISION_KEYWORDS):
            capabilities.append("vision")

        # Check code
        if any(kw in name_lower for kw in _CODE_KEYWORDS):
            capabilities.append("code")

        # All non-embedding models can chat (even code/vision models)
        capabilities.append("chat")

        return capabilities

    # ----------------------------------------------------------
    # Default Model Selection
    # ----------------------------------------------------------

    def _set_defaults(self) -> None:
        """Select the default model for each capability bucket.

        Prefers smaller parameter sizes for speed.  If a bucket is
        empty, the default remains ``None`` and fallback logic will
        be used at routing time.
        """
        # Chat default: smallest chat model
        self._defaults["chat"] = self._pick_smallest(
            self._models_by_capability["chat"]
        )

        # Code default: smallest code model
        self._defaults["code"] = self._pick_smallest(
            self._models_by_capability["code"]
        )

        # Vision default: first available vision model
        self._defaults["vision"] = self._pick_smallest(
            self._models_by_capability["vision"]
        )

        # Embedding default: first available embedding model
        self._defaults["embedding"] = self._pick_first(
            self._models_by_capability["embedding"]
        )

    @staticmethod
    def _pick_smallest(models: list[str]) -> Optional[str]:
        """Return the model with the smallest parameter count.

        Falls back to the first model in the list if sizes cannot
        be determined.  Returns ``None`` for empty lists.
        """
        if not models:
            return None
        return min(models, key=_extract_param_size)

    @staticmethod
    def _pick_largest(models: list[str]) -> Optional[str]:
        """Return the model with the largest parameter count.

        Returns ``None`` for empty lists.
        """
        if not models:
            return None
        return max(models, key=_extract_param_size)

    @staticmethod
    def _pick_first(models: list[str]) -> Optional[str]:
        """Return the first model in the list or ``None``."""
        return models[0] if models else None

    # ----------------------------------------------------------
    # Cache Management
    # ----------------------------------------------------------

    def _refresh_if_stale(self) -> None:
        """Re-scan Ollama models if the cache has expired."""
        if time.time() - self._last_scan > _CACHE_TTL:
            logger.debug("Cache de modelos expirado, re-escaneando...")
            self._detect_available_models()

    # ----------------------------------------------------------
    # Public API: Model Selection
    # ----------------------------------------------------------

    def get_model_for_task(self, task_type: str) -> str:
        """Return the best model name for the given task type.

        Args:
            task_type: One of the recognised task categories
                (routing, simple, quick, code, coding, programming,
                 vision, image, analyze_image, embedding, vector,
                 reasoning, complex, planning, creative, writing, ...).

        Returns:
            Model name string, e.g. "qwen2.5-coder:7b".
            Falls back to the default chat model if no specialised
            model is available.
        """
        self._refresh_if_stale()

        task = task_type.lower().strip()

        # --- Routing / simple / quick -> smallest chat model ---
        if task in _ROUTING_TASKS:
            model = self._defaults["chat"]
            if model:
                logger.debug(f"Task '{task_type}' -> chat model: {model}")
                return model

        # --- Code tasks -> code model, else largest chat ---
        if task in _CODE_TASKS:
            model = self._defaults["code"]
            if model:
                logger.debug(f"Task '{task_type}' -> code model: {model}")
                return model
            # Fallback to largest chat model for complex code
            model = self._pick_largest(self._models_by_capability["chat"])
            if model:
                logger.debug(
                    f"Task '{task_type}' -> no code model, using largest chat: {model}"
                )
                return model

        # --- Vision tasks -> vision model ---
        if task in _VISION_TASKS:
            model = self._defaults["vision"]
            if model:
                logger.debug(f"Task '{task_type}' -> vision model: {model}")
                return model

        # --- Embedding tasks -> embedding model ---
        if task in _EMBEDDING_TASKS:
            model = self._defaults["embedding"]
            if model:
                logger.debug(f"Task '{task_type}' -> embedding model: {model}")
                return model

        # --- Reasoning / complex -> largest chat model ---
        if task in _REASONING_TASKS:
            model = self._pick_largest(self._models_by_capability["chat"])
            if model:
                logger.debug(f"Task '{task_type}' -> reasoning model: {model}")
                return model

        # --- Creative / writing -> prefer instruct variants ---
        if task in _CREATIVE_TASKS:
            model = self._pick_creative_model()
            if model:
                logger.debug(f"Task '{task_type}' -> creative model: {model}")
                return model

        # --- Final fallback: default chat model ---
        model = self._defaults["chat"]
        if model:
            logger.debug(f"Task '{task_type}' -> fallback chat model: {model}")
            return model

        # Absolute fallback (Ollama down, no models at all)
        fallback = "qwen2.5:7b"
        logger.warning(
            f"Ningun modelo disponible para task '{task_type}', "
            f"usando fallback: {fallback}"
        )
        return fallback

    def _pick_creative_model(self) -> Optional[str]:
        """Select the best model for creative/writing tasks.

        Prefers models with 'instruct' variants, otherwise uses the
        largest available chat model for richer generation.
        """
        chat_models = self._models_by_capability["chat"]
        if not chat_models:
            return None

        # Prefer instruct variants
        for m in chat_models:
            if "instruct" in m.lower():
                return m

        # Otherwise largest chat model
        return self._pick_largest(chat_models)

    def get_default_model(self) -> str:
        """Return the best general-purpose model available.

        Selects the smallest chat model for general tasks (speed over
        size for the default).  Falls back to a hardcoded name if
        nothing is available.
        """
        self._refresh_if_stale()
        model = self._defaults["chat"]
        if model:
            return model
        return "qwen2.5:7b"

    # ----------------------------------------------------------
    # Public API: Request Routing
    # ----------------------------------------------------------

    def route_request(self, prompt: str, tool_name: str = "") -> dict:
        """Analyse a request and return a full routing decision.

        Uses heuristics on the tool name and prompt content to
        determine the task type, then selects the best model.

        Args:
            prompt: The user prompt / request text.
            tool_name: Name of the tool being invoked (optional).

        Returns:
            dict with keys:
                - model: selected model name
                - reason: human-readable reason for the selection
                - task_type: detected task category
                - estimated_complexity: "low", "medium", or "high"
        """
        self._refresh_if_stale()

        task_type, reason = self._infer_task_type(prompt, tool_name)
        model = self.get_model_for_task(task_type)
        complexity = self._estimate_complexity(prompt, task_type)

        logger.debug(
            f"Route: tool='{tool_name}' task='{task_type}' "
            f"-> model={model} ({reason})"
        )

        return {
            "model": model,
            "reason": reason,
            "task_type": task_type,
            "estimated_complexity": complexity,
        }

    def _infer_task_type(self, prompt: str, tool_name: str = "") -> tuple[str, str]:
        """Determine the task type from tool name and prompt content.

        Returns:
            (task_type, reason) tuple.
        """
        tool_lower = tool_name.lower()
        prompt_lower = prompt.lower()

        # --- Check tool name heuristics first (high signal) ---
        for kw in _TOOL_VISION_KEYWORDS:
            if kw in tool_lower:
                return "vision", f"tool '{tool_name}' indicates image analysis"

        for kw in _TOOL_CODE_KEYWORDS:
            if kw in tool_lower:
                return "code", f"tool '{tool_name}' indicates code generation"

        for kw in _TOOL_REASONING_KEYWORDS:
            if kw in tool_lower:
                return "reasoning", f"tool '{tool_name}' indicates planning/analysis"

        # --- Check prompt content ---
        # Vision
        for kw in _VISION_TASKS:
            if kw in prompt_lower:
                return "vision", f"prompt mentions '{kw}'"

        # Code
        code_hits = sum(1 for kw in _PROMPT_CODE_KEYWORDS if kw in prompt_lower)
        if code_hits >= 2:
            return "code", f"prompt contains {code_hits} code-related keywords"

        # Reasoning
        for kw in _PROMPT_REASONING_KEYWORDS:
            if kw in prompt_lower:
                return "reasoning", f"prompt mentions '{kw}'"

        # Creative
        for kw in _PROMPT_CREATIVE_KEYWORDS:
            if kw in prompt_lower:
                return "creative", f"prompt mentions '{kw}'"

        # --- Short / simple prompt -> routing ---
        word_count = len(prompt.split())
        if word_count <= 6:
            return "routing", "short simple prompt, using fast model"

        # --- Default: chat ---
        return "chat", "general-purpose chat request"

    @staticmethod
    def _estimate_complexity(prompt: str, task_type: str) -> str:
        """Estimate request complexity as low / medium / high.

        Heuristics:
          - embedding, routing, simple -> low
          - code, creative with long prompt -> high
          - reasoning -> high
          - everything else -> medium
        """
        if task_type in ("embedding", "routing", "simple"):
            return "low"
        if task_type in ("reasoning", "complex", "planning"):
            return "high"
        if task_type == "code":
            word_count = len(prompt.split())
            return "high" if word_count > 20 else "medium"
        if task_type == "creative":
            word_count = len(prompt.split())
            return "high" if word_count > 30 else "medium"
        return "medium"

    # ----------------------------------------------------------
    # Public API: Information & Recommendations
    # ----------------------------------------------------------

    def get_model_info(self) -> dict:
        """Return complete model inventory with classifications.

        Returns:
            dict with keys:
                - available: list of all detected model names
                - by_capability: dict mapping capability -> model list
                - defaults: dict mapping capability -> default model name
                - recommended: best general-purpose model name
        """
        self._refresh_if_stale()
        return {
            "available": list(self._all_models),
            "by_capability": {
                k: list(v) for k, v in self._models_by_capability.items()
            },
            "defaults": dict(self._defaults),
            "recommended": self.get_default_model(),
        }

    def recommend_model_install(self) -> list[str]:
        """Return a list of recommendations for missing model types.

        Checks each capability bucket and suggests a model to install
        if the bucket is empty.

        Returns:
            List of human-readable recommendation strings.
        """
        self._refresh_if_stale()
        recommendations: list[str] = []

        if not self._models_by_capability.get("code"):
            recommendations.append(
                f"Install {_RECOMMENDATIONS['code']} for better code generation"
            )
        if not self._models_by_capability.get("vision"):
            recommendations.append(
                f"Install {_RECOMMENDATIONS['vision']} for image analysis"
            )
        if not self._models_by_capability.get("embedding"):
            recommendations.append(
                f"Install {_RECOMMENDATIONS['embedding']} for vector operations"
            )
        if not self._models_by_capability.get("chat"):
            recommendations.append(
                f"Install {_RECOMMENDATIONS['chat']} for general chat"
            )

        # Extra: if only one chat model and it's large, suggest a smaller one too
        chat_models = self._models_by_capability.get("chat", [])
        if len(chat_models) == 1:
            size = _extract_param_size(chat_models[0])
            if size > 10:
                recommendations.append(
                    f"Consider installing a smaller model (e.g. qwen2.5:7b) "
                    f"for faster simple tasks (current chat model is {chat_models[0]})"
                )

        return recommendations


# ============================================================
# SINGLETON ACCESS
# ============================================================

_router: Optional[ModelRouter] = None
_router_lock = threading.Lock()


def get_router() -> ModelRouter:
    """Return the global ModelRouter singleton (lazy initialisation).

    Thread-safe: multiple threads calling this concurrently will still
    get a single shared instance.
    """
    global _router
    if _router is None:
        with _router_lock:
            # Double-check after acquiring lock
            if _router is None:
                _router = ModelRouter()
                logger.info("ModelRouter singleton inicializado")
    return _router
