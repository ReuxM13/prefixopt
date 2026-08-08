"""
Shared helpers and type aliases for the core layer.

This is a deliberately small module - it avoids importing the heavy algorithm
modules so that anything needing just the :data:`IPNet` type or a normaliser
can depend on it cheaply.
"""

import ipaddress
from ipaddress import IPv4Network, IPv6Network
from typing import Literal, Union


# A network in prefixopt is always either an IPv4 or an IPv6 network.
# Using a single alias everywhere keeps signatures short and consistent.
IPNet = Union[IPv4Network, IPv6Network]


def normalize_prefix(s: str, strict: bool = False) -> IPNet:
    """Convert a string into a valid IP network object.

    Handles three common input shapes:
        * CIDR network     - ``"10.0.0.0/8"``
        * bare IP address  - ``"10.0.0.1"`` (expanded to ``/32`` or ``/128``)
        * network with host bits set, e.g. ``"10.0.0.1/24"``

    Args:
        s:      String to parse.
        strict: When ``True``, host bits being set raises ``ValueError`` with
                a helpful "Did you mean ...?" hint. When ``False`` (default)
                the standard library silently zeroes the host bits.

    Returns:
        An ``IPv4Network`` or ``IPv6Network``.

    Raises:
        ValueError: If the string cannot be interpreted as an IP/network.
    """
    s = s.strip()

    if strict:
        # Strict mode: produce a clear, actionable error for mis-masked nets.
        if "/" in s:
            try:
                return ipaddress.ip_network(s, strict=True)
            except ValueError as exc:
                # Figure out the canonical network so we can suggest it.
                try:
                    corrected = ipaddress.ip_network(s, strict=False)
                except ValueError:
                    raise ValueError(f"Cannot normalize '{s}' to an IP network") from exc

                raise ValueError(
                    f"Invalid network '{s}': host bits are set. "
                    f"Did you mean '{corrected}'?"
                ) from exc

        # No mask => treat as a single host route.
        try:
            ip = ipaddress.ip_address(s)
        except ValueError as exc:
            raise ValueError(f"Cannot normalize '{s}' to an IP network") from exc

        if ip.version == 4:
            return ipaddress.IPv4Network(f"{ip}/32", strict=False)
        return ipaddress.IPv6Network(f"{ip}/128", strict=False)

    # Lenient mode: let ipaddress zero host bits itself.
    try:
        return ipaddress.ip_network(s, strict=False)
    except ValueError:
        # Maybe it was a bare address - promote it to a /32 or /128.
        try:
            ip = ipaddress.ip_address(s)
        except ValueError as exc:
            raise ValueError(f"Cannot normalize '{s}' to an IP network") from exc

        if ip.version == 4:
            return ipaddress.IPv4Network(f"{ip}/32", strict=False)
        return ipaddress.IPv6Network(f"{ip}/128", strict=False)


def get_version(net: IPNet) -> Literal[4, 6]:
    """Return the IP version (4 or 6) of a network."""
    return net.version


def is_subnet_of(a: IPNet, b: IPNet) -> bool:
    """Return ``True`` if network ``a`` is contained within network ``b``.

    Thin safety wrapper around :meth:`IPv4Network.subnet_of` that also guards
    against comparing IPv4 with IPv6 (which would otherwise raise ``TypeError``).

    Args:
        a: Candidate inner network.
        b: Candidate outer network.

    Returns:
        ``True`` when ``a`` is equal to or a subnet of ``b``.
    """
    # Different address families can never contain each other.
    if a.version != b.version:
        return False

    if isinstance(a, IPv4Network) and isinstance(b, IPv4Network):
        return a.subnet_of(b)
    if isinstance(a, IPv6Network) and isinstance(b, IPv6Network):
        return a.subnet_of(b)

    return False
