"""
=============================================================
AGENTE v14 - Herramienta de Busqueda Web
=============================================================
buscar_web: Busca en internet usando DuckDuckGo.
v14.4: Resultados reales con links, no solo resumen.
=============================================================
"""

import json
import logging

from config import WEB_TIMEOUT, logger
from utils.security import sanitize_input


def buscar_web(consulta: str) -> str:
    """Busca en internet usando DuckDuckGo API. Retorna resultados con links."""
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
            results.append(f"📄 Resumen: {data['AbstractText']}")
            if source_url:
                results.append(f"   Fuente: {source_url}")
        if data.get("Answer"):
            results.append(f"💡 Respuesta: {data['Answer']}")
        for r in data.get("RelatedTopics", [])[:5]:
            if isinstance(r, dict) and r.get("Text"):
                topic_url = r.get("FirstURL", "")
                results.append(f"- {r['Text']}")
                if topic_url:
                    results.append(f"  Link: {topic_url}")
    except Exception as e:
        logger.debug(f"DDG Instant Answer fallo: {e}")

    # 2. Intentar DuckDuckGo HTML Search para resultados reales con links
    try:
        import urllib.request
        import urllib.parse
        import re
        encoded = urllib.parse.quote(consulta)
        # DDG Lite (HTML) para obtener links reales
        search_url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(search_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=WEB_TIMEOUT) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Parsear resultados del HTML
        link_pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)">(.*?)</a>'
        snippet_pattern = r'<a class="result__snippet"[^>]*>(.*?)</a>'
        
        links = re.findall(link_pattern, html, re.DOTALL)[:6]
        snippets = re.findall(snippet_pattern, html, re.DOTALL)[:6]
        
        if links:
            results.append("\n🔗 Resultados web:")
            for i, (link, title) in enumerate(links[:5]):
                # Limpiar HTML del titulo
                clean_title = re.sub(r'<[^>]+>', '', title).strip()
                # Limpiar URL (DDG usa redirect)
                clean_link = urllib.parse.unquote(link)
                # Extraer URL real del redirect de DDG
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
        logger.debug(f"DDG HTML search fallo: {e}")

    if results:
        return "\n".join(results)
    return "No se encontraron resultados. Intenta con otra consulta."
