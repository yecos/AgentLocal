"""
=============================================================
AGENTE LOCAL AUTONOMO v16 - Entry Point Streamlit
=============================================================
Interfaz web completa con: streaming, deep thinking, tokens,
model selector, file upload, voice controls, sub-agent status,
chat export, y visualizacion mejorada.

Para ejecutar: streamlit run app.py
=============================================================
"""

import os
import json
import time
import streamlit as st
from agent import ReactAgent
from memory.triple_memory import TripleMemory
from llm import ollama
from utils.metrics import get_metrics

# ============================================================
# INICIALIZACION
# ============================================================

def init_session():
    """Inicializa la sesion de Streamlit con el agente."""
    if "agent" not in st.session_state:
        memory = TripleMemory()
        memory.load_session()
        st.session_state.agent = ReactAgent(memory=memory)
        st.session_state.memory = memory
        st.session_state.pending_dangerous_cmd = None
        st.session_state.last_meta_status = None
        st.session_state.last_token_stats = None
        st.session_state.last_deep_thinking = None
        st.session_state.uploaded_files = []
        ollama.detect_models()

        # Verificar GPU al inicio
        gpu = ollama.check_gpu_status()
        if gpu is False:
            st.session_state.gpu_warning = True
        else:
            st.session_state.gpu_warning = False

init_session()

# ============================================================
# STYLES
# ============================================================

STYLES = """
<style>
.stApp { max-width: 1200px; margin: 0 auto; }

.main-title {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.2rem; font-weight: 800; text-align: center; margin-bottom: 0.3rem;
}
.main-subtitle {
    text-align: center; color: #888; font-size: 0.85rem; margin-bottom: 1.5rem;
}

.thinking-box {
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    color: #00ff88; padding: 16px; border-radius: 12px;
    font-family: 'Consolas', 'Monaco', monospace; font-size: 11px;
    max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;
    border: 1px solid rgba(100, 100, 255, 0.2); box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
}
.thinking-box .thinking { color: #88aaff; }
.thinking-box .plan { color: #ffaa44; }
.thinking-box .execution { color: #00ff88; }
.thinking-box .observation { color: #44ddaa; }
.thinking-box .evaluation { color: #aa88ff; }
.thinking-box .warning { color: #ffaa00; }
.thinking-box .error { color: #ff4444; }
.thinking-box .cloud { color: #44aaff; }
.thinking-box .input { color: #88ff88; }
.thinking-box .react { color: #ff88ff; font-weight: bold; }
.thinking-box .success { color: #44ff88; font-weight: bold; }
.thinking-box .deep_thinking { color: #ff88ff; }

.deep-thinking-box {
    background: linear-gradient(135deg, #1a0a3e, #2d1b69, #1a0a3e);
    color: #dd88ff; padding: 16px; border-radius: 12px;
    border: 1px solid rgba(150, 80, 255, 0.3);
    box-shadow: 0 4px 15px rgba(100, 0, 200, 0.2);
    margin: 8px 0;
}
.deep-thinking-box .complexity-bar {
    height: 6px; border-radius: 3px; background: rgba(255,255,255,0.1);
    margin: 8px 0;
}
.deep-thinking-box .complexity-fill {
    height: 100%; border-radius: 3px;
    background: linear-gradient(90deg, #667eea, #764ba2, #ff6b9d);
}
.deep-thinking-box .plan-step {
    padding: 4px 8px; margin: 2px 0; border-left: 3px solid #764ba2;
    background: rgba(118, 75, 162, 0.1);
}

.danger-box {
    background: linear-gradient(135deg, #4a1010, #6b1a1a);
    color: #ff8888; padding: 16px; border-radius: 12px;
    border: 2px solid #ff4444; margin: 10px 0;
}
.danger-box .cmd { color: #ffcc00; font-family: monospace; font-weight: bold; }

.tool-badge {
    display: inline-block; background: #2d2d6b; color: #88aaff;
    padding: 2px 8px; border-radius: 10px; font-size: 11px;
    margin: 2px; font-family: monospace;
}
.tool-badge.success { background: #1a3a2a; color: #44ff88; }
.tool-badge.error { background: #3a1a1a; color: #ff4444; }

.token-bar {
    height: 8px; border-radius: 4px; background: rgba(255,255,255,0.1);
    margin: 4px 0; overflow: hidden;
}
.token-fill {
    height: 100%; border-radius: 4px; transition: width 0.3s ease;
}
.token-fill.low { background: linear-gradient(90deg, #44ff88, #66ffaa); }
.token-fill.medium { background: linear-gradient(90deg, #ffaa44, #ffcc66); }
.token-fill.high { background: linear-gradient(90deg, #ff4444, #ff6666); }

.subagent-status {
    display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0;
}
.subagent-card {
    background: #1a2a3a; color: #88ccff; padding: 6px 12px;
    border-radius: 8px; font-size: 12px; font-family: monospace;
    border: 1px solid rgba(100, 150, 255, 0.2);
}
.subagent-card.running { border-color: #44ff88; color: #44ff88; }
.subagent-card.done { border-color: #888; color: #888; }

.meta-badge {
    display: inline-block; background: #1a3a2a; color: #44ff88;
    padding: 2px 8px; border-radius: 10px; font-size: 11px;
    margin: 2px; font-family: monospace;
}
.meta-badge.warning {
    background: #3a2a1a; color: #ffaa00;
}

.gpu-warning {
    background: linear-gradient(135deg, #3a2a1a, #5a3a1a);
    color: #ffaa00; padding: 12px; border-radius: 8px;
    border: 1px solid #ff8800; margin: 8px 0; font-size: 13px;
}

.file-chip {
    display: inline-block; background: #2a3a1a; color: #88ff88;
    padding: 2px 10px; border-radius: 12px; font-size: 12px;
    margin: 2px; border: 1px solid rgba(100, 255, 100, 0.2);
}

[data-testid="stChatMessage"] { border-radius: 12px; padding: 12px 16px; margin: 4px 0; }
.stButton > button { border-radius: 8px; transition: all 0.2s; }
.stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(100, 100, 255, 0.3); }

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.1); border-radius: 3px; }
::-webkit-scrollbar-thumb { background: rgba(100, 100, 255, 0.3); border-radius: 3px; }
</style>
"""

