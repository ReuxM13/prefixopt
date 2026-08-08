"""
Counting IPs and computing summary statistics.

These functions are used by the ``stats`` command and the GUI stats tab. They
build on top of the core operations: to count *unique* addresses we first
optimise the list (sort -> remove nested -> aggregate) to avoid double counting
overlapping ranges.
"""

from collections import Counter
from typing import Dict, Iterable, List, Tuple, Union

from ipaddress import IPv4Network, IPv6Network

from .operations.aggregator import aggregate
from .operations.nested import remove_nested
from .operations.sorter import sort_networks


def count_unique_ips(
    prefixes: Iterable[Union[IPv4Network, IPv6Network]],
) -> int:
    """Count the number of distinct IP addresses represented by ``prefixes``.

    Overlapping/nested ranges are collapsed first so each address is counted
    exactly once. Works for both IPv4 and IPv6.

    Args:
        prefixes: Arbitrary iterable of networks (may contain duplicates).

    Returns:
        Total number of unique IP addresses across all networks.
    """
    # Optimise the set so overlapping ranges don't inflate the count.
    sorted_prefixes = sort_networks(prefixes)
    clean_prefixes = remove_nested(sorted_prefixes, assume_sorted=True)
    aggregated_prefixes = aggregate(clean_prefixes)

    total_ips = 0
    for network in aggregated_prefixes:
        # num_addresses is the size of the CIDR (2^(32-prefixlen) for IPv4).
        total_ips += int(network.num_addresses)

    return total_ips


def count_total_ips_in_prefixes(
    prefixes: Iterable[Union[IPv4Network, IPv6Network]],
) -> int:
    """Sum of ``num_addresses`` without deduplication.

    Useful to report the raw address space referenced by a file *before*
    optimisation (can be larger than :func:`count_unique_ips` when overlaps
    exist).
    """
    total_ips = 0
    for network in prefixes:
        total_ips += int(network.num_addresses)
    return total_ips


def get_prefix_statistics(
    prefixes: List[Union[IPv4Network, IPv6Network]],
) -> Dict[str, Union[int, float]]:
    """Compute a bundle of statistics shown by the stats command/tab.

    Args:
        prefixes: Input list (should be materialised - len() is called).

    Returns:
        Dictionary with keys:
            original_prefix_count      - rows in the input.
            optimized_prefix_count     - rows after sort/nest/aggregate.
            compression_ratio_percent  - how many rows were collapsed.
            original_total_ips         - sum of sizes before optimisation.
            unique_ips                 - unique address count.
            addresses_saved            - original_total_ips - unique_ips.
    """
    original_count = len(prefixes)
    original_total_ips = count_total_ips_in_prefixes(prefixes)

    # Produce the optimised representation to compare against.
    sorted_prefixes = sort_networks(prefixes)
    clean_prefixes = remove_nested(sorted_prefixes, assume_sorted=True)
    optimized_prefixes = aggregate(clean_prefixes)
    optimized_count = len(optimized_prefixes)

    unique_ips = count_unique_ips(prefixes)

    compression_ratio = 0.0
    if original_count > 0:
        compression_ratio = (
            (original_count - optimized_count) / original_count * 100
        )

    return {
        "original_prefix_count": original_count,
        "optimized_prefix_count": optimized_count,
        "compression_ratio_percent": round(compression_ratio, 2),
        "original_total_ips": original_total_ips,
        "unique_ips": unique_ips,
        # "Saved" means addresses that were double-referenced by overlaps.
        "addresses_saved": original_total_ips - unique_ips,
    }


def get_duplicate_prefixes(
    prefixes: Iterable[Union[IPv4Network, IPv6Network]],
) -> List[Tuple[str, int]]:
    """Return prefixes that appear more than once, with their occurrence count.

    Used by the stats report to highlight redundant rows. Output is a list of
    ``(prefix_string, count)`` sorted by insertion order via Counter.
    """
    counts = Counter(str(p) for p in prefixes)
    return [(prefix, count) for prefix, count in counts.items() if count > 1]
