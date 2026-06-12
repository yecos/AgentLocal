"""
=============================================================
AGENTE v19 - Direct Intent Parser
=============================================================
Detecta la intención del usuario y ejecuta herramientas directamente
SIN depender de que el LLM genere JSON válido.

Problema que resuelve:
  Los modelos locales pequeños (qwen3:4b, llama3:8b) frecuentemente
  fallan en generar JSON con formato exacto. El agente se queda
  "pensando" pero nunca ejecuta nada.

Solución:
  Pattern matching directo sobre el mensaje del usuario para
  detectar intención y ejecutar la herramienta correcta.
  Solo recurre al LLM cuando la intención es ambigua.

v19: Primera versión con 20+ patrones de intención.
=============================================================
"""

import re
import os
import logging
from typing import Optional, Tuple, Dict, Any

from config import REPOS_DIR, logger

# ============================================================
# PATRONES DE INTENCIÓN
# ============================================================

# Cada patrón: (regex, tool_name, param_mapping, confidence)
# confidence: 1.0 = certeza absoluta, 0.7 = bastante seguro, 0.5 = probable

INTENT_PATTERNS = [
    # --- LISTAR ARCHIVOS ---
    (r'(?:lista|listar|ver|mostrar|muestra)\s+(?:los\s+)?(?:archivos|carpetas|contenido|directorios|ficheros)(?:\s+(?:de|en|del)\s+(.+))?',
     "listar_archivos", {"ruta": 1}, 0.95),
    (r'(?:que\s+hay\s+en|que\s+contiene)\s+(.+)',
     "listar_archivos", {"ruta": 1}, 0.90),
    (r'^ls\s*(.*)',
     "listar_archivos", {"ruta": 1}, 0.95),
    (r'^dir\s*(.*)',
     "listar_archivos", {"ruta": 1}, 0.90),

    # --- LEER ARCHIVO ---
    (r'(?:lee|leer|mostrar|ver|abrir|muestra)\s+(?:el\s+)?(?:archivo|contenido|fichero)\s+(.+)',
     "leer_archivo", {"ruta": 1}, 0.90),
    (r'(?:muestra|ver|lee)\s+(?:lo\s+que\s+tiene|el\s+contenido\s+de)\s+(.+)',
     "leer_archivo", {"ruta": 1}, 0.85),
    (r'^cat\s+(.+)',
     "leer_archivo", {"ruta": 1}, 0.95),
    (r'^type\s+(.+)',
     "leer_archivo", {"ruta": 1}, 0.90),

    # --- ESCRIBIR ARCHIVO ---
    (r'(?:escribir|crear|guardar|generar)\s+(?:un\s+)?(?:archivo|fichero)\s+(.+?)(?:\s+con\s+(.+))?$',
     "escribir_archivo", {"ruta": 1, "contenido": 2}, 0.85),

    # --- EJECUTAR COMANDO ---
    (r'(?:ejecuta|ejecutar|corre| correr|run)\s+(?:el\s+)?(?:comando|cmd|orden)?\s*:?\s*(.+)',
     "ejecutar_comando", {"comando": 1}, 0.90),
    (r'^\$?\s*(?:npm|npx|pip|python|node|bun|git|docker|cargo|go|make|bash|sh)\s+(.+)',
     "ejecutar_comando", {"comando": 0}, 0.90),

    # --- BUSCAR EN WEB ---
    (r'(?:busca|buscar|consulta|consultar|googlea|googlear)\s+(?:en\s+(?:internet|la\s+web|google|linea))?\s*(.+)',
     "buscar_web", {"consulta": 1}, 0.90),
    (r'(?:que\s+es|quien\s+es|como\s+(?:se|funciona)|donde\s+(?:esta|encuentro)|cuando\s+(?:es|fue))\s+(.+)',
     "buscar_web", {"consulta": 0}, 0.70),
    (r'(?:busca|buscar)\s+(.+?)(?:\s+en\s+(?:internet|la\s+web))?$',
     "buscar_web", {"consulta": 1}, 0.85),

    # --- LEER WEB ---
    (r'(?:lee|leer|abrir|ver|descarga)\s+(?:la\s+)?(?:pagina|web|url|sitio|link|articulo)\s+(.+)',
     "leer_web", {"url": 1}, 0.85),
    (r'(?:lee|leer)\s+(?:el\s+)?(?:contenido\s+de\s+)?(?:https?://\S+)',
     "leer_web", {"url": 0}, 0.90),

    # --- PROCESOS ---
    (r'(?:muestra|ver|lista|listar)\s+(?:los\s+)?(?:procesos|programas|apps|aplicaciones)',
     "procesos_activos", {}, 0.90),
    (r'(?:mata|cerrar|terminar|kill|detener)\s+(?:el\s+)?(?:proceso|programa|app)\s+(.+)',
     "matar_proceso", {"pid_o_nombre": 1}, 0.90),

    # --- CLONAR REPO ---
    (r'(?:clona|clonar|descarga|descargar)\s+(?:el\s+)?(?:repo|repositorio)\s+(.+)',
     "clonar_repositorio", {"url": 1}, 0.90),
    (r'(?:clona|clonar)\s+(https?://github\.com/\S+)',
     "clonar_repositorio", {"url": 1}, 0.95),

    # --- ABRIR APP ---
    (r'(?:abre|abrir|lanza|inicia|ejecuta)\s+(?:la\s+)?(?:app|aplicacion|programa)\s+(.+)',
     "abrir_aplicacion", {"app": 1}, 0.85),
    (r'(?:abre|abrir|lanza|inicia)\s+(chrome|firefox|vscode|word|excel|powerpoint|photoshop|illustrator|blender|figma|telegram|whatsapp|notepad|spotify|discord|steam|obs|blender|sketchup)(?:\s+.*)?$',
     "abrir_aplicacion", {"app": 1}, 0.90),

    # --- ABRIR URL ---
    (r'(?:abre|abrir|ve|navega)\s+(?:a\s+)?(?:la\s+)?(?:url|pagina|web|sitio)\s+(.+)',
     "abrir_url", {"url": 1}, 0.85),
    (r'(?:abre|abrir|ve|navega)\s+(https?://\S+)',
     "abrir_url", {"url": 1}, 0.95),

    # --- ANALIZAR PROYECTO ---
    (r'(?:analiza|analizar|revisa|revisar|audita|auditar|inspecciona)\s+(?:el\s+)?(?:proyecto|repo|repositorio|codigo)\s+(.+)',
     "analizar_proyecto", {"ruta": 1}, 0.85),

    # --- INSTALAR DEPENDENCIAS ---
    (r'(?:instala|instalar)\s+(?:las\s+)?(?:dependencias|deps|paquetes)(?:\s+(?:de|en)\s+(.+))?',
     "instalar_dependencias", {"ruta": 1}, 0.90),
    (r'^npm\s+install',
     "ejecutar_comando", {"comando": 0}, 0.95),
    (r'^pip\s+install\s+(.+)',
     "ejecutar_comando", {"comando": 0}, 0.95),
    (r'^bun\s+install',
     "ejecutar_comando", {"comando": 0}, 0.95),

    # --- BUSCAR EN ARCHIVOS ---
    (r'(?:busca|buscar|encuentra|encontrar)\s+(.+?)\s+(?:en\s+(?:los\s+)?archivos|en\s+el\s+codigo|en\s+la\s+carpeta)\s+(.+)',
     "buscar_en_archivos", {"patron": 1, "ruta": 2}, 0.85),
    (r'^grep\s+(.+)',
     "buscar_en_archivos", {"patron": 1, "ruta": None}, 0.90),

    # --- GIT ---
    (r'(?:git\s+)(status|diff|log|push|pull|add|commit|branch|stash|init)',
     "git_operacion", {"operacion": 1}, 0.95),
    (r'(?:haz|has|hacer)\s+(?:un\s+)?(?:commit|push|pull)',
     "git_operacion", {}, 0.80),

    # --- GENERAR CODIGO ---
    (r'(?:genera|generar|crea|crear|escribe|escribir|haz|has)\s+(?:un\s+)?(?:script|codigo|programa|app|aplicacion|juego|pagina|web|bot)\s+(.+)',
     "generar_codigo", {"descripcion": 1}, 0.70),

    # --- NOTAS ---
    (r'(?:nota|apunta|guarda|recordar)\s+(.+)',
     "crear_nota", {"titulo": "Nota", "contenido": 1}, 0.70),
    (r'(?:ver|mostrar|lista)\s+(?:las\s+)?notas',
     "ver_notas", {}, 0.90),

    # --- SKILL: BUSCAR WEB API ---
    (r'(?:busca|buscar)\s+(?:en\s+)?(?:la\s+)?(?:api|internet)\s*(.+)',
     "buscar_web_api", {"consulta": 1}, 0.80),

    # --- SKILL: IMAGEN ---
    (r'(?:genera|generar|crea|crear|haz)\s+(?:una\s+)?(?:imagen|foto|picture|dibujo)\s+(.+)',
     "generar_imagen", {"descripcion": 1}, 0.80),

    # --- SKILL: TTS ---
    (r'(?:lee|leer|dicta|dictar|voz|habla|pronuncia)\s+(.+?)\s+(?:en\s+voz|en\s+audio|con\s+voz)',
     "texto_a_voz", {"texto": 1}, 0.70),

    # --- DOCKER ---
    (r'(?:docker|contenedor)\s+(run|build|ps|stop|rm|exec|logs)',
     "ejecutar_en_contenedor", {}, 0.70),
]

