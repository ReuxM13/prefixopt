"""
Модуль команд слияния и пересечения для CLI.

Содержит две команды:

1. merge
   Объединение нескольких списков префиксов в один.
   Поддерживает сохранение комментариев и аннотацию источников.

2. intersect
   Поиск пересечений между файлами:
   - 1 файл   — self‑check (внутренние перекрытия).
   - 2 файла  — сравнение двух файлов (точные совпадения, coverage, частичные перекрытия).
   - 3+ файлов — матрица присутствия для префиксов,
     попарные точные совпадения и частичные перекрытия между всеми парами.
"""
import sys
import ipaddress
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Generator, Set

import typer
from rich.table import Table

from .common import OutputFormat, handle_output, console
from ..data.file_reader import read_networks, read_prefixes_with_comments
from ..core.pipeline import process_prefixes
from ..core.operations.sorter import sort_networks
from ..core.ip_utils import IPNet
from ..core.ip_counter import count_unique_ips
from ..core.operations.overlap import find_two_list_overlaps, find_self_overlaps, classify_overlap_pair, build_intersection_fragments


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================

def _split_comment_parts(comment: str) -> List[str]:
    if not comment:
        return []
    raw = comment.strip()
    if raw.startswith("#"):
        raw = raw[1:].strip()
    if not raw:
        return []
    parts = [part.strip() for part in raw.split("|")]
    return [part for part in parts if part]


def _merge_comment_strings(*comments: str) -> str:
    merged_parts: List[str] = []
    seen: Set[str] = set()
    for comment in comments:
        for part in _split_comment_parts(comment):
            if part not in seen:
                seen.add(part)
                merged_parts.append(part)
    if not merged_parts:
        return ""
    return f"# {' | '.join(merged_parts)}"