# ============================================================
# INTERFAZ STREAMLIT
# ============================================================

def main():
    st.set_page_config(
        page_title="Agente Autonomo v16",
        page_icon="🧠",
        layout="wide"
    )

    st.markdown(STYLES, unsafe_allow_html=True)

    # Titulo
    st.markdown('<h1 class="main-title">Agente Autonomo v16</h1>', unsafe_allow_html=True)

    # Info del modelo + GPU
    model_info = f"Modelo: {ollama.model or 'detectando...'}"
    if ollama.chat_model and ollama.chat_model != ollama.model:
        model_info += f" | Chat: {ollama.chat_model}"
    if ollama.code_model and ollama.code_model != ollama.model:
        model_info += f" | Code: {ollama.code_model}"

    # Token stats en subtitulo
    token_stats = st.session_state.get("last_token_stats")
    if token_stats:
        used = token_stats.get("used", 0)
        total = token_stats.get("context_size", 0)
        pct = token_stats.get("utilization_pct", 0)
        model_info += f" | Tokens: {used:,}/{total:,} ({pct}%)"

    gpu_status = ollama._gpu_status
    if gpu_status is True:
        model_info += " | GPU: ACTIVA"
    elif gpu_status is False:
        model_info += " | GPU: NO DETECTADA"
    else:
        model_info += " | GPU: desconocido"

    st.markdown(f'<p class="main-subtitle">{model_info}</p>', unsafe_allow_html=True)

    # Advertencia GPU
    if st.session_state.get("gpu_warning"):
        st.markdown("""
        <div class="gpu-warning">
            <strong>GPU NO detectada por Ollama</strong> - El agente corre en CPU, lo cual es MUY lento.<br>
            Ejecuta <code>python check_gpu.py</code> para diagnosticar y solucionar.<br>
            Solucion rapida: Panel de Control NVIDIA > "Alto rendimiento" para ollama.exe
        </div>
        """, unsafe_allow_html=True)

    # ---- Deep Thinking Display (si hay de la ultima consulta) ----
    deep_thinking = st.session_state.get("last_deep_thinking")
    if deep_thinking:
        depth = deep_thinking.get("depth", 0)
        complexity = deep_thinking.get("complexity", 0)
        plan = deep_thinking.get("plan", [])
        reasoning = deep_thinking.get("reasoning", "")
        depth_labels = {0: "ninguno", 1: "rapido", 2: "completo", 3: "profundo"}

        with st.expander(f"🧠 Pensamiento Profundo (profundidad: {depth_labels.get(depth, '?')})", expanded=False):
            # Barra de complejidad
            complexity_pct = int(complexity * 100)
            st.markdown(
                f'<div class="deep-thinking-box">'
                f'<b>Complejidad:</b> {complexity:.2f} ({complexity_pct}%)'
                f'<div class="complexity-bar"><div class="complexity-fill" style="width:{complexity_pct}%"></div></div>'
                f'</div>',
                unsafe_allow_html=True
            )

            # Plan
            if plan:
                st.markdown("**Plan:**")
                plan_html = '<div class="deep-thinking-box">'
                for i, step in enumerate(plan[:8]):
                    plan_html += f'<div class="plan-step">{i+1}. {step}</div>'
                plan_html += '</div>'
                st.markdown(plan_html, unsafe_allow_html=True)

            # Razonamiento
            if reasoning:
                st.markdown("**Razonamiento:**")
                st.caption(reasoning[:500])

    # ---- Token Stats Bar ----
    if token_stats:
        pct = token_stats.get("utilization_pct", 0)
        level = "low" if pct < 60 else "medium" if pct < 85 else "high"
        breakdown = token_stats.get("breakdown", {})

        with st.expander("📊 Gestion de Tokens", expanded=False):
            st.markdown(
                f'<div class="token-bar"><div class="token-fill {level}" style="width:{min(pct, 100)}%"></div></div>',
                unsafe_allow_html=True
            )
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Sistema", f"{breakdown.get('system', 0):,}")
            with col2:
                st.metric("Contexto", f"{breakdown.get('context', 0):,}")
            with col3:
                st.metric("Herramientas", f"{breakdown.get('tools', 0):,}")
            with col4:
                st.metric("Disponibles", f"{token_stats.get('remaining', 0):,}")

            if token_stats.get("needs_compression"):
                st.warning(f"Compresion necesaria: {token_stats.get('compression_level', '?')}")

    # ---- File Upload ----
    with st.expander("📎 Subir Archivos", expanded=False):
        uploaded_files = st.file_uploader(
            "Sube imagenes, documentos o datos",
            accept_multiple_files=True,
            type=["png", "jpg", "jpeg", "gif", "webp", "pdf", "docx", "xlsx", "csv", "txt", "py", "js", "html", "json"]
        )
        if uploaded_files:
            st.session_state.uploaded_files = uploaded_files
            chips = " ".join([f'<span class="file-chip">{f.name}</span>' for f in uploaded_files])
            st.markdown(f"<div>{chips}</div>", unsafe_allow_html=True)

    # Chat
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # Mostrar deep thinking si lo hay
            if "deep_thinking" in msg and msg["deep_thinking"]:
                dt = msg["deep_thinking"]
                depth_labels = {0: "ninguno", 1: "rapido", 2: "completo", 3: "profundo"}
                with st.expander(f"🧠 Pensamiento: {depth_labels.get(dt.get('depth', 0), '?')} (complejidad: {dt.get('complexity', 0):.2f})"):
                    if dt.get("plan"):
                        for i, step in enumerate(dt["plan"][:5]):
                            st.text(f"  {i+1}. {step}")
                    if dt.get("reasoning"):
                        st.caption(dt["reasoning"][:300])

            # Mostrar tools ejecutadas si las hay
            if "tools_used" in msg and msg["tools_used"]:
                tools_html = " ".join([f'<span class="tool-badge">{t}</span>' for t in msg["tools_used"]])
                st.markdown(f"<div>{tools_html}</div>", unsafe_allow_html=True)

            # Mostrar token stats si lo hay
            if "token_stats" in msg and msg["token_stats"]:
                ts = msg["token_stats"]
                pct = ts.get("utilization_pct", 0)
                st.caption(f"Tokens: {ts.get('used', 0):,}/{ts.get('context_size', 0):,} ({pct}%)")

            # Mostrar estado metacognitivo si lo hay
            if "meta_status" in msg and msg["meta_status"]:
                meta = msg["meta_status"]
                conf = meta.get("confidence", 0)
                assessment = meta.get("assessment", "")
                conf_class = "" if conf >= 0.5 else "warning"
                meta_html = f'<span class="meta-badge {conf_class}">confianza: {conf:.0%}</span>'
                if assessment and assessment != "pending":
                    meta_html += f' <span class="meta-badge {conf_class}">{assessment}</span>'
                st.markdown(f"<div>{meta_html}</div>", unsafe_allow_html=True)

    # Input
    if prompt := st.chat_input("Que necesitas?"):
        _handle_user_input(prompt)

    # Verificar si hay comando peligroso pendiente de confirmacion
    if st.session_state.get("pending_dangerous_cmd"):
        _handle_dangerous_confirmation()


