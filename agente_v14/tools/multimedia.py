"""
=============================================================
AGENTE v15 - Herramientas Multimedia
=============================================================
Text-to-Speech (TTS):
- Sintesis de voz desde texto usando modelos locales o APIs

Generacion de imagenes:
- Generacion de imagenes desde texto (Stable Diffusion via Ollama,
  DALL-E via API, etc.)

Edicion de imagenes:
- Redimensionar, recortar, convertir formatos, ajustes basicos

Comprension de video:
- Extraccion de frames, analisis de video con VLM

Busqueda de imagenes:
- Busqueda de imagenes en la web (DuckDuckGo, Unsplash)

Dependencias opcionales: Pillow, edge-tts, stable-diffusion
=============================================================
"""

import os
import json
import logging
import shlex
import subprocess
import tempfile
from config import REPOS_DIR, LEARN_DIR, MAX_TOOL_OUTPUT, logger
from utils.security import validate_path, sanitize_input


# ============================================================
# TEXT-TO-SPEECH (TTS)
# ============================================================

def texto_a_voz(texto: str, ruta: str = "", voz: str = "es",
                velocidad: float = 1.0, formato: str = "mp3") -> str:
    """Convierte texto a voz (TTS). Genera un archivo de audio con el texto hablado.

    Args:
        texto: Texto a convertir a voz
        ruta: Ruta donde guardar el audio (si vacio, genera automatica)
        voz: Idioma/voz: es, en, fr, de, pt, it, ja, ko, zh o nombre especifico
        velocidad: Velocidad de habla (0.5=lenta, 1.0=normal, 2.0=rapida)
        formato: Formato de salida: mp3, wav
    """
    if not texto:
        return "ERROR: No se proporciono texto para convertir a voz."

    # Generar ruta si no se especifica
    if not ruta:
        import time
        ext = f".{formato}" if formato in ("mp3", "wav") else ".mp3"
        ruta = os.path.join(LEARN_DIR, f"tts_{int(time.time())}{ext}")

    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    dir_name = os.path.dirname(ruta)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    # Intentar edge-tts (Microsoft Edge TTS, gratis, alta calidad)
    result = _tts_edge(texto, ruta, voz, velocidad)
    if result is not None:
        return result

    # Intentar pyttsx3 (offline, usa voces del sistema)
    result = _tts_pyttsx3(texto, ruta, voz, velocidad)
    if result is not None:
        return result

    # Intentar gTTS (Google TTS, requiere internet)
    result = _tts_gtts(texto, ruta, voz)
    if result is not None:
        return result

    # Intentar espeak (comando del sistema Linux)
    result = _tts_espeak(texto, ruta, voz, velocidad)
    if result is not None:
        return result

    return ("ERROR: No se pudo generar audio TTS. Instala una opcion:\n"
            "  pip install edge-tts    (recomendado, alta calidad, gratis)\n"
            "  pip install pyttsx3     (offline, usa voces del sistema)\n"
            "  pip install gTTS        (Google TTS, requiere internet)\n"
            "  sudo apt install espeak (Linux, comando del sistema)")


