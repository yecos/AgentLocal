"""
=============================================================
AGENTE v17 - Browser Automation con Playwright
=============================================================
Automatizacion real de navegador web usando Playwright.
Permite navegar, hacer click, escribir, tomar screenshots,
extraer datos, y automatizar flujos web completos.

Operaciones:
- navigate: Ir a una URL
- click: Hacer click en un elemento
- type: Escribir texto en un campo
- screenshot: Capturar pantalla
- extract: Extraer texto/HTML de la pagina
- fill_form: Llenar un formulario completo
- wait: Esperar por un elemento o condicion
- scroll: Scroll en la pagina
- evaluate: Ejecutar JavaScript
- pdf: Guardar pagina como PDF
- download: Descargar un archivo
- get_page_info: Obtener info de la pagina actual

v17: Automatizacion web de primera clase.
=============================================================
"""

import os
import json
import time
import threading
from datetime import datetime

from config import REPOS_DIR, logger
from utils.security import validate_url

# ============================================================
# DIRECTORIO DE SCREENSHOTS
# ============================================================
SCREENSHOT_DIR = os.path.join(REPOS_DIR, ".screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# ============================================================
# TIMEOUTS Y LIMITES
# ============================================================
DEFAULT_NAV_TIMEOUT = 30000    # 30s para navegacion
DEFAULT_ACTION_TIMEOUT = 5000  # 5s para acciones (click, type, etc.)
INACTIVITY_LIMIT = 300         # 5 min de inactividad -> auto-cleanup
MAX_SCREENSHOT_SIZE = 5 * 1024 * 1024  # 5MB max por screenshot
MAX_EXTRACT_CHARS = 8000       # Max chars en extraccion de texto
MAX_TOOL_OUTPUT = 6000         # Max chars en salida de herramienta

# ============================================================
# VERIFICACION DE PLAYWRIGHT
# ============================================================
_PLAYWRIGHT_AVAILABLE = False
_PLAYWRIGHT_ERROR_MSG = ""

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_ERROR_MSG = (
        "Playwright no esta instalado. Para usar browser_automation ejecuta:\n"
        "  pip install playwright\n"
        "  playwright install chromium\n"
        "Despues reinicia el agente."
    )
    PwTimeout = Exception  # Fallback para type hints


# ============================================================
# BROWSER MANAGER (SINGLETON)
# ============================================================

class BrowserManager:
    """Gestor singleton del navegador Playwright.
    Mantiene una sola instancia del navegador abierta entre operaciones.
    Auto-cleanup tras 5 minutos de inactividad.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._last_activity = 0.0
        self._cleanup_thread = None
        self._stop_cleanup = False
        self._screenshot_dir = SCREENSHOT_DIR
        self._initialized = True

    # --------------------------------------------------------
    # Inicio y parada del navegador
    # --------------------------------------------------------

    def start(self, headless: bool = True) -> str:
        """Inicia el navegador Playwright (chromium por defecto).

        Args:
            headless: Si True, navegador sin UI (por defecto True)

        Returns:
            Mensaje de estado
        """
        if not _PLAYWRIGHT_AVAILABLE:
            return _PLAYWRIGHT_ERROR_MSG

        # Si ya esta corriendo, reutilizar
        if self._browser and self._browser.is_connected():
            self._last_activity = time.time()
            return "Navegador ya esta corriendo (reutilizando sesion)"

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )
            self._context = self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                accept_downloads=True,
            )
            self._context.set_default_timeout(DEFAULT_NAV_TIMEOUT)
            self._page = self._context.new_page()
            self._last_activity = time.time()

            # Iniciar thread de cleanup por inactividad
            self._start_cleanup_thread()

            logger.info("Navegador Playwright iniciado (headless=%s)", headless)
            return f"Navegador iniciado correctamente (headless={headless})"

        except Exception as e:
            logger.error("Error iniciando navegador: %s", e)
            self._cleanup_resources()
            return f"Error iniciando navegador: {e}"

    def stop(self) -> str:
        """Cierra el navegador y libera recursos."""
        self._stop_cleanup = True
        self._cleanup_resources()
        return "Navegador cerrado y recursos liberados"

    def _cleanup_resources(self):
        """Libera todos los recursos de Playwright."""
        try:
            if self._page and not self._page.is_closed():
                self._page.close()
        except Exception:
            pass

        try:
            if self._context:
                self._context.close()
        except Exception:
            pass

        try:
            if self._browser and self._browser.is_connected():
                self._browser.close()
        except Exception:
            pass

        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    # --------------------------------------------------------
    # Thread de auto-cleanup por inactividad
    # --------------------------------------------------------

    def _start_cleanup_thread(self):
        """Inicia el thread daemon que cierra el navegador tras inactividad."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return
        self._stop_cleanup = False
        self._cleanup_thread = threading.Thread(
            target=self._inactivity_monitor,
            daemon=True,
            name="browser-cleanup"
        )
        self._cleanup_thread.start()

    def _inactivity_monitor(self):
        """Monitor de inactividad: cierra navegador tras 5 min sin uso."""
        while not self._stop_cleanup:
            time.sleep(30)  # Chequear cada 30s
            if self._stop_cleanup:
                break
            if self._browser and self._browser.is_connected():
                idle_time = time.time() - self._last_activity
                if idle_time > INACTIVITY_LIMIT:
                    logger.info(
                        "Auto-cleanup: navegador inactivo por %ds, cerrando",
                        int(idle_time)
                    )
                    self._cleanup_resources()
                    break
            else:
                # Navegador ya cerrado externamente
                break

    # --------------------------------------------------------
    # Obtener pagina actual
    # --------------------------------------------------------

    def get_page(self):
        """Retorna la pagina actual. Si no existe, inicia el navegador y crea una."""
        if not _PLAYWRIGHT_AVAILABLE:
            return None

        # Si el navegador no esta corriendo, iniciarlo
        if not self._browser or not self._browser.is_connected():
            result = self.start(headless=True)
            if "Error" in result:
                return None

        # Si la pagina se cerro, crear una nueva
        if not self._page or self._page.is_closed():
            self._page = self._context.new_page()

        self._last_activity = time.time()
        return self._page

    # --------------------------------------------------------
    # Screenshots
    # --------------------------------------------------------

    def take_screenshot(self, name: str = "", full_page: bool = False) -> str:
        """Toma un screenshot y lo guarda en el directorio de screenshots.

        Args:
            name: Nombre personalizado (sin extension). Si vacio, usa timestamp.
            full_page: Si True, captura la pagina completa (scroll).

        Returns:
            Ruta del archivo guardado o mensaje de error
        """
        page = self.get_page()
        if page is None:
            return "Error: navegador no disponible"

        try:
            # Generar nombre de archivo
            if not name:
                name = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            # Sanitizar nombre
            name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
            filename = f"{name}.png"
            filepath = os.path.join(self._screenshot_dir, filename)

            # Tomar screenshot
            page.screenshot(path=filepath, full_page=full_page)

            # Verificar tamano
            file_size = os.path.getsize(filepath)
            if file_size > MAX_SCREENSHOT_SIZE:
                # Reducir calidad re-tomando sin full_page
                if full_page:
                    page.screenshot(path=filepath, full_page=False)
                    file_size = os.path.getsize(filepath)

            self._last_activity = time.time()
            logger.info("Screenshot guardado: %s (%d bytes)", filepath, file_size)
            return f"Screenshot guardado: {filepath}"

        except Exception as e:
            logger.error("Error tomando screenshot: %s", e)
            return f"Error tomando screenshot: {e}"


# ============================================================
# INSTANCIA GLOBAL DEL MANAGER
# ============================================================
_manager = BrowserManager()


# ============================================================
# FUNCIONES AUXILIARES DE EXTRACCION
# ============================================================

def _extract_page_summary(page) -> str:
    """Extrae un resumen limpio de la pagina actual.
    Elimina scripts, estilos, nav, footer para quedarse con el contenido principal.
    """
    try:
        # Ejecutar JS para extraer texto limpio del body
        summary = page.evaluate("""() => {
            // Clonar el body para no modificar la pagina
            const clone = document.body.cloneNode(true);

            // Eliminar elementos no deseados
            const removeTags = ['script', 'style', 'nav', 'footer', 'header',
                                'aside', 'noscript', 'iframe', 'svg', 'form'];
            removeTags.forEach(tag => {
                clone.querySelectorAll(tag).forEach(el => el.remove());
            });

            // Eliminar elementos ocultos
            clone.querySelectorAll('[hidden], [style*="display: none"], [style*="display:none"]')
                .forEach(el => el.remove());

            // Obtener texto
            let text = clone.innerText || clone.textContent || '';

            // Limpiar espacios multiples y lineas vacias
            text = text.replace(/\\n{3,}/g, '\\n\\n');
            text = text.replace(/ {2,}/g, ' ');

            return text.trim();
        }""")

        if not summary:
            return "(pagina sin contenido de texto)"

        # Truncar si es muy largo
        if len(summary) > MAX_EXTRACT_CHARS:
            summary = summary[:MAX_EXTRACT_CHARS] + "\n... [truncado]"

        return summary

    except Exception as e:
        logger.debug("Error en _extract_page_summary: %s", e)
        return f"Error extrayendo resumen: {e}"


def _extract_structured_data(page, selector: str) -> str:
    """Extrae datos estructurados de elementos que matchean el selector.
    Retorna informacion de texto, href, src, value de cada elemento.
    """
    try:
        data = page.evaluate("""(selector) => {
            const elements = document.querySelectorAll(selector);
            const results = [];
            elements.forEach((el, i) => {
                if (i >= 50) return; // Limitar a 50 elementos
                const item = {
                    index: i,
                    tag: el.tagName.toLowerCase(),
                    text: (el.innerText || el.textContent || '').trim().substring(0, 200),
                };
                if (el.href) item.href = el.href;
                if (el.src) item.src = el.src;
                if (el.value) item.value = el.value;
                if (el.id) item.id = el.id;
                if (el.className && typeof el.className === 'string') item.class = el.className.substring(0, 100);
                results.push(item);
            });
            return JSON.stringify(results, null, 2);
        }""", selector)

        if not data:
            return f"No se encontraron elementos con selector: {selector}"

        # Parsear y formatear para salida legible
        try:
            items = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data[:MAX_EXTRACT_CHARS]

        lines = [f"Elementos encontrados: {len(items)}", ""]
        for item in items:
            line = f"[{item.get('index', '?')}] <{item.get('tag', '?')}>"
            if item.get('id'):
                line += f" #{item['id']}"
            if item.get('text'):
                text = item['text'][:100].replace('\n', ' ')
                line += f" -> {text}"
            if item.get('href'):
                line += f"\n    href: {item['href']}"
            if item.get('src'):
                line += f"\n    src: {item['src']}"
            if item.get('value'):
                line += f"\n    value: {item['value'][:80]}"
            lines.append(line)

        result = "\n".join(lines)
        if len(result) > MAX_EXTRACT_CHARS:
            result = result[:MAX_EXTRACT_CHARS] + "\n... [truncado]"
        return result

    except Exception as e:
        logger.debug("Error en _extract_structured_data: %s", e)
        return f"Error extrayendo datos estructurados: {e}"


def _extract_all_links(page) -> str:
    """Extrae todos los links de la pagina actual."""
    try:
        links = page.evaluate("""() => {
            const anchors = document.querySelectorAll('a[href]');
            const results = [];
            anchors.forEach((a, i) => {
                if (i >= 100) return;
                const text = (a.innerText || a.textContent || '').trim().substring(0, 80);
                const href = a.href;
                if (href && !href.startsWith('javascript:')) {
                    results.push({text: text || '(sin texto)', href: href});
                }
            });
            return results;
        }""")

        if not links:
            return "No se encontraron links en la pagina"

        lines = [f"Links encontrados: {len(links)}", ""]
        for i, link in enumerate(links):
            lines.append(f"{i+1}. {link['text']}")
            lines.append(f"   {link['href']}")

        result = "\n".join(lines)
        if len(result) > MAX_EXTRACT_CHARS:
            result = result[:MAX_EXTRACT_CHARS] + "\n... [truncado]"
        return result

    except Exception as e:
        return f"Error extrayendo links: {e}"


def _extract_all_images(page) -> str:
    """Extrae todas las imagenes de la pagina actual."""
    try:
        images = page.evaluate("""() => {
            const imgs = document.querySelectorAll('img[src]');
            const results = [];
            imgs.forEach((img, i) => {
                if (i >= 50) return;
                results.push({
                    alt: (img.alt || '').substring(0, 80),
                    src: img.src,
                    width: img.naturalWidth || img.width,
                    height: img.naturalHeight || img.height
                });
            });
            return results;
        }""")

        if not images:
            return "No se encontraron imagenes en la pagina"

        lines = [f"Imagenes encontradas: {len(images)}", ""]
        for i, img in enumerate(images):
            alt = img.get('alt', '(sin alt)')
            src = img.get('src', '')
            dims = f"{img.get('width', '?')}x{img.get('height', '?')}"
            lines.append(f"{i+1}. [{dims}] {alt}")
            lines.append(f"   {src}")

        result = "\n".join(lines)
        if len(result) > MAX_EXTRACT_CHARS:
            result = result[:MAX_EXTRACT_CHARS] + "\n... [truncado]"
        return result

    except Exception as e:
        return f"Error extrayendo imagenes: {e}"


# ============================================================
# VALIDACION DE URLs
# ============================================================

def _validate_navigation_url(url: str) -> str:
    """Valida que una URL sea segura para navegacion.
    Solo permite http:// y https://. Bloquea file:// y otros protocolos.

    Returns:
        URL validada o string de error (empieza con "ERROR:")
    """
    if not url or not url.strip():
        return "ERROR: URL vacia"

    url = url.strip()

    # Agregar https:// si no tiene protocolo
    if not url.startswith(("http://", "https://")):
        # No permitir file:// u otros protocolos
        if "://" in url:
            protocol = url.split("://")[0].lower()
            if protocol in ("file", "javascript", "data", "vbscript", "blob"):
                return f"ERROR: Protocolo '{protocol}://' no permitido. Solo http:// y https://"
        url = "https://" + url

    # Usar validacion de seguridad del proyecto
    if not validate_url(url):
        return f"ERROR: URL no valida o protocolo no permitido: {url[:100]}"

    return url


# ============================================================
# FUNCION PRINCIPAL: BROWSER AUTOMATION
# ============================================================

def browser_automation(accion: str, **kwargs) -> str:
    """Automatizacion real de navegador web usando Playwright.

    Acciones disponibles:
    - navigate: Ir a una URL
    - click: Hacer click en un elemento
    - type: Escribir texto en un campo
    - screenshot: Capturar pantalla
    - extract: Extraer texto/HTML de la pagina
    - fill_form: Llenar un formulario completo
    - wait: Esperar por un elemento o condicion
    - scroll: Scroll en la pagina
    - evaluate: Ejecutar JavaScript
    - pdf: Guardar pagina como PDF
    - download: Descargar un archivo
    - get_page_info: Obtener info de la pagina actual
    - start: Iniciar el navegador
    - stop: Cerrar el navegador

    Args:
        accion: Accion a ejecutar (navigate, click, type, etc.)
        **kwargs: Argumentos especificos de cada accion

    Returns:
        Resultado de la accion como string
    """
    # Verificar que Playwright este disponible
    if not _PLAYWRIGHT_AVAILABLE:
        return _PLAYWRIGHT_ERROR_MSG

    # Dispatch por accion
    accion = accion.lower().strip()

    dispatch = {
        "navigate": _accion_navigate,
        "click": _accion_click,
        "type": _accion_type,
        "screenshot": _accion_screenshot,
        "extract": _accion_extract,
        "fill_form": _accion_fill_form,
        "wait": _accion_wait,
        "scroll": _accion_scroll,
        "evaluate": _accion_evaluate,
        "pdf": _accion_pdf,
        "download": _accion_download,
        "get_page_info": _accion_get_page_info,
        "start": _accion_start,
        "stop": _accion_stop,
    }

    handler = dispatch.get(accion)
    if not handler:
        acciones_disponibles = ", ".join(sorted(dispatch.keys()))
        return (f"Accion '{accion}' no reconocida. "
                f"Acciones disponibles: {acciones_disponibles}")

    try:
        return handler(**kwargs)
    except PwTimeout as e:
        return f"TIMEOUT: La operacion '{accion}' excedio el tiempo limite. Detalle: {e}"
    except Exception as e:
        logger.error("Error en browser_automation accion='%s': %s", accion, e)
        return f"Error en accion '{accion}': {e}"


# ============================================================
# IMPLEMENTACION DE CADA ACCION
# ============================================================

def _accion_start(**kwargs) -> str:
    """Inicia el navegador Playwright."""
    headless = kwargs.get("headless", True)
    if isinstance(headless, str):
        headless = headless.lower() in ("true", "1", "yes", "si")
    return _manager.start(headless=headless)


def _accion_stop(**kwargs) -> str:
    """Cierra el navegador."""
    return _manager.stop()


def _accion_navigate(**kwargs) -> str:
    """Navega a una URL.

    Kwargs:
        url: URL a la que navegar
        wait_until: Condicion de espera (domcontentloaded, load, networkidle)
    """
    url = kwargs.get("url", "")
    wait_until = kwargs.get("wait_until", "domcontentloaded")

    # Validar URL
    validated = _validate_navigation_url(url)
    if validated.startswith("ERROR:"):
        return validated[6:]  # Quitar prefijo ERROR:

    url = validated

    # Validar wait_until
    valid_wait = ("domcontentloaded", "load", "networkidle", "commit")
    if wait_until not in valid_wait:
        wait_until = "domcontentloaded"

    page = _manager.get_page()
    if page is None:
        return "Error: no se pudo iniciar el navegador"

    try:
        response = page.goto(url, wait_until=wait_until, timeout=DEFAULT_NAV_TIMEOUT)

        # Obtener info de la pagina
        title = page.title()
        status = response.status if response else "sin respuesta"
        final_url = page.url

        result = f"Pagina cargada: {title}\n"
        result += f"URL: {final_url}\n"
        result += f"Status: {status}"

        # Si la URL final difiere (redirect), informar
        if final_url != url:
            result += f"\n(Redirigido desde: {url})"

        return result

    except PwTimeout:
        return f"TIMEOUT: La pagina {url} tardo demasiado en cargar"
    except Exception as e:
        return f"Error navegando a {url}: {e}"


def _accion_click(**kwargs) -> str:
    """Hace click en un elemento por selector CSS.

    Kwargs:
        selector: Selector CSS del elemento
        timeout: Timeout en ms (por defecto 5000)
    """
    selector = kwargs.get("selector", "")
    timeout = int(kwargs.get("timeout", DEFAULT_ACTION_TIMEOUT))

    if not selector:
        return "Error: se requiere un selector CSS (ej: '#btn-submit', '.login-btn', 'a[href=\"/login\"]')"

    page = _manager.get_page()
    if page is None:
        return "Error: navegador no disponible"

    try:
        # Esperar que el elemento este visible y habilitado
        page.wait_for_selector(selector, state="visible", timeout=timeout)
        page.click(selector, timeout=timeout)

        # Esperar un poco para que la accion se procese
        page.wait_for_load_state("domcontentloaded", timeout=5000)

        title = page.title()
        url = page.url

        return f"Click exitoso en '{selector}'\nPagina actual: {title}\nURL: {url}"

    except PwTimeout:
        return f"TIMEOUT: Elemento '{selector}' no encontrado o no visible en {timeout}ms"
    except Exception as e:
        return f"Error haciendo click en '{selector}': {e}"


def _accion_type(**kwargs) -> str:
    """Escribe texto en un campo de input.

    Kwargs:
        selector: Selector CSS del campo
        text: Texto a escribir
        clear: Si True, limpiar campo antes de escribir (por defecto True)
        press_enter: Si True, presionar Enter despues de escribir (por defecto False)
    """
    selector = kwargs.get("selector", "")
    text = kwargs.get("text", "")
    clear = kwargs.get("clear", True)
    press_enter = kwargs.get("press_enter", False)

    # Convertir strings a bool si vienen como string
    if isinstance(clear, str):
        clear = clear.lower() in ("true", "1", "yes", "si")
    if isinstance(press_enter, str):
        press_enter = press_enter.lower() in ("true", "1", "yes", "si")

    if not selector:
        return "Error: se requiere un selector CSS del campo de input"

    page = _manager.get_page()
    if page is None:
        return "Error: navegador no disponible"

    try:
        # Esperar que el campo este visible
        page.wait_for_selector(selector, state="visible", timeout=DEFAULT_ACTION_TIMEOUT)

        # Limpiar campo si se solicita
        if clear:
            page.fill(selector, "")
            # Tambien usar shortcut por si fill no funciona
            page.click(selector)
            page.keyboard.press("Control+a")
            page.keyboard.press("Backspace")

        # Escribir texto
        page.type(selector, str(text), delay=50)

        # Presionar Enter si se solicita
        if press_enter:
            page.keyboard.press("Enter")
            # Esperar navegacion si el Enter causa un submit
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except PwTimeout:
                pass  # No siempre hay navegacion tras Enter

        return f"Texto escrito en '{selector}': '{text[:50]}{'...' if len(text) > 50 else ''}"

    except PwTimeout:
        return f"TIMEOUT: Campo '{selector}' no encontrado en {DEFAULT_ACTION_TIMEOUT}ms"
    except Exception as e:
        return f"Error escribiendo en '{selector}': {e}"


def _accion_screenshot(**kwargs) -> str:
    """Toma un screenshot de la pagina actual.

    Kwargs:
        name: Nombre del archivo (sin extension)
        full_page: Si True, captura toda la pagina con scroll (por defecto False)
    """
    name = kwargs.get("name", "")
    full_page = kwargs.get("full_page", False)

    if isinstance(full_page, str):
        full_page = full_page.lower() in ("true", "1", "yes", "si")

    page = _manager.get_page()
    if page is None:
        return "Error: navegador no disponible"

    return _manager.take_screenshot(name=name, full_page=full_page)


def _accion_extract(**kwargs) -> str:
    """Extrae contenido de la pagina.

    Kwargs:
        selector: Selector CSS (opcional, si vacio extrae toda la pagina)
        extract_type: Tipo de extraccion:
            - text: Texto del elemento (por defecto)
            - html: HTML interno del elemento
            - href: Valor del atributo href
            - src: Valor del atributo src
            - value: Valor del campo (inputs)
            - all_links: Todos los links de la pagina
            - all_images: Todas las imagenes de la pagina
    """
    selector = kwargs.get("selector", "")
    extract_type = kwargs.get("extract_type", "text").lower().strip()

    page = _manager.get_page()
    if page is None:
        return "Error: navegador no disponible"

    try:
        # Extracciones especiales que no necesitan selector
        if extract_type == "all_links":
            return _extract_all_links(page)

        if extract_type == "all_images":
            return _extract_all_images(page)

        # Si no hay selector, extraer resumen de toda la pagina
        if not selector:
            if extract_type == "text":
                return _extract_page_summary(page)
            elif extract_type == "html":
                html = page.content()
                if len(html) > MAX_EXTRACT_CHARS:
                    html = html[:MAX_EXTRACT_CHARS] + "\n... [truncado]"
                return html
            else:
                return _extract_page_summary(page)

        # Extraccion con selector especifico
        if extract_type == "text":
            # Usar extraccion estructurada para mejor info
            return _extract_structured_data(page, selector)

        elif extract_type == "html":
            element = page.query_selector(selector)
            if not element:
                return f"No se encontro elemento con selector: {selector}"
            html = element.inner_html()
            if len(html) > MAX_EXTRACT_CHARS:
                html = html[:MAX_EXTRACT_CHARS] + "\n... [truncado]"
            return html

        elif extract_type == "href":
            element = page.query_selector(selector)
            if not element:
                return f"No se encontro elemento con selector: {selector}"
            href = element.get_attribute("href")
            return href or f"El elemento no tiene atributo href"

        elif extract_type == "src":
            element = page.query_selector(selector)
            if not element:
                return f"No se encontro elemento con selector: {selector}"
            src = element.get_attribute("src")
            return src or f"El elemento no tiene atributo src"

        elif extract_type == "value":
            element = page.query_selector(selector)
            if not element:
                return f"No se encontro elemento con selector: {selector}"
            value = element.get_attribute("value")
            if not value:
                # Intentar con evaluate para inputs
                try:
                    value = element.evaluate("el => el.value")
                except Exception:
                    pass
            return value or f"El elemento no tiene valor"

        else:
            return (f"Tipo de extraccion '{extract_type}' no reconocido. "
                    f"Tipos validos: text, html, href, src, value, all_links, all_images")

    except Exception as e:
        logger.error("Error extrayendo contenido: %s", e)
        return f"Error extrayendo contenido: {e}"


def _accion_fill_form(**kwargs) -> str:
    """Llena un formulario completo con multiples campos.

    Kwargs:
        fields: JSON string o lista de diccionarios con:
            - selector: Selector CSS del campo
            - value: Valor a escribir
            - type (opcional): "text", "select", "check", "radio"
    """
    fields = kwargs.get("fields", "")

    if not fields:
        return "Error: se requiere 'fields' con los campos del formulario"

    # Parsear fields si viene como string JSON
    if isinstance(fields, str):
        try:
            fields = json.loads(fields)
        except json.JSONDecodeError:
            return "Error: 'fields' debe ser un JSON valido. Formato: [{\"selector\": \"...\", \"value\": \"...\"}]"

    if not isinstance(fields, list):
        return "Error: 'fields' debe ser una lista de objetos"

    page = _manager.get_page()
    if page is None:
        return "Error: navegador no disponible"

    results = []
    errors = []

    for i, field in enumerate(fields):
        selector = field.get("selector", "")
        value = field.get("value", "")
        field_type = field.get("type", "text").lower()

        if not selector:
            errors.append(f"Campo {i+1}: sin selector")
            continue

        try:
            # Esperar que el campo este visible
            page.wait_for_selector(selector, state="visible", timeout=DEFAULT_ACTION_TIMEOUT)

            if field_type == "select":
                page.select_option(selector, value)
                results.append(f"Campo {i+1} ({selector}): seleccionado '{value}'")

            elif field_type == "check":
                page.check(selector)
                results.append(f"Campo {i+1} ({selector}): checkbox marcado")

            elif field_type == "uncheck":
                page.uncheck(selector)
                results.append(f"Campo {i+1} ({selector}): checkbox desmarcado")

            elif field_type == "radio":
                page.click(selector)
                results.append(f"Campo {i+1} ({selector}): radio seleccionado")

            else:  # text (default)
                page.fill(selector, "")
                page.type(selector, str(value), delay=30)
                results.append(f"Campo {i+1} ({selector}): escrito '{str(value)[:30]}'")

        except PwTimeout:
            errors.append(f"Campo {i+1} ({selector}): no encontrado o no visible")
        except Exception as e:
            errors.append(f"Campo {i+1} ({selector}): error - {e}")

    # Construir resultado
    output_parts = []
    if results:
        output_parts.append(f"Campos completados: {len(results)}/{len(fields)}")
        output_parts.extend(results)
    if errors:
        output_parts.append(f"\nErrores: {len(errors)}")
        output_parts.extend(errors)

    return "\n".join(output_parts)


def _accion_wait(**kwargs) -> str:
    """Espera por un elemento o condicion en la pagina.

    Kwargs:
        selector: Selector CSS del elemento a esperar (opcional)
        timeout: Timeout en ms (por defecto 5000)
        condition: Condicion a esperar (visible, hidden, attached, detached)
    """
    selector = kwargs.get("selector", "")
    timeout = int(kwargs.get("timeout", DEFAULT_ACTION_TIMEOUT))
    condition = kwargs.get("condition", "visible").lower().strip()

    page = _manager.get_page()
    if page is None:
        return "Error: navegador no disponible"

    try:
        if selector:
            # Validar condicion
            valid_conditions = ("visible", "hidden", "attached", "detached")
            if condition not in valid_conditions:
                return (f"Condicion '{condition}' no valida. "
                        f"Condiciones validas: {', '.join(valid_conditions)}")

            page.wait_for_selector(selector, state=condition, timeout=timeout)
            return f"Elemento '{selector}' ahora esta {condition}"

        else:
            # Si no hay selector, esperar a que la pagina termine de cargar
            page.wait_for_load_state("networkidle", timeout=timeout)
            return "Pagina cargada completamente (network idle)"

    except PwTimeout:
        if selector:
            return f"TIMEOUT: Elemento '{selector}' no alcanzo estado '{condition}' en {timeout}ms"
        else:
            return f"TIMEOUT: La pagina no termino de cargar en {timeout}ms"
    except Exception as e:
        return f"Error esperando: {e}"


def _accion_scroll(**kwargs) -> str:
    """Hace scroll en la pagina.

    Kwargs:
        direction: Direccion del scroll (up, down, left, right)
        amount: Cantidad de pixels a scrollear (por defecto 500)
    """
    direction = kwargs.get("direction", "down").lower().strip()
    amount = int(kwargs.get("amount", 500))

    page = _manager.get_page()
    if page is None:
        return "Error: navegador no disponible"

    try:
        if direction == "down":
            page.mouse.wheel(0, amount)
        elif direction == "up":
            page.mouse.wheel(0, -amount)
        elif direction == "right":
            page.mouse.wheel(amount, 0)
        elif direction == "left":
            page.mouse.wheel(-amount, 0)
        else:
            return f"Direccion '{direction}' no valida. Usar: up, down, left, right"

        # Pequena pausa para que el scroll se procese
        page.wait_for_timeout(300)

        return f"Scroll {direction} {amount}px ejecutado"

    except Exception as e:
        return f"Error haciendo scroll: {e}"


def _accion_evaluate(**kwargs) -> str:
    """Ejecuta JavaScript en la pagina y retorna el resultado.

    Kwargs:
        script: Codigo JavaScript a ejecutar
    """
    script = kwargs.get("script", "")

    if not script:
        return "Error: se requiere codigo JavaScript en 'script'"

    page = _manager.get_page()
    if page is None:
        return "Error: navegador no disponible"

    try:
        result = page.evaluate(script)

        if result is None:
            return "JavaScript ejecutado (sin retorno)"

        # Formatear resultado
        if isinstance(result, (dict, list)):
            formatted = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            formatted = str(result)

        if len(formatted) > MAX_EXTRACT_CHARS:
            formatted = formatted[:MAX_EXTRACT_CHARS] + "\n... [truncado]"

        return f"Resultado: {formatted}"

    except Exception as e:
        return f"Error ejecutando JavaScript: {e}"


def _accion_pdf(**kwargs) -> str:
    """Guarda la pagina actual como PDF (solo funciona en modo headless).

    Kwargs:
        output_path: Ruta donde guardar el PDF. Si vacio, usa directorio de screenshots.
    """
    output_path = kwargs.get("output_path", "")

    page = _manager.get_page()
    if page is None:
        return "Error: navegador no disponible"

    try:
        # Generar ruta de salida si no se proporciona
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(SCREENSHOT_DIR, f"page_{timestamp}.pdf")
        else:
            # Validar ruta de salida
            from utils.security import validate_path
            validation = validate_path(output_path)
            if validation.startswith("ACCESO DENEGADO"):
                return validation

        # PDF solo funciona en modo headless con Chromium
        pdf_data = page.pdf(path=output_path, format="A4", print_background=True)

        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else len(pdf_data)
        return f"PDF guardado: {output_path} ({file_size} bytes)"

    except Exception as e:
        error_msg = str(e)
        if "headless" in error_msg.lower():
            return ("Error: PDF solo se puede generar en modo headless. "
                    "Reinicia el navegador con start(headless=True)")
        return f"Error generando PDF: {e}"


def _accion_download(**kwargs) -> str:
    """Descarga un archivo desde una URL.

    Kwargs:
        url: URL del archivo a descargar
        output_dir: Directorio donde guardar (por defecto REPOS_DIR)
    """
    url = kwargs.get("url", "")
    output_dir = kwargs.get("output_dir", REPOS_DIR)

    if not url:
        return "Error: se requiere una URL para descargar"

    # Validar URL
    validated = _validate_navigation_url(url)
    if validated.startswith("ERROR:"):
        return validated[6:]

    url = validated

    # Validar directorio de salida
    from utils.security import validate_path
    validation = validate_path(output_dir)
    if validation.startswith("ACCESO DENEGADO"):
        return validation

    page = _manager.get_page()
    if page is None:
        return "Error: navegador no disponible"

    try:
        # Usar el mecanismo de descarga de Playwright
        with page.expect_download(timeout=DEFAULT_NAV_TIMEOUT) as download_info:
            # Navegar a la URL de descarga
            page.evaluate(f"window.location.href = '{url}'")

        download = download_info.value

        # Generar ruta de destino
        suggested_name = download.suggested_filename
        if not suggested_name:
            suggested_name = f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        output_path = os.path.join(output_dir, suggested_name)
        download.save_as(output_path)

        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        return f"Archivo descargado: {output_path} ({file_size} bytes)"

    except PwTimeout:
        # Fallback: usar urllib si Playwright no detecta la descarga
        return _download_fallback(url, output_dir)
    except Exception as e:
        # Intentar fallback
        return _download_fallback(url, output_dir)


def _download_fallback(url: str, output_dir: str) -> str:
    """Fallback para descargas usando urllib cuando Playwright falla."""
    try:
        import urllib.request
        filename = url.split("/")[-1].split("?")[0] or f"download_{int(time.time())}"
        output_path = os.path.join(output_dir, filename)

        req = urllib.request.Request(url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
        })

        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(output_path, "wb") as f:
                f.write(resp.read())

        file_size = os.path.getsize(output_path)
        return f"Archivo descargado (fallback): {output_path} ({file_size} bytes)"

    except Exception as e:
        return f"Error descargando archivo: {e}"