def _comment_from_text(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if not cleaned:
        return ""
    return f"# {cleaned}"


def merge(
    file1: Path = typer.Argument(..., help="First input file with IP prefixes"),
    file2: Path = typer.Argument(..., help="Second input file with IP prefixes"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    ),
    keep_comments: bool = typer.Option(
        False,
        "--keep-comments",
        help="Preserve comments. Disables aggregation and CSV format."
    ),
    append_comment: Optional[str] = typer.Option(
        None,
        "--append-comment",
        help="Append this comment to prefixes coming from the first file. Works only with --keep-comments."
    )
) -> None:
    """Объединение двух файлов."""
    try:
        if keep_comments and format == OutputFormat.csv:
            console.print("[red]Error: Cannot use --keep-comments with CSV format.[/red]")
            sys.exit(1)

        if append_comment and not keep_comments:
            console.print("[red]Error: --append-comment works only with --keep-comments.[/red]")
            sys.exit(1)

        if keep_comments:
            unique_map: Dict[str, str] = {}
            if append_comment:
                annotation_comment = _comment_from_text(append_comment)
                for ip, comment in read_prefixes_with_comments(file2):
                    ip_str = str(ip)
                    if ip_str not in unique_map:
                        unique_map[ip_str] = comment
                    else:
                        unique_map[ip_str] = _merge_comment_strings(unique_map[ip_str], comment)
                for ip, comment in read_prefixes_with_comments(file1):
                    ip_str = str(ip)
                    merged_comment = _merge_comment_strings(comment, annotation_comment)
                    if ip_str in unique_map:
                        unique_map[ip_str] = _merge_comment_strings(unique_map[ip_str], merged_comment)
                    else:
                        unique_map[ip_str] = merged_comment
            else:
                def process_stream(stream: Generator[Tuple[IPNet, str], None, None]) -> None:
                    for ip, comment in stream:
                        ip_str = str(ip)
                        if ip_str not in unique_map:
                            unique_map[ip_str] = comment
                        else:
                            if not unique_map[ip_str] and comment:
                                unique_map[ip_str] = comment
                process_stream(read_prefixes_with_comments(file1))
                process_stream(read_prefixes_with_comments(file2))

            merged_list: List[Tuple[IPNet, str]] = []
            for ip_str_key, comm in unique_map.items():
                net_obj = ipaddress.ip_network(ip_str_key, strict=False)
                merged_list.append((net_obj, comm))
            merged_list.sort(key=lambda item: (item[0].version, int(item[0].network_address), item[0].prefixlen))

            lines = []
            for ip_obj, comment in merged_list:
                if comment:
                    lines.append(f"{ip_obj} {comment}")
                else:
                    lines.append(str(ip_obj))
            content = "\n".join(lines) + "\n"

            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                console.print(f"[green]Merged {len(lines)} prefixes to {output_file}[/green]")
            else:
                print(content, end="")
        else:
            prefixes1 = list(read_networks(file1))
            prefixes2 = list(read_networks(file2))
            all_prefixes = prefixes1 + prefixes2
            processed_prefixes = process_prefixes(all_prefixes, sort=True, remove_nested=True, aggregate=True)
            handle_output(list(processed_prefixes), format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


# ===================== INTERSECT =====================

def intersect(
    files: List[Path] = typer.Argument(..., help="Input files (1, 2 or more). 1=self‑check, 2=coverage, 3+=matrix (≥2 sources)"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Fail on invalid network addresses with host bits set."
    ),
) -> None:
    """
    Finds intersections between prefix lists.

    - 1 file   → self‑check (internal overlaps).
    - 2 files  → side‑by‑side comparison with coverage and partial overlaps.
    - 3+ files → presence matrix (prefixes in ≥2 sources) and pairwise exact matches & partial overlaps.
    """
    try:
        all_lists = []
        names = []
        for f in files:
            lst = list(read_networks(f, strict=strict))
            all_lists.append(lst)
            names.append(f.name)

        num_files = len(files)

        # ---------- 1 файл (self‑check) ----------
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
                partial_overlaps.append((subnet, supernet, src_sub, src_super))

            console.print(f"\n[bold underline]Self-Intersection Report[/bold underline]")
            console.print(f"File: [cyan]{sole_name}[/cyan]")
            console.print(f"Total prefixes: {len(sole_list)}")
            console.print(f"Unique IPs: {volume:,}")
            console.print("")
            if partial_overlaps:
                console.print(f"[bold yellow]=== Internal Overlaps ({len(partial_overlaps)}) ===[/bold yellow]")
                partial_overlaps.sort(key=lambda x: (x[0].version, int(x[0].network_address)))
                for sub, parent, _, _ in partial_overlaps:
                    console.print(f"  [yellow]{sub}[/yellow] [dim]is inside[/dim] [yellow]{parent}[/yellow]")
            else:
                console.print("[bold green][OK] No internal overlaps found. List is clean.[/bold green]")

            all_results = set()
            for sub, parent, _, _ in partial_overlaps:
                all_results.update([sub, parent])
            if all_results:
                handle_output(sort_networks(list(all_results)), format, output_file)
            return

        # ---------- 2 файла (сравнение) ----------
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
                partial_overlaps.append((subnet, supernet, src_sub, src_super))

            intersection_fragments: List[IPNet] = build_intersection_fragments(common, raw_overlaps)

            volume_intersection = count_unique_ips(intersection_fragments) if intersection_fragments else 0
            cov1 = (volume_intersection / volume1 * 100) if volume1 > 0 else 0.0
            cov2 = (volume_intersection / volume2 * 100) if volume2 > 0 else 0.0

            console.print(f"\n[bold underline]Intersection Report[/bold underline]")
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Metric")
            table.add_column(name1, justify="right")
            table.add_column(name2, justify="right")
            table.add_column("Intersection", justify="right", style="green")
            table.add_row("Unique IPs", f"{volume1:,}", f"{volume2:,}", f"{volume_intersection:,}")
            table.add_row("Coverage", f"{cov1:.2f}%", f"{cov2:.2f}%", "")
            console.print(table)
            console.print("")
            if volume1 > 0:
                if volume_intersection == volume1:
                    console.print(f"[bold green][OK] All unique IPs from {name1} are present in {name2}[/bold green]")
                else:
                    console.print(f"[yellow][!] Only {cov1:.2f}% of {name1} is covered by {name2}[/yellow]")
            if volume2 > 0:
                if volume_intersection == volume2:
                    console.print(f"[bold green][OK] All unique IPs from {name2} are present in {name1}[/bold green]")
            console.print("")
            if common:
                console.print(f"[bold green]=== Exact Matches ({len(common)}) ===[/bold green]")
                for prefix in sort_networks(common):
                    console.print(f"  [green]= {prefix}[/green]")
            else:
                console.print("[dim]No exact matches found.[/dim]")
            if partial_overlaps:
                console.print(f"\n[bold yellow]=== Partial Overlaps ({len(partial_overlaps)}) ===[/bold yellow]")
                partial_overlaps.sort(key=lambda x: (x[0].version, int(x[0].network_address)))
                for sub, parent, sub_src, parent_src in partial_overlaps:
                    sub_color = "cyan" if sub_src == name1 else "magenta"
                    parent_color = "cyan" if parent_src == name1 else "magenta"
                    console.print(
                        f"  [{sub_color}]{sub}[/{sub_color}] ({sub_src}) "
                        f"[dim]is inside[/dim] "
                        f"[{parent_color}]{parent}[/{parent_color}] ({parent_src})"
                    )
            else:
                console.print("\n[dim]No partial overlaps found.[/dim]")

            all_results = list(common)
            for sub, parent, _, _ in partial_overlaps:
                all_results.extend([sub, parent])
            all_results = sort_networks(list(set(all_results)))
            if all_results:
                handle_output(all_results, format, output_file)
            return

        # ---------- 3+ файлов ----------
        optimized_lists = []
        volumes = []
        for lst in all_lists:
            opt = list(process_prefixes(lst, sort=True, remove_nested=True, aggregate=True))
            optimized_lists.append(opt)
            volumes.append(count_unique_ips(opt))

        sets = [set(lst) for lst in optimized_lists]
        union = set()
        for s in sets:
            union.update(s)

        # Карта присутствия для всех префиксов
        presence_map: Dict[str, List[int]] = {}
        for net in union:
            str_net = str(net)
            presence_map[str_net] = [idx for idx in range(num_files) if net in sets[idx]]

        # Фильтр: ≥2 источников
        filtered = {net for net, indices in presence_map.items() if len(indices) >= 2}
        common_prefixes = [ipaddress.ip_network(ns, strict=False) for ns in filtered]
        common_prefixes = sort_networks(common_prefixes)

        intersection_volume = count_unique_ips(common_prefixes) if common_prefixes else 0

        console.print(f"\n[bold underline]Multi-Intersection Report[/bold underline]")
        console.print(f"Sources: {', '.join(names)}")
        console.print(f"Prefixes appearing in at least 2 sources: {len(common_prefixes)}")
        if common_prefixes:
            console.print(f"Total unique IPs in shown prefixes: {intersection_volume:,}")
            table = Table(title="Presence Matrix (≥2 sources)", show_header=True, header_style="bold cyan")
            table.add_column("Prefix", style="green")
            for idx in range(num_files):
                table.add_column(names[idx], justify="center")
            for net in common_prefixes:
                str_net = str(net)
                row = [str_net]
                for idx in range(num_files):
                    row.append("Y" if idx in presence_map[str_net] else "N")
                table.add_row(*row)
            console.print(table)
        else:
            console.print("[yellow]No prefixes appear in at least 2 sources.[/yellow]")

        # Попарные точные совпадения
        console.print("\n[bold green]Pairwise Exact Matches[/bold green]")
        found_any_exact = False
        sorted_opt_lists = [sort_networks(lst) for lst in optimized_lists]
        for i in range(num_files):
            for j in range(i + 1, num_files):
                # Пересечение множеств после оптимизации (без дубликатов)
                exact = sets[i] & sets[j]
                if exact:
                    found_any_exact = True
                    console.print(f"  Between {names[i]} and {names[j]}: {len(exact)} prefixes")
                    for net in sort_networks(list(exact)):
                        console.print(f"    = {net}")
        if not found_any_exact:
            console.print("[dim]No exact matches between any pair of sources.[/dim]")

        # Попарные частичные перекрытия
        all_pairs_partial: List[Tuple[IPNet, IPNet, str, str]] = []
        for i in range(num_files):
            for j in range(i + 1, num_files):
                raw = find_two_list_overlaps(sorted_opt_lists[i], sorted_opt_lists[j])
                for net1, net2 in raw:
                    _, subnet, supernet, src_sub, src_super = classify_overlap_pair(
                        net1, net2, names[i], names[j]
                    )
                    all_pairs_partial.append((subnet, supernet, src_sub, src_super))

        if all_pairs_partial:
            all_pairs_partial.sort(key=lambda x: (x[0].version, int(x[0].network_address)))
            console.print(f"\n[bold yellow]=== Partial Overlaps ({len(all_pairs_partial)}) ===[/bold yellow]")
            for sub, parent, sub_src, parent_src in all_pairs_partial:
                sub_color = "cyan" if sub_src == names[0] else "magenta"
                parent_color = "cyan" if parent_src == names[0] else "magenta"
                console.print(
                    f"  [{sub_color}]{sub}[/{sub_color}] ({sub_src}) "
                    f"[dim]is inside[/dim] "
                    f"[{parent_color}]{parent}[/{parent_color}] ({parent_src})"
                )
        else:
            console.print("\n[dim]No partial overlaps found between any pair of sources.[/dim]")

        # Выходной список: общие префиксы + все exact + все partial
        out_set = set(common_prefixes)
        for i in range(num_files):
            for j in range(i + 1, num_files):
                out_set.update(sets[i] & sets[j])           # добавляем точные совпадения
                # частичные перекрытия уже были бы добавлены выше?
                # Добавим все фигурирующие сети из partial overlaps
                for sub, parent, _, _ in all_pairs_partial:
                    out_set.update([sub, parent])
        if out_set:
            handle_output(sort_networks(list(out_set)), format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)