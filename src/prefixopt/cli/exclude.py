"""
CLI command: ``exclude`` - subtract networks from a source list.

This is "hole punching": given a source network and a network to remove, the
source is split into the CIDR fragments that cover the remainder. For example,
``10.0.0.0/30`` minus ``10.0.0.1/32`` yields ``10.0.0.0/32`` and
``10.0.0.2/31``.

Supports comment inheritance (fragments inherit their parent network's
comment, unless replaced by ``--append-comment``) and the standard output
options.
"""

import contextlib
import sys
from pathlib import Path
from typing import Dict, List, Optional

import typer

from ..comments import apply_append_comment
from ..core.ip_utils import IPNet, is_subnet_of, normalize_prefix
from ..core.operations.subtractor import subtract_networks
from ..core.pipeline import process_prefixes
from ..data.file_reader import (
    read_networks,
    read_prefixes_with_comments,
    read_stream,
)
from .common import OutputFormat, console, handle_output, is_interactive


def _inherited_comment(
    fragment: IPNet,
    comments_map: Dict[IPNet, str],
    source_prefixes: List[IPNet],
) -> str:
    """Return the comment that should be inherited by a resulting fragment.

    If the fragment exactly matches a source prefix its comment is used;
    otherwise we find the smallest source network that contains it and
    inherit that parent's comment (used after hole-punching).
    """
    if fragment in comments_map:
        return comments_map[fragment]
    for original in source_prefixes:
        if (
            fragment.version == original.version
            and is_subnet_of(fragment, original)
            and original in comments_map
        ):
            return comments_map[original]
    return ""


def exclude(
    target: str = typer.Argument(
        ..., help="Prefix to exclude (e.g. 10.0.0.0/8) OR path to file"
    ),
    input_file: Optional[Path] = typer.Argument(
        None, help="Input file with IP prefixes"
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file"
    ),
    ipv6_only: bool = typer.Option(
        False, "--ipv6-only", help="Process IPv6 only"
    ),
    ipv4_only: bool = typer.Option(
        False, "--ipv4-only", help="Process IPv4 only"
    ),
    format: OutputFormat = typer.Option(
        OutputFormat.list, "--format", "-f"
    ),
    keep_comments: bool = typer.Option(
        False,
        "--keep-comments",
        help="Preserve comments from input file.",
    ),
    append_comment: Optional[str] = typer.Option(
        None,
        "--append-comment",
        help="Append this comment to all remaining fragments. Existing "
        "comments are removed unless --keep-existing-comments is used.",
    ),
    keep_existing_comments: bool = typer.Option(
        False,
        "--keep-existing-comments",
        help="Keep inherited comments and append the new comment to the end. "
        "Requires --append-comment.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Fail on invalid network addresses with host bits set instead "
        "of auto-correcting them.",
    ),
) -> None:
    """Delete specified networks (Target) from the source list (Input)."""
    try:
        # Comment outputs are line-based and cannot be combined with CSV.
        if keep_comments and format == OutputFormat.csv:
            console.print(
                "[red]Error: Cannot use --keep-comments with CSV "
                "format.[/red]"
            )
            sys.exit(1)
        if append_comment and format == OutputFormat.csv:
            console.print(
                "[red]Error: Cannot use --append-comment with CSV "
                "format.[/red]"
            )
            sys.exit(1)
        if keep_existing_comments and not append_comment:
            console.print(
                "[red]Error: --keep-existing-comments requires "
                "--append-comment.[/red]"
            )
            sys.exit(1)

        # The exclusion target may be either a file of prefixes or a single
        # prefix given on the command line.
        exclude_list: List[IPNet] = []
        target_path = Path(target)
        if target_path.exists():
            exclude_list = list(read_networks(target_path, strict=strict))
        else:
            try:
                exclude_list = [normalize_prefix(target, strict=strict)]
            except ValueError:
                console.print(
                    f"[red]Error: '{target}' is not a valid IP prefix or "
                    "file.[/red]"
                )
                sys.exit(1)

        commented_mode = keep_comments or bool(append_comment)
        source_prefixes: List[IPNet] = []
        comments_map: Dict[IPNet, str] = {}

        if commented_mode:
            # In comment mode we must read from a file (STDIN has no comments
            # support in exclude because target already takes the first arg).
            if not input_file:
                console.print(
                    "[red]Error: comment modes require an input file.[/red]"
                )
                sys.exit(1)
            for net, comm in read_prefixes_with_comments(
                input_file, strict=strict
            ):
                source_prefixes.append(net)
                if comm:
                    comments_map[net] = comm
        else:
            if input_file:
                source_prefixes = list(
                    read_networks(input_file, strict=strict)
                )
            elif not sys.stdin.isatty():
                source_prefixes = list(read_stream(sys.stdin, strict=strict))
            else:
                console.print("[red]Error: No input provided.[/red]")
                sys.exit(1)

        if is_interactive():
            status_cm = console.status("Processing exclusions...", spinner="dots")
        else:
            status_cm = contextlib.nullcontext()
        with status_cm:
            # Core subtraction produces raw fragments.
            raw_result = subtract_networks(source_prefixes, exclude_list)

            if commented_mode:
                # Without preserving old comments we can safely optimise
                # (aggregate) the fragments before stamping the new comment.
                if append_comment and not keep_existing_comments:
                    final_result = process_prefixes(
                        raw_result,
                        sort=True,
                        remove_nested=True,
                        aggregate=True,
                        ipv4_only=ipv4_only,
                        ipv6_only=ipv6_only,
                    )
                    lines = [
                        f"{net} # {append_comment.strip()}"
                        for net in final_result
                    ]
                else:
                    # Preserve/inherit comments: don't aggregate fragments
                    # because that would change comment ownership.
                    raw_result.sort(
                        key=lambda x: (
                            x.version,
                            int(x.network_address),
                            x.prefixlen,
                        )
                    )
                    lines = []
                    for fragment in raw_result:
                        inherited = (
                            _inherited_comment(
                                fragment, comments_map, source_prefixes
                            )
                            if (keep_comments or keep_existing_comments)
                            else ""
                        )
                        if append_comment:
                            comment = apply_append_comment(
                                inherited,
                                append_comment,
                                keep_existing=keep_existing_comments,
                            )
                        else:
                            comment = inherited
                        lines.append(
                            f"{fragment} {comment}"
                            if comment
                            else str(fragment)
                        )

                content = "\n".join(lines)
                if content:
                    content += "\n"
                if output_file:
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    console.print(
                        f"[green]Saved {len(lines)} fragments to "
                        f"{output_file}[/green]"
                    )
                else:
                    print(content, end="")
            else:
                # Non-comment mode: fully optimise the remainder.
                final_result = process_prefixes(
                    raw_result,
                    sort=True,
                    remove_nested=True,
                    aggregate=True,
                    ipv4_only=ipv4_only,
                    ipv6_only=ipv6_only,
                )
                handle_output(list(final_result), format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
