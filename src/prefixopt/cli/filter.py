"""
Модуль команды filter для CLI.
"""
import sys
from pathlib import Path
from typing import Optional

import typer

from .common import OutputFormat, handle_output, console
from ..data.file_reader import read_networks, read_stream
from ..core.pipeline import process_prefixes


def filter(
    input_file: Optional[Path] = typer.Argument(None, help="Input file (optional if using pipe/stdin)"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    exclude_private: bool = typer.Option(False, "--no-private", help="Exclude Private networks (RFC 1918, ULA)"),
    exclude_loopback: bool = typer.Option(False, "--no-loopback", help="Exclude Loopback (127.x.x.x, ::1)"),
    exclude_link_local: bool = typer.Option(False, "--no-link-local", help="Exclude Link-Local (169.254.x.x, fe80::)"),
    exclude_multicast: bool = typer.Option(False, "--no-multicast", help="Exclude Multicast"),
    exclude_reserved: bool = typer.Option(False, "--no-reserved", help="Exclude IETF Reserved networks"),
    bogons: bool = typer.Option(False, "--bogons", help="Exclude ALL special use networks (Private, Loopback, Reserved, etc.)"),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    )
) -> None:
    """
    Filters out special types of networks.
    """
    try:
        if input_file:
            all_prefixes = list(read_networks(input_file))
        elif not sys.stdin.isatty():
            all_prefixes = list(read_stream(sys.stdin))
        else:
            console.print("[red]Error: No input provided.[/red]")
            sys.exit(1)

        original_count = len(all_prefixes)

        filtered_prefixes = process_prefixes(
            all_prefixes,
            sort=False,
            remove_nested=False,
            aggregate=False,
            exclude_private=exclude_private,
            exclude_loopback=exclude_loopback,
            exclude_link_local=exclude_link_local,
            exclude_multicast=exclude_multicast,
            exclude_reserved=exclude_reserved,
            exclude_unspecified=True,
            bogons=bogons
        )
        
        filtered_list = list(filtered_prefixes)
        removed_count = original_count - len(filtered_list)

        handle_output(filtered_list, format, output_file)

        if output_file or (format == OutputFormat.list and sys.stdout.isatty()):
             if removed_count > 0:
                console.print(f"\n[dim]Removed {removed_count} networks based on filter criteria[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)