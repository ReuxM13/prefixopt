"""
Сервисный слой для интеграции ядра (core) с графическим интерфейсом.

Каждая функция выполняет полный цикл обработки: загрузка данных,
математические операции и форматирование результата в строку.
Все функции вызываются исключительно из фоновых потоков (Worker).
"""

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

from ..core.ip_counter import count_unique_ips, get_duplicate_prefixes, get_prefix_statistics
from ..core.ip_utils import IPNet, is_subnet_of, normalize_prefix
from ..core.operations.diff import calculate_diff
from ..core.operations.sorter import sort_networks
from ..core.operations.subnetter import split_network
from ..core.operations.subtractor import subtract_networks
from ..core.pipeline import process_prefixes
from ..data.file_reader import (
    extract_prefixes_from_text,
    read_networks,
    read_prefixes_with_comments,
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
    """
    Загружает сети из файла или текстовой строки.

    Args:
        source: Путь к файлу или текст с префиксами.
        strict: Строгая валидация (host bits).

    Yields:
        Объекты IPv4Network / IPv6Network.
    """
    if isinstance(source, Path):
        yield from read_networks(source, show_progress=False, strict=strict)
    else:
        results = extract_prefixes_from_text(source, strict=strict)
        if results:
            yield from results


def _load_with_comments(
    source: InputSource,
    strict: bool = False,
) -> Iterator[Tuple[IPNet, str]]:
    """
    Загружает сети с комментариями из файла или текстовой строки.

    Args:
        source: Путь к файлу или текст.
        strict: Строгая валидация.

    Yields:
        Кортеж (IPNet, comment).
    """
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
    """
    Дедупликация префиксов с сохранением комментариев.

    При дублировании приоритет отдается непустому комментарию.

    Returns:
        Отсортированный список кортежей (IPNet, comment).
    """
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
    strict: bool = False,
) -> OptimizeResult:
    """
    Выполняет полный цикл оптимизации префиксов.

    Args:
        source: Источник данных (путь к файлу или текст).
        fmt: Формат вывода ("list" или "csv").
        ipv4_only: Оставить только IPv4.
        ipv6_only: Оставить только IPv6.
        keep_comments: Режим дедупликации с сохранением комментариев.
        strict: Строгая валидация host bits.

    Returns:
        OptimizeResult с готовой строкой formatted_text и статистикой.
    """
    if keep_comments:
        raw = _load_with_comments(source, strict=strict)
        commented = _deduplicate_commented(
            raw, ipv4_only=ipv4_only, ipv6_only=ipv6_only
        )
        formatted_text = format_prefixes([], fmt, commented=commented)

        return OptimizeResult(
            keep_comments=True,
            input_count=len(commented),
            output_count=len(commented),
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
) -> OptimizeResult:
    """
    Добавляет новый префикс в список и выполняет реоптимизацию.

    Args:
        source: Источник данных (путь к файлу или текст).
        new_prefix: Строковое представление добавляемого префикса.
        fmt: Формат вывода ("list" или "csv").
        keep_comments: Режим с сохранением комментариев.

    Returns:
        OptimizeResult с готовой строкой formatted_text и статистикой.
    """
    net_to_add = normalize_prefix(new_prefix)

    if keep_comments:
        raw = _load_with_comments(source)
        commented = _deduplicate_commented(raw)

        exists = any(item[0] == net_to_add for item in commented)
        if not exists:
            commented.append(
                (net_to_add, f"# Added manually: {new_prefix}")
            )
            commented.sort(
                key=lambda x: (
                    x[0].version,
                    int(x[0].network_address),
                    x[0].prefixlen,
                )
            )

        formatted_text = format_prefixes([], fmt, commented=commented)

        return OptimizeResult(
            keep_comments=True,
            input_count=len(commented),
            output_count=len(commented),
            formatted_text=formatted_text,
        )

    data = list(_load_networks(source))
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
    strict: bool = False,
) -> FilterResult:
    """
    Фильтрует список, удаляя указанные категории сетей.

    Args:
        source: Источник данных.
        fmt: Формат вывода ("list" или "csv").
        exclude_private: Удалить RFC 1918.
        exclude_loopback: Удалить loopback.
        exclude_link_local: Удалить link-local.
        exclude_multicast: Удалить multicast.
        exclude_reserved: Удалить reserved.
        bogons: Удалить bogons.
        strict: Строгая валидация.

    Returns:
        FilterResult с готовой строкой formatted_text и статистикой.
    """
    raw = list(_load_networks(source, strict=strict))
    original_count = len(raw)

    result_iter = process_prefixes(
        raw,
        sort=False,
        remove_nested=False,
        aggregate=False,
        exclude_private=exclude_private,
        exclude_loopback=exclude_loopback,
        exclude_link_local=exclude_link_local,
        exclude_multicast=exclude_multicast,
        exclude_reserved=exclude_reserved,
        exclude_unspecified=True,
        bogons=bogons,
    )
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
    strict: bool = False,
) -> MergeResult:
    """
    Объединяет два источника данных.

    Args:
        source1: Первый источник.
        source2: Второй источник.
        fmt: Формат вывода ("list" или "csv").
        keep_comments: Режим дедупликации с комментариями.
        append_comment: Текст для добавления к комментариям source1.
        strict: Строгая валидация.

    Returns:
        MergeResult с готовой строкой formatted_text.
    """
    if keep_comments:
        unique_map: dict[str, str] = {}

        if append_comment:
            annotation = (
                f"# {append_comment.strip()}" if append_comment.strip() else ""
            )

            for ip, comment in _load_with_comments(source2, strict=strict):
                ip_str = str(ip)
                if ip_str not in unique_map:
                    unique_map[ip_str] = comment

            for ip, comment in _load_with_comments(source1, strict=strict):
                ip_str = str(ip)
                parts_existing: set[str] = set()
                parts_new: list[str] = []

                if ip_str in unique_map:
                    for p in _split_comment(unique_map[ip_str]):
                        parts_existing.add(p)
                        parts_new.append(p)

                for p in _split_comment(comment):
                    if p not in parts_existing:
                        parts_existing.add(p)
                        parts_new.append(p)

                for p in _split_comment(annotation):
                    if p not in parts_existing:
                        parts_existing.add(p)
                        parts_new.append(p)

                unique_map[ip_str] = _join_comment(parts_new)
        else:
            for ip, comment in _load_with_comments(source1, strict=strict):
                ip_str = str(ip)
                if ip_str not in unique_map:
                    unique_map[ip_str] = comment
                elif not unique_map[ip_str] and comment:
                    unique_map[ip_str] = comment

            for ip, comment in _load_with_comments(source2, strict=strict):
                ip_str = str(ip)
                if ip_str not in unique_map:
                    unique_map[ip_str] = comment
                elif not unique_map[ip_str] and comment:
                    unique_map[ip_str] = comment

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


