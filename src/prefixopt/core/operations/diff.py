"""
Semantic diff between two optimised prefix sets.

The CLI's ``diff`` command first fully optimises both inputs (sort, remove
nested, aggregate), then hands the canonical representations here. This means
two lists that cover the same address space but use different CIDR boundaries
(e.g. one /23 versus two /24s) will compare as equal.
"""

from typing import Iterable, Set, Tuple

from ..ip_utils import IPNet


def calculate_diff(
    prefixes_new: Iterable[IPNet],
    prefixes_old: Iterable[IPNet],
) -> Tuple[Set[IPNet], Set[IPNet], Set[IPNet]]:
    """Return ``(added, removed, unchanged)`` between two sets.

    Because both inputs are expected to be canonical (optimised), a plain set
    difference is sufficient to express the semantic change.

    Args:
        prefixes_new: Optimised representation of the new list.
        prefixes_old: Optimised representation of the old list.

    Returns:
        A tuple of three sets:
            added     - networks present only in ``prefixes_new``.
            removed   - networks present only in ``prefixes_old``.
            unchanged - networks present in both.
    """
    set_new = set(prefixes_new)
    set_old = set(prefixes_old)

    added = set_new - set_old
    removed = set_old - set_new
    unchanged = set_new & set_old

    return added, removed, unchanged
