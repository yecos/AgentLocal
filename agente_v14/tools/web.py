"""
=============================================================
AGENTE v14 - Herramientas de Busqueda Web MEJORADAS
=============================================================
buscar_web: Busca en internet (DuckDuckGo + SearXNG fallback)
leer_web: Lee el contenido de una URL y extrae texto util
buscar_web_profundo: Busca + lee las mejores paginas automaticamente
v15: Busqueda agresiva, nunca se rinde, aprende de lo que encuentra
=============================================================
"""

import json
import logging
import re

from config import WEB_TIMEOUT, logger, LEARN_DIR
from utils.security import sanitize_input, validate_url


def buscar_web(consulta: str) -> str:
    """Busca en internet usando DuckDuckGo API y SearXNG. Retorna resultados con links y contexto."""
    consulta = sanitize_input(consulta)
    results = []
    
    # 1. Intentar DuckDuckGo Instant Answer API (resumen + related)
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
            results.append(f"Resumen: {data['AbstractText']}")
            if source_url:
                results.append(f"Fuente: {source_url}")
        if data.get("Answer"):
            results.append(f"Respuesta directa: {data['Answer']}")
        for r in data.get("RelatedTopics", [])[:5]:
            if isinstance(r, dict) and r.get("Text"):
                topic_url = r.get("FirstURL", "")
                results.append(f"- {r['Text']}")
                if topic_url:
                    results.append(f"  Link: {topic_url}")
    except Exception as e:
        logger.debug(f"DDG Instant Answer fallo: {e}")

    # 2. DuckDuckGo HTML Search para resultados reales con links
    found_urls = []
    try:
        import urllib.request
        import urllib.parse
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
            results.append("\nResultados web:")
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
                
                found_urls.append(actual_url)
                results.append(f"{i+1}. {clean_title}")
                if snippet_text:
                    results.append(f"   {snippet_text[:150]}")
                results.append(f"   {actual_url}")
    except Exception as e:
        logger.debug(f"DDG HTML search fallo: {e}")

    # 3. SearXNG fallback (si hay instancia local disponible)
    if not results or len(results) < 3:
        searxng_results = _buscar_searxng(consulta)
        if searxng_results:
            results.append("\nResultados SearXNG:")
            results.extend(searxng_results)
            for line in searxng_results:
                if line.startswith("   http"):
                    found_urls.append(line.strip())

    # 4. Wikipedia en espanol como fuente adicional de conocimiento
    wiki_result = _buscar_wikipedia(consulta)
    if wiki_result:
        results.insert(0, f"WIKIPEDIA: {wiki_result}")

    if results:
        result_text = "\n".join(results)
        # Guardar las URLs encontradas como metadata para buscar_web_profundo
        _save_search_urls(consulta, found_urls[:3])
        return result_text
    return "No se encontraron resultados. Intenta con otra consulta o usa buscar_web_profundo para una busqueda mas profunda."


def leer_web(url: str) -> str:
    """Lee el contenido de una URL y extrae el texto util. Usa la herramienta para obtener informacion detallada de una pagina web.
    
    Args:
        url: URL de la pagina web a leer
    """
    url = url.strip()
    
    # Si no empieza con http, agregarlo
    if not url.startswith("http"):
        url = "https://" + url
    
    # Validar URL
    if not validate_url(url):
        return "URL no valida. Usa formato: https://ejemplo.com"

    try:
        import urllib.request
        
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es,en;q=0.5",
        })
        
        with urllib.request.urlopen(req, timeout=15) as resp:
            # Verificar que es HTML (no PDF, imagen, etc.)
            content_type = resp.headers.get("Content-Type", "")
            if "text" not in content_type and "html" not in content_type:
                return f"La URL no es una pagina web (Content-Type: {content_type}). No se puede leer."
            
            html = resp.read().decode("utf-8", errors="replace")
        
        # Extraer texto del HTML
        text = _html_to_text(html, url)
        
        if not text or len(text) < 50:
            return "La pagina no contiene texto util o esta protegida contra lectura."
        
        # Guardar en memoria para aprendizaje
        _save_web_content(url, text[:500])
        
        return text[:4000]  # Limitar a 4000 chars para no saturar el contexto
        
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return f"Acceso denegado (403). La pagina bloquea solicitudes automaticas. Prueba con otra URL."
        if e.code == 404:
            return f"Pagina no encontrada (404). La URL puede estar desactualizada."
        return f"Error HTTP {e.code} al leer la pagina. Prueba con otra URL."
    except urllib.error.URLError as e:
        return f"Error de conexion: {e.reason}. Verifica tu conexion a internet."
    except Exception as e:
        return f"Error leyendo la pagina: {str(e)[:200]}"