def _split_comment(comment: str) -> List[str]:
    """Разбивает комментарий на части по разделителю '|'."""
    if not comment:
        return []
    raw = comment.strip()
    if raw.startswith("#"):
        raw = raw[1:].strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split("|") if p.strip()]


def _join_comment(parts: List[str]) -> str:
    """Собирает части комментария в строку с разделителем '|'."""
    if not parts:
        return ""
    return f"# {' | '.join(parts)}"


def run_intersect(
    source1: InputSource,
    source2: Optional[InputSource] = None,
    strict: bool = False,
    name1: str = "Source A",
    name2: str = "Source B",
) -> IntersectReport:
    """
    Находит пересечения между двумя списками или внутри одного.

    Args:
        source1: Первый источник.
        source2: Второй источник (None для self-intersect).
        strict: Строгая валидация.
        name1: Имя первого источника для отчета.
        name2: Имя второго источника для отчета.

    Returns:
        IntersectReport с результатами анализа пересечений.
    """
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
        raw_overlaps = _find_self_overlaps(sorted1)
    else:
        set1 = set(list1)
        set2 = set(list2)
        common = set1.intersection(set2)
        sorted2 = sort_networks(list2)
        raw_overlaps = _find_two_list_overlaps(sorted1, sorted2)

    partial_overlaps: List[Tuple[IPNet, IPNet, str, str]] = []

    for net1, net2 in raw_overlaps:
        if net1 == net2:
            continue
        if net1.subnet_of(net2):
            partial_overlaps.append(
                (net1, net2, name1, name2 if not self_mode else name1)
            )
        elif net2.subnet_of(net1):
            partial_overlaps.append(
                (net2, net1, name2 if not self_mode else name1, name1)
            )
        else:
            partial_overlaps.append(
                (net1, net2, name1, name2 if not self_mode else name1)
            )

    intersection_fragments: List[IPNet] = list(common)
    for net1, net2 in raw_overlaps:
        if net1 == net2:
            continue
        if net1.subnet_of(net2):
            intersection_fragments.append(net1)
        elif net2.subnet_of(net1):
            intersection_fragments.append(net2)

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


def _find_two_list_overlaps(
    sorted1: List[IPNet],
    sorted2: List[IPNet],
) -> List[Tuple[IPNet, IPNet]]:
    """
    Линейный поиск пересечений между двумя отсортированными списками.

    Использует two-pointer алгоритм по диапазонам адресов.
    """
    overlaps: List[Tuple[IPNet, IPNet]] = []
    i, j = 0, 0
    len1, len2 = len(sorted1), len(sorted2)

    while i < len1 and j < len2:
        n1, n2 = sorted1[i], sorted2[j]

        if n1.version < n2.version:
            i += 1
            continue
        if n1.version > n2.version:
            j += 1
            continue

        s1 = int(n1.network_address)
        e1 = int(n1.broadcast_address)
        s2 = int(n2.network_address)
        e2 = int(n2.broadcast_address)

        if max(s1, s2) <= min(e1, e2):
            overlaps.append((n1, n2))
            if e1 < e2:
                i += 1
            elif e2 < e1:
                j += 1
            else:
                i += 1
                j += 1
        elif e1 < s2:
            i += 1
        else:
            j += 1

    return overlaps


