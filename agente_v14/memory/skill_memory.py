"""
SkillMemory — Memoria específica para outputs de skills.
Permite al agente recordar: "el PDF de marketing que creé ayer"
"""

import os
import json
import logging
from datetime import datetime
from config import LEARN_DIR

logger = logging.getLogger(__name__)

SKILL_MEMORY_FILE = os.path.join(LEARN_DIR, "skill_outputs.json")

# Skills que generan archivos (para auto-registro)
FILE_PRODUCING_SKILLS = {
    "crear_pdf", "crear_docx", "crear_xlsx", "crear_pptx",
    "generar_imagen", "crear_grafico", "crear_grafico_avanzado",
    "generar_codigo", "crear_dashboard", "crear_documento",
}


class SkillMemory:
    """Records and retrieves outputs of skills for future reference."""

    def __init__(self):
        self._outputs: list[dict] = []
        self._load()

    def record(self, skill_name: str, params: dict, output_path: str,
               description: str, user_request: str = ""):
        """Register a skill output for future reference."""
        entry = {
            "skill": skill_name,
            "params": {k: str(v)[:100] for k, v in params.items()},
            "output_path": output_path,
            "description": description[:200],
            "user_request": user_request[:100],
            "timestamp": datetime.now().isoformat(),
            "exists": os.path.exists(output_path) if output_path else False,
        }
        self._outputs.append(entry)
        if len(self._outputs) > 100:
            self._outputs = self._outputs[-100:]
        self._save()
        logger.info(f"[SkillMemory] Registrado: {skill_name} → {output_path}")

    def search(self, query: str, limit: int = 3) -> list[dict]:
        """Search skill outputs matching query."""
        query_lower = query.lower()
        scored = []
        for entry in self._outputs:
            score = 0
            for word in query_lower.split():
                if word in entry.get("description", "").lower():
                    score += 2
                if word in entry.get("user_request", "").lower():
                    score += 1
                if word in entry.get("skill", "").lower():
                    score += 1
            if score > 0:
                path = entry.get("output_path", "")
                entry["exists"] = os.path.exists(path) if path else False
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    def get_recent(self, skill_name: str = None, limit: int = 5) -> list[dict]:
        """Return most recent outputs, optionally filtered by skill."""
        outputs = self._outputs
        if skill_name:
            outputs = [o for o in outputs if o["skill"] == skill_name]
        return list(reversed(outputs))[:limit]

    def _load(self):
        """Load history from disk."""
        try:
            if os.path.exists(SKILL_MEMORY_FILE):
                with open(SKILL_MEMORY_FILE, "r", encoding="utf-8") as f:
                    self._outputs = json.load(f)
        except Exception as e:
            logger.debug(f"[SkillMemory] Error cargando: {e}")

    def _save(self):
        """Persist history to disk."""
        try:
            os.makedirs(os.path.dirname(SKILL_MEMORY_FILE), exist_ok=True)
            with open(SKILL_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._outputs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[SkillMemory] Error guardando: {e}")


_singleton = None

def get_skill_memory() -> SkillMemory:
    global _singleton
    if _singleton is None:
        _singleton = SkillMemory()
    return _singleton
