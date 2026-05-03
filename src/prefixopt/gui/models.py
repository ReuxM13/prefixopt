"""
Модели данных для GUI.

Каждая модель содержит поле formatted_text для передачи
готовой строки вывода из фонового потока в GUI.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ..core.ip_utils import IPNet


@dataclass
class OptimizeResult:
    """Результат операции оптимизации или добавления префикса."""

    prefixes: List[IPNet] = field(default_factory=list)
    commented_prefixes: List[Tuple[IPNet, str]] = field(default_factory=list)
    keep_comments: bool = False
    input_count: int = 0
    output_count: int = 0
    formatted_text: str = ""


@dataclass
class FilterResult:
    """Результат операции фильтрации."""

    prefixes: List[IPNet] = field(default_factory=list)
    original_count: int = 0
    removed_count: int = 0
    formatted_text: str = ""


@dataclass
class MergeResult:
    """Результат операции слияния."""

    prefixes: List[IPNet] = field(default_factory=list)
    commented_prefixes: List[Tuple[IPNet, str]] = field(default_factory=list)
    keep_comments: bool = False
    total_count: int = 0
    formatted_text: str = ""


@dataclass
class IntersectReport:
    """Результат анализа пересечений двух источников."""

    exact_matches: List[IPNet] = field(default_factory=list)
    partial_overlaps: List[Tuple[IPNet, IPNet, str, str]] = field(
        default_factory=list
    )
    volume1: int = 0
    volume2: int = 0
    volume_intersection: int = 0
    coverage1: float = 0.0
    coverage2: float = 0.0
    all_a_in_b: bool = False
    all_b_in_a: bool = False
    self_mode: bool = False
    name1: str = ""
    name2: str = ""
    all_results: List[IPNet] = field(default_factory=list)


@dataclass
class PairwiseExact:
    """Попарные точные совпадения между двумя источниками."""

    name_a: str = ""
    name_b: str = ""
    prefixes: List[IPNet] = field(default_factory=list)


@dataclass
class PairwisePartial:
    """Попарные частичные перекрытия между двумя источниками."""

    subnet: IPNet = field(default_factory=lambda: None)
    supernet: IPNet = field(default_factory=lambda: None)
    source_subnet: str = ""
    source_supernet: str = ""


@dataclass
class MultiIntersectReport:
    """Результат мульти-пересечения (3+ источников)."""

    common_prefixes: List[IPNet] = field(default_factory=list)
    presence_map: Dict[str, List[int]] = field(default_factory=dict)
    volumes: List[int] = field(default_factory=list)
    intersection_volume: int = 0
    source_names: List[str] = field(default_factory=list)
    source_count: int = 0
    filtered_prefixes: List[IPNet] = field(default_factory=list)
    pairwise_exact: List[PairwiseExact] = field(default_factory=list)
    pairwise_partial: List[PairwisePartial] = field(default_factory=list)
    output_prefixes: List[IPNet] = field(default_factory=list)
    filtered_unique_ips: int = 0


@dataclass
class DiffReport:
    """Результат операции сравнения."""

    added: List[IPNet] = field(default_factory=list)
    removed: List[IPNet] = field(default_factory=list)
    unchanged: List[IPNet] = field(default_factory=list)


@dataclass
class ExcludeResult:
    """Результат операции вычитания."""

    prefixes: List[IPNet] = field(default_factory=list)
    commented_prefixes: List[Tuple[IPNet, str]] = field(default_factory=list)
    keep_comments: bool = False
    total_count: int = 0
    formatted_text: str = ""


@dataclass
class SplitResult:
    """Результат операции разбиения на подсети."""

    subnets: List[IPNet] = field(default_factory=list)
    total_count: int = 0
    formatted_text: str = ""


@dataclass
class StatsResult:
    """Результат сбора статистики."""

    original_prefix_count: int = 0
    optimized_prefix_count: int = 0
    compression_ratio_percent: float = 0.0
    original_total_ips: int = 0
    unique_ips: int = 0
    addresses_saved: int = 0
    ipv4_count: int = 0
    ipv6_count: int = 0
    duplicates: List[Tuple[str, int]] = field(default_factory=list)


@dataclass
class CheckResult:
    """Результат проверки вхождения адреса в список."""

    target: str = ""
    found: bool = False
    containing_networks: List[IPNet] = field(default_factory=list)
    formatted_text: str = ""