# ============================================================
# CLASE PRINCIPAL
# ============================================================

class DirectIntentParser:
    """
    Parser de intenciones que detecta qué quiere el usuario
    y ejecuta la herramienta directamente sin pasar por el LLM.
    """

    def __init__(self):
        self._compiled_patterns = []
        for pattern, tool_name, param_mapping, confidence in INTENT_PATTERNS:
            try:
                compiled = re.compile(pattern, re.IGNORECASE | re.UNICODE)
                self._compiled_patterns.append((compiled, tool_name, param_mapping, confidence))
            except re.error as e:
                logger.warning(f"Patron regex invalido '{pattern}': {e}")

    def parse(self, message: str) -> Optional[Tuple[str, Dict[str, Any], float]]:
        """
        Parsea el mensaje del usuario y retorna (tool_name, params, confidence)
        o None si no se detecta intención clara.

        Args:
            message: Mensaje del usuario

        Returns:
            (tool_name, params_dict, confidence) o None
        """
        message = message.strip()
        if not message:
            return None

        # Si el mensaje ya es JSON válido, no parsear
        if message.startswith('{') and message.endswith('}'):
            return None

        best_match = None
        best_confidence = 0.0

        for compiled, tool_name, param_mapping, confidence in self._compiled_patterns:
            match = compiled.search(message)
            if match:
                params = self._extract_params(match, param_mapping, message)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = (tool_name, params, confidence)

        return best_match

    def _extract_params(self, match, param_mapping: dict, original_message: str) -> dict:
        """
        Extrae parámetros del match regex según el mapping.

        param_mapping: {"param_name": group_index}
          - group_index 0 = todo el match
          - group_index 1,2... = grupos capturados
          - None = parámetro no requerido (omitir)
          - string literal = valor fijo
        """
        params = {}
        for param_name, source in param_mapping.items():
            if source is None:
                # Parámetro opcional, no extraer
                continue
            elif isinstance(source, str) and not source.isdigit():
                # Valor literal
                params[param_name] = source
            elif isinstance(source, int):
                try:
                    if source == 0:
                        # Todo el match
                        value = match.group(0)
                    else:
                        value = match.group(source)
                    if value is not None:
                        value = value.strip()
                        # Limpiar comillas residuales
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        if value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        params[param_name] = value
                except IndexError:
                    pass  # Grupo no capturado, omitir parámetro

        return params

    def should_bypass_llm(self, message: str) -> bool:
        """
        Determina si el mensaje debe ejecutarse directamente
        sin pasar por el LLM (alta confianza).

        Returns:
            True si la intención es suficientemente clara para bypass
        """
        result = self.parse(message)
        if result is None:
            return False
        _, _, confidence = result
        return confidence >= 0.90


# ============================================================
# SINGLETON
# ============================================================

_parser_instance: Optional[DirectIntentParser] = None

def get_intent_parser() -> DirectIntentParser:
    """Obtiene o crea la instancia singleton del parser."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = DirectIntentParser()
        logger.info("DirectIntentParser inicializado con %d patrones", len(INTENT_PATTERNS))
    return _parser_instance


def parse_direct_intent(message: str) -> Optional[Tuple[str, Dict[str, Any], float]]:
    """Función de conveniencia para parsear intención directamente."""
    parser = get_intent_parser()
    return parser.parse(message)
