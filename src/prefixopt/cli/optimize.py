"""
CLI commands for list optimisation: ``optimize`` and ``add``.

``optimize`` runs the full sort -> remove-nested -> aggregate pipeline and is
the most commonly used command. ``add`` inserts a new prefix into an existing
list and then re-optimises it.

Both commands support two comment modes:
    * ``--keep-comments`` preserves inline ``# comments`` but disables
      aggregation/nested removal because merging networks would lose or
      ambiguously combine comments.
    * ``--append-comment TEXT`` [+ ``--keep-existing-comments``] stamps every
      output prefix with a new comment. By default old comments are discarded;
      with ``--keep-existing-comments`` the new comment is appended to them.
"""

import ipaddress
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import typer

from ..comments import (
    annotate_networks,
    apply_append_comment,
    normalize_comment,
)
from ..core.ip_utils import IPNet, normalize_prefix
from ..core.pipeline import process_prefixes
from ..data.file_reader import (
    read_networks,
    read_prefixes_with_comments,
    read_stream,
    read_stream_with_comments,
)
from .common import OutputFormat, console, handle_output

# A prefix together with its comment string (empty if none).
CommentedItem = Tuple[IPNet, str]


def _sort_key(item: CommentedItem) -> tuple[int, int, int]:
    """Sort key for commented items matching the broadest-first ordering."""
    net, _ = item
    return (net.version, int(net.network_address), net.prefixlen)


def _deduplicate_commented_prefixes(
    source: Iterable[CommentedItem],
    ipv4_only: bool = False,
    ipv6_only: bool = False,
) -> Dict[str, str]:
    """Collapse duplicate prefixes, keeping the first non-empty comment.

    Returns a mapping of canonical prefix string -> comment.
    """
    unique_map: Dict[str, str] = {}

    for net, comment in source:
        if ipv4_only and net.version != 4:
            continue
        if ipv6_only and net.version != 6:
            continue

        net_str = str(net)
        if net_str not in unique_map:
            unique_map[net_str] = comment
        elif not unique_map[net_str] and comment:
            # Prefer any non-empty comment over an empty earlier one.
            unique_map[net_str] = comment

    return unique_map


def _materialize_commented_prefixes(
    unique_map: Dict[str, str],
) -> List[CommentedItem]:
    """Turn the dedup dictionary back into a sorted list of pairs."""
    result: List[CommentedItem] = []
    for prefix_str, comment in unique_map.items():
        net_obj = ipaddress.ip_network(prefix_str, strict=False)
        result.append((net_obj, comment))
    result.sort(key=_sort_key)
    return result


def _render_commented_prefixes(items: List[CommentedItem]) -> str:
    """Render commented pairs into a newline-terminated text block."""
    lines: List[str] = []
    for net, comment in items:
        if comment:
            lines.append(f"{net} {comment}")
        else:
            lines.append(str(net))
    return "\n".join(lines) + "\n"


def _write_commented_output(
    items: List[CommentedItem],
    output_file: Optional[Path],
    success_message: str,
) -> None:
    """Write commented output to a file or stdout and print a status line."""
    content = _render_commented_prefixes(items)
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
        console.print(
            success_message.format(count=len(items), path=output_file)
        )
    else:
        # Avoid adding an extra newline when piping to stdout.
        print(content, end="")


def _validate_comment_append_options(
    append_comment: Optional[str],
    keep_existing_comments: bool,
    fmt: OutputFormat,
) -> None:
    """Reject incompatible combinations of comment flags."""
    if append_comment and fmt == OutputFormat.csv:
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


