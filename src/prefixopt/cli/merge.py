"""
CLI commands for merging/intersecting prefix lists: ``merge`` and ``intersect``.

``merge`` combines two files (with optional comment preservation and source-1
annotation). ``intersect`` analyses overlaps between one, two or three+ files.

The intersection command deliberately shares a module with merge because both
operate on multiple source lists and use the same overlap-reporting helpers
from :mod:`core.operations.overlap`.
"""

import ipaddress
import sys
from pathlib import Path
from typing import Dict, Generator, List, Optional, Set, Tuple

import typer
from rich.table import Table

from ..comments import merge_comments, normalize_comment
from ..core.ip_counter import count_unique_ips
from ..core.ip_utils import IPNet
from ..core.operations.overlap import (
    build_intersection_fragments,
    classify_overlap_pair,
    find_self_overlaps,
    find_two_list_overlaps,
)
from ..core.operations.sorter import sort_networks
from ..core.pipeline import process_prefixes
from ..data.file_reader import read_networks, read_prefixes_with_comments
from .common import OutputFormat, console, handle_output


def _deduplicate(
    unique_map: Dict[str, str],
    stream: Generator[Tuple[IPNet, str], None, None],
) -> None:
    """Merge a commented stream into ``unique_map`` in place.

    The first non-empty comment wins; later empty comments never overwrite it.
    """
    for ip, comment in stream:
        ip_str = str(ip)
        if ip_str not in unique_map:
            unique_map[ip_str] = comment
        elif not unique_map[ip_str] and comment:
            unique_map[ip_str] = comment


def _validate_comment_options(
    keep_comments: bool,
    append_comment: Optional[str],
    keep_existing_comments: bool,
    fmt: OutputFormat,
) -> None:
    """Reject invalid combinations of merge comment flags."""
    if keep_comments and fmt == OutputFormat.csv:
        console.print(
            "[red]Error: Cannot use --keep-comments with CSV format.[/red]"
        )
        sys.exit(1)
    if keep_existing_comments and not append_comment:
        console.print(
            "[red]Error: --keep-existing-comments requires "
            "--append-comment.[/red]"
        )
        sys.exit(1)
    if append_comment and not keep_comments:
        # Merge historically requires --keep-comments for comment annotation
        # because the flag disables aggregation (which would mix sources).
        console.print(
            "[red]Error: --append-comment requires --keep-comments.[/red]"
        )
        sys.exit(1)


def _render_commented(items: List[Tuple[IPNet, str]]) -> str:
    """Render commented pairs into a newline-terminated text block."""
    lines = []
    for net, comment in items:
        if comment:
            lines.append(f"{net} {comment}")
        else:
            lines.append(str(net))
    return "\n".join(lines) + "\n"