def _tts_edge(texto, ruta, voz, velocidad):
    """TTS con edge-tts (Microsoft Edge, gratis, alta calidad)."""
    try:
        import asyncio

        # Mapear idioma a voz de Edge
        voice_map = {
            "es": "es-ES-ElviraNeural",
            "es-MX": "es-MX-DaliaNeural",
            "en": "en-US-AriaNeural",
            "en-GB": "en-GB-SoniaNeural",
            "fr": "fr-FR-DeniseNeural",
            "de": "de-DE-KatjaNeural",
            "pt": "pt-BR-FranciscaNeural",
            "it": "it-IT-ElsaNeural",
            "ja": "ja-JP-NanamiNeural",
            "ko": "ko-KR-SunHiNeural",
            "zh": "zh-CN-XiaoxiaoNeural",
            "ru": "ru-RU-SvetlanaNeural",
        }

        voice_name = voice_map.get(voz, voz)
        # Si es solo un codigo de 2 letras, usar el mapeo
        if len(voz) == 2 and voz in voice_map:
            voice_name = voice_map[voz]

        rate = f"{'+'
                       if velocidad >= 1.0 else ''}{int((velocidad - 1.0) * 100)}%"

        try:
            import edge_tts
        except ImportError:
            return None

        async def _generate():
            communicate = edge_tts.Communicate(texto, voice_name, rate=rate)
            await communicate.save(ruta)

        # Ejecutar async
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(lambda: asyncio.run(_generate())).result()
            else:
                loop.run_until_complete(_generate())
        except RuntimeError:
            asyncio.run(_generate())

        if os.path.exists(ruta) and os.path.getsize(ruta) > 0:
            size_kb = os.path.getsize(ruta) / 1024
            return f"Audio TTS creado: {ruta} ({size_kb:.0f} KB, voz: {voice_name})"

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"edge-tts fallo: {e}")
        return f"ERROR TTS con edge-tts: {e}"


def _tts_pyttsx3(texto, ruta, voz, velocidad):
    """TTS con pyttsx3 (offline, voces del sistema)."""
    try:
        import pyttsx3

        engine = pyttsx3.init()

        # Configurar velocidad
        rate = engine.getProperty('rate')
        engine.setProperty('rate', int(rate * velocidad))

        # Buscar voz en el idioma deseado
        voices = engine.getProperty('voices')
        for v in voices:
            if voz.lower() in v.id.lower() or voz.lower() in v.name.lower():
                engine.setProperty('voice', v.id)
                break

        # Guardar
        engine.save_to_file(texto, ruta)
        engine.runAndWait()

        if os.path.exists(ruta) and os.path.getsize(ruta) > 0:
            size_kb = os.path.getsize(ruta) / 1024
            return f"Audio TTS creado: {ruta} ({size_kb:.0f} KB, pyttsx3)"

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"pyttsx3 fallo: {e}")
        return f"ERROR TTS con pyttsx3: {e}"


def _tts_gtts(texto, ruta, voz):
    """TTS con gTTS (Google Text-to-Speech, requiere internet)."""
    try:
        from gtts import gTTS

        # Mapear idioma
        lang_map = {
            "es": "es", "en": "en", "fr": "fr", "de": "de",
            "pt": "pt", "it": "it", "ja": "ja", "ko": "ko",
            "zh": "zh-CN", "ru": "ru",
        }
        lang = lang_map.get(voz, voz if len(voz) == 2 else "es")

        tts = gTTS(text=texto, lang=lang)
        tts.save(ruta)

        if os.path.exists(ruta) and os.path.getsize(ruta) > 0:
            size_kb = os.path.getsize(ruta) / 1024
            return f"Audio TTS creado: {ruta} ({size_kb:.0f} KB, gTTS, idioma: {lang})"

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"gTTS fallo: {e}")
        return f"ERROR TTS con gTTS: {e}"


def _tts_espeak(texto, ruta, voz, velocidad):
    """TTS con espeak (comando del sistema Linux)."""
    try:
        speed = int(160 * velocidad)
        cmd = ["espeak", "-v", voz, "-s", str(speed), "-w", ruta, texto[:500]]
        result = subprocess.run(cmd, capture_output=True, timeout=30)

        if result.returncode == 0 and os.path.exists(ruta):
            size_kb = os.path.getsize(ruta) / 1024
            return f"Audio TTS creado: {ruta} ({size_kb:.0f} KB, espeak)"

    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as e:
        logger.debug(f"espeak fallo: {e}")

    return None


# ============================================================
# GENERACION DE IMAGENES
# ============================================================

