"""
Sort IP networks in "broadest first" order.

Ordering key:
    1. IP version          (4 before 6 - keeps families grouped together)
    2. network address     (numeric, ascending)
    3. prefix length       (shorter mask / larger network first)

This ordering is a prerequisite for the linear nested-removal and aggregation
algorithms: they rely on a parent network appearing before its children and
on adjacent networks being neighbours in the sequence.
"""

from typing import Iterable, List, Union

from ipaddress import IPv4Network, IPv6Network


def sort_networks(
    networks: Iterable[Union[IPv4Network, IPv6Network]],
) -> List[Union[IPv4Network, IPv6Network]]:
    """Return a new list containing ``networks`` sorted broadest-first.

    The input iterable is not modified.
    """
    def sort_key(net: Union[IPv4Network, IPv6Network]):
        # Casting network_address to int enables numeric comparison.
        """Sort key."""
        return (
            net.version,
            int(net.network_address),
            net.prefixlen,
        )

    return sorted(networks, key=sort_key)
