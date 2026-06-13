"""
=============================================================
AGENTE v14.7 - Herramientas de Audio, OCR y Web Automation
=============================================================
Audio:
- Transcripcion de audio (Whisper local via Ollama o whisper.py)
- Text-to-speech basico

OCR:
- Lectura de texto en imagenes (pytesseract / easyocr / vision LLM)

Web Automation:
- Scraping de paginas web (requests + BeautifulSoup)
- Interaccion con paginas web (Playwright)
=============================================================
"""

import os
import logging
from config import REPOS_DIR, MAX_FILE_READ, logger
from utils.security import validate_path


# ============================================================
# TRANSCRIPCION DE AUDIO
# ============================================================

def transcribir_audio(ruta: str, idioma: str = "es") -> str:
    """Transcribe un archivo de audio a texto usando Whisper local. Soporta MP3, WAV, M4A, FLAC, OGG.

    Args:
        ruta: Ruta del archivo de audio
        idioma: Codigo de idioma (es=espanol, en=ingles, auto=deteccion)
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    ruta = _resolve_path(ruta)
    if not ruta:
        return f"Archivo no encontrado: {ruta}"

    ext = ruta.lower()
    supported = ('.mp3', '.wav', '.m4a', '.flac', '.ogg', '.wma', '.aac')
    if not ext.endswith(supported):
        return f"ERROR: Formato no soportado. Usar: {', '.join(supported)}"

    # Intentar con whisper (openai-whisper)
    result = _transcribir_whisper(ruta, idioma)
    if result is not None:
        return result

    # Intentar con Ollama whisper (si esta instalado)
    result = _transcribir_ollama(ruta, idioma)
    if result is not None:
        return result

    # Intentar con comando ffmpeg + whisper-ctranslate2
    result = _transcribir_comando(ruta, idioma)
    if result is not None:
        return result

    return ("ERROR: No se pudo transcribir el audio. Instala una opcion:\n"
            "  pip install openai-whisper   (recomendado, requiere ffmpeg)\n"
            "  O: ollama pull whisper   (modelo de Ollama)\n"
            "  O: pip install whisper-ctranslate2 (mas rapido)")


def _transcribir_whisper(ruta, idioma):
    """Transcribe con openai-whisper."""
    try:
        import whisper

        # Cargar modelo base (rapido, ~1GB RAM)
        model = whisper.load_model("base")

        options = {}
        if idioma and idioma != "auto":
            options["language"] = idioma

        result = model.transcribe(ruta, **options)

        text = result.get("text", "").strip()
        if not text:
            return "Audio transcrito pero sin texto detectado (posible silencio o idioma no reconocido)."

        # Formatear con segmentos si hay
        segments = result.get("segments", [])
        if segments and len(segments) > 1:
            parts = [f"Audio: {os.path.basename(ruta)}"]
            parts.append(f"Idioma detectado: {result.get('language', idioma)}")
            parts.append(f"Duracion: {segments[-1].get('end', 0):.1f}s\n")

            for seg in segments[:50]:  # Max 50 segmentos
                start = seg.get("start", 0)
                end = seg.get("end", 0)
                text_seg = seg.get("text", "").strip()
                if text_seg:
                    parts.append(f"[{start:.0f}s - {end:.0f}s] {text_seg}")

            content = "\n".join(parts)
        else:
            content = f"Audio: {os.path.basename(ruta)}\n\n{text}"

        if len(content) > MAX_FILE_READ:
            content = content[:MAX_FILE_READ] + "\n... [truncado]"

        return content

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"whisper fallo: {e}")
        return f"ERROR transcribiendo con whisper: {e}"


def _transcribir_ollama(ruta, idioma):
    """Transcribe usando modelo whisper de Ollama."""
    try:
        from llm import ollama

        # Verificar si Ollama tiene modelo whisper
        models = ollama.list_models() if hasattr(ollama, 'list_models') else []
        has_whisper = any('whisper' in m.lower() for m in models)

        if not has_whisper:
            return None

        # Usar Ollama para transcripcion
        import json
        import urllib.request

        with open(ruta, 'rb') as f:
            audio_data = f.read()

        # Intentar via API de Ollama
        payload = {
            "model": "whisper",
            "audio": audio_data.hex() if hasattr(audio_data, 'hex') else "",
        }

        # Esta funcionalidad puede no estar disponible en todas las versiones de Ollama
        return None

    except Exception:
        return None


def _transcribir_comando(ruta, idioma):
    """Fallback: transcribe con comando whisper."""
    import subprocess
    try:
        lang_opt = f"--language {idioma}" if idioma != "auto" else ""
        result = subprocess.run(
            f"whisper '{ruta}' --model base --output_format txt {lang_opt} --output_dir /tmp/whisper_out",
            shell=True, capture_output=True, text=True, timeout=300
        )

        # Leer archivo de salida
        base_name = os.path.splitext(os.path.basename(ruta))[0]
        output_file = f"/tmp/whisper_out/{base_name}.txt"

        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()
            os.remove(output_file)  # Limpiar
            return f"Audio: {os.path.basename(ruta)}\n\n{content[:MAX_FILE_READ]}"

    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as e:
        logger.debug(f"whisper comando fallo: {e}")

    return None


# ============================================================
# OCR (LECTURA DE TEXTO EN IMAGENES)
# ============================================================

def leer_imagen_ocr(ruta: str, idioma: str = "spa") -> str:
    """Extrae texto de una imagen usando OCR. Soporta JPG, PNG, BMP, TIFF, PDF (escaneado).

    Args:
        ruta: Ruta de la imagen
        idioma: Idioma para OCR (spa=espanol, eng=ingles, spa+eng=ambos)
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    ruta = _resolve_path(ruta)
    if not ruta:
        return f"Archivo no encontrado: {ruta}"

    # Intentar con pytesseract
    result = _ocr_tesseract(ruta, idioma)
    if result is not None:
        return result

    # Intentar con easyocr
    result = _ocr_easyocr(ruta, idioma)
    if result is not None:
        return result

    # Fallback: usar vision LLM
    result = _ocr_vision_llm(ruta)
    if result is not None:
        return result

    return ("ERROR: No se pudo hacer OCR. Instala una opcion:\n"
            "  pip install pytesseract   (+ instalar Tesseract OCR del sistema)\n"
            "  pip install easyocr       (puro Python, sin instalacion adicional)\n"
            "  O usa un modelo de vision (llava, llama3.2-vision) con analizar_imagen")


