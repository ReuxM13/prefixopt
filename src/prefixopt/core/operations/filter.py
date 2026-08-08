"""
Filter out "special" IP ranges (private, loopback, multicast, reserved, ...).

This is implemented as a lazy generator so very large lists can be streamed
without materialising them. It delegates the actual classification to
attributes already provided by the standard-library :mod:`ipaddress` module
(``is_private``, ``is_loopback``, etc.).
"""

from typing import Iterable, Iterator, Union

from ipaddress import IPv4Network, IPv6Network


def filter_special(
    networks: Iterable[Union[IPv4Network, IPv6Network]],
    exclude_private: bool = False,
    exclude_loopback: bool = False,
    exclude_link_local: bool = False,
    exclude_multicast: bool = False,
    exclude_reserved: bool = False,
    exclude_unspecified: bool = False,
) -> Iterator[Union[IPv4Network, IPv6Network]]:
    """Yield networks that pass all the enabled exclusion filters.

    Args:
        networks:           Input networks.
        exclude_private:    Drop RFC1918 (IPv4) / ULA (IPv6) networks.
        exclude_loopback:   Drop loopback networks.
        exclude_link_local: Drop link-local networks.
        exclude_multicast:  Drop multicast networks.
        exclude_reserved:   Drop IETF-reserved networks.
        exclude_unspecified:Drop 0.0.0.0/:: hosts *and* default routes
                            (prefix length 0).

    Yields:
        Networks that were not excluded.
    """
    for network in networks:
        # Each check is independent - order doesn't matter, but we short-circuit
        # as soon as one flag rejects the network.
        if exclude_private and network.is_private:
            continue
        if exclude_loopback and network.is_loopback:
            continue
        if exclude_link_local and network.is_link_local:
            continue
        if exclude_multicast and network.is_multicast:
            continue
        if exclude_reserved and network.is_reserved:
            continue
        # prefixlen == 0 catches the default route 0.0.0.0/0 and ::/0 which
        # is_unspecified alone does not classify.
        if exclude_unspecified and (
            network.is_unspecified or network.prefixlen == 0
        ):
            continue

        yield network
