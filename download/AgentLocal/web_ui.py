# web_ui.py - Interfaz Web del Agente Inteligente Local
# Muestra DOS paneles en pantalla:
#   IZQUIERDA: Proceso de pensamiento del agente (como yo lo hago)
#   DERECHA:   Terminal que muestra todo lo que ejecuta
#
# Requiere: pip install gradio
# Ejecutar: python web_ui.py
import sys
import os
import json
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from agent import AgenteInteligente, PasoPensamiento


# ── Agente global con callback para capturar pasos ──────────
agent = AgenteInteligente()
pasos_pendientes = []  # Pasos acumulados para la UI
lock = threading.Lock()


def on_paso_ui(paso: PasoPensamiento):
    """Callback que acumula pasos para la UI web."""
    with lock:
        pasos_pendientes.append({
            "tipo": paso.tipo,
            "contenido": paso.contenido,
            "timestamp": paso.timestamp,
            "datos": paso.datos,
        })


agent.on_paso = on_paso_ui


def formatear_paso_pensamiento(paso):
    """Formatea un paso para el panel de pensamiento (izquierda)."""
    tipo = paso["tipo"]
    contenido = paso["contenido"]
    timestamp = paso["timestamp"]

    iconos = {
        "pensamiento": "💭",
        "accion": "🔧",
        "observacion": "👁",
        "respuesta": "✅",
        "error": "❌",
    }
    icono = iconos.get(tipo, "📌")

    if tipo == "pensamiento":
        return f"### {icono} Pensamiento [{timestamp}]\n{contenido}\n\n---\n"
    elif tipo == "respuesta":
        return f"### {icono} Respuesta Final [{timestamp}]\n\n{contenido}\n\n---\n"
    elif tipo == "error":
        return f"### {icono} Error [{timestamp}]\n**{contenido}**\n\n---\n"
    else:
        return f"### {icono} {tipo.title()} [{timestamp}]\n{contenido[:300]}\n\n---\n"


def formatear_paso_terminal(paso):
    """Formatea un paso para el panel de terminal (derecha)."""
    tipo = paso["tipo"]
    datos = paso.get("datos", {})
    timestamp = paso["timestamp"]

    if tipo == "accion":
        tool = datos.get("tool", "?")
        params = datos.get("params", {})
        params_str = json.dumps(params, ensure_ascii=False, indent=2)
        return (
            f"```\n[{timestamp}] $ {tool}\n"
            f"Parámetros:\n{params_str}\n```\n\n"
        )
    elif tipo == "observacion":
        resultado = datos.get("resultado", {})
        exito = resultado.get("exito", False) if resultado else False
        estado = "✅ EXITOSO" if exito else "❌ FALLIDO"
        result_str = json.dumps(resultado, ensure_ascii=False, indent=2)[:800]
        return (
            f"```\n[{timestamp}] Resultado: {estado}\n"
            f"{result_str}\n```\n\n"
        )
    elif tipo == "error":
        return f"```\n[{timestamp}] ERROR: {paso['contenido']}\n```\n\n"
    else:
        return ""


def chat(message, history):
    """Función principal del chat para Gradio."""
    global pasos_pendientes
    with lock:
        pasos_pendientes = []

    # Ejecutar el agente en un hilo para poder actualizar la UI
    resultado = agent.think(message)

    # Construir outputs para los paneles
    pensamiento_text = ""
    terminal_text = ""

    with lock:
        for paso in pasos_pendientes:
            pensamiento_text += formatear_paso_pensamiento(paso)
            terminal_text += formatear_paso_terminal(paso)

    # Si no hay terminal output, mostrar algo
    if not terminal_text.strip():
        terminal_text = "```\nNo se ejecutaron herramientas.\n```"

    # Stats
    stats = agent.obtener_estadisticas()
    stats_text = (
        f"📊 **Conocimientos:** {stats['total_conocimientos']} | "
        f"**Soluciones:** {stats['total_soluciones']} | "
        f"**Exitosas:** {stats['soluciones_exitosas']}"
    )

    return resultado["respuesta"], pensamiento_text, terminal_text, stats_text


# ── Crear Interfaz Gradio ──────────────────────────────────
def crear_ui():
    """Crea la interfaz web con Gradio."""
    try:
        import gradio as gr
    except ImportError:
        print("❌ Necesitas instalar gradio: pip install gradio")
        print("   Luego ejecuta: python web_ui.py")
        return

    with gr.Blocks(
        title="🧠 Agente Inteligente Local",
        theme=gr.themes.Soft(),
        css="""
        .pensamiento-panel {
            background: #1a1b26;
            color: #a9b1d6;
            font-family: 'JetBrains Mono', monospace;
            padding: 16px;
            border-radius: 8px;
            height: 500px;
            overflow-y: auto;
        }
        .terminal-panel {
            background: #0d1117;
            color: #58a6ff;
            font-family: 'JetBrains Mono', monospace;
            padding: 16px;
            border-radius: 8px;
            height: 500px;
            overflow-y: auto;
        }
        """,
    ) as demo:

        # ── Header ──────────────────────────────────────
        gr.Markdown(
            "# 🧠 Agente Inteligente Local\n"
            f"**Modelo:** {Config.MODEL_NAME} | "
            f"**Iteraciones máx:** {Config.MAX_ITERATIONS} | "
            f"**Memoria:** {'✅ Activada' if Config.MEMORY_ENABLED else '❌ Desactivada'}"
        )

        # ── Chat input ─────────────────────────────────
        with gr.Row():
            msg_input = gr.Textbox(
                label="🧑 Tu pregunta",
                placeholder="Escribe tu pregunta aquí... El agente pensará paso a paso.",
                scale=4,
            )
            btn_enviar = gr.Button("🚀 Preguntar", variant="primary", scale=1)

        # ── Respuesta ──────────────────────────────────
        respuesta_output = gr.Markdown(
            label="✅ Respuesta",
            value="",
        )

        # ── Paneles: Pensamiento + Terminal ─────────────
        gr.Markdown("### 📊 Proceso Interno del Agente")

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("#### 💭 Proceso de Pensamiento")
                pensamiento_output = gr.Markdown(
                    value="*El proceso de pensamiento aparecerá aquí...*",
                    elem_classes=["pensamiento-panel"],
                )

            with gr.Column(scale=1):
                gr.Markdown("#### 💻 Terminal de Ejecución")
                terminal_output = gr.Markdown(
                    value="*Las ejecuciones de herramientas aparecerán aquí...*",
                    elem_classes=["terminal-panel"],
                )

        # ── Stats ──────────────────────────────────────
        stats_output = gr.Markdown("📊 **Conocimientos:** 0 | **Soluciones:** 0")

        # ── Conectar eventos ────────────────────────────
        btn_enviar.click(
            fn=chat,
            inputs=[msg_input],
            outputs=[respuesta_output, pensamiento_output, terminal_output, stats_output],
        )
        msg_input.submit(
            fn=chat,
            inputs=[msg_input],
            outputs=[respuesta_output, pensamiento_output, terminal_output, stats_output],
        )

    # ── Lanzar ─────────────────────────────────────────
    print("\n🚀 Iniciando interfaz web...")
    print(f"   Modelo: {Config.MODEL_NAME}")
    print(f"   URL: http://localhost:7860")
    print()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
    )


if __name__ == "__main__":
    crear_ui()
