"""
=============================================================
AGENTE v14 - Herramienta de Busqueda Web
=============================================================
buscar_web: Busca en internet usando DuckDuckGo API.
=============================================================
"""

import json

from config import WEB_TIMEOUT, logger


def buscar_web(consulta: str) -> str:
    """Busca en internet usando DuckDuckGo API."""
    try:
        import urllib.request
        import urllib.parse
        encoded = urllib.parse.quote(consulta)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=WEB_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []
        if data.get("AbstractText"):
            results.append(f"Resumen: {data['AbstractText']}")
        if data.get("Answer"):
            results.append(f"Respuesta: {data['Answer']}")
        for r in data.get("RelatedTopics", [])[:5]:
            if isinstance(r, dict) and r.get("Text"):
                results.append(f"- {r['Text']}")

        if results:
            return "\n".join(results)
        return "No se encontraron resultados. Intenta con otra consulta."
    except Exception as e:
        return f"ERROR en busqueda web: {e}"
