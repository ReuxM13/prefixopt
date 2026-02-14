"""
Модуль команды split для CLI.

Реализует функциональность разбиения (subnetting) IP-сетей на более мелкие подсети
заданной длины (CIDR). Позволяет обрабатывать как одиночные префиксы, так и файлы.
"""
import sys
import ipaddress
from pathlib import Path
from typing import Optional, List, Union

import typer
from ipaddress import IPv4Network, IPv6Network

# Локальные импорты
from .common import OutputFormat, handle_output, console
from ..data.file_reader import read_networks, read_stream
from ..core.operations.subnetter import split_network


def split(
    target_length: int = typer.Argument(..., help="Target prefix length (e.g., 24 for /24)"),
    prefix: Optional[str] = typer.Argument(None, help="Prefix to split (e.g., 192.168.0.0/16). Optional if file/stdin used."),
    input_file: Optional[Path] = typer.Option(None, "--file", "-i", help="Input file"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    format: OutputFormat = typer.Option(
        OutputFormat.list,
        "--format", "-f",
        help="Output format: 'list' (1 per line) or 'csv' (single line, comma-separated)"
    )
) -> None:
    """
    Splits the network into subnets.

    Принимает на вход целевую длину маски (например, 24) и либо одиночный префикс,
    либо файл со списком префиксов. Генерирует все возможные подсети указанной длины.

    Args:
        target_length: Целевая длина префикса (например, 24).
        prefix: Одиночный префикс для разбиения (опционально, если есть input_file).
        input_file: Путь к файлу с префиксами для разбиения (опционально).
        output_file: Файл для сохранения результата.
        format: Формат вывода (List/CSV).

    Raises:
        SystemExit: Если аргументы некорректны или произошла ошибка разбиения (слишком много подсетей).
    """
    try:
        # Список для хранения всех сгенерированных подсетей
        # Используем Union для явной типизации
        result: List[Union[IPv4Network, IPv6Network]] = []
        
        # Определяем источник данных
        prefixes = None
        
        if input_file:
            prefixes = read_networks(input_file)
        elif not sys.stdin.isatty() and not prefix:
            # Читаем из STDIN только если не передан конкретный префикс аргументом
            prefixes = read_stream(sys.stdin)
            
        if prefixes:
            # Режим работы с файлом/потоком: читаем и разбиваем каждый префикс
            # Используем генератор для чтения, но результат накапливаем в список
            for p in prefixes:
                subnets = split_network(p, target_length)
                result.extend(subnets)
        elif prefix:
            # Режим работы с одним префиксом из аргументов
            # strict=False позволяет принимать IP адреса с битами хоста (они обнулятся)
            network = ipaddress.ip_network(prefix, strict=False)
            result = split_network(network, target_length)
        else:
            # Если не указан ни префикс, ни файл, ни поток - это ошибка использования
            console.print("[red]Error: Either a prefix, an input file, or piped data must be specified[/red]")
            sys.exit(1)

        # Передаем список результатов в обработчик вывода
        handle_output(result, format, output_file)

        # Выводим статистику только в интерактивном режиме (List-формат) или при записи в файл,
        # чтобы не нарушать формат CSV в stdout.
        if output_file or format == OutputFormat.list:
            console.print(f"[green]Generated {len(result)} subnets[/green]")

    except Exception as e:
        # Ловим ValueError от split_network (если маска больше исходной или превышен лимит)
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)