def optimize(
    input_file: Optional[Path] = typer.Argument(
        None, help="Input file (optional if using pipe/stdin)"
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file (default: stdout)"
    ),
    ipv6_only: bool = typer.Option(
        False, "--ipv6-only", help="Process IPv6 prefixes only"
    ),
    ipv4_only: bool = typer.Option(
        False, "--ipv4-only", help="Process IPv4 prefixes only"
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
        help="Preserve comments. Disables aggregation and nested cleanup.",
    ),
    append_comment: Optional[str] = typer.Option(
        None,
        "--append-comment",
        help="Append this comment to all output prefixes. Existing comments "
        "are removed unless --keep-existing-comments is used.",
    ),
    keep_existing_comments: bool = typer.Option(
        False,
        "--keep-existing-comments",
        help="Keep existing comments and append the new comment to the end. "
        "Requires --append-comment.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Fail on invalid network addresses with host bits set instead "
        "of auto-correcting them.",
    ),
) -> None:
    """Optimise an IP prefix list (sort, remove nested, aggregate)."""
    try:
        if keep_comments and format == OutputFormat.csv:
            console.print(
                "[red]Error: Cannot use --keep-comments with CSV format.[/red]"
            )
            sys.exit(1)
        _validate_comment_append_options(
            append_comment, keep_existing_comments, format
        )

        # Fast path: append a comment while allowing full optimisation. Old
        # comments are discarded here, so aggregation is safe.
        if append_comment and not keep_existing_comments:
            if input_file:
                prefixes = list(read_networks(input_file, strict=strict))
                input_count = len(prefixes)
            elif not sys.stdin.isatty():
                prefixes = list(read_stream(sys.stdin, strict=strict))
                input_count = len(prefixes)
            else:
                console.print(
                    "[red]Error: No input provided. Give me a file or pipe "
                    "data via STDIN.[/red]"
                )
                sys.exit(1)

            processed = process_prefixes(
                prefixes,
                sort=True,
                remove_nested=True,
                aggregate=True,
                ipv4_only=ipv4_only,
                ipv6_only=ipv6_only,
            )
            result_list = list(processed)
            # Stamp every optimised prefix with the same comment.
            items = annotate_networks(result_list, append_comment)
            _write_commented_output(
                items,
                output_file,
                "[green]Saved {count} prefixes (with comments) to {path}[/green]",
            )
            if output_file:
                console.print(
                    f"[dim]Input: {input_count}, output: {len(result_list)}[/dim]"
                )
            return

        # Comment-preserving path: only dedupe/sort, never aggregate.
        if keep_comments or keep_existing_comments or append_comment:
            source: Iterable[CommentedItem]
            if input_file:
                source = read_prefixes_with_comments(input_file, strict=strict)
            elif not sys.stdin.isatty():
                source = read_stream_with_comments(sys.stdin, strict=strict)
            else:
                console.print(
                    "[red]Error: No input provided. Give me a file or pipe "
                    "data via STDIN.[/red]"
                )
                sys.exit(1)

            if append_comment:
                # keep_existing_comments is True in this branch; apply the
                # append rule lazily via a generator.
                source = (
                    (
                        net,
                        apply_append_comment(
                            comment, append_comment, keep_existing=True
                        ),
                    )
                    for net, comment in source
                )

            unique_map = _deduplicate_commented_prefixes(
                source, ipv4_only=ipv4_only, ipv6_only=ipv6_only
            )
            result_list = _materialize_commented_prefixes(unique_map)
            _write_commented_output(
                result_list,
                output_file,
                "[green]Saved {count} prefixes (with comments) to {path}[/green]",
            )
            return

        # Default path: no comments at all - full pipeline + standard output.
        if input_file:
            prefixes = read_networks(input_file, strict=strict)
        elif not sys.stdin.isatty():
            prefixes = read_stream(sys.stdin, strict=strict)
        else:
            console.print(
                "[red]Error: No input provided. Give me a file or pipe data "
                "via STDIN.[/red]"
            )
            sys.exit(1)

        processed_prefixes = process_prefixes(
            prefixes,
            sort=True,
            remove_nested=True,
            aggregate=True,
            ipv4_only=ipv4_only,
            ipv6_only=ipv6_only,
        )
        handle_output(processed_prefixes, format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def add(
    new_prefix: str = typer.Argument(..., help="New prefix to add"),
    input_file: Path = typer.Argument(
        ..., help="Input file with existing IP prefixes"
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file (default: stdout)"
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
        help="Preserve comments. Disables aggregation.",
    ),
    append_comment: Optional[str] = typer.Option(
        None,
        "--append-comment",
        help="Append this comment to all output prefixes. Existing comments "
        "are removed unless --keep-existing-comments is used.",
    ),
    keep_existing_comments: bool = typer.Option(
        False,
        "--keep-existing-comments",
        help="Keep existing comments and append the new comment to the end. "
        "Requires --append-comment.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Fail on invalid network addresses with host bits set instead "
        "of auto-correcting them.",
    ),
) -> None:
    """Add a prefix to a list and return the re-optimised result."""
    try:
        try:
            network_to_add = normalize_prefix(new_prefix, strict=strict)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

        if keep_comments and format == OutputFormat.csv:
            console.print(
                "[red]Error: Cannot use --keep-comments with CSV format.[/red]"
            )
            sys.exit(1)
        _validate_comment_append_options(
            append_comment, keep_existing_comments, format
        )

        # Append-comment mode: optimise fully then stamp every result.
        if append_comment:
            if not keep_existing_comments:
                prefixes = list(read_networks(input_file, strict=strict))
                if network_to_add not in prefixes:
                    prefixes.append(network_to_add)
                processed = process_prefixes(
                    prefixes,
                    sort=True,
                    remove_nested=True,
                    aggregate=True,
                )
                items = annotate_networks(list(processed), append_comment)
                _write_commented_output(
                    items,
                    output_file,
                    "[green]Saved {count} prefixes to {path}[/green]",
                )
                return

            # Append while preserving existing comments.
            unique_map = _deduplicate_commented_prefixes(
                read_prefixes_with_comments(input_file, strict=strict)
            )
            annotation = normalize_comment(append_comment)
            for net_str, comment in list(unique_map.items()):
                unique_map[net_str] = apply_append_comment(
                    comment, append_comment, keep_existing=True
                )
            unique_map[str(network_to_add)] = annotation
            result_list = _materialize_commented_prefixes(unique_map)
            _write_commented_output(
                result_list,
                output_file,
                "[green]Saved {count} prefixes to {path}[/green]",
            )
            return

        # Legacy keep-comments mode: add with an explicit marker comment.
        if keep_comments:
            if format == OutputFormat.csv:
                console.print(
                    "[red]Error: Cannot use --keep-comments with CSV "
                    "format.[/red]"
                )
                sys.exit(1)

            unique_map = _deduplicate_commented_prefixes(
                read_prefixes_with_comments(input_file, strict=strict)
            )
            new_net_str = str(network_to_add)
            if new_net_str in unique_map:
                console.print(
                    f"[yellow]Prefix {new_net_str} already exists in the "
                    "list.[/yellow]"
                )
            else:
                unique_map[new_net_str] = (
                    f"# Added manually: {new_prefix}"
                )

            result_list = _materialize_commented_prefixes(unique_map)
            _write_commented_output(
                result_list,
                output_file,
                "[green]Saved {count} prefixes to {path}[/green]",
            )
            return

        # Default: add and fully re-optimise, no comments.
        prefixes = list(read_networks(input_file, strict=strict))
        if network_to_add not in prefixes:
            prefixes.append(network_to_add)

        processed_prefixes = process_prefixes(
            prefixes,
            sort=True,
            remove_nested=True,
            aggregate=True,
        )
        handle_output(processed_prefixes, format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
