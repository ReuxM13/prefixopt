"""
Service layer for the GUI.

Each ``run_*`` function performs one complete operation: it loads inputs from
either a file path or raw text, calls the core algorithms, and returns a result
dataclass (see ``models.py``) containing a ready-to-display ``formatted_text``.
Functions are executed off the GUI thread by ``Worker`` so the UI stays
responsive. This module is the GUI equivalent of the CLI command modules but
returns structured objects instead of printing to stdout.

Key entry points: run_optimize, run_add, run_filter, run_merge, run_exclude,
run_split, run_diff, run_intersect, run_multi_intersect, run_stats, run_check.
"""


import io
import ipaddress
from pathlib import Path
from typing import (
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Tuple,
    Union,
)

from ..comments import apply_append_comment, merge_comments, normalize_comment
from ..core.ip_counter import count_unique_ips, get_duplicate_prefixes, get_prefix_statistics
from ..core.operations.filter import filter_special
from ..core.ip_utils import IPNet, is_subnet_of, normalize_prefix
from ..core.operations.diff import calculate_diff
from ..core.operations.sorter import sort_networks
from ..core.operations.subnetter import split_network
from ..core.operations.subtractor import subtract_networks
from ..core.operations.overlap import find_two_list_overlaps, find_self_overlaps, classify_overlap_pair, build_intersection_fragments
from ..core.pipeline import process_prefixes
from ..data.file_reader import (
    extract_prefixes_from_text,
    read_networks,
    read_prefixes_with_comments,
    read_stream,
)
from .models import (
    CheckResult,
    DiffReport,
    ExcludeResult,
    FilterResult,
    IntersectReport,
    MergeResult,
    MultiIntersectReport,
    OptimizeResult,
    PairwiseExact,
    PairwisePartial,
    SplitResult,
    StatsResult,
)
from .output_formatter import format_prefixes

InputSource = Union[Path, str]


def _load_networks(
    source: InputSource,
    strict: bool = False,
) -> Iterator[IPNet]:
    """Load networks from a file path or raw text, yielding IPNet objects."""
    if isinstance(source, Path):
        yield from read_networks(source, show_progress=False, strict=strict)
    else:
        # Parse the text line by line (mirroring the CLI's STDIN reader) so
        # that duplicates on separate lines are preserved and per-line ranges
        # behave identically to file input.
        yield from read_stream(io.StringIO(source), strict=strict)


def _load_with_comments(
    source: InputSource,
    strict: bool = False,
) -> Iterator[Tuple[IPNet, str]]:
    """Load (network, comment) pairs from a file path or raw text. For string input, text after the first '#' on each line becomes the comment."""
    if isinstance(source, Path):
        yield from read_prefixes_with_comments(source, strict=strict)
    else:
        for line in source.splitlines():
            line_stripped = line.strip()
            if not line_stripped:
                continue

            comment = ""
            content = line_stripped

            if "#" in line_stripped:
                parts = line_stripped.split("#", 1)
                content = parts[0].strip()
                raw_comment = parts[1].strip()
                if raw_comment:
                    comment = f"# {raw_comment}"

            prefixes = extract_prefixes_from_text(content, strict=strict)
            for p in prefixes:
                yield (p, comment)


def _deduplicate_commented(
    source: Iterable[Tuple[IPNet, str]],
    ipv4_only: bool = False,
    ipv6_only: bool = False,
) -> List[Tuple[IPNet, str]]:
    """Deduplicate networks preserving a non-empty comment, then sort broadest-first."""
    unique_map: dict[str, str] = {}

    for net, comment in source:
        if ipv4_only and net.version != 4:
            continue
        if ipv6_only and net.version != 6:
            continue

        net_str = str(net)

        if net_str not in unique_map:
            unique_map[net_str] = comment
        elif not unique_map[net_str] and comment:
            unique_map[net_str] = comment

    result: List[Tuple[IPNet, str]] = []
    for net_str, comm in unique_map.items():
        net_obj = ipaddress.ip_network(net_str, strict=False)
        result.append((net_obj, comm))

    result.sort(
        key=lambda x: (
            x[0].version,
            int(x[0].network_address),
            x[0].prefixlen,
        )
    )
    return result


