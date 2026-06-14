"""
=============================================================
AGENTE v16 - Gestor de Tokens y Contexto
=============================================================
Gestiona el presupuesto de tokens del modelo para evitar
desbordar la ventana de contexto. Provee:

- Conteo aproximado de tokens (sin dependencias externas)
- Presupuesto de tokens por tipo (sistema, contexto, herramientas, respuesta)
- Compresion automatica de contexto cuando se excede el budget
- Estadisticas de uso de tokens por sesion

Uso:
    from utils.token_manager import TokenManager
    tm = TokenManager(model_context_size=8192)
    tm.add_system(system_prompt)
    tm.add_context(memory_text)
    remaining = tm.budget_for_response()
    if tm.needs_compression():
        context = tm.compress(context)
=============================================================
"""

from __future__ import annotations

import re
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("agente")


# ============================================================
# ESTIMACION DE TOKENS
# ============================================================

# Ratios aproximados de tokens por palabra segun idioma
TOKEN_RATIOS: dict[str, float] = {
    "english": 1.3,     # ~1.3 tokens por palabra
    "spanish": 1.7,     # ~1.7 tokens por palabra (mas tokens por acentos)
    "code": 1.5,        # ~1.5 tokens por palabra en codigo
    "default": 1.5,
}

# Tamanos de contexto por modelo conocido (en tokens)
MODEL_CONTEXT_SIZES: dict[str, int] = {
    # Qwen
    "qwen3:4b": 32768,
    "qwen3:8b": 32768,
    "qwen3:30b-a3b": 32768,
    "qwen3-coder": 32768,
    "qwen2.5:7b": 131072,
    "qwen2.5:14b": 131072,
    "qwen2.5-coder:7b": 131072,
    # Llama
    "llama3.1:8b": 131072,
    "llama3.2:1b": 131072,
    "llama3.2:3b": 131072,
    # Mistral
    "mistral:7b": 32768,
    # Gemma
    "gemma2:2b": 8192,
    "gemma2:9b": 8192,
    # DeepSeek
    "deepseek-r1:7b": 65536,
    "deepseek-r1:8b": 65536,
    # Default
    "default": 8192,
}

# Distribucion del presupuesto
BUDGET_SYSTEM: float = 0.15       # 15% para system prompt
BUDGET_CONTEXT: float = 0.30      # 30% para contexto (memoria, historial)
BUDGET_TOOLS: float = 0.15        # 15% para tool schemas + resultados
BUDGET_RESPONSE: float = 0.40     # 40% para respuesta del modelo


def estimate_tokens(text: str, language: str = "default") -> int:
    """Estima la cantidad de tokens de un texto.

    Usa una aproximacion basada en palabras y tipo de contenido.
    Es una estimación; el conteo real requiere tiktoken o similar.

    La fórmula es::

        tokens = int(words * ratio + special_chars * 0.3 + numbers * 0.2)

    Args:
        text: Texto a estimar.
        language: Idioma/tipo de contenido para el ratio de tokens.
            Valores posibles: ``"english"`` (~1.3), ``"spanish"`` (~1.7),
            ``"code"`` (~1.5), ``"default"`` (~1.5). Default: ``"default"``.

    Returns:
        Estimación del número de tokens. Mínimo 1 si el texto no
        está vacío, 0 si está vacío.
    """
    if not text:
        return 0

    ratio = TOKEN_RATIOS.get(language, TOKEN_RATIOS["default"])

    # Contar palabras (split por espacios)
    words = len(text.split())

    # Contar caracteres especiales que generan tokens extra
    special_chars = len(re.findall(r'[^\w\s]', text))

    # Contar numeros (cada digito puede ser un token)
    numbers = len(re.findall(r'\d+', text))

    # Estimacion
    tokens = int(words * ratio + special_chars * 0.3 + numbers * 0.2)

    return max(tokens, 1)


def get_model_context_size(model_name: str) -> int:
    """Obtiene el tamano de contexto de un modelo por su nombre.

    Busca primero coincidencia exacta, luego coincidencia parcial
    (por nombre base del modelo sin tag de versión).

    Args:
        model_name: Nombre del modelo (e.g., ``"qwen3:8b"``,
            ``"llama3.1:8b"``). Si es vacío, retorna el default.

    Returns:
        Tamaño de contexto en tokens. Default: 8192 si el modelo
        no se reconoce.
    """
    if not model_name:
        return MODEL_CONTEXT_SIZES["default"]

    model_lower = model_name.lower()

    # Buscar coincidencia exacta
    if model_lower in MODEL_CONTEXT_SIZES:
        return MODEL_CONTEXT_SIZES[model_lower]

    # Buscar coincidencia parcial
    for key, size in MODEL_CONTEXT_SIZES.items():
        if key in model_lower or model_lower.startswith(key.split(":")[0]):
            return size

    return MODEL_CONTEXT_SIZES["default"]


