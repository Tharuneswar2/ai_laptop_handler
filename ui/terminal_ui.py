"""
ui/terminal_ui.py — Rich terminal interface for the assistant.

Displays status, recognized text, selected tool, and results
in a styled terminal panel using the `rich` library.
"""

import logging
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
from rich.columns import Columns

logger = logging.getLogger(__name__)

console = Console()


def print_banner() -> None:
    """Print the startup banner."""
    banner = Text()
    banner.append("╔══════════════════════════════════════════╗\n", style="bold cyan")
    banner.append("║     ", style="bold cyan")
    banner.append("🎤 AI Laptop Handler ", style="bold white")
    banner.append("(Nova)          ", style="bold magenta")
    banner.append("║\n", style="bold cyan")
    banner.append("║     ", style="bold cyan")
    banner.append("Voice-Controlled Laptop Assistant   ", style="dim white")
    banner.append("║\n", style="bold cyan")
    banner.append("╚══════════════════════════════════════════╝", style="bold cyan")
    console.print(banner)
    console.print()


def print_status(status: str, style: str = "bold green") -> None:
    """Print a status message."""
    console.print(f"  [bold white]Status:[/] [{style}]{status}[/]")


def print_heard(text: str) -> None:
    """Print what the assistant heard."""
    if text:
        console.print(f"  [bold white]Heard :[/] [yellow]{text}[/]")


def print_intent(tool: str, action: str) -> None:
    """Print the parsed intent."""
    console.print(f"  [bold white]Tool  :[/] [cyan]{tool}[/]")
    console.print(f"  [bold white]Action:[/] [cyan]{action}[/]")


def print_result(message: str, success: bool = True) -> None:
    """Print the tool result."""
    icon = "✅" if success else "❌"
    style = "green" if success else "red"
    console.print(f"  [bold white]Result:[/] [{style}]{icon} {message}[/]")


def print_divider() -> None:
    """Print a visual divider between interactions."""
    console.print("[dim]  ─────────────────────────────────────────[/]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"  [bold red]Error :[/] [red]{message}[/]")


def print_help() -> None:
    """Print help information with example commands."""
    table = Table(title="Example Commands", show_header=True, header_style="bold cyan")
    table.add_column("Say this...", style="yellow", min_width=35)
    table.add_column("Does this", style="white")

    examples = [
        ("Hey Nova, open Chrome", "Opens Google Chrome"),
        ("Hey Nova, create a folder called projects", "Creates ~/projects folder"),
        ("Hey Nova, search FastAPI on YouTube", "Searches YouTube"),
        ("Hey Nova, how much disk space is left?", "Shows disk usage"),
        ("Hey Nova, take a screenshot", "Captures screen"),
        ("Hey Nova, list running apps", "Shows running apps"),
        ("Hey Nova, check battery", "Shows battery status"),
        ("Hey Nova, lock the screen", "Locks screen"),
    ]

    for cmd, desc in examples:
        table.add_row(cmd, desc)

    console.print()
    console.print(table)
    console.print()


def display_interaction(heard: str, tool: str, action: str, result_msg: str, success: bool) -> None:
    """Display a complete interaction in a single panel."""
    content = Table.grid(padding=(0, 1))
    content.add_column(min_width=8)
    content.add_column()

    content.add_row("[bold white]Heard[/]", f"[yellow]{heard}[/]")
    content.add_row("[bold white]Tool[/]", f"[cyan]{tool}[/]")
    content.add_row("[bold white]Action[/]", f"[cyan]{action}[/]")

    icon = "✅" if success else "❌"
    style = "green" if success else "red"
    content.add_row("[bold white]Result[/]", f"[{style}]{icon} {result_msg}[/]")

    panel = Panel(
        content,
        title="[bold magenta]Nova[/]",
        border_style="cyan",
        padding=(0, 1),
    )
    console.print(panel)


def prompt_text_input() -> str:
    """Get text input from the user (for text mode)."""
    try:
        text = console.input("[bold cyan]You > [/]")
        return text.strip()
    except (EOFError, KeyboardInterrupt):
        return ""
