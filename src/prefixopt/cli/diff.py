"""
Модуль команды diff для CLI.

Позволяет сравнивать два списка префиксов (New vs Old) и выявлять изменения.
Поддерживает различные режимы отображения (только добавленные, только удаленные и т.д.).
"""
import sys
from pathlib import Path
from typing import Optional, Iterable
from enum import Enum

import typer

# Локальные импорты
from .common import console
from ..data.file_reader import read_networks
from ..core.pipeline import process_prefixes
from ..core.operations.diff import calculate_diff
from ..core.operations.sorter import sort_networks
from ..core.ip_utils import IPNet


class DiffMode(str, Enum):
    """Режимы отображения разницы."""
    changes = "changes"      # Только изменения (+ и -) [По умолчанию]
    added = "added"          # Только добавленные (+)
    removed = "removed"      # Только удаленные (-)
    unchanged = "unchanged"  # Только неизменные (=)
    all = "all"              # Полный отчет (+, -, =)


def diff(
    new_file: Path = typer.Argument(..., help="New/Target file (Source of Truth)"),
    old_file: Path = typer.Argument(..., help="Old/Current file (to compare against)"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file for diff report"),
    summary_only: bool = typer.Option(False, "--summary", "-s", help="Show only counts, not prefixes"),
    mode: DiffMode = typer.Option(DiffMode.changes, "--mode", "-m", help="Display mode: changes (default), added, removed, unchanged, all"),
    ipv6_only: bool = typer.Option(False, "--ipv6-only", help="Process IPv6 prefixes only"),
    ipv4_only: bool = typer.Option(False, "--ipv4-only", help="Process IPv4 prefixes only"),
) -> None:
    """
    Compares two prefix files and shows the changes.

    Оба файла предварительно проходят полную оптимизацию.
    Вы можете выбрать, какие именно изменения показывать, используя флаг --mode.
    """
    try:
        def prepare(path: Path) -> Iterable[IPNet]:
            """Вспомогательная функция: Чтение + Пайплайн."""
            raw = read_networks(path)
            return process_prefixes(
                raw, 
                sort=True, 
                remove_nested=True, 
                aggregate=True,
                ipv4_only=ipv4_only,
                ipv6_only=ipv6_only
            )

        with console.status("[bold green]Calculating differences...", spinner="dots"):
            # Материализуем в списки для diff
            nets_new = list(prepare(new_file))
            nets_old = list(prepare(old_file))
            
            # Вычисляем разницу (множества)
            added, removed, unchanged = calculate_diff(nets_new, nets_old)

        # Определение того, что показывать, на основе выбранного режима
        show_added = mode in (DiffMode.changes, DiffMode.added, DiffMode.all)
        show_removed = mode in (DiffMode.changes, DiffMode.removed, DiffMode.all)
        show_unchanged = mode in (DiffMode.unchanged, DiffMode.all)

        # --- Режим Summary ---
        if summary_only:
            if show_added:
                console.print(f"[green]Added: {len(added)}[/green]")
            if show_removed:
                console.print(f"[red]Removed: {len(removed)}[/red]")
            if show_unchanged:
                console.print(f"[blue]Unchanged: {len(unchanged)}[/blue]")
            return

        # Сортировка для вывода (только тех данных, которые нужны)
        sorted_added = sort_networks(added) if show_added else []
        sorted_removed = sort_networks(removed) if show_removed else []
        sorted_unchanged = sort_networks(unchanged) if show_unchanged else []

        # --- Вывод в файл или консоль ---

        if output_file:
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    for net in sorted_added:
                        f.write(f"+ {net}\n")
                    for net in sorted_removed:
                        f.write(f"- {net}\n")
                    for net in sorted_unchanged:
                        f.write(f"= {net}\n")
                            
                console.print(f"[green]Diff saved to {output_file} (Mode: {mode.value})[/green]")
            except IOError as e:
                console.print(f"[red]Error writing to file: {e}[/red]")
                sys.exit(1)
        
        else:
            # Если ничего не найдено в выбранном режиме
            if not sorted_added and not sorted_removed and not sorted_unchanged:
                if mode == DiffMode.changes and (not added and not removed):
                     console.print("[bold green]Files are identical (semantically)[/bold green]")
                return

            # Вывод секций
            if sorted_added:
                console.print(f"\n[bold green]+++ Added ({len(sorted_added)}):[/bold green]")
                for net in sorted_added:
                    console.print(f"[green]+ {net}[/green]")
            
            if sorted_removed:
                console.print(f"\n[bold red]--- Removed ({len(sorted_removed)}):[/bold red]")
                for net in sorted_removed:
                    console.print(f"[red]- {net}[/red]")

            if sorted_unchanged:
                console.print(f"\n[bold blue]=== Unchanged ({len(sorted_unchanged)}):[/bold blue]")
                for net in sorted_unchanged:
                    console.print(f"[blue]= {net}[/blue]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)