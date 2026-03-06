"""
Модуль команды exclude для CLI.

Отвечает за операции вычитания сетей (исключение подмножеств) из списка.
Поддерживает режим сохранения комментариев при разбиении сетей.
"""
import sys
from pathlib import Path
from typing import Optional, List, Dict

import typer

from .common import OutputFormat, handle_output, console
from ..data.file_reader import read_networks, read_stream, read_prefixes_with_comments
from ..core.pipeline import process_prefixes
from ..core.ip_utils import normalize_prefix, IPNet, is_subnet_of
from ..core.operations.subtractor import subtract_networks


def exclude(
    target: str = typer.Argument(..., help="Prefix to exclude (e.g. 10.0.0.0/8) OR path to file"),
    input_file: Optional[Path] = typer.Argument(None, help="Input file with IP prefixes"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
    ipv6_only: bool = typer.Option(False, "--ipv6-only", help="Process IPv6 only"),
    ipv4_only: bool = typer.Option(False, "--ipv4-only", help="Process IPv4 only"),
    format: OutputFormat = typer.Option(OutputFormat.list, "--format", "-f"),
    keep_comments: bool = typer.Option(False, "--keep-comments", help="Preserve comments from input file.")
) -> None:
    """
    Deletes the specified networks (Target) from the source list (Input).

    Если исключаемая сеть находится внутри более крупной сети из списка,
    исходная сеть будет разбита на фрагменты ("пробивание дырок").
    """
    try:
        # 1. Загрузка списка исключений (Target)
        # Target может быть как файлом, так и просто строкой с префиксом.
        exclude_list: List[IPNet] = []
        target_path = Path(target)

        if target_path.exists() and target_path.is_file():
            try:
                # Читаем файл исключений. Комментарии здесь не важны, нужны только сети.
                exclude_list = list(read_networks(target_path))
                console.print(f"[dim]Loaded {len(exclude_list)} exclusion rules.[/dim]")
            except Exception as e:
                console.print(f"[red]Error reading exclusion file: {e}[/red]")
                sys.exit(1)
        else:
            # Если это не файл, пробуем распарсить как одиночный префикс
            try:
                net = normalize_prefix(target)
                exclude_list = [net]
            except ValueError:
                console.print(f"[red]Error: '{target}' is not a valid IP prefix or file.[/red]")
                sys.exit(1)

        # 2. Загрузка исходных данных (Source)
        source_prefixes: List[IPNet] = []
        comments_map: Dict[IPNet, str] = {}

        if keep_comments:
            if not input_file:
                 console.print("[red]Error: --keep-comments requires an input file.[/red]")
                 sys.exit(1)
            
            # Читаем файл, сохраняя привязку "Сеть -> Комментарий"
            for net, comm in read_prefixes_with_comments(input_file):
                source_prefixes.append(net)
                if comm:
                    comments_map[net] = comm
        else:
            # Обычный режим: читаем из файла или STDIN
            if input_file:
                source_prefixes = list(read_networks(input_file))
            elif not sys.stdin.isatty():
                source_prefixes = list(read_stream(sys.stdin))
            else:
                console.print("[red]Error: No input provided.[/red]")
                sys.exit(1)

        # 3. Выполнение операции вычитания
        with console.status("Processing exclusions...", spinner="dots"):
            # Получаем "сырой" список остатков сетей
            raw_result = subtract_networks(source_prefixes, exclude_list)
            
            if keep_comments:
                # Режим с комментариями:
                # Мы не можем агрегировать результат, чтобы не потерять привязку к комментариям.
                # Наша задача - восстановить комментарии для каждого оставшегося фрагмента.
                
                final_output_lines = []
                
                # Сортируем для удобства чтения (Broadest First)
                raw_result.sort(key=lambda x: (x.version, int(x.network_address), x.prefixlen))

                for fragment in raw_result:
                    inherited_comment = ""
                    
                    # Сценарий А: Сеть не изменилась (прямое совпадение)
                    if fragment in comments_map:
                        inherited_comment = comments_map[fragment]
                    else:
                        # Сценарий Б: Сеть была разбита. Ищем её родителя.
                        # Это линейный поиск O(N*M), но гарантирует корректность наследования.
                        for original in source_prefixes:
                            # Ускорение: проверяем версию перед дорогой проверкой subnet_of
                            if fragment.version == original.version and is_subnet_of(fragment, original):
                                if original in comments_map:
                                    inherited_comment = comments_map[original]
                                    break
                    
                    line = f"{fragment} {inherited_comment}" if inherited_comment else str(fragment)
                    final_output_lines.append(line)
                
                # Вывод результатов в файл или консоль
                content = "\n".join(final_output_lines) + "\n"
                
                if output_file:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    console.print(f"[green]Saved {len(final_output_lines)} fragments (with comments) to {output_file}[/green]")
                else:
                    print(content, end="")

            else:
                # Стандартный режим:
                # Запускаем полный цикл оптимизации для получения минимального списка CIDR.
                final_result = process_prefixes(
                    raw_result,
                    sort=True,
                    remove_nested=True,
                    aggregate=True,
                    ipv4_only=ipv4_only,
                    ipv6_only=ipv6_only
                )
                handle_output(list(final_result), format, output_file)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)