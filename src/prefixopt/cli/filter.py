"""
CLI command: ``filter`` - remove special-use IP ranges from a list.

Removes networks matching any of the selected categories (private, loopback,
link-local, multicast, reserved, and/or the catch-all ``--bogons`` flag). By
design the filter does *not* aggregate or sort; it only drops rows.

The command also supports comment mode (``--keep-comments`` /
``--append-comment``); when active the output is rendered as commented lines
and CSV is unavailable.
"""

import sys
from pathlib import Path
from typing import Optional

import typer

from ..comments import merge_comments, normalize_comment
from ..core.operations.filter import filter_special
from ..data.file_reader import (
    read_networks,
    read_prefixes_with_comments,
    read_stream,
    read_stream_with_comments,
)
from .common import OutputFormat, console, handle_output


def _filter_flags(bogons: bool, **flags: bool) -> dict[str, bool]:
    """Resolve individual filter flags against the ``--bogons`` shortcut.

    When ``bogons`` is True every special-range category is enabled regardless
    of the individual flags. Otherwise the passed flags are returned as-is.
    """
    if bogons:
        return {
            "exclude_private": True,
            "exclude_loopback": True,
            "exclude_link_local": True,
            "exclude_multicast": True,
            "exclude_reserved": True,
            "exclude_unspecified": True,
        }
    return {key: value for key, value in flags.items() if key != "bogons"}


def filter(
    input_file: Optional[Path] = typer.Argument(
        None, help="Input file (optional if using pipe/stdin)"
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file (default: stdout)"
    ),
    exclude_private: bool = typer.Option(
        False, "--no-private", help="Exclude Private networks (RFC 1918, ULA)"
    ),
    exclude_loopback: bool = typer.Option(
        False, "--no-loopback", help="Exclude Loopback (127.x.x.x, ::1)"
    ),
    exclude_link_local: bool = typer.Option(
        False,
        "--no-link-local",
        help="Exclude Link-Local (169.254.x.x, fe80::)",
    ),
    exclude_multicast: bool = typer.Option(
        False, "--no-multicast", help="Exclude Multicast"
    ),
    exclude_reserved: bool = typer.Option(
        False, "--no-reserved", help="Exclude IETF Reserved networks"
    ),
    bogons: bool = typer.Option(
        False,
        "--bogons",
        help="Exclude ALL special use networks",
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
        help="Preserve comments from the input list.",
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
    """Filter out special types of networks."""
    try:
        # Commented output is line-based; combining it with CSV makes no sense.
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

        flags = _filter_flags(
            bogons=bogons,
            exclude_private=exclude_private,
            exclude_loopback=exclude_loopback,
            exclude_link_local=exclude_link_local,
            exclude_multicast=exclude_multicast,
            exclude_reserved=exclude_reserved,
            exclude_unspecified=True,
        )

        commented_mode = keep_comments or bool(append_comment)

        # Pick the right reader depending on source (file vs STDIN) and mode.
        if input_file:
            source = (
                read_prefixes_with_comments(input_file, strict=strict)
                if commented_mode
                else read_networks(input_file, strict=strict)
            )
        elif not sys.stdin.isatty():
            source = (
                read_stream_with_comments(sys.stdin, strict=strict)
                if commented_mode
                else read_stream(sys.stdin, strict=strict)
            )
        else:
            console.print("[red]Error: No input provided.[/red]")
            sys.exit(1)

        if commented_mode:
            # Filter one (network, comment) pair at a time. We apply the filter
            # per network rather than building a set to keep comments bound to
            # their original prefixes.
            items = []
            original_count = 0
            for net, comment in source:
                original_count += 1
                filtered = list(filter_special([net], **flags))
                if not filtered:
                    continue
                if append_comment:
                    base = comment if keep_existing_comments else ""
                    comment = merge_comments(
                        base, normalize_comment(append_comment)
                    )
                items.append((filtered[0], comment))

            lines = []
            for net, comment in items:
                if comment:
                    lines.append(f"{net} {comment}")
                else:
                    lines.append(str(net))
            content = "\n".join(lines)
            if content:
                content += "\n"
            removed_count = original_count - len(items)

            if output_file:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(content)
                console.print(
                    f"[green]Saved {len(items)} prefixes to {output_file}[/green]"
                )
            else:
                print(content, end="")
        else:
            all_prefixes = list(source)
            original_count = len(all_prefixes)
            filtered_list = list(filter_special(all_prefixes, **flags))
            removed_count = original_count - len(filtered_list)
            handle_output(filtered_list, format, output_file)

        # Avoid polluting piped CSV output with a trailing status message.
        if output_file or (
            format == OutputFormat.list
            and sys.stdout.isatty()
            and not commented_mode
        ):
            if removed_count > 0:
                console.print(
                    f"\n[dim]Removed {removed_count} networks based on "
                    "filter criteria[/dim]"
                )

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
