"""
SkillHealthChecker — Verifies that each skill works correctly.
Runs minimal test cases for each tool to detect silent breakage.
"""

from __future__ import annotations
import logging
from tools.registry import TOOL_FUNCTIONS

logger = logging.getLogger(__name__)

# Minimal test cases per skill
SKILL_TESTS = {
    "buscar_web": {
        "params": {"consulta": "test ping"},
        "expect_not_contains": ["Traceback", "Exception"],
        "timeout": 10,
    },
    "ejecutar_comando": {
        "params": {"comando": "echo health_check"},
        "expect_contains": ["health_check"],
        "timeout": 5,
    },
    "leer_archivo": {
        "params": {"ruta": "/dev/null"},
        "expect_not_contains": ["ERROR"],
        "timeout": 5,
    },
    "listar_archivos": {
        "params": {"ruta": "/tmp"},
        "expect_not_contains": ["Traceback"],
        "timeout": 5,
    },
    "ejecutar_python": {
        "params": {"codigo": "print('health_check_ok')"},
        "expect_contains": ["health_check_ok"],
        "timeout": 10,
    },
    "review_code": {
        "params": {"ruta": "/dev/null", "profundidad": "rapido"},
        "expect_not_contains": ["Traceback"],
        "timeout": 15,
    },
    "resumir_documento": {
        "params": {"ruta": "/dev/null", "tipo_resumen": "ejecutivo"},
        "expect_not_contains": ["Traceback"],
        "timeout": 10,
    },
    "query_natural_language": {
        "params": {"pregunta": "test"},
        "expect_contains": ["ERROR"],  # Expected: no db_path provided
        "timeout": 5,
    },
}


class SkillHealthChecker:
    """Verifies that each skill works correctly."""

    def __init__(self):
        self.results: dict[str, dict] = {}

    def run_health_check(self, skill_names: list[str] = None) -> dict:
        """Run health checks for specified skills (or all with tests)."""
        skills_to_test = skill_names or list(SKILL_TESTS.keys())

        for skill in skills_to_test:
            if skill not in SKILL_TESTS:
                self.results[skill] = {"status": "no_test", "reason": "No test defined"}
                continue

            if skill not in TOOL_FUNCTIONS:
                self.results[skill] = {"status": "not_registered", "reason": "Tool not in registry"}
                continue

            test_config = SKILL_TESTS[skill]

            try:
                result = TOOL_FUNCTIONS[skill](**test_config["params"])
                result_str = str(result)

                passed = True
                # Check expected content
                for expected in test_config.get("expect_contains", []):
                    if expected.lower() not in result_str.lower():
                        passed = False

                # Check unexpected content
                for unexpected in test_config.get("expect_not_contains", []):
                    if unexpected.lower() in result_str.lower():
                        passed = False

                self.results[skill] = {
                    "status": "ok" if passed else "degraded",
                    "output_preview": result_str[:100],
                }

            except Exception as e:
                self.results[skill] = {"status": "error", "error": str(e)[:100]}

        return self.results

    def get_summary(self) -> str:
        """Return a human-readable summary."""
        ok = sum(1 for r in self.results.values() if r["status"] == "ok")
        total = len(self.results)
        return f"Skills health: {ok}/{total} OK"

    def get_detailed(self) -> dict:
        """Return detailed results."""
        return {
            "summary": self.get_summary(),
            "results": self.results,
            "total": len(self.results),
            "ok": sum(1 for r in self.results.values() if r["status"] == "ok"),
            "degraded": sum(1 for r in self.results.values() if r["status"] == "degraded"),
            "error": sum(1 for r in self.results.values() if r["status"] == "error"),
            "no_test": sum(1 for r in self.results.values() if r["status"] == "no_test"),
            "not_registered": sum(1 for r in self.results.values() if r["status"] == "not_registered"),
        }


# Singleton
_checker: SkillHealthChecker | None = None

def get_skill_health_checker() -> SkillHealthChecker:
    global _checker
    if _checker is None:
        _checker = SkillHealthChecker()
    return _checker
