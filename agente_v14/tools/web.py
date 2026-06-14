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
v14.8: Seguridad mejorada
       - Validacion de URLs con bloqueo de IPs privadas
       - Limite de tamano de respuesta HTTP (5MB)
       - Timeout configurable (30s por defecto)
       - User-Agent consistente
=============================================================
"""

import json
import time
import hashlib
import logging
import ipaddress
import socket
import re
from urllib.parse import urlparse

from config import WEB_TIMEOUT, logger
from utils.security import sanitize_input, validate_url

# ============================================================
# CONSTANTES DE SEGURIDAD WEB
# ============================================================
WEB_USER_AGENT = "AgentLocal/1.0 (compatible; web-search-tool)"
WEB_RESPONSE_MAX_SIZE = 5 * 1024 * 1024  # 5MB max response body
WEB_DEFAULT_TIMEOUT = 30  # 30 seconds default timeout

# Schemes explicitly blocked
BLOCKED_SCHEMES = {"file", "ftp", "data", "javascript", "vbscript", "blob"}

# Private/internal IP ranges to block
PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),    # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),   # IPv6 link-local
]


def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname resolves to a private/internal IP address.

    Blocks SSRF attacks by preventing requests to internal networks.
    """
    try:
        # Try parsing as IP directly first
        try:
            ip = ipaddress.ip_address(hostname)
            for network in PRIVATE_NETWORKS:
                if ip in network:
                    logger.warning(f"Blocked request to private IP: {hostname}")
                    return True
            return False
        except ValueError:
            pass  # Not a direct IP, try DNS resolution

        # Resolve hostname via DNS
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            for network in PRIVATE_NETWORKS:
                if ip in network:
                    logger.warning(f"Blocked request to private IP (resolved): {hostname} -> {ip_str}")
                    return True
    except (socket.gaierror, OSError, ValueError):
        # Cannot resolve - let it through (will fail at connection time anyway)
        pass
    return False


def _validate_web_url(url: str) -> tuple[bool, str]:
    """Validate a URL for web requests with enhanced security.

    Returns:
        (is_valid, error_message) tuple. If valid, error_message is empty.
    """
    if not url or not url.strip():
        return False, "URL vacia"

    url = url.strip()

    # Check scheme - only http and https allowed
    try:
        parsed = urlparse(url)
    except Exception:
        return False, f"URL con formato invalido: {url[:100]}"

    scheme = parsed.scheme.lower()
    if not scheme:
        return False, f"URL sin esquema: {url[:100]}"

    if scheme in BLOCKED_SCHEMES:
        logger.warning(f"Blocked URL with forbidden scheme: {scheme}:// in {url[:100]}")
        return False, f"Esquema bloqueado: {scheme}://. Solo se permite http:// y https://"

    if scheme not in ("http", "https"):
        return False, f"Esquema no permitido: {scheme}://. Solo se permite http:// y https://"

    # Check for embedded dangerous schemes
    dangerous_patterns = [r"javascript\s*:", r"data\s*:", r"file\s*:", r"vbscript\s*:"]
    for pattern in dangerous_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            logger.warning(f"Blocked URL with embedded dangerous scheme: {url[:100]}")
            return False, f"URL contiene esquema peligroso embebido"

    # Check hostname
    hostname = parsed.hostname
    if not hostname:
        return False, f"URL sin hostname valido: {url[:100]}"

    # Block private/internal IPs (SSRF protection)
    if _is_private_ip(hostname):
        return False, f"URL apunta a IP privada/interna bloqueada: {hostname}"

    return True, ""


def _safe_urlopen(url: str, timeout: int = None) -> bytes:
    """Make a safe HTTP request with URL validation, size limit, and timeout.

    Args:
        url: URL to request (must be http:// or https://)
        timeout: Request timeout in seconds (default: WEB_DEFAULT_TIMEOUT)

    Returns:
        Response body as bytes

    Raises:
        ValueError: If URL is invalid or blocked
        RuntimeError: If response exceeds size limit
    """
    import urllib.request

    # Validate URL
    is_valid, error = _validate_web_url(url)
    if not is_valid:
        raise ValueError(f"URL bloqueada: {error}")

    actual_timeout = timeout or WEB_DEFAULT_TIMEOUT

    req = urllib.request.Request(url, headers={
        "User-Agent": WEB_USER_AGENT,
    })

    with urllib.request.urlopen(req, timeout=actual_timeout) as resp:
        # Read with size limit
        chunks = []
        total_size = 0
        while True:
            chunk = resp.read(65536)  # 64KB chunks
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > WEB_RESPONSE_MAX_SIZE:
                raise RuntimeError(
                    f"Respuesta HTTP excede el limite de 5MB "
                    f"({total_size / (1024*1024):.1f}MB recibidos)"
                )
            chunks.append(chunk)

        return b"".join(chunks)


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
# SOURCE QUALITY SCORING (S6.1)
# ============================================================

