"""
prefixopt - high-performance CLI/GUI tool for optimizing IP prefix lists.

This package re-exports the high-level API so external callers can simply do::

    from prefixopt import optimize, merge, load

Project layout (read these in order to get up to speed quickly):

    core/        Pure algorithms over IPv4/IPv6 networks (sort, aggregate,
                 remove-nested, subtract, diff, overlap). No I/O, no UI here.
    data/        Parsing and streaming input files (.txt, .csv, .json) plus
                 STDIN. This is where raw text becomes IPNet objects.
    cli/         Typer commands that wire core + data together and print/write
                 results. One module per command.
    gui/         Optional PySide6 desktop application. The ``services`` module
                 is the bridge between the core algorithms and Qt widgets.
    api.py       Programmatic Python API (load, optimize, merge, ...).
    comments.py  Helpers for line-comments attached to prefixes.

The central type used everywhere is ``IPNet`` (an alias for
``IPv4Network | IPv6Network``), defined in ``core.ip_utils``.
"""

from .api import (
    load,
    optimize,
    add,
    exclude,
    diff,
    merge,
    intersect,
    filter,
    split,
    stats,
    check,
)
from .core.ip_utils import IPNet

__version__ = "1.4.0"

__all__ = [
    "load",
    "optimize",
    "add",
    "exclude",
    "diff",
    "merge",
    "intersect",
    "filter",
    "split",
    "stats",
    "check",
    "IPNet",
]
