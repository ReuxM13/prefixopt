"""
CLI-команда для запуска графического интерфейса.
"""
import sys
import typer

from .common import console


def gui() -> None:
    """
    Launch the graphical user interface.
    """
    # Сначала проверяем, установлен ли PySide6
    try:
        import PySide6  # noqa: F401
    except ImportError:
        console.print(
            "[red]GUI dependencies are not installed.[/red]\n"
            "Install them with:\n"
            "[bold]pip install prefixopt[gui][/bold]"
        )
        raise typer.Exit(code=1)

    # Теперь импортируем run_gui, позволяя другим импортным ошибкам проявиться
    try:
        from ..gui.app import run_gui
    except Exception as e:
        console.print(f"[red]Failed to import GUI module: {e}[/red]")
        from traceback import format_exc
        console.print(format_exc())
        raise typer.Exit(code=1)

    try:
        run_gui()
    except Exception as e:
        console.print(f"[red]Error starting GUI: {e}[/red]")
        raise typer.Exit(code=1)