def generar_imagen(descripcion: str, ruta: str = "", tamano: str = "512x512",
                   estilo: str = "", negativo: str = "") -> str:
    """Genera una imagen a partir de una descripcion de texto usando IA.
    Usa modelos locales de Ollama (stable-diffusion, etc.) o APIs.

    Args:
        descripcion: Descripcion de la imagen a generar (prompt)
        ruta: Ruta donde guardar la imagen (si vacio, genera automatica)
        tamano: Tamano de la imagen: 256x256, 512x512, 768x768
        estilo: Estilo adicional (ej: "realista", "anime", "pintura")
        negativo: Prompt negativo (que NO incluir)
    """
    if not descripcion:
        return "ERROR: No se proporciono descripcion para generar imagen."

    # Generar ruta si no se especifica
    if not ruta:
        import time
        ruta = os.path.join(LEARN_DIR, f"generated_{int(time.time())}.png")

    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    dir_name = os.path.dirname(ruta)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    # Construir prompt completo
    full_prompt = descripcion
    if estilo:
        full_prompt += f", {estilo} style"

    # Intentar con APIs cloud (DALL-E, Stability, Replicate, HuggingFace)
    result = _gen_cloud(full_prompt, ruta, tamano)
    if result is not None:
        return result

    # Intentar con Ollama (stable-diffusion)
    result = _gen_ollama_sd(full_prompt, ruta, tamano, negativo)
    if result is not None:
        return result

    # Intentar con Stable Diffusion WebUI API
    result = _gen_sd_webui(full_prompt, ruta, tamano, negativo)
    if result is not None:
        return result

    # Intentar con ComfyUI API
    result = _gen_comfyui(full_prompt, ruta, tamano, negativo)
    if result is not None:
        return result

    return ("ERROR: No se pudo generar imagen. Opciones:\n"
            "  1. Configura una API key: configurar_api_key('openai', 'sk-...')\n"
            "  2. Ollama + modelo de imagen: ollama pull stable-diffusion\n"
            "  3. Automatic1111 WebUI: https://github.com/AUTOMATIC1111/stable-diffusion-webui\n"
            "  4. ComfyUI: https://github.com/comfyanonymous/ComfyUI")


def _gen_cloud(prompt, ruta, tamano):
    """Genera imagen usando APIs cloud (DALL-E, Stability, Replicate, HF)."""
    try:
        from tools.cloud import generar_imagen_cloud
        result = generar_imagen_cloud(prompt, ruta, tamano)
        return result
    except Exception as e:
        logger.debug(f"Cloud image generation fallo: {e}")
        return None


def _gen_ollama_sd(prompt, ruta, tamano, negativo):
    """Genera imagen con modelo de Ollama (si hay modelo de imagen instalado)."""
    try:
        import urllib.request
        import json

        # Verificar modelos disponibles
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as resp:
                models = json.loads(resp.read()).get("models", [])
                image_models = [m["name"] for m in models
                                if any(kw in m["name"].lower()
                                       for kw in ["stable", "diffusion", "flux", "image"])]
        except Exception:
            image_models = []

        if not image_models:
            return None

        model = image_models[0]
        logger.info(f"Generando imagen con Ollama modelo: {model}")

        # Generar via API
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "negative_prompt": negativo,
        }).encode('utf-8')

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            response = json.loads(resp.read())

        # Las imagenes de Ollama vienen en base64
        import base64
        img_data = response.get("images", [])
        if img_data:
            with open(ruta, 'wb') as f:
                f.write(base64.b64decode(img_data[0]))

            if os.path.exists(ruta):
                size_kb = os.path.getsize(ruta) / 1024
                return f"Imagen generada: {ruta} ({size_kb:.0f} KB, modelo: {model})"

    except Exception as e:
        logger.debug(f"Ollama SD fallo: {e}")

    return None