# ============================================================
# TOKEN MANAGER
# ============================================================

class TokenManager:
    """Gestiona el presupuesto de tokens de una conversacion.

    Distribuye el presupuesto de la ventana de contexto del modelo
    en 4 categorías:
        - Sistema (15%): system prompt
        - Contexto (30%): memoria, historial, resultados de tools
        - Herramientas (15%): schemas de function calling
        - Respuesta (40%): respuesta generada por el modelo

    Cuando el contexto excede el presupuesto, proporciona 3 niveles
    de compresión: light (truncar herramientas), medium (resumir
    historial), heavy (solo system + últimos intercambios).

    Args:
        model_context_size: Tamaño de contexto del modelo en tokens.
            Si es 0, se usa ``get_model_context_size(model_name)``.
        model_name: Nombre del modelo (para lookup automático del
            tamaño de contexto). Default: ``""``.
    """

    def __init__(
        self,
        model_context_size: int = 0,
        model_name: str = "",
    ) -> None:
        self.context_size: int = model_context_size or get_model_context_size(model_name)
        self.system_tokens: int = 0
        self.context_tokens: int = 0
        self.tools_tokens: int = 0
        self.response_tokens: int = 0
        self.total_used: int = 0
        self.history: list[dict[str, Any]] = []  # [(timestamp, type, tokens, description)]
        self._compression_count: int = 0

    def add_system(self, text: str) -> int:
        """Registra tokens del system prompt.

        Reemplaza el conteo anterior (solo hay un system prompt).

        Args:
            text: Contenido del system prompt.

        Returns:
            Número estimado de tokens del system prompt.
        """
        tokens = estimate_tokens(text, "english")  # System prompts usually English
        self.system_tokens = tokens
        self._log("system", tokens, "System prompt")
        return tokens

    def add_context(self, text: str, description: str = "Context") -> int:
        """Registra tokens de contexto (memoria, historial).

        Acumula tokens (no reemplaza). Detecta automáticamente
        el idioma para elegir el ratio de estimación adecuado.

        Args:
            text: Contenido de contexto a registrar.
            description: Descripción para el historial. Default: ``"Context"``.

        Returns:
            Número estimado de tokens agregados.
        """
        # Detectar idioma
        lang = self._detect_language(text)
        tokens = estimate_tokens(text, lang)
        self.context_tokens += tokens
        self._log("context", tokens, description)
        return tokens

    def add_tools(self, schemas_text: str) -> int:
        """Registra tokens de tool schemas.

        Reemplaza el conteo anterior (los schemas se reemplazan
        en cada request, no se acumulan).

        Args:
            schemas_text: Texto de los schemas de function calling.

        Returns:
            Número estimado de tokens de los schemas.
        """
        tokens = estimate_tokens(schemas_text, "code")
        self.tools_tokens = tokens
        self._log("tools", tokens, "Tool schemas")
        return tokens

    def add_tool_result(self, text: str, tool_name: str = "") -> int:
        """Registra tokens del resultado de una herramienta.

        Acumula en context_tokens (los resultados de tools son
        parte del contexto de la conversación).

        Args:
            text: Contenido del resultado de la herramienta.
            tool_name: Nombre de la herramienta (para el historial).
                Default: ``""``.

        Returns:
            Número estimado de tokens agregados.
        """
        tokens = estimate_tokens(text)
        self.context_tokens += tokens
        self._log("tool_result", tokens, f"Tool result: {tool_name}")
        return tokens

    def add_response(self, text: str) -> int:
        """Registra tokens de la respuesta del modelo.

        Acumula tokens de todas las respuestas del modelo en la sesión.

        Args:
            text: Contenido de la respuesta del modelo.

        Returns:
            Número estimado de tokens de la respuesta.
        """
        tokens = estimate_tokens(text)
        self.response_tokens += tokens
        self._log("response", tokens, "Model response")
        return tokens

    def budget_for_response(self) -> int:
        """Retorna cuantos tokens quedan para la respuesta.

        Calcula el espacio restante como ``context_size - used``,
        pero garantiza al menos el 40% del contexto (BUDGET_RESPONSE).

        Returns:
            Número de tokens disponibles para la respuesta del modelo.
        """
        used = self.system_tokens + self.context_tokens + self.tools_tokens
        max_response = int(self.context_size * BUDGET_RESPONSE)
        remaining = self.context_size - used
        return max(remaining, max_response)

    def needs_compression(self) -> bool:
        """Determina si el contexto necesita compresion.

        Returns:
            True si los tokens usados (system + context + tools)
            exceden el 60% del contexto (1 - BUDGET_RESPONSE).
        """
        used = self.system_tokens + self.context_tokens + self.tools_tokens
        threshold = self.context_size * (1 - BUDGET_RESPONSE)
        return used > threshold

    def compression_level(self) -> str:
        """Retorna el nivel de compresion necesario.

        Evalúa la ratio de uso y determina el nivel de compresión:

        - ``"none"``: No se necesita compresión.
        - ``"light"``: Recortar resultados de herramientas largos (>1500 chars)
          y respuestas del asistente (>2000 chars).
        - ``"medium"``: Resumir mensajes antiguos, mantener system + últimos 4.
        - ``"heavy"``: Solo mantener system prompt + últimos 2 intercambios.

        Returns:
            Uno de ``"none"``, ``"light"``, ``"medium"``, ``"heavy"``.
        """
        used = self.system_tokens + self.context_tokens + self.tools_tokens
        available = self.context_size * BUDGET_RESPONSE

        if not self.needs_compression():
            return "none"

        ratio = used / (self.context_size - available) if self.context_size > available else 2.0

        if ratio < 0.8:
            return "light"     # Recortar resultados de herramientas
        elif ratio < 1.2:
            return "medium"   # Resumir historial + recortar
        else:
            return "heavy"    # Compresion agresiva: solo mantener ultimos N mensajes

    def compress(
        self,
        messages: list[dict[str, Any]],
        level: str | None = None,
    ) -> list[dict[str, Any]]:
        """Comprime mensajes para ajustar al presupuesto de tokens.

        Args:
            messages: Lista de mensajes de la conversacion (dicts con
                keys ``"role"`` y ``"content"``).
            level: Nivel de compresion: ``"none"``, ``"light"``,
                ``"medium"``, ``"heavy"``. Si es None, se detecta
                automáticamente con ``compression_level()``.
                Default: None.

        Returns:
            Lista de mensajes comprimidos. Puede ser más corta que
            la original.
        """
        if level is None:
            level = self.compression_level()

        if level == "none":
            return messages

        self._compression_count += 1
        logger.info(f"Comprimiendo contexto (nivel: {level}, mensajes: {len(messages)})")

        if level == "light":
            return self._compress_light(messages)
        elif level == "medium":
            return self._compress_medium(messages)
        else:
            return self._compress_heavy(messages)

    def _compress_light(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Compresion ligera: truncar resultados de herramientas largos.

        Trunca resultados de herramientas con más de 1500 caracteres
        y respuestas del asistente con más de 2000 caracteres.

        Args:
            messages: Lista de mensajes originales.

        Returns:
            Lista de mensajes con textos largos truncados.
        """
        compressed: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "tool" and len(content) > 1500:
                # Truncar resultado de herramienta
                content = content[:1200] + "\n... [resultado truncado para ahorrar tokens]"
                compressed.append({**msg, "content": content})
            elif role == "assistant" and len(content) > 2000:
                # Truncar respuesta larga del asistente
                content = content[:1500] + "\n... [respuesta truncada]"
                compressed.append({**msg, "content": content})
            else:
                compressed.append(msg)

        return compressed

    def _compress_medium(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Compresion media: resumir mensajes antiguos, mantener recientes.

        Mantiene el system prompt y los últimos 4 mensajes completos.
        Los mensajes antiguos se condensan en un resumen de sistema.

        Args:
            messages: Lista de mensajes originales.

        Returns:
            Lista de mensajes con historial antiguo resumido.
        """
        if len(messages) <= 4:
            return messages

        # Mantener system prompt + ultimos 4 mensajes completos
        system_msgs = [m for m in messages if m.get("role") == "system"]
        recent_msgs = messages[-4:]

        # Resumir mensajes antiguos
        old_msgs = [m for m in messages if m not in system_msgs and m not in recent_msgs]

        if not old_msgs:
            return messages

        # Crear resumen compacto
        summary_parts: list[str] = []
        for msg in old_msgs:
            role = msg.get("role", "")
            content = msg.get("content", "")[:200]
            summary_parts.append(f"[{role}] {content}")

        summary = "RESUMEN DEL CONTEXTO ANTERIOR:\n" + "\n".join(summary_parts)

        # Truncar si es muy largo
        if len(summary) > 1000:
            summary = summary[:1000] + "\n... [resumen truncado]"

        compressed = system_msgs + [
            {"role": "system", "content": summary}
        ] + recent_msgs

        return compressed

    def _compress_heavy(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Compresion pesada: solo mantener system + ultimos 2 intercambios.

        Descarta todo el historial excepto el system prompt y los
        últimos 4 mensajes (2 intercambios user/assistant).

        Args:
            messages: Lista de mensajes originales.

        Returns:
            Lista reducida a system + últimos 4 mensajes.
        """
        system_msgs = [m for m in messages if m.get("role") == "system"]

        # Solo ultimos 2 intercambios (4 mensajes: 2 user + 2 assistant)
        recent = messages[-4:] if len(messages) >= 4 else messages

        return system_msgs + recent

    def stats(self) -> dict[str, Any]:
        """Retorna estadisticas de uso de tokens.

        Returns:
            Diccionario con keys: ``context_size``, ``used``,
            ``remaining``, ``utilization_pct``, ``breakdown``
            (dict con system/context/tools/response), ``compressions``,
            ``needs_compression``, ``compression_level``.
        """
        used = self.system_tokens + self.context_tokens + self.tools_tokens + self.response_tokens
        remaining = max(0, self.context_size - used)
        utilization = (used / self.context_size * 100) if self.context_size > 0 else 0

        return {
            "context_size": self.context_size,
            "used": used,
            "remaining": remaining,
            "utilization_pct": round(utilization, 1),
            "breakdown": {
                "system": self.system_tokens,
                "context": self.context_tokens,
                "tools": self.tools_tokens,
                "response": self.response_tokens,
            },
            "compressions": self._compression_count,
            "needs_compression": self.needs_compression(),
            "compression_level": self.compression_level(),
        }

    def format_stats(self) -> str:
        """Retorna estadisticas formateadas para mostrar al usuario.

        Returns:
            String legible con desglose de tokens y estado de compresión.
        """
        s = self.stats()
        parts: list[str] = [
            f"Gestion de Tokens:",
            f"  Modelo: {self.context_size:,} tokens de contexto",
            f"  Usados: {s['used']:,} ({s['utilization_pct']}%)",
            f"  Disponibles: {s['remaining']:,}",
            f"  Desglose:",
            f"    Sistema: {s['breakdown']['system']:,}",
            f"    Contexto: {s['breakdown']['context']:,}",
            f"    Herramientas: {s['breakdown']['tools']:,}",
            f"    Respuesta: {s['breakdown']['response']:,}",
        ]

        if s['needs_compression']:
            parts.append(f"  ⚠ Necesita compresion: {s['compression_level']}")

        if s['compressions'] > 0:
            parts.append(f"  Compresiones realizadas: {s['compressions']}")

        return "\n".join(parts)

    def _detect_language(self, text: str) -> str:
        """Detecta el idioma predominante del texto (simple).

        Heurística basada en caracteres especiales:
        - Si tiene >3 caracteres españoles (áéíóúñ¿¡) → ``"spanish"``
        - Si tiene >5% de caracteres de código ({}()[];=<>) → ``"code"``
        - En otro caso → ``"default"``

        Args:
            text: Texto a analizar.

        Returns:
            Uno de ``"spanish"``, ``"code"`` o ``"default"``.
        """
        # Heuristica basica
        spanish_chars = len(re.findall(r'[áéíóúñ¿¡]', text.lower()))
        if spanish_chars > 3:
            return "spanish"

        # Si tiene mucho codigo
        code_indicators = len(re.findall(r'[{}()\[\];=<>]', text))
        if code_indicators > len(text) * 0.05:
            return "code"

        return "default"

    def _log(self, token_type: str, tokens: int, description: str) -> None:
        """Registra en el historial de tokens.

        Args:
            token_type: Tipo de token (``"system"``, ``"context"``,
                ``"tools"``, ``"tool_result"``, ``"response"``).
            tokens: Número de tokens estimados.
            description: Descripción de la entrada.
        """
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "type": token_type,
            "tokens": tokens,
            "description": description,
        })
        self.total_used += tokens
