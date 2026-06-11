"""
=============================================================
AGENTE LOCAL AUTONOMO v14 - Entry Point Streamlit
=============================================================
Arquitectura modular: importa los modulos que necesita.
Streaming de respuestas + metacognicion + diagnostico GPU.
Para ejecutar: streamlit run app.py
=============================================================
"""

import streamlit as st
from agent import ReactAgent
from memory.triple_memory import TripleMemory
from llm import ollama

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
        ollama.detect_models()

        # Verificar GPU al inicio
        gpu = ollama.check_gpu_status()
        if gpu is False:
            st.session_state.gpu_warning = True
        else:
            st.session_state.gpu_warning = False

init_session()

# ============================================================
# INTERFAZ STREAMLIT
# ============================================================

def main():
    st.set_page_config(
        page_title="Agente Autonomo v14",
        page_icon="🧠",
        layout="wide"
    )

    st.markdown("""
    <style>
    .stApp { max-width: 1200px; margin: 0 auto; }

    .main-title {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.2rem; font-weight: 800; text-align: center; margin-bottom: 0.3rem;
    }
    .main-subtitle {
        text-align: center; color: #888; font-size: 0.9rem; margin-bottom: 1.5rem;
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

    [data-testid="stChatMessage"] { border-radius: 12px; padding: 12px 16px; margin: 4px 0; }

    .stButton > button { border-radius: 8px; transition: all 0.2s; }
    .stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(100, 100, 255, 0.3); }

    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.1); border-radius: 3px; }
    ::-webkit-scrollbar-thumb { background: rgba(100, 100, 255, 0.3); border-radius: 3px; }
    </style>
    """, unsafe_allow_html=True)

    # Titulo
    st.markdown('<h1 class="main-title">Agente Autonomo v14</h1>', unsafe_allow_html=True)

    # Info del modelo + GPU
    model_info = f"Modelo: {ollama.model or 'detectando...'}"
    if ollama.chat_model and ollama.chat_model != ollama.model:
        model_info += f" | Chat: {ollama.chat_model}"
    if ollama.code_model and ollama.code_model != ollama.model:
        model_info += f" | Code: {ollama.code_model}"

    # Indicador GPU
    gpu_status = ollama._gpu_status
    if gpu_status is True:
        model_info += " | GPU: ACTIVA"
    elif gpu_status is False:
        model_info += " | GPU: NO DETECTADA (CPU lento)"
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

    # Chat
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            # Mostrar tools ejecutadas si las hay
            if "tools_used" in msg and msg["tools_used"]:
                tools_html = " ".join([f'<span class="tool-badge">{t}</span>' for t in msg["tools_used"]])
                st.markdown(f"<div>{tools_html}</div>", unsafe_allow_html=True)
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

        try:
            for event in st.session_state.agent.run_stream(prompt):
                if event["type"] == "text":
                    full_response += event["data"]
                    response_placeholder.markdown(full_response + "▌")
                elif event["type"] == "tool_start":
                    tc = event["data"]
                    tool_name = tc.get("name", "?")
                    tools_used.append(tool_name)
                    with thinking_placeholder:
                        st.caption(f"🔧 Ejecutando: {tool_name}...")
                elif event["type"] == "tool_result":
                    result = event["data"]
                    tool_name = result["tool"].get("name", "?")
                    result_text = result["result"][:100]
                    # Verificar si es un comando peligroso bloqueado
                    if "PELIGROSO" in result_text:
                        st.session_state.pending_dangerous_cmd = {
                            "tool": result["tool"],
                            "result": result["result"],
                            "original_prompt": prompt,
                            "tools_used": tools_used,
                        }
                        with thinking_placeholder:
                            st.warning(f"⚠️ Comando peligroso detectado: {tool_name}")
                elif event["type"] == "meta":
                    # Evento de metacognicion
                    meta_data = event["data"]
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
                elif event["type"] == "done":
                    full_response = event["data"]
                    thinking_log = event.get("thinking_log", [])
                    meta_status = event.get("meta_status")
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
                        ("SUCCESS", "success"),
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
                            "excelente": "🟢",
                            "bueno": "🟢",
                            "aceptable": "🟡",
                            "problematico": "🔴",
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

        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "tools_used": tools_used,
            "meta_status": meta_status,
        })
        st.session_state.last_meta_status = meta_status


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
            # Re-ejecutar con confirmacion
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
    """Renderiza el sidebar con stats y controles."""
    with st.sidebar:
        st.header("Estado del Agente")

        if st.button("Nueva Sesion"):
            st.session_state.memory.clear_session()
            st.session_state.messages = []
            st.session_state.agent = ReactAgent(memory=st.session_state.memory)
            st.rerun()

        col_save, col_clean = st.columns(2)
        with col_save:
            if st.button("Guardar"):
                st.session_state.memory.save_session()
                st.success("Guardado!")
        with col_clean:
            if st.button("Limpiar Memoria"):
                removed = st.session_state.memory.cleanup(max_entries=300)
                if removed > 0:
                    st.success(f"Eliminadas {removed} entradas viejas")
                else:
                    st.info("Memoria ya esta limpia")

        # Stats de memoria
        stats = st.session_state.memory.get_stats()
        st.subheader("Estadisticas")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Mensajes", stats.get("short_term_messages", 0))
            st.metric("Conocimiento", stats.get("long_term_entries", 0))
        with col2:
            st.metric("Correcciones", stats.get("corrections", 0))
            st.metric("Cache Embed", stats.get("embed_cache_size", 0))

        # Backend info
        backend = stats.get("vector_backend", "?")
        with_vectors = stats.get("long_term_with_vectors", "?")
        backend_emoji = "🟢" if "Chroma" in backend else "🟡"
        st.caption(f"{backend_emoji} Backend: {backend} | Con vectores: {with_vectors}")

        # Ultima sesion
        last_age = stats.get("last_session_age_hours")
        if last_age is not None:
            if last_age < 1:
                st.caption(f"Ultima sesion: hace {last_age*60:.0f} min")
            else:
                st.caption(f"Ultima sesion: hace {last_age:.1f} horas")

        # Modelo activo
        st.subheader("Modelo")
        st.text(f"Principal: {ollama.model or '?'}")
        st.text(f"Chat: {ollama.chat_model or '?'}")
        st.text(f"Code: {ollama.code_model or '?'}")
        st.text(f"Embed: {ollama.embed_model or '?'}")

        # Estado GPU
        st.subheader("GPU")
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

        # Estado metacognitivo de la ultima consulta
        meta = st.session_state.get("last_meta_status")
        if meta:
            st.subheader("Metacognicion")
            conf_val = meta.get("confidence", 0)
            assessment = meta.get("assessment", "N/A")

            # Barra de confianza
            conf_color = "green" if conf_val >= 0.7 else "orange" if conf_val >= 0.4 else "red"
            st.progress(conf_val, text=f"Confianza: {conf_val:.0%}")
            st.text(f"Evaluacion: {assessment}")
            st.text(f"Errores: {meta.get('errors', 0)} | Exitos: {meta.get('successes', 0)}")
            st.text(f"Cambios de plan: {meta.get('plan_changes', 0)}")

        # Configuracion
        st.subheader("Configuracion")
        use_streaming = st.checkbox("Streaming", value=True, key="use_streaming")
        show_thinking = st.checkbox("Mostrar pensamiento", value=False, key="show_thinking")


# Ejecutar sidebar
_render_sidebar()


if __name__ == "__main__":
    main()