def _gen_sd_webui(prompt, ruta, tamano, negativo):
    """Genera imagen con Automatic1111 Stable Diffusion WebUI API."""
    try:
        import urllib.request
        import base64

        width, height = tamano.split("x")
        width, height = int(width), int(height)

        payload = json.dumps({
            "prompt": prompt,
            "negative_prompt": negativo,
            "width": width,
            "height": height,
            "steps": 20,
            "cfg_scale": 7,
        }).encode('utf-8')

        req = urllib.request.Request(
            "http://127.0.0.1:7860/sdapi/v1/txt2img",
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            response = json.loads(resp.read())

        images = response.get("images", [])
        if images:
            with open(ruta, 'wb') as f:
                f.write(base64.b64decode(images[0]))

            if os.path.exists(ruta):
                size_kb = os.path.getsize(ruta) / 1024
                return f"Imagen generada: {ruta} ({size_kb:.0f} KB, SD WebUI)"

    except Exception as e:
        logger.debug(f"SD WebUI fallo: {e}")

    return None


def _gen_comfyui(prompt, ruta, tamano, negativo):
    """Genera imagen con ComfyUI API (placeholder)."""
    # ComfyUI requiere un workflow JSON complejo, se implementa como placeholder
    return None


# ============================================================
# EDICION DE IMAGENES
# ============================================================

def editar_imagen(ruta_entrada: str, accion: str = "info",
                  parametros: str = "{}", ruta_salida: str = "") -> str:
    """Edita una imagen: redimensionar, recortar, convertir formato, rotar, ajustes.

    Args:
        ruta_entrada: Ruta de la imagen de entrada
        accion: Accion: info, redimensionar, recortar, rotar, convertir, espejo, grayscale, ajustar
        parametros: Parametros en JSON segun la accion
        ruta_salida: Ruta de salida (si vacio, sobreescribe)
    """
    validation = validate_path(ruta_entrada)
    if validation != ruta_entrada:
        return validation

    if not os.path.exists(ruta_entrada):
        return f"ERROR: Archivo no encontrado: {ruta_entrada}"

    try:
        from PIL import Image, ImageEnhance, ImageFilter

        img = Image.open(ruta_entrada)
        params = _parse_json(parametros, {})
        salida = ruta_salida or ruta_entrada

        if accion == "info":
            return (f"Imagen: {ruta_entrada}\n"
                    f"  Formato: {img.format}\n"
                    f"  Tamano: {img.size[0]}x{img.size[1]}\n"
                    f"  Modo: {img.mode}\n"
                    f"  Archivo: {os.path.getsize(ruta_entrada)/1024:.0f} KB")

        elif accion == "redimensionar" or accion == "resize":
            ancho = params.get("ancho", params.get("width"))
            alto = params.get("alto", params.get("height"))
            mantener = params.get("mantener_proporcion", params.get("keep_aspect", True))

            if not ancho and not alto:
                return "ERROR: Especifica ancho y/o alto."

            if mantener and ancho and alto:
                img.thumbnail((ancho, alto), Image.Resampling.LANCZOS)
            else:
                if ancho and alto:
                    img = img.resize((ancho, alto), Image.Resampling.LANCZOS)
                elif ancho:
                    ratio = ancho / img.width
                    img = img.resize((ancho, int(img.height * ratio)), Image.Resampling.LANCZOS)
                elif alto:
                    ratio = alto / img.height
                    img = img.resize((int(img.width * ratio), alto), Image.Resampling.LANCZOS)

        elif accion == "recortar" or accion == "crop":
            left = params.get("left", params.get("izquierda", 0))
            top = params.get("top", params.get("arriba", 0))
            right = params.get("right", params.get("derecha", img.width))
            bottom = params.get("bottom", params.get("abajo", img.height))
            img = img.crop((left, top, right, bottom))

        elif accion == "rotar" or accion == "rotate":
            angulo = params.get("angulo", params.get("angle", 90))
            expand = params.get("expand", True)
            img = img.rotate(angulo, expand=expand)

        elif accion == "convertir" or accion == "convert":
            fmt = params.get("formato", params.get("format", "PNG")).upper()
            if not salida.endswith(f".{fmt.lower()}"):
                salida = salida.rsplit('.', 1)[0] + f".{fmt.lower()}"
            img.save(salida, format=fmt)
            size_kb = os.path.getsize(salida) / 1024
            return f"Imagen convertida: {salida} ({size_kb:.0f} KB, formato: {fmt})"

        elif accion == "espejo" or accion == "flip":
            direccion = params.get("direccion", params.get("direction", "horizontal"))
            if direccion == "vertical":
                img = img.transpose(Image.FLIP_TOP_BOTTOM)
            else:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)

        elif accion == "grayscale" or accion == "grises":
            img = img.convert('L')

        elif accion == "ajustar":
            brillo = params.get("brillo", params.get("brightness", 1.0))
            contraste = params.get("contraste", params.get("contrast", 1.0))
            saturacion = params.get("saturacion", params.get("saturation", 1.0))
            nitidez = params.get("nitidez", params.get("sharpness", 1.0))

            if brillo != 1.0:
                img = ImageEnhance.Brightness(img).enhance(brillo)
            if contraste != 1.0:
                img = ImageEnhance.Contrast(img).enhance(contraste)
            if saturacion != 1.0:
                img = ImageEnhance.Color(img).enhance(saturacion)
            if nitidez != 1.0:
                img = ImageEnhance.Sharpness(img).enhance(nitidez)

        else:
            return (f"ERROR: Accion '{accion}' no reconocida.\n"
                    "Usar: info, redimensionar, recortar, rotar, convertir, espejo, grayscale, ajustar")

        # Guardar
        img.save(salida)
        size_kb = os.path.getsize(salida) / 1024
        return f"Imagen editada [{accion}]: {salida} ({size_kb:.0f} KB, {img.size[0]}x{img.size[1]})"

    except ImportError:
        return "ERROR: Pillow no instalado. Instala: pip install Pillow"
    except Exception as e:
        return f"ERROR editando imagen: {e}"