def _find_self_overlaps(
    sorted_list: List[IPNet],
) -> List[Tuple[IPNet, IPNet]]:
    """
    Поиск пересечений внутри одного отсортированного списка.

    Для каждого элемента проверяются последующие до выхода за broadcast-границу.
    """
    overlaps: List[Tuple[IPNet, IPNet]] = []
    length = len(sorted_list)

    for i in range(length):
        net_i = sorted_list[i]
        end_i = int(net_i.broadcast_address)

        for j in range(i + 1, length):
            net_j = sorted_list[j]

            if net_i.version != net_j.version:
                break
            if int(net_j.network_address) > end_i:
                break

            overlaps.append((net_i, net_j))

    return overlaps


def run_diff(
    new_source: InputSource,
    old_source: InputSource,
    ipv4_only: bool = False,
    ipv6_only: bool = False,
    strict: bool = False,
) -> DiffReport:
    """
    Семантическое сравнение двух наборов данных.

    Args:
        new_source: Новый набор данных.
        old_source: Старый набор данных.
        ipv4_only: Оставить только IPv4.
        ipv6_only: Оставить только IPv6.
        strict: Строгая валидация.

    Returns:
        DiffReport со списками добавленных, удаленных и неизменных префиксов.
    """

    def prepare(src: InputSource) -> List[IPNet]:
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
    ipv4_only: bool = False,
    ipv6_only: bool = False,
    strict: bool = False,
) -> ExcludeResult:
    """
    Вычитает target из source (hole punching).

    Args:
        source: Исходный список.
        target: Список для исключения.
        fmt: Формат вывода ("list" или "csv").
        keep_comments: Наследовать комментарии от родительских сетей.
        ipv4_only: Оставить только IPv4.
        ipv6_only: Оставить только IPv6.
        strict: Строгая валидация.

    Returns:
        ExcludeResult с готовой строкой formatted_text.
    """
    exclude_list = list(_load_networks(target, strict=strict))

    if keep_comments:
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
            commented.append((fragment, inherited))

        formatted_text = format_prefixes([], fmt, commented=commented)

        return ExcludeResult(
            keep_comments=True,
            total_count=len(commented),
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
    strict: bool = False,
) -> SplitResult:
    """
    Разбивает сети на подсети указанной длины.

    Args:
        source: Источник данных.
        target_length: Целевая длина префикса.
        fmt: Формат вывода ("list" или "csv").
        strict: Строгая валидация.

    Returns:
        SplitResult с готовой строкой formatted_text.
    """
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
    """
    Собирает статистику по списку префиксов.

    Args:
        source: Источник данных.
        strict: Строгая валидация.

    Returns:
        StatsResult с метриками.
    """
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
    """
    Проверяет, входит ли target в список source.

    Args:
        target: IP-адрес или префикс для проверки.
        source: Источник данных для поиска.
        strict: Строгая валидация.

    Returns:
        CheckResult с результатом проверки и готовой строкой.
    """
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
    """
    Находит карту присутствия префиксов и выполняет полный pairwise-анализ.

    Загружает и оптимизирует все источники, строит матрицу присутствия,
    вычисляет попарные точные совпадения и частичные перекрытия.

    Args:
        *sources: Два и более источника данных.
        strict: Строгая валидация.
        source_names: Имена источников для отчета.

    Returns:
        MultiIntersectReport с полными данными для рендеринга.
    """
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

    presence_map: Dict[str, List[int]] = {}
    for key in freq:
        presence_map[key] = [
            idx
            for idx in range(num_sources)
            if key in {str(n) for n in sets[idx]}
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
            raw_overlaps = _find_two_list_overlaps(
                sorted_lists[i], sorted_lists[j]
            )
            for net1, net2 in raw_overlaps:
                if net1 == net2:
                    continue
                if net1.subnet_of(net2):
                    pairwise_partial.append(
                        PairwisePartial(
                            subnet=net1,
                            supernet=net2,
                            source_subnet=source_names[i],
                            source_supernet=source_names[j],
                        )
                    )
                elif net2.subnet_of(net1):
                    pairwise_partial.append(
                        PairwisePartial(
                            subnet=net2,
                            supernet=net1,
                            source_subnet=source_names[j],
                            source_supernet=source_names[i],
                        )
                    )
                else:
                    pairwise_partial.append(
                        PairwisePartial(
                            subnet=net1,
                            supernet=net2,
                            source_subnet=source_names[i],
                            source_supernet=source_names[j],
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