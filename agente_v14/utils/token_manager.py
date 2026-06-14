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

import re
import logging
from datetime import datetime

logger = logging.getLogger("agente")


# ============================================================
# ESTIMACION DE TOKENS
# ============================================================

# Ratios aproximados de tokens por palabra segun idioma
TOKEN_RATIOS = {
    "english": 1.3,     # ~1.3 tokens por palabra
    "spanish": 1.7,     # ~1.7 tokens por palabra (mas tokens por acentos)
    "code": 1.5,        # ~1.5 tokens por palabra en codigo
    "default": 1.5,
}

# Tamanos de contexto por modelo conocido (en tokens)
MODEL_CONTEXT_SIZES = {
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
BUDGET_SYSTEM = 0.15       # 15% para system prompt
BUDGET_CONTEXT = 0.30      # 30% para contexto (memoria, historial)
BUDGET_TOOLS = 0.15        # 15% para tool schemas + resultados
BUDGET_RESPONSE = 0.40     # 40% para respuesta del modelo


def estimate_tokens(text: str, language: str = "default") -> int:
    """Estima la cantidad de tokens de un texto.

    Usa una aproximacion basada en palabras y tipo de contenido.
    Es una estimacion; el conteo real requiere tiktoken o similar.

    Args:
        text: Texto a estimar
        language: Idioma/tipo: english, spanish, code, default
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
    """Obtiene el tamano de contexto de un modelo por su nombre."""
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
    """Gestiona el presupuesto de tokens de una conversacion."""

    def __init__(self, model_context_size: int = 0, model_name: str = ""):
        self.context_size = model_context_size or get_model_context_size(model_name)
        self.system_tokens = 0
        self.context_tokens = 0
        self.tools_tokens = 0
        self.response_tokens = 0
        self.total_used = 0
        self.history = []  # [(timestamp, type, tokens, description)]
        self._compression_count = 0

    def add_system(self, text: str) -> int:
        """Registra tokens del system prompt."""
        tokens = estimate_tokens(text, "english")  # System prompts usually English
        self.system_tokens = tokens
        self._log("system", tokens, "System prompt")
        return tokens

    def add_context(self, text: str, description: str = "Context") -> int:
        """Registra tokens de contexto (memoria, historial)."""
        # Detectar idioma
        lang = self._detect_language(text)
        tokens = estimate_tokens(text, lang)
        self.context_tokens += tokens
        self._log("context", tokens, description)
        return tokens

    def add_tools(self, schemas_text: str) -> int:
        """Registra tokens de tool schemas."""
        tokens = estimate_tokens(schemas_text, "code")
        self.tools_tokens = tokens
        self._log("tools", tokens, "Tool schemas")
        return tokens

    def add_tool_result(self, text: str, tool_name: str = "") -> int:
        """Registra tokens del resultado de una herramienta."""
        tokens = estimate_tokens(text)
        self.context_tokens += tokens
        self._log("tool_result", tokens, f"Tool result: {tool_name}")
        return tokens

    def add_response(self, text: str) -> int:
        """Registra tokens de la respuesta del modelo."""
        tokens = estimate_tokens(text)
        self.response_tokens += tokens
        self._log("response", tokens, "Model response")
        return tokens

    def budget_for_response(self) -> int:
        """Retorna cuantos tokens quedan para la respuesta."""
        used = self.system_tokens + self.context_tokens + self.tools_tokens
        max_response = int(self.context_size * BUDGET_RESPONSE)
        remaining = self.context_size - used
        return max(remaining, max_response)

    def needs_compression(self) -> bool:
        """Determina si el contexto necesita compresion."""
        used = self.system_tokens + self.context_tokens + self.tools_tokens
        threshold = self.context_size * (1 - BUDGET_RESPONSE)
        return used > threshold

    def compression_level(self) -> str:
        """Retorna el nivel de compresion necesario: none, light, medium, heavy."""
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

    def compress(self, messages: list, level: str = None) -> list:
        """Comprime mensajes para ajustar al presupuesto de tokens.

        Args:
            messages: Lista de mensajes de la conversacion
            level: Nivel de compresion: none, light, medium, heavy (auto-detect si None)
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

    def _compress_light(self, messages: list) -> list:
        """Compresion ligera: truncar resultados de herramientas largos."""
        compressed = []
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

    def _compress_medium(self, messages: list) -> list:
        """Compresion media: resumir mensajes antiguos, mantener recientes."""
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
        summary_parts = []
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

    def _compress_heavy(self, messages: list) -> list:
        """Compresion pesada: solo mantener system + ultimos 2 intercambios."""
        system_msgs = [m for m in messages if m.get("role") == "system"]

        # Solo ultimos 2 intercambios (4 mensajes: 2 user + 2 assistant)
        recent = messages[-4:] if len(messages) >= 4 else messages

        return system_msgs + recent

    def stats(self) -> dict:
        """Retorna estadisticas de uso de tokens."""
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
        """Retorna estadisticas formateadas para mostrar al usuario."""
        s = self.stats()
        parts = [
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
        """Detecta el idioma predominante del texto (simple)."""
        # Heuristica basica
        spanish_chars = len(re.findall(r'[áéíóúñ¿¡]', text.lower()))
        if spanish_chars > 3:
            return "spanish"

        # Si tiene mucho codigo
        code_indicators = len(re.findall(r'[{}()\[\];=<>]', text))
        if code_indicators > len(text) * 0.05:
            return "code"

        return "default"

    def _log(self, token_type: str, tokens: int, description: str):
        """Registra en el historial de tokens."""
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "type": token_type,
            "tokens": tokens,
            "description": description,
        })
        self.total_used += tokens
