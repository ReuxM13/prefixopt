"""
High-level Python API for using prefixopt from other scripts.

Every public function here accepts a flexible *source* (see
:data:`InputSource`): a file path, a free-form string, or an iterable of
strings/networks. They return plain Python objects (lists of networks or
``(network, comment)`` tuples) - they never print to the console, which makes
them easy to embed in automation.

The CLI and GUI sit on top of these functions (the GUI additionally has its
own :mod:`prefixopt.gui.services` bridge with more features), so this module
is the most stable integration surface for library users.
"""

import ipaddress
import itertools
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Tuple, Union

from .core.ip_counter import get_prefix_statistics
from .core.ip_utils import IPNet, is_subnet_of, normalize_prefix
from .core.operations.diff import calculate_diff
from .core.operations.overlap import find_two_list_overlaps
from .core.operations.subnetter import split_network
from .core.operations.subtractor import subtract_networks
from .core.pipeline import process_prefixes
from .data.file_reader import (
    extract_prefixes_from_text,
    read_networks,
    read_prefixes_with_comments,
)

# A source accepted by the API can be a path, raw text, or an iterable of
# strings/IPNet objects.
InputSource = Union[str, Path, Iterable[Union[str, IPNet]]]


def load(source: InputSource) -> Iterator[IPNet]:
    """Convert any supported input into an iterator of :data:`IPNet` objects.

    Resolution order:
        1. If ``source`` is an existing file path, read networks from it.
        2. If it is a string that looks like a path, read that file; otherwise
           parse it as raw text containing IPs/prefixes.
        3. If it is an iterable, yield each item (IPNet objects pass through;
           everything else is parsed as text).

    Raises:
        ValueError: for unsupported input types.
    """
    if isinstance(source, Path):
        if source.exists():
            yield from read_networks(source, show_progress=False)
            return

    if isinstance(source, str):
        # Treat short strings that resolve to an existing file as a path,
        # otherwise fall back to parsing the text itself.
        try:
            path_obj = Path(source)
            if len(source) < 255 and path_obj.exists():
                yield from read_networks(path_obj, show_progress=False)
                return
        except OSError:
            pass

        yield from extract_prefixes_from_text(source)
        return

    if isinstance(source, Iterable) and not isinstance(source, bytes):
        for item in source:
            if isinstance(
                item, (ipaddress.IPv4Network, ipaddress.IPv6Network)
            ):
                yield item
            else:
                yield from extract_prefixes_from_text(str(item))
        return

    raise ValueError(f"Unsupported input type: {type(source)}")


def _optimize_with_comments(source: InputSource) -> List[Tuple[IPNet, str]]:
    """Internal helper: optimise a source while preserving inline comments.

    Reads prefixes with comments, deduplicates by canonical prefix string
    (preferring a non-empty comment when collisions occur), and returns a
    broadest-first sorted list.
    """
    data_iter: Iterator[Tuple[IPNet, str]]

    # Detect whether the source is a real file so we can stream comments from
    # disk; non-file sources fall back to load().
    is_file = False
    if isinstance(source, Path) and source.exists():
        is_file = True
    elif isinstance(source, str):
        try:
            p = Path(source)
            if len(source) < 255 and p.exists():
                is_file = True
        except OSError:
            pass

    if is_file:
        path_ref = Path(str(source))
        data_iter = read_prefixes_with_comments(path_ref)
    else:
        data_iter = ((net, "") for net in load(source))

    unique_map: Dict[str, str] = {}
    for ip, comment in data_iter:
        ip_str = str(ip)
        if ip_str not in unique_map:
            unique_map[ip_str] = comment
        elif not unique_map[ip_str] and comment:
            unique_map[ip_str] = comment

    merged_list = []
    for ip_str_key, comm in unique_map.items():
        net_obj = ipaddress.ip_network(ip_str_key, strict=False)
        merged_list.append((net_obj, comm))

    merged_list.sort(
        key=lambda item: (
            item[0].version,
            int(item[0].network_address),
            item[0].prefixlen,
        )
    )
    return merged_list


