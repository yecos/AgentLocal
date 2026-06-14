"""
=============================================================
AGENTE v24 - Motor de Auto-Evolucion
=============================================================
6 fases del ciclo de auto-mejora:

1. AUTOEVALUARSE  - Inventario de capacidades, analisis de errores
2. BUSCAR         - Buscar en MCP, web, PyPI, skills internos
3. EVALUAR SEGURIDAD - Verificar limites, dominios, risk level
4. INTEGRAR       - MCP Server / pip Package / Internal Skill
5. PROBAR         - Import test, discover test, rollback si falla
6. APRENDER       - Guardar en TripleMemory + Learning System

Uso (como herramienta del agente):
    from tools.auto_evolve_tool_module import auto_evolve
    result = auto_evolve(focus="email")

Uso (programatico):
    from agent.auto_evolve import AutoEvolver
    evolver = AutoEvolver()
    result = evolver.evolve(focus="email")

v24: Implementacion inicial.
=============================================================
"""

import os
import json
import time
import logging
import subprocess
import importlib
from datetime import datetime
from typing import Any, Optional
from pathlib import Path

logger = logging.getLogger("auto_evolve")


# ============================================================
# CONFIGURACION
# ============================================================

EVOLVE_DIR = os.path.join(os.path.expanduser("~"), ".ia-local", "evolution")
EVOLVE_LOG = os.path.join(EVOLVE_DIR, "evolution_log.json")

# Limites de seguridad
MAX_INSTALLS_PER_DAY = 3
BLOCKED_DOMAINS = [
    "malware", "exploit", "keylogger", "rat", "trojan",
    "ransomware", "spyware", "backdoor", "cryptominer",
]
ALLOWED_LICENSES = ["MIT", "Apache", "BSD", "GPL", "LGPL", "MPL", "Unlicense"]
MAX_FAILED_ATTEMPTS = 2

# Paquetes PyPI conocidos por categoria
KNOWN_PACKAGES = {
    "email": [
        {"name": "yagmail", "description": "Gmail sending made easy", "license": "MIT"},
        {"name": "imapclient", "description": "IMAP client library", "license": "BSD"},
    ],
    "calendar": [
        {"name": "google-api-python-client", "description": "Google Calendar API", "license": "Apache"},
        {"name": "icalendar", "description": "iCalendar parser/generator", "license": "BSD"},
    ],
    "spreadsheet": [
        {"name": "openpyxl", "description": "Excel file handler", "license": "MIT"},
        {"name": "xlrd", "description": "Excel reader", "license": "BSD"},
    ],
    "image_edit": [
        {"name": "Pillow", "description": "Image processing library", "license": "MIT"},
        {"name": "python-resize-image", "description": "Image resizing", "license": "MIT"},
    ],
    "database_admin": [
        {"name": "sqlalchemy", "description": "SQL toolkit and ORM", "license": "MIT"},
        {"name": "psycopg2-binary", "description": "PostgreSQL adapter", "license": "LGPL"},
    ],
    "voice": [
        {"name": "pyttsx3", "description": "Text-to-speech offline", "license": "MIT"},
        {"name": "SpeechRecognition", "description": "Speech recognition", "license": "BSD"},
    ],
    "pdf": [
        {"name": "reportlab", "description": "PDF generation", "license": "BSD"},
        {"name": "PyPDF2", "description": "PDF manipulation", "license": "BSD"},
    ],
    "api": [
        {"name": "httpx", "description": "Modern HTTP client", "license": "BSD"},
        {"name": "fastapi", "description": "Web API framework", "license": "MIT"},
    ],
}

# 20 capacidades comunes que un agente puede necesitar
COMMON_CAPABILITIES = [
    "email", "calendar", "spreadsheet", "presentation", "pdf",
    "image_edit", "voice", "database_admin", "api_integration",
    "cloud_storage", "messaging", "scheduling", "monitoring",
    "notification", "encryption", "compression", "web_scraping",
    "data_analysis", "chart_generation", "project_management",
]


# ============================================================
# AUTO-EVOLVER
# ============================================================

