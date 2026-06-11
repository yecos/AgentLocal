"""
=============================================================
AGENTE LOCAL AUTONOMO v14 - Cliente Ollama Optimizado
=============================================================
Singleton con cache de conexion persistente.
- Cache en archivo JSON (sobrevive reinicios)
- Timeout agresivo con 1 solo reintento
- Modelo dual: chat rapido vs code potente
- Streaming para respuestas en tiempo real
- Deteccion de GPU para diagnosticar lentitud
=============================================================
"""

import json
import os
import logging
from datetime import datetime

from config import (
    PREFERRED_MODELS, CHAT_MODEL_PATTERNS, CODE_MODEL_PATTERNS,
    EMBED_MODEL_CANDIDATES, LEARN_DIR, CONNECTION_CACHE_FILE,
    CONNECTION_CACHE_DAYS, LLM_TIMEOUT_SMALL, LLM_TIMEOUT_LARGE,
    EMBED_TIMEOUT, logger
)

# ============================================================
# CACHE LRU PARA EMBEDDINGS
# ============================================================
from collections import OrderedDict


class LRUCache:
    """Cache LRU real usando OrderedDict. Reemplaza el FIFO del v13."""

    def __init__(self, maxsize=200):
        self._cache = OrderedDict()
        self._maxsize = maxsize

    def get(self, key):
        if key in self._cache:
            self._cache.move_to_end(key)  # Mas reciente al final
            return self._cache[key]
        return None

    def put(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)  # Elimina el mas viejo
            self._cache[key] = value

    def __len__(self):
        return len(self._cache)

    def clear(self):
        self._cache.clear()


# Instancia global del cache de embeddings
embed_cache = LRUCache(maxsize=200)


# ============================================================
# CLIENTE OLLAMA SINGLETON
# ============================================================