def run_optimize(
    source: InputSource,
    fmt: str,
    ipv4_only: bool = False,
    ipv6_only: bool = False,
    keep_comments: bool = False,
    append_comment: Optional[str] = None,
    keep_existing_comments: bool = False,
    strict: bool = False,
) -> OptimizeResult:
    """Optimize a source (sort, remove nested, aggregate). In comment/append mode aggregation is disabled so comments remain meaningful."""
    if append_comment and not keep_existing_comments:
        raw_list = list(_load_networks(source, strict=strict))
        input_count = len(raw_list)
        result_list = list(
            process_prefixes(
                raw_list,
                sort=True,
                remove_nested=True,
                aggregate=True,
                ipv4_only=ipv4_only,
                ipv6_only=ipv6_only,
            )
        )
        commented = [(net, normalize_comment(append_comment)) for net in result_list]
        return OptimizeResult(
            keep_comments=True,
            input_count=input_count,
            output_count=len(result_list),
            commented_prefixes=commented,
            formatted_text=format_prefixes([], fmt, commented=commented),
        )

    if keep_comments or keep_existing_comments or append_comment:
        raw = _load_with_comments(source, strict=strict)
        if append_comment:
            raw = (
                (net, apply_append_comment(comment, append_comment, True))
                for net, comment in raw
            )
        commented = _deduplicate_commented(
            raw, ipv4_only=ipv4_only, ipv6_only=ipv6_only
        )
        formatted_text = format_prefixes([], fmt, commented=commented)

        return OptimizeResult(
            keep_comments=True,
            input_count=len(commented),
            output_count=len(commented),
            commented_prefixes=commented,
            formatted_text=formatted_text,
        )

    raw_list = list(_load_networks(source, strict=strict))
    input_count = len(raw_list)

    result_iter = process_prefixes(
        raw_list,
        sort=True,
        remove_nested=True,
        aggregate=True,
        ipv4_only=ipv4_only,
        ipv6_only=ipv6_only,
    )
    result_list = list(result_iter)
    formatted_text = format_prefixes(result_list, fmt)

    return OptimizeResult(
        keep_comments=False,
        input_count=input_count,
        output_count=len(result_list),
        formatted_text=formatted_text,
    )


def run_add(
    source: InputSource,
    new_prefix: str,
    fmt: str,
    keep_comments: bool = False,
    append_comment: Optional[str] = None,
    keep_existing_comments: bool = False,
    strict: bool = False,
) -> OptimizeResult:
    """Add one prefix to a source and re-optimize or merge it into the commented list."""
    net_to_add = normalize_prefix(new_prefix, strict=strict)

    if append_comment and not keep_existing_comments:
        data = list(_load_networks(source, strict=strict))
        input_count = len(data)
        if net_to_add not in data:
            data.append(net_to_add)
        result = list(
            process_prefixes(data, sort=True, remove_nested=True, aggregate=True)
        )
        commented = [(net, normalize_comment(append_comment)) for net in result]
        formatted_text = format_prefixes([], fmt, commented=commented)
        return OptimizeResult(
            keep_comments=True,
            input_count=input_count + 1,
            output_count=len(result),
            commented_prefixes=commented,
            formatted_text=formatted_text,
        )

    if keep_comments or append_comment:
        raw = _load_with_comments(source, strict=strict)
        commented_map = {str(net): comment for net, comment in _deduplicate_commented(raw)}
        if append_comment:
            for key, comment in list(commented_map.items()):
                commented_map[key] = apply_append_comment(
                    comment, append_comment, keep_existing_comments
                )
        new_key = str(net_to_add)
        if new_key not in commented_map:
            commented_map[new_key] = normalize_comment(append_comment) if append_comment else f"# Added manually: {new_prefix}"
        elif append_comment:
            commented_map[new_key] = apply_append_comment(
                commented_map[new_key], append_comment, keep_existing_comments
            )
        commented = _deduplicate_commented(
            (ipaddress.ip_network(k, strict=False), v) for k, v in commented_map.items()
        )
        formatted_text = format_prefixes([], fmt, commented=commented)

        return OptimizeResult(
            keep_comments=True,
            input_count=len(commented),
            output_count=len(commented),
            commented_prefixes=commented,
            formatted_text=formatted_text,
        )

    data = list(_load_networks(source, strict=strict))
    input_count = len(data)

    if net_to_add not in data:
        data.append(net_to_add)

    result = list(
        process_prefixes(
            data, sort=True, remove_nested=True, aggregate=True
        )
    )
    formatted_text = format_prefixes(result, fmt)

    return OptimizeResult(
        keep_comments=False,
        input_count=input_count + 1,
        output_count=len(result),
        formatted_text=formatted_text,
    )