def buscar_web_profundo(consulta: str) -> str:
    """Busqueda profunda: busca en internet, lee las mejores paginas y retorna informacion detallada.
    Usa esta herramienta cuando buscar_web no fue suficiente o necesitas informacion mas detallada.
    
    Args:
        consulta: Lo que quieres buscar en detalle
    """
    consulta = sanitize_input(consulta)
    logger.info(f"Busqueda profunda iniciada: {consulta}")
    
    # 1. Buscar normalmente primero
    search_results = buscar_web(consulta)
    
    # 2. Obtener URLs de la busqueda anterior
    urls = _load_search_urls(consulta)
    
    if not urls:
        # Intentar extraer URLs del texto de resultados
        urls = _extract_urls_from_text(search_results)
    
    if not urls:
        return f"RESULTADO DE BUSQUEDA (sin profundizar):\n{search_results}\n\nNo se encontraron URLs para profundizar. Prueba con otra consulta."
    
    # 3. Leer las 2 mejores paginas (para no tardar mucho)
    detailed_results = [f"BUSQUEDA PROFUNDA: {consulta}\n"]
    detailed_results.append(f"Resultados basicos:\n{search_results[:1000]}\n")
    detailed_results.append("--- CONTENIDO PROFUNDO ---\n")
    
    pages_read = 0
    for url in urls[:2]:
        try:
            content = leer_web(url)
            if content and not content.startswith("Error") and not content.startswith("Acceso denegado") and len(content) > 100:
                pages_read += 1
                # Extraer solo las partes mas relevantes
                relevant = _extract_relevant_sections(content, consulta)
                detailed_results.append(f"--- De {url} ---")
                detailed_results.append(relevant[:2000])
                detailed_results.append("")
        except Exception as e:
            logger.debug(f"Error leyendo {url}: {e}")
            continue
    
    if pages_read == 0:
        detailed_results.append("No se pudo leer ninguna pagina en detalle. Los resultados basicos pueden ser suficientes.")
    
    # 4. Guardar conocimiento aprendido
    _auto_learn_from_search(consulta, search_results, detailed_results)
    
    result = "\n".join(detailed_results)
    return result[:6000]  # Limitar para no saturar contexto


# ============================================================
# FUNCIONES AUXILIARES PRIVADAS
# ============================================================

def _html_to_text(html: str, source_url: str = "") -> str:
    """Convierte HTML a texto limpio, eliminando scripts, estilos, y tags."""
    # Eliminar scripts, estilos, nav, footer, header, sidebar
    for tag in ['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript', 'iframe']:
        html = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', html, flags=re.DOTALL | re.IGNORECASE)
    
    # Eliminar comentarios HTML
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
    
    # Preservar estructura de titulos y parrafos
    html = re.sub(r'<h[1-6][^>]*>', '\n\n## ', html, flags=re.IGNORECASE)
    html = re.sub(r'</h[1-6]>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<p[^>]*>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<br[^>]*/?\s*>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<li[^>]*>', '\n- ', html, flags=re.IGNORECASE)
    html = re.sub(r'<div[^>]*>', '\n', html, flags=re.IGNORECASE)
    
    # Eliminar todos los tags restantes
    text = re.sub(r'<[^>]+>', '', html)
    
    # Decodificar entidades HTML
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    text = text.replace('&nbsp;', ' ')
    # Entidades numericas
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
    
    # Limpiar espacios y lineas multiples
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    
    # Elimar lineas muy cortas (menus, etc.)
    lines = text.split('\n')
    meaningful_lines = []
    for line in lines:
        stripped = line.strip()
        # Mantener lineas con contenido real (mas de 20 chars o que son bullets)
        if len(stripped) > 20 or stripped.startswith('-') or stripped.startswith('##'):
            meaningful_lines.append(stripped)
    
    result = '\n'.join(meaningful_lines).strip()
    
    if source_url:
        result = f"[Fuente: {source_url}]\n\n{result}"
    
    return result