def optimize(
    source: InputSource,
    ipv4_only: bool = False,
    ipv6_only: bool = False,
    remove_nested: bool = True,
    aggregate: bool = True,
    bogons: bool = False,
    keep_comments: bool = False,
) -> Union[List[IPNet], List[Tuple[IPNet, str]]]:
    """Optimise a prefix list (sort, remove nested, optionally aggregate).

    Args:
        source:        Input data.
        ipv4_only:     Keep only IPv4 networks.
        ipv6_only:     Keep only IPv6 networks.
        remove_nested: Drop subnets covered by a parent.
        aggregate:     Merge adjacent CIDRs.
        bogons:        Drop all special-use ranges.
        keep_comments: When True, return ``(network, comment)`` tuples and
                       disable aggregation.

    Returns:
        A list of networks or a list of (network, comment) pairs.
    """
    if keep_comments:
        return _optimize_with_comments(source)

    iterator = load(source)
    result_iter = process_prefixes(
        iterator,
        sort=True,
        remove_nested=remove_nested,
        aggregate=aggregate,
        ipv4_only=ipv4_only,
        ipv6_only=ipv6_only,
        bogons=bogons,
    )
    return list(result_iter)


def add(
    source: InputSource,
    new_prefix: str,
    keep_comments: bool = False,
) -> Union[List[IPNet], List[Tuple[IPNet, str]]]:
    """Add a single prefix to a list and re-optimise.

    In comment mode the new prefix is tagged with ``# Added: <prefix>``.
    """
    net = normalize_prefix(new_prefix)

    if keep_comments:
        data = _optimize_with_comments(source)
        exists = any(item[0] == net for item in data)
        if not exists:
            data.append((net, f"# Added: {new_prefix}"))
            data.sort(
                key=lambda item: (
                    item[0].version,
                    int(item[0].network_address),
                    item[0].prefixlen,
                )
            )
        return data

    data_list = list(load(source))
    if net not in data_list:
        data_list.append(net)

    return optimize(data_list)


def filter(
    source: InputSource,
    exclude_private: bool = False,
    bogons: bool = False,
) -> List[IPNet]:
    """Filter special-use networks without aggregating the result.

    Args:
        source:          Input data.
        exclude_private: Drop RFC1918/ULA ranges.
        bogons:          Drop all special-use ranges.

    Returns:
        The surviving networks (in input order).
    """
    iterator = load(source)
    result_iter = process_prefixes(
        iterator,
        sort=False,
        remove_nested=False,
        aggregate=False,
        exclude_private=exclude_private,
        bogons=bogons,
        exclude_unspecified=True,
    )
    return list(result_iter)


def merge(
    *sources: InputSource,
    keep_comments: bool = False,
) -> Union[List[IPNet], List[Tuple[IPNet, str]]]:
    """Merge any number of sources into one optimised list.

    With ``keep_comments`` the function deduplicates prefixes but does not
    aggregate, preserving each surviving prefix's comment.
    """
    if keep_comments:
        all_data: List[Tuple[IPNet, str]] = []
        for src in sources:
            all_data.extend(_optimize_with_comments(src))

        unique_map: Dict[str, str] = {}
        for ip, comment in all_data:
            ip_str = str(ip)
            if ip_str not in unique_map:
                unique_map[ip_str] = comment
            elif not unique_map[ip_str] and comment:
                unique_map[ip_str] = comment

        merged_list = []
        for ip_str_key, comm in unique_map.items():
            net_obj = ipaddress.ip_network(ip_str_key, strict=False)
            merged_list.append((net_obj, comm))

        merged_list.sort(
            key=lambda item: (
                item[0].version,
                int(item[0].network_address),
                item[0].prefixlen,
            )
        )
        return merged_list

    combined_iter = itertools.chain.from_iterable(
        load(src) for src in sources
    )
    result_iter = process_prefixes(
        combined_iter, sort=True, remove_nested=True, aggregate=True
    )
    return list(result_iter)