def _handle_user_input(prompt):
    """Maneja el input del usuario con streaming y metacognicion."""
    get_metrics().record_user_message()

    # Adjuntar archivos subidos si los hay
    uploaded = st.session_state.get("uploaded_files", [])
    if uploaded:
        file_names = ", ".join([f.name for f in uploaded])
        prompt = f"[Archivos adjuntos: {file_names}]\n\n{prompt}"
        st.session_state.uploaded_files = []  # Limpiar despues de usar

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        # Usar streaming
        response_placeholder = st.empty()
        thinking_placeholder = st.container()
        tools_used = []
        full_response = ""
        thinking_log = []
        meta_status = None
        token_stats = None
        deep_thinking_data = None
        subagents_running = []

        try:
            for event in st.session_state.agent.run_stream(prompt):
                event_type = event.get("type", "")

                if event_type == "text":
                    full_response += event.get("data", "")
                    response_placeholder.markdown(full_response + "▌")

                elif event_type == "thinking":
                    # Deep thinking event
                    deep_thinking_data = event.get("data", {})
                    depth = deep_thinking_data.get("depth", 0)
                    complexity = deep_thinking_data.get("complexity", 0)
                    plan = deep_thinking_data.get("plan", [])
                    depth_labels = {0: "ninguno", 1: "rapido", 2: "completo", 3: "profundo"}

                    with thinking_placeholder:
                        complexity_pct = int(complexity * 100)
                        thinking_html = (
                            f'<div class="deep-thinking-box">'
                            f'🧠 <b>Pensamiento Profundo</b> (profundidad: {depth_labels.get(depth, "?")} | complejidad: {complexity:.2f})<br>'
                            f'<div class="complexity-bar"><div class="complexity-fill" style="width:{complexity_pct}%"></div></div>'
                        )
                        if plan:
                            thinking_html += "<br><b>Plan:</b><br>"
                            for i, step in enumerate(plan[:5]):
                                thinking_html += f'<div class="plan-step">{i+1}. {step}</div>'
                        thinking_html += '</div>'
                        st.markdown(thinking_html, unsafe_allow_html=True)

                elif event_type == "tool_start":
                    tc = event.get("data", {})
                    tool_name = tc.get("name", "?") if isinstance(tc, dict) else str(tc)
                    tools_used.append(tool_name)
                    with thinking_placeholder:
                        # Badge con estado running
                        st.markdown(
                            f'<span class="tool-badge">⏳ {tool_name}</span>',
                            unsafe_allow_html=True
                        )

                elif event_type == "tool_result":
                    result = event.get("data", {})
                    tool_name = "?"
                    result_text = ""
                    if isinstance(result, dict):
                        tool_info = result.get("tool", {})
                        tool_name = tool_info.get("name", "?") if isinstance(tool_info, dict) else "?"
                        result_text = str(result.get("result", ""))[:100]

                    # Verificar si es un comando peligroso bloqueado
                    if "PELIGROSO" in result_text:
                        st.session_state.pending_dangerous_cmd = {
                            "tool": result.get("tool", {}),
                            "result": result.get("result", ""),
                            "original_prompt": prompt,
                            "tools_used": tools_used,
                        }
                        with thinking_placeholder:
                            st.warning(f"⚠️ Comando peligroso detectado: {tool_name}")
                    else:
                        with thinking_placeholder:
                            is_error = "ERROR" in result_text
                            badge_class = "error" if is_error else "success"
                            icon = "✗" if is_error else "✓"
                            st.markdown(
                                f'<span class="tool-badge {badge_class}">{icon} {tool_name}</span>',
                                unsafe_allow_html=True
                            )

                elif event_type == "meta":
                    meta_data = event.get("data", {})
                    conf = meta_data.get("confidence", 0)
                    with thinking_placeholder:
                        if conf < 0.4:
                            st.warning(
                                f"🧠 Metacognicion: Confianza baja ({conf:.0%}) - "
                                f"Revisando estrategia... ({meta_data.get('plan_changes', 0)} cambios de plan)"
                            )
                        else:
                            st.info(
                                f"🧠 Metacognicion: Confianza {conf:.0%} | "
                                f"Errores: {meta_data.get('errors', 0)} | "
                                f"Exitos: {meta_data.get('successes', 0)}"
                            )

                elif event_type == "done":
                    full_response = event.get("data", full_response)
                    thinking_log = event.get("thinking_log", [])
                    meta_status = event.get("meta_status")
                    token_stats = event.get("token_stats")
                    deep_thinking_from_done = event.get("deep_thinking_stats")
                    response_placeholder.markdown(full_response)

            # Mostrar thinking log
            if thinking_log:
                with st.expander("Proceso de pensamiento", expanded=False):
                    log_text = "\n".join(thinking_log)
                    for category, css_class in [
                        ("THINKING", "thinking"), ("PLAN", "plan"),
                        ("EXECUTION", "execution"), ("OBSERVATION", "observation"),
                        ("EVALUATION", "evaluation"), ("WARNING", "warning"),
                        ("ERROR", "error"), ("CLOUD", "cloud"),
                        ("INPUT", "input"), ("REACT", "react"),
                        ("SUCCESS", "success"), ("DEEP_THINKING", "deep_thinking"),
                    ]:
                        log_text = log_text.replace(
                            f"[{category}]",
                            f'<span class="{css_class}">[{category}]</span>'
                        )
                    st.markdown(
                        f'<div class="thinking-box">{log_text}</div>',
                        unsafe_allow_html=True
                    )

            # Mostrar resumen metacognitivo
            if meta_status:
                with st.expander("Auto-evaluacion", expanded=False):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        conf_val = meta_status.get("confidence", 0)
                        st.metric("Confianza", f"{conf_val:.0%}")
                    with col2:
                        st.metric("Errores", meta_status.get("errors", 0))
                        st.metric("Exitos", meta_status.get("successes", 0))
                    with col3:
                        st.metric("Cambios de plan", meta_status.get("plan_changes", 0))
                        assessment = meta_status.get("assessment", "N/A")
                        assessment_emoji = {
                            "excelente": "🟢", "bueno": "🟢",
                            "aceptable": "🟡", "problematico": "🔴",
                            "limite_alcanzado": "🔴",
                        }.get(assessment, "⚪")
                        st.metric("Evaluacion", f"{assessment_emoji} {assessment}")

        except Exception as e:
            # Fallback a modo no-streaming si falla
            full_response, thinking_log = st.session_state.agent.run(prompt)
            response_placeholder.markdown(full_response)
            if thinking_log:
                with st.expander("Proceso de pensamiento", expanded=False):
                    log_text = "\n".join(thinking_log)
                    st.markdown(
                        f'<div class="thinking-box">{log_text}</div>',
                        unsafe_allow_html=True
                    )

        # Guardar en session state
        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "tools_used": tools_used,
            "meta_status": meta_status,
            "token_stats": token_stats,
            "deep_thinking": deep_thinking_data,
        })
        st.session_state.last_meta_status = meta_status
        st.session_state.last_token_stats = token_stats
        st.session_state.last_deep_thinking = deep_thinking_data


