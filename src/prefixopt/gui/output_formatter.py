"""
Helpers that render operation results into text for the GUI output panels.

Kept separate from the services so the formatting can be unit-tested without
instantiating any Qt widgets.
"""

from typing import List, Optional, Tuple

from ..core.ip_utils import IPNet


def format_prefixes(
    prefixes: List[IPNet],
    fmt: str = "list",
    commented: Optional[List[Tuple[IPNet, str]]] = None,
) -> str:
    """Render a list of networks (or network/comment pairs) to plain text.

    Args:
        prefixes: Networks to render when ``commented`` is not supplied.
        fmt:      ``"list"`` (one per line) or ``"csv"`` (comma-separated).
        commented: When provided, renders these ``(network, comment)`` pairs
                   instead of ``prefixes``; CSV is rejected in that mode.

    Returns:
        The rendered text, always terminated with a trailing newline.
    """
    if commented is not None:
        if fmt == "csv":
            raise ValueError("CSV format is not supported with comments")
        lines = []
        for net, comment in commented:
            if comment:
                lines.append(f"{net} {comment}")
            else:
                lines.append(str(net))
        return "\n".join(lines) + "\n"

    if fmt == "csv":
        return ",".join(str(net) for net in prefixes) + "\n"
    return "\n".join(str(net) for net in prefixes) + "\n"
