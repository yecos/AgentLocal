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
from utils.metrics import timed, get_metrics

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
            self._cache[key] = value  # Actualizar valor existente
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
        self._last_thinking = ""  # Último thinking nativo generado (qwen3, deepseek-r1)

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
                except Exception as e:
                    logger.debug(f"Error eliminando cache invalido: {e}")

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
        """Detecta que modelo de embeddings esta disponible.
        v3: Guarda el modelo detectado en cache para consistencia entre sesiones.
        """
        # Primero intentar cargar modelo de embeddings desde cache
        cached_embed = self._load_embed_model_cache()
        if cached_embed:
            # Verificar que el modelo cacheado siga instalado
            available_lower = [m.lower() for m in available]
            if any(cached_embed.lower() in al for al in available_lower):
                self.embed_model = cached_embed
                logger.info(f"Modelo de embeddings (desde cache): {cached_embed}")
                return
            else:
                logger.warning(f"Modelo de embeddings cacheado '{cached_embed}' ya no esta instalado. Detectando nuevo...")
        
        available_lower = [m.lower() for m in available]
        for candidate in EMBED_MODEL_CANDIDATES:
            for al in available_lower:
                if candidate in al:
                    self.embed_model = candidate
                    logger.info(f"Modelo de embeddings detectado: {candidate}")
                    # Guardar en cache para consistencia
                    self._save_embed_model_cache(candidate)
                    return
        self.embed_model = "nomic-embed-text"  # Default
        self._save_embed_model_cache(self.embed_model)

    def _load_embed_model_cache(self):
        """Carga el modelo de embeddings desde cache."""
        try:
            cache_file = os.path.join(LEARN_DIR, "embed_model_cache.json")
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("embed_model")
        except Exception as e:
            logger.debug(f"Error cargando cache de modelo de embeddings: {e}")
        return None

    def _save_embed_model_cache(self, model_name):
        """Guarda el modelo de embeddings en cache para consistencia."""
        try:
            cache_file = os.path.join(LEARN_DIR, "embed_model_cache.json")
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"embed_model": model_name, "saved_at": datetime.now().isoformat()}, f)
        except Exception as e:
            logger.debug(f"Error guardando cache de modelo de embeddings: {e}")

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
                except Exception as e:
                    logger.debug(f"Error verificando GPU con nvidia-smi: {e}")
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
        except Exception as e:
            logger.debug(f"Error cargando cache de conexion: {e}")
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
        except Exception as e:
            logger.debug(f"Error guardando cache de conexion: {e}")

    # ----------------------------------------------------------
    # GENERACION (sin streaming)
    # ----------------------------------------------------------

    def _get_timeout(self, model_name):
        """Timeout adaptativo segun tamano del modelo."""
        if any(x in (model_name or "").lower() for x in ["14b", "30b", "70b", "32b"]):
            return LLM_TIMEOUT_LARGE
        return LLM_TIMEOUT_SMALL

    def _detect_tool_calling_support_fast(self) -> bool | None:
        """Detecta soporte de tool calling por nombre del modelo (M8.2).
        
        Returns:
            True if model is known to support tools
            False if model is known NOT to support tools
            None if model is unknown (needs live check)
        """
        model = (self.model or "").lower()
        
        # Modelos conocidos con soporte nativo de function calling
        SUPPORTS_TOOLS = {
            "qwen3", "qwen2.5-coder", "mistral-nemo",
            "hermes", "llama3.1", "llama3.2", "phi3.5",
            "command-r", "firefunction", "qwen2.5"
        }
        
        # Modelos conocidos SIN soporte de function calling
        LACKS_TOOLS = {
            "gemma", "orca", "phi2", "codellama",
            "deepseek-coder:6.7b", "starcoder", "tinyllama"
        }
        
        for pattern in SUPPORTS_TOOLS:
            if pattern in model:
                return True
        
        for pattern in LACKS_TOOLS:
            if pattern in model:
                return False
        
        return None  # Unknown model - needs live check

    @timed("llm")
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

    @timed("llm")
    def generate_chat(self, messages):
        """Para conversacion: usa modelo rapido."""
        return self.generate(messages, model_override=self.chat_model)

    @timed("llm")
    def generate_code(self, messages):
        """Para codigo: usa modelo potente."""
        return self.generate(messages, model_override=self.code_model)

    # ----------------------------------------------------------
    # MULTIMODAL (vision - imagenes)
    # ----------------------------------------------------------

    def generate_with_image(self, text, image_path, model_override=None):
        """
        Genera respuesta del LLM con una imagen (multimodal/vision).
        Soporta modelos como llava, llama3.2-vision, etc.
        Retorna: str con la descripcion/respuesta sobre la imagen.
        """
        self.detect_models()
        
        # Buscar modelo con capacidad de vision
        vision_model = self._detect_vision_model()
        model = model_override or vision_model or self.model
        
        try:
            import base64
            import urllib.request
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            
            # Detectar tipo de imagen
            ext = image_path.lower().split(".")[-1]
            mime_type = {
                "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "gif": "image/gif",
                "webp": "image/webp",
            }.get(ext, "image/jpeg")

            messages = [{
                "role": "user",
                "content": text,
                "images": [image_data]
            }]

            # Intentar via HTTP
            for host in ['http://localhost:11434', 'http://127.0.0.1:11434']:
                try:
                    payload = {
                        "model": model,
                        "messages": messages,
                        "stream": False
                    }
                    data = json.dumps(payload).encode("utf-8")
                    req = urllib.request.Request(
                        f"{host}/api/chat",
                        data=data,
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_LARGE) as resp:
                        result = json.loads(resp.read().decode("utf-8"))
                        content = result.get("message", {}).get("content", "")
                        if content:
                            return content
                except Exception as e:
                    logger.debug(f"Vision HTTP failed on {host}: {e}")

            # Intentar via ollama client
            try:
                import ollama as ollama_lib
                client = ollama_lib.Client(host='http://localhost:11434')
                response = client.chat(
                    model=model,
                    messages=messages
                )
                return response.get("message", {}).get("content", "")
            except Exception as e:
                logger.debug(f"Vision client failed: {e}")

        except FileNotFoundError:
            return f"ERROR: Imagen no encontrada: {image_path}"
        except Exception as e:
            return f"ERROR en vision: {e}"

        return "No se pudo procesar la imagen. Puede que el modelo no soporte vision."

    def _detect_vision_model(self):
        """Detecta si hay un modelo de vision disponible."""
        available = self._fetch_available_models(refresh=False)
        # Modelos con capacidad de vision
        vision_patterns = ["llava", "llama3.2-vision", "minicpm-v", "bakllava", 
                          "moondream", "llama3.1:8b", "qwen2.5-coder"]
        for pattern in vision_patterns:
            for model in available:
                if pattern in model.lower():
                    return model
        return None

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

    def _try_method(self, host, method, model, messages, tools, timeout, think=None):
        """Intenta una combinacion de host/metodo/modelo. Retorna None si falla.

        Args:
            think: Si True, activa pensamiento nativo del modelo (qwen3, deepseek-r1).
                   Si None, se detecta automaticamente segun el modelo.
        """
        # Auto-detectar soporte de think nativo
        if think is None:
            try:
                from agent.deep_thinking import detect_native_thinking_support
                think = detect_native_thinking_support(model)
            except ImportError:
                think = False

        if method == 'client':
            return self._try_client(host, model, messages, tools, timeout, think=think)
        elif method == 'http':
            return self._try_http(host, model, messages, tools, timeout, think=think)
        return None

    def _try_client(self, host, model, messages, tools, timeout, think=False):
        """Intenta via ollama.Client. Soporta think nativo para modelos compatibles."""
        try:
            import ollama
            client = self._get_or_create_client(host)

            # Construir kwargs
            kwargs = {"model": model, "messages": messages}
            if tools:
                kwargs["tools"] = tools
            if think and not tools:
                # Think nativo: solo sin tools (Ollama no soporta ambos)
                kwargs["think"] = True

            response = client.chat(**kwargs)

            # Procesar respuesta con posible thinking
            msg = response.get("message", response)
            content = msg.get("content", "") if isinstance(msg, dict) else ""
            thinking_content = msg.get("thinking", "") if isinstance(msg, dict) else ""

            # Si hay thinking, guardarlo para referencia
            if thinking_content:
                self._last_thinking = thinking_content
                logger.debug(f"Native thinking: {len(thinking_content)} chars")

            if tools:
                if content or msg.get("tool_calls"):
                    return response
            else:
                if content:
                    return content
        except TypeError as e:
            # Si el client no soporta 'think', reintentar sin él
            if 'think' in str(e).lower():
                logger.debug("Cliente no soporta param 'think', reintentando sin él")
                try:
                    import ollama as ollama_lib
                    client = self._get_or_create_client(host)
                    if tools:
                        response = client.chat(model=model, messages=messages, tools=tools)
                    else:
                        response = client.chat(model=model, messages=messages)
                    msg = response.get("message", response)
                    content = msg.get("content", "") if isinstance(msg, dict) else ""
                    if tools:
                        if content or msg.get("tool_calls"):
                            return response
                    else:
                        if content:
                            return content
                except Exception as e2:
                    logger.debug(f"Retry sin think param fallo: {e2}")
        except Exception as e:
            logger.debug(f"Client method failed: {e}")
        return None

    def _try_http(self, host, model, messages, tools, timeout, think=False):
        """Intenta via HTTP directo (sin lib ollama). Soporta think nativo."""
        try:
            import urllib.request
            payload = {
                "model": model,
                "messages": messages,
                "stream": False
            }
            if tools:
                payload["tools"] = tools
            if think and not tools:
                # Think nativo via API de Ollama (v0.6+)
                payload["think"] = True

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{host}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))

                # Procesar thinking nativo si existe
                msg = result.get("message", result)
                thinking_content = msg.get("thinking", "") if isinstance(msg, dict) else ""
                if thinking_content:
                    self._last_thinking = thinking_content
                    logger.debug(f"Native thinking (HTTP): {len(thinking_content)} chars")

                if tools:
                    content = msg.get("content", "") if isinstance(msg, dict) else ""
                    if content or msg.get("tool_calls"):
                        return result
                else:
                    content = msg.get("content", "") if isinstance(msg, dict) else ""
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
            except Exception as e:
                logger.debug(f"Error creando ollama.Client: {e}")
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
            except Exception as e:
                logger.debug(f"Error escribiendo log de errores LLM: {e}")

    # ----------------------------------------------------------
    # EMBEDDINGS (con cache optimizado)
    # ----------------------------------------------------------

    def get_embedding(self, text):
        """Obtiene el embedding de un texto usando Ollama. Con cache LRU.
        v3: Retry con modelo alternativo si falla el principal.
        """
        import hashlib
        cache_key = hashlib.md5(text[:500].encode()).hexdigest()[:16]

        # Cache hit
        cached = embed_cache.get(cache_key)
        if cached is not None:
            return cached

        self.detect_models()
        
        # Intentar con el modelo principal de embeddings
        embedding = self._try_get_embedding(text, self.embed_model)
        if embedding:
            embed_cache.put(cache_key, embedding)
            get_metrics().record_embedding_call()
            return embedding
        
        # Fallback: intentar con otros modelos de embedding disponibles
        for fallback_model in EMBED_MODEL_CANDIDATES:
            if fallback_model == self.embed_model:
                continue
            embedding = self._try_get_embedding(text, fallback_model)
            if embedding:
                logger.warning(f"Embedding fallback exitoso con modelo: {fallback_model}")
                # Actualizar modelo de embeddings al que funciona
                self.embed_model = fallback_model
                self._save_embed_model_cache(fallback_model)
                embed_cache.put(cache_key, embedding)
                get_metrics().record_embedding_call()
                return embedding
        
        logger.warning("No se pudo obtener embedding con ningun modelo")
        get_metrics().record_error("embedding")
        return []

    def _try_get_embedding(self, text, model_name):
        """Intenta obtener embedding con un modelo especifico. Retorna [] si falla."""
        try:
            import urllib.request
            data = json.dumps({
                "model": model_name,
                "prompt": text[:2000]
            }).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:11434/api/embeddings",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=EMBED_TIMEOUT) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("embedding", [])
        except Exception as e:
            logger.debug(f"Embedding falló con modelo {model_name}: {e}")
            return []

    @staticmethod
    def cosine_similarity(vec1, vec2):
        """Calcula similitud coseno entre dos vectores.
        Usa numpy si esta disponible (10-50x mas rapido en batch).
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        try:
            import numpy as np
            a = np.array(vec1, dtype=np.float32)
            b = np.array(vec2, dtype=np.float32)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return float(np.dot(a, b) / (norm_a * norm_b))
        except ImportError:
            # Fallback: Python puro
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = sum(a * a for a in vec1) ** 0.5
            norm2 = sum(b * b for b in vec2) ** 0.5
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)

    @staticmethod
    def cosine_similarity_batch(query_vec, vectors_dict):
        """Calcula similitud coseno de un vector contra muchos vectores de una vez.
        
        Args:
            query_vec: Lista[float] - vector de consulta
            vectors_dict: Dict[id, Lista[float]] - diccionario de vectores
            
        Returns:
            Dict[id, float] - similitud de cada vector vs query
            
        Usa numpy para calculo vectorizado (10-50x mas rapido que bucle Python).
        Fallback a Python puro si numpy no esta disponible.
        """
        if not query_vec or not vectors_dict:
            return {}

        ids = list(vectors_dict.keys())
        vecs = list(vectors_dict.values())

        # Filtrar vectores de tamano incompatible
        valid_pairs = [(eid, v) for eid, v in zip(ids, vecs)
                       if v and len(v) == len(query_vec)]
        if not valid_pairs:
            return {}

        valid_ids, valid_vecs = zip(*valid_pairs)

        try:
            import numpy as np
            query = np.array(query_vec, dtype=np.float32)
            matrix = np.array(valid_vecs, dtype=np.float32)  # shape: (N, D)

            # Normalizar query
            query_norm = np.linalg.norm(query)
            if query_norm == 0:
                return {eid: 0.0 for eid in valid_ids}
            query_normalized = query / query_norm

            # Normalizar filas de la matriz
            row_norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            row_norms = np.where(row_norms == 0, 1.0, row_norms)  # Evitar div/0
            matrix_normalized = matrix / row_norms

            # Producto punto vectorizado: (D,) @ (N, D).T -> (N,)
            similarities = matrix_normalized @ query_normalized

            return {eid: float(sim) for eid, sim in zip(valid_ids, similarities)}

        except ImportError:
            # Fallback: Python puro (bucle)
            results = {}
            for eid, vec in valid_pairs:
                dot_product = sum(a * b for a, b in zip(query_vec, vec))
                norm1 = sum(a * a for a in query_vec) ** 0.5
                norm2 = sum(b * b for b in vec) ** 0.5
                if norm1 > 0 and norm2 > 0:
                    results[eid] = dot_product / (norm1 * norm2)
                else:
                    results[eid] = 0.0
            return results


# ============================================================
# INSTANCIA GLOBAL
# ============================================================
ollama = OllamaClient.get()