def _handle_dangerous_confirmation():
    """Muestra dialogo de confirmacion para comandos peligrosos."""
    pending = st.session_state.pending_dangerous_cmd
    if not pending:
        return

    st.markdown("""
    <div class="danger-box">
        <h3>⚠️ Comando Peligroso Detectado</h3>
        <p>El agente quiere ejecutar un comando que podria ser destructivo.</p>
    </div>
    """, unsafe_allow_html=True)

    st.warning(f"Comando: {pending['result'][:200]}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Confirmar y ejecutar", type="primary"):
            from tools.sistema import ejecutar_comando
            tool = pending["tool"]
            params = tool.get("params", {})
            params["confirmar_peligroso"] = True
            try:
                result = ejecutar_comando(**params)
                st.success(f"Ejecutado: {result[:200]}")
            except Exception as e:
                st.error(f"Error: {e}")
            st.session_state.pending_dangerous_cmd = None
            st.rerun()

    with col2:
        if st.button("❌ Cancelar"):
            st.info("Comando cancelado.")
            st.session_state.pending_dangerous_cmd = None
            st.rerun()


# ============================================================
# SIDEBAR
# ============================================================
def _render_sidebar():
    """Renderiza el sidebar con stats, controles y model selector."""
    with st.sidebar:
        st.header("Estado del Agente")

        # ---- Sesion ----
        col_new, col_save = st.columns(2)
        with col_new:
            if st.button("🔄 Nueva Sesion"):
                get_metrics().reset()
                st.session_state.memory.clear_session()
                st.session_state.messages = []
                st.session_state.agent = ReactAgent(memory=st.session_state.memory)
                st.session_state.last_token_stats = None
                st.session_state.last_deep_thinking = None
                st.rerun()
        with col_save:
            if st.button("💾 Guardar"):
                st.session_state.memory.save_session()
                st.success("Guardado!")

        if st.button("🧹 Limpiar Memoria"):
            removed = st.session_state.memory.cleanup(max_entries=300)
            if removed > 0:
                st.success(f"Eliminadas {removed} entradas viejas")
            else:
                st.info("Memoria ya esta limpia")

        # ---- Model Selector ----
        st.subheader("🤖 Modelo")
        try:
            available_models = ollama._fetch_available_models() or []
        except Exception as e:
            logger.debug(f"Error obteniendo modelos disponibles: {e}")
            available_models = []

        if available_models:
            current_model = ollama.model or available_models[0] if available_models else ""
            selected_model = st.selectbox(
                "Modelo principal",
                options=available_models,
                index=available_models.index(current_model) if current_model in available_models else 0,
                key="model_selector"
            )
            if selected_model != current_model:
                ollama.model = selected_model
                st.session_state.agent._models_cache = None
                st.success(f"Modelo cambiado a: {selected_model}")

        # Info de modelos
        st.caption(f"Principal: {ollama.model or '?'}")
        st.caption(f"Chat: {ollama.chat_model or '?'}")
        st.caption(f"Code: {ollama.code_model or '?'}")
        st.caption(f"Embed: {ollama.embed_model or '?'}")

        # ---- GPU ----
        st.subheader("🖥️ GPU")
        gpu = ollama._gpu_status
        if gpu is True:
            st.success("GPU ACTIVA - Inferencia rapida")
        elif gpu is False:
            st.error("GPU NO detectada - CPU lento!")
            st.caption("Ejecuta: python check_gpu.py")
        else:
            st.warning("GPU desconocida")
            if st.button("Verificar GPU"):
                gpu = ollama.check_gpu_status()
                st.rerun()

        # ---- Token Stats ----
        token_stats = st.session_state.get("last_token_stats")
        if token_stats:
            st.subheader("📊 Tokens")
            used = token_stats.get("used", 0)
            total = token_stats.get("context_size", 0)
            pct = token_stats.get("utilization_pct", 0)
            level = "low" if pct < 60 else "medium" if pct < 85 else "high"

            st.progress(min(pct / 100, 1.0), text=f"{used:,}/{total:,} ({pct}%)")

            breakdown = token_stats.get("breakdown", {})
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.metric("Sistema", f"{breakdown.get('system', 0):,}")
                st.metric("Contexto", f"{breakdown.get('context', 0):,}")
            with col_t2:
                st.metric("Herramientas", f"{breakdown.get('tools', 0):,}")
                st.metric("Respuesta", f"{breakdown.get('response', 0):,}")

            if token_stats.get("compressions", 0) > 0:
                st.info(f"Compresiones: {token_stats['compressions']}")

        # ---- Memoria ----
        stats = st.session_state.memory.get_stats()
        st.subheader("🧠 Memoria")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Mensajes", stats.get("short_term_messages", 0))
            st.metric("Conocimiento", stats.get("long_term_entries", 0))
        with col2:
            st.metric("Correcciones", stats.get("corrections", 0))
            st.metric("Cache Embed", stats.get("embed_cache_size", 0))

        backend = stats.get("vector_backend", "?")
        backend_emoji = "🟢" if "Chroma" in backend else "🟡"
        st.caption(f"{backend_emoji} {backend}")

        # ---- Metacognicion ----
        meta = st.session_state.get("last_meta_status")
        if meta:
            st.subheader("🎯 Metacognicion")
            conf_val = meta.get("confidence", 0)
            assessment = meta.get("assessment", "N/A")

            conf_color = "green" if conf_val >= 0.7 else "orange" if conf_val >= 0.4 else "red"
            st.progress(conf_val, text=f"Confianza: {conf_val:.0%}")
            st.caption(f"Evaluacion: {assessment}")
            st.caption(f"Errores: {meta.get('errors', 0)} | Exitos: {meta.get('successes', 0)}")

        # ---- Metricas ----
        st.subheader("📈 Metricas")
        metrics = get_metrics()
        summary = metrics.get_summary()

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("LLM calls", summary["llm_calls"])
            st.metric("Tool calls", summary["tool_calls_total"])
        with col_m2:
            st.metric("LLM avg", f"{summary['llm_latency_ms']:.0f} ms")
            st.metric("Tool avg", f"{summary['tool_latency_overall_ms']:.0f} ms")

        if summary["tool_calls"]:
            with st.expander("Tool breakdown", expanded=False):
                for tname, tcount in sorted(summary["tool_calls"].items(), key=lambda x: -x[1]):
                    tlat = summary["tool_latency_ms"].get(tname, 0)
                    st.text(f"  {tname}: {tcount}x ({tlat:.0f} ms)")

        # ---- Chat Export ----
        st.subheader("💾 Exportar")
        if st.button("📤 Exportar Chat"):
            export_data = {
                "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "version": "16.2.0",
                "messages": st.session_state.messages,
                "metrics": summary,
            }
            export_json = json.dumps(export_data, ensure_ascii=False, indent=2)
            st.download_button(
                "Descargar JSON",
                data=export_json,
                file_name=f"chat_export_{time.strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

        # ---- Configuracion ----
        st.subheader("⚙️ Config")
        use_streaming = st.checkbox("Streaming", value=True, key="use_streaming")
        show_thinking = st.checkbox("Mostrar pensamiento", value=False, key="show_thinking")

        # ---- Herramientas ----
        with st.expander("🔧 Herramientas (81+)", expanded=False):
            from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
            schema_map = {}
            for s in TOOL_SCHEMAS:
                func = s.get("function", {})
                name = func.get("name", "")
                desc = func.get("description", "")
                if name:
                    schema_map[name] = desc[:60]

            for name in sorted(TOOL_FUNCTIONS.keys()):
                desc = schema_map.get(name, "")
                st.caption(f"`{name}` — {desc}")


# Ejecutar sidebar
_render_sidebar()


if __name__ == "__main__":
    main()
