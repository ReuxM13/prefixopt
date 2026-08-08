"""
CIDR aggregation: merge adjacent networks into their common supernet.

Example:
    Input:   [192.168.0.0/24, 192.168.1.0/24]
    Output:  [192.168.0.0/23]

The implementation is the classic "CIDR stack" algorithm. Networks must be
sorted broadest-first (see :mod:`sorter`). Each new network is pushed onto a
stack; while the top two entries are siblings (same prefix length, contiguous
address ranges, aligned so they together form a valid supernet), they are
popped and replaced by that supernet. This is repeated because the resulting
supernet may itself be sibling to the next item down.

Worst-case complexity is O(N) because every network is pushed and popped at
most once.
"""

from typing import Iterable, List, Union

from ipaddress import IPv4Network, IPv6Network


def aggregate(
    networks: Iterable[Union[IPv4Network, IPv6Network]],
) -> List[Union[IPv4Network, IPv6Network]]:
    """Aggregate adjacent, equal-length networks into supernets.

    Args:
        networks: Sorted iterable of networks (broadest-first). The function
                  does not sort internally - callers that need robust
                  behaviour should sort first.

    Returns:
        A new, potentially shorter list of networks.
    """
    # The stack holds the partially-aggregated prefixes in order.
    stack: List[Union[IPv4Network, IPv6Network]] = []

    for net in networks:
        stack.append(net)

        # Collapse the top of the stack as much as possible.
        while len(stack) >= 2:
            right = stack[-1]
            left = stack[-2]

            # Siblings must be the same protocol and same prefix length.
            if left.version != right.version or left.prefixlen != right.prefixlen:
                break

            # They must be contiguous: left's broadcast immediately precedes
            # right's network address.
            if int(left.broadcast_address) + 1 != int(right.network_address):
                break

            try:
                supernet = left.supernet(prefixlen_diff=1)

                # Only merge if left is the first half of the supernet; this
                # guards against merging across alignment boundaries.
                if supernet.network_address == left.network_address:
                    stack.pop()
                    stack.pop()
                    stack.append(supernet)
                    # Loop again: the new supernet may now pair with its sibling.
                    continue
            except (ValueError, IndexError):
                # supernet() raises for /0; in that case there is nothing to do.
                pass

            break

    return stack
