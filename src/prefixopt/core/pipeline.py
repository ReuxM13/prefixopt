"""
Central processing pipeline for prefix lists.

``process_prefixes`` is the orchestrator used by most CLI/GUI operations. It
chains a configurable sequence of stages (filter -> sort -> remove nested ->
aggregate) over an iterable of networks.

Design notes:
    * Filtering and version selection are done lazily via generators so that
      small operations don't pay to materialise huge inputs.
    * Sorting, nested-removal and aggregation inevitably need the whole set in
      memory, so they are deferred until actually requested.
    * The function returns an *iterable* (sometimes a generator, sometimes a
      list) - callers that need to reuse the result should wrap it in list().
"""

from typing import Iterable

from .ip_utils import IPNet

# Operations are imported with explicit aliases to avoid name clashes with the
# boolean flags of this function (e.g. ``aggregate`` the flag vs. the function).
from .operations import aggregate as aggregate_op
from .operations import remove_nested as remove_nested_op
from .operations import sort_networks as sort_networks_op
from .operations import filter_special as filter_special_op


def process_prefixes(
    networks: Iterable[IPNet],
    sort: bool = True,
    remove_nested: bool = True,
    aggregate: bool = True,
    ipv4_only: bool = False,
    ipv6_only: bool = False,
    exclude_private: bool = False,
    exclude_loopback: bool = False,
    exclude_link_local: bool = False,
    exclude_multicast: bool = False,
    exclude_reserved: bool = False,
    exclude_unspecified: bool = False,
    bogons: bool = False,
) -> Iterable[IPNet]:
    """Run a chain of prefix-processing stages.

    Args:
        networks:           Input networks.
        sort:               Sort broadest-first (required by later stages).
        remove_nested:      Drop subnets covered by an already-present parent.
        aggregate:          Merge adjacent CIDRs into supernets where possible.
        ipv4_only:          Keep only IPv4 networks.
        ipv6_only:          Keep only IPv6 networks.
        exclude_private:    Drop RFC1918 / ULA space.
        exclude_loopback:   Drop loopback networks.
        exclude_link_local: Drop link-local networks.
        exclude_multicast:  Drop multicast networks.
        exclude_reserved:   Drop IETF-reserved networks.
        exclude_unspecified:Drop 0.0.0.0/:: and default routes (prefixlen 0).
        bogons:             Shortcut that enables every ``exclude_*`` flag.

    Returns:
        An iterable of processed networks.
    """
    current_data: Iterable[IPNet] = networks

    # ---- Stage 1: streaming filters (no full materialisation needed) ----

    # Version filtering is mutually exclusive; v4 takes precedence if both are
    # somehow set, mirroring the CLI semantics.
    if ipv4_only:
        current_data = (n for n in current_data if n.version == 4)
    elif ipv6_only:
        current_data = (n for n in current_data if n.version == 6)

    # The "bogons" shortcut simply turns on every special-range filter.
    if bogons:
        exclude_private = exclude_loopback = exclude_link_local = (
            exclude_multicast
        ) = exclude_reserved = exclude_unspecified = True

    if any(
        [
            exclude_private,
            exclude_loopback,
            exclude_link_local,
            exclude_multicast,
            exclude_reserved,
            exclude_unspecified,
        ]
    ):
        current_data = filter_special_op(
            current_data,
            exclude_private=exclude_private,
            exclude_loopback=exclude_loopback,
            exclude_link_local=exclude_link_local,
            exclude_multicast=exclude_multicast,
            exclude_reserved=exclude_reserved,
            exclude_unspecified=exclude_unspecified,
        )

    # ---- Stage 2: global operations (require the data in memory) ----

    # Tracks whether the data is currently in broadest-first sorted order,
    # so downstream stages can skip redundant sorts.
    is_sorted_broadest = False

    if sort:
        # sort_networks internally calls list() on the iterable.
        current_data = sort_networks_op(current_data)
        is_sorted_broadest = True

    if remove_nested:
        current_data = remove_nested_op(
            current_data, assume_sorted=is_sorted_broadest
        )
        # remove_nested always returns a sorted list.
        is_sorted_broadest = True

    if aggregate:
        # Aggregation needs sorted input; ensure it if previous stages were off.
        if not is_sorted_broadest:
            current_data = sort_networks_op(current_data)
            is_sorted_broadest = True

        current_data = aggregate_op(current_data)

    return current_data
