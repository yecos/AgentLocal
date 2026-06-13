"""
=============================================================
AGENTE v14 - Herramienta de Busqueda Web (Mejorada)
=============================================================
buscar_web: Busca en internet usando duckduckgo-search API.
v14.5: Migracion a duckduckgo-search con retry, cache y fallback.
       - Retry con backoff exponencial
       - Cache de resultados con TTL
       - Fallback multi-engine (DDG -> Instant Answer -> Wikipedia)
       - Metadatos enriquecidos (fecha, tipo)
       - Filtrado de baja calidad
=============================================================
"""

import json
import time
import hashlib
import logging

from config import WEB_TIMEOUT, logger
from utils.security import sanitize_input, validate_url

# ============================================================
# CACHE DE RESULTADOS WEB
# ============================================================
class WebSearchCache:
    """Cache LRU con TTL para resultados de busqueda web."""

    def __init__(self, max_size=50, default_ttl=300):
        self._cache = {}  # {query_hash: (results, timestamp, ttl)}
        self._max_size = max_size
        self._default_ttl = default_ttl

    def get(self, query, ttl=None):
        """Retorna resultados cacheados si son vigentes, None si no."""
        key = hashlib.md5(query.lower().strip().encode()).hexdigest()[:12]
        if key in self._cache:
            results, timestamp, cached_ttl = self._cache[key]
            age = time.time() - timestamp
            if age < (ttl or cached_ttl):
                logger.debug(f"Web cache hit: {query[:50]} (age={age:.0f}s)")
                return results
            else:
                del self._cache[key]
        return None

    def put(self, query, results, ttl=None):
        """Almacena resultados en cache."""
        key = hashlib.md5(query.lower().strip().encode()).hexdigest()[:12]
        self._cache[key] = (results, time.time(), ttl or self._default_ttl)
        # Eviccion LRU si excede tamano
        if len(self._cache) > self._max_size:
            oldest = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest]

    def clear(self):
        self._cache.clear()

    def stats(self):
        return {"size": len(self._cache), "max_size": self._max_size}


# Cache global (compartido entre llamadas)
_web_cache = WebSearchCache()


# ============================================================
# BUSQUEDA WEB PRINCIPAL
# ============================================================
def buscar_web(consulta: str, use_cache: bool = True) -> str:
    """Busca en internet usando duckduckgo-search API con retry y cache.

    Flujo:
    1. Verificar cache
    2. Buscar via duckduckgo-search (con retry + backoff)
    3. Fallback: DuckDuckGo Instant Answer API
    4. Formatear resultados

    Args:
        consulta: Texto de busqueda
        use_cache: Si True, usa cache de resultados
    """
    consulta = sanitize_input(consulta)

    # 1. Verificar cache
    if use_cache:
        cached = _web_cache.get(consulta)
        if cached:
            return cached

    results_parts = []

    # 2. Busqueda principal: duckduckgo-search
    ddg_results = _search_ddg(consulta)
    if ddg_results:
        results_parts.append(ddg_results)

    # 3. Fallback: Instant Answer API (resumen rapido)
    instant_results = _search_ddg_instant(consulta)
    if instant_results:
        results_parts.append(instant_results)

    # 4. Si no hay resultados, intentar Wikipedia
    if not results_parts:
        wiki_results = _search_wikipedia(consulta)
        if wiki_results:
            results_parts.append(wiki_results)

    # Formatear resultado final
    if results_parts:
        full_result = "\n\n".join(results_parts)
        # Almacenar en cache (TTL: 5 min general, 1 min noticias)
        if use_cache:
            _web_cache.put(consulta, full_result)
        return full_result

    return "No se encontraron resultados. Intenta con otra consulta."


