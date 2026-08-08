"""
CLI command: ``split`` - de-aggregate networks into smaller subnets.

Given a target prefix length (e.g. 24 for /24) and either a single prefix or
a file/STDIN of prefixes, emits all subnets of that length contained in each
input. Useful for slicing large ranges into scanner-sized chunks.

Supports comment inheritance: each child subnet can carry its parent's
comment and/or a freshly appended comment.
"""

import ipaddress
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Union

import typer
from ipaddress import IPv4Network, IPv6Network

from ..comments import apply_append_comment
from ..core.ip_utils import IPNet
from ..core.operations.subnetter import split_network
from ..data.file_reader import (
    read_networks,
    read_prefixes_with_comments,
    read_stream,
    read_stream_with_comments,
)
from .common import OutputFormat, console, handle_output


def _write_commented_output(
    items: List[Tuple[Union[IPv4Network, IPv6Network], str]],
    output_file: Optional[Path],
) -> None:
    """Render commented subnets and write to a file or STDOUT."""
    lines = [
        f"{net} {comment}" if comment else str(net)
        for net, comment in items
    ]
    content = "\n".join(lines)
    if content:
        content += "\n"
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
        console.print(f"[green]Generated {len(items)} subnets[/green]")
    else:
        print(content, end="")


def split(
    target_length: int = typer.Argument(
        ..., help="Target prefix length (e.g., 24 for /24)"
    ),
    prefix: Optional[str] = typer.Argument(
        None,
        help="Prefix to split. Optional if file/stdin used.",
    ),
    input_file: Optional[Path] = typer.Option(
        None, "--file", "-i", help="Input file"
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file (default: stdout)",
    ),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format",
        "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)",
    ),
    keep_comments: bool = typer.Option(
        False,
        "--keep-comments",
        help="Preserve parent comments on generated subnets.",
    ),
    append_comment: Optional[str] = typer.Option(
        None,
        "--append-comment",
        help="Append this comment to all generated subnets. Existing comments "
        "are removed unless --keep-existing-comments is used.",
    ),
    keep_existing_comments: bool = typer.Option(
        False,
        "--keep-existing-comments",
        help="Keep existing parent comments and append the new comment to the "
        "end. Requires --append-comment.",
    ),
) -> None:
    """Split one or more networks into subnets of the given length."""
    try:
        # Comments and CSV output are mutually exclusive.
        if keep_comments and format == OutputFormat.csv:
            console.print(
                "[red]Error: Cannot use --keep-comments with CSV format.[/red]"
            )
            sys.exit(1)
        if append_comment and format == OutputFormat.csv:
            console.print(
                "[red]Error: Cannot use --append-comment with CSV format.[/red]"
            )
            sys.exit(1)
        if keep_existing_comments and not append_comment:
            console.print(
                "[red]Error: --keep-existing-comments requires "
                "--append-comment.[/red]"
            )
            sys.exit(1)

        commented_mode = keep_comments or bool(append_comment)
        result: List[Union[IPv4Network, IPv6Network]] = []
        commented_result: List[
            Tuple[Union[IPv4Network, IPv6Network], str]
        ] = []

        # Branch on the input source. Each branch mirrors the same split logic
        # but chooses between commented and non-commented readers.
        if input_file:
            if commented_mode:
                for net, comment in read_prefixes_with_comments(input_file):
                    for sub in split_network(net, target_length):
                        effective_comment = (
                            comment
                            if (keep_comments or keep_existing_comments)
                            else ""
                        )
                        if append_comment:
                            effective_comment = apply_append_comment(
                                effective_comment,
                                append_comment,
                                keep_existing=keep_existing_comments,
                            )
                        commented_result.append((sub, effective_comment))
            else:
                for p in read_networks(input_file):
                    result.extend(split_network(p, target_length))
        elif not sys.stdin.isatty() and not prefix:
            # No explicit prefix and piped input available.
            if commented_mode:
                for net, comment in read_stream_with_comments(sys.stdin):
                    for sub in split_network(net, target_length):
                        effective_comment = (
                            comment
                            if (keep_comments or keep_existing_comments)
                            else ""
                        )
                        if append_comment:
                            effective_comment = apply_append_comment(
                                effective_comment,
                                append_comment,
                                keep_existing=keep_existing_comments,
                            )
                        commented_result.append((sub, effective_comment))
            else:
                for p in read_stream(sys.stdin):
                    result.extend(split_network(p, target_length))
        elif prefix:
            # Single-prefix mode from the command line.
            network = ipaddress.ip_network(prefix, strict=False)
            result = split_network(network, target_length)
            if append_comment:
                commented_result = [
                    (sub, apply_append_comment("", append_comment, False))
                    for sub in result
                ]
        else:
            console.print(
                "[red]Error: Either a prefix, an input file, or piped data "
                "must be specified[/red]"
            )
            sys.exit(1)

        if commented_result:
            _write_commented_output(commented_result, output_file)
        else:
            handle_output(result, format, output_file)
            if output_file or format == OutputFormat.list:
                console.print(
                    f"[green]Generated {len(result)} subnets[/green]"
                )

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
