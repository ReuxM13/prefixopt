"""
Helpers for line-comments attached to prefixes.

In "comment mode" every output line has the shape::

    <prefix> # <comment>

When multiple comments are attached to the same prefix they are merged with
the `` | `` separator, e.g. ``192.0.2.0/24 # old | new``. This module keeps
all normalisation/merging logic in one place so the CLI and the GUI share
exactly the same rules.

Key concepts:
    * normalize_comment      - coerce arbitrary text into the canonical ``# x`` form.
    * merge_comments         - combine several comments, dropping duplicates.
    * apply_append_comment   - implement the ``--append-comment`` behaviour
                               (replace old comments by default; append to them
                               when ``keep_existing=True``).
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from .core.ip_utils import IPNet


def normalize_comment(text: Optional[str]) -> str:
    """Return a comment in the canonical ``# text`` form.

    Args:
        text: Raw comment text, with or without a leading ``#``.

    Returns:
        ``""`` for empty/``None`` input, otherwise ``# <stripped text>``.
    """
    if text is None:
        return ""
    cleaned = str(text).strip()
    if not cleaned:
        return ""
    # Strip a user-supplied '#' so we don't end up with a doubled '##'.
    if cleaned.startswith("#"):
        cleaned = cleaned[1:].strip()
    if not cleaned:
        return ""
    return f"# {cleaned}"


def split_comment_parts(comment: Optional[str]) -> List[str]:
    """Split a comment into its ``|``-separated parts.

    Args:
        comment: A comment string such as ``# a | b``.

    Returns:
        The list of non-empty parts with surrounding whitespace removed,
        e.g. ``["a", "b"]``.
    """
    normalized = normalize_comment(comment)
    if not normalized:
        return []
    # Everything after the leading '#' is the comment body.
    body = normalized[1:].strip()
    return [part.strip() for part in body.split("|") if part.strip()]


def join_comment_parts(parts: Iterable[str]) -> str:
    """Join comment parts back together with `` | ``.

    Duplicate parts are suppressed; order is preserved by first occurrence.

    Args:
        parts: Any iterable of comment fragments (with or without ``#``).

    Returns:
        A canonical comment string, or ``""`` if there are no parts.
    """
    normalized_parts: List[str] = []
    for part in parts:
        normalized = str(part).strip().lstrip("#").strip()
        if normalized and normalized not in normalized_parts:
            normalized_parts.append(normalized)
    if not normalized_parts:
        return ""
    return f"# {' | '.join(normalized_parts)}"


def merge_comments(*comments: Optional[str]) -> str:
    """Merge multiple comment strings, preserving order and dropping duplicates.

    Args:
        *comments: Any number of comment strings (``None`` allowed).

    Returns:
        A single merged comment.
    """
    return join_comment_parts(
        part for comment in comments for part in split_comment_parts(comment)
    )


def apply_append_comment(
    existing_comment: Optional[str],
    append_comment: Optional[str],
    keep_existing: bool = False,
) -> str:
    """Apply an "append comment" operation to an existing comment.

    Behaviour:
        * ``keep_existing=False`` (default): previous comments are discarded,
          only the new comment is returned.
        * ``keep_existing=True``: the new comment is appended after any
          existing comment using the `` | `` separator.

    If ``append_comment`` is empty the result depends on ``keep_existing``:
    with it set, the existing comment is normalised and returned; without it,
    an empty string is returned (i.e. comments are wiped).

    Args:
        existing_comment: Comment already attached to the prefix.
        append_comment:   New comment to append/replace with.
        keep_existing:    Whether to preserve the previous comment(s).

    Returns:
        The resulting comment string.
    """
    annotation = normalize_comment(append_comment)
    if not annotation:
        return normalize_comment(existing_comment) if keep_existing else ""

    if keep_existing:
        return merge_comments(existing_comment, annotation)
    return annotation


def annotate_networks(
    networks: Sequence[IPNet],
    append_comment: Optional[str],
) -> List[Tuple[IPNet, str]]:
    """Attach the same comment to every network.

    Useful for operations that discard old comments and stamp a new one onto
    every result (e.g. ``optimize --append-comment foo``).

    Args:
        networks:       Networks to annotate.
        append_comment: Comment text to use.

    Returns:
        A list of ``(network, comment)`` tuples.
    """
    annotation = normalize_comment(append_comment)
    return [(net, annotation) for net in networks]


def annotate_commented_networks(
    items: Iterable[Tuple[IPNet, str]],
    append_comment: Optional[str],
    keep_existing: bool = False,
) -> List[Tuple[IPNet, str]]:
    """Map :func:`apply_append_comment` over a stream of ``(network, comment)``.

    Args:
        items:           Stream of prefix/comment pairs.
        append_comment:  New comment to apply.
        keep_existing:   Whether old comments should be retained.

    Returns:
        A materialised list of pairs with updated comments.
    """
    return [
        (net, apply_append_comment(comment, append_comment, keep_existing))
        for net, comment in items
    ]
