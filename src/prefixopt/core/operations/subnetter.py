"""
De-aggregate (split) a network into smaller subnets of a fixed prefix length.

Example:
    split_network(192.168.1.0/24, 25) -> [192.168.1.0/25, 192.168.1.128/25]

A safety limit (``max_subnets``) prevents accidental explosion when a user
asks, for example, to split 10.0.0.0/8 into /32s - that would be ~16 million
networks. The CLI uses a conservative default; tests can lower it.
"""

from typing import List, Union

from ipaddress import IPv4Network, IPv6Network


def split_network(
    network: Union[IPv4Network, IPv6Network],
    target_length: int,
    max_subnets: int = 500_000,
) -> List[Union[IPv4Network, IPv6Network]]:
    """Split ``network`` into subnets of prefix length ``target_length``.

    Args:
        network:       Network to split.
        target_length: Desired prefix length. Must be >= the network's current
                       prefix length (you can only split *into smaller* nets).
        max_subnets:   Safety cap on how many subnets may be produced.

    Returns:
        List of subnets.

    Raises:
        ValueError: If the target length is invalid or would produce more
                    than ``max_subnets`` networks.
    """
    # You can't aggregate by splitting into a shorter prefix.
    if target_length < network.prefixlen:
        raise ValueError(
            f"Target prefix length ({target_length}) must be greater than or "
            f"equal to current prefix length ({network.prefixlen})"
        )

    # Protocol-specific maximum prefix lengths.
    if network.version == 4:
        if target_length > 32:
            raise ValueError("Target prefix length for IPv4 cannot be greater than 32")
    else:
        if target_length > 128:
            raise ValueError("Target prefix length for IPv6 cannot be greater than 128")

    # Number of subnets is 2 raised to the difference in prefix lengths.
    prefix_diff = target_length - network.prefixlen
    num_subnets = 2**prefix_diff

    if num_subnets > max_subnets:
        raise ValueError(
            f"Splitting {network} to /{target_length} would create "
            f"{num_subnets} subnets, which exceeds the maximum allowed "
            f"({max_subnets}). Operation cancelled for safety."
        )

    # The standard library does the heavy lifting.
    subnets = list(network.subnets(new_prefix=target_length))
    return subnets
