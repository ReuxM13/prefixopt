"""
CLI command: ``gui`` - launch the optional PySide6 desktop application.

The GUI is an *optional* dependency (``pip install prefixopt[gui]``). This
shim checks that PySide6 is importable before deferring to
:func:`prefixopt.gui.app.run_gui`, producing a friendly installation hint
when the extras are missing.
"""

import typer

from .common import console


def gui() -> None:
    """Launch the graphical user interface."""
    # First verify the GUI extra is installed.
    try:
        import PySide6  # noqa: F401  (import is the availability check)
    except ImportError:
        console.print(
            "[red]GUI dependencies are not installed.[/red]\n"
            "Install them with:\n"
            "[bold]pip install prefixopt[gui][/bold]"
        )
        raise typer.Exit(code=1)

    # Imported lazily so the rest of the CLI works without PySide6 present.
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
