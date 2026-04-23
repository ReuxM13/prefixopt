"""
Модуль команд слияния и пересечения для CLI.

Предоставляет функциональность для объединения (merge) нескольких списков
префиксов с опциональным сохранением комментариев, а также для поиска
пересечений (intersect) и перекрытий между двумя списками.
"""
import sys
import ipaddress
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Generator
from rich.table import Table

import typer

# Локальные импорты
from .common import OutputFormat, handle_output, console
from ..data.file_reader import read_networks, read_prefixes_with_comments
from ..core.pipeline import process_prefixes
from ..core.operations.sorter import sort_networks
from ..core.ip_utils import IPNet
from ..core.ip_counter import count_unique_ips


def merge(
    file1: Path = typer.Argument(..., help="First input file with IP prefixes"),
    file2: Path = typer.Argument(..., help="Second input file with IP prefixes"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    ),
    keep_comments: bool = typer.Option(False, "--keep-comments", help="Preserve comments. Disables aggregation and CSV format."),
    strict: bool = typer.Option(
    False,
    "--strict",
    help="Fail on invalid network addresses with host bits set instead of auto-correcting them."
    )
) -> None:
    """
    Combines two files with IP prefixes.

    Команда поддерживает два режима работы:
    1. Стандартный (Оптимизация): Списки загружаются, объединяются, сортируются,
       очищаются от вложенностей и агрегируются.
    2. Режим --keep-comments: Используется для слияния списков "белого доступа"
       или конфигов с комментариями.
       - Агрегация и удаление вложенных сетей ОТКЛЮЧАЮТСЯ (чтобы не потерять
         привязку комментария к конкретной подсети).
       - Выполняется дедупликация (удаление полных дублей IP).
       - Используется потоковая обработка для экономии памяти.
    """
    try:
        # Проверка на конфликт: CSV не поддерживает комментарии
        if keep_comments and format == OutputFormat.csv:
            console.print("[red]Error: Cannot use --keep-comments with CSV format.[/red]")
            sys.exit(1)

        if keep_comments:        
            # Словарь для дедупликации: ключ - строковый IP, значение - комментарий.
            unique_map: Dict[str, str] = {}
            
            # Вспомогательная функция для обработки потока
            def process_stream(stream: Generator[Tuple[IPNet, str], None, None]) -> None:
                for ip, comment in stream:
                    ip_str = str(ip)
                    if ip_str not in unique_map:
                        unique_map[ip_str] = comment
                    else:
                        # Если у существующего нет коммента, а у нового есть - обновляем
                        if not unique_map[ip_str] and comment:
                            unique_map[ip_str] = comment

            # 1. Читаем первый файл прямо в словарь (минуя создание огромных списков)
            process_stream(read_prefixes_with_comments(file1, strict=strict))

            # 2. Читаем второй файл прямо в словарь
            process_stream(read_prefixes_with_comments(file2, strict=strict))

            # Восстанавливаем объекты IP для корректной сортировки
            merged_list: List[Tuple[IPNet, str]] = []
            for ip_str_key, comm in unique_map.items():
                net_obj = ipaddress.ip_network(ip_str_key, strict=False)
                merged_list.append((net_obj, comm))

            # Сортировка Broadest First (аналогично ядру)
            # Ключ: (Версия, Адрес, Маска)
            merged_list.sort(key=lambda item: (
                item[0].version,
                int(item[0].network_address),
                item[0].prefixlen
            ))

            # Формирование текстового вывода
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
                console.print(f"[green]Merged {len(lines)} prefixes (with comments) to {output_file}[/green]")
            else:
                print(content, end="")

        else:
            # Используем list() для загрузки генераторов в память, чтобы объединить их
            prefixes1 = list(read_networks(file1, strict=strict))
            prefixes2 = list(read_networks(file2, strict=strict))
            all_prefixes = prefixes1 + prefixes2

            # Запускаем полный цикл оптимизации через Pipeline
            processed_prefixes = process_prefixes(
                all_prefixes,
                sort=True,           # Всегда сортируем при слиянии
                remove_nested=True,  # Чистим вложенность
                aggregate=True       # Склеиваем соседей
            )

            # Материализуем результат
            processed_list = list(processed_prefixes)

            # Передаем результат в обработчик вывода
            handle_output(processed_list, format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def _find_overlaps_linear(
    sorted_list1: List[IPNet],
    sorted_list2: List[IPNet]
) -> List[Tuple[IPNet, IPNet]]:
    """
    Ищет пересечения между двумя уже отсортированными списками сетей.

    Функция используется в режиме сравнения двух разных файлов.
    Возвращает пары сетей, которые пересекаются между собой.

    Args:
        sorted_list1: Первый отсортированный список сетей.
        sorted_list2: Второй отсортированный список сетей.

    Returns:
        Список пар (net_from_list1, net_from_list2), которые пересекаются.
    """
    overlaps: List[Tuple[IPNet, IPNet]] = []

    i = 0
    j = 0
    len1 = len(sorted_list1)
    len2 = len(sorted_list2)

    while i < len1 and j < len2:
        net1 = sorted_list1[i]
        net2 = sorted_list2[j]

        if net1.version < net2.version:
            i += 1
            continue
        if net1.version > net2.version:
            j += 1
            continue

        start1 = int(net1.network_address)
        end1 = int(net1.broadcast_address)
        start2 = int(net2.network_address)
        end2 = int(net2.broadcast_address)

        if max(start1, start2) <= min(end1, end2):
            overlaps.append((net1, net2))

            if end1 < end2:
                i += 1
            elif end2 < end1:
                j += 1
            else:
                i += 1
                j += 1
        elif end1 < start2:
            i += 1
        else:
            j += 1

    return overlaps


def _find_self_overlaps(sorted_list: List[IPNet]) -> List[Tuple[IPNet, IPNet]]:
    """
    Ищет пересечения внутри одного отсортированного списка сетей.

    Используется в режиме самопроверки, когда команда intersect вызвана
    только с одним файлом.

    Args:
        sorted_list: Отсортированный список сетей.

    Returns:
        Список пар сетей из одного и того же списка, которые пересекаются.
    """
    overlaps: List[Tuple[IPNet, IPNet]] = []
    length = len(sorted_list)

    for i in range(length):
        net_i = sorted_list[i]
        end_i = int(net_i.broadcast_address)

        for j in range(i + 1, length):
            net_j = sorted_list[j]

            if net_i.version != net_j.version:
                break

            start_j = int(net_j.network_address)

            if start_j > end_i:
                break

            overlaps.append((net_i, net_j))

    return overlaps


def intersect(
    file1: Path = typer.Argument(..., help="First input file (Source A)"),
    file2: Optional[Path] = typer.Argument(None, help="Second input file (Source B). If omitted, checks file1 against itself."),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    ),
    strict: bool = typer.Option(False, "--strict", help="Fail on invalid network addresses with host bits set.")
) -> None:
    """
    Finds intersections and calculates coverage ratio.
    If only one file is given, checks for internal overlaps within that file.
    """
    try:
        list1 = list(read_networks(file1, strict=strict))
        name1 = file1.name

        # Определяем режим работы
        self_mode = file2 is None

        if self_mode:
            list2 = list1
            name2 = name1
        else:
            list2 = list(read_networks(file2, strict=strict))
            name2 = file2.name

        with console.status("[bold green]Calculating volumes...", spinner="dots"):
            volume1 = count_unique_ips(list1)
            if self_mode:
                volume2 = volume1
            else:
                volume2 = count_unique_ips(list2)

        set1 = set(list1)
        set2 = set(list2)

        sorted1 = sort_networks(list1)

        if self_mode:
            # Режим самопроверки: ищем пересечения внутри одного списка
            common_prefixes = set()  # В self-mode точных "совпадений" не ищем (всё совпадет)
            raw_overlaps = _find_self_overlaps(sorted1)
        else:
            # Стандартный режим: два файла
            common_prefixes = set1.intersection(set2)
            sorted2 = sort_networks(list2)
            raw_overlaps = _find_overlaps_linear(sorted1, sorted2)

        # Формируем список частичных перекрытий
        partial_overlaps: List[Tuple[IPNet, IPNet, str, str]] = []

        for net1, net2 in raw_overlaps:
            if net1 == net2:
                continue

            if net1.subnet_of(net2):  # type: ignore
                partial_overlaps.append((net1, net2, name1, name2 if not self_mode else name1))
            elif net2.subnet_of(net1):  # type: ignore
                partial_overlaps.append((net2, net1, name2 if not self_mode else name1, name1))
            else:
                partial_overlaps.append((net1, net2, name1, name2 if not self_mode else name1))

        # Подсчет объема пересечений
        intersection_fragments: List[IPNet] = list(common_prefixes)

        for net1, net2 in raw_overlaps:
            if net1 == net2:
                continue
            if net1.subnet_of(net2):  # type: ignore
                intersection_fragments.append(net1)
            elif net2.subnet_of(net1):  # type: ignore
                intersection_fragments.append(net2)

        volume_intersection = count_unique_ips(intersection_fragments) if intersection_fragments else 0

        # Вывод результатов
        should_print_details = output_file is not None or format == OutputFormat.list

        if should_print_details:
            if self_mode:
                console.print(f"\n[bold underline]Self-Intersection Report[/bold underline]")
                console.print(f"File: [cyan]{name1}[/cyan]")
                console.print(f"Total prefixes: {len(list1)}")
                console.print(f"Unique IPs: {volume1:,}")
                console.print("")

                if partial_overlaps:
                    console.print(f"[bold yellow]=== Internal Overlaps ({len(partial_overlaps)}) ===[/bold yellow]")
                    partial_overlaps.sort(key=lambda x: (x[0].version, int(x[0].network_address)))

                    for sub, parent, _, _ in partial_overlaps:
                        console.print(
                            f"  [yellow]{sub}[/yellow] "
                            f"[dim]is inside[/dim] "
                            f"[yellow]{parent}[/yellow]"
                        )
                else:
                    console.print("[bold green][OK] No internal overlaps found. List is clean.[/bold green]")

            else:
                console.print(f"\n[bold underline]Intersection Report[/bold underline]")

                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Metric")
                table.add_column(name1, justify="right")
                table.add_column(name2, justify="right")
                table.add_column("Intersection", justify="right", style="green")

                cov1 = (volume_intersection / volume1 * 100) if volume1 > 0 else 0
                cov2 = (volume_intersection / volume2 * 100) if volume2 > 0 else 0

                table.add_row("Unique IPs", f"{volume1:,}", f"{volume2:,}", f"{volume_intersection:,}")
                table.add_row("Coverage", f"{cov1:.2f}%", f"{cov2:.2f}%", "")

                console.print(table)
                console.print("")

                if volume1 > 0:
                    if volume_intersection == volume1:
                        console.print(f"[bold green][OK] All unique IPs from {name1} are present in {name2}[/bold green]")
                    else:
                        missing_count = volume1 - volume_intersection
                        console.print(f"[yellow][!] Only {cov1:.2f}% of {name1} is covered by {name2}[/yellow]")
                        console.print(f"    (Missing {missing_count:,} IPs from {name1})")

                if volume2 > 0:
                    if volume_intersection == volume2:
                        console.print(f"[bold green][OK] All unique IPs from {name2} are present in {name1}[/bold green]")

                console.print("")

                if common_prefixes:
                    console.print(f"[bold green]=== Exact Matches ({len(common_prefixes)}) ===[/bold green]")
                    for prefix in sort_networks(common_prefixes):
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

        # Формирование выходного списка
        all_results = list(common_prefixes)
        for sub, parent, _, _ in partial_overlaps:
            all_results.extend([sub, parent])

        all_results = list(set(all_results))
        all_results = sort_networks(all_results)

        if not all_results and should_print_details:
            if not self_mode:
                console.print("\n[bold red]No intersections found anywhere.[/bold red]")
            return

        if all_results:
            handle_output(all_results, format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)