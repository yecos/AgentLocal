"""
=============================================================
AGENTE v16 - Herramientas Cloud (APIs externas como fallback)
=============================================================
Provee acceso a APIs cloud cuando las herramientas locales fallan
o no estan disponibles:

- Busqueda web: Google Custom Search, Bing (fallback a DDG local)
- Generacion de imagenes: Replicate, Stability AI, OpenAI DALL-E
- LLM cloud: OpenAI, Anthropic, Google Gemini (fallback a Ollama local)
- Vision cloud: OpenAI Vision, Google Vision (fallback a Ollama VLM)

Configuracion: Las API keys se leen desde:
1. Variables de entorno (AGENTE_GOOGLE_KEY, AGENTE_OPENAI_KEY, etc.)
2. Archivo ~/.ia-local/api_keys.json

Si no hay API keys configuradas, se usa el fallback local automaticamente.
=============================================================
"""

import os
import json
import logging
import base64
import urllib.request
import urllib.parse
import urllib.error
from config import LEARN_DIR, logger


# ============================================================
# GESTION DE API KEYS
# ============================================================

_keys_cache = None

def _load_api_keys() -> dict:
    """Carga API keys desde env vars y archivo de configuracion."""
    global _keys_cache
    if _keys_cache is not None:
        return _keys_cache

    keys = {}

    # 1. Desde variables de entorno
    env_map = {
        "google": ["AGENTE_GOOGLE_KEY", "GOOGLE_API_KEY", "GCS_API_KEY"],
        "google_cx": ["AGENTE_GOOGLE_CX", "GOOGLE_CX", "GCS_CX"],
        "openai": ["AGENTE_OPENAI_KEY", "OPENAI_API_KEY"],
        "anthropic": ["AGENTE_ANTHROPIC_KEY", "ANTHROPIC_API_KEY"],
        "stability": ["AGENTE_STABILITY_KEY", "STABILITY_API_KEY"],
        "replicate": ["AGENTE_REPLICATE_KEY", "REPLICATE_API_TOKEN"],
        "huggingface": ["AGENTE_HF_KEY", "HUGGINGFACE_API_KEY", "HF_API_KEY"],
        "google_gemini": ["AGENTE_GEMINI_KEY", "GEMINI_API_KEY", "GOOGLE_GEMINI_KEY"],
    }

    for key_name, env_names in env_map.items():
        for env_name in env_names:
            val = os.environ.get(env_name, "").strip()
            if val:
                keys[key_name] = val
                break

    # 2. Desde archivo de configuracion
    keys_file = os.path.join(LEARN_DIR, "api_keys.json")
    if os.path.exists(keys_file):
        try:
            with open(keys_file, "r", encoding="utf-8") as f:
                file_keys = json.load(f)
                for k, v in file_keys.items():
                    if v and str(v).strip():
                        keys[k] = str(v).strip()
        except Exception as e:
            logger.debug(f"Error leyendo api_keys.json: {e}")

    _keys_cache = keys
    return keys


def get_api_key(service: str) -> str:
    """Obtiene la API key para un servicio. Retorna string vacio si no hay."""
    keys = _load_api_keys()
    return keys.get(service, "")