# ============================================================
# BUSQUEDA DE IMAGENES
# ============================================================

def buscar_imagenes(consulta: str, cantidad: int = 5) -> str:
    """Busca imagenes en internet a partir de una consulta de texto.

    Args:
        consulta: Texto de busqueda
        cantidad: Cantidad de imagenes a buscar (max 10)
    """
    consulta = sanitize_input(consulta)
    cantidad = min(max(cantidad, 1), 10)

    # Intentar con DuckDuckGo
    result = _search_images_ddg(consulta, cantidad)
    if result:
        return result

    return "ERROR: No se pudieron buscar imagenes. Verifica la conexion a internet."


def _search_images_ddg(consulta, cantidad):
    """Busca imagenes via DuckDuckGo."""
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.images(consulta, max_results=cantidad))

        if not results:
            return "No se encontraron imagenes."

        parts = [f"Imagenes para: {consulta} ({len(results)} resultados)\n"]
        for i, r in enumerate(results):
            title = r.get("title", "")
            url = r.get("image", r.get("url", ""))
            source = r.get("source", "")
            size = r.get("width", "?")
            height = r.get("height", "?")

            parts.append(f"{i+1}. {title}")
            parts.append(f"   URL: {url}")
            parts.append(f"   Fuente: {source} | Tamano: {size}x{height}")

        return "\n".join(parts)

    except ImportError:
        # Fallback: scraping basico
        return _search_images_fallback(consulta, cantidad)
    except Exception as e:
        logger.debug(f"DDG image search fallo: {e}")
        return None


