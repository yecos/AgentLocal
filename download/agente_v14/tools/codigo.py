"""
=============================================================
AGENTE v14 - Herramienta de Generacion de Codigo
=============================================================
generar_codigo: Usa el LLM para generar codigo y lo guarda en archivo.
=============================================================
"""

import os
import re

from config import REPOS_DIR, CODE_GEN_PROMPTS, CODE_EXT_MAP, IS_WINDOWS
from tools.archivos import escribir_archivo
from tools.sistema import ejecutar_comando
from llm import ollama


def generar_codigo(descripcion: str, tipo: str, ruta: str = "") -> str:
    """Genera codigo/texto completo usando el LLM y lo guarda en un archivo."""
    if not ruta:
        ext = CODE_EXT_MAP.get(tipo, ".txt")
        safe_name = re.sub(r'[^a-z0-9]', '_', descripcion[:30].lower()).strip('_')
        ruta = os.path.join(REPOS_DIR, f"{safe_name}{ext}")
    else:
        ruta = ruta.replace("REPOS_DIR", REPOS_DIR)

    system_prompt = CODE_GEN_PROMPTS.get(tipo, "Genera contenido completo y funcional. Responde SOLO con el contenido.")

    # Usar modelo de codigo (potente)
    contenido = ollama.generate_code([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Crea: {descripcion}"}
    ])

    if not contenido:
        return "ERROR: No se pudo generar contenido (Ollama no responde)"

    # Limpiar markdown code blocks
    contenido = contenido.strip()
    if contenido.startswith("```"):
        contenido = re.sub(r'^```[a-z]*\n?', '', contenido)
        contenido = re.sub(r'\n?```$', '', contenido)
        contenido = contenido.strip()

    resultado = escribir_archivo(ruta, contenido)
    if "ERROR" in resultado:
        return resultado

    # Si es HTML, abrir en navegador
    if tipo == "html" and IS_WINDOWS:
        ejecutar_comando(f'start "" "{ruta}"')
        return f"Contenido generado y guardado en: {ruta}\nAbierto en el navegador automaticamente!"

    size_kb = len(contenido) / 1024
    return f"Contenido generado ({size_kb:.1f}KB) y guardado en: {ruta}"