def configurar_api_key(servicio: str, clave: str) -> str:
    """Configura una API key para un servicio cloud.

    Args:
        servicio: Nombre del servicio: google, openai, anthropic, stability, replicate, huggingface, google_gemini
        clave: API key del servicio
    """
    global _keys_cache

    keys_file = os.path.join(LEARN_DIR, "api_keys.json")

    # Cargar existentes
    existing = {}
    if os.path.exists(keys_file):
        try:
            with open(keys_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    # Agregar/actualizar
    existing[servicio] = clave

    # Guardar
    try:
        os.makedirs(os.path.dirname(keys_file), exist_ok=True)
        with open(keys_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        logger.info(f"API key configurada para: {servicio}")
    except Exception as e:
        return f"ERROR guardando API key: {e}"

    # Invalidar cache
    _keys_cache = None

    return f"API key para '{servicio}' configurada correctamente."


def listar_api_keys() -> str:
    """Lista los servicios cloud con API keys configuradas."""
    keys = _load_api_keys()

    services = {
        "google": "Google Custom Search",
        "google_cx": "Google Custom Search CX",
        "openai": "OpenAI (GPT, DALL-E, Vision)",
        "anthropic": "Anthropic (Claude)",
        "stability": "Stability AI (Stable Diffusion)",
        "replicate": "Replicate (Modelos ML)",
        "huggingface": "Hugging Face",
        "google_gemini": "Google Gemini",
    }

    parts = ["Servicios cloud configurados:\n"]
    for key_name, label in services.items():
        has_key = key_name in keys and keys[key_name]
        status = "CONFIGURADO" if has_key else "no configurado"
        masked = keys.get(key_name, "")[:8] + "..." if has_key else ""
        parts.append(f"  {label}: {status} {masked}")

    parts.append("\nPara configurar: configurar_api_key('openai', 'sk-...')")
    parts.append("O define variables de entorno: AGENTE_OPENAI_KEY, AGENTE_GOOGLE_KEY, etc.")

    return "\n".join(parts)


# ============================================================
# BUSQUEDA WEB CLOUD
# ============================================================

def buscar_web_cloud(consulta: str, num_resultados: int = 8) -> str | None:
    """Busca en internet usando APIs cloud (Google Custom Search).
    Retorna None si no hay API keys configuradas.

    Args:
        consulta: Texto de busqueda
        num_resultados: Numero de resultados (max 10)
    """
    api_key = get_api_key("google")
    cx = get_api_key("google_cx")

    if not api_key or not cx:
        return None

    try:
        encoded = urllib.parse.quote(consulta)
        url = (
            f"https://www.googleapis.com/customsearch/v1?"
            f"key={api_key}&cx={cx}&q={encoded}&num={min(num_resultados, 10)}"
        )

        req = urllib.request.Request(url, headers={"User-Agent": "AgenteLocal/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        items = data.get("items", [])
        if not items:
            return None

        results = ["Resultados web (Google):"]
        for i, item in enumerate(items):
            title = item.get("title", "").strip()
            link = item.get("link", "")
            snippet = item.get("snippet", "").strip()

            results.append(f"{i+1}. {title}")
            if snippet:
                results.append(f"   {snippet}")
            if link:
                results.append(f"   {link}")

        return "\n".join(results)

    except urllib.error.HTTPError as e:
        logger.debug(f"Google Search API error: {e.code} {e.reason}")
        return None
    except Exception as e:
        logger.debug(f"Google Search fallo: {e}")
        return None


# ============================================================
# GENERACION DE IMAGENES CLOUD
# ============================================================

def generar_imagen_cloud(descripcion: str, ruta: str = "",
                         tamano: str = "1024x1024") -> str | None:
    """Genera una imagen usando APIs cloud (OpenAI DALL-E, Stability AI, Replicate).
    Retorna None si no hay API keys o falla.

    Args:
        descripcion: Descripcion de la imagen a generar
        ruta: Ruta donde guardar la imagen (opcional)
        tamano: Tamano de la imagen
    """
    # Intentar con OpenAI DALL-E
    result = _generate_dalle(descripcion, ruta, tamano)
    if result is not None:
        return result

    # Intentar con Stability AI
    result = _generate_stability(descripcion, ruta, tamano)
    if result is not None:
        return result

    # Intentar con Replicate
    result = _generate_replicate(descripcion, ruta, tamano)
    if result is not None:
        return result

    # Intentar con Hugging Face
    result = _generate_huggingface(descripcion, ruta, tamano)
    if result is not None:
        return result

    return None


def _generate_dalle(descripcion: str, ruta: str, tamano: str) -> str | None:
    """Genera imagen con OpenAI DALL-E API."""
    api_key = get_api_key("openai")
    if not api_key:
        return None

    try:
        # Validar tamano
        valid_sizes = ["1024x1024", "1792x1024", "1024x1792"]
        size = tamano if tamano in valid_sizes else "1024x1024"

        payload = json.dumps({
            "model": "dall-e-3",
            "prompt": descripcion,
            "n": 1,
            "size": size,
            "quality": "standard",
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.openai.com/v1/images/generations",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        image_url = data.get("data", [{}])[0].get("url", "")
        revised_prompt = data.get("data", [{}])[0].get("revised_prompt", "")

        if not image_url:
            return None

        # Descargar imagen
        if not ruta:
            import time
            ruta = os.path.join(LEARN_DIR, f"generated_{int(time.time())}.png")

        _download_image(image_url, ruta)

        result = f"Imagen generada (DALL-E 3): {ruta}"
        if revised_prompt:
            result += f"\nPrompt refinado: {revised_prompt}"
        return result

    except urllib.error.HTTPError as e:
        logger.debug(f"DALL-E API error: {e.code}")
        return None
    except Exception as e:
        logger.debug(f"DALL-E fallo: {e}")
        return None


def _generate_stability(descripcion: str, ruta: str, tamano: str) -> str | None:
    """Genera imagen con Stability AI API."""
    api_key = get_api_key("stability")
    if not api_key:
        return None

    try:
        width, height = tamano.split("x") if "x" in tamano else ("1024", "1024")
        width = min(int(width), 1024)
        height = min(int(height), 1024)

        payload = json.dumps({
            "text_prompts": [{"text": descripcion, "weight": 1}],
            "cfg_scale": 7,
            "height": height,
            "width": width,
            "samples": 1,
            "steps": 30,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        base64_image = data.get("artifacts", [{}])[0].get("base64", "")
        if not base64_image:
            return None

        if not ruta:
            import time
            ruta = os.path.join(LEARN_DIR, f"generated_{int(time.time())}.png")

        with open(ruta, "wb") as f:
            f.write(base64.b64decode(base64_image))

        return f"Imagen generada (Stability AI SDXL): {ruta}"

    except urllib.error.HTTPError as e:
        logger.debug(f"Stability API error: {e.code}")
        return None
    except Exception as e:
        logger.debug(f"Stability fallo: {e}")
        return None


def _generate_replicate(descripcion: str, ruta: str, tamano: str) -> str | None:
    """Genera imagen con Replicate API."""
    api_key = get_api_key("replicate")
    if not api_key:
        return None

    try:
        payload = json.dumps({
            "version": "39ed52f2a78e934b3ba6e2a89f5b1c712de7d5c6e1e6c155e7d6e8e8e8e8e8e8",
            "input": {
                "prompt": descripcion,
                "width": int(tamano.split("x")[0]) if "x" in tamano else 1024,
                "height": int(tamano.split("x")[1]) if "x" in tamano else 1024,
            }
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.replicate.com/v1/predictions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Token {api_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Replicate es async - obtener resultado
        get_url = data.get("urls", {}).get("get", "")
        if not get_url:
            return None

        # Polling por resultado (max 60s)
        for _ in range(12):
            import time
            time.sleep(5)

            req = urllib.request.Request(get_url, headers={
                "Authorization": f"Token {api_key}",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                result_data = json.loads(resp.read().decode("utf-8"))

            if result_data.get("status") == "succeeded":
                output = result_data.get("output", [])
                if output:
                    image_url = output[0] if isinstance(output, list) else output
                    if not ruta:
                        ruta = os.path.join(LEARN_DIR, f"generated_{int(time.time())}.png")
                    _download_image(image_url, ruta)
                    return f"Imagen generada (Replicate SDXL): {ruta}"
            elif result_data.get("status") == "failed":
                return None

        return None

    except Exception as e:
        logger.debug(f"Replicate fallo: {e}")
        return None


def _generate_huggingface(descripcion: str, ruta: str, tamano: str) -> str | None:
    """Genera imagen con Hugging Face Inference API."""
    api_key = get_api_key("huggingface")
    if not api_key:
        return None

    try:
        payload = json.dumps({
            "inputs": descripcion,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=90) as resp:
            image_data = resp.read()

        if not image_data or len(image_data) < 100:
            return None

        if not ruta:
            import time
            ruta = os.path.join(LEARN_DIR, f"generated_{int(time.time())}.png")

        with open(ruta, "wb") as f:
            f.write(image_data)

        return f"Imagen generada (HuggingFace SDXL): {ruta}"

    except urllib.error.HTTPError as e:
        logger.debug(f"HuggingFace API error: {e.code}")
        return None
    except Exception as e:
        logger.debug(f"HuggingFace fallo: {e}")
        return None


# ============================================================
# LLM CLOUD
# ============================================================

def llm_cloud_chat(mensajes: list, modelo: str = "auto",
                   temperatura: float = 0.7, max_tokens: int = 2048) -> str | None:
    """Chat con LLM cloud (OpenAI, Anthropic, Gemini).
    Retorna None si no hay API keys.

    Args:
        mensajes: Lista de mensajes [{"role": "user", "content": "..."}]
        modelo: Modelo a usar: auto, gpt-4, gpt-3.5, claude, gemini
        temperatura: Temperatura de generacion
        max_tokens: Max tokens de respuesta
    """
    # Intentar OpenAI
    if modelo in ("auto", "gpt-4", "gpt-4o", "gpt-3.5", "gpt-3.5-turbo"):
        result = _chat_openai(mensajes, modelo, temperatura, max_tokens)
        if result is not None:
            return result

    # Intentar Anthropic
    if modelo in ("auto", "claude", "claude-3", "claude-3.5"):
        result = _chat_anthropic(mensajes, modelo, temperatura, max_tokens)
        if result is not None:
            return result

    # Intentar Gemini
    if modelo in ("auto", "gemini", "gemini-pro", "gemini-1.5"):
        result = _chat_gemini(mensajes, modelo, temperatura, max_tokens)
        if result is not None:
            return result

    return None


def _chat_openai(mensajes: list, modelo: str, temperatura: float, max_tokens: int) -> str | None:
    """Chat con OpenAI API."""
    api_key = get_api_key("openai")
    if not api_key:
        return None

    try:
        model_map = {
            "auto": "gpt-4o-mini",
            "gpt-4": "gpt-4o",
            "gpt-4o": "gpt-4o",
            "gpt-3.5": "gpt-4o-mini",
            "gpt-3.5-turbo": "gpt-4o-mini",
        }
        model = model_map.get(modelo, "gpt-4o-mini")

        payload = json.dumps({
            "model": model,
            "messages": mensajes,
            "temperature": temperatura,
            "max_tokens": max_tokens,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if content:
            return content

    except urllib.error.HTTPError as e:
        logger.debug(f"OpenAI API error: {e.code}")
    except Exception as e:
        logger.debug(f"OpenAI fallo: {e}")

    return None


def _chat_anthropic(mensajes: list, modelo: str, temperatura: float, max_tokens: int) -> str | None:
    """Chat con Anthropic Claude API."""
    api_key = get_api_key("anthropic")
    if not api_key:
        return None

    try:
        # Separar system prompt de mensajes
        system_content = ""
        chat_messages = []
        for msg in mensajes:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                chat_messages.append(msg)

        payload = json.dumps({
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": max_tokens,
            "temperature": temperatura,
            "system": system_content,
            "messages": chat_messages,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        content = data.get("content", [{}])[0].get("text", "")
        if content:
            return content

    except urllib.error.HTTPError as e:
        logger.debug(f"Anthropic API error: {e.code}")
    except Exception as e:
        logger.debug(f"Anthropic fallo: {e}")

    return None


def _chat_gemini(mensajes: list, modelo: str, temperatura: float, max_tokens: int) -> str | None:
    """Chat con Google Gemini API."""
    api_key = get_api_key("google_gemini")
    if not api_key:
        return None

    try:
        # Convertir mensajes a formato Gemini
        contents = []
        for msg in mensajes:
            if msg.get("role") == "system":
                continue  # Gemini maneja system en generationConfig
            role = "user" if msg.get("role") in ("user", "tool") else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}]
            })

        payload = json.dumps({
            "contents": contents,
            "generationConfig": {
                "temperature": temperatura,
                "maxOutputTokens": max_tokens,
            }
        }).encode("utf-8")

        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if text:
            return text

    except urllib.error.HTTPError as e:
        logger.debug(f"Gemini API error: {e.code}")
    except Exception as e:
        logger.debug(f"Gemini fallo: {e}")

    return None


# ============================================================
# VISION CLOUD
# ============================================================

def analizar_imagen_cloud(ruta: str, pregunta: str = "Describe esta imagen") -> str | None:
    """Analiza una imagen usando APIs cloud (OpenAI Vision, Gemini).
    Retorna None si no hay API keys.

    Args:
        ruta: Ruta de la imagen a analizar
        pregunta: Pregunta sobre la imagen
    """
    # Leer y codificar imagen
    try:
        with open(ruta, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.debug(f"Error leyendo imagen: {e}")
        return None

    # Detectar formato
    ext = ruta.lower().split(".")[-1]
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp"}
    mime = mime_map.get(ext, "image/png")

    # Intentar OpenAI Vision
    result = _vision_openai(image_data, mime, pregunta)
    if result is not None:
        return result

    # Intentar Gemini Vision
    result = _vision_gemini(image_data, mime, pregunta)
    if result is not None:
        return result

    return None


def _vision_openai(image_data: str, mime: str, pregunta: str) -> str | None:
    """Analiza imagen con OpenAI Vision API."""
    api_key = get_api_key("openai")
    if not api_key:
        return None

    try:
        payload = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": pregunta},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime};base64,{image_data}"
                    }},
                ]
            }],
            "max_tokens": 1024,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if content:
            return f"Vision AI (GPT-4o): {content}"

    except Exception as e:
        logger.debug(f"OpenAI Vision fallo: {e}")

    return None


def _vision_gemini(image_data: str, mime: str, pregunta: str) -> str | None:
    """Analiza imagen con Google Gemini Vision API."""
    api_key = get_api_key("google_gemini")
    if not api_key:
        return None

    try:
        payload = json.dumps({
            "contents": [{
                "parts": [
                    {"text": pregunta},
                    {"inline_data": {"mime_type": mime, "data": image_data}},
                ]
            }],
        }).encode("utf-8")

        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if text:
            return f"Vision AI (Gemini): {text}"

    except Exception as e:
        logger.debug(f"Gemini Vision fallo: {e}")

    return None


# ============================================================
# UTILIDADES
# ============================================================

def _download_image(url: str, ruta: str) -> bool:
    """Descarga una imagen desde URL y la guarda en ruta."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            image_data = resp.read()

        os.makedirs(os.path.dirname(ruta) if os.path.dirname(ruta) else ".", exist_ok=True)
        with open(ruta, "wb") as f:
            f.write(image_data)

        return True

    except Exception as e:
        logger.debug(f"Error descargando imagen: {e}")
        return False
