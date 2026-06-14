"""
=============================================================
AGENTE v14 - Metrics Collector
=============================================================
Singleton that tracks performance metrics for the agent:
- LLM call counts and latency
- Tool call counts and latency per tool
- Embedding generation counts
- Memory operation counts
- Error counts by category
- Session tracking

Lightweight: only uses stdlib (time, json, os, logging).
Auto-saves to LEARN_DIR/metrics.json every 10 operations.
=============================================================
"""

from __future__ import annotations

import time
import json
import os
import logging
import functools
from datetime import datetime
from threading import Lock
from typing import Any, Callable

logger = logging.getLogger("agente.metrics")

# Default path for metrics persistence (same dir as other data files)
_METRICS_FILE: str = os.path.join(
    os.path.expanduser("~"), ".ia-local", "learning", "metrics.json"
)


class MetricsCollector:
    """Singleton metrics collector for the agent.

    Thread-safe via a single Lock for all mutations. Tracks LLM calls,
    tool calls, embeddings, memory operations, errors, and session info.
    Auto-saves to disk every 10 operations.

    Usage::

        metrics = MetricsCollector.get()
        metrics.record_llm_call(150.5)
        metrics.record_tool_call("buscar_web", 200.3)
        summary = metrics.get_summary()
    """

    _instance: MetricsCollector | None = None
    _lock: Lock = Lock()

    def __init__(self) -> None:
        self._reset_state()
        self._previous_session: dict[str, Any] | None = self._load_previous()

    @classmethod
    def get(cls) -> MetricsCollector:
        """Obtiene la instancia singleton del MetricsCollector.

        Thread-safe: usa double-checked locking para evitar races.

        Returns:
            La instancia única de MetricsCollector.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ----------------------------------------------------------
    # INTERNAL STATE
    # ----------------------------------------------------------

    def _reset_state(self) -> None:
        """Initialize / reset all metric counters."""
        self.llm_calls: int = 0
        self._llm_latencies: list[float] = []       # list of ms values for averaging

        self.tool_calls: dict[str, int] = {}            # {tool_name: count}
        self._tool_latencies: dict[str, list[float]] = {}       # {tool_name: [ms, ms, ...]}

        self.embeddings_generated: int = 0

        self.memory_operations: dict[str, int] = {      # {op_type: count}
            "add": 0,
            "search": 0,
        }

        self.errors: dict[str, int] = {}                # {category: count}

        self.session_start: str = datetime.now().isoformat()
        self.session_messages: int = 0

        self._ops_since_save: int = 0        # counter for auto-save

    # ----------------------------------------------------------
    # RECORDING METHODS
    # ----------------------------------------------------------

    def record_llm_call(self, latency_ms: float) -> None:
        """Record an LLM call with its latency.

        Args:
            latency_ms: Tiempo de respuesta del LLM en milisegundos.
        """
        with self._lock:
            self.llm_calls += 1
            self._llm_latencies.append(latency_ms)
            self._ops_since_save += 1
            self._maybe_auto_save()

    def record_tool_call(self, tool_name: str, latency_ms: float) -> None:
        """Record a tool call with its latency.

        Args:
            tool_name: Nombre de la herramienta ejecutada.
            latency_ms: Tiempo de ejecución en milisegundos.
        """
        with self._lock:
            self.tool_calls[tool_name] = self.tool_calls.get(tool_name, 0) + 1
            if tool_name not in self._tool_latencies:
                self._tool_latencies[tool_name] = []
            self._tool_latencies[tool_name].append(latency_ms)
            self._ops_since_save += 1
            self._maybe_auto_save()

    def record_embedding_call(self) -> None:
        """Record an embedding generation call."""
        with self._lock:
            self.embeddings_generated += 1
            self._ops_since_save += 1
            self._maybe_auto_save()

    def record_memory_operation(self, op_type: str) -> None:
        """Record a memory operation.

        Args:
            op_type: Tipo de operación (e.g., ``"add"`` o ``"search"``).
                Si el tipo no existe, se crea automáticamente.
        """
        with self._lock:
            if op_type in self.memory_operations:
                self.memory_operations[op_type] += 1
            else:
                self.memory_operations[op_type] = 1
            self._ops_since_save += 1
            self._maybe_auto_save()

    def record_error(self, category: str) -> None:
        """Record an error by category string.

        Args:
            category: Categoría del error (e.g., ``"llm_stream"``,
                ``"tool:buscar_web"``, ``"embedding"``).
        """
        with self._lock:
            self.errors[category] = self.errors.get(category, 0) + 1
            self._ops_since_save += 1
            self._maybe_auto_save()

    def record_user_message(self) -> None:
        """Record a user message in the session."""
        with self._lock:
            self.session_messages += 1
            self._ops_since_save += 1
            self._maybe_auto_save()

    # ----------------------------------------------------------
    # COMPUTED METRICS
    # ----------------------------------------------------------

    @property
    def llm_latency_ms(self) -> float:
        """Average LLM response time in milliseconds.

        Returns:
            Promedio de latencia de llamadas LLM, o 0.0 si no hay
            llamadas registradas.
        """
        if not self._llm_latencies:
            return 0.0
        return sum(self._llm_latencies) / len(self._llm_latencies)

    def tool_latency_ms(self, tool_name: str | None = None) -> float:
        """Average tool latency.

        Args:
            tool_name: Si se proporciona, retorna la latencia promedio
                de esa herramienta. Si es None, retorna la latencia
                promedio global de todas las herramientas.

        Returns:
            Latencia promedio en milisegundos, o 0.0 si no hay datos.
        """
        if tool_name:
            latencies = self._tool_latencies.get(tool_name, [])
            return sum(latencies) / len(latencies) if latencies else 0.0
        # Overall average across all tools
        all_latencies: list[float] = []
        for lat_list in self._tool_latencies.values():
            all_latencies.extend(lat_list)
        return sum(all_latencies) / len(all_latencies) if all_latencies else 0.0

    # ----------------------------------------------------------
    # REPORTING
    # ----------------------------------------------------------

    def _build_summary_unlocked(self) -> dict[str, Any]:
        """Build summary dict WITHOUT acquiring lock (caller must hold lock).

        Returns:
            Diccionario con todas las métricas actuales: llm_calls,
            llm_latency_ms, tool_calls, tool_calls_total, etc.
        """
        total_tool_calls = sum(self.tool_calls.values())
        all_tool_latencies: list[float] = []
        for lats in self._tool_latencies.values():
            all_tool_latencies.extend(lats)
        overall_tool_latency = (
            sum(all_tool_latencies) / len(all_tool_latencies)
            if all_tool_latencies else 0.0
        )
        overall_llm_latency = (
            sum(self._llm_latencies) / len(self._llm_latencies)
            if self._llm_latencies else 0.0
        )
        return {
            "llm_calls": self.llm_calls,
            "llm_latency_ms": round(overall_llm_latency, 1),
            "tool_calls": dict(self.tool_calls),
            "tool_calls_total": total_tool_calls,
            "tool_latency_ms": {
                name: round(sum(lats) / len(lats), 1)
                for name, lats in self._tool_latencies.items() if lats
            },
            "tool_latency_overall_ms": round(overall_tool_latency, 1),
            "embeddings_generated": self.embeddings_generated,
            "memory_operations": dict(self.memory_operations),
            "errors": dict(self.errors),
            "errors_total": sum(self.errors.values()),
            "session_start": self.session_start,
            "session_messages": self.session_messages,
        }

    def get_summary(self) -> dict[str, Any]:
        """Returns a dict with all current metrics.

        Thread-safe: adquiere el lock internamente.

        Returns:
            Diccionario con todas las métricas de la sesión actual.
        """
        with self._lock:
            return self._build_summary_unlocked()

    def get_formatted_summary(self) -> str:
        """Returns a formatted string for display in the UI.

        Incluye métricas de la sesión actual y, si están disponibles,
        comparación con la sesión anterior.

        Returns:
            String formateado con métricas legibles para el sidebar
            de Streamlit.
        """
        s = self.get_summary()
        prev = self._previous_session

        lines: list[str] = []
        lines.append(f"**Sesion actual** (desde {s['session_start'][:19]})")
        lines.append(f"  Mensajes: {s['session_messages']}")
        lines.append(f"  LLM calls: {s['llm_calls']}  |  Latencia avg: {s['llm_latency_ms']:.0f} ms")
        lines.append(f"  Tool calls: {s['tool_calls_total']}  |  Latencia avg: {s['tool_latency_overall_ms']:.0f} ms")

        if s["tool_calls"]:
            tool_lines = []
            for name, count in sorted(s["tool_calls"].items(), key=lambda x: -x[1]):
                lat = s["tool_latency_ms"].get(name, 0)
                tool_lines.append(f"    {name}: {count}x ({lat:.0f} ms avg)")
            lines.append("  Tools:")
            lines.extend(tool_lines)

        lines.append(f"  Embeddings: {s['embeddings_generated']}")
        lines.append(f"  Mem ops: add={s['memory_operations'].get('add', 0)}, search={s['memory_operations'].get('search', 0)}")

        if s["errors"]:
            lines.append(f"  Errores ({s['errors_total']}):")
            for cat, count in sorted(s["errors"].items(), key=lambda x: -x[1]):
                lines.append(f"    {cat}: {count}")

        # Comparison with previous session
        if prev:
            lines.append("")
            lines.append(f"**Sesion anterior** ({prev.get('session_start', '?')[:19]})")
            prev_llm = prev.get("llm_calls", 0)
            prev_lat = prev.get("llm_latency_ms", 0)
            lines.append(f"  LLM: {prev_llm} calls | {prev_lat:.0f} ms avg")
            lines.append(f"  Tools: {prev.get('tool_calls_total', 0)} calls | {prev.get('tool_latency_overall_ms', 0):.0f} ms avg")
            prev_err = prev.get("errors_total", 0)
            if prev_err:
                lines.append(f"  Errores: {prev_err}")

        return "\n".join(lines)

    # ----------------------------------------------------------
    # RESET
    # ----------------------------------------------------------

    def reset(self) -> None:
        """Reset all metrics for a new session. Saves current session first.

        Guarda la sesión actual a disco, la almacena como sesión previa
        (para comparación), y reinicia todos los contadores.
        """
        with self._lock:
            self._save_unlocked()
            self._previous_session = self._build_summary_unlocked()
            self._reset_state()
            self._ops_since_save = 0

    # ----------------------------------------------------------
    # PERSISTENCE
    # ----------------------------------------------------------

    def _maybe_auto_save(self) -> None:
        """Auto-save every 10 operations (called inside lock).

        Llamado internamente después de cada operación de grabación.
        Si se acumulan 10 operaciones desde el último save, guarda
        automáticamente a disco.
        """
        if self._ops_since_save >= 10:
            self._save_unlocked()
            self._ops_since_save = 0

    def save(self) -> None:
        """Explicitly save metrics to disk.

        Thread-safe: adquiere el lock internamente.
        """
        with self._lock:
            self._save_unlocked()

    def _save_unlocked(self) -> None:
        """Save metrics JSON (must be called inside lock).

        Escribe las métricas actuales a ``_METRICS_FILE`` en formato
        JSON con la key adicional ``saved_at``.
        """
        try:
            data = self._build_summary_unlocked()
            data["saved_at"] = datetime.now().isoformat()
            dir_path = os.path.dirname(_METRICS_FILE)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(_METRICS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Error guardando metricas: {e}")

    def _load_previous(self) -> dict[str, Any] | None:
        """Load previous session metrics from disk for comparison.

        Returns:
            Diccionario con las métricas de la sesión anterior, o None
            si no hay archivo de métricas o falla la lectura.
        """
        try:
            if os.path.exists(_METRICS_FILE):
                with open(_METRICS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"Error cargando metricas previas: {e}")
        return None


# ============================================================
# DECORATOR: @timed(category)
# ============================================================

def timed(category: str) -> Callable[[Callable], Callable]:
    """Decorator that times function execution and records in MetricsCollector.

    Usage::

        @timed("llm")
        def generate(self, ...):
            ...

    The category determines which metric bucket the timing goes into:
        - ``"llm"``        -> record_llm_call(latency_ms)
        - ``"tool"``       -> record_tool_call(func_name, latency_ms)
        - ``"embedding"``  -> record_embedding_call()
        - ``"memory"``     -> record_memory_operation(...) (type inferred from func name)
        - any other        -> only records elapsed time in structured log

    If the decorated function raises, the error is recorded via
    ``record_error(category)`` and the exception is re-raised.

    Args:
        category: Categoría de la métrica (``"llm"``, ``"tool"``,
            ``"embedding"``, ``"memory"``, etc.).

    Returns:
        Decorador que envuelve la función con medición de tiempo.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            metrics = MetricsCollector.get()
            start = time.monotonic()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.monotonic() - start) * 1000.0

                if category == "llm":
                    metrics.record_llm_call(elapsed_ms)
                elif category == "tool":
                    # Use function name as tool name
                    tool_name = func.__name__
                    metrics.record_tool_call(tool_name, elapsed_ms)
                elif category == "embedding":
                    metrics.record_embedding_call()
                elif category == "memory":
                    # Infer operation type from function name
                    fname = func.__name__.lower()
                    if "add" in fname or "save" in fname or "store" in fname or "remember" in fname:
                        metrics.record_memory_operation("add")
                    elif "search" in fname or "find" in fname or "get" in fname or "query" in fname:
                        metrics.record_memory_operation("search")
                    else:
                        metrics.record_memory_operation("add")

                return result

            except Exception as e:
                elapsed_ms = (time.monotonic() - start) * 1000.0
                metrics.record_error(category)
                raise

        return wrapper
    return decorator


# ============================================================
# CONVENIENCE: module-level singleton accessor
# ============================================================

def get_metrics() -> MetricsCollector:
    """Get the global MetricsCollector singleton.

    Returns:
        La instancia única de MetricsCollector.
    """
    return MetricsCollector.get()
