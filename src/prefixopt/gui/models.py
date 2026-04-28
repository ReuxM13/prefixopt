"""
Модели данных для GUI.
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Union

from ..core.ip_utils import IPNet


@dataclass
class OptimizeResult:
    prefixes: List[IPNet] = field(default_factory=list)
    commented_prefixes: List[Tuple[IPNet, str]] = field(default_factory=list)
    keep_comments: bool = False
    input_count: int = 0
    output_count: int = 0


@dataclass
class FilterResult:
    prefixes: List[IPNet] = field(default_factory=list)
    original_count: int = 0
    removed_count: int = 0


@dataclass
class MergeResult:
    prefixes: List[IPNet] = field(default_factory=list)
    commented_prefixes: List[Tuple[IPNet, str]] = field(default_factory=list)
    keep_comments: bool = False
    total_count: int = 0


@dataclass
class IntersectReport:
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
class MultiIntersectReport:
    common_prefixes: List[IPNet] = field(default_factory=list)
    presence_map: Dict[str, List[int]] = field(default_factory=dict)
    volumes: List[int] = field(default_factory=list)
    intersection_volume: int = 0
    source_names: List[str] = field(default_factory=list)
    source_count: int = 0


@dataclass
class DiffReport:
    added: List[IPNet] = field(default_factory=list)
    removed: List[IPNet] = field(default_factory=list)
    unchanged: List[IPNet] = field(default_factory=list)


@dataclass
class ExcludeResult:
    prefixes: List[IPNet] = field(default_factory=list)
    commented_prefixes: List[Tuple[IPNet, str]] = field(default_factory=list)
    keep_comments: bool = False
    total_count: int = 0


@dataclass
class SplitResult:
    subnets: List[IPNet] = field(default_factory=list)
    total_count: int = 0


@dataclass
class StatsResult:
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
    target: str = ""
    found: bool = False
    containing_networks: List[IPNet] = field(default_factory=list)