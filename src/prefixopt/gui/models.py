"""
Dataclasses used to ferry operation results from background workers to the GUI.

Each service function in :mod:`prefixopt.gui.services` returns one of these
objects. Tabs connect to the worker's ``result`` signal and read both the
ready-to-display ``formatted_text`` and the structured fields used to update
status counters. Keeping result types explicit makes the signal/slot boundary
type-friendly and easy to test.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ..core.ip_utils import IPNet


@dataclass
class OptimizeResult:
    """Result of an optimize/add run."""

    prefixes: List[IPNet] = field(default_factory=list)
    # Populated when the operation ran in comment-preserving mode.
    commented_prefixes: List[Tuple[IPNet, str]] = field(default_factory=list)
    keep_comments: bool = False
    input_count: int = 0
    output_count: int = 0
    # Final text shown in the output panel.
    formatted_text: str = ""


@dataclass
class FilterResult:
    """Result of a filter run."""

    prefixes: List[IPNet] = field(default_factory=list)
    original_count: int = 0
    removed_count: int = 0
    formatted_text: str = ""


@dataclass
class MergeResult:
    """Result of a merge run."""

    prefixes: List[IPNet] = field(default_factory=list)
    commented_prefixes: List[Tuple[IPNet, str]] = field(default_factory=list)
    keep_comments: bool = False
    total_count: int = 0
    formatted_text: str = ""


@dataclass
class IntersectReport:
    """Structured result of a two-source intersection analysis."""

    exact_matches: List[IPNet] = field(default_factory=list)
    # Each item: (subnet, supernet, source_of_subnet, source_of_supernet).
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
    # True when only one source was supplied (self-intersection mode).
    self_mode: bool = False
    name1: str = ""
    name2: str = ""
    # Prefixes to list in the "common prefixes" output panel.
    all_results: List[IPNet] = field(default_factory=list)


@dataclass
class PairwiseExact:
    """Exact matches shared by two sources in a multi-intersection report."""

    name_a: str = ""
    name_b: str = ""
    prefixes: List[IPNet] = field(default_factory=list)


@dataclass
class PairwisePartial:
    """A partial overlap between two sources in a multi-intersection report."""

    subnet: IPNet = field(default_factory=lambda: None)
    supernet: IPNet = field(default_factory=lambda: None)
    source_subnet: str = ""
    source_supernet: str = ""


@dataclass
class MultiIntersectReport:
    """Result of analysing three or more sources together."""

    # All unique prefixes across sources.
    common_prefixes: List[IPNet] = field(default_factory=list)
    # Maps str(prefix) -> indices of sources containing it.
    presence_map: Dict[str, List[int]] = field(default_factory=dict)
    volumes: List[int] = field(default_factory=list)
    intersection_volume: int = 0
    source_names: List[str] = field(default_factory=list)
    source_count: int = 0
    # Prefixes present in at least two sources (the matrix subset).
    filtered_prefixes: List[IPNet] = field(default_factory=list)
    pairwise_exact: List[PairwiseExact] = field(default_factory=list)
    pairwise_partial: List[PairwisePartial] = field(default_factory=list)
    output_prefixes: List[IPNet] = field(default_factory=list)
    filtered_unique_ips: int = 0


@dataclass
class DiffReport:
    """Added/removed/unchanged sets from a semantic diff."""

    added: List[IPNet] = field(default_factory=list)
    removed: List[IPNet] = field(default_factory=list)
    unchanged: List[IPNet] = field(default_factory=list)


@dataclass
class ExcludeResult:
    """Result of a subtract/exclude operation."""

    prefixes: List[IPNet] = field(default_factory=list)
    commented_prefixes: List[Tuple[IPNet, str]] = field(default_factory=list)
    keep_comments: bool = False
    total_count: int = 0
    formatted_text: str = ""


@dataclass
class SplitResult:
    """Result of splitting networks into smaller subnets."""

    subnets: List[IPNet] = field(default_factory=list)
    total_count: int = 0
    formatted_text: str = ""


@dataclass
class StatsResult:
    """Statistics shown in the stats tab."""

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
    """Result of looking up a target IP/prefix in a list."""

    target: str = ""
    found: bool = False
    containing_networks: List[IPNet] = field(default_factory=list)
    formatted_text: str = ""