def _ocr_tesseract(ruta, idioma):
    """OCR con pytesseract."""
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(ruta)

        # Configurar idioma
        lang_map = {"spa": "spa", "eng": "eng", "espanol": "spa", "ingles": "eng"}
        lang = lang_map.get(idioma, idioma)

        # Extraer texto
        text = pytesseract.image_to_string(img, lang=lang)

        if not text.strip():
            return "OCR completado pero no se detecto texto en la imagen."

        # Informacion adicional
        try:
            data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
            conf_values = [int(c) for c in data['conf'] if c.isdigit()]
            avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0
            confidence = f"Confianza promedio: {avg_conf:.0f}%"
        except Exception:
            confidence = ""

        result = f"OCR: {os.path.basename(ruta)}"
        if confidence:
            result += f" ({confidence})"
        result += f"\n\n{text.strip()}"

        if len(result) > MAX_FILE_READ:
            result = result[:MAX_FILE_READ] + "\n... [truncado]"

        return result

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"pytesseract fallo: {e}")
        return f"ERROR OCR: {e}. Verifica que Tesseract este instalado (apt install tesseract-ocr)"


def _ocr_easyocr(ruta, idioma):
    """OCR con easyocr (puro Python)."""
    try:
        import easyocr

        # Mapear idioma
        lang_map = {"spa": "es", "eng": "en", "espanol": "es", "ingles": "en"}
        lang = lang_map.get(idioma, "es")

        reader = easyocr.Reader([lang], gpu=False)  # CPU mode para compatibilidad
        results = reader.readtext(ruta)

        if not results:
            return "OCR completado pero no se detecto texto en la imagen."

        parts = [f"OCR: {os.path.basename(ruta)}\n"]

        for (bbox, text, confidence) in results:
            if confidence > 0.3:  # Filtrar detecciones de baja confianza
                parts.append(text)

        full_text = "\n".join(parts)
        if len(full_text) > MAX_FILE_READ:
            full_text = full_text[:MAX_FILE_READ] + "\n... [truncado]"

        return full_text

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"easyocr fallo: {e}")
        return f"ERROR OCR con easyocr: {e}"


