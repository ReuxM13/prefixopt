"""
Command-line interface built on Typer.

Each submodule implements one user-facing command (optimize, filter, merge,
exclude, etc.) and is wired into the Typer app by :mod:`prefixopt.main`. The
modules here translate CLI options into calls to the core/data layers and then
format results for STDOUT or a file using :mod:`common`.
"""