def _accion_get_page_info(**kwargs) -> str:
    """Obtiene informacion de la pagina actual.

    Retorna: titulo, URL, dimensiones del viewport, longitud del contenido.
    """
    page = _manager.get_page()
    if page is None:
        return "Error: navegador no disponible"

    try:
        title = page.title()
        url = page.url
        viewport = page.viewport_size

        # Obtener info adicional via JS
        page_info = page.evaluate("""() => {
            return {
                contentLength: document.body ? document.body.innerHTML.length : 0,
                textLength: document.body ? (document.body.innerText || '').length : 0,
                links: document.querySelectorAll('a').length,
                images: document.querySelectorAll('img').length,
                forms: document.querySelectorAll('form').length,
                inputs: document.querySelectorAll('input, textarea, select').length,
            };
        }""")

        lines = [
            f"Titulo: {title}",
            f"URL: {url}",
            f"Viewport: {viewport.get('width', '?')}x{viewport.get('height', '?')}" if viewport else "Viewport: N/A",
            f"Contenido HTML: {page_info.get('contentLength', 0):,} caracteres",
            f"Texto visible: {page_info.get('textLength', 0):,} caracteres",
            f"Links: {page_info.get('links', 0)}",
            f"Imagenes: {page_info.get('images', 0)}",
            f"Formularios: {page_info.get('forms', 0)}",
            f"Campos input: {page_info.get('inputs', 0)}",
        ]

        return "\n".join(lines)

    except Exception as e:
        return f"Error obteniendo info de la pagina: {e}"


# ============================================================
# FUNCION DE LIMPIEZA PARA SHUTDOWN
# ============================================================

def cleanup_browser():
    """Funcion de limpieza para llamar en el shutdown del agente.
    Cierra el navegador y libera todos los recursos.
    """
    try:
        _manager.stop()
        logger.info("Browser cleanup completado")
    except Exception as e:
        logger.debug("Error en browser cleanup: %s", e)