class AutoEvolver:
    """Motor de auto-mejora continua del agente.

    El evolver analiza las capacidades actuales del agente,
    identifica carencias, busca soluciones, evalua su seguridad,
    las integra, las prueba y aprende del resultado.
    """

    def __init__(self, memory=None):
        self.memory = memory
        self._installs_today = 0
        self._installs_date = datetime.now().strftime("%Y-%m-%d")
        self._failed_attempts = {}  # {focus: count}
        self._evolution_history = []
        self._load_evolution_log()

    def _load_evolution_log(self):
        """Carga el historial de evolucion desde disco."""
        if os.path.exists(EVOLVE_LOG):
            try:
                with open(EVOLVE_LOG, "r") as f:
                    self._evolution_history = json.load(f)
            except Exception as e:
                logger.error(f"Error cargando evolution log: {e}")
                self._evolution_history = []

    def _save_evolution_log(self):
        """Guarda el historial de evolucion a disco."""
        os.makedirs(EVOLVE_DIR, exist_ok=True)
        try:
            with open(EVOLVE_LOG, "w") as f:
                json.dump(self._evolution_history[-100:], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando evolution log: {e}")

    def _reset_daily_installs_if_needed(self):
        """Resetea el contador de installs si cambio el dia."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._installs_date:
            self._installs_today = 0
            self._installs_date = today

    # ========================================================
    # FASE 1: AUTOEVALUARSE
    # ========================================================

    def self_assess(self, tool_functions: dict = None) -> dict:
        """Evalua las capacidades actuales del agente.

        Args:
            tool_functions: Dict de herramientas disponibles (opcional)

        Returns:
            Dict con el assessment completo
        """
        # Inventario de herramientas
        available_tools = set(tool_functions.keys()) if tool_functions else set()

        # Mapeo de capacidades a herramientas
        capability_tools = {
            "web_search": {"buscar_web", "buscar_web_profundo", "buscar_web_api"},
            "file_operations": {"leer_archivo", "escribir_archivo", "listar_archivos", "buscar_en_archivos"},
            "code_execution": {"ejecutar_comando", "ejecutar_codigo", "ejecutar_en_contenedor"},
            "web_browsing": {"navegador_web", "leer_web", "leer_web_api"},
            "git": {"git_operacion", "clonar_repositorio"},
            "database": {"base_de_datos"},
            "code_generation": {"generar_codigo"},
            "project_management": {"analizar_proyecto", "crear_proyecto", "planificar_tarea"},
            "deployment": {"desplegar_proyecto", "opciones_despliegue"},
            "image_generation": {"generar_imagen"},
            "document_creation": {"crear_documento", "crear_pdf", "crear_presentacion"},
            "tts": {"texto_a_voz"},
            "stt": {"voz_a_texto"},
            "image_analysis": {"analizar_imagen_api"},
            "scheduling": {"tarea_programada", "vigilar_archivo"},
            "notifications": {"crear_nota"},
        }

        # Evaluar cada capacidad
        capabilities = {}
        for cap, required_tools in capability_tools.items():
            has_any = bool(available_tools & required_tools)
            capabilities[cap] = {
                "available": has_any,
                "coverage": len(available_tools & required_tools) / len(required_tools) if required_tools else 0,
                "tools": list(available_tools & required_tools),
                "missing": list(required_tools - available_tools),
            }

        # Detectar capacidades faltantes comunes
        missing_common = []
        for cap in COMMON_CAPABILITIES:
            cap_found = False
            for existing_cap, info in capabilities.items():
                if existing_cap == cap or cap in existing_cap:
                    if info["available"]:
                        cap_found = True
                        break
            if not cap_found:
                missing_common.append(cap)

        # Health score (0.0 - 1.0)
        total_capabilities = len(capabilities)
        available_capabilities = sum(1 for c in capabilities.values() if c["available"])
        health_score = available_capabilities / total_capabilities if total_capabilities > 0 else 0

        assessment = {
            "timestamp": datetime.now().isoformat(),
            "total_tools": len(available_tools),
            "total_capabilities": total_capabilities,
            "available_capabilities": available_capabilities,
            "missing_common": missing_common,
            "health_score": round(health_score, 2),
            "capabilities": capabilities,
        }

        return assessment

    # ========================================================
    # FASE 2: BUSCAR
    # ========================================================

    def search_solutions(self, focus: str = None) -> list:
        """Busca soluciones para una necesidad especifica.

        Busca en:
        1. Servidores MCP disponibles
        2. Paquetes PyPI conocidos
        3. Skills internos no cargados

        Args:
            focus: Capacidad especifica a buscar (ej: "email")

        Returns:
            Lista de soluciones encontradas
        """
        solutions = []

        # 1. Buscar en paquetes PyPI conocidos
        if focus and focus in KNOWN_PACKAGES:
            for pkg in KNOWN_PACKAGES[focus]:
                solutions.append({
                    "type": "pip",
                    "name": pkg["name"],
                    "description": pkg["description"],
                    "license": pkg.get("license", "Unknown"),
                    "source": "known_packages",
                    "risk": "low",
                })

        # 2. Buscar en MCP servers disponibles
        try:
            from mcp.client import get_mcp_client
            mcp_client = get_mcp_client()
            mcp_status = mcp_client.get_status()

            if mcp_status["total_servers"] > 0:
                for server_name, server_info in mcp_status.get("servers", {}).items():
                    if server_info.get("connected"):
                        for tool in server_info.get("tools", []):
                            if focus and focus.lower() in tool.lower():
                                solutions.append({
                                    "type": "mcp",
                                    "name": tool,
                                    "server": server_name,
                                    "source": "mcp_servers",
                                    "risk": "low",
                                })
        except ImportError:
            pass

        # 3. Buscar en skills internos
        try:
            from tools.skill_loader import list_available_skills
            available_skills = list_available_skills()
            for skill in available_skills:
                skill_name = skill.get("name", "")
                if focus and focus.lower() in skill_name.lower():
                    solutions.append({
                        "type": "skill",
                        "name": skill_name,
                        "source": "internal_skills",
                        "risk": "low",
                    })
        except (ImportError, Exception):
            pass

        # 4. Si no hay soluciones conocidas, sugerir busqueda web
        if not solutions and focus:
            solutions.append({
                "type": "search_web",
                "name": f"Buscar paquete Python para {focus}",
                "source": "fallback",
                "risk": "medium",
                "query": f"python {focus} library pip install",
            })

        return solutions

    # ========================================================
    # FASE 3: EVALUAR SEGURIDAD
    # ========================================================

    def evaluate_safety(self, solution: dict) -> dict:
        """Evalua la seguridad de una solucion antes de instalarla.

        Args:
            solution: Dict con la solucion a evaluar

        Returns:
            Dict con la evaluacion de seguridad
        """
        risk_level = "low"
        warnings = []
        blocked = False

        # Verificar limite diario de installs
        self._reset_daily_installs_if_needed()
        if self._installs_today >= MAX_INSTALLS_PER_DAY:
            blocked = True
            warnings.append(f"Limite diario de installs alcanzado ({MAX_INSTALLS_PER_DAY})")

        # Verificar intentos fallidos previos
        focus = solution.get("name", "")
        if focus in self._failed_attempts and self._failed_attempts[focus] >= MAX_FAILED_ATTEMPTS:
            blocked = True
            warnings.append(f"Demasiados intentos fallidos para {focus}")

        # Verificar dominios bloqueados
        name_lower = solution.get("name", "").lower()
        desc_lower = solution.get("description", "").lower()
        for domain in BLOCKED_DOMAINS:
            if domain in name_lower or domain in desc_lower:
                blocked = True
                risk_level = "critical"
                warnings.append(f"Dominio bloqueado detectado: {domain}")

        # Evaluar por tipo
        sol_type = solution.get("type", "")
        if sol_type == "pip":
            # Verificar licencia
            license_name = solution.get("license", "Unknown")
            if license_name not in ALLOWED_LICENSES and license_name != "Unknown":
                risk_level = "medium"
                warnings.append(f"Licencia no verificada: {license_name}")

            # pip install es de riesgo medio por defecto
            if risk_level == "low":
                risk_level = "medium"

        elif sol_type == "mcp":
            # MCP es generalmente seguro
            risk_level = "low"

        elif sol_type == "search_web":
            # Busqueda web necesita validacion manual
            risk_level = "medium"
            warnings.append("Requiere validacion manual")

        return {
            "risk_level": risk_level,
            "blocked": blocked,
            "warnings": warnings,
            "solution": solution,
        }

    # ========================================================
    # FASE 4: INTEGRAR
    # ========================================================

    def integrate(self, solution: dict) -> dict:
        """Integra una solucion en el agente.

        Args:
            solution: Dict con la solucion a integrar

        Returns:
            Dict con el resultado de la integracion
        """
        sol_type = solution.get("type", "")

        try:
            if sol_type == "pip":
                return self._integrate_pip(solution)
            elif sol_type == "mcp":
                return self._integrate_mcp(solution)
            elif sol_type == "skill":
                return self._integrate_skill(solution)
            else:
                return {"success": False, "error": f"Tipo de solucion no soportado: {sol_type}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _integrate_pip(self, solution: dict) -> dict:
        """Instala un paquete PyPI."""
        pkg_name = solution.get("name", "")
        logger.info(f"Instalando paquete PyPI: {pkg_name}")

        try:
            result = subprocess.run(
                ["pip", "install", pkg_name],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                self._installs_today += 1
                return {
                    "success": True,
                    "type": "pip",
                    "package": pkg_name,
                    "output": result.stdout[-500:] if len(result.stdout) > 500 else result.stdout,
                }
            else:
                return {
                    "success": False,
                    "type": "pip",
                    "package": pkg_name,
                    "error": result.stderr[-500:] if len(result.stderr) > 500 else result.stderr,
                }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout instalando paquete"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _integrate_mcp(self, solution: dict) -> dict:
        """Registra herramientas de un servidor MCP."""
        server_name = solution.get("server", "")
        logger.info(f"Integrando herramientas MCP de: {server_name}")

        try:
            from mcp.client import get_mcp_client
            mcp_client = get_mcp_client()

            # Obtener schemas de herramientas MCP
            schemas = mcp_client.get_all_tools_schemas()

            if schemas:
                # Registrar en el Tool Registry del agente
                try:
                    from tools.registry import TOOL_FUNCTIONS, TOOL_SCHEMAS
                    for schema in schemas:
                        if schema not in TOOL_SCHEMAS:
                            TOOL_SCHEMAS.append(schema)
                    return {
                        "success": True,
                        "type": "mcp",
                        "server": server_name,
                        "tools_added": len(schemas),
                    }
                except ImportError:
                    return {"success": False, "error": "Tool Registry no disponible"}
            else:
                return {"success": False, "error": "No se encontraron herramientas MCP"}

        except ImportError:
            return {"success": False, "error": "Cliente MCP no disponible"}

    def _integrate_skill(self, solution: dict) -> dict:
        """Carga un skill interno."""
        skill_name = solution.get("name", "")
        logger.info(f"Cargando skill interno: {skill_name}")

        try:
            from tools.skill_loader import load_skill
            result = load_skill(skill_name)
            if result:
                return {"success": True, "type": "skill", "skill": skill_name}
            else:
                return {"success": False, "error": f"Skill {skill_name} no encontrado"}
        except ImportError:
            return {"success": False, "error": "Skill loader no disponible"}

    # ========================================================
    # FASE 5: PROBAR
    # ========================================================

    def test_integration(self, solution: dict) -> dict:
        """Prueba que la integracion funciona correctamente.

        Args:
            solution: Dict con la solucion integrada

        Returns:
            Dict con el resultado del test
        """
        sol_type = solution.get("type", "")

        try:
            if sol_type == "pip":
                return self._test_pip(solution)
            elif sol_type == "mcp":
                return self._test_mcp(solution)
            elif sol_type == "skill":
                return self._test_skill(solution)
            else:
                return {"success": False, "error": "Tipo no testeable"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _test_pip(self, solution: dict) -> dict:
        """Prueba importar un paquete PyPI."""
        pkg_name = solution.get("name", "").replace("-", "_")

        try:
            mod = importlib.import_module(pkg_name)
            version = getattr(mod, "__version__", "unknown")
            return {
                "success": True,
                "type": "pip",
                "package": pkg_name,
                "version": version,
            }
        except ImportError:
            # Probar nombre alternativo
            alt_name = solution.get("name", "")
            try:
                mod = importlib.import_module(alt_name)
                version = getattr(mod, "__version__", "unknown")
                return {
                    "success": True,
                    "type": "pip",
                    "package": alt_name,
                    "version": version,
                }
            except ImportError:
                return {"success": False, "error": f"No se pudo importar {pkg_name}"}

    def _test_mcp(self, solution: dict) -> dict:
        """Prueba descubrir herramientas de un servidor MCP."""
        server_name = solution.get("server", "")
        try:
            from mcp.client import get_mcp_client
            mcp_client = get_mcp_client()
            tools = mcp_client.discover_tools(server_name)
            return {
                "success": len(tools) > 0,
                "type": "mcp",
                "server": server_name,
                "tools_found": len(tools),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _test_skill(self, solution: dict) -> dict:
        """Prueba que un skill esta cargado."""
        skill_name = solution.get("name", "")
        try:
            from tools.registry import TOOL_FUNCTIONS
            # Verificar si alguna herramienta del skill esta registrada
            matching = [k for k in TOOL_FUNCTIONS if skill_name.lower() in k.lower()]
            return {
                "success": len(matching) > 0,
                "type": "skill",
                "skill": skill_name,
                "tools_registered": matching,
            }
        except ImportError:
            return {"success": False, "error": "Registry no disponible"}

    def _rollback(self, solution: dict) -> dict:
        """Revierte una instalacion fallida."""
        sol_type = solution.get("type", "")
        pkg_name = solution.get("name", "")

        if sol_type == "pip" and pkg_name:
            try:
                subprocess.run(
                    ["pip", "uninstall", "-y", pkg_name],
                    capture_output=True, text=True, timeout=60,
                )
                logger.info(f"Rollback: {pkg_name} desinstalado")
                return {"success": True, "action": "uninstall", "package": pkg_name}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "Rollback no soportado para este tipo"}

    # ========================================================
    # FASE 6: APRENDER
    # ========================================================

    def learn(self, solution: dict, integration_result: dict, test_result: dict) -> dict:
        """Registra la leccion aprendida de la evolucion.

        Args:
            solution: La solucion que se intento integrar
            integration_result: Resultado de la integracion
            test_result: Resultado del test

        Returns:
            Dict con la leccion registrada
        """
        success = integration_result.get("success", False) and test_result.get("success", False)

        # Registrar en evolution log
        lesson = {
            "timestamp": datetime.now().isoformat(),
            "solution": solution,
            "integration_success": integration_result.get("success", False),
            "test_success": test_result.get("success", False),
            "overall_success": success,
            "integration_error": integration_result.get("error"),
            "test_error": test_result.get("error"),
        }

        self._evolution_history.append(lesson)
        self._save_evolution_log()

        # Si fallo, incrementar contador de intentos fallidos
        if not success:
            focus = solution.get("name", "")
            self._failed_attempts[focus] = self._failed_attempts.get(focus, 0) + 1
        else:
            # Si tuvo exito, resetear contador
            focus = solution.get("name", "")
            self._failed_attempts.pop(focus, None)

        # Guardar en memoria del agente si esta disponible
        if self.memory:
            try:
                if success:
                    self.memory.save_knowledge(
                        topic=f"evolution_{solution.get('type', 'unknown')}",
                        content=f"Instalado exitosamente: {solution.get('name')} - {solution.get('description', '')}",
                    )
                else:
                    self.memory.save_knowledge(
                        topic=f"evolution_failed_{solution.get('type', 'unknown')}",
                        content=f"Fallo instalando: {solution.get('name')} - Error: {integration_result.get('error', test_result.get('error', 'unknown'))}",
                    )
            except Exception as e:
                logger.error(f"Error guardando en memoria: {e}")

        return lesson

    # ========================================================
    # CICLO COMPLETO
    # ========================================================

    def evolve(self, focus: str = None, tool_functions: dict = None) -> dict:
        """Ejecuta un ciclo completo de auto-evolucion.

        Args:
            focus: Capacidad especifica a mejorar (ej: "email")
            tool_functions: Dict de herramientas disponibles

        Returns:
            Dict con el resultado completo del ciclo
        """
        start_time = time.time()
        logger.info(f"Iniciando ciclo de auto-evolucion (focus={focus})")

        # Fase 1: Autoevaluarse
        assessment = self.self_assess(tool_functions)

        # Fase 2: Buscar soluciones
        solutions = self.search_solutions(focus)

        if not solutions:
            return {
                "success": False,
                "phase": "search",
                "message": f"No se encontraron soluciones para: {focus}",
                "assessment": assessment,
                "elapsed": round(time.time() - start_time, 2),
            }

        # Seleccionar la mejor solucion (primera con riesgo bajo/medio)
        selected = None
        for solution in solutions:
            safety = self.evaluate_safety(solution)
            if not safety["blocked"]:
                selected = solution
                selected["safety"] = safety
                break

        if not selected:
            return {
                "success": False,
                "phase": "safety",
                "message": "Todas las soluciones fueron bloqueadas por seguridad",
                "solutions_found": len(solutions),
                "assessment": assessment,
                "elapsed": round(time.time() - start_time, 2),
            }

        # Fase 4: Integrar
        integration_result = self.integrate(selected)

        if not integration_result.get("success"):
            # Registrar el fallo y retornar
            lesson = self.learn(selected, integration_result, {"success": False})
            return {
                "success": False,
                "phase": "integrate",
                "message": f"Error integrando: {integration_result.get('error')}",
                "solution": selected,
                "integration": integration_result,
                "lesson": lesson,
                "assessment": assessment,
                "elapsed": round(time.time() - start_time, 2),
            }

        # Fase 5: Probar
        test_result = self.test_integration(selected)

        if not test_result.get("success"):
            # Rollback si fallo
            self._rollback(selected)
            lesson = self.learn(selected, integration_result, test_result)
            return {
                "success": False,
                "phase": "test",
                "message": f"Test fallo: {test_result.get('error')}",
                "solution": selected,
                "integration": integration_result,
                "test": test_result,
                "rollback": True,
                "lesson": lesson,
                "assessment": assessment,
                "elapsed": round(time.time() - start_time, 2),
            }

        # Fase 6: Aprender
        lesson = self.learn(selected, integration_result, test_result)

        return {
            "success": True,
            "phase": "complete",
            "message": f"Auto-evolucion exitosa: {selected.get('name')} integrado y verificado",
            "solution": selected,
            "integration": integration_result,
            "test": test_result,
            "lesson": lesson,
            "assessment": assessment,
            "elapsed": round(time.time() - start_time, 2),
        }

    # ========================================================
    # UTILIDADES
    # ========================================================

    def get_evolution_history(self, limit: int = 10) -> list:
        """Retorna el historial reciente de evolucion."""
        return self._evolution_history[-limit:]

    def get_status(self) -> dict:
        """Retorna el estado del sistema de auto-evolucion."""
        self._reset_daily_installs_if_needed()
        total = len(self._evolution_history)
        successes = sum(1 for e in self._evolution_history if e.get("overall_success"))
        return {
            "installs_today": self._installs_today,
            "max_installs_per_day": MAX_INSTALLS_PER_DAY,
            "failed_attempts": dict(self._failed_attempts),
            "total_evolutions": total,
            "successful_evolutions": successes,
            "success_rate": round(successes / total * 100, 1) if total > 0 else 0,
        }


# ============================================================
# M9: ANALISIS DE USO Y EVOLUCION BASADA EN DATOS REALES
# ============================================================

def analyze_usage_gaps() -> dict:
    """M9: Analyze which tools fail most or are never used.
    
    Examina las metricas de uso actual para identificar:
    - Herramientas con alta tasa de error (>30%) que necesitan mejora
    - Herramientas que nunca se usaron (posibles carencias)
    
    Returns:
        Dict con analisis de gaps de uso:
        - high_error_tools: lista de tools con error rate > 30%
        - never_used_tools: lista de tools registrados pero nunca usados
        - total_tools: numero total de herramientas disponibles
        - used_tools: numero de herramientas usadas en la sesion
    """
    from utils.metrics import get_metrics
    
    metrics = get_metrics()
    stats = metrics.get_summary()
    
    tool_calls = stats.get("tool_calls", {})
    tool_latency = stats.get("tool_latency_ms", {})
    errors = stats.get("errors", {})
    
    # Tools with high error rate → need improvement
    high_error_tools = []
    for tool_name, count in tool_calls.items():
        error_key = f"tool:{tool_name}"
        error_count = errors.get(error_key, 0)
        if count > 0 and error_count / count > 0.3:  # >30% error rate
            high_error_tools.append({
                "tool": tool_name,
                "error_rate": round(error_count / count, 2),
                "total_calls": count,
            })
    
    # Tools never used → potential gaps
    try:
        from tools.registry import TOOL_FUNCTIONS
        all_tools = set(TOOL_FUNCTIONS.keys())
    except ImportError:
        try:
            from tools import TOOL_FUNCTIONS
            all_tools = set(TOOL_FUNCTIONS.keys())
        except ImportError:
            all_tools = set()
    
    used_tools = set(tool_calls.keys())
    never_used = list(all_tools - used_tools)
    
    return {
        "high_error_tools": high_error_tools,
        "never_used_tools": never_used,
        "total_tools": len(all_tools),
        "used_tools": len(used_tools),
    }


def _analyze_feedback_patterns() -> dict:
    """M9.2: Analyze user feedback to find tools/skills that need improvement.
    
    Reads the UserFeedbackTracker history and identifies:
    - Tools with consistent negative feedback (thumbs down, low ratings)
    - Categories of problems reported by users
    - Specific feedback patterns that indicate systemic issues
    
    Returns:
        Dict with:
        - negative_tools: tools with high negative feedback ratio
        - problem_categories: most common feedback problem categories
        - recent_corrections: recent correction-type feedback for context
    """
    try:
        from tools.user_feedback import UserFeedbackTracker
        tracker = UserFeedbackTracker()
        
        # Get recent feedback history
        history = tracker._history[-100:]  # Last 100 entries
        
        # Count negative feedback per tool
        tool_feedback = {}
        category_counts = {}
        recent_corrections = []
        
        for entry in history:
            fb_type = entry.get("type", "")
            tool = entry.get("tool_name", "unknown")
            category = entry.get("category", "general")
            
            if tool not in tool_feedback:
                tool_feedback[tool] = {"positive": 0, "negative": 0, "total": 0}
            
            tool_feedback[tool]["total"] += 1
            
            if fb_type in ("thumbs_down", "correction"):
                tool_feedback[tool]["negative"] += 1
                category_counts[category] = category_counts.get(category, 0) + 1
                
                if fb_type == "correction" and entry.get("details"):
                    recent_corrections.append({
                        "tool": tool,
                        "correction": entry["details"][:200],
                        "category": category,
                    })
            elif fb_type in ("thumbs_up",):
                tool_feedback[tool]["positive"] += 1
            elif fb_type == "rating":
                rating = entry.get("rating", 3)
                if rating <= 2:
                    tool_feedback[tool]["negative"] += 1
                else:
                    tool_feedback[tool]["positive"] += 1
        
        # Find tools with high negative ratio
        negative_tools = []
        for tool, counts in tool_feedback.items():
            if counts["total"] >= 2:  # Need at least 2 feedback points
                ratio = counts["negative"] / counts["total"]
                if ratio > 0.4:  # >40% negative
                    negative_tools.append({
                        "tool": tool,
                        "negative_ratio": ratio,
                        "total_feedback": counts["total"],
                    })
        
        negative_tools.sort(key=lambda x: x["negative_ratio"], reverse=True)
        
        return {
            "negative_tools": negative_tools[:10],
            "problem_categories": dict(sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]),
            "recent_corrections": recent_corrections[-5:],
        }
    except Exception as e:
        logger.debug(f"[AutoEvolve] Error analyzing feedback: {e}")
        return {"negative_tools": [], "problem_categories": {}, "recent_corrections": []}


def get_evolution_suggestions() -> list[dict]:
    """M9: Generate evolution suggestions based on usage and feedback.
    
    Combina datos de uso (analyze_usage_gaps) con el historial de
    feedback del usuario (M9.2) para generar sugerencias de evolucion
    accionables:
    - Mejorar herramientas con alta tasa de error
    - Mejorar herramientas con feedback negativo consistente
    - Considerar remover herramientas nunca usadas
    - Ajustar comportamiento basado en correcciones del usuario
    
    Returns:
        Lista de dicts con sugerencias de evolucion, cada una con:
        - type: "improve_tool", "consider_removing", "fix_from_feedback"
        - tool: nombre de la herramienta
        - reason: razon de la sugerencia
        - priority: "high", "medium" o "low"
    """
    gaps = analyze_usage_gaps()
    feedback_analysis = _analyze_feedback_patterns()
    suggestions = []
    
    # From usage metrics: high error tools
    for tool_info in gaps["high_error_tools"]:
        suggestions.append({
            "type": "improve_tool",
            "tool": tool_info["tool"],
            "reason": f"Error rate {tool_info['error_rate']*100:.0f}%",
            "priority": "high" if tool_info["error_rate"] > 0.5 else "medium",
        })
    
    # M9.2: From user feedback: tools with consistent negative feedback
    for fb_tool in feedback_analysis["negative_tools"]:
        # Check if already suggested from usage metrics
        already_suggested = any(s["tool"] == fb_tool["tool"] for s in suggestions)
        if not already_suggested:
            suggestions.append({
                "type": "fix_from_feedback",
                "tool": fb_tool["tool"],
                "reason": f"User negative feedback ratio: {fb_tool['negative_ratio']*100:.0f}% ({fb_tool['total_feedback']} reports)",
                "priority": "high" if fb_tool["negative_ratio"] > 0.7 else "medium",
            })
        else:
            # Boost priority if both metrics and feedback agree
            for s in suggestions:
                if s["tool"] == fb_tool["tool"]:
                    s["reason"] += f" + negative feedback ({fb_tool['negative_ratio']*100:.0f}%)"
                    if fb_tool["negative_ratio"] > 0.6:
                        s["priority"] = "high"
    
    # M9.2: From user corrections: specific improvements
    for correction in feedback_analysis["recent_corrections"]:
        suggestions.append({
            "type": "fix_from_feedback",
            "tool": correction["tool"],
            "reason": f"User correction: {correction['correction'][:100]}",
            "priority": "medium",
        })
    
    # Never-used tools: consider removing
    for tool_name in gaps["never_used_tools"][:5]:
        suggestions.append({
            "type": "consider_removing",
            "tool": tool_name,
            "reason": "Never used in current session",
            "priority": "low",
        })
    
    # Deduplicate by tool+type
    seen = set()
    deduped = []
    for s in suggestions:
        key = (s["tool"], s["type"])
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    
    return deduped


# ============================================================
# SINGLETON
# ============================================================

_evolver_instance: Optional[AutoEvolver] = None

def get_evolver(memory=None) -> AutoEvolver:
    """Obtiene la instancia singleton del AutoEvolver."""
    global _evolver_instance
    if _evolver_instance is None:
        _evolver_instance = AutoEvolver(memory=memory)
    return _evolver_instance