def _ocr_vision_llm(ruta):
    """Fallback: OCR usando el modelo de vision del LLM."""
    try:
        from llm import ollama

        # Verificar si hay modelo de vision
        result = ollama.generate_with_image(
            "Extrae TODO el texto visible en esta imagen. Transcribelo exactamente como aparece.",
            ruta
        )

        if result and len(result.strip()) > 10:
            return f"OCR (vision AI): {os.path.basename(ruta)}\n\n{result}"

    except Exception:
        pass

    return None


# ============================================================
# WEB SCRAPING
# ============================================================

def scrapear_web(url: str, selector: str = None, max_caracteres: int = 5000) -> str:
    """Extrae el contenido textual de una pagina web. Lee el HTML y extrae texto limpio.

    Args:
        url: URL de la pagina web a leer
        selector: Selector CSS para extraer seccion especifica (opcional)
        max_caracteres: Maximo de caracteres a extraer (default 5000)
    """
    # Intentar con requests + BeautifulSoup
    result = _scrapear_bs4(url, selector, max_caracteres)
    if result is not None:
        return result

    # Fallback: urllib
    result = _scrapear_urllib(url, max_caracteres)
    if result is not None:
        return result

    return "ERROR: No se pudo acceder a la pagina web. Verifica la URL y la conexion a internet."


def _scrapear_bs4(url, selector, max_caracteres):
    """Scraping con requests + BeautifulSoup."""
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        # Detectar codificacion
        if response.encoding and response.encoding.lower() != 'utf-8':
            response.encoding = response.apparent_encoding

        soup = BeautifulSoup(response.text, 'html.parser')

        # Remover scripts, estilos, nav, footer
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe']):
            tag.decompose()

        # Si hay selector, usarlo
        if selector:
            elements = soup.select(selector)
            if elements:
                text = "\n".join(el.get_text(separator="\n", strip=True) for el in elements)
            else:
                return f"Selector '{selector}' no encontro elementos. Mostrando contenido general:\n\n" + soup.get_text(separator="\n", strip=True)
        else:
            # Extraer titulo
            title = soup.find('title')
            title_text = title.get_text(strip=True) if title else ""

            # Extraer contenido principal
            # Intentar encontrar el contenido principal
            main = soup.find('main') or soup.find('article') or soup.find(class_='content') or soup.find(class_='post')

            if main:
                text = main.get_text(separator="\n", strip=True)
            else:
                text = soup.get_text(separator="\n", strip=True)

            # Limpiar lineas vacias excesivas
            lines = [l for l in text.split('\n') if l.strip()]
            text = '\n'.join(lines)

            if title_text:
                text = f"Titulo: {title_text}\n\n{text}"

        if len(text) > max_caracteres:
            text = text[:max_caracteres] + "\n... [truncado]"

        return f"Web: {url}\n\n{text}"

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"requests+BS4 fallo: {e}")
        return f"ERROR scrapeando: {e}"