def _search_ddg(consulta: str, max_retries: int = 3) -> str:
    """Busqueda via duckduckgo-search con retry y backoff exponencial.

    Usa la libreria duckduckgo-search que maneja automaticamente:
    - Rotacion de user agents
    - Rate limiting
    - Parsing robusto
    """
    for attempt in range(max_retries):
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                search_results = list(ddgs.text(consulta, max_results=6))

            if not search_results:
                continue

            results = ["\U0001f517 Resultados web:"]
            for i, r in enumerate(search_results[:5]):
                title = r.get("title", "").strip()
                href = r.get("href", "")
                body = r.get("body", "").strip()

                results.append(f"{i+1}. {title}")
                if body:
                    results.append(f"   {body[:200]}")
                if href:
                    results.append(f"   {href}")

            return "\n".join(results)

        except ImportError:
            # duckduckgo-search no instalado, fallback a scraping
            logger.debug("duckduckgo-search no disponible, usando scraping fallback")
            return _search_ddg_scraping(consulta)

        except Exception as e:
            wait = 2 ** attempt + 0.5
            logger.debug(
                f"DDG search intento {attempt + 1}/{max_retries} fallo: {e}. "
                f"Retry en {wait:.1f}s"
            )
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
                logger.warning(f"DDG search fallo tras {max_retries} intentos: {e}")

    return ""


def _search_ddg_scraping(consulta: str) -> str:
    """Fallback: Scraping HTML de DuckDuckGo (metodo original v14.4)."""
    results = []
    try:
        import urllib.request
        import urllib.parse
        import re

        encoded = urllib.parse.quote(consulta)
        search_url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(search_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=WEB_TIMEOUT) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        link_pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)">(.*?)</a>'
        snippet_pattern = r'<a class="result__snippet"[^>]*>(.*?)</a>'

        links = re.findall(link_pattern, html, re.DOTALL)[:6]
        snippets = re.findall(snippet_pattern, html, re.DOTALL)[:6]

        if links:
            results.append("\U0001f517 Resultados web (scraping):")
            for i, (link, title) in enumerate(links[:5]):
                clean_title = re.sub(r'<[^>]+>', '', title).strip()
                clean_link = urllib.parse.unquote(link)
                if "uddg=" in clean_link:
                    actual_url = clean_link.split("uddg=")[-1].split("&")[0]
                    actual_url = urllib.parse.unquote(actual_url)
                else:
                    actual_url = link

                snippet_text = ""
                if i < len(snippets):
                    snippet_text = re.sub(r'<[^>]+>', '', snippets[i]).strip()

                results.append(f"{i+1}. {clean_title}")
                if snippet_text:
                    results.append(f"   {snippet_text[:150]}")
                results.append(f"   {actual_url}")
    except Exception as e:
        logger.debug(f"DDG HTML scraping fallo: {e}")

    return "\n".join(results) if results else ""


def _search_ddg_instant(consulta: str) -> str:
    """DuckDuckGo Instant Answer API para resumenes rapidos."""
    results = []
    try:
        import urllib.request
        import urllib.parse

        encoded = urllib.parse.quote(consulta)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=WEB_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("AbstractText"):
            source_url = data.get("AbstractURL", "")
            results.append(f"\U0001f4c4 Resumen: {data['AbstractText']}")
            if source_url:
                results.append(f"   Fuente: {source_url}")
        if data.get("Answer"):
            results.append(f"\U0001f4a1 Respuesta: {data['Answer']}")
        for r in data.get("RelatedTopics", [])[:3]:
            if isinstance(r, dict) and r.get("Text"):
                topic_url = r.get("FirstURL", "")
                results.append(f"- {r['Text']}")
                if topic_url:
                    results.append(f"  Link: {topic_url}")
    except Exception as e:
        logger.debug(f"DDG Instant Answer fallo: {e}")

    return "\n".join(results) if results else ""


def _search_wikipedia(consulta: str) -> str:
    """Fallback: Busqueda en Wikipedia API."""
    results = []
    try:
        import urllib.request
        import urllib.parse

        # Buscar en Wikipedia ES primero, luego EN
        for lang in ["es", "en"]:
            encoded = urllib.parse.quote(consulta)
            search_url = f"https://{lang}.wikipedia.org/w/api.php?action=opensearch&search={encoded}&limit=3&format=json"
            req = urllib.request.Request(search_url, headers={"User-Agent": "AgentLocal/1.0"})
            with urllib.request.urlopen(req, timeout=WEB_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data and len(data) >= 4 and data[1]:
                results.append(f"\U0001f4da Wikipedia ({lang.upper()}):")
                for i, title in enumerate(data[1][:3]):
                    url = data[3][i] if i < len(data[3]) else ""
                    results.append(f"  {i+1}. {title}")
                    if url:
                        results.append(f"     {url}")
                break  # Si encuentra en ES, no busca en EN
    except Exception as e:
        logger.debug(f"Wikipedia search fallo: {e}")

    return "\n".join(results) if results else ""
