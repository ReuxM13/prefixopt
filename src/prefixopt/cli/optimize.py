"""
Модуль команды optimize для CLI.

Этот модуль предоставляет основные команды для оптимизации списков IP-префиксов:
- optimize: Очистка списка (удаление вложенных, агрегация, сортировка).
- add: Добавление нового префикса с последующей полной оптимизацией.
"""
import sys
from pathlib import Path
from typing import Optional

import typer

# Локальные импорты
from .common import OutputFormat, handle_output, console
# Импортируем read_stream явно
from ..data.file_reader import read_networks, read_stream
from ..core.pipeline import process_prefixes
from ..core.ip_utils import normalize_prefix


def optimize(
    input_file: Optional[Path] = typer.Argument(None, help="Input file (optional if using pipe/stdin)"),
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
    Optimizes the list of IP prefixes.

    Выполняет полный цикл обработки: сортировка, очистка, агрегация.
    """
    try:
        # Определяем, откуда читать данные
        if input_file:
            prefixes = read_networks(input_file)
        elif not sys.stdin.isatty():
            # Если данные идут через Pipe
            prefixes = read_stream(sys.stdin)
        else:
            console.print("[red]Error: No input provided. Give me a file or pipe data via STDIN.[/red]")
            sys.exit(1)

        # Запускаем пайплайн обработки.
        # Здесь мы НЕ используем list(), чтобы сохранить ленивость генератора
        # до самого последнего момента (записи в файл).
        processed_prefixes = process_prefixes(
            prefixes,
            sort=True,
            remove_nested=True,
            aggregate=True,
            ipv4_only=ipv4_only,
            ipv6_only=ipv6_only
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
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    )
) -> None:
    """
    Adds a new prefix to the file and optimizes the entire list.
    """
    try:
        try:
            network = normalize_prefix(new_prefix)
        except ValueError:
            console.print(f"[red]Error: Invalid prefix {new_prefix}[/red]")
            sys.exit(1)

        # Читаем в список, чтобы проверить наличие и добавить
        prefixes = list(read_networks(input_file))

        if network not in prefixes:
            prefixes.append(network)

        # Запускаем оптимизацию
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