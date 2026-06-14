"""
=============================================================
AGENTE LOCAL v16 - Interfaz CLI Interactiva
=============================================================
Terminal con streaming en colores, tool badges, deep thinking,
comandos de control y historial persistente.

Ejecutar: python cli.py
Requiere: rich, prompt_toolkit
=============================================================
"""

import os
import sys
import json
import time
import signal
import logging

# Agregar directorio al path
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule
from rich.syntax import Syntax
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style as PTStyle

console = Console()
pt_style = PTStyle.from_dict({
    'prompt': 'bold cyan',
})

# Ctrl+C graceful
_interrupted = False
def _signal_handler(sig, frame):
    global _interrupted
    _interrupted = True
    console.print("\n[yellow]Interrumpido. Escribe 'salir' para terminar.[/yellow]")
signal.signal(signal.SIGINT, _signal_handler)


# ============================================================
# INICIALIZACION DEL AGENTE
# ============================================================

def init_agent():
    """Inicializa el agente con memoria persistente."""
    from memory.triple_memory import TripleMemory
    from agent import ReactAgent
    from llm import ollama

    console.print("[bold blue]Inicializando agente...[/bold blue]")

    memory = TripleMemory()
    memory.load_session()
    agent = ReactAgent(memory=memory)

    ollama.detect_models()
    model = ollama.model or "desconocido"
    chat_model = ollama.chat_model or ""
    gpu = ollama._gpu_status

    console.print(Panel(
        f"[bold green]Agente Local v16.1[/bold green]\n"
        f"Modelo: [cyan]{model}[/cyan]"
        + (f" | Chat: [cyan]{chat_model}[/cyan]" if chat_model and chat_model != model else "")
        + f"\nGPU: {'[green]ACTIVA[/green]' if gpu is True else '[red]NO DETECTADA[/red]' if gpu is False else '[yellow]Desconocida[/yellow]'}"
        + f"\nMemoria: [cyan]{memory.get_stats().get('long_term_entries', 0)}[/cyan] entradas"
        + f"\nHerramientas: [cyan]{len(TOOL_FUNCTIONS)}[/cyan] disponibles",
        title="Agente Autonomo",
        border_style="blue"
    ))

    return agent, memory


# ============================================================
# COMANDOS ESPECIALES
# ============================================================

def handle_command(cmd: str, agent, memory) -> bool:
    """Maneja comandos especiales del CLI. Retorna True si debe salir."""
    cmd = cmd.strip().lower()

    if cmd in ("/salir", "/exit", "/quit", "salir", "exit"):
        memory.save_session()
        console.print("[green]Sesion guardada. Hasta luego![/green]")
        return True

    elif cmd in ("/nueva", "/new", "/reset"):
        memory.clear_session()
        from agent import ReactAgent
        agent = ReactAgent(memory=memory)
        console.print("[green]Nueva sesion iniciada.[/green]")
        return False

    elif cmd in ("/guardar", "/save"):
        memory.save_session()
        console.print("[green]Sesion guardada.[/green]")
        return False

    elif cmd in ("/herramientas", "/tools", "/tools"):
        _show_tools()
        return False

    elif cmd in ("/memoria", "/memory"):
        _show_memory(memory)
        return False

    elif cmd in ("/tokens", "/token"):
        _show_tokens(agent)
        return False

    elif cmd in ("/modelo", "/model"):
        _show_model()
        return False

    elif cmd in ("/config", "/cfg"):
        _show_config()
        return False

    elif cmd in ("/stats", "/metricas"):
        _show_stats(agent)
        return False

    elif cmd in ("/ayuda", "/help", "/?"):
        _show_help()
        return False

    elif cmd.startswith("/exportar ") or cmd.startswith("/export "):
        path = cmd.split(" ", 1)[1] if " " in cmd else "chat_export.json"
        _export_chat(path)
        return False

    elif cmd.startswith("/modelo "):
        model_name = cmd.split(" ", 1)[1].strip()
        _switch_model(model_name)
        return False

    return None  # No es un comando especial


