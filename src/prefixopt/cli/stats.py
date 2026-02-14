"""
Модуль команд статистики и проверки для CLI.
"""
import sys
import ipaddress
from pathlib import Path
from typing import Optional, List, Union

import typer
from rich.table import Table
from ipaddress import IPv4Network, IPv6Network, IPv4Address, IPv6Address

from .common import console
from ..data.file_reader import read_networks, read_stream
from ..core.ip_counter import get_prefix_statistics


def stats(
    input_file: Optional[Path] = typer.Argument(None, help="Input file (optional if using pipe/stdin)"),
    show_details: bool = typer.Option(False, "--details", "-d", help="Show detailed statistics")
) -> None:
    """
    Displays statistics on a list of IP prefixes.
    """
    try:
        if input_file:
            prefixes = list(read_networks(input_file))
            source_name = input_file.name
        elif not sys.stdin.isatty():
            prefixes = list(read_stream(sys.stdin))
            source_name = "STDIN"
        else:
            console.print("[red]Error: No input provided.[/red]")
            sys.exit(1)
        
        statistics = get_prefix_statistics(prefixes)

        table = Table(title=f"Statistics for {source_name}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right", style="magenta")

        table.add_row("Original prefix count", str(statistics['original_prefix_count']))
        table.add_row("Optimized prefix count", str(statistics['optimized_prefix_count']))
        table.add_row("Compression ratio", f"{statistics['compression_ratio_percent']}%")
        table.add_row("Original total IPs", f"{statistics['original_total_ips']:,}")
        table.add_row("Unique IPs", f"{statistics['unique_ips']:,}")
        table.add_row("Addresses saved", f"{statistics['addresses_saved']:,}")

        console.print(table)

        if show_details:
            console.print("\n[bold]Detailed information:[/bold]")
            ipv4_count = len([p for p in prefixes if p.version == 4])
            ipv6_count = len([p for p in prefixes if p.version == 6])
            
            detail_table = Table()
            detail_table.add_column("Category", style="cyan")
            detail_table.add_column("Count", justify="right", style="magenta")
            detail_table.add_row("IPv4 prefixes", str(ipv4_count))
            detail_table.add_row("IPv6 prefixes", str(ipv6_count))
            console.print(detail_table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def check(
    ip_or_prefix: str = typer.Argument(..., help="IP address or prefix to check"),
    input_file: Optional[Path] = typer.Argument(None, help="Input file (optional if using pipe/stdin)")
) -> None:
    """
    Checks whether the specified IP or subnet is included in the prefix list.
    """
    try:
        check_item: Union[IPv4Network, IPv6Network, IPv4Address, IPv6Address]
        try:
            if '/' in ip_or_prefix:
                check_item = ipaddress.ip_network(ip_or_prefix, strict=False)
            else:
                check_item = ipaddress.ip_address(ip_or_prefix)
        except ValueError:
            console.print(f"[red]Error: Invalid IP address or prefix {ip_or_prefix}[/red]")
            sys.exit(1)

        # Ленивое чтение
        if input_file:
            prefixes = read_networks(input_file)
        elif not sys.stdin.isatty():
            prefixes = read_stream(sys.stdin)
        else:
            console.print("[red]Error: No input list provided.[/red]")
            sys.exit(1)

        containing_networks: List[Union[IPv4Network, IPv6Network]] = []
        
        for net in prefixes:
            if check_item.version != net.version:
                continue

            if isinstance(check_item, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
                if check_item in net:
                    containing_networks.append(net)
            else:
                if isinstance(check_item, ipaddress.IPv4Network) and isinstance(net, ipaddress.IPv4Network):
                    if check_item.subnet_of(net):
                        containing_networks.append(net)
                elif isinstance(check_item, ipaddress.IPv6Network) and isinstance(net, ipaddress.IPv6Network):
                    if check_item.subnet_of(net):
                        containing_networks.append(net)

        if containing_networks:
            console.print(f"[green]{ip_or_prefix} is contained in:[/green]")
            for net in containing_networks:
                console.print(f"  [blue]{net}[/blue]")
        else:
            src = f" in {input_file}" if input_file else ""
            console.print(f"[red]{ip_or_prefix} is not contained in any prefix{src}[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)