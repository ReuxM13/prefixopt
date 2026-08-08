"""
Remove networks that are nested inside another network in the list.

Example:
    Input:   [10.0.0.0/8, 10.0.0.0/24]
    Output:  [10.0.0.0/8]

The algorithm is O(N) when the input is pre-sorted broadest-first because a
parent always precedes its children. If the caller has already sorted the data
it can pass ``assume_sorted=True`` to skip the redundant sort.
"""

from typing import Iterable, List, Union

from ipaddress import IPv4Network, IPv6Network


def remove_nested(
    networks: Iterable[Union[IPv4Network, IPv6Network]],
    assume_sorted: bool = False,
) -> List[Union[IPv4Network, IPv6Network]]:
    """Drop subnets that are covered by an earlier, broader network.

    Args:
        networks:      Input networks.
        assume_sorted: When ``True``, the caller guarantees the input is
                       sorted broadest-first. When ``False``, we sort here.

    Returns:
        A new list without redundant nested entries.
    """
    if assume_sorted:
        sorted_networks = (
            networks if isinstance(networks, list) else list(networks)
        )
    else:
        sorted_networks = sorted(
            networks,
            key=lambda net: (
                net.version,
                int(net.network_address),
                net.prefixlen,
            ),
        )

    if not sorted_networks:
        return []

    optimized: List[Union[IPv4Network, IPv6Network]] = []

    # Seed with the broadest first network; it is the reference parent.
    last_added = sorted_networks[0]
    optimized.append(last_added)

    for current in sorted_networks[1:]:
        # A new IP version can never be nested in the previous one.
        if current.version != last_added.version:
            optimized.append(current)
            last_added = current
            continue

        # If the current network is inside the last added parent it is redundant.
        if current.subnet_of(last_added):
            continue

        # Otherwise keep it and treat it as the active parent going forward.
        optimized.append(current)
        last_added = current

    return optimized
