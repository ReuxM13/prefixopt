"""
Модуль команды exclude для CLI.

Позволяет исключить конкретные IP-адреса, подсети или целый
список сетей из входного файла.
"""
import sys
from pathlib import Path
from typing import Optional, List

import typer

# Локальные импорты
from .common import OutputFormat, handle_output, console
from ..data.file_reader import read_networks, read_stream
from ..core.pipeline import process_prefixes
from ..core.ip_utils import normalize_prefix, IPNet
from ..core.operations.subtractor import subtract_networks


def exclude(
    target: str = typer.Argument(..., help="Prefix to exclude (e.g. 10.0.0.0/8) OR path to file with prefixes"),
    input_file: Optional[Path] = typer.Argument(None, help="Input file with IP prefixes (optional if using pipe)"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    ipv6_only: bool = typer.Option(False, "--ipv6-only", help="Process IPv6 prefixes only"),
    ipv4_only: bool = typer.Option(False, "--ipv4-only", help="Process IPv4 prefixes only"),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    )
) -> None:
    """
    Excludes networks (Target) from the list (Input).

    Реализует алгоритм вычитания адресного пространства. Если исключаемая сеть
    является частью большей сети из списка, большая сеть будет разбита на фрагменты.

    Target может быть:
    1. Одиночным префиксом (например, "192.168.1.1").
    2. Файлом со списком префиксов.

    После вычитания выполняется полная оптимизация результата.
    """
    try:
        # 1. Определение типа Target (Файл или Префикс)
        exclude_list: List[IPNet] = []
        target_path = Path(target)

        if target_path.exists() and target_path.is_file():
            # Если это файл - читаем список исключений
            try:
                # Используем list(), так как subtractor требует многократного доступа к excludes
                # или мы хотим загрузить их в память для оптимизации
                exclude_list = list(read_networks(target_path))
                console.print(f"[dim]Loaded {len(exclude_list)} exclusion rules from file.[/dim]")
            except Exception as e:
                console.print(f"[red]Error reading exclusion file: {e}[/red]")
                sys.exit(1)
        else:
            # Если не файл - пробуем парсить как IP/Сеть
            try:
                net = normalize_prefix(target)
                exclude_list = [net]
            except ValueError:
                console.print(f"[red]Error: '{target}' is not a valid IP prefix and not an existing file.[/red]")
                sys.exit(1)

        # 2. Чтение исходного файла (или потока)
        if input_file:
            source_prefixes = read_networks(input_file)
        elif not sys.stdin.isatty():
            source_prefixes = read_stream(sys.stdin)
        else:
            console.print("[red]Error: No input provided. Give me a file or pipe data.[/red]")
            sys.exit(1)

        # 3. Вычитание
        with console.status("Processing exclusions...", spinner="dots"):
            # Результат вычитания - сырой список фрагментов
            raw_result = subtract_networks(source_prefixes, exclude_list)
            
            # 4. Финальная оптимизация
            # Фрагменты нужно отсортировать и склеить, если это возможно
            # (например, если мы вырезали дырку, а потом оказалось, что соседи могут склеиться)
            final_result = process_prefixes(
                raw_result,
                sort=True,
                remove_nested=True,
                aggregate=True,
                ipv4_only=ipv4_only,
                ipv6_only=ipv6_only
            )
            # Материализуем здесь, чтобы спиннер работал корректно
            final_list = list(final_result)

        # 5. Вывод
        handle_output(final_list, format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)