def _search_images_fallback(consulta, cantidad):
    """Fallback: busca imagenes via Unsplash API (sin key)."""
    try:
        import urllib.request
        import urllib.parse

        encoded = urllib.parse.quote(consulta)
        url = f"https://unsplash.com/napi/search/photos?query={encoded}&per_page={cantidad}"

        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        results = data.get("results", [])
        if not results:
            return "No se encontraron imagenes."

        parts = [f"Imagenes para: {consulta} ({len(results)} resultados)\n"]
        for i, r in enumerate(results):
            desc = r.get("description") or r.get("alt_description") or "Sin descripcion"
            img_url = r.get("urls", {}).get("regular", "")
            user = r.get("user", {}).get("name", "Unknown")

            parts.append(f"{i+1}. {desc[:80]}")
            parts.append(f"   URL: {img_url}")
            parts.append(f"   Autor: {user}")

        return "\n".join(parts)

    except Exception as e:
        logger.debug(f"Unsplash search fallo: {e}")
        return None


# ============================================================
# COMPrension DE VIDEO
# ============================================================

def analizar_video(ruta: str, accion: str = "info",
                   parametros: str = "{}") -> str:
    """Analiza un archivo de video: extraer informacion, frames, o analizar con VLM.

    Args:
        ruta: Ruta del archivo de video
        accion: Accion: info, frames, analizar, transcribir
        parametros: Parametros extra en JSON
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    if not os.path.exists(ruta):
        return f"ERROR: Archivo no encontrado: {ruta}"

    params = _parse_json(parametros, {})

    if accion == "info":
        return _video_info(ruta)
    elif accion == "frames":
        return _video_extract_frames(ruta, params)
    elif accion == "analizar":
        return _video_analyze_with_vlm(ruta, params)
    elif accion == "transcribir":
        return _video_transcribe(ruta, params)
    else:
        return (f"ERROR: Accion '{accion}' no reconocida.\n"
                "Usar: info, frames, analizar, transcribir")


def _video_info(ruta):
    """Extrae informacion del video usando ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json',
             '-show_format', '-show_streams', ruta],
            capture_output=True, text=True, timeout=15
        )

        if result.returncode != 0:
            return f"ERROR: ffprobe fallo. Asegurate de tener ffmpeg instalado."

        data = json.loads(result.stdout)
        format_info = data.get("format", {})
        streams = data.get("streams", [])

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        parts = [f"Video: {ruta}"]
        parts.append(f"  Duracion: {float(format_info.get('duration', 0)):.1f}s")
        parts.append(f"  Tamano: {int(format_info.get('size', 0))/1024/1024:.1f} MB")
        parts.append(f"  Formato: {format_info.get('format_name', 'unknown')}")

        if video_stream:
            parts.append(f"  Video: {video_stream.get('codec_name', '?')} "
                         f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')} "
                         f"@ {video_stream.get('r_frame_rate', '?')} fps")

        if audio_stream:
            parts.append(f"  Audio: {audio_stream.get('codec_name', '?')} "
                         f"{audio_stream.get('sample_rate', '?')} Hz")

        return "\n".join(parts)

    except FileNotFoundError:
        return "ERROR: ffmpeg/ffprobe no instalado. Instala: sudo apt install ffmpeg"
    except Exception as e:
        return f"ERROR obteniendo info del video: {e}"


