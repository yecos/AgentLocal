# main.py - Interfaz Terminal del Agente Inteligente Local
# Muestra EN PANTALLA el proceso de pensamiento y la terminal de ejecución
# usando la librería 'rich' para una experiencia visual profesional.
import sys
import os
import time

# Agregar directorio del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from agent import AgenteInteligente, PasoPensamiento

# Intentar usar rich para interfaz bonita
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.table import Table
    from rich.text import Text
    from rich.live import Live
    from rich.layout import Layout
    from rich.markdown import Markdown
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def crear_interfaz_rich():
    """Crea la interfaz con Rich (paneles de pensamiento + terminal)."""
    console = Console()

    def on_paso(paso: PasoPensamiento):
        """Callback que se ejecuta cada vez que el agente da un paso."""
        iconos = {
            "pensamiento": "💭",
            "accion": "🔧",
            "observacion": "👁",
            "respuesta": "✅",
            "error": "❌",
        }
        colores = {
            "pensamiento": "cyan",
            "accion": "yellow",
            "observacion": "green",
            "respuesta": "bold green",
            "error": "bold red",
        }

        icono = iconos.get(paso.tipo, "📌")
        color = colores.get(paso.tipo, "white")

        # Panel de pensamiento (izquierda)
        if paso.tipo == "pensamiento":
            console.print(
                Panel(
                    f"[{color}]{paso.contenido}[/{color}]",
                    title=f"[bold]{icono} PENSAMIENTO[/bold] [{paso.timestamp}]",
                    border_style="cyan",
                    padding=(0, 2),
                )
            )
        elif paso.tipo == "accion":
            # Terminal de ejecución (derecha) — muestra qué se ejecuta
            tool = paso.datos.get("tool", "")
            params = paso.datos.get("params", {})
            console.print(
                Panel(
                    f"[bold yellow]$ {tool}[/bold yellow]({json_dumps(params)})\n",
                    title=f"[bold]{icono} TERMINAL — EJECUTANDO[/bold] [{paso.timestamp}]",
                    border_style="yellow",
                    padding=(0, 2),
                )
            )
        elif paso.tipo == "observacion":
            resultado = paso.datos.get("resultado", {})
            exito = resultado.get("exito", False) if resultado else False
            estado = "[green]EXITOSO[/green]" if exito else "[red]FALLIDO[/red]"
            contenido_truncado = paso.contenido[:300]
            console.print(
                Panel(
                    f"[{color}]{contenido_truncado}[/{color}]\n"
                    f"Estado: {estado}",
                    title=f"[bold]{icono} OBSERVACIÓN[/bold] [{paso.timestamp}]",
                    border_style="green",
                    padding=(0, 2),
                )
            )
        elif paso.tipo == "respuesta":
            console.print()
            console.print(
                Panel(
                    Markdown(paso.contenido),
                    title="[bold green]✅ RESPUESTA FINAL[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            )
        elif paso.tipo == "error":
            console.print(
                Panel(
                    f"[bold red]{paso.contenido}[/bold red]",
                    title=f"[bold]{icono} ERROR[/bold]",
                    border_style="red",
                    padding=(0, 2),
                )
            )

    return console, on_paso


def crear_interfaz_simple():
    """Interfaz simple sin Rich (funciona en cualquier terminal)."""

    def on_paso(paso: PasoPensamiento):
        iconos = {
            "pensamiento": "💭",
            "accion": "🔧",
            "observacion": "👁",
            "respuesta": "✅",
            "error": "❌",
        }
        icono = iconos.get(paso.tipo, "📌")

        if paso.tipo == "accion":
            tool = paso.datos.get("tool", "")
            params = paso.datos.get("params", {})
            print(f"  {icono} [{paso.timestamp}] TERMINAL > {tool}({json_dumps(params)})")
        elif paso.tipo == "respuesta":
            print(f"\n  {icono} RESPUESTA FINAL:\n")
            print(f"  {paso.contenido}\n")
        else:
            print(f"  {icono} [{paso.timestamp}] {paso.tipo.upper()}: {paso.contenido[:200]}")

    return None, on_paso


def json_dumps(obj):
    """JSON dumps seguro para impresión."""
    import json
    return json.dumps(obj, ensure_ascii=False)


def main():
    # ── Banner de inicio ────────────────────────────────────
    if RICH_AVAILABLE:
        console, on_paso = crear_interfaz_rich()
        console.print(Panel(
            "[bold cyan]🧠 Agente Inteligente Local[/bold cyan]\n"
            f"[dim]Modelo: {Config.MODEL_NAME} | "
            f"Memoria: {'✅' if Config.MEMORY_ENABLED else '❌'} | "
            f"Iteraciones máx: {Config.MAX_ITERATIONS}[/dim]",
            border_style="cyan",
            padding=(1, 2),
        ))
    else:
        _, on_paso = crear_interfaz_simple()
        print("=" * 60)
        print("🧠 Agente Inteligente Local")
        print(f"   Modelo: {Config.MODEL_NAME}")
        print(f"   Memoria: {'✅' if Config.MEMORY_ENABLED else '❌'}")
        print(f"   Iteraciones máx: {Config.MAX_ITERATIONS}")
        print("=" * 60)
        print()
        print("💡 Escribe tu pregunta y el agente pensará paso a paso.")
        print("   Comandos: 'salir', 'stats', 'historial'")
        print()

    # ── Crear agente ────────────────────────────────────────
    agent = AgenteInteligente()
    agent.on_paso = on_paso

    # ── Loop principal ──────────────────────────────────────
    while True:
        try:
            if RICH_AVAILABLE:
                pregunta = console.input("[bold cyan]🧑 Tú:[/bold cyan] ")
            else:
                pregunta = input("🧑 Tú: ")
        except (EOFError, KeyboardInterrupt):
            break

        pregunta = pregunta.strip()
        if not pregunta:
            continue

        # Comandos especiales
        if pregunta.lower() in ("salir", "exit", "quit", "q"):
            stats = agent.obtener_estadisticas()
            if RICH_AVAILABLE:
                console.print(f"\n📊 Conocimientos guardados: {stats['total_conocimientos']}")
                console.print("👋 ¡Hasta luego!")
            else:
                print(f"\n📊 Conocimientos guardados: {stats['total_conocimientos']}")
                print("👋 ¡Hasta luego!")
            break

        if pregunta.lower() == "stats":
            stats = agent.obtener_estadisticas()
            if RICH_AVAILABLE:
                table = Table(title="📊 Estadísticas del Agente")
                table.add_column("Métrica", style="cyan")
                table.add_column("Valor", style="green")
                table.add_row("Conocimientos", str(stats["total_conocimientos"]))
                table.add_row("Soluciones registradas", str(stats["total_soluciones"]))
                table.add_row("Soluciones exitosas", str(stats["soluciones_exitosas"]))
                console.print(table)
            else:
                print(f"  Conocimientos: {stats['total_conocimientos']}")
                print(f"  Soluciones: {stats['total_soluciones']}")
                print(f"  Exitosas: {stats['soluciones_exitosas']}")
            continue

        if pregunta.lower() == "historial":
            for paso in agent.historial_pasos:
                print(f"  {paso}")
            continue

        # ── Ejecutar agente ─────────────────────────────────
        if RICH_AVAILABLE:
            console.print("\n[dim]🤖 Pensando...[/dim]\n")
        else:
            print("\n🤖 Pensando...\n")

        resultado = agent.think(pregunta)

        # Mostrar resumen de la ejecución
        if RICH_AVAILABLE:
            console.print(
                f"\n[dim]Iteraciones: {resultado['iteraciones']} | "
                f"Herramientas usadas: {len(resultado['herramientas_usadas'])}[/dim]\n"
            )
        else:
            print(f"\n  Iteraciones: {resultado['iteraciones']} | "
                  f"Herramientas: {len(resultado['herramientas_usadas'])}\n")

    # ── Cerrar ──────────────────────────────────────────────
    agent.memory.cerrar()


if __name__ == "__main__":
    main()