def merge(
    file1: Path = typer.Argument(..., help="First input file with IP prefixes"),
    file2: Path = typer.Argument(..., help="Second input file with IP prefixes"),
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
        help="Preserve comments. Disables aggregation and CSV format.",
    ),
    append_comment: Optional[str] = typer.Option(
        None,
        "--append-comment",
        help="Append this comment to prefixes coming from the first file. "
        "Works only with --keep-comments.",
    ),
    keep_existing_comments: bool = typer.Option(
        False,
        "--keep-existing-comments",
        help="Keep existing comments from the first file and append the new "
        "comment to the end. Requires --append-comment.",
    ),
) -> None:
    """Merge two prefix files into one deduplicated list."""
    try:
        _validate_comment_options(
            keep_comments, append_comment, keep_existing_comments, format
        )

        if keep_comments:
            unique_map: Dict[str, str] = {}
            annotation = normalize_comment(append_comment)

            # Source 2 is the EXISTING (old/base) list; load its prefixes
            # and comments first.
            _deduplicate(unique_map, read_prefixes_with_comments(file2))

            # Source 1 is the INCOMING (new) list. The annotation marks every
            # prefix from this list as "new", including prefixes that already
            # exist in Source 2. For a duplicate, Source 1's contribution is
            # merged with Source 2's existing comment instead of replacing it.
            for ip, comment in read_prefixes_with_comments(file1):
                ip_str = str(ip)

                if annotation:
                    source1_comment = (
                        comment if keep_existing_comments else ""
                    )
                    combined = merge_comments(source1_comment, annotation)
                else:
                    combined = comment

                if ip_str in unique_map:
                    # Prefix exists in both sources.
                    if annotation and not keep_existing_comments:
                        # Replacement mode: Source 1's append comment wins,
                        # replacing Source 2's existing comment.
                        unique_map[ip_str] = combined
                    else:
                        # Keep-existing mode (or no annotation): merge the
                        # comments from both sources.
                        unique_map[ip_str] = merge_comments(
                            unique_map[ip_str], combined
                        )
                else:
                    unique_map[ip_str] = combined

            # Convert dict back to a sorted list of (network, comment).
            merged_list: List[Tuple[IPNet, str]] = []
            for ip_str_key, comm in unique_map.items():
                net_obj = ipaddress.ip_network(ip_str_key, strict=False)
                merged_list.append((net_obj, comm))
            merged_list.sort(
                key=lambda item: (
                    item[0].version,
                    int(item[0].network_address),
                    item[0].prefixlen,
                )
            )

            content = _render_commented(merged_list)
            if output_file:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(content)
                console.print(
                    f"[green]Merged {len(merged_list)} prefixes to "
                    f"{output_file}[/green]"
                )
            else:
                print(content, end="")
        else:
            # Non-comment mode: full optimisation of the combined input.
            prefixes1 = list(read_networks(file1))
            prefixes2 = list(read_networks(file2))
            all_prefixes = prefixes1 + prefixes2
            processed_prefixes = process_prefixes(
                all_prefixes,
                sort=True,
                remove_nested=True,
                aggregate=True,
            )
            handle_output(list(processed_prefixes), format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def intersect(
    files: List[Path] = typer.Argument(
        ...,
        help="Input files (1, 2 or more). 1=self-check, 2=coverage, "
        "3+=matrix (>=2 sources)",
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
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Fail on invalid network addresses with host bits set.",
    ),
) -> None:
    """Find intersections between prefix lists."""
    try:
        all_lists = []
        names = []
        for f in files:
            lst = list(read_networks(f, strict=strict))
            all_lists.append(lst)
            names.append(f.name)

        num_files = len(files)

        # ---- 1 file: self-check (internal overlaps) ----
        if num_files == 1:
            sole_list = all_lists[0]
            sole_name = names[0]
            volume = count_unique_ips(sole_list)
            sorted_lst = sort_networks(sole_list)
            raw_overlaps = find_self_overlaps(sorted_lst)

            partial_overlaps = []
            for net1, net2 in raw_overlaps:
                _, subnet, supernet, src_sub, src_super = classify_overlap_pair(
                    net1, net2, sole_name, sole_name
                )
                partial_overlaps.append(
                    (subnet, supernet, src_sub, src_super)
                )

            console.print(
                "\n[bold underline]Self-Intersection Report[/bold underline]"
            )
            console.print(f"File: [cyan]{sole_name}[/cyan]")
            console.print(f"Total prefixes: {len(sole_list)}")
            console.print(f"Unique IPs: {volume:,}")
            console.print("")
            if partial_overlaps:
                console.print(
                    f"[bold yellow]=== Internal Overlaps "
                    f"({len(partial_overlaps)}) ===[/bold yellow]"
                )
                partial_overlaps.sort(
                    key=lambda x: (x[0].version, int(x[0].network_address))
                )
                for sub, parent, _, _ in partial_overlaps:
                    console.print(
                        f"  [yellow]{sub}[/yellow] [dim]is inside[/dim] "
                        f"[yellow]{parent}[/yellow]"
                    )
            else:
                console.print(
                    "[bold green][OK] No internal overlaps found. "
                    "List is clean.[/bold green]"
                )

            all_results = set()
            for sub, parent, _, _ in partial_overlaps:
                all_results.update([sub, parent])
            if all_results:
                handle_output(
                    sort_networks(list(all_results)), format, output_file
                )
            return

        # ---- 2 files: side-by-side comparison ----
        if num_files == 2:
            list1 = all_lists[0]
            list2 = all_lists[1]
            name1, name2 = names[0], names[1]
            volume1 = count_unique_ips(list1)
            volume2 = count_unique_ips(list2)
            set1 = set(list1)
            set2 = set(list2)
            common = set1.intersection(set2)
            sorted1 = sort_networks(list1)
            sorted2 = sort_networks(list2)
            raw_overlaps = find_two_list_overlaps(sorted1, sorted2)

            partial_overlaps: List[Tuple[IPNet, IPNet, str, str]] = []
            for net1, net2 in raw_overlaps:
                _, subnet, supernet, src_sub, src_super = classify_overlap_pair(
                    net1, net2, name1, name2
                )
                partial_overlaps.append(
                    (subnet, supernet, src_sub, src_super)
                )

            intersection_fragments = build_intersection_fragments(
                common, raw_overlaps
            )
            volume_intersection = (
                count_unique_ips(intersection_fragments)
                if intersection_fragments
                else 0
            )
            cov1 = (
                volume_intersection / volume1 * 100 if volume1 > 0 else 0.0
            )
            cov2 = (
                volume_intersection / volume2 * 100 if volume2 > 0 else 0.0
            )

            console.print(
                "\n[bold underline]Intersection Report[/bold underline]"
            )
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Metric")
            table.add_column(name1, justify="right")
            table.add_column(name2, justify="right")
            table.add_column(
                "Intersection", justify="right", style="green"
            )
            table.add_row(
                "Unique IPs",
                f"{volume1:,}",
                f"{volume2:,}",
                f"{volume_intersection:,}",
            )
            table.add_row(
                "Coverage", f"{cov1:.2f}%", f"{cov2:.2f}%", ""
            )
            console.print(table)
            console.print("")

            if common:
                console.print(
                    f"[bold green]=== Exact Matches "
                    f"({len(common)}) ===[/bold green]"
                )
                for prefix in sort_networks(common):
                    console.print(f"  [green]= {prefix}[/green]")
            else:
                console.print("[dim]No exact matches found.[/dim]")
            if partial_overlaps:
                console.print(
                    f"\n[bold yellow]=== Partial Overlaps "
                    f"({len(partial_overlaps)}) ===[/bold yellow]"
                )
                partial_overlaps.sort(
                    key=lambda x: (x[0].version, int(x[0].network_address))
                )
                for sub, parent, sub_src, parent_src in partial_overlaps:
                    sub_color = "cyan" if sub_src == name1 else "magenta"
                    parent_color = (
                        "cyan" if parent_src == name1 else "magenta"
                    )
                    console.print(
                        f"  [{sub_color}]{sub}[/{sub_color}] ({sub_src}) "
                        f"[dim]is inside[/dim] "
                        f"[{parent_color}]{parent}[/{parent_color}] "
                        f"({parent_src})"
                    )

            all_results = list(common)
            for sub, parent, _, _ in partial_overlaps:
                all_results.extend([sub, parent])
            all_results = sort_networks(list(set(all_results)))
            if all_results:
                handle_output(all_results, format, output_file)
            return

        # ---- 3+ files: presence matrix + pairwise overlaps ----
        optimized_lists = []
        for lst in all_lists:
            opt = list(
                process_prefixes(
                    lst,
                    sort=True,
                    remove_nested=True,
                    aggregate=True,
                )
            )
            optimized_lists.append(opt)

        sets = [set(lst) for lst in optimized_lists]
        union = set()
        for s in sets:
            union.update(s)

        # Map each prefix to the indices of sources that contain it.
        presence_map: Dict[str, List[int]] = {}
        for net in union:
            str_net = str(net)
            presence_map[str_net] = [
                idx for idx in range(num_files) if net in sets[idx]
            ]

        filtered = {
            net
            for net, indices in presence_map.items()
            if len(indices) >= 2
        }
        common_prefixes = [
            ipaddress.ip_network(ns, strict=False) for ns in filtered
        ]
        common_prefixes = sort_networks(common_prefixes)

        console.print(
            "\n[bold underline]Multi-Intersection Report[/bold underline]"
        )
        console.print(f"Sources: {', '.join(names)}")
        console.print(
            f"Prefixes appearing in at least 2 sources: "
            f"{len(common_prefixes)}"
        )
        if common_prefixes:
            table = Table(
                title="Presence Matrix (≥2 sources)",
                show_header=True,
                header_style="bold cyan",
            )
            table.add_column("Prefix", style="green")
            for idx in range(num_files):
                table.add_column(names[idx], justify="center")
            for net in common_prefixes:
                row = [str(net)]
                for idx in range(num_files):
                    row.append(
                        "Y" if idx in presence_map[str(net)] else "N"
                    )
                table.add_row(*row)
            console.print(table)
        else:
            console.print(
                "[yellow]No prefixes appear in at least 2 sources.[/yellow]"
            )

        # Output set: every prefix shared by any pair of sources.
        out_set = set(common_prefixes)
        for i in range(num_files):
            for j in range(i + 1, num_files):
                out_set.update(sets[i] & sets[j])
        if out_set:
            handle_output(
                sort_networks(list(out_set)), format, output_file
            )

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