def run_filter(
    source: InputSource,
    fmt: str,
    exclude_private: bool = False,
    exclude_loopback: bool = False,
    exclude_link_local: bool = False,
    exclude_multicast: bool = False,
    exclude_reserved: bool = False,
    bogons: bool = False,
    keep_comments: bool = False,
    append_comment: Optional[str] = None,
    keep_existing_comments: bool = False,
    strict: bool = False,
) -> FilterResult:
    """Filter special-use networks out of a source. In comment mode each surviving prefix keeps/gets a comment."""
    flags = dict(
        exclude_private=exclude_private or bogons,
        exclude_loopback=exclude_loopback or bogons,
        exclude_link_local=exclude_link_local or bogons,
        exclude_multicast=exclude_multicast or bogons,
        exclude_reserved=exclude_reserved or bogons,
        exclude_unspecified=True,
    )

    if keep_comments or append_comment:
        raw = list(_load_with_comments(source, strict=strict))
        original_count = len(raw)
        result = []
        for net, comment in raw:
            kept = list(filter_special([net], **flags))
            if not kept:
                continue
            if append_comment:
                comment = apply_append_comment(
                    comment if keep_existing_comments else "",
                    append_comment,
                    keep_existing_comments,
                )
            elif keep_comments:
                pass
            else:
                comment = ""
            result.append((kept[0], comment))
        formatted_text = format_prefixes([], fmt, commented=result)
        return FilterResult(
            original_count=original_count,
            removed_count=original_count - len(result),
            formatted_text=formatted_text,
        )

    raw = list(_load_networks(source, strict=strict))
    original_count = len(raw)

    result_iter = filter_special(raw, **flags)
    result = list(result_iter)
    formatted_text = format_prefixes(result, fmt)

    return FilterResult(
        original_count=original_count,
        removed_count=original_count - len(result),
        formatted_text=formatted_text,
    )


def run_merge(
    source1: InputSource,
    source2: InputSource,
    fmt: str,
    keep_comments: bool = False,
    append_comment: Optional[str] = None,
    keep_existing_comments: bool = False,
    strict: bool = False,
) -> MergeResult:
    """Merge two sources. In comment mode Source 2 comments are preserved; Source 1 may get an append-comment."""
    if keep_comments:
        unique_map: dict[str, str] = {}
        annotation = normalize_comment(append_comment)

        # Source 2 = existing (old/base) list.
        for ip, comment in _load_with_comments(source2, strict=strict):
            ip_str = str(ip)
            if ip_str not in unique_map:
                unique_map[ip_str] = comment

        # Source 1 = incoming (new) list. Marker is applied to every Source 1
        # prefix, including duplicates already present in Source 2.
        for ip, comment in _load_with_comments(source1, strict=strict):
            ip_str = str(ip)

            if annotation:
                source1_comment = (
                    comment if keep_existing_comments else ""
                )
                combined = merge_comments(source1_comment, annotation)
            else:
                combined = comment

            if ip_str in unique_map:
                if annotation and not keep_existing_comments:
                    unique_map[ip_str] = combined
                else:
                    unique_map[ip_str] = merge_comments(
                        unique_map[ip_str], combined
                    )
            else:
                unique_map[ip_str] = combined

        commented: List[Tuple[IPNet, str]] = []
        for ip_str, comm in unique_map.items():
            net = ipaddress.ip_network(ip_str, strict=False)
            commented.append((net, comm))

        commented.sort(
            key=lambda x: (
                x[0].version,
                int(x[0].network_address),
                x[0].prefixlen,
            )
        )

        formatted_text = format_prefixes([], fmt, commented=commented)

        return MergeResult(
            keep_comments=True,
            total_count=len(commented),
            commented_prefixes=commented,
            formatted_text=formatted_text,
        )

    list1 = list(_load_networks(source1, strict=strict))
    list2 = list(_load_networks(source2, strict=strict))

    result = list(
        process_prefixes(
            list1 + list2,
            sort=True,
            remove_nested=True,
            aggregate=True,
        )
    )
    formatted_text = format_prefixes(result, fmt)

    return MergeResult(
        keep_comments=False,
        total_count=len(result),
        formatted_text=formatted_text,
    )


