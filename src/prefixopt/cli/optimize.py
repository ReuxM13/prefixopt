"""
Модуль команд оптимизации для CLI.

Содержит:
1. optimize: Основная команда для чистки и сжатия списков.
2. add: Утилита для добавления нового префикса в существующий список.
"""
import sys
import ipaddress
from pathlib import Path
from typing import Optional, List, Tuple, Dict

import typer

# Локальные импорты
from .common import OutputFormat, handle_output, console
from ..data.file_reader import read_networks, read_stream, read_prefixes_with_comments
from ..core.pipeline import process_prefixes
from ..core.ip_utils import normalize_prefix, IPNet


def optimize(
    input_file: Optional[Path] = typer.Argument(None, help="Input file (optional if using pipe/stdin)"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    ipv6_only: bool = typer.Option(False, "--ipv6-only", help="Process IPv6 prefixes only"),
    ipv4_only: bool = typer.Option(False, "--ipv4-only", help="Process IPv4 prefixes only"),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    ),
    keep_comments: bool = typer.Option(False, "--keep-comments", help="Preserve comments. WARNING: Disables aggregation!")
) -> None:
    """
    Optimizes the list of IP prefixes.

    Стандартный режим:
        Полный цикл: Сортировка -> Удаление вложенных -> Агрегация.
        Максимальное сжатие списка.

    Режим --keep-comments:
        Используется для обработки конфигурационных файлов или списков ACL,
        где важно сохранить пояснения (комментарии) к IP-адресам.
        В этом режиме:
        1. Агрегация ОТКЛЮЧАЕТСЯ (нельзя склеить две сети, если у них разные комментарии).
        2. Удаление вложенных ОТКЛЮЧАЕТСЯ (чтобы не удалить специфичную запись с важным комментом).
        3. Работает только Дедупликация (удаление полных дублей) и Сортировка.
    """
    try:
        # 1. Проверка совместимости флагов
        if keep_comments and format == OutputFormat.csv:
            console.print("[red]Error: Cannot use --keep-comments with CSV format.[/red]")
            sys.exit(1)

        # 2. Логика для режима с комментариями
        if keep_comments:
            if not input_file:
                console.print("[red]Error: --keep-comments requires an input file (STDIN not supported yet).[/red]")
                sys.exit(1)

            # Словарь для дедупликации: "1.1.1.1/32" -> "Comment"
            unique_map: Dict[str, str] = {}

            # Читаем файл, сохраняя привязку строк к комментариям
            for net, comment in read_prefixes_with_comments(input_file):
                # Фильтрация по версии (если запрошено)
                if ipv4_only and net.version != 4:
                    continue
                if ipv6_only and net.version != 6:
                    continue

                ip_str = str(net)
                
                # Логика дедупликации:
                # Если IP уже есть, но без коммента, а новый пришел с комментом -> обновляем.
                if ip_str not in unique_map:
                    unique_map[ip_str] = comment
                elif not unique_map[ip_str] and comment:
                    unique_map[ip_str] = comment

            # Превращаем словарь обратно в список объектов для сортировки
            # Нам нужно сортировать объекты, а не строки, чтобы 10.0.0.10 шло после 10.0.0.2
            result_list: List[Tuple[IPNet, str]] = []
            for ip_key, comm in unique_map.items():
                net_obj = ipaddress.ip_network(ip_key, strict=False)
                result_list.append((net_obj, comm))

            # Сортировка Broadest First (Версия -> IP -> Маска)
            result_list.sort(key=lambda item: (
                item[0].version,
                int(item[0].network_address),
                item[0].prefixlen
            ))

            # Формируем итоговый текст
            lines = []
            for net_obj, comm in result_list:
                if comm:
                    lines.append(f"{net_obj} {comm}")
                else:
                    lines.append(str(net_obj))

            content = "\n".join(lines) + "\n"

            # Вывод результата
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                console.print(f"[green]Saved {len(lines)} prefixes (with comments) to {output_file}[/green]")
            else:
                print(content, end="")

        # 3. Стандартная логика (без комментариев, полная оптимизация)
        else:
            # Определяем источник данных
            if input_file:
                prefixes = read_networks(input_file)
            elif not sys.stdin.isatty():
                prefixes = read_stream(sys.stdin)
            else:
                console.print("[red]Error: No input provided. Give me a file or pipe data via STDIN.[/red]")
                sys.exit(1)

            # Запускаем полный пайплайн
            processed_prefixes = process_prefixes(
                prefixes,
                sort=True,
                remove_nested=True,
                aggregate=True,
                ipv4_only=ipv4_only,
                ipv6_only=ipv6_only
            )

            # Вывод через общий обработчик
            handle_output(processed_prefixes, format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def add(
    new_prefix: str = typer.Argument(..., help="New prefix to add"),
    input_file: Path = typer.Argument(..., help="Input file with existing IP prefixes"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    ),
    keep_comments: bool = typer.Option(False, "--keep-comments", help="Preserve comments. Disables aggregation.")
) -> None:
    """
    Adds a new prefix to the file and optimizes the list.
    """
    try:
        # Валидация входного префикса
        try:
            network_to_add = normalize_prefix(new_prefix)
        except ValueError:
            console.print(f"[red]Error: Invalid prefix {new_prefix}[/red]")
            sys.exit(1)

        # Режим с комментариями
        if keep_comments:
            if format == OutputFormat.csv:
                console.print("[red]Error: Cannot use --keep-comments with CSV format.[/red]")
                sys.exit(1)

            # Читаем существующие данные
            unique_map: Dict[str, str] = {}
            for net, comment in read_prefixes_with_comments(input_file):
                unique_map[str(net)] = comment

            # Добавляем новый IP
            new_ip_str = str(network_to_add)
            
            if new_ip_str in unique_map:
                console.print(f"[yellow]Prefix {new_ip_str} already exists in the list.[/yellow]")
            else:
                # Добавляем с пометкой, что это новый IP
                unique_map[new_ip_str] = f"# Added manually: {new_prefix}"
            
            # Конвертируем обратно и сортируем
            result_list: List[Tuple[IPNet, str]] = []
            for ip_key, comm in unique_map.items():
                net_obj = ipaddress.ip_network(ip_key, strict=False)
                result_list.append((net_obj, comm))

            result_list.sort(key=lambda item: (
                item[0].version,
                int(item[0].network_address),
                item[0].prefixlen
            ))

            # Формирование вывода
            lines = []
            for net_obj, comm in result_list:
                if comm:
                    lines.append(f"{net_obj} {comm}")
                else:
                    lines.append(str(net_obj))
            
            content = "\n".join(lines) + "\n"

            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                console.print(f"[green]Saved {len(lines)} prefixes to {output_file}[/green]")
            else:
                print(content, end="")

        # Стандартный режим (без комментариев)
        else:
            prefixes = list(read_networks(input_file))

            if network_to_add not in prefixes:
                prefixes.append(network_to_add)

            # Полная оптимизация
            processed_prefixes = process_prefixes(
                prefixes,
                sort=True,
                remove_nested=True,
                aggregate=True
            )

            handle_output(processed_prefixes, format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)