def _extract_urls_from_text(text: str) -> list:
    """Extrae URLs de un texto de resultados de busqueda."""
    urls = []
    url_pattern = r'https?://[^\s<>"\)]+'
    for match in re.finditer(url_pattern, text):
        url = match.group(0)
        # Filtrar URLs no utiles
        skip_domains = ['duckduckgo.com', 'google.com', 'bing.com', 'youtube.com']
        if not any(domain in url for domain in skip_domains):
            urls.append(url)
    return urls[:5]


def _buscar_searxng(consulta: str) -> list:
    """Busca usando SearXNG local (si esta disponible via Docker)."""
    try:
        import urllib.request
        import urllib.parse
        
        # Intentar instancia local primero, luego publica
        searxng_urls = [
            "http://localhost:8080/search",
            "http://localhost:8888/search", 
            "https://searx.be/search",
            "https://search.sapti.me/search",
        ]
        
        encoded = urllib.parse.quote(consulta)
        
        for base_url in searxng_urls:
            try:
                url = f"{base_url}?q={encoded}&format=json&language=es"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                
                results = []
                for r in data.get("results", [])[:5]:
                    title = r.get("title", "")
                    content = r.get("content", "")
                    result_url = r.get("url", "")
                    results.append(f"- {title}")
                    if content:
                        results.append(f"   {content[:150]}")
                    if result_url:
                        results.append(f"   {result_url}")
                
                if results:
                    logger.info(f"SearXNG exitoso: {base_url}")
                    return results
            except Exception:
                continue
        
        return []
    except Exception as e:
        logger.debug(f"SearXNG no disponible: {e}")
        return []


