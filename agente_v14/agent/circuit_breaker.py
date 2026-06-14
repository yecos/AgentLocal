"""
=============================================================
AGENTE v24 - Circuit Breaker
=============================================================
Patron Circuit Breaker para resiliencia de herramientas.

3 estados:
  CLOSED (normal) -> OPEN (bloqueado) -> HALF_OPEN (probando)

Cuando una herramienta falla repetidamente:
1. CLOSED: todo funciona normalmente
2. OPEN: la herramienta se bloquea, se usa fallback
3. HALF_OPEN: se permite un intento para ver si se recupero

Caracteristicas:
- Fallbacks automaticos por herramienta
- Tiempos de respuesta rastreados
- Herramientas criticas nunca se bloquean
- Reset manual o automatico

Uso:
    from agent.circuit_breaker import CircuitBreakerManager
    cb = CircuitBreakerManager()
    result = cb.call("buscar_web", tool_function, **params)

v24: Implementacion inicial.
=============================================================
"""

from __future__ import annotations

import time
import logging
import threading
from datetime import datetime
from typing import Any, Callable
from collections import defaultdict
from enum import Enum

logger = logging.getLogger("circuit_breaker")


# ============================================================
# ESTADOS DEL CIRCUIT BREAKER
# ============================================================

class CircuitState(Enum):
    """Estados posibles de un Circuit Breaker.

    Attributes:
        CLOSED: Estado normal - todas las llamadas pasan.
        OPEN: Estado bloqueado - las llamadas se redirigen a fallback.
        HALF_OPEN: Estado de prueba - se permite un intento para
            verificar si el servicio se ha recuperado.
    """

    CLOSED = "closed"       # Normal - todo funciona
    OPEN = "open"           # Bloqueado - usando fallback
    HALF_OPEN = "half_open" # Probando - un intento permitido


# ============================================================
# CIRCUIT BREAKER INDIVIDUAL
# ============================================================