def _show_tools():
    """Muestra las herramientas disponibles."""
    from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
    table = Table(title="Herramientas Disponibles", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Nombre", style="cyan")
    table.add_column("Descripcion", style="white", max_width=60)

    schema_map = {}
    for s in TOOL_SCHEMAS:
        func = s.get("function", {})
        name = func.get("name", "")
        desc = func.get("description", "")
        if name:
            schema_map[name] = desc

    for i, name in enumerate(sorted(TOOL_FUNCTIONS.keys()), 1):
        desc = schema_map.get(name, "")[:80]
        table.add_row(str(i), name, desc)

    console.print(table)


def _show_memory(memory):
    """Muestra estadisticas de memoria."""
    stats = memory.get_stats()
    table = Table(title="Estado de Memoria")
    table.add_column("Metrica", style="cyan")
    table.add_column("Valor", style="green")

    table.add_row("Mensajes corto plazo", str(stats.get("short_term_messages", 0)))
    table.add_row("Entradas largo plazo", str(stats.get("long_term_entries", 0)))
    table.add_row("Correcciones", str(stats.get("corrections", 0)))
    table.add_row("Cache Embed", str(stats.get("embed_cache_size", 0)))
    table.add_row("Backend", str(stats.get("vector_backend", "?")))

    console.print(table)


def _show_tokens(agent):
    """Muestra estadisticas de tokens."""
    if hasattr(agent, 'token_manager'):
        stats = agent.token_manager.stats()
        table = Table(title="Gestion de Tokens")
        table.add_column("Metrica", style="cyan")
        table.add_column("Valor", style="green")

        table.add_row("Tamano contexto", f"{stats['context_size']:,}")
        table.add_row("Tokens usados", f"{stats['used']:,}")
        table.add_row("Disponibles", f"{stats['remaining']:,}")
        table.add_row("Utilizacion", f"{stats['utilization_pct']}%")
        table.add_row("Sistema", f"{stats['breakdown']['system']:,}")
        table.add_row("Contexto", f"{stats['breakdown']['context']:,}")
        table.add_row("Herramientas", f"{stats['breakdown']['tools']:,}")
        table.add_row("Compresiones", str(stats['compressions']))

        if stats['needs_compression']:
            table.add_row("[yellow]Compresion[/yellow]", f"[yellow]{stats['compression_level']}[/yellow]")

        console.print(table)
    else:
        console.print("[yellow]TokenManager no disponible[/yellow]")


def _show_model():
    """Muestra informacion del modelo actual."""
    from llm import ollama
    table = Table(title="Modelo Actual")
    table.add_column("Parametro", style="cyan")
    table.add_column("Valor", style="green")

    table.add_row("Principal", ollama.model or "?")
    table.add_row("Chat", ollama.chat_model or "?")
    table.add_row("Code", ollama.code_model or "?")
    table.add_row("Embed", ollama.embed_model or "?")
    table.add_row("GPU", "ACTIVA" if ollama._gpu_status is True else "NO DETECTADA")

    console.print(table)


def _show_config():
    """Muestra la configuracion actual."""
    import config as cfg
    table = Table(title="Configuracion")
    table.add_column("Parametro", style="cyan")
    table.add_column("Valor", style="green")

    configs = [
        ("Deep Thinking", cfg.DEEP_THINKING_MODE),
        ("Max Iteraciones ReAct", str(cfg.MAX_REACT_ITERATIONS)),
        ("Max Memoria Conversacion", str(cfg.MAX_CONVERSATION_MEMORY)),
        ("Streaming", str(cfg.USE_STREAMING)),
        ("Busqueda Hibrida", str(cfg.USE_HYBRID_SEARCH)),
        ("Reranker", str(cfg.USE_RERANKER)),
        ("Max Tool Output", f"{cfg.MAX_TOOL_OUTPUT} chars"),
        ("Sub-agentes Paralelos", str(cfg.SUBAGENT_MAX_PARALLEL)),
        ("TTS Voice", cfg.TTS_DEFAULT_VOICE),
    ]
    for k, v in configs:
        table.add_row(k, v)

    console.print(table)


def _show_stats(agent):
    """Muestra metricas de rendimiento."""
    from utils.metrics import get_metrics
    metrics = get_metrics()
    summary = metrics.get_summary()

    table = Table(title="Metricas de Rendimiento")
    table.add_column("Metrica", style="cyan")
    table.add_column("Valor", style="green")

    table.add_row("LLM Calls", str(summary["llm_calls"]))
    table.add_row("LLM Latencia Promedio", f"{summary['llm_latency_ms']:.0f} ms")
    table.add_row("Tool Calls Total", str(summary["tool_calls_total"]))
    table.add_row("Tool Latencia Promedio", f"{summary['tool_latency_overall_ms']:.0f} ms")
    table.add_row("Embeddings Generados", str(summary["embeddings_generated"]))
    table.add_row("Errores Total", str(summary["errors_total"]))

    if summary["tool_calls"]:
        console.print(table)
        table2 = Table(title="Desglose por Herramienta")
        table2.add_column("Herramienta", style="cyan")
        table2.add_column("Llamadas", style="green")
        table2.add_column("Latencia Prom.", style="yellow")
        for tname, tcount in sorted(summary["tool_calls"].items(), key=lambda x: -x[1]):
            tlat = summary["tool_latency_ms"].get(tname, 0)
            table2.add_row(tname, str(tcount), f"{tlat:.0f} ms")
        console.print(table2)
    else:
        console.print(table)


def _show_help():
    """Muestra la ayuda."""
    help_text = """
[bold cyan]Comandos del CLI:[/bold cyan]

  [green]/ayuda[/green]        - Mostrar esta ayuda
  [green]/herramientas[/green] - Listar todas las herramientas (81+)
  [green]/memoria[/green]      - Estado de la memoria
  [green]/tokens[/green]       - Gestion de tokens y contexto
  [green]/modelo[/green]       - Info del modelo actual
  [green]/modelo NOMBRE[/green]- Cambiar modelo activo
  [green]/config[/green]       - Ver configuracion
  [green]/stats[/green]        - Metricas de rendimiento
  [green]/guardar[/green]      - Guardar sesion
  [green]/nueva[/green]        - Nueva sesion (limpia memoria)
  [green]/exportar PATH[/green]- Exportar historial a JSON
  [green]/salir[/green]        - Guardar y salir

[bold cyan]Tips:[/bold cyan]
  - Ctrl+C interrumpe la respuesta actual
  - Las respuestas se muestran con Markdown renderizado
  - Las herramientas ejecutadas se muestran como badges
  - El proceso de pensamiento se muestra en paneles colapsables
"""
    console.print(Panel(help_text, title="Ayuda", border_style="cyan"))


def _export_chat(path: str):
    """Exporta el historial a JSON."""
    try:
        from utils.metrics import get_metrics
        metrics = get_metrics()
        data = {
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "version": "16.1.0",
            "metrics": metrics.get_summary(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        console.print(f"[green]Exportado a: {path}[/green]")
    except Exception as e:
        console.print(f"[red]Error exportando: {e}[/red]")


def _switch_model(model_name: str):
    """Cambia el modelo activo."""
    from llm import ollama
    try:
        ollama.model = model_name
        console.print(f"[green]Modelo cambiado a: {model_name}[/green]")
    except Exception as e:
        console.print(f"[red]Error cambiando modelo: {e}[/red]")


# ============================================================
# STREAMING DE RESPUESTAS
# ============================================================

def stream_response(agent, prompt: str):
    """Ejecuta el agente con streaming y renderizado en tiempo real."""
    global _interrupted
    _interrupted = False

    full_response = ""
    tools_used = []
    thinking_data = None
    meta_status = None
    token_stats = None
    start_time = time.time()

    try:
        for event in agent.run_stream(prompt):
            if _interrupted:
                console.print("\n[yellow]Respuesta interrumpida.[/yellow]")
                break

            event_type = event.get("type", "")

            if event_type == "text":
                # Acumular texto (no imprimir token a token para evitar flicker)
                full_response += event.get("data", "")

            elif event_type == "thinking":
                # Deep thinking
                thinking_data = event.get("data", {})
                depth = thinking_data.get("depth", 0)
                depth_labels = {0: "ninguno", 1: "rapido", 2: "completo", 3: "profundo"}
                complexity = thinking_data.get("complexity", 0)
                plan = thinking_data.get("plan", [])

                thinking_panel = Panel(
                    f"[dim]Complejidad: {complexity:.2f} | Profundidad: {depth_labels.get(depth, '?')}[/dim]\n"
                    + (f"\nPlan:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan[:5])) if plan else "")
                    + (f"\n\n[dim]{thinking_data.get('reasoning', '')[:300]}[/dim]" if thinking_data.get('reasoning') else ""),
                    title="[bold blue]Pensamiento Profundo[/bold blue]",
                    border_style="blue",
                    expand=False
                )
                console.print(thinking_panel)

            elif event_type == "tool_start":
                tool_info = event.get("data", {})
                tool_name = tool_info.get("name", "?") if isinstance(tool_info, dict) else str(tool_info)
                tools_used.append(tool_name)
                console.print(f"  [dim yellow]▸ Ejecutando: [bold]{tool_name}[/bold]...[/dim yellow]")

            elif event_type == "tool_result":
                result_data = event.get("data", {})
                tool_name = "?"
                result_text = ""
                if isinstance(result_data, dict):
                    tool_info = result_data.get("tool", {})
                    tool_name = tool_info.get("name", "?") if isinstance(tool_info, dict) else "?"
                    result_text = str(result_data.get("result", ""))[:150]

                is_error = "ERROR" in result_text
                icon = "[red]✗[/red]" if is_error else "[green]✓[/green]"
                console.print(f"  {icon} [dim]{tool_name}: {result_text}[/dim]")

            elif event_type == "meta":
                meta_data = event.get("data", {})
                conf = meta_data.get("confidence", 0)
                if conf < 0.4:
                    console.print(f"  [yellow]Meta: Confianza baja ({conf:.0%}) - Ajustando estrategia[/yellow]")

            elif event_type == "done":
                full_response = event.get("data", full_response)
                meta_status = event.get("meta_status")
                token_stats = event.get("token_stats")

    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        # Fallback a modo no-streaming
        try:
            full_response, _ = agent.run(prompt)
        except Exception as e2:
            full_response = f"Error: {e2}"

    # Renderizar respuesta final con Markdown
    elapsed = time.time() - start_time

    console.print()  # Separador
    console.print(Rule(style="dim"))

    if full_response:
        # Intentar renderizar como Markdown
        try:
            console.print(Markdown(full_response))
        except Exception:
            console.print(full_response)

    # Badge de herramientas
    if tools_used:
        badges = " ".join(f"[blue on dark_blue] {t} [/blue on dark_blue]" for t in tools_used)
        console.print(f"\n{badges}")

    # Stats rápidos
    stats_parts = [f"{elapsed:.1f}s"]
    if tools_used:
        stats_parts.append(f"{len(tools_used)} tools")
    if token_stats:
        used = token_stats.get("used", 0)
        total = token_stats.get("context_size", 0)
        pct = token_stats.get("utilization_pct", 0)
        stats_parts.append(f"tokens: {used:,}/{total:,} ({pct}%)")
    if meta_status:
        conf = meta_status.get("confidence", 0)
        stats_parts.append(f"conf: {conf:.0%}")

    console.print(f"[dim]{' | '.join(stats_parts)}[/dim]")
    console.print(Rule(style="dim"))


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    """Loop principal del CLI."""
    # Banner
    console.print(Rule("[bold blue]Agente Local Autonomo v16.1[/bold blue]", style="blue"))
    console.print("[dim]Escribe /ayuda para ver los comandos disponibles[/dim]\n")

    # Inicializar agente
    try:
        agent, memory = init_agent()
    except Exception as e:
        console.print(f"[red]Error inicializando agente: {e}[/red]")
        console.print("[yellow]Asegurate de que Ollama este corriendo: ollama serve[/yellow]")
        sys.exit(1)

    # Historial persistente
    history_file = os.path.join(os.path.expanduser("~"), ".ia-local", "cli_history")
    os.makedirs(os.path.dirname(history_file), exist_ok=True)

    session = PromptSession(
        history=FileHistory(history_file),
        auto_suggest=AutoSuggestFromHistory(),
        style=pt_style,
    )

    from tools import TOOL_FUNCTIONS

    # Loop principal
    while True:
        try:
            prompt = session.prompt(
                [("class:prompt", ">>> ")],
            )

            if not prompt or not prompt.strip():
                continue

            # Verificar comandos especiales
            result = handle_command(prompt, agent, memory)
            if result is True:
                break  # Salir
            elif result is False:
                continue  # Comando manejado

            # Ejecutar agente con streaming
            stream_response(agent, prompt)

        except KeyboardInterrupt:
            console.print("\n[yellow]Presiona Ctrl+C de nuevo o escribe 'salir'[/yellow]")
            try:
                prompt = session.prompt([("class:prompt", ">>> ")])
                if prompt.strip().lower() in ("salir", "exit", "quit"):
                    memory.save_session()
                    console.print("[green]Hasta luego![/green]")
                    break
            except KeyboardInterrupt:
                memory.save_session()
                console.print("\n[green]Hasta luego![/green]")
                break

        except EOFError:
            memory.save_session()
            console.print("\n[green]Hasta luego![/green]")
            break

        except Exception as e:
            console.print(f"[red]Error inesperado: {e}[/red]")


if __name__ == "__main__":
    main()
