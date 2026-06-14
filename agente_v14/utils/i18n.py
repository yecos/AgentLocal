"""
=============================================================
AGENTE v23 - Internationalization (i18n)
=============================================================
Framework de internacionalizacion para el agente:
- Deteccion automatica de idioma del sistema
- Traducciones cargadas desde archivos JSON
- Fallback a espanol si no hay traduccion
- Soporte para interpolacion de variables
- Deteccion de idioma del usuario por input
- Cambio de idioma en runtime

v23: Primera implementacion - es/en soportados
=============================================================
"""

import os
import json
import locale
import logging
import threading
from pathlib import Path

logger = logging.getLogger("agente.i18n")

# ============================================================
# DIRECTORIO DE TRADUCCIONES
# ============================================================

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_TRANSLATIONS_DIR = os.path.normpath(
    os.path.join(_AGENT_DIR, "..", "data", "translations")
)

# Idioma por defecto (fallback)
_DEFAULT_LANGUAGE = "es"

# Palabras clave en ingles para deteccion heuristica
_ENGLISH_KEYWORDS = {
    "hello", "hi", "please", "help", "what", "how", "can", "you", "the",
    "is", "are", "do", "make", "create", "build", "run", "show", "list",
    "find", "search", "write", "read", "open", "close", "start", "stop",
    "check", "tell", "give", "get", "set",
}

# Umbral de palabras en ingles para considerar el input como ingles
_ENGLISH_THRESHOLD = 0.4