def _buscar_wikipedia(consulta: str) -> str:
    """Busca en Wikipedia en espanol para obtener resumos enciclopedicos."""
    try:
        import urllib.request
        import urllib.parse
        
        # Buscar en Wikipedia API
        encoded = urllib.parse.quote(consulta)
        url = f"https://es.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "AgenteLocal/1.0"})
        
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        
        extract = data.get("extract", "")
        if extract and len(extract) > 50:
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
            result = extract[:500]
            if page_url:
                result += f"\nMas info: {page_url}"
            return result
        
        # Si no hay extract, intentar buscar paginas relacionadas
        search_url = f"https://es.wikipedia.org/w/api.php?action=opensearch&search={encoded}&limit=3&format=json"
        req = urllib.request.Request(search_url, headers={"User-Agent": "AgenteLocal/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            search_data = json.loads(resp.read().decode("utf-8"))
        
        if search_data and len(search_data) >= 4:
            titles = search_data[1]
            urls = search_data[3]
            if titles:
                result_parts = []
                for title, wiki_url in zip(titles[:2], urls[:2]):
                    result_parts.append(f"{title}: {wiki_url}")
                return "Paginas relacionadas: " + " | ".join(result_parts)
        
        return ""
    except Exception as e:
        logger.debug(f"Wikipedia fallo: {e}")
        return ""


def _extract_relevant_sections(text: str, query: str) -> str:
    """Extrae las secciones mas relevantes de un texto largo basado en la consulta."""
    query_words = set(w.lower() for w in query.split() if len(w) > 3)
    if not query_words:
        return text[:2000]
    
    lines = text.split('\n')
    relevant_lines = []
    
    # Buscar lineas que contengan palabras de la query
    for i, line in enumerate(lines):
        line_lower = line.lower()
        word_matches = sum(1 for w in query_words if w in line_lower)
        
        if word_matches >= 1:
            # Incluir contexto alrededor (2 lineas antes y despues)
            start = max(0, i - 2)
            end = min(len(lines), i + 3)
            for j in range(start, end):
                if lines[j] not in relevant_lines:
                    relevant_lines.append(lines[j])
    
    if relevant_lines:
        return '\n'.join(relevant_lines)
    
    # Si no encontro nada relevante, devolver las primeras lineas
    return text[:2000]


def _save_search_urls(consulta: str, urls: list):
    """Guarda las URLs encontradas en una busqueda para uso posterior."""
    try:
        import os
        cache_file = os.path.join(LEARN_DIR, "search_urls.json")
        cache = {}
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
        
        # Guardar con hash de la consulta como clave
        key = consulta[:50].lower().strip()
        cache[key] = {
            "urls": urls,
            "timestamp": __import__("datetime").datetime.now().isoformat()
        }
        
        # Limpiar cache viejo (mas de 100 entradas)
        if len(cache) > 100:
            sorted_items = sorted(cache.items(), key=lambda x: x[1].get("timestamp", ""), reverse=True)
            cache = dict(sorted_items[:50])
        
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"Error guardando URLs de busqueda: {e}")


def _load_search_urls(consulta: str) -> list:
    """Carga las URLs guardadas de una busqueda anterior."""
    try:
        import os
        cache_file = os.path.join(LEARN_DIR, "search_urls.json")
        if not os.path.exists(cache_file):
            return []
        
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
        
        key = consulta[:50].lower().strip()
        if key in cache:
            return cache[key].get("urls", [])
        
        # Busqueda fuzzy: si alguna clave es substring de la consulta
        for k, v in cache.items():
            if k in consulta.lower() or consulta.lower() in k:
                return v.get("urls", [])
    except Exception:
        pass
    return []


def _save_web_content(url: str, content_preview: str):
    """Guarda un resumen del contenido web para aprendizaje futuro."""
    try:
        import os
        web_cache_file = os.path.join(LEARN_DIR, "web_knowledge.json")
        cache = []
        if os.path.exists(web_cache_file):
            with open(web_cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
        
        # Verificar si ya existe
        for entry in cache:
            if entry.get("url") == url:
                entry["content"] = content_preview
                entry["updated"] = __import__("datetime").datetime.now().isoformat()
                break
        else:
            cache.append({
                "url": url,
                "content": content_preview,
                "created": __import__("datetime").datetime.now().isoformat()
            })
        
        # Mantener solo las 200 mas recientes
        cache = cache[-200:]
        
        with open(web_cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"Error guardando contenido web: {e}")


def _auto_learn_from_search(consulta: str, basic_results: str, deep_results: list):
    """Guarda automaticamente conocimiento aprendido de busquedas web."""
    try:
        import os
        from datetime import datetime
        
        knowledge_file = os.path.join(LEARN_DIR, "web_learned.json")
        knowledge = []
        if os.path.exists(knowledge_file):
            with open(knowledge_file, "r", encoding="utf-8") as f:
                knowledge = json.load(f)
        
        # Extraer informacion clave de los resultados
        combined = "\n".join(deep_results)
        
        # Solo guardar si encontramos algo significativo
        if len(combined) > 200:
            knowledge.append({
                "query": consulta[:100],
                "summary": combined[:800],
                "basic_results": basic_results[:300],
                "learned_at": datetime.now().isoformat(),
                "times_used": 1
            })
        
        # Mantener solo las 300 mas recientes
        knowledge = knowledge[-300:]
        
        with open(knowledge_file, "w", encoding="utf-8") as f:
            json.dump(knowledge, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"Error en auto-learn: {e}")


def get_web_learned(query: str) -> str:
    """Busca conocimiento previamente aprendido de busquedas web."""
    try:
        import os
        knowledge_file = os.path.join(LEARN_DIR, "web_learned.json")
        if not os.path.exists(knowledge_file):
            return ""
        
        with open(knowledge_file, "r", encoding="utf-8") as f:
            knowledge = json.load(f)
        
        query_lower = query.lower()
        relevant = []
        for entry in knowledge:
            if any(w in entry.get("query", "").lower() for w in query_lower.split() if len(w) > 3):
                relevant.append(entry)
        
        if not relevant:
            return ""
        
        # Retornar el mas relevante
        best = relevant[-1]
        best["times_used"] = best.get("times_used", 0) + 1
        
        # Actualizar archivo
        try:
            with open(knowledge_file, "w", encoding="utf-8") as f:
                json.dump(knowledge, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        
        return f"[CONOCIMIENTO WEB APRENDIDO de busqueda '{best['query']}']:\n{best.get('summary', '')[:500]}"
    except Exception:
        return ""
