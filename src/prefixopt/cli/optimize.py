"""
CLI-команды для оптимизации списков префиксов.

Модуль содержит две команды:

1. optimize
   Выполняет полную оптимизацию списка префиксов.
   В режиме --keep-comments сохраняет комментарии и делает только
   дедупликацию с сортировкой.

2. add
   Добавляет новый префикс в существующий список.
   В режиме --keep-comments сохраняет комментарии и не агрегирует сети.
"""
import sys
import ipaddress
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Iterable, Iterator

import typer

from .common import OutputFormat, handle_output, console
from ..data.file_reader import (
    read_networks,
    read_stream,
    read_prefixes_with_comments,
    read_stream_with_comments,
)
from ..core.pipeline import process_prefixes
from ..core.ip_utils import normalize_prefix, IPNet


def _sort_key(item: Tuple[IPNet, str]) -> tuple[int, int, int]:
    """
    Ключ сортировки для списков с комментариями.

    Сортировка идет в каноническом порядке:
    версия IP -> адрес сети -> длина префикса.
    """
    net, _ = item
    return (
        net.version,
        int(net.network_address),
        net.prefixlen,
    )


def _deduplicate_commented_prefixes(
    source: Iterable[Tuple[IPNet, str]],
    ipv4_only: bool = False,
    ipv6_only: bool = False,
) -> Dict[str, str]:
    """
    Собирает уникальные префиксы с комментариями.

    Если один и тот же префикс встречается несколько раз, приоритет отдается
    непустому комментарию.

    Args:
        source: Поток кортежей (префикс, комментарий).
        ipv4_only: Оставить только IPv4.
        ipv6_only: Оставить только IPv6.

    Returns:
        Словарь вида {"prefix": "comment"}.
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
            unique_map[net_str] = comment

    return unique_map


def _materialize_commented_prefixes(unique_map: Dict[str, str]) -> List[Tuple[IPNet, str]]:
    """
    Превращает словарь префиксов с комментариями обратно в отсортированный список.

    Args:
        unique_map: Словарь вида {"prefix": "comment"}.

    Returns:
        Отсортированный список кортежей (IPNet, comment).
    """
    result: List[Tuple[IPNet, str]] = []

    for prefix_str, comment in unique_map.items():
        net_obj = ipaddress.ip_network(prefix_str, strict=False)
        result.append((net_obj, comment))

    result.sort(key=_sort_key)
    return result


def _render_commented_prefixes(items: List[Tuple[IPNet, str]]) -> str:
    """
    Превращает список префиксов с комментариями в текстовый вывод.

    Args:
        items: Список кортежей (IPNet, comment).

    Returns:
        Готовая строка для вывода в файл или stdout.
    """
    lines: List[str] = []

    for net, comment in items:
        if comment:
            lines.append(f"{net} {comment}")
        else:
            lines.append(str(net))

    return "\n".join(lines) + "\n"


def _write_commented_output(
    items: List[Tuple[IPNet, str]],
    output_file: Optional[Path],
    success_message: str,
) -> None:
    """
    Пишет результат с комментариями в файл или stdout.

    Args:
        items: Список кортежей (IPNet, comment).
        output_file: Путь к файлу назначения или None для stdout.
        success_message: Шаблон сообщения об успешной записи в файл.
    """
    content = _render_commented_prefixes(items)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
        console.print(success_message.format(count=len(items), path=output_file))
    else:
        print(content, end="")


def optimize(
    input_file: Optional[Path] = typer.Argument(None, help="Input file (optional if using pipe/stdin)"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    ipv6_only: bool = typer.Option(False, "--ipv6-only", help="Process IPv6 prefixes only"),
    ipv4_only: bool = typer.Option(False, "--ipv4-only", help="Process IPv4 prefixes only"),
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
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Fail on invalid network addresses with host bits set instead of auto-correcting them.",
    ),
) -> None:
    """
    Оптимизирует список IP-префиксов.

    Обычный режим:
        Выполняет полный цикл обработки:
        сортировка -> удаление вложенных -> агрегация.

    Режим --keep-comments:
        Сохраняет комментарии, привязанные к строкам.
        В этом режиме агрегация и удаление вложенных сетей отключены,
        потому что иначе можно потерять смысл комментариев.
        Остаются только дедупликация и сортировка.
    """
    try:
        if keep_comments and format == OutputFormat.csv:
            console.print("[red]Error: Cannot use --keep-comments with CSV format.[/red]")
            sys.exit(1)

        if keep_comments:
            source: Iterable[Tuple[IPNet, str]]

            if input_file:
                source = read_prefixes_with_comments(input_file, strict=strict)
            elif not sys.stdin.isatty():
                source = read_stream_with_comments(sys.stdin, strict=strict)
            else:
                console.print("[red]Error: No input provided. Give me a file or pipe data via STDIN.[/red]")
                sys.exit(1)

            unique_map = _deduplicate_commented_prefixes(
                source,
                ipv4_only=ipv4_only,
                ipv6_only=ipv6_only,
            )
            result_list = _materialize_commented_prefixes(unique_map)

            _write_commented_output(
                result_list,
                output_file,
                "[green]Saved {count} prefixes (with comments) to {path}[/green]",
            )
            return

        if input_file:
            prefixes = read_networks(input_file, strict=strict)
        elif not sys.stdin.isatty():
            prefixes = read_stream(sys.stdin, strict=strict)
        else:
            console.print("[red]Error: No input provided. Give me a file or pipe data via STDIN.[/red]")
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
    input_file: Path = typer.Argument(..., help="Input file with existing IP prefixes"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
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
) -> None:
    """
    Добавляет новый префикс в список и возвращает обновленный результат.

    Обычный режим:
        Новый префикс добавляется в список, после чего запускается полная оптимизация.

    Режим --keep-comments:
        Сохраняет существующие комментарии и не выполняет агрегацию.
        Новый префикс добавляется как отдельная запись.
    """
    try:
        try:
            network_to_add = normalize_prefix(new_prefix)
        except ValueError:
            console.print(f"[red]Error: Invalid prefix {new_prefix}[/red]")
            sys.exit(1)

        if keep_comments:
            if format == OutputFormat.csv:
                console.print("[red]Error: Cannot use --keep-comments with CSV format.[/red]")
                sys.exit(1)

            unique_map = _deduplicate_commented_prefixes(
                read_prefixes_with_comments(input_file)
            )

            new_net_str = str(network_to_add)

            if new_net_str in unique_map:
                console.print(f"[yellow]Prefix {new_net_str} already exists in the list.[/yellow]")
            else:
                unique_map[new_net_str] = f"# Added manually: {new_prefix}"

            result_list = _materialize_commented_prefixes(unique_map)

            _write_commented_output(
                result_list,
                output_file,
                "[green]Saved {count} prefixes to {path}[/green]",
            )
            return

        prefixes = list(read_networks(input_file))

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