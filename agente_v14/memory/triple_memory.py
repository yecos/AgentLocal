"""
=============================================================
AGENTE v14 - Triple Memoria
=============================================================
1. Corto Plazo: Conversacion actual (ventana deslizante)
2. Largo Plazo: Conocimiento con busqueda semantica (VectorStore)
3. Trabajo: Scratchpad para la tarea actual

v14: Sin duplicacion de historial, usa solo TripleMemory.
=============================================================
"""

import os
import json
import logging
from datetime import datetime

from config import (
    LEARN_DIR, MAX_CONVERSATION_MEMORY, MAX_CONTEXT_CHARS,
    SKIP_EMBED_ON_INTERACTION, logger
)
from memory.vectorstore import VectorStore
from memory.chroma_store import create_vector_store
from memory.learning import LearningSystem
from llm import embed_cache

learning = LearningSystem()


class TripleMemory:
    """
    Sistema de Triple Memoria v14.
    Fuente unica de verdad para el historial de conversacion.
    """

    def __init__(self):
        self.short_term = []  # Memoria a corto plazo (conversacion)
        # Usar factory: ChromaDB si esta disponible, sino VectorStore casero
        # Ambos incluyen decaimiento temporal y deduplicacion
        try:
            self.long_term = create_vector_store()
            logger.info("TripleMemory: vector store inicializado via factory")
        except Exception as e:
            logger.warning(f"Factory fallo, usando VectorStore basico: {e}")
            self.long_term = VectorStore()
        self.working = {  # Memoria de trabajo (scratchpad)
            "current_task": "",
            "task_steps": [],
            "notes": [],
            "context_files": [],
            "last_error": "",
            "last_success": "",
        }
        self._summary_cache = None
        self._summary_last_update = None
        self._session_file = os.path.join(LEARN_DIR, "session.json")
        self._auto_save_counter = 0

    def add_conversation(self, role, content):
        """Agrega un mensaje a la memoria a corto plazo."""
        self.short_term.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        # Mantener ventana deslizante
        if len(self.short_term) > MAX_CONVERSATION_MEMORY * 2:
            removed = self.short_term[:len(self.short_term) - MAX_CONVERSATION_MEMORY * 2]
            for msg in removed:
                if msg["role"] == "assistant" and len(msg["content"]) > 50:
                    self.long_term.add(
                        msg["content"][:500],
                        metadata={"type": "conversation", "role": msg["role"]},
                        skip_embedding=SKIP_EMBED_ON_INTERACTION
                    )
            self.short_term = self.short_term[-(MAX_CONVERSATION_MEMORY * 2):]

        # Auto-save cada 5 mensajes
        self._auto_save_counter += 1
        if self._auto_save_counter >= 5:
            self._auto_save_counter = 0
            self.save_session()

    def remember(self, text, metadata=None, fast=False):
        """Guarda algo en la memoria a largo plazo.
        
        Args:
            fast: Si True, salta el calculo de embedding (mas rapido).
                  La entrada solo aparecera en busquedas por texto.
        """
        # Todos los backends ahora soportan skip_embedding nativamente:
        # - VectorStore (vectorstore.py)
        # - ChromaVectorStore (chroma_store.py)
        # - SimpleVectorStore (chroma_store.py fallback)
        return self.long_term.add(text, metadata=metadata, skip_embedding=fast)

    def recall(self, query, limit=5):
        """Recupera recuerdos relevantes de la memoria a largo plazo."""
        return self.long_term.search(query, limit=limit)

    def set_task(self, task):
        self.working["current_task"] = task
        self.working["task_steps"] = []
        self.working["notes"] = []

    def add_step(self, step, result=""):
        self.working["task_steps"].append({
            "step": step,
            "result": result[:200],
            "timestamp": datetime.now().isoformat()
        })

    def add_note(self, note):
        self.working["notes"].append(note)

    def set_error(self, error):
        self.working["last_error"] = error

    def set_success(self, success):
        self.working["last_success"] = success

    def get_context_for(self, query):
        """Construye contexto enriquecido combinando las 3 memorias."""
        context_parts = []
        budget_remaining = MAX_CONTEXT_CHARS

        # 1. Memoria de Trabajo - max 800 chars
        if self.working["current_task"]:
            work_context = f"TAREA ACTUAL: {self.working['current_task']}"
            if self.working["task_steps"]:
                steps_text = "\n".join([
                    f"  - {s['step']}: {s['result']}"
                    for s in self.working["task_steps"][-5:]
                ])
                work_context += f"\nPASOS REALIZADOS:\n{steps_text}"
            if self.working["last_error"]:
                work_context += f"\nULTIMO ERROR: {self.working['last_error']}"
            if self.working["notes"]:
                work_context += f"\nNOTAS: {'; '.join(self.working['notes'][-3:])}"

            work_text = work_context[:800]
            context_parts.append(work_text)
            budget_remaining -= len(work_text)

        # 2. Correcciones aprendidas - max 400 chars
        corrections = learning.get_corrections_for(query)
        if corrections and budget_remaining > 200:
            corr_text = "\n".join([
                f"  - NO hagas '{c['wrong_action']}'. Haz '{c['correct_action']}'"
                for c in corrections[-3:]
            ])
            corr_full = f"CORRECCIONES:\n{corr_text}"[:400]
            context_parts.append(corr_full)
            budget_remaining -= len(corr_full)

        # 3. Memoria a Largo Plazo - budget restante
        if budget_remaining > 200:
            recall_results = self.recall(query, limit=3)
            if recall_results:
                knowledge_text = "\n".join([
                    f"  - [{r.get('score', 0):.2f}] {r['text'][:150]}"
                    for r in recall_results
                ])
                knowledge_full = f"CONOCIMIENTO RELEVANTE:\n{knowledge_text}"
                context_parts.append(knowledge_full[:budget_remaining])

        # 4. Resumen si conversacion larga
        if len(self.short_term) > 10:
            summary = self._get_conversation_summary()
            if summary:
                summary_text = f"RESUMEN: {summary}"[:300]
                context_parts.append(summary_text)

        return "\n\n".join(context_parts) if context_parts else ""

    def _get_conversation_summary(self):
        if self._summary_cache and self._summary_last_update:
            msgs_since = len(self.short_term) - self._summary_last_update
            if msgs_since < 5:
                return self._summary_cache
        user_msgs = [m["content"][:80] for m in self.short_term if m["role"] == "user"]
        if not user_msgs:
            return ""
        summary = "Temas recientes: " + "; ".join(user_msgs[-5:])
        self._summary_cache = summary
        self._summary_last_update = len(self.short_term)
        return summary

    def save_session(self):
        try:
            session_data = {
                "short_term": self.short_term[-MAX_CONVERSATION_MEMORY:],
                "working": self.working,
                "saved_at": datetime.now().isoformat()
            }
            with open(self._session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_session(self):
        try:
            if os.path.exists(self._session_file):
                with open(self._session_file, "r", encoding="utf-8") as f:
                    session_data = json.load(f)
                saved_at = session_data.get("saved_at", "")
                if saved_at:
                    saved_time = datetime.fromisoformat(saved_at)
                    hours_ago = (datetime.now() - saved_time).total_seconds() / 3600
                    if hours_ago < 24:
                        self.short_term = session_data.get("short_term", [])
                        self.working = session_data.get("working", self.working)
                        return True
                self.working = session_data.get("working", self.working)
        except Exception:
            pass
        return False

    def clear_session(self):
        self.short_term = []
        self.working = {
            "current_task": "",
            "task_steps": [],
            "notes": [],
            "context_files": [],
            "last_error": "",
            "last_success": "",
        }
        self._summary_cache = None
        self._summary_last_update = None

    def get_stats(self):
        stats = {
            "short_term_messages": len(self.short_term),
            "long_term_entries": self.long_term.count(),
            "working_task": bool(self.working["current_task"]),
            "working_steps": len(self.working["task_steps"]),
            "corrections": len(learning.get_corrections_for("")),
            "embed_cache_size": len(embed_cache),
        }
        # Detectar tipo de backend
        backend_type = type(self.long_term).__name__
        stats["vector_backend"] = backend_type
        if hasattr(self.long_term, "count_with_vectors"):
            stats["long_term_with_vectors"] = self.long_term.count_with_vectors()
        return stats
