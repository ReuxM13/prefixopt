"""
Individual prefix-list operations.

Each module exposes one pure algorithm operating on :data:`IPNet` objects.
They are composed by :mod:`core.pipeline` and by the CLI/GUI service layer.
"""

from .aggregator import aggregate
from .nested import remove_nested
from .sorter import sort_networks
from .filter import filter_special
from .subnetter import split_network
from .diff import calculate_diff
from .subtractor import subtract_networks
from .overlap import find_two_list_overlaps, find_self_overlaps