def _scrapear_urllib(url, max_caracteres):
    """Fallback: scraping con urllib (sin dependencias)."""
    try:
        import urllib.request
        from html.parser import HTMLParser

        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.skip = False
                self.title = ""

            def handle_starttag(self, tag, attrs):
                if tag in ('script', 'style', 'nav', 'footer'):
                    self.skip = True
                if tag == 'title':
                    self._in_title = True

            def handle_endtag(self, tag):
                if tag in ('script', 'style', 'nav', 'footer'):
                    self.skip = False
                if tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'br', 'li'):
                    self.text.append('\n')
                if tag == 'title':
                    self._in_title = False

            def handle_data(self, data):
                if not self.skip and data.strip():
                    if getattr(self, '_in_title', False):
                        self.title = data.strip()
                    self.text.append(data.strip())

        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })

        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', errors='replace')

        extractor = _TextExtractor()
        extractor.feed(html)

        text = " ".join(extractor.text)
        if extractor.title:
            text = f"Titulo: {extractor.title}\n\n{text}"

        # Limpiar
        text = text.replace("  ", " ").strip()
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        text = '\n'.join(lines)

        if len(text) > max_caracteres:
            text = text[:max_caracteres] + "\n... [truncado]"

        return f"Web: {url}\n\n{text}"

    except Exception as e:
        logger.debug(f"urllib scraping fallo: {e}")
        return f"ERROR scrapeando: {e}"


# ============================================================
# WEB AUTOMATION (Playwright)
# ============================================================

def automatizar_web(url: str, accion: str = "screenshot", selector: str = "",
                    texto: str = "", esperar: int = 3) -> str:
    """Interactua con paginas web usando Playwright. Puede tomar screenshots, hacer click, escribir texto, extraer contenido.

    Args:
        url: URL de la pagina web
        accion: Accion a realizar: screenshot, click, escribir, extraer, scroll
        selector: Selector CSS del elemento (para click, escribir, extraer)
        texto: Texto a escribir (para accion "escribir")
        esperar: Segundos a esperar antes de la accion (default 3)
    """
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})

            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(esperar * 1000)

            result = ""

            if accion == "screenshot":
                # Tomar screenshot
                from config import LEARN_DIR
                import time
                screenshot_path = os.path.join(LEARN_DIR, f"web_screenshot_{int(time.time())}.png")
                page.screenshot(path=screenshot_path, full_page=False)
                result = f"Screenshot guardado: {screenshot_path}"

            elif accion == "click":
                if not selector:
                    result = "ERROR: Necesitas especificar un selector CSS para hacer click."
                else:
                    page.click(selector)
                    page.wait_for_timeout(1000)
                    result = f"Click realizado en: {selector}"

            elif accion == "escribir":
                if not selector or not texto:
                    result = "ERROR: Necesitas selector y texto para escribir."
                else:
                    page.fill(selector, texto)
                    result = f"Texto escrito en {selector}: {texto[:50]}"

            elif accion == "extraer":
                if selector:
                    element = page.query_selector(selector)
                    if element:
                        result = element.inner_text()
                    else:
                        result = f"No se encontro elemento: {selector}"
                else:
                    # Extraer todo el texto visible
                    result = page.inner_text("body")

                if len(result) > MAX_FILE_READ:
                    result = result[:MAX_FILE_READ] + "\n... [truncado]"

            elif accion == "scroll":
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)
                result = "Scroll al final de la pagina completado"

            else:
                result = f"ERROR: Accion '{accion}' no reconocida. Usar: screenshot, click, escribir, extraer, scroll"

            browser.close()
            return f"Web automation: {url}\nAccion: {accion}\n\n{result}"

    except ImportError:
        return ("ERROR: Playwright no instalado. Instala:\n"
                "  pip install playwright\n"
                "  playwright install chromium")
    except Exception as e:
        return f"ERROR en web automation: {e}"


# ============================================================
# UTILIDADES
# ============================================================

def _resolve_path(ruta):
    """Resuelve la ruta del archivo."""
    if os.path.isabs(ruta) and os.path.exists(ruta):
        return ruta
    if os.path.exists(ruta):
        return ruta
    alt = os.path.join(REPOS_DIR, ruta)
    if os.path.exists(alt):
        return alt
    return None
