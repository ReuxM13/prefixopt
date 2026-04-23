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
    Линейный алгоритм поиска пересечений для отсортированных списков.
    Сложность O(N + M) в среднем случае.
    
    Возвращает список пар (Сеть из List1, Сеть из List2), которые пересекаются.
    """
    overlaps = []
    
    # Индексы для прохода по спискам
    i, j = 0, 0
    len1, len2 = len(sorted_list1), len(sorted_list2)
    
    while i < len1 and j < len2:
        net1 = sorted_list1[i]
        net2 = sorted_list2[j]
        
        # 1. Проверка версий (IPv4 vs IPv6)
        if net1.version < net2.version:
            i += 1
            continue
        if net1.version > net2.version:
            j += 1
            continue
            
        # Версии совпадают. Сравниваем диапазоны.
        # Используем числовое представление (int) для скорости.
        start1, end1 = int(net1.network_address), int(net1.broadcast_address)
        start2, end2 = int(net2.network_address), int(net2.broadcast_address)
        
        # 2. Проверка на пересечение интервалов [start, end]
        # Интервалы пересекаются, если max(start1, start2) <= min(end1, end2)
        if max(start1, start2) <= min(end1, end2):
            # Нашли пересечение!
            overlaps.append((net1, net2))
            
            # Одна широкая сеть может пересекаться с несколькими узкими.
            # Нужно продвинуть тот указатель, чей интервал заканчивается раньше,
            # чтобы найти все возможные пересечения.
            
            # Если net1 шире net2 (накрывает её), то net1 может накрыть и следующую net2[j+1].
            # Поэтому двигаем J. Если net2 шире net1, то двигаем I.
            if end1 < end2:
                i += 1
            elif end2 < end1:
                j += 1
            else:
                # Если концы совпадают, двигаем оба (или любой), чтобы избежать зацикливания
                i += 1
                j += 1
        
        # 3. Если пересечения нет, двигаем тот, который левее (меньше)
        elif end1 < start2:
            i += 1
        else:
            j += 1
            
    return overlaps


def intersect(
    file1: Path = typer.Argument(..., help="First input file"),
    file2: Path = typer.Argument(..., help="Second input file"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    ),
    strict: bool = typer.Option(
    False,
    "--strict",
    help="Fail on invalid network addresses with host bits set instead of auto-correcting them."
    )
) -> None:
    """
    Finds intersections between two files.

    Определяет:
    1. Common prefixes: Точные совпадения сетей (через Set Intersection).
    2. Overlapping networks: Сети, которые пересекаются или вложены, но не равны.
       Использует оптимизированный алгоритм O(N+M) с предварительной сортировкой.
    """
    try:
        # 1. Загрузка данных
        list1 = list(read_networks(file1, strict=strict))
        list2 = list(read_networks(file2, strict=strict))
        
        name1 = file1.name
        name2 = file2.name

        # 2. Подсчет объема исходных данных (Уникальные IP)
        # Это может занять время для больших файлов, но это необходимо для честной статистики
        with console.status("[bold green]Calculating volumes...", spinner="dots"):
            volume1 = count_unique_ips(list1)
            volume2 = count_unique_ips(list2)

        # 3. Поиск пересечений
        set1 = set(list1)
        set2 = set(list2)
        common_prefixes = set1.intersection(set2)

        sorted1 = sort_networks(list1)
        sorted2 = sort_networks(list2)
        
        raw_overlaps = _find_overlaps_linear(sorted1, sorted2)
        
        partial_overlaps: List[Tuple[IPNet, IPNet, str, str]] = []
        
        for net1, net2 in raw_overlaps:
            if net1 == net2:
                continue
            
            if net1.subnet_of(net2): # type: ignore
                partial_overlaps.append((net1, net2, name1, name2))
            elif net2.subnet_of(net1): # type: ignore
                partial_overlaps.append((net2, net1, name2, name1))
            else:
                partial_overlaps.append((net1, net2, name1, name2))

        # 4. Формирование списка всех пересечений для подсчета объема
        # В этот список мы кладем МЕНЬШУЮ часть каждого пересечения.
        # - Если точное совпадение: берем любую.
        # - Если A внутри B: берем A.
        # - Если частичное пересечение: это сложнее, но наш алгоритм 
        #   subtractor может вычислить точную геометрию. 
        #   Для простоты и скорости мы возьмем объединение всех вложенных частей.
        
        intersection_fragments: List[IPNet] = list(common_prefixes)
        
        for net1, net2 in raw_overlaps:
            if net1 == net2: continue
            
            # Добавляем в список фрагментов ту сеть, которая МЕНЬШЕ (или пересечение)
            # В простейшем случае overlaps (без subnet_of) мы не можем точно сказать,
            # поэтому (для безопасности статистики) пока считаем только явные вложения.
            # Для точной математики нужно было бы делать (net1 & net2), чего ipaddress не умеет напрямую.
            # Но так как мы работаем с CIDR, 99% случаев это вложенность.
            
            if net1.subnet_of(net2): # type: ignore
                intersection_fragments.append(net1)
            elif net2.subnet_of(net1): # type: ignore
                intersection_fragments.append(net2)
            # Игнорируем сложные частичные перекрытия для статистики, чтобы не замедлять код
        
        # Считаем объем пересечения
        # Обязательно делаем count_unique_ips, чтобы убрать дубли (если одна сеть пересеклась с двумя)
        volume_intersection = count_unique_ips(intersection_fragments)


        # Вывод результатов
        should_print_details = output_file is not None or format == OutputFormat.list

        if should_print_details:
            console.print(f"\n[bold underline]Intersection Report[/bold underline]")
            
            # Таблица статистики
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Metric")
            table.add_column(name1, justify="right")
            table.add_column(name2, justify="right")
            table.add_column("Intersection", justify="right", style="green")

            # Форматирование процентов
            cov1 = (volume_intersection / volume1 * 100) if volume1 > 0 else 0
            cov2 = (volume_intersection / volume2 * 100) if volume2 > 0 else 0

            table.add_row("Unique IPs", f"{volume1:,}", f"{volume2:,}", f"{volume_intersection:,}")
            table.add_row("Coverage", f"{cov1:.2f}%", f"{cov2:.2f}%", "")
            
            console.print(table)
            console.print("") # Empty line

            # Проверка полного вхождения
            if volume1 > 0:
                if volume_intersection == volume1:
                    console.print(f"[bold green][OK] All unique IPs from {name1} are present in {name2}[/bold green]")
                else:
                    missing_count = volume1 - volume_intersection
                    console.print(f"[yellow][!] Only {cov1:.2f}% of {name1} is covered by {name2}[/yellow]")
                    console.print(f"  (Missing {missing_count:,} IPs from {name1})")

            if volume2 > 0:
                if volume_intersection == volume2:
                    console.print(f"[bold green]✓ All unique IPs from {name2} are present in {name1}[/bold green]")
            
            console.print("") # Empty line

            # Секция деталей (Exact / Partial)
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
             console.print("\n[bold red]No intersections found anywhere.[/bold red]")
             return

        handle_output(all_results, format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)