def run_intersect(
    source1: InputSource,
    source2: Optional[InputSource] = None,
    strict: bool = False,
    name1: str = "Source A",
    name2: str = "Source B",
) -> IntersectReport:
    """Compute intersections between one/two sources (exact matches and partial overlaps)."""
    list1 = list(_load_networks(source1, strict=strict))
    self_mode = source2 is None

    if self_mode:
        list2 = list1
        name2 = name1
    else:
        list2 = list(_load_networks(source2, strict=strict))

    volume1 = count_unique_ips(list1)
    volume2 = volume1 if self_mode else count_unique_ips(list2)

    sorted1 = sort_networks(list1)

    if self_mode:
        common: set[IPNet] = set()
        raw_overlaps = find_self_overlaps(sorted1)
    else:
        set1 = set(list1)
        set2 = set(list2)
        common = set1.intersection(set2)
        sorted2 = sort_networks(list2)
        raw_overlaps = find_two_list_overlaps(sorted1, sorted2)

    partial_overlaps: List[Tuple[IPNet, IPNet, str, str]] = []

    for net1, net2 in raw_overlaps:
        _, subnet, supernet, src_sub, src_super = classify_overlap_pair(
            net1, net2, name1, name2 if not self_mode else name1
        )
        partial_overlaps.append((subnet, supernet, src_sub, src_super))

    intersection_fragments: List[IPNet] = build_intersection_fragments(common, raw_overlaps)

    volume_intersection = (
        count_unique_ips(intersection_fragments)
        if intersection_fragments
        else 0
    )

    cov1 = (volume_intersection / volume1 * 100) if volume1 > 0 else 0.0
    cov2 = (volume_intersection / volume2 * 100) if volume2 > 0 else 0.0

    all_results = list(common)
    for sub, parent, _, _ in partial_overlaps:
        all_results.extend([sub, parent])
    all_results = sort_networks(list(set(all_results)))

    return IntersectReport(
        exact_matches=sort_networks(list(common)),
        partial_overlaps=partial_overlaps,
        volume1=volume1,
        volume2=volume2,
        volume_intersection=volume_intersection,
        coverage1=cov1,
        coverage2=cov2,
        all_a_in_b=(volume1 > 0 and volume_intersection == volume1),
        all_b_in_a=(volume2 > 0 and volume_intersection == volume2),
        self_mode=self_mode,
        name1=name1,
        name2=name2,
        all_results=all_results,
    )


def run_diff(
    new_source: InputSource,
    old_source: InputSource,
    ipv4_only: bool = False,
    ipv6_only: bool = False,
    strict: bool = False,
) -> DiffReport:

    """Semantic diff: both sources are optimized before comparing."""
    def prepare(src: InputSource) -> List[IPNet]:
        """Read and optimise one side of the diff."""
        raw = _load_networks(src, strict=strict)
        return list(
            process_prefixes(
                raw,
                sort=True,
                remove_nested=True,
                aggregate=True,
                ipv4_only=ipv4_only,
                ipv6_only=ipv6_only,
            )
        )

    new_list = prepare(new_source)
    old_list = prepare(old_source)

    added, removed, unchanged = calculate_diff(new_list, old_list)

    return DiffReport(
        added=sort_networks(list(added)),
        removed=sort_networks(list(removed)),
        unchanged=sort_networks(list(unchanged)),
    )


