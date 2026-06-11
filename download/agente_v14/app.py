"""
=============================================================
AGENTE LOCAL AUTONOMO v14 - Entry Point Streamlit
=============================================================
Arquitectura modular: importa los modulos que necesita.
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
        ollama.detect_models()

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

    # Info del modelo
    model_info = f"Modelo: {ollama.model or 'detectando...'}"
    if ollama.chat_model and ollama.chat_model != ollama.model:
        model_info += f" | Chat: {ollama.chat_model}"
    if ollama.code_model and ollama.code_model != ollama.model:
        model_info += f" | Code: {ollama.code_model}"
    st.markdown(f'<p class="main-subtitle">{model_info}</p>', unsafe_allow_html=True)

    # Chat
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input
    if prompt := st.chat_input("Que necesitas?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                respuesta, thinking_log = st.session_state.agent.run(prompt)

            st.markdown(respuesta)
            st.session_state.messages.append({"role": "assistant", "content": respuesta})

            # Mostrar thinking log en expander
            if thinking_log:
                with st.expander("Proceso de pensamiento", expanded=False):
                    log_text = "\n".join(thinking_log)
                    # Colorear por categoria
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

    # Sidebar con stats
    with st.sidebar:
        st.header("Estado del Agente")
        if st.button("Nueva Sesion"):
            st.session_state.memory.clear_session()
            st.session_state.messages = []
            st.session_state.agent = ReactAgent(memory=st.session_state.memory)
            st.rerun()

        if st.button("Guardar Sesion"):
            st.session_state.memory.save_session()
            st.success("Sesion guardada!")

        stats = st.session_state.memory.get_stats()
        st.json(stats)


if __name__ == "__main__":
    main()
