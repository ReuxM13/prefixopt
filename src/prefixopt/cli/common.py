"""
Shared utilities for CLI commands.

Contains:
    * :class:`OutputFormat` - enum of the supported output formats.
    * :data:`console`       - shared Rich Console used for coloured messages.
    * :func:`handle_output` - write an iterable of networks to stdout or a file
                              in either list (one per line) or CSV format.
"""

import sys
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional, TextIO, Union

from ipaddress import IPv4Network, IPv6Network
from rich.console import Console

# One console is shared across commands so Rich's colour/terminal detection is
# configured consistently for the whole process.
console = Console()


def is_interactive() -> bool:
    """Return True when both stdout and stderr are attached to a TTY.

    Live spinners and progress bars are only enabled interactively; when the
    output is piped/redirected we suppress them so no control characters or
    stray newlines leak into the machine-readable data on stdout.
    """
    try:
        return sys.stdout.isatty() and sys.stderr.isatty()
    except (AttributeError, ValueError):
        return False


class OutputFormat(str, Enum):
    """Output format used by commands that emit a plain prefix list.

    ``list`` produces one prefix per line; ``csv`` produces a single
    comma-separated line (useful for shell one-liners).
    """

    list = "list"
    csv = "csv"


def handle_output(
    prefixes: Iterable[Union[IPv4Network, IPv6Network]],
    fmt: OutputFormat,
    output_file: Optional[Path],
) -> None:
    """Write networks to stdout or to ``output_file`` in the chosen format.

    The function streams the input iterable rather than materialising it, so
    very large outputs can be written without loading everything into RAM.

    Args:
        prefixes:     Networks to emit.
        fmt:          List or CSV.
        output_file:  Destination path, or ``None`` for stdout.

    Exits:
        Calls ``sys.exit(1)`` if the output file cannot be opened/written.
    """
    file_handle: TextIO
    if output_file:
        try:
            file_handle = open(output_file, "w", encoding="utf-8")
        except IOError as e:
            console.print(f"[red]Error opening file: {e}[/red]")
            sys.exit(1)
    else:
        file_handle = sys.stdout

    count = 0
    try:
        # Enumerate so we know whether to emit a leading CSV separator.
        for i, prefix in enumerate(prefixes):
            prefix_str = str(prefix)

            if fmt == OutputFormat.csv:
                separator = "," if i > 0 else ""
                file_handle.write(f"{separator}{prefix_str}")
            else:
                file_handle.write(f"{prefix_str}\n")

            count = i + 1

        # POSIX text files should end with a newline; in list mode each line
        # already has one, for CSV we append it after the final element.
        if fmt == OutputFormat.csv and count > 0:
            file_handle.write("\n")

        # Only print a success message when writing to a file - printing to
        # stdout would corrupt piped output.
        if output_file:
            file_handle.close()
            format_desc = (
                "comma-separated" if fmt == OutputFormat.csv else "list"
            )
            console.print(
                f"[green]Saved {count} prefixes to {output_file} "
                f"({format_desc})[/green]"
            )

    except IOError as e:
        console.print(f"[red]Error writing output: {e}[/red]")
        sys.exit(1)
    finally:
        # Never close stdout; only close files we opened ourselves.
        if output_file and not file_handle.closed:
            file_handle.close()