# Domains with boosted quality scores
_HIGH_QUALITY_DOMAINS = {
    # Government
    ".gov": 1.5, ".gob": 1.5, ".gov.uk": 1.5, ".gc.ca": 1.5,
    # Education
    ".edu": 1.4, ".ac.uk": 1.4, ".ac.jp": 1.4,
    # Known high-quality tech sites
    "docs.python.org": 1.3, "developer.mozilla.org": 1.3,
    "stackoverflow.com": 1.2, "stackexchange.com": 1.2,
    "github.com": 1.2, "npmjs.com": 1.2,
    "arxiv.org": 1.3, "ieee.org": 1.3, "acm.org": 1.3,
    "wikipedia.org": 1.2, "wikimedia.org": 1.2,
    "microsoft.com": 1.1, "azure.microsoft.com": 1.2,
    "aws.amazon.com": 1.2, "cloud.google.com": 1.2,
    "doc.rust-lang.org": 1.3, "go.dev": 1.3, "kubernetes.io": 1.3,
    # Lower quality domains
    "pinterest.com": 0.5, "reddit.com": 0.8, "quora.com": 0.7,
    "facebook.com": 0.6, "twitter.com": 0.6, "x.com": 0.6,
    "tiktok.com": 0.4, "instagram.com": 0.4,
    "medium.com": 0.7, "dev.to": 0.8, "hackernoon.com": 0.7,
}

# Generic TLD quality scores
_TLD_QUALITY = {
    ".org": 1.1, ".com": 1.0, ".net": 0.9, ".io": 1.0,
    ".info": 0.7, ".biz": 0.5, ".xyz": 0.5, ".top": 0.4,
}


