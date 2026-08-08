"""
Subtract ("exclude") one set of networks from another.

This implements "hole punching": given a source network such as 10.0.0.0/30
and a network to exclude such as 10.0.0.1/32, the result is the list of
fragments that cover the remainder of the source range:

    10.0.0.0/30 minus 10.0.0.1/32  ->  [10.0.0.0/32, 10.0.0.2/31]

Strategy:
    1. Optimise the exclusion list (sort, remove nested, aggregate) so we
       never apply redundant rules.
    2. For each source network, start with ``[source]`` as the current set of
       surviving fragments. For every overlapping exclusion, each fragment is
       either kept, discarded entirely (if fully contained in the exclusion),
       or split via ``IPv4Network.address_exclude``.
    3. A global pointer ``exclude_idx`` is advanced across sources, exploiting
       the fact that both lists are sorted to avoid quadratic scanning.
"""

from typing import Iterable, List

from ..ip_utils import IPNet, is_subnet_of
from .aggregator import aggregate
from .nested import remove_nested
from .sorter import sort_networks


# Safety guard: hole punching can explode combinatorially (e.g. /8 minus /32s).
# If the result exceeds this, abort rather than exhausting memory.
MAX_OUTPUT_FRAGMENTS = 2_000_000


def subtract_networks(
    sources: Iterable[IPNet],
    excludes: Iterable[IPNet],
) -> List[IPNet]:
    """Return the address space in ``sources`` not covered by ``excludes``.

    Args:
        sources:  Networks to keep.
        excludes: Networks to remove.

    Returns:
        A list of remaining fragments (not necessarily aggregated).

    Raises:
        ValueError: If the operation would produce more than
                    :data:`MAX_OUTPUT_FRAGMENTS` fragments.
    """
    excludes_list = list(excludes)
    if not excludes_list:
        # Nothing to subtract - avoid sorting/processing work.
        return list(sources)

    # Canonicalise the exclusion set so redundant rules don't cause extra splits.
    excludes_list = sort_networks(excludes_list)
    excludes_list = remove_nested(excludes_list, assume_sorted=True)
    excludes_list = aggregate(excludes_list)

    # Sort the sources so we can advance the exclusion pointer monotonically.
    sources_list = sort_networks(sources)

    final_results: List[IPNet] = []

    # Shared index into excludes_list: because sources are sorted, exclusions
    # that end before the current source starts will also end before every
    # later source starts, so we never need to revisit them.
    exclude_idx = 0
    num_excludes = len(excludes_list)

    for source in sources_list:
        src_start = int(source.network_address)
        src_end = int(source.broadcast_address)
        src_ver = source.version

        # Fast-forward the exclusion pointer past rules that end before this
        # source begins, and stop at the first rule from a newer IP version.
        while exclude_idx < num_excludes:
            curr_exc = excludes_list[exclude_idx]

            if curr_exc.version < src_ver:
                exclude_idx += 1
                continue
            if curr_exc.version > src_ver:
                break

            exc_end = int(curr_exc.broadcast_address)
            if exc_end < src_start:
                exclude_idx += 1
            else:
                break

        # Start with the whole source; each exclusion splits it further.
        current_fragments: List[IPNet] = [source]

        # Apply exclusions starting from the pointer, but don't permanently
        # advance it: the same exclusion may also affect later sources.
        local_idx = exclude_idx
        while local_idx < num_excludes:
            exc = excludes_list[local_idx]

            # Stop once exclusions move past this source's address range.
            if exc.version > src_ver:
                break
            if exc.version == src_ver and int(exc.network_address) > src_end:
                break

            next_pass_fragments = []
            for frag in current_fragments:
                if not frag.overlaps(exc):
                    # Fragment untouched by this exclusion.
                    next_pass_fragments.append(frag)
                    continue

                if is_subnet_of(frag, exc):
                    # Entire fragment is removed.
                    continue

                if is_subnet_of(exc, frag):
                    # Punch the exclusion out of the fragment. address_exclude
                    # returns the CIDR pieces that cover frag minus exc.
                    try:
                        remaining = list(frag.address_exclude(exc))
                        next_pass_fragments.extend(remaining)
                    except ValueError:
                        # Defensive: if subtraction isn't possible, keep frag.
                        next_pass_fragments.append(frag)

            current_fragments = next_pass_fragments
            if not current_fragments:
                break
            local_idx += 1

        final_results.extend(current_fragments)

        if len(final_results) > MAX_OUTPUT_FRAGMENTS:
            raise ValueError(
                f"Subtraction resulted in too many fragments "
                f"(> {MAX_OUTPUT_FRAGMENTS}). Operation stopped."
            )

    return final_results
