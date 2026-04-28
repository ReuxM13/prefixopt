"""
Модели данных для GUI.

Каждая модель соответствует результату одной операции.
Сервисный слой возвращает эти объекты,
а GUI-вкладки их отображают.
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Union

from ..core.ip_utils import IPNet


@dataclass
class OptimizeResult:
    """Результат команды optimize или add."""

    prefixes: List[IPNet] = field(default_factory=list)
    commented_prefixes: List[Tuple[IPNet, str]] = field(default_factory=list)
    keep_comments: bool = False
    input_count: int = 0
    output_count: int = 0


@dataclass
class FilterResult:
    """Результат команды filter."""

    prefixes: List[IPNet] = field(default_factory=list)
    original_count: int = 0
    removed_count: int = 0


@dataclass
class MergeResult:
    """Результат команды merge."""

    prefixes: List[IPNet] = field(default_factory=list)
    commented_prefixes: List[Tuple[IPNet, str]] = field(default_factory=list)
    keep_comments: bool = False
    total_count: int = 0


@dataclass
class IntersectReport:
    """Результат команды intersect."""

    exact_matches: List[IPNet] = field(default_factory=list)
    partial_overlaps: List[Tuple[IPNet, IPNet, str, str]] = field(default_factory=list)
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
class DiffReport:
    """Результат команды diff."""

    added: List[IPNet] = field(default_factory=list)
    removed: List[IPNet] = field(default_factory=list)
    unchanged: List[IPNet] = field(default_factory=list)


@dataclass
class ExcludeResult:
    """Результат команды exclude."""

    prefixes: List[IPNet] = field(default_factory=list)
    commented_prefixes: List[Tuple[IPNet, str]] = field(default_factory=list)
    keep_comments: bool = False
    total_count: int = 0


@dataclass
class SplitResult:
    """Результат команды split."""

    subnets: List[IPNet] = field(default_factory=list)
    total_count: int = 0


@dataclass
class StatsResult:
    """Результат команды stats."""

    original_prefix_count: int = 0
    optimized_prefix_count: int = 0
    compression_ratio_percent: float = 0.0
    original_total_ips: int = 0
    unique_ips: int = 0
    addresses_saved: int = 0
    ipv4_count: int = 0
    ipv6_count: int = 0


@dataclass
class CheckResult:
    """Результат команды check."""

    target: str = ""
    found: bool = False
    containing_networks: List[IPNet] = field(default_factory=list)