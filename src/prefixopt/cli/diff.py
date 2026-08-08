"""
CLI command: ``diff`` - semantic comparison of two prefix lists.

Both files are first fully optimised (sort -> remove nested -> aggregate), so
two lists that cover the same address space with different CIDR boundaries
(e.g. one /23 vs two /24s) compare as identical. The result is shown with
``+``/``-``/``=`` markers and can be filtered by mode.
"""

import contextlib
import sys
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

import typer

from ..core.ip_utils import IPNet
from ..core.operations.diff import calculate_diff
from ..core.operations.sorter import sort_networks
from ..core.pipeline import process_prefixes
from ..data.file_reader import read_networks
from .common import console, is_interactive


class DiffMode(str, Enum):
    """Which sections of the diff to display."""

    changes = "changes"
    added = "added"
    removed = "removed"
    unchanged = "unchanged"
    all = "all"


def diff(
    new_file: Path = typer.Argument(
        ..., help="New/Target file (Source of Truth)"
    ),
    old_file: Path = typer.Argument(
        ..., help="Old/Current file (to compare against)"
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file for diff report"
    ),
    summary_only: bool = typer.Option(
        False,
        "--summary",
        "-s",
        help="Show only counts, not prefixes",
    ),
    mode: DiffMode = typer.Option(
        DiffMode.changes,
        "--mode",
        "-m",
        help="Display mode: changes (default), added, removed, unchanged, all",
    ),
    ipv6_only: bool = typer.Option(
        False, "--ipv6-only", help="Process IPv6 prefixes only"
    ),
    ipv4_only: bool = typer.Option(
        False, "--ipv4-only", help="Process IPv4 prefixes only"
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Fail on invalid network addresses with host bits set instead "
        "of auto-correcting them.",
    ),
) -> None:
    """Compare two files and show added/removed/unchanged prefixes."""
    try:

        def prepare(path: Path) -> Iterable[IPNet]:
            """Read and fully optimise one side of the diff."""
            raw = read_networks(path, strict=strict)
            return process_prefixes(
                raw,
                sort=True,
                remove_nested=True,
                aggregate=True,
                ipv4_only=ipv4_only,
                ipv6_only=ipv6_only,
            )

        if is_interactive():
            status_cm = console.status(
                "[bold green]Calculating differences...", spinner="dots"
            )
        else:
            status_cm = contextlib.nullcontext()
        with status_cm:
            nets_new = list(prepare(new_file))
            nets_old = list(prepare(old_file))
            added, removed, unchanged = calculate_diff(nets_new, nets_old)

        # Translate the display mode into which sections should be printed.
        show_added = mode in (DiffMode.changes, DiffMode.added, DiffMode.all)
        show_removed = mode in (
            DiffMode.changes,
            DiffMode.removed,
            DiffMode.all,
        )
        show_unchanged = mode in (DiffMode.unchanged, DiffMode.all)

        if summary_only:
            # Compact count-only output, suitable for scripts.
            if show_added:
                console.print(f"[green]Added: {len(added)}[/green]")
            if show_removed:
                console.print(f"[red]Removed: {len(removed)}[/red]")
            if show_unchanged:
                console.print(f"[blue]Unchanged: {len(unchanged)}[/blue]")
            return

        sorted_added = sort_networks(added) if show_added else []
        sorted_removed = sort_networks(removed) if show_removed else []
        sorted_unchanged = (
            sort_networks(unchanged) if show_unchanged else []
        )

        if output_file:
            # File output uses simple markers that are easy to grep/parse.
            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    for net in sorted_added:
                        f.write(f"+ {net}\n")
                    for net in sorted_removed:
                        f.write(f"- {net}\n")
                    for net in sorted_unchanged:
                        f.write(f"= {net}\n")
                console.print(
                    f"[green]Diff saved to {output_file} "
                    f"(Mode: {mode.value})[/green]"
                )
            except IOError as e:
                console.print(f"[red]Error writing to file: {e}[/red]")
                sys.exit(1)
        else:
            # Interactive output with Rich colours.
            if (
                not sorted_added
                and not sorted_removed
                and not sorted_unchanged
            ):
                if mode == DiffMode.changes and (not added and not removed):
                    console.print(
                        "[bold green]Files are identical "
                        "(semantically)[/bold green]"
                    )
                return

            if sorted_added:
                console.print(
                    f"\n[bold green]+++ Added ({len(sorted_added)}):[/bold green]"
                )
                for net in sorted_added:
                    console.print(f"[green]+ {net}[/green]")

            if sorted_removed:
                console.print(
                    f"\n[bold red]--- Removed ({len(sorted_removed)}):[/bold red]"
                )
                for net in sorted_removed:
                    console.print(f"[red]- {net}[/red]")

            if sorted_unchanged:
                console.print(
                    f"\n[bold blue]=== Unchanged "
                    f"({len(sorted_unchanged)}):[/bold blue]"
                )
                for net in sorted_unchanged:
                    console.print(f"[blue]= {net}[/blue]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