def run_exclude(
    source: InputSource,
    target: InputSource,
    fmt: str,
    keep_comments: bool = False,
    append_comment: Optional[str] = None,
    keep_existing_comments: bool = False,
    ipv4_only: bool = False,
    ipv6_only: bool = False,
    strict: bool = False,
) -> ExcludeResult:
    """Subtract target from source (hole punching), optionally inheriting/annotating comments."""
    exclude_list = list(_load_networks(target, strict=strict))

    if append_comment and not keep_existing_comments:
        source_list = list(_load_networks(source, strict=strict))
        raw_result = subtract_networks(source_list, exclude_list)
        result = list(
            process_prefixes(
                raw_result,
                sort=True,
                remove_nested=True,
                aggregate=True,
                ipv4_only=ipv4_only,
                ipv6_only=ipv6_only,
            )
        )
        commented = [(net, normalize_comment(append_comment)) for net in result]
        return ExcludeResult(
            keep_comments=True,
            total_count=len(commented),
            commented_prefixes=commented,
            formatted_text=format_prefixes([], fmt, commented=commented),
        )

    if keep_comments or append_comment:
        source_prefixes: List[IPNet] = []
        comments_map: dict[IPNet, str] = {}

        for net, comm in _load_with_comments(source, strict=strict):
            source_prefixes.append(net)
            if comm:
                comments_map[net] = comm

        raw_result = subtract_networks(source_prefixes, exclude_list)
        raw_result.sort(
            key=lambda x: (x.version, int(x.network_address), x.prefixlen)
        )

        commented: List[Tuple[IPNet, str]] = []
        for fragment in raw_result:
            inherited = ""
            if fragment in comments_map:
                inherited = comments_map[fragment]
            else:
                for original in source_prefixes:
                    if (
                        fragment.version == original.version
                        and is_subnet_of(fragment, original)
                    ):
                        if original in comments_map:
                            inherited = comments_map[original]
                            break
            if append_comment:
                inherited = apply_append_comment(
                    inherited, append_comment, keep_existing_comments
                )
            commented.append((fragment, inherited))

        formatted_text = format_prefixes([], fmt, commented=commented)

        return ExcludeResult(
            keep_comments=True,
            total_count=len(commented),
            commented_prefixes=commented,
            formatted_text=formatted_text,
        )

    source_list = list(_load_networks(source, strict=strict))
    raw_result = subtract_networks(source_list, exclude_list)

    result = list(
        process_prefixes(
            raw_result,
            sort=True,
            remove_nested=True,
            aggregate=True,
            ipv4_only=ipv4_only,
            ipv6_only=ipv6_only,
        )
    )
    formatted_text = format_prefixes(result, fmt)

    return ExcludeResult(
        keep_comments=False,
        total_count=len(result),
        formatted_text=formatted_text,
    )


def run_split(
    source: InputSource,
    target_length: int,
    fmt: str = "list",
    keep_comments: bool = False,
    append_comment: Optional[str] = None,
    keep_existing_comments: bool = False,
    strict: bool = False,
) -> SplitResult:
    """Split each source network into subnets of the target prefix length."""
    if keep_comments or append_comment:
        commented: List[Tuple[IPNet, str]] = []
        for net, comment in _load_with_comments(source, strict=strict):
            for sub in split_network(net, target_length):
                inherited = comment if keep_comments or keep_existing_comments else ""
                if append_comment:
                    inherited = apply_append_comment(
                        inherited,
                        append_comment,
                        keep_existing=keep_existing_comments,
                    )
                commented.append((sub, inherited))
        return SplitResult(
            total_count=len(commented),
            formatted_text=format_prefixes([], fmt, commented=commented),
        )

    all_subnets: List[IPNet] = []

    for net in _load_networks(source, strict=strict):
        subs = split_network(net, target_length)
        all_subnets.extend(subs)

    formatted_text = format_prefixes(all_subnets, fmt)

    return SplitResult(
        total_count=len(all_subnets),
        formatted_text=formatted_text,
    )


def run_stats(source: InputSource, strict: bool = False) -> StatsResult:
    """Return summary statistics for a source list."""
    data = list(_load_networks(source, strict=strict))
    raw_stats = get_prefix_statistics(data)

    ipv4_count = len([p for p in data if p.version == 4])
    ipv6_count = len([p for p in data if p.version == 6])

    duplicates = get_duplicate_prefixes(data)

    return StatsResult(
        original_prefix_count=raw_stats["original_prefix_count"],
        optimized_prefix_count=raw_stats["optimized_prefix_count"],
        compression_ratio_percent=raw_stats["compression_ratio_percent"],
        original_total_ips=raw_stats["original_total_ips"],
        unique_ips=raw_stats["unique_ips"],
        addresses_saved=raw_stats["addresses_saved"],
        ipv4_count=ipv4_count,
        ipv6_count=ipv6_count,
        duplicates=[(str(p), c) for p, c in duplicates],
    )