def _video_extract_frames(ruta, params):
    """Extrae frames del video como imagenes PNG."""
    try:
        interval = params.get("intervalo", params.get("interval", 5))  # cada N segundos
        max_frames = params.get("max", 10)
        output_dir = params.get("output_dir", LEARN_DIR)

        os.makedirs(output_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(ruta))[0]
        pattern = os.path.join(output_dir, f"{base_name}_frame_%03d.png")

        cmd = [
            'ffmpeg', '-i', ruta,
            '-vf', f'fps=1/{interval}',
            '-frames:v', str(max_frames),
            '-q:v', '2',
            pattern
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        # Contar frames generados
        frames = [f for f in os.listdir(output_dir)
                  if f.startswith(base_name) and f.endswith('.png')]

        if frames:
            return (f"Frames extraidos: {len(frames)} de {ruta}\n"
                    f"  Intervalo: cada {interval}s\n"
                    f"  Directorio: {output_dir}\n"
                    f"  Archivos: {', '.join(sorted(frames)[:5])}"
                    + (f" ... y {len(frames)-5} mas" if len(frames) > 5 else ""))

        return "ERROR: No se pudieron extraer frames del video."

    except FileNotFoundError:
        return "ERROR: ffmpeg no instalado. Instala: sudo apt install ffmpeg"
    except Exception as e:
        return f"ERROR extrayendo frames: {e}"


def _video_analyze_with_vlm(ruta, params):
    """Analiza video extrayendo frames y usando VLM para describir."""
    try:
        # Extraer 3 frames clave (inicio, medio, final)
        temp_dir = tempfile.mkdtemp()
        base_name = "frame"

        # Obtener duracion
        probe = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json',
             '-show_format', ruta],
            capture_output=True, text=True, timeout=10
        )
        duration = float(json.loads(probe.stdout).get("format", {}).get("duration", 0))

        frames_info = []
        positions = [0, duration * 0.5, duration * 0.9] if duration > 0 else [0]

        for i, pos in enumerate(positions[:3]):
            frame_path = os.path.join(temp_dir, f"{base_name}_{i}.png")
            cmd = ['ffmpeg', '-ss', str(pos), '-i', ruta,
                   '-frames:v', '1', '-q:v', '2', frame_path]
            subprocess.run(cmd, capture_output=True, timeout=30)

            if os.path.exists(frame_path):
                frames_info.append((pos, frame_path))

        if not frames_info:
            return "ERROR: No se pudieron extraer frames para analizar."

        # Analizar cada frame con VLM
        results = [f"Analisis de video: {ruta}\nDuracion: {duration:.1f}s\n"]

        for pos, frame_path in frames_info:
            try:
                from llm import ollama
                desc = ollama.generate_with_image(
                    f"Describe lo que ves en este frame de video. "
                    f"Timestamp: {pos:.1f}s",
                    frame_path
                )
                results.append(f"[{pos:.1f}s] {desc}")
            except Exception as e:
                results.append(f"[{pos:.1f}s] (VLM no disponible: {e})")

        # Limpiar
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

        return "\n".join(results)

    except Exception as e:
        return f"ERROR analizando video: {e}"


def _video_transcribe(ruta, params):
    """Extrae el audio de un video y lo transcribe."""
    try:
        # Extraer audio
        temp_audio = tempfile.mktemp(suffix=".wav")
        cmd = ['ffmpeg', '-i', ruta, '-vn', '-acodec', 'pcm_s16le',
               '-ar', '16000', '-ac', '1', temp_audio]
        subprocess.run(cmd, capture_output=True, timeout=120)

        if not os.path.exists(temp_audio):
            return "ERROR: No se pudo extraer el audio del video."

        # Transcribir
        from .percepcion import transcribir_audio
        result = transcribir_audio(temp_audio, params.get("idioma", "es"))

        # Limpiar
        try:
            os.remove(temp_audio)
        except Exception:
            pass

        return f"Transcripcion de video: {ruta}\n\n{result}"

    except Exception as e:
        return f"ERROR transcribiendo video: {e}"


# ============================================================
# UTILIDADES
# ============================================================

def _parse_json(s, default=None):
    """Parsea JSON de forma segura."""
    if not s or s in ("{}", "[]", ""):
        return default if default is not None else {}
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


# ============================================================
# S5.7: AUDIO MEETING NOTES
# ============================================================