class I18n:
    """Sistema de internacionalizacion (singleton).

    Carga traducciones desde archivos JSON en data/translations/.
    Detecta el idioma del sistema al iniciar y permite cambiar
    el idioma en runtime. Soporta interpolacion de variables
    en las cadenas de traduccion.

    Uso:
        from utils.i18n import get_i18n
        i18n = get_i18n()
        msg = i18n.t("agent.greeting")
        msg = i18n.t("agent.executing", tool="git")
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        """Inicializa el sistema i18n.

        Detecta el idioma del sistema y carga las traducciones
        correspondientes. Si no se encuentran traducciones para
        el idioma detectado, usa espanol como fallback.
        """
        self._language = self.detect_language()
        self._translations: dict[str, dict[str, str]] = {}
        self._translations_lock = threading.Lock()
        # Cargar traducciones del idioma actual y del fallback
        self._ensure_loaded(self._language)
        self._ensure_loaded(_DEFAULT_LANGUAGE)

    @classmethod
    def get(cls) -> "I18n":
        """Retorna la instancia singleton de I18n.

        Thread-safe: multiples threads llamando esto concurrentemente
        obtendran la misma instancia.

        Returns:
            Instancia unica de I18n.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ----------------------------------------------------------
    # TRADUCCION
    # ----------------------------------------------------------

    def t(self, key: str, **kwargs) -> str:
        """Traduce una clave a el idioma actual con interpolacion opcional.

        Busca la clave en las traducciones del idioma actual. Si no la
        encuentra, busca en el idioma por defecto (es). Si tampoco la
        encuentra, retorna la clave misma.

        Soporta interpolacion de variables con formato Python:
            i18n.t("agent.executing", tool="git")
            -> "Ejecutando: git" / "Executing: git"

        Args:
            key: Clave de traduccion (ej: "agent.greeting").
            **kwargs: Variables para interpolacion en la cadena.

        Returns:
            Cadena traducida con variables interpoladas.
        """
        # Buscar en idioma actual
        template = self._get_template(key, self._language)

        # Fallback a idioma por defecto
        if template is None and self._language != _DEFAULT_LANGUAGE:
            template = self._get_template(key, _DEFAULT_LANGUAGE)

        # Fallback a la clave misma
        if template is None:
            logger.debug(f"Clave i18n no encontrada: {key}")
            return key

        # Interpolar variables
        if kwargs:
            try:
                return template.format(**kwargs)
            except KeyError as e:
                logger.debug(f"Variable de interpolacion faltante en '{key}': {e}")
                return template
            except (IndexError, ValueError) as e:
                logger.debug(f"Error de interpolacion en '{key}': {e}")
                return template

        return template

    def _get_template(self, key: str, lang: str) -> str | None:
        """Obtiene una plantilla de traduccion para una clave e idioma.

        Args:
            key: Clave de traduccion.
            lang: Codigo de idioma (ej: "es", "en").

        Returns:
            Cadena de traduccion o None si no se encuentra.
        """
        with self._translations_lock:
            translations = self._translations.get(lang, {})
            return translations.get(key)

    # ----------------------------------------------------------
    # GESTION DE IDIOMA
    # ----------------------------------------------------------

    def set_language(self, lang: str) -> None:
        """Cambia el idioma activo en runtime.

        Carga las traducciones del nuevo idioma si no estan ya
        en memoria. Si el idioma no tiene archivo de traducciones,
        se emite un warning y se mantiene el idioma actual.

        Args:
            lang: Codigo de idioma (ej: "es", "en").
        """
        lang = lang.lower().strip()

        if lang == self._language:
            return

        # Verificar que hay traducciones disponibles
        self._ensure_loaded(lang)

        available = self.available_languages()
        if lang not in available:
            logger.warning(
                f"Idioma '{lang}' no disponible. "
                f"Disponibles: {available}. Manteniendo '{self._language}'."
            )
            return

        self._language = lang
        logger.info(f"Idioma cambiado a: {lang}")

    def get_language(self) -> str:
        """Retorna el codigo del idioma activo.

        Returns:
            Codigo de idioma (ej: "es", "en").
        """
        return self._language

    # ----------------------------------------------------------
    # DETECCION DE IDIOMA
    # ----------------------------------------------------------

    def detect_language(self) -> str:
        """Detecta el idioma del sistema operativo.

        Intenta detectar el idioma a partir de:
        1. Variable de entorno LANG
        2. Variable de entorno LC_ALL
        3. Configuracion de locale del sistema
        5. Fallback a espanol

        Returns:
            Codigo de idioma detectado ("es" o "en").
        """
        # Intentar desde variables de entorno
        for env_var in ("LANG", "LC_ALL", "LC_MESSAGES"):
            env_val = os.getenv(env_var, "").lower()
            if env_val:
                if env_val.startswith("en"):
                    return "en"
                if env_val.startswith("es"):
                    return "es"

        # Intentar desde locale del sistema
        try:
            sys_locale = locale.getdefaultlocale()[0]
            if sys_locale:
                if sys_locale.lower().startswith("en"):
                    return "en"
                if sys_locale.lower().startswith("es"):
                    return "es"
        except (ValueError, TypeError):
            pass

        # Intentar desde locale.getlocale()
        try:
            sys_locale = locale.getlocale()[0]
            if sys_locale:
                if sys_locale.lower().startswith("en"):
                    return "en"
                if sys_locale.lower().startswith("es"):
                    return "es"
        except (ValueError, TypeError):
            pass

        # Fallback a espanol
        return _DEFAULT_LANGUAGE

    def detect_from_text(self, text: str) -> str:
        """Detecta el idioma a partir de un texto del usuario.

        Usa una heuristica simple: si mas del 40% de las palabras
        del texto son palabras clave en ingles, se considera ingles.
        De lo contrario, se considera espanol.

        Args:
            text: Texto de entrada del usuario.

        Returns:
            Codigo de idioma detectado ("es" o "en").
        """
        if not text or not text.strip():
            return self._language

        # Tokenizar: separar por espacios y limpiar
        words = text.lower().split()
        words = [w.strip(".,!?;:\"'()[]{}") for w in words]
        words = [w for w in words if w]  # eliminar vacios

        if not words:
            return self._language

        # Contar palabras que coinciden con keywords en ingles
        english_count = sum(1 for w in words if w in _ENGLISH_KEYWORDS)
        ratio = english_count / len(words)

        if ratio >= _ENGLISH_THRESHOLD:
            return "en"

        return "es"

    # ----------------------------------------------------------
    # CARGA DE TRADUCCIONES
    # ----------------------------------------------------------

    def load_translations(self, lang: str) -> dict:
        """Carga las traducciones para un idioma desde archivo JSON.

        Busca el archivo {lang}.json en el directorio data/translations/.
        Si el archivo no existe o tiene formato invalido, retorna
        un diccionario vacio y emite un warning.

        Args:
            lang: Codigo de idioma (ej: "es", "en").

        Returns:
            Diccionario con las traducciones cargadas.
        """
        filepath = os.path.join(_TRANSLATIONS_DIR, f"{lang}.json")

        if not os.path.exists(filepath):
            logger.debug(f"Archivo de traducciones no encontrado: {filepath}")
            return {}

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning(
                    f"Traducciones invalidas en {filepath}: "
                    f"se esperaba dict, se obtuvo {type(data).__name__}"
                )
                return {}
            logger.debug(f"Cargadas {len(data)} traducciones para '{lang}'")
            return data
        except json.JSONDecodeError as e:
            logger.warning(f"Error parseando traducciones {filepath}: {e}")
            return {}
        except OSError as e:
            logger.warning(f"Error leyendo traducciones {filepath}: {e}")
            return {}

    def _ensure_loaded(self, lang: str) -> None:
        """Asegura que las traducciones de un idioma estan cargadas.

        Carga las traducciones desde disco si no estan ya en memoria.

        Args:
            lang: Codigo de idioma a cargar.
        """
        with self._translations_lock:
            if lang in self._translations:
                return

        translations = self.load_translations(lang)

        with self._translations_lock:
            self._translations[lang] = translations

    # ----------------------------------------------------------
    # INFORMACION
    # ----------------------------------------------------------

    def available_languages(self) -> list[str]:
        """Lista los idiomas disponibles con archivo de traducciones.

        Escanea el directorio data/translations/ buscando archivos
        JSON con nombre de codigo de idioma.

        Returns:
            Lista de codigos de idioma disponibles (ej: ["es", "en"]).
        """
        languages = []

        if not os.path.isdir(_TRANSLATIONS_DIR):
            return [_DEFAULT_LANGUAGE]

        try:
            for filename in os.listdir(_TRANSLATIONS_DIR):
                if filename.endswith(".json"):
                    lang_code = filename[:-5]  # quitar .json
                    languages.append(lang_code)
        except OSError as e:
            logger.debug(f"Error listando traducciones: {e}")
            return [_DEFAULT_LANGUAGE]

        # Siempre incluir el idioma por defecto
        if _DEFAULT_LANGUAGE not in languages:
            languages.append(_DEFAULT_LANGUAGE)

        return sorted(languages)


# ============================================================
# CONVENIENCE: module-level singleton accessor
# ============================================================

def get_i18n() -> I18n:
    """Retorna la instancia singleton del sistema i18n.

    Returns:
        Instancia unica de I18n.
    """
    return I18n.get()
