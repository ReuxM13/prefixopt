"""
Утилиты для форматирования вывода результатов в GUI.
"""
from typing import List, Tuple, Optional
from ..core.ip_utils import IPNet


def format_prefixes(
    prefixes: List[IPNet],
    fmt: str = "list",
    commented: Optional[List[Tuple[IPNet, str]]] = None,
) -> str:
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
    else:
        if fmt == "csv":
            return ",".join(str(net) for net in prefixes) + "\n"
        else:
            return "\n".join(str(net) for net in prefixes) + "\n"