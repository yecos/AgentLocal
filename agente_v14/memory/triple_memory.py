"""
=============================================================
AGENTE v14 - Triple Memoria (Mejorada)
=============================================================
1. Corto Plazo: Conversacion actual (ventana deslizante)
2. Largo Plazo: Conocimiento con busqueda semantica (VectorStore)
3. Trabajo: Scratchpad para la tarea actual

v14.5: Integracion con HybridVectorStore y MultiSignalReranker.
       recall() ahora pasa por re-ranker multi-señal.
       Decaimiento diferenciado por tipo de contenido.
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

# Decaimiento diferenciado por tipo de contenido (en dias half-life)
DECAY_HALF_LIFE_BY_TYPE = {
    "knowledge": 365,     # Conocimiento factual: decae muy lentamente (1 año)
    "correction": 180,    # Correcciones: decaimiento lento (6 meses)
    "lesson": 90,         # Lecciones aprendidas: 3 meses
    "experience": 60,     # Experiencia: 2 meses
    "task": 14,           # Tareas: decaen rapido (2 semanas)
    "conversation": 7,    # Conversacion: decae muy rapido (1 semana)
    "note": 30,           # Notas: 1 mes
}


class TripleMemory:
    """
    Sistema de Triple Memoria v14.5.
    Fuente unica de verdad para el historial de conversacion.
    Integra busqueda hibrida BM25+Vectorial y re-ranking multi-señal.
    """

    def __init__(self, use_hybrid=True, use_reranker=True):
        self.short_term = []  # Memoria a corto plazo (conversacion)
        self._use_reranker = use_reranker
        self._reranker = None

        # Usar factory: HybridVectorStore(ChromaDB/SimpleVectorStore + BM25)
        try:
            self.long_term = create_vector_store(use_hybrid=use_hybrid, use_reranker=use_reranker)
            logger.info("TripleMemory: vector store inicializado via factory (hibrido)")
        except Exception as e:
            logger.warning(f"Factory fallo, usando VectorStore basico: {e}")
            self.long_term = VectorStore()

        # Inicializar re-ranker si se solicita
        if use_reranker:
            try:
                from memory.reranker import MultiSignalReranker
                self._reranker = MultiSignalReranker(use_adaptive_weights=True)
                logger.info("TripleMemory: re-ranker multi-señal activado")
            except ImportError as e:
                logger.warning(f"Re-ranker no disponible ({e}), usando recall directo")
            except Exception as e:
                logger.warning(f"Error inicializando re-ranker: {e}")

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
        # Auto-cleanup al iniciar: limpiar memoria si hay demasiadas entradas
        self._auto_cleanup()

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
                    try:
                        self.long_term.add(
                            msg["content"][:500],
                            metadata={"type": "conversation", "role": msg["role"]},
                            skip_embedding=SKIP_EMBED_ON_INTERACTION
                        )
                    except Exception as e:
                        logger.debug(f"Error guardando mensaje viejo en memoria: {e}")
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
            metadata: Metadatos opcionales. Si incluye 'type', se usa para
                     decaimiento diferenciado.
        v14.5: Anade tipo de contenido para decaimiento diferenciado.
        """
        try:
            # Enriquecer metadata con tipo para decaimiento diferenciado
            meta = metadata or {}
            if "type" not in meta:
                # Inferir tipo del contenido
                meta["type"] = self._infer_content_type(text)
            return self.long_term.add(text, metadata=meta, skip_embedding=fast)
        except Exception as e:
            logger.warning(f"Error guardando en memoria a largo plazo (no critico): {e}")
            return None

    def _infer_content_type(self, text):
        """Infiere el tipo de contenido a partir del texto.

        Se usa para decaimiento diferenciado.
        """
        text_lower = text.lower()

        # Patrones heuristicos
        if any(w in text_lower for w in ["correccion", "no hagas", "error corregido"]):
            return "correction"
        if any(w in text_lower for w in ["leccion", "aprendi", "importante recordar"]):
            return "lesson"
        if any(w in text_lower for w in ["tarea", "pendiente", "por hacer", "todo"]):
            return "task"
        if any(w in text_lower for w in ["nota", "recordar", "tener en cuenta"]):
            return "note"
        # Default: experiencia general
        return "experience"

    def recall(self, query, limit=5):
        """Recupera recuerdos relevantes de la memoria a largo plazo.

        v14.5: Si el re-ranker esta activo, pasa los resultados por
        MultiSignalReranker antes de retornarlos.
        """
        try:
            results = self.long_term.search(query, limit=limit * 2)  # Over-retrieve for reranking

            if self._reranker and results:
                reranked = self._reranker.rerank(query, results, limit=limit)
                return reranked

            return results[:limit]
        except Exception as e:
            logger.warning(f"Error buscando en memoria a largo plazo (no critico): {e}")
            return []

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
        """Construye contexto enriquecido combinando las 3 memorias.
        v14.5: Usa recall() con re-ranker para mejor calidad de contexto.
        """
        context_parts = []
        budget_remaining = MAX_CONTEXT_CHARS

        # 1. Memoria de Trabajo - max 800 chars
        try:
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
        except Exception as e:
            logger.debug(f"Error construyendo contexto de trabajo: {e}")

        # 2. Correcciones aprendidas - max 400 chars
        try:
            corrections = learning.get_corrections_for(query)
            if corrections and budget_remaining > 200:
                corr_text = "\n".join([
                    f"  - NO hagas '{c['wrong_action']}'. Haz '{c['correct_action']}'"
                    for c in corrections[-3:]
                ])
                corr_full = f"CORRECCIONES:\n{corr_text}"[:400]
                context_parts.append(corr_full)
                budget_remaining -= len(corr_full)
        except Exception as e:
            logger.debug(f"Error obteniendo correcciones: {e}")

        # 3. Memoria a Largo Plazo - budget restante (con re-ranker)
        try:
            if budget_remaining > 200:
                recall_results = self.recall(query, limit=3)
                if recall_results:
                    knowledge_text = "\n".join([
                        f"  - [{r.get('rerank_score', r.get('score', 0)):.2f}] {r['text'][:150]}"
                        for r in recall_results
                    ])
                    knowledge_full = f"CONOCIMIENTO RELEVANTE:\n{knowledge_text}"
                    context_parts.append(knowledge_full[:budget_remaining])
        except Exception as e:
            logger.debug(f"Error obteniendo conocimiento: {e}")

        # 4. Resumen si conversacion larga
        try:
            if len(self.short_term) > 10:
                summary = self._get_conversation_summary()
                if summary:
                    summary_text = f"RESUMEN: {summary}"[:300]
                    context_parts.append(summary_text)
        except Exception as e:
            logger.debug(f"Error generando resumen: {e}")

        return "\n\n".join(context_parts) if context_parts else ""

    def _get_conversation_summary(self):
        """Genera un resumen de la conversacion. Usa LLM si la conversacion es muy larga."""
        if self._summary_cache and self._summary_last_update:
            msgs_since = len(self.short_term) - self._summary_last_update
            if msgs_since < 5:
                return self._summary_cache

        # Si hay mas de 20 mensajes, intentar resumen con LLM (mas inteligente)
        if len(self.short_term) > 20:
            llm_summary = self._generate_llm_summary()
            if llm_summary:
                self._summary_cache = llm_summary
                self._summary_last_update = len(self.short_term)
                return llm_summary

        # Fallback: resumen simple por temas
        user_msgs = [m["content"][:80] for m in self.short_term if m["role"] == "user"]
        if not user_msgs:
            return ""
        summary = "Temas recientes: " + "; ".join(user_msgs[-5:])
        self._summary_cache = summary
        self._summary_last_update = len(self.short_term)
        return summary

    def _generate_llm_summary(self):
        """Usa el LLM para generar un resumen inteligente de la conversacion."""
        try:
            from llm import ollama

            # Tomar los ultimos 20 mensajes para resumir
            recent = self.short_term[-20:]
            conversation_text = "\n".join([
                f"{'Usuario' if m['role'] == 'user' else 'Asistente'}: {m['content'][:200]}"
                for m in recent
            ])

            prompt = (
                "Resume esta conversacion en 2-3 frases, mencionando los temas principales "
                "y cualquier tarea pendiente o resultado importante. Se conciso:\n\n"
                f"{conversation_text}"
            )

            messages = [
                {"role": "system", "content": "Eres un asistente que resume conversaciones. Responde en espanol, maximo 3 frases."},
                {"role": "user", "content": prompt}
            ]

            summary = ollama.generate_chat(messages)
            if summary and len(summary) > 20:
                return f"RESUMEN: {summary[:300]}"
        except Exception as e:
            logger.debug(f"Error generando resumen LLM: {e}")
        return ""

    def save_session(self):
        try:
            session_data = {
                "short_term": self.short_term[-MAX_CONVERSATION_MEMORY:],
                "working": self.working,
                "saved_at": datetime.now().isoformat()
            }
            with open(self._session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Error guardando sesion: {e}")

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
        except Exception as e:
            logger.warning(f"Error cargando sesion: {e}")
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
        # Info de re-ranker
        if self._reranker:
            stats["reranker_stats"] = self._reranker.stats()
        # Info de vector store hibrido
        if hasattr(self.long_term, "get_info"):
            stats["hybrid_info"] = self.long_term.get_info()
        # Info de ultima sesion
        try:
            if os.path.exists(self._session_file):
                mtime = os.path.getmtime(self._session_file)
                stats["last_session_age_hours"] = round(
                    (datetime.now().timestamp() - mtime) / 3600, 1
                )
        except Exception as e:
            logger.debug(f"Error obteniendo stats de sesion: {e}")
        return stats

    def cleanup(self, max_entries=500):
        """Limpia entradas viejas de la memoria a largo plazo."""
        before = self.long_term.count()
        if hasattr(self.long_term, 'cleanup'):
            self.long_term.cleanup(max_entries=max_entries)
        after = self.long_term.count()
        removed = before - after
        if removed > 0:
            logger.info(f"Cleanup de memoria: eliminadas {removed} entradas viejas ({before} -> {after})")
        return removed

    def _auto_cleanup(self):
        """Auto-cleanup al iniciar si la memoria esta llena."""
        try:
            count = self.long_term.count()
            if count > 800:  # Si hay mas de 800 entradas, limpiar a 500
                logger.info(f"Auto-cleanup: {count} entradas en memoria, limpiando...")
                self.cleanup(max_entries=500)
        except Exception as e:
            logger.debug(f"Auto-cleanup fallo (no critico): {e}")
