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

import typer

# Локальные импорты
from .common import OutputFormat, handle_output, console
from ..data.file_reader import read_networks, read_prefixes_with_comments
from ..core.pipeline import process_prefixes
from ..core.operations.sorter import sort_networks
from ..core.ip_utils import IPNet


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

    Команда поддерживает два режима работы:
    1. Стандартный (Оптимизация): Списки загружаются, объединяются, сортируются,
       очищаются от вложенностей и агрегируются.
    2. Режим --keep-comments: Используется для слияния списков "белого доступа"
       или конфигов с комментариями.
       - Агрегация и удаление вложенных сетей ОТКЛЮЧАЮТСЯ (чтобы не потерять
         привязку комментария к конкретной подсети).
       - Выполняется дедупликация (удаление полных дублей IP).
       - Используется потоковая обработка для экономии памяти.

    Args:
        file1: Путь к первому файлу.
        file2: Путь ко второму файлу.
        output_file: Файл для сохранения результата.
        format: Формат вывода.
        keep_comments: Включить режим сохранения комментариев.

    Raises:
        SystemExit: При ошибках ввода-вывода или несовместимых аргументах.
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
            process_stream(read_prefixes_with_comments(file1))

            # 2. Читаем второй файл прямо в словарь
            process_stream(read_prefixes_with_comments(file2))

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

            # Материализуем результат
            processed_list = list(processed_prefixes)

            # Передаем результат в обработчик вывода
            handle_output(processed_list, format, output_file)

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
        # Список кортежей (Подсеть, Суперсеть/Пересечение)
        overlapping: List[Tuple[IPNet, IPNet]] = []

        for net1 in prefixes1:
            for net2 in prefixes2:
                # Пропускаем, если сети уже найдены как точные копии
                if net1 in common_prefixes and net2 in common_prefixes:
                    continue

                # type: ignore - Pylance иногда ложно срабатывает на overlaps с Union типами
                if net1.overlaps(net2): 
                    # Проверяем версию перед subnet_of для безопасности типов
                    if net1.version == net2.version:
                        # Используем явные проверки типов или type ignore, 
                        # так как мы гарантировали совпадение версий
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
        # Используем set для дедупликации, потом сортируем
        all_results = list(set(all_results))
        all_results = sort_networks(all_results)

        if not all_results and should_print_details:
             console.print("\n[red]No intersections found[/red]")
             return

        handle_output(all_results, format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)