class CircuitBreaker:
    """Circuit breaker para una herramienta individual.

    Implementa el patrón Circuit Breaker con 3 estados (CLOSED,
    OPEN, HALF_OPEN) y transiciones automáticas basadas en
    fallos y éxitos consecutivos.

    Transiciones:
        - CLOSED → OPEN: cuando ``failure_threshold`` fallos consecutivos
        - OPEN → HALF_OPEN: cuando pasa ``recovery_timeout`` segundos
        - HALF_OPEN → CLOSED: cuando ``success_threshold`` éxitos consecutivos
        - HALF_OPEN → OPEN: cuando falla un intento en HALF_OPEN

    Thread-safe: todas las mutaciones están protegidas por un Lock.

    Args:
        name: Nombre de la herramienta.
        failure_threshold: Fallos consecutivos antes de abrir.
            Default: 3.
        recovery_timeout: Segundos antes de pasar a HALF_OPEN.
            Default: 30.0.
        success_threshold: Éxitos consecutivos en HALF_OPEN para cerrar.
            Default: 2.
        is_critical: Si es True, nunca se abre completamente (solo
            loguea advertencias pero sigue permitiendo llamadas).
            Default: False.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
        is_critical: bool = False,
    ) -> None:
        self.name: str = name
        self.failure_threshold: int = failure_threshold
        self.recovery_timeout: float = recovery_timeout
        self.success_threshold: int = success_threshold
        self.is_critical: bool = is_critical

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._last_failure_time: float | None = None
        self._last_state_change: str = datetime.now().isoformat()

        # Metricas
        self._total_calls: int = 0
        self._total_failures: int = 0
        self._total_fallbacks: int = 0
        self._response_times: list[float] = []
        self._max_response_times: int = 100

        self._lock: threading.Lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Retorna el estado actual, con transicion automatica a HALF_OPEN.

        Si el estado es OPEN y ha pasado ``recovery_timeout`` desde
        el último fallo, transita automáticamente a HALF_OPEN.

        Returns:
            El estado actual del Circuit Breaker.
        """
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._last_failure_time is not None:
                    elapsed = time.time() - self._last_failure_time
                    if elapsed >= self.recovery_timeout:
                        self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    def call(
        self,
        func: Callable[..., Any],
        fallback: Callable[..., Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Ejecuta una funcion a traves del circuit breaker.

        Comportamiento según estado:
        - CLOSED: ejecuta la función normalmente.
        - OPEN: si es crítico, intenta de todos modos; si hay fallback,
          lo usa; si no, retorna mensaje de no disponible.
        - HALF_OPEN: ejecuta la función (un intento permitido); si falla,
          usa fallback si está disponible.

        Args:
            func: Funcion a ejecutar.
            fallback: Funcion alternativa si el circuito esta abierto.
                Debe aceptar los mismos ``**kwargs``. Default: None.
            **kwargs: Argumentos para la funcion.

        Returns:
            Resultado de la funcion o del fallback. Si el circuito
            está OPEN y no hay fallback, retorna un string con el
            mensaje de no disponible.

        Raises:
            Exception: Si la funcion falla y no hay fallback disponible
                (o el circuito está en HALF_OPEN sin fallback).
        """
        current_state = self.state

        # Si esta OPEN y no es critico, usar fallback
        if current_state == CircuitState.OPEN:
            if self.is_critical:
                logger.warning(f"Circuit BREAKER OPEN para herramienta critica {self.name}, intentando de todos modos")
            elif fallback:
                self._total_fallbacks += 1
                logger.info(f"Circuit OPEN para {self.name}, usando fallback")
                return fallback(**kwargs)
            else:
                self._total_fallbacks += 1
                logger.warning(f"Circuit OPEN para {self.name}, sin fallback disponible")
                return f"[CircuitBreaker] Herramienta {self.name} temporalmente no disponible. Intenta de nuevo en unos segundos."

        # Ejecutar la funcion
        start_time = time.time()
        self._total_calls += 1

        try:
            result = func(**kwargs)
            elapsed = time.time() - start_time

            self._record_success(elapsed)
            return result

        except Exception as e:
            elapsed = time.time() - start_time
            self._record_failure(elapsed)

            # Si hay fallback y estamos en HALF_OPEN, usarlo
            if current_state == CircuitState.HALF_OPEN and fallback:
                self._total_fallbacks += 1
                logger.info(f"Fallo en HALF_OPEN para {self.name}, usando fallback: {e}")
                return fallback(**kwargs)

            raise

    def _record_success(self, elapsed_time: float) -> None:
        """Registra una llamada exitosa.

        Si el estado es HALF_OPEN, incrementa el contador de éxitos
        y transita a CLOSED si se alcanza ``success_threshold``.
        Si el estado es CLOSED, resetea el contador de fallos consecutivos.

        Args:
            elapsed_time: Tiempo de ejecución en segundos.
        """
        with self._lock:
            self._response_times.append(elapsed_time)
            if len(self._response_times) > self._max_response_times:
                self._response_times = self._response_times[-self._max_response_times:]

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(f"Circuit BREAKER CLOSED para {self.name} - recuperado")
            else:
                # Resetear contador de fallos consecutivos
                self._failure_count = 0

    def _record_failure(self, elapsed_time: float) -> None:
        """Registra una llamada fallida.

        Si el estado es HALF_OPEN, transita de vuelta a OPEN.
        Si el estado es CLOSED y se alcanza ``failure_threshold``,
        transita a OPEN (a menos que sea crítico).

        Args:
            elapsed_time: Tiempo hasta el fallo en segundos.
        """
        with self._lock:
            self._total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.time()
            self._response_times.append(elapsed_time)
            if len(self._response_times) > self._max_response_times:
                self._response_times = self._response_times[-self._max_response_times:]

            if self._state == CircuitState.HALF_OPEN:
                # Fallo en HALF_OPEN -> volver a OPEN
                self._transition_to(CircuitState.OPEN)
                logger.warning(f"Circuit BREAKER volvio a OPEN para {self.name}")

            elif self._failure_count >= self.failure_threshold:
                if self.is_critical:
                    logger.warning(
                        f"Circuit BREAKER para herramienta critica {self.name} "
                        f"tendraia {self._failure_count} fallos pero no se abre"
                    )
                else:
                    self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        f"Circuit BREAKER OPEN para {self.name} - "
                        f"{self._failure_count} fallos consecutivos"
                    )

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transiciona a un nuevo estado.

        Resetea los contadores de éxito/fallo según el nuevo estado
        y registra el timestamp de la transición.

        Args:
            new_state: El nuevo estado al que transitar.
        """
        old_state = self._state
        self._state = new_state
        self._last_state_change = datetime.now().isoformat()

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.OPEN:
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0

        logger.debug(f"Circuit {self.name}: {old_state.value} -> {new_state.value}")

    def reset(self) -> None:
        """Resetea el circuit breaker a CLOSED.

        Fuerza la transición a CLOSED y resetea todos los contadores
        de fallos y éxitos consecutivos.
        """
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0
            logger.info(f"Circuit BREAKER reseteado para {self.name}")

    def get_stats(self) -> dict[str, Any]:
        """Retorna estadisticas del circuit breaker.

        Returns:
            Diccionario con keys: ``name``, ``state``, ``failure_count``,
            ``success_count``, ``total_calls``, ``total_failures``,
            ``total_fallbacks``, ``avg_response_time``, ``is_critical``,
            ``last_state_change``.
        """
        avg_response = 0.0
        if self._response_times:
            avg_response = sum(self._response_times) / len(self._response_times)

        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "total_fallbacks": self._total_fallbacks,
            "avg_response_time": round(avg_response, 3),
            "is_critical": self.is_critical,
            "last_state_change": self._last_state_change,
        }


# ============================================================
# CIRCUIT BREAKER MANAGER
# ============================================================

class CircuitBreakerManager:
    """Gestiona circuit breakers para todas las herramientas.

    Mantiene un circuit breaker por herramienta y define
    los fallbacks automaticos según la tabla ``FALLBACKS``.

    Herramientas marcadas como críticas en ``CRITICAL_TOOLS``
    nunca se bloquean completamente (siguen intentando aunque
    estén en estado OPEN).

    Usage::

        manager = CircuitBreakerManager()
        result = manager.call("buscar_web", tool_func, query="test")
    """

    # Herramientas criticas que nunca se bloquean
    CRITICAL_TOOLS: set[str] = {
        "ejecutar_comando",
        "leer_archivo",
        "buscar_web",
    }

    # Fallbacks automaticos por herramienta
    FALLBACKS: dict[str, str | None] = {
        "buscar_web_profundo": "buscar_web",           # Busqueda simple como fallback
        "buscar_web": None,                              # No hay fallback, pero es critico
        "navegador_web": "buscar_web",                  # Si Playwright falla, usar DuckDuckGo
        "ejecutar_en_contenedor": "ejecutar_codigo",    # Si Docker falla, ejecucion local
        "leer_web": "buscar_web",                       # Si scraping falla, buscar resumen
        "buscar_web_api": "buscar_web",                 # Si API falla, usar busqueda directa
    }

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock: threading.Lock = threading.Lock()

    def get_breaker(self, tool_name: str) -> CircuitBreaker:
        """Obtiene o crea el circuit breaker para una herramienta.

        Si la herramienta está en ``CRITICAL_TOOLS``, el breaker
        se crea con ``is_critical=True``.

        Args:
            tool_name: Nombre de la herramienta.

        Returns:
            Instancia de CircuitBreaker para la herramienta.
        """
        with self._lock:
            if tool_name not in self._breakers:
                is_critical = tool_name in self.CRITICAL_TOOLS
                self._breakers[tool_name] = CircuitBreaker(
                    name=tool_name,
                    is_critical=is_critical,
                )
            return self._breakers[tool_name]

    def call(self, tool_name: str, func: Callable[..., Any], **kwargs: Any) -> Any:
        """Ejecuta una herramienta a traves de su circuit breaker.

        Busca automáticamente un fallback según ``FALLBACKS``.
        Si la herramienta falla y el breaker no maneja el error,
        retorna un mensaje de error en lugar de lanzar excepción.

        Args:
            tool_name: Nombre de la herramienta.
            func: Funcion a ejecutar.
            **kwargs: Argumentos para la funcion.

        Returns:
            Resultado de la funcion, del fallback, o un string de error.
        """
        breaker = self.get_breaker(tool_name)

        # Buscar fallback
        fallback: Callable[..., Any] | None = None
        fallback_name = self.FALLBACKS.get(tool_name)
        if fallback_name:
            # Importar aqui para evitar circular imports
            try:
                from tools import TOOL_FUNCTIONS
                fallback_func = TOOL_FUNCTIONS.get(fallback_name)
                if fallback_func:
                    fallback = fallback_func
            except ImportError:
                pass

        try:
            return breaker.call(func, fallback=fallback, **kwargs)
        except Exception as e:
            # Si el circuit breaker no manejo el error, retornar mensaje
            return f"ERROR en {tool_name}: {e}"

    def reset(self, tool_name: str | None = None) -> None:
        """Resetea uno o todos los circuit breakers.

        Args:
            tool_name: Si se especifica, solo resetea ese breaker.
                Si es None, resetea todos. Default: None.
        """
        if tool_name:
            breaker = self._breakers.get(tool_name)
            if breaker:
                breaker.reset()
        else:
            for breaker in self._breakers.values():
                breaker.reset()

    def get_all_stats(self) -> dict[str, Any]:
        """Retorna estadisticas de todos los circuit breakers.

        Returns:
            Diccionario con keys: ``total_breakers``, ``open``,
            ``half_open``, ``closed``, ``breakers`` (dict de
            nombre → stats del breaker).
        """
        stats: dict[str, dict[str, Any]] = {}
        for name, breaker in self._breakers.items():
            stats[name] = breaker.get_stats()

        # Resumen
        total_open = sum(1 for s in stats.values() if s["state"] == "open")
        total_half_open = sum(1 for s in stats.values() if s["state"] == "half_open")

        return {
            "total_breakers": len(self._breakers),
            "open": total_open,
            "half_open": total_half_open,
            "closed": len(self._breakers) - total_open - total_half_open,
            "breakers": stats,
        }

    def get_open_breakers(self) -> list[str]:
        """Retorna los nombres de los circuit breakers abiertos.

        Returns:
            Lista de nombres de herramientas con breaker en estado OPEN.
        """
        return [
            name for name, breaker in self._breakers.items()
            if breaker.state == CircuitState.OPEN
        ]


# ============================================================
# SINGLETON
# ============================================================

_manager_instance: CircuitBreakerManager | None = None

def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Obtiene la instancia singleton del Circuit Breaker Manager.

    Returns:
        La instancia única de CircuitBreakerManager.
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = CircuitBreakerManager()
    return _manager_instance