def notas_reunion(
    ruta_audio: str,
    idioma: str = "es",
    tipo_resumen: str = "ejecutivo",
    extraer_acciones: bool = True
) -> str:
    """S5.7: Transcribe audio de reunion y genera notas estructuradas.

    Transcribe la grabacion de audio, extrae action items,
    identifica temas clave, participantes, y genera un
    resumen ejecutivo de la reunion.

    Args:
        ruta_audio: Ruta al archivo de audio (MP3, WAV, M4A, etc.)
        idioma: Idioma de la transcripcion: es, en, fr, pt
        tipo_resumen: Tipo de resumen: ejecutivo, detallado, puntos_clave
        extraer_acciones: Si True, extrae action items y compromisos

    Returns:
        Notas estructuradas de la reunion con transcripcion, resumen y acciones
    """
    from utils.security import validate_path

    validation = validate_path(ruta_audio)
    if validation != ruta_audio:
        return validation

    # Paso 1: Transcribir audio
    try:
        from .percepcion import transcribir_audio
        transcripcion = transcribir_audio(ruta_audio, idioma=idioma)
    except Exception as e:
        return f"ERROR: No se pudo transcribir el audio: {e}"

    if not transcripcion or "ERROR" in transcripcion:
        return f"ERROR: La transcripcion fallo: {transcripcion[:200]}"

    # Truncar transcripcion si es muy larga para el LLM
    full_transcription = transcripcion
    if len(transcripcion) > 15000:
        transcripcion = transcripcion[:12000] + "\n... [transcripcion truncada]"

    # Paso 2: Analizar con LLM para generar notas estructuradas
    lang_name = {"es": "espanol", "en": "english", "fr": "frances", "pt": "portugues"}.get(idioma, "espanol")

    type_prompts = {
        "ejecutivo": (
            "Genera un resumen ejecutivo conciso de esta reunion. "
            "Incluye: tema principal, decisiones tomadas, y proximos pasos."
        ),
        "detallado": (
            "Genera un resumen detallado de esta reunion. "
            "Incluye: temas tratados, discusiones clave, puntos de acuerdo y desacuerdo, "
            "decisiones tomadas con responsables, y compromisos adquiridos."
        ),
        "puntos_clave": (
            "Extrae los puntos clave de esta reunion en formato de lista. "
            "Para cada punto: tema, decision o conclusion, responsable (si aplica)."
        ),
    }

    summary_instruction = type_prompts.get(tipo_resumen, type_prompts["ejecutivo"])

    acciones_instruction = ""
    if extraer_acciones:
        acciones_instruction = (
            "\n\nACCIONES: Identifica y lista todos los action items mencionados. "
            "Para cada accion indica: que hacer, quien es responsable (si se menciono), "
            "y fecha limite (si se menciono). Formato: "
            "- [ ] Accion | Responsable | Fecha limite"
        )

    participantes_instruction = (
        "\n\nPARTICIPANTES: Si se mencionan nombres de personas, listalos como participantes."
    )

    prompt = (
        f"{summary_instruction}"
        f"{acciones_instruction}"
        f"{participantes_instruction}"
        f"\n\nIdioma del resumen: {lang_name}"
        f"\n\nTRANSCRIPCION DE LA REUNION:\n{transcripcion}"
    )

    try:
        from llm import ollama
        messages = [{"role": "user", "content": prompt}]
        response = ollama.generate_chat(messages)
        analysis = str(response).strip() if response else "No se pudo generar el analisis."
    except Exception as e:
        analysis = f"Error generando analisis: {e}"

    # Formatear salida completa
    filename = os.path.basename(ruta_audio)
    output = (
        f"== NOTAS DE REUNION ==\n"
        f"Archivo: {filename}\n"
        f"Tipo de resumen: {tipo_resumen}\n"
        f"Idioma: {lang_name}\n"
        f"{'=' * 40}\n\n"
        f"{analysis}\n\n"
        f"{'=' * 40}\n"
        f"TRANSCRIPCION COMPLETA ({len(full_transcription)} caracteres):\n"
        f"{'=' * 40}\n"
        f"{full_transcription[:3000]}"
    )

    if len(full_transcription) > 3000:
        output += f"\n... [transcripcion truncada, {len(full_transcription)} caracteres totales]"

    return output