def run_check(
    target: str,
    source: InputSource,
    strict: bool = False,
) -> CheckResult:
    """Return all networks in source that contain the target IP/prefix."""
    try:
        if "/" in target:
            check_item = ipaddress.ip_network(target, strict=False)
        else:
            check_item = ipaddress.ip_address(target)
    except ValueError:
        return CheckResult(target=target, found=False)

    containing: List[IPNet] = []

    for net in _load_networks(source, strict=strict):
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

    formatted_text = format_prefixes(containing, "list") if containing else ""

    return CheckResult(
        target=target,
        found=len(containing) > 0,
        containing_networks=containing,
        formatted_text=formatted_text,
    )


def run_multi_intersect(
    *sources: InputSource,
    strict: bool = False,
    source_names: Optional[List[str]] = None,
) -> MultiIntersectReport:
    """Analyse 2+ sources, building a presence matrix and pairwise exact/partial overlaps."""
    if len(sources) < 2:
        raise ValueError("Multi-intersect requires at least 2 sources")

    lists: List[List[IPNet]] = []
    volumes: List[int] = []

    for source in sources:
        raw = _load_networks(source, strict=strict)
        optimized = list(
            process_prefixes(
                raw, sort=True, remove_nested=True, aggregate=True
            )
        )
        lists.append(optimized)
        volumes.append(count_unique_ips(optimized))

    num_sources = len(sources)
    if source_names is None:
        source_names = [f"Source {i + 1}" for i in range(num_sources)]

    freq: Dict[str, int] = {}
    for lst in lists:
        for net in lst:
            key = str(net)
            freq[key] = freq.get(key, 0) + 1

    sets = [set(lst) for lst in lists]

    str_sets = [{str(n) for n in s} for s in sets]

    presence_map: Dict[str, List[int]] = {}
    for key in freq:
        presence_map[key] = [
            idx
            for idx in range(num_sources)
            if key in str_sets[idx]
        ]

    all_prefixes = [ipaddress.ip_network(key, strict=False) for key in freq]
    all_prefixes = sort_networks(all_prefixes)

    intersection_volume = (
        count_unique_ips(all_prefixes) if all_prefixes else 0
    )

    filtered = [
        net for net in all_prefixes
        if len(presence_map.get(str(net), [])) >= 2
    ]

    filtered_unique_ips = count_unique_ips(filtered) if filtered else 0

    pairwise_exact: List[PairwiseExact] = []
    for i in range(num_sources):
        for j in range(i + 1, num_sources):
            exact = sort_networks(list(sets[i] & sets[j]))
            if exact:
                pairwise_exact.append(
                    PairwiseExact(
                        name_a=source_names[i],
                        name_b=source_names[j],
                        prefixes=exact,
                    )
                )

    sorted_lists = [sort_networks(lst) for lst in lists]
    pairwise_partial: List[PairwisePartial] = []

    for i in range(num_sources):
        for j in range(i + 1, num_sources):
            raw_overlaps = find_two_list_overlaps(
                sorted_lists[i], sorted_lists[j]
            )
            for net1, net2 in raw_overlaps:
                is_ident, subnet, supernet, src_sub, src_super = classify_overlap_pair(
                    net1, net2, source_names[i], source_names[j]
                )
                if not is_ident:
                    pairwise_partial.append(
                        PairwisePartial(
                            subnet=subnet,
                            supernet=supernet,
                            source_subnet=src_sub,
                            source_supernet=src_super,
                        )
                    )

    pairwise_partial.sort(
        key=lambda x: (x.subnet.version, int(x.subnet.network_address))
    )

    out_set: set[IPNet] = set(filtered)
    for pe in pairwise_exact:
        out_set.update(pe.prefixes)
    for pp in pairwise_partial:
        out_set.update([pp.subnet, pp.supernet])

    output_prefixes = sort_networks(list(out_set))

    return MultiIntersectReport(
        common_prefixes=all_prefixes,
        presence_map=presence_map,
        volumes=volumes,
        intersection_volume=intersection_volume,
        source_names=source_names,
        source_count=num_sources,
        filtered_prefixes=filtered,
        pairwise_exact=pairwise_exact,
        pairwise_partial=pairwise_partial,
        output_prefixes=output_prefixes,
        filtered_unique_ips=filtered_unique_ips,
    )