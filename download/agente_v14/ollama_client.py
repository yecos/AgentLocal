"""
ollama_client.py - Cliente Ollama simplificado con cache LRU y conexion persistente
Refactoring de _llm_generate() (v13, 140+ lineas, 3 estrategias redundantes)
a una clase OllamaClient con patron simple: client -> HTTP fallback.
"""
import json
import logging
import hashlib
import urllib.request
from collections import OrderedDict
from typing import Optional, Union

from .config import (
    OLLAMA_HOSTS, PREFERRED_MODELS, EMBED_MODELS,
    EMBED_CACHE_MAX, LLM_ERRORS_LOG, LEARN_DIR
)

logger = logging.getLogger("agente.llm")


class LRUEmbedCache:
    """Cache LRU para embeddings. Reemplaza el FIFO de v13."""
    
    def __init__(self, max_size=EMBED_CACHE_MAX):
        self._cache = OrderedDict()
        self._max_size = max_size
    
    def get(self, key):
        if key in self._cache:
            self._cache.move_to_end(key)  # Marcar como recien usado
            return self._cache[key]
        return None
    
    def put(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            self._cache[key] = value
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)  # Eliminar menos reciente
    
    def __len__(self):
        return len(self._cache)


class OllamaClient:
    """Cliente Ollama con conexion persistente y retry simple.
    
    Simplificacion de _llm_generate() de v13:
    - Patron: client cacheado -> nuevo client -> HTTP directo
    - Cache LRU para embeddings (reemplaza FIFO)
    - Deteccion de modelo una sola vez
    - Logging de errores para diagnostico
    """
    
    def __init__(self, host="http://localhost:11434"):
        self.host = host
        self._client = None
        self._model = None
        self._fallback_model = None
        self._embed_model = None
        self._embed_cache = LRUEmbedCache()
        self._tool_calling_support = None
    
    def _get_client(self):
        """Obtiene o crea cliente ollama."""
        if self._client is not None:
            return self._client
        try:
            import ollama
            self._client = ollama.Client(host=self.host)
            return self._client
        except ImportError:
            logger.warning("Paquete ollama no instalado, usando HTTP directo")
            return None
    
    def chat(self, messages, model=None, tools=None, timeout=120):
        """Chat simplificado: client -> HTTP directo.
        
        Retorna:
        - str: texto de respuesta (sin tools)
        - dict: respuesta completa con tool_calls (con tools)
        - "": si todo falla
        """
        model = model or self.detect_model()
        
        # Estrategia 1: ollama Client
        client = self._get_client()
        if client:
            try:
                kwargs = {"model": model, "messages": messages}
                if tools:
                    kwargs["tools"] = tools
                resp = client.chat(**kwargs)
                if tools:
                    msg = resp.get("message", resp)
                    if msg.get("content") or msg.get("tool_calls"):
                        return resp
                else:
                    content = resp.get("message", {}).get("content", "")
                    if content:
                        return content
            except Exception as e:
                logger.warning(f"Client falló: {e}, intentando HTTP")
                self._client = None  # Reset client roto
        
        # Estrategia 2: HTTP directo
        return self._http_chat(messages, model, tools, timeout)
    
    def _http_chat(self, messages, model, tools=None, timeout=120):
        """Fallback HTTP directo."""
        try:
            payload = {
                "model": model, 
                "messages": messages, 
                "stream": False
            }
            if tools:
                payload["tools"] = tools
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/chat", data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if tools:
                    return result
                return result.get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"HTTP directo fallo: {e}")
            self._log_error(str(e))
            return ""
    
    def detect_model(self) -> str:
        """Detecta el mejor modelo disponible. Se ejecuta UNA vez."""
        if self._model:
            return self._model
        
        available = self._get_available_models()
        
        if not available:
            self._model = "qwen2.5:14b"
            self._fallback_model = "llama3.1:8b"
            return self._model
        
        # Buscar el mejor modelo en orden de preferencia
        for preferred in PREFERRED_MODELS:
            for avail in available:
                if preferred in avail or avail.startswith(preferred.split(":")[0]):
                    self._model = avail
                    # Buscar fallback
                    for fb in PREFERRED_MODELS:
                        if fb != preferred:
                            for avail2 in available:
                                if fb in avail2 or avail2.startswith(fb.split(":")[0]):
                                    self._fallback_model = avail2
                                    return self._model
                    self._fallback_model = available[0] if len(available) > 1 else avail
                    return self._model
        
        self._model = available[0]
        self._fallback_model = available[1] if len(available) > 1 else available[0]
        return self._model
    
    def detect_embed_model(self) -> str:
        """Detecta que modelo de embeddings esta disponible. Se ejecuta UNA vez."""
        if self._embed_model:
            return self._embed_model
        
        try:
            available = self._get_available_models()
            available_lower = [m.lower() for m in available]
            for candidate in EMBED_MODELS:
                for avail in available_lower:
                    if candidate in avail:
                        self._embed_model = candidate
                        logger.info(f"Modelo de embeddings detectado: {candidate}")
                        return candidate
        except Exception as e:
            logger.warning(f"No se pudo detectar modelo de embeddings: {e}")
        
        self._embed_model = "nomic-embed-text"  # Default
        return self._embed_model
    
    def get_embedding(self, text: str) -> list:
        """Obtiene el embedding de un texto usando Ollama. Con cache LRU."""
        cache_key = hashlib.md5(text[:500].encode()).hexdigest()[:16]
        
        # Cache hit
        cached = self._embed_cache.get(cache_key)
        if cached is not None:
            return cached
        
        embed_model = self.detect_embed_model()
        
        try:
            data = json.dumps({
                "model": embed_model,
                "prompt": text[:2000]
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/embeddings", data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                embedding = result.get("embedding", [])
                if embedding:
                    self._embed_cache.put(cache_key, embedding)
                    return embedding
        except Exception as e:
            logger.warning(f"Error obteniendo embedding: {e}")
        return []
    
    def _get_available_models(self) -> list:
        """Obtiene la lista de modelos disponibles en Ollama."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []
    
    def detect_tool_calling_support(self) -> bool:
        """Detecta si el modelo soporta function calling nativo."""
        if self._tool_calling_support is not None:
            return self._tool_calling_support
        
        model = self.detect_model()
        model_lower = model.lower()
        
        # Modelos que SI soportan tool calling
        if any(x in model_lower for x in ["qwen3", "qwen3-coder"]):
            self._tool_calling_support = True
            return True
        
        # Modelos que probablemente NO
        if any(x in model_lower for x in ["qwen2.5:14b", "qwen2.5:32b"]):
            self._tool_calling_support = False
            return False
        
        # Test rapido
        try:
            client = self._get_client()
            if client:
                from .tools import get_tool_schemas
                schemas = get_tool_schemas()
                if schemas:
                    client.chat(
                        model=model,
                        messages=[{"role": "user", "content": "hi"}],
                        tools=[schemas[0]]
                    )
                    self._tool_calling_support = True
                    return True
        except Exception:
            pass
        
        self._tool_calling_support = False
        return False
    
    def _log_error(self, error_msg: str):
        """Guarda errores de LLM en log para diagnostico."""
        try:
            from datetime import datetime
            with open(LLM_ERRORS_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now().isoformat()} ---\n")
                f.write(f"  {error_msg[:200]}\n")
        except OSError:
            pass
    
    @property
    def embed_cache_size(self) -> int:
        return len(self._embed_cache)
    
    @property
    def model(self):
        return self._model
    
    @property
    def fallback_model(self):
        return self._fallback_model


# Singleton global
ollama_client = OllamaClient()