def intersect(source_a: InputSource, source_b: InputSource) -> List[IPNet]:
    """Return the networks that participate in an overlap between two lists.

    The result includes exact matches plus both sides of any partial overlap,
    then is optimised. This is intentionally broader than a strict set
    intersection so callers can review conflicts.
    """
    list_a = list(load(source_a))
    list_b = list(load(source_b))

    sorted_a = sorted(
        list_a,
        key=lambda n: (n.version, int(n.network_address), n.prefixlen),
    )
    sorted_b = sorted(
        list_b,
        key=lambda n: (n.version, int(n.network_address), n.prefixlen),
    )

    set_a = set(list_a)
    set_b = set(list_b)
    common = set_a.intersection(set_b)

    raw_overlaps = find_two_list_overlaps(sorted_a, sorted_b)
    for net1, net2 in raw_overlaps:
        if net1 == net2:
            continue
        if net1 in common or net2 in common:
            continue
        common.add(net1)
        common.add(net2)

    return optimize(list(common))


def split(target: str, length: int) -> List[IPNet]:
    """Split one network into subnets of the given prefix length."""
    net = normalize_prefix(target)
    return split_network(net, length)


def exclude(source: InputSource, target: InputSource) -> List[IPNet]:
    """Subtract networks in ``target`` from ``source`` (hole punching)."""
    src_iter = load(source)
    dst_iter = load(target)

    raw_result = subtract_networks(src_iter, dst_iter)

    final_iter = process_prefixes(
        raw_result, sort=True, remove_nested=True, aggregate=True
    )
    return list(final_iter)


def diff(
    new_source: InputSource,
    old_source: InputSource,
) -> Tuple[List[IPNet], List[IPNet], List[IPNet]]:
    """Semantic diff: returns ``(added, removed, unchanged)`` prefix sets.

    Both sides are optimised first so equivalent CIDR decompositions compare
    as equal.
    """

    def prepare(src: InputSource) -> List[IPNet]:
        """Prepare."""
        return list(
            process_prefixes(
                load(src),
                sort=True,
                remove_nested=True,
                aggregate=True,
            )
        )

    new_list = prepare(new_source)
    old_list = prepare(old_source)

    added, removed, unchanged = calculate_diff(new_list, old_list)

    def to_sorted_list(data_set):
        """Convert to sorted list."""
        return list(
            process_prefixes(
                data_set,
                sort=True,
                remove_nested=False,
                aggregate=False,
            )
        )

    return (
        to_sorted_list(added),
        to_sorted_list(removed),
        to_sorted_list(unchanged),
    )


def stats(source: InputSource) -> Dict[str, Union[int, float]]:
    """Return a dictionary of summary statistics for a prefix list."""
    data_list = list(load(source))
    return get_prefix_statistics(data_list)


def check(target: str, source: InputSource) -> List[IPNet]:
    """Return every network in ``source`` that contains ``target``.

    ``target`` may be an IP address or a CIDR. Returns an empty list when the
    target is not covered at all.
    """
    try:
        check_item = ipaddress.ip_network(target, strict=False)
    except ValueError:
        try:
            check_item = ipaddress.ip_address(target)
        except ValueError:
            return []

    containing = []
    for net in load(source):
        if net.version != check_item.version:
            continue

        if isinstance(
            check_item, (ipaddress.IPv4Address, ipaddress.IPv6Address)
        ):
            if check_item in net:
                containing.append(net)
        else:
            if is_subnet_of(check_item, net):
                containing.append(net)

    return containing


def merge_with_comments(
    file1: Union[str, Path],
    file2: Union[str, Path],
) -> List[Tuple[IPNet, str]]:
    """Legacy helper kept for backward compatibility.

    Equivalent to ``merge(file1, file2, keep_comments=True)``.
    """
    return merge(file1, file2, keep_comments=True)
