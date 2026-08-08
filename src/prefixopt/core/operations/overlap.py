"""
Find overlapping networks between (or within) prefix lists.

The overlap analysis powers the ``intersect`` command and the GUI's intersect
tab. There are two main entry points:

* :func:`find_two_list_overlaps` - two-pointer scan over two *sorted* lists
  that reports every pair of networks whose address ranges intersect.
* :func:`find_self_overlaps` - scan a single sorted list and report internal
  conflicts (a network covered by another in the same file).

:func:`classify_overlap_pair` then turns a raw pair into a structured
description (which side is the subnet vs supernet, and which source each came
from), while :func:`build_intersection_fragments` yields the concrete prefixes
that represent the shared address space.
"""

from typing import Dict, List, Set, Tuple

from ..ip_utils import IPNet


def find_two_list_overlaps(
    sorted_a: List[IPNet],
    sorted_b: List[IPNet],
) -> List[Tuple[IPNet, IPNet]]:
    """Find overlapping pairs between two sorted network lists in O(N+M).

    Both inputs must be sorted broadest-first (see :func:`sorter.sort_networks`).
    The two-pointer scan advances whichever list element has the smaller
    broadcast address, much like merging two sorted ranges.

    Args:
        sorted_a: First sorted list.
        sorted_b: Second sorted list.

    Returns:
        All ``(a, b)`` pairs whose address ranges overlap. Exact matches are
        included.
    """
    overlaps: List[Tuple[IPNet, IPNet]] = []
    i, j = 0, 0
    len_a, len_b = len(sorted_a), len(sorted_b)

    while i < len_a and j < len_b:
        n1, n2 = sorted_a[i], sorted_b[j]

        # Keep the two pointers on the same IP version.
        if n1.version < n2.version:
            i += 1
            continue
        if n1.version > n2.version:
            j += 1
            continue

        # Numeric bounds make overlap math trivial.
        s1 = int(n1.network_address)
        e1 = int(n1.broadcast_address)
        s2 = int(n2.network_address)
        e2 = int(n2.broadcast_address)

        # Two ranges overlap when the later start is <= the earlier end.
        if max(s1, s2) <= min(e1, e2):
            overlaps.append((n1, n2))
            # Advance the one that ends earlier so we don't miss later pairs.
            if e1 < e2:
                i += 1
            elif e2 < e1:
                j += 1
            else:
                i += 1
                j += 1
        elif e1 < s2:
            # n1 is entirely before n2 - move the first pointer on.
            i += 1
        else:
            j += 1

    return overlaps


def find_self_overlaps(
    sorted_list: List[IPNet],
) -> List[Tuple[IPNet, IPNet]]:
    """Find pairs of overlapping networks inside one sorted list.

    The outer loop walks each network; the inner loop only needs to examine
    following networks whose start is still within the current network's
    broadcast address, which keeps the average cost low on clean inputs.
    """
    overlaps: List[Tuple[IPNet, IPNet]] = []
    length = len(sorted_list)

    for i in range(length):
        net_i = sorted_list[i]
        end_i = int(net_i.broadcast_address)

        for j in range(i + 1, length):
            net_j = sorted_list[j]

            # A new IP version can't overlap with the previous one.
            if net_i.version != net_j.version:
                break
            # Once we've passed net_i's end there can be no further overlap.
            if int(net_j.network_address) > end_i:
                break

            overlaps.append((net_i, net_j))

    return overlaps


def classify_overlap_pair(
    net_a: IPNet,
    net_b: IPNet,
    name_a: str,
    name_b: str,
) -> Tuple[bool, IPNet, IPNet, str, str]:
    """Classify a raw overlap pair into (is_ident, subnet, supernet, src_sub, src_super).

    The returned tuple always identifies the *smaller* network as ``subnet``
    and the *larger* as ``supernet``, together with which source each came
    from. This lets callers render a uniform report without re-checking
    containment themselves.

    Args:
        net_a, net_b: The overlapping networks.
        name_a, name_b: Labels (typically file names) for each source.

    Returns:
        ``(is_identical, subnet, supernet, subnet_source, supernet_source)``.
    """
    if net_a == net_b:
        return True, net_a, net_b, name_a, name_b

    if net_a.subnet_of(net_b):
        return False, net_a, net_b, name_a, name_b

    if net_b.subnet_of(net_a):
        return False, net_b, net_a, name_b, name_a

    # Partial overlap (neither fully contains the other): return both as-is.
    return False, net_a, net_b, name_a, name_b


def build_intersection_fragments(
    exact_matches: Set[IPNet],
    raw_overlaps: List[Tuple[IPNet, IPNet]],
) -> List[IPNet]:
    """Collect the concrete fragments representing shared address space.

    Exact matches are included verbatim. For nested overlaps only the smaller
    (inner) network is added, because that is the fragment actually contained
    in both sources. Partial overlaps (where neither contains the other) are
    not represented here; callers render them separately.

    Args:
        exact_matches: Networks identical in both sources.
        raw_overlaps:  Pairs produced by :func:`find_two_list_overlaps`.

    Returns:
        A list of networks covering the exact intersections.
    """
    fragments: List[IPNet] = list(exact_matches)
    for net1, net2 in raw_overlaps:
        if net1 == net2:
            continue
        if net1.subnet_of(net2):
            fragments.append(net1)
        elif net2.subnet_of(net1):
            fragments.append(net2)
    return fragments
