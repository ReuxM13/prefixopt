"""
Console entry point for prefixopt.

Creates the Typer application and registers every CLI subcommand. Each command
lives in its own module under ``cli/``; this file only wires names to callables.

Adding a new command:
    1. Implement a function in ``src/prefixopt/cli/<name>.py``.
    2. Import the module here.
    3. Register it with ``app.command(name="<name>")(<module>.<function>)``.

The same ``app`` object is referenced by the ``prefixopt`` console script
declared in ``pyproject.toml`` (``[project.scripts]``).
"""

import os
import sys

import typer

# Import each command module under a short alias so the registration lines
# below stay readable.
from .cli import optimize as opt_cmd
from .cli import filter as flt_cmd
from .cli import merge as mrg_cmd
from .cli import subnet as sub_cmd
from .cli import stats as stat_cmd
from .cli import exclude as exc_cmd
from .cli import diff as diff_cmd
from .cli import gui as gui_cmd


# ``add_completion=False`` disables Typer's one-time shell-completion installer
# prompt so running the tool never unexpectedly modifies the user's shell rc.
app = typer.Typer(add_completion=False)


# Registration uses the explicit decorator-call form rather than ``@app.command``
# so we can keep the command functions themselves free of Typer decoration.
app.command(name="optimize")(opt_cmd.optimize)
app.command(name="add")(opt_cmd.add)
app.command(name="filter")(flt_cmd.filter)
app.command(name="merge")(mrg_cmd.merge)
app.command(name="intersect")(mrg_cmd.intersect)
app.command(name="split")(sub_cmd.split)
app.command(name="stats")(stat_cmd.stats)
app.command(name="check")(stat_cmd.check)
app.command(name="exclude")(exc_cmd.exclude)
app.command(name="diff")(diff_cmd.diff)
app.command(name="gui")(gui_cmd.gui)


if __name__ == "__main__":
    # When executed directly as a script, ensure the package directory is on
    # sys.path so imports work from a source checkout without installation.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    app()
