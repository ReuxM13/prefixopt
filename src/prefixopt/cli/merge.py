"""
Модуль команд слияния и пересечения для CLI.

Предоставляет функциональность для объединения (merge) нескольких списков
префиксов с опциональным сохранением комментариев, а также для поиска
пересечений (intersect) и перекрытий между двумя списками.
"""
import sys
import ipaddress
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import typer

# Локальные импорты
from .common import OutputFormat, handle_output, console
from ..data.file_reader import read_networks, read_prefixes_with_comments
from ..core.pipeline import process_prefixes
from ..core.operations.sorter import sort_networks


def merge(
    file1: Path = typer.Argument(..., help="First input file with IP prefixes"),
    file2: Path = typer.Argument(..., help="Second input file with IP prefixes"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    ),
    keep_comments: bool = typer.Option(False, "--keep-comments", help="Preserve comments. Disables aggregation and CSV format.")
) -> None:
    """
    Combines two files with IP prefixes.

    По умолчанию выполняет полную оптимизацию (сортировка, удаление вложенных, агрегация).
    Результат всегда отсортирован.

    Args:
        file1: Путь к первому файлу.
        file2: Путь ко второму файлу.
        output_file: Файл для сохранения результата.
        format: Формат вывода (List/CSV).
        keep_comments: Режим сохранения комментариев. Отключает агрегацию.

    Raises:
        SystemExit: При ошибках ввода-вывода или несовместимых аргументах.
    """
    try:
        # Проверка на конфликт: CSV не поддерживает комментарии в нашем формате
        if keep_comments and format == OutputFormat.csv:
            console.print("[red]Error: Cannot use --keep-comments with CSV format.[/red]")
            sys.exit(1)

        if keep_comments:
            # Читаем данные как кортежи (IP объект, Комментарий)
            data1 = read_prefixes_with_comments(file1)
            data2 = read_prefixes_with_comments(file2)
            all_data = data1 + data2
            
            # Дедупликация с сохранением комментариев.
            # Приоритет отдается записи с непустым комментарием.
            unique_map: Dict[str, str] = {}
            for ip, comment in all_data:
                ip_str = str(ip)
                if ip_str not in unique_map:
                    unique_map[ip_str] = comment
                else:
                    # Если у существующего нет коммента, а у нового есть - обновляем
                    if not unique_map[ip_str] and comment:
                        unique_map[ip_str] = comment

            # Восстанавливаем объекты IP для корректной сортировки
            merged_list: List[Tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, str]] = []
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
            # Обычный режим
            # Используем list() для загрузки генераторов в память, чтобы объединить их
            prefixes1 = list(read_networks(file1))
            prefixes2 = list(read_networks(file2))
            all_prefixes = prefixes1 + prefixes2

            # Запускаем полный цикл оптимизации через Pipeline
            processed_prefixes = process_prefixes(
                all_prefixes,
                sort=True,           # Всегда сортируем при слиянии
                remove_nested=True,  # Чистим вложенность
                aggregate=True       # Склеиваем соседей
            )

            # Передаем результат в обработчик вывода
            handle_output(processed_prefixes, format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def intersect(
    file1: Path = typer.Argument(..., help="First input file with IP prefixes"),
    file2: Path = typer.Argument(..., help="Second input file with IP prefixes"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    )
) -> None:
    """
    Finds intersections between two files.

    Определяет:
    1. Common prefixes: Точные совпадения сетей.
    2. Overlapping networks: Сети, которые пересекаются или вложены, но не равны.

    Args:
        file1: Первый файл.
        file2: Второй файл.
        output_file: Файл для вывода результата (только список сетей).
        format: Формат вывода.
    """
    try:
        # Используем set для быстрого поиска точных совпадений
        prefixes1 = set(read_networks(file1))
        prefixes2 = set(read_networks(file2))

        # 1. Точные совпадения
        common_prefixes = prefixes1.intersection(prefixes2)

        # 2. Частичные перекрытия и вложенность
        overlapping: List[Tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ipaddress.IPv4Network | ipaddress.IPv6Network]] = []
        
        for net1 in prefixes1:
            for net2 in prefixes2:
                # Пропускаем, если сети уже найдены как точные копии
                if net1 in common_prefixes or net2 in common_prefixes:
                    continue
                
                # Оптимизация: overlaps работает быстро, subnet_of медленнее
                if net1.overlaps(net2):
                    # Проверяем версию перед subnet_of для безопасности типов
                    if net1.version == net2.version:
                        # type: ignore - Pylance иногда не видит проверку версии
                        if net1.subnet_of(net2): # type: ignore
                            overlapping.append((net1, net2))
                        elif net2.subnet_of(net1): # type: ignore
                            overlapping.append((net2, net1))

        # Логика вывода: в консоль пишем детали, в файл/csv только данные
        should_print_details = output_file is not None or format == OutputFormat.list

        if should_print_details:
            console.print(f"[bold]Common prefixes:[/bold] {len(common_prefixes)}")
            for prefix in sort_networks(common_prefixes):
                console.print(f"  [blue]{prefix}[/blue]")

            console.print(f"\n[bold]Overlapping networks:[/bold] {len(overlapping)}")
            
            # Сортируем перекрытия для красивого вывода
            sorted_overlapping = sorted(
                overlapping, 
                key=lambda x: (x[0].version, int(x[0].network_address), x[0].prefixlen)
            )
            for sub, parent in sorted_overlapping:
                console.print(f"  [yellow]{sub}[/yellow] is in [yellow]{parent}[/yellow]")

        # Формируем итоговый список для сохранения
        all_results = list(common_prefixes)
        for sub, parent in overlapping:
            all_results.extend([sub, parent])

        # Финальная очистка и сортировка результата
        all_results = list(set(all_results))
        all_results = sort_networks(all_results)

        if not all_results and should_print_details:
             console.print("\n[red]No intersections found[/red]")
             return

        handle_output(all_results, format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)