def _score_domain(url: str) -> float:
    """Score a URL's source quality on a 0.0-1.5 scale."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        hostname_lower = hostname.lower()

        # Check specific domains first
        for domain, score in _HIGH_QUALITY_DOMAINS.items():
            if domain.startswith("."):
                if hostname_lower.endswith(domain) or f".{hostname_lower}".endswith(domain):
                    return score
            elif hostname_lower == domain or hostname_lower.endswith(f".{domain}"):
                return score

        # Check TLD
        for tld, score in _TLD_QUALITY.items():
            if hostname_lower.endswith(tld):
                return score

        return 1.0  # Default
    except Exception:
        return 1.0


def _deduplicate_results(results: list) -> list:
    """Remove duplicate domains, keeping the most relevant result per domain."""
    seen_domains = {}
    deduped = []

    for result in results:
        url = result.get("href", result.get("url", ""))
        try:
            hostname = urlparse(url).hostname or ""
            # Remove www. prefix for dedup
            domain_key = hostname.replace("www.", "").lower()
        except Exception:
            domain_key = url

        if domain_key in seen_domains:
            # Keep the one with better quality score
            existing_idx = seen_domains[domain_key]
            existing_score = _score_domain(deduped[existing_idx].get("href", ""))
            new_score = _score_domain(url)
            if new_score > existing_score:
                deduped[existing_idx] = result
        else:
            seen_domains[domain_key] = len(deduped)
            deduped.append(result)

    return deduped


# ============================================================
# AUTO-LEARN FROM SEARCHES (S6.1)
# ============================================================

def _auto_learn_from_search(consulta: str, result_text: str) -> None:
    """After a successful search, store key facts in memory for future recall."""
    try:
        from config import LEARN_DIR
        learn_file = os.path.join(LEARN_DIR, "search_facts.json")

        facts = []
        if os.path.exists(learn_file):
            try:
                with open(learn_file, "r", encoding="utf-8") as f:
                    facts = json.load(f)
            except Exception:
                facts = []

        # Extract a brief fact from the search result (first 200 chars)
        fact_text = result_text[:300].strip()
        if not fact_text:
            return

        entry = {
            "query": consulta[:100],
            "fact": fact_text,
            "timestamp": time.time(),
        }

        # Keep max 100 facts
        facts.append(entry)
        if len(facts) > 100:
            facts = facts[-100:]

        with open(learn_file, "w", encoding="utf-8") as f:
            json.dump(facts, f, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.debug(f"Error auto-learning from search: {e}")


def recall_search_facts(consulta: str) -> str:
    """Recall previously learned facts related to a query."""
    try:
        from config import LEARN_DIR
        learn_file = os.path.join(LEARN_DIR, "search_facts.json")

        if not os.path.exists(learn_file):
            return ""

        with open(learn_file, "r", encoding="utf-8") as f:
            facts = json.load(f)

        # Simple keyword matching
        query_words = set(consulta.lower().split())
        relevant = []
        for fact in facts[-20:]:  # Check last 20 facts
            fact_words = set(fact.get("query", "").lower().split())
            if query_words & fact_words:  # Intersection
                relevant.append(fact.get("fact", ""))

        if relevant:
            return "Hechos recordados:\n" + "\n".join(f"- {r[:150]}" for r in relevant[:3])
        return ""

    except Exception:
        return ""


# ============================================================
# BUSQUEDA WEB PRINCIPAL
# ============================================================
def buscar_web(consulta: str, use_cache: bool = True) -> str:
    """Busca en internet usando duckduckgo-search API con retry y cache.
    Incluye deduplicacion de dominios, scoring de calidad, y auto-aprendizaje.

    Flujo:
    1. Verificar cache
    2. Intentar recordar hechos previos
    3. Buscar via duckduckgo-search (con retry + backoff + dedup + quality scoring)
    4. Fallback: DuckDuckGo Instant Answer API
    5. Auto-aprender de la busqueda
    6. Formatear resultados

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

    # 2. Intentar recordar hechos previos
    recalled = recall_search_facts(consulta)
    if recalled:
        results_parts.append(recalled)

    # 3. Busqueda principal: duckduckgo-search (con dedup y quality scoring)
    ddg_results = _search_ddg(consulta)
    if ddg_results:
        results_parts.append(ddg_results)

    # 4. Fallback: Instant Answer API (resumen rapido)
    instant_results = _search_ddg_instant(consulta)
    if instant_results:
        results_parts.append(instant_results)

    # 5. Si no hay resultados, intentar Wikipedia
    if not results_parts or (len(results_parts) == 1 and results_parts[0] == recalled):
        wiki_results = _search_wikipedia(consulta)
        if wiki_results:
            results_parts.append(wiki_results)

    # Formatear resultado final
    if results_parts:
        full_result = "\n\n".join(results_parts)
        # Almacenar en cache (TTL: 5 min general, 1 min noticias)
        if use_cache:
            _web_cache.put(consulta, full_result)
        # Auto-learn from search
        _auto_learn_from_search(consulta, full_result)
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

            # Deduplicate by domain and sort by quality score
            search_results = _deduplicate_results(search_results)
            search_results.sort(key=lambda r: _score_domain(r.get("href", "")), reverse=True)

            results = ["\U0001f517 Resultados web:"]
            for i, r in enumerate(search_results[:5]):
                title = r.get("title", "").strip()
                href = r.get("href", "")
                body = r.get("body", "").strip()
                quality = _score_domain(href)

                quality_indicator = ""
                if quality >= 1.3:
                    quality_indicator = " \u2b50"  # star for high quality
                elif quality <= 0.7:
                    quality_indicator = " \u26a0"  # warning for low quality

                results.append(f"{i+1}. {title}{quality_indicator}")
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

        encoded = urllib.parse.quote(consulta)
        search_url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(search_url, headers={
            "User-Agent": WEB_USER_AGENT,
        })
        data = _safe_urlopen(search_url, timeout=WEB_DEFAULT_TIMEOUT)
        html = data.decode("utf-8", errors="replace")

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
    except (ValueError, RuntimeError) as e:
        logger.warning(f"DDG scraping bloqueado por seguridad: {e}")
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
        data = _safe_urlopen(url, timeout=WEB_DEFAULT_TIMEOUT)
        data_json = json.loads(data.decode("utf-8"))

        if data_json.get("AbstractText"):
            source_url = data_json.get("AbstractURL", "")
            results.append(f"\U0001f4c4 Resumen: {data_json['AbstractText']}")
            if source_url:
                results.append(f"   Fuente: {source_url}")
        if data_json.get("Answer"):
            results.append(f"\U0001f4a1 Respuesta: {data_json['Answer']}")
        for r in data_json.get("RelatedTopics", [])[:3]:
            if isinstance(r, dict) and r.get("Text"):
                topic_url = r.get("FirstURL", "")
                results.append(f"- {r['Text']}")
                if topic_url:
                    results.append(f"  Link: {topic_url}")
    except (ValueError, RuntimeError) as e:
        logger.warning(f"DDG Instant Answer bloqueado por seguridad: {e}")
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
            data = _safe_urlopen(search_url, timeout=WEB_DEFAULT_TIMEOUT)
            data_json = json.loads(data.decode("utf-8"))

            if data_json and len(data_json) >= 4 and data_json[1]:
                results.append(f"\U0001f4da Wikipedia ({lang.upper()}):")
                for i, title in enumerate(data_json[1][:3]):
                    url = data_json[3][i] if i < len(data_json[3]) else ""
                    results.append(f"  {i+1}. {title}")
                    if url:
                        results.append(f"     {url}")
                break  # Si encuentra en ES, no busca en EN
    except (ValueError, RuntimeError) as e:
        logger.warning(f"Wikipedia search bloqueado por seguridad: {e}")
    except Exception as e:
        logger.debug(f"Wikipedia search fallo: {e}")

    return "\n".join(results) if results else ""