class OllamaClient:
    """
    Singleton que maneja la conexion a Ollama.
    Cachea la conexion exitosa en archivo JSON para sobrevivir reinicios.
    Soporta streaming para respuestas en tiempo real.
    """

    _instance = None

    def __init__(self):
        self.model = None
        self.fallback_model = None
        self.chat_model = None
        self.code_model = None
        self.host = None
        self.method = None  # 'client' or 'http'
        self.embed_model = None
        self._models_list = None
        self._detected = False
        self._client = None
        self._gpu_status = None  # None = no verificado, True/False

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ----------------------------------------------------------
    # DETECCION DE MODELOS
    # ----------------------------------------------------------

    def _fetch_available_models(self, refresh=False):
        """Obtiene la lista de modelos disponibles en Ollama."""
        if self._models_list is not None and not refresh:
            return self._models_list
        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self._models_list = [m["name"] for m in data.get("models", [])]
                return self._models_list
        except Exception as e:
            logger.warning(f"No se pudo conectar a Ollama: {e}")
            return []

    def detect_models(self):
        """Detecta el mejor modelo disponible. Se ejecuta 1 vez."""
        if self._detected:
            return self.model

        # Intentar cargar cache persistente primero
        cached = self._load_connection_cache()
        if cached:
            self.model = cached.get("model")
            self.host = cached.get("host")
            self.method = cached.get("method")
            logger.info(f"Cache de conexion cargado: {self.model}@{self.host}")
            # IMPORTANTE: Verificar que el modelo cacheado siga instalado
            available_check = self._fetch_available_models(refresh=True)
            if self.model and self.model not in available_check:
                logger.warning(f"Modelo cacheado '{self.model}' ya no esta instalado. Reseteando cache.")
                self.model = None
                self.host = None
                self.method = None
                # Borrar cache invalido
                try:
                    if os.path.exists(CONNECTION_CACHE_FILE):
                        os.remove(CONNECTION_CACHE_FILE)
                except Exception:
                    pass

        available = self._fetch_available_models()
        if not available:
            self.model = "qwen2.5:14b"
            self.fallback_model = "llama3.1:8b"
            self.chat_model = "llama3.1:8b"
            self.code_model = "qwen2.5:14b"
            self._detected = True
            return self.model

        # Buscar el mejor modelo en orden de preferencia (match EXACTO primero)
        for preferred in PREFERRED_MODELS:
            # 1. Match exacto: "qwen3:4b" == "qwen3:4b"
            for avail in available:
                if avail == preferred or avail.startswith(preferred + ":"):
                    self.model = avail
                    break
            if not self.model:
                # 2. Match parcial: modelo base coincide ("qwen3" en "qwen3:30b-a3b")
                #    PERO solo si no hay ya un match exacto de otro preferred
                preferred_base = preferred.split(":")[0]
                for avail in available:
                    if avail.split(":")[0] == preferred_base:
                        self.model = avail
                        break
            if self.model:
                # El fallback es el segundo mejor
                for fb in PREFERRED_MODELS:
                    if fb != preferred:
                        for avail2 in available:
                            if avail2 == fb or avail2.startswith(fb + ":"):
                                self.fallback_model = avail2
                                break
                        if self.fallback_model:
                            break
                if not self.fallback_model:
                    # Buscar fallback por modelo base
                    for fb in PREFERRED_MODELS:
                        if fb != preferred:
                            fb_base = fb.split(":")[0]
                            for avail2 in available:
                                if avail2.split(":")[0] == fb_base:
                                    self.fallback_model = avail2
                                    break
                            if self.fallback_model:
                                break
                if not self.fallback_model:
                    self.fallback_model = available[0] if len(available) > 1 else self.model
                break

        if not self.model:
            self.model = available[0]
            self.fallback_model = available[1] if len(available) > 1 else available[0]

        # Detectar modelos especializados
        self._detect_specialized_models(available)

        # Detectar modelo de embeddings
        self._detect_embed_model(available)

        self._detected = True
        logger.info(f"Modelo principal: {self.model}, Fallback: {self.fallback_model}")
        logger.info(f"Chat: {self.chat_model}, Code: {self.code_model}, Embed: {self.embed_model}")
        return self.model

    def _detect_specialized_models(self, available):
        """Detecta modelos para chat rapido y codigo potente."""
        available_lower = [m.lower() for m in available]
        # Chat model: el mas rapido
        for pattern in CHAT_MODEL_PATTERNS:
            for i, al in enumerate(available_lower):
                if pattern.lower() in al:
                    self.chat_model = available[i]
                    break
            if self.chat_model:
                break
        if not self.chat_model:
            self.chat_model = self.fallback_model or self.model

        # Code model: el mas potente
        for pattern in CODE_MODEL_PATTERNS:
            for i, al in enumerate(available_lower):
                if pattern.lower() in al:
                    self.code_model = available[i]
                    break
            if self.code_model:
                break
        if not self.code_model:
            self.code_model = self.model

    def _detect_embed_model(self, available):
        """Detecta que modelo de embeddings esta disponible."""
        available_lower = [m.lower() for m in available]
        for candidate in EMBED_MODEL_CANDIDATES:
            for al in available_lower:
                if candidate in al:
                    self.embed_model = candidate
                    logger.info(f"Modelo de embeddings detectado: {candidate}")
                    return
        self.embed_model = "nomic-embed-text"  # Default

    # ----------------------------------------------------------
    # DETECCION DE GPU
    # ----------------------------------------------------------

    def check_gpu_status(self):
        """
        Verifica si Ollama esta usando la GPU.
        Retorna: True (GPU), False (CPU), None (no se pudo determinar)
        """
        if self._gpu_status is not None:
            return self._gpu_status

        try:
            import subprocess
            result = subprocess.run(
                ["ollama", "ps"],
                capture_output=True, text=True, timeout=5
            )
            output = result.stdout
            if "100% CPU" in output:
                self._gpu_status = False
                logger.warning("GPU NO detectada por Ollama - corriendo en CPU (LENTO)")
            elif "GPU" in output:
                self._gpu_status = True
                logger.info("Ollama esta usando GPU")
            else:
                # No hay modelo cargado, verificar con nvidia-smi
                try:
                    nvidia = subprocess.run(
                        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                        capture_output=True, text=True, timeout=5
                    )
                    if nvidia.returncode == 0 and nvidia.stdout.strip():
                        logger.info(f"GPU NVIDIA detectada: {nvidia.stdout.strip()}")
                        # GPU existe pero no sabemos si Ollama la usa
                        self._gpu_status = None
                    else:
                        self._gpu_status = False
                except Exception:
                    self._gpu_status = False
        except Exception as e:
            logger.debug(f"No se pudo verificar GPU: {e}")
            self._gpu_status = None

        return self._gpu_status

    # ----------------------------------------------------------
    # CACHE PERSISTENTE DE CONEXION
    # ----------------------------------------------------------

    def _load_connection_cache(self):
        """Carga la conexion cacheada desde archivo JSON."""
        try:
            if os.path.exists(CONNECTION_CACHE_FILE):
                with open(CONNECTION_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                saved_at = data.get("saved_at", "")
                if saved_at:
                    saved_time = datetime.fromisoformat(saved_at)
                    days_ago = (datetime.now() - saved_time).days
                    if days_ago < CONNECTION_CACHE_DAYS:
                        return data
        except Exception:
            pass
        return None

    def _save_connection_cache(self):
        """Guarda la conexion exitosa en archivo JSON."""
        try:
            data = {
                "host": self.host,
                "method": self.method,
                "model": self.model,
                "saved_at": datetime.now().isoformat()
            }
            with open(CONNECTION_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ----------------------------------------------------------
    # GENERACION (sin streaming)
    # ----------------------------------------------------------

    def _get_timeout(self, model_name):
        """Timeout adaptativo segun tamano del modelo."""
        if any(x in (model_name or "").lower() for x in ["14b", "30b", "70b", "32b"]):
            return LLM_TIMEOUT_LARGE
        return LLM_TIMEOUT_SMALL

    def generate(self, messages, tools=None, model_override=None, timeout_overwrite=None):
        """
        Genera respuesta del LLM. Usa cache de conexion persistente.
        Retorna: str (texto) o dict (respuesta completa con tool_calls).
        Retorna "" si todo falla.
        """
        self.detect_models()
        model = model_override or self.model
        timeout = timeout_overwrite or self._get_timeout(model)

        errors = []

        # ---- ESTRATEGIA 1: Probar conexion cacheada ----
        if self.host and self.method:
            result = self._try_method(self.host, self.method, model, messages, tools, timeout)
            if result is not None:
                return result
            # Cache fallo, resetear
            self.method = None
            errors.append("cached connection failed")

        # ---- ESTRATEGIA 2: Buscar conexion que funcione ----
        models_to_try = [model]
        fallback = self.fallback_model
        if fallback and fallback != model:
            models_to_try.append(fallback)

        hosts = ['http://localhost:11434', 'http://127.0.0.1:11434']

        for m in models_to_try:
            for host in hosts:
                for method in ['client', 'http']:
                    result = self._try_method(host, method, m, messages, tools, timeout)
                    if result is not None:
                        # Guardar conexion exitosa
                        self.host = host
                        self.method = method
                        self._save_connection_cache()
                        logger.info(f"LLM conectado: {m}@{host} via {method}")
                        return result
                    errors.append(f"{m}@{host}/{method}: fallo")

        # Si llegamos aqui, todo fallo
        self._log_errors(errors)
        return ""

    def generate_chat(self, messages):
        """Para conversacion: usa modelo rapido."""
        return self.generate(messages, model_override=self.chat_model)

    def generate_code(self, messages):
        """Para codigo: usa modelo potente."""
        return self.generate(messages, model_override=self.code_model)

    # ----------------------------------------------------------
    # GENERACION CON STREAMING
    # ----------------------------------------------------------

    def generate_stream(self, messages, tools=None, model_override=None):
        """
        Genera respuesta del LLM con streaming.
        Yields: str (tokens de texto) o dict (resultado final con tool_calls).
        El llamador itera sobre los chunks para streaming en tiempo real.
        Retorna None si todo falla (el llamador debe usar generate() como fallback).
        """
        self.detect_models()
        model = model_override or self.model

        # Probar hosts en orden
        hosts = [self.host] if self.host else ['http://localhost:11434', 'http://127.0.0.1:11434']
        hosts = [h for h in hosts if h]  # Filtrar None
        if not hosts:
            hosts = ['http://localhost:11434', 'http://127.0.0.1:11434']

        for host in hosts:
            # Intentar streaming HTTP directo (mas rapido)
            stream = self._try_stream_http(host, model, messages, tools)
            if stream is not None:
                yield from stream
                return

            # Intentar streaming via client
            stream = self._try_stream_client(host, model, messages, tools)
            if stream is not None:
                yield from stream
                return

        # Ultimo fallback: sin streaming
        result = self.generate(messages, tools=tools, model_override=model_override)
        if result:
            if isinstance(result, str):
                yield result
            elif isinstance(result, dict):
                yield result
            return
        return

    def _try_stream_http(self, host, model, messages, tools):
        """Intenta streaming HTTP. Retorna generador o None si falla."""
        try:
            import urllib.request
            payload = {
                "model": model,
                "messages": messages,
                "stream": True
            }
            if tools:
                payload["tools"] = tools
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{host}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"}
            )

            def _stream():
                with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_LARGE) as resp:
                    full_content = ""
                    full_tool_calls = []
                    for line in resp:
                        line = line.decode("utf-8").strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        msg = chunk.get("message", {})
                        content = msg.get("content", "")
                        tool_calls = msg.get("tool_calls", [])

                        if content:
                            full_content += content
                            yield content

                        if tool_calls:
                            full_tool_calls.extend(tool_calls)

                        if chunk.get("done", False):
                            self.host = host
                            self.method = 'http'
                            self._save_connection_cache()

                            if full_tool_calls:
                                yield {
                                    "message": {
                                        "content": full_content,
                                        "tool_calls": full_tool_calls
                                    }
                                }
                            return

            # Test rapido: verificar que podemos abrir la conexion
            test_req = urllib.request.Request(
                f"{host}/api/tags",
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(test_req, timeout=3)
            return _stream()
        except Exception as e:
            logger.debug(f"HTTP streaming setup failed: {e}")
        return None

    def _try_stream_client(self, host, model, messages, tools):
        """Intenta streaming via ollama.Client. Retorna generador o None si falla."""
        try:
            import ollama as ollama_lib
            client = ollama_lib.Client(host=host)

            def _stream():
                full_content = ""
                full_tool_calls = []

                if tools:
                    # ollama client no soporta streaming con tools
                    # Usar modo no-streaming y yield todo de golpe
                    response = client.chat(model=model, messages=messages, tools=tools)
                    msg = response.get("message", response)
                    content = msg.get("content", "")
                    tool_calls = msg.get("tool_calls", [])

                    if content:
                        full_content = content
                        yield content
                    if tool_calls:
                        full_tool_calls = tool_calls

                    self.host = host
                    self.method = 'client'
                    self._save_connection_cache()

                    if full_tool_calls:
                        yield {"message": {"content": full_content, "tool_calls": full_tool_calls}}
                    return
                else:
                    stream = client.chat(model=model, messages=messages, stream=True)
                    for chunk in stream:
                        msg = chunk.get("message", {})
                        content = msg.get("content", "")
                        if content:
                            full_content += content
                            yield content

                        if chunk.get("done", False):
                            self.host = host
                            self.method = 'client'
                            self._save_connection_cache()
                            return

            return _stream()
        except Exception as e:
            logger.debug(f"Client streaming setup failed: {e}")
        return None

    # ----------------------------------------------------------
    # METODOS INTERNOS
    # ----------------------------------------------------------

    def _try_method(self, host, method, model, messages, tools, timeout):
        """Intenta una combinacion de host/metodo/modelo. Retorna None si falla."""
        if method == 'client':
            return self._try_client(host, model, messages, tools, timeout)
        elif method == 'http':
            return self._try_http(host, model, messages, tools, timeout)
        return None

    def _try_client(self, host, model, messages, tools, timeout):
        """Intenta via ollama.Client."""
        try:
            import ollama
            client = self._get_or_create_client(host)
            if tools:
                response = client.chat(model=model, messages=messages, tools=tools)
                msg = response.get("message", response)
                if msg.get("content") or msg.get("tool_calls"):
                    return response
            else:
                response = client.chat(model=model, messages=messages)
                content = response.get("message", {}).get("content", "")
                if content:
                    return content
        except Exception as e:
            logger.debug(f"Client method failed: {e}")
        return None

    def _try_http(self, host, model, messages, tools, timeout):
        """Intenta via HTTP directo (sin lib ollama)."""
        try:
            import urllib.request
            payload = {
                "model": model,
                "messages": messages,
                "stream": False
            }
            if tools:
                payload["tools"] = tools
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{host}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if tools:
                    msg = result.get("message", result)
                    if msg.get("content") or msg.get("tool_calls"):
                        return result
                else:
                    content = result.get("message", {}).get("content", "")
                    if content:
                        return content
        except Exception as e:
            logger.debug(f"HTTP method failed: {e}")
        return None

    def _get_or_create_client(self, host):
        """Obtiene o crea un ollama.Client."""
        if self._client is None:
            try:
                import ollama
                self._client = ollama.Client(host=host)
            except Exception:
                pass
        return self._client

    def _log_errors(self, errors):
        """Guarda errores en log para debug."""
        if errors:
            try:
                log_path = os.path.join(LEARN_DIR, "llm_errors.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"\n--- {datetime.now().isoformat()} ---\n")
                    for err in errors[-5:]:
                        f.write(f"  {err}\n")
            except Exception:
                pass

    # ----------------------------------------------------------
    # EMBEDDINGS (con cache optimizado)
    # ----------------------------------------------------------

    def get_embedding(self, text):
        """Obtiene el embedding de un texto usando Ollama. Con cache LRU."""
        import hashlib
        cache_key = hashlib.md5(text[:500].encode()).hexdigest()[:16]

        # Cache hit
        cached = embed_cache.get(cache_key)
        if cached is not None:
            return cached

        self.detect_models()
        try:
            import urllib.request
            data = json.dumps({
                "model": self.embed_model,
                "prompt": text[:2000]
            }).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:11434/api/embeddings",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=EMBED_TIMEOUT) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                embedding = result.get("embedding", [])
                if embedding:
                    embed_cache.put(cache_key, embedding)
                    return embedding
        except Exception as e:
            logger.warning(f"Error obteniendo embedding: {e}")
        return []

    @staticmethod
    def cosine_similarity(vec1, vec2):
        """Calcula similitud coseno entre dos vectores."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)


# ============================================================
# INSTANCIA GLOBAL
# ============================================================
ollama = OllamaClient.get()
