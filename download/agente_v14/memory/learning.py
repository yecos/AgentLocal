"""
=============================================================
AGENTE v14 - Sistema de Aprendizaje
=============================================================
Correcciones, conocimiento, patrones aprendidos.
=============================================================
"""

import os
import json
import logging
from datetime import datetime

from config import (
    CORRECTIONS_FILE, FEEDBACK_FILE, PATTERNS_FILE,
    KNOWLEDGE_FILE, logger
)


class LearningSystem:
    """Sistema de aprendizaje persistente con correcciones y conocimiento."""

    @staticmethod
    def _load(filepath, default=None):
        if default is None:
            default = []
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return default

    @staticmethod
    def _save(filepath, data):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save_knowledge(self, topic, content, source="experience"):
        knowledge = self._load(KNOWLEDGE_FILE, [])
        for k in knowledge:
            if k["topic"].lower() == topic.lower():
                k["content"] = content
                k["updated"] = datetime.now().isoformat()
                self._save(KNOWLEDGE_FILE, knowledge)
                return
        knowledge.append({
            "topic": topic, "content": content, "source": source,
            "created": datetime.now().isoformat()
        })
        self._save(KNOWLEDGE_FILE, knowledge)

    def get_knowledge(self, topic=None):
        knowledge = self._load(KNOWLEDGE_FILE, [])
        if topic:
            return [k for k in knowledge if topic.lower() in k["topic"].lower()]
        return knowledge

    def save_correction(self, user_msg, wrong_action, correct_action, reason=""):
        corrections = self._load(CORRECTIONS_FILE, [])
        corrections.append({
            "timestamp": datetime.now().isoformat(),
            "user_message": user_msg, "wrong_action": wrong_action,
            "correct_action": correct_action, "reason": reason
        })
        self._save(CORRECTIONS_FILE, corrections)
        self.save_knowledge(
            f"correccion:{user_msg[:50]}",
            f"Cuando el usuario dice '{user_msg}', NO hacer '{wrong_action}'. "
            f"Hacer '{correct_action}'. Razon: {reason}",
            source="user_correction"
        )

    def get_lessons(self):
        knowledge = self._load(KNOWLEDGE_FILE, [])
        return [k["content"] for k in knowledge if k["topic"].startswith("leccion:")]

    def get_corrections_for(self, user_msg):
        corrections = self._load(CORRECTIONS_FILE, [])
        msg_lower = user_msg.lower()
        relevant = []
        for c in corrections:
            if any(w in msg_lower for w in c["user_message"].lower().split() if len(w) > 3):
                relevant.append(c)
        return relevant[-5:]

    def get_stats(self):
        corrections = self._load(CORRECTIONS_FILE, [])
        return {
            "knowledge": len(self._load(KNOWLEDGE_FILE, [])),
            "corrections": len(corrections),
            "patterns": len(self._load(PATTERNS_FILE, [])),
            "feedback": len(self._load(FEEDBACK_FILE, [])),
        }
