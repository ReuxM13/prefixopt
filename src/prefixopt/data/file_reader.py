"""
Streaming readers for prefix lists.

Responsibilities:
    * Read text files, CSV files and JSON arrays from disk (with a Rich
      progress bar for large files).
    * Read lines from STDIN so the tool works in shell pipelines.
    * Extract IPs/CIDRs from "dirty" lines (router configs, logs, CSV rows,
      JSON values) using regex + :mod:`ipaddress`.
    * Optionally preserve inline ``# comments`` bound to each prefix.

Safety limits protect against accidentally reading a multi-GB file or a JSON
array with hundreds of millions of entries (which would otherwise cause an
out-of-memory crash). All readers are generators so callers can process data
lazily.
"""

import csv
import ipaddress
import re
import contextlib
import sys
from pathlib import Path
from typing import (
    BinaryIO,
    Generator,
    Iterator,
    List,
    TextIO,
    Tuple,
    Union,
)

from ipaddress import IPv4Network, IPv6Network
from rich.progress import (
    TaskID,
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)


# Hard safety limits. They are deliberately generous but bounded so malformed
# or hostile inputs cannot exhaust all memory.
MAX_FILE_SIZE_MB = 700
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_LINE_COUNT = 8_000_000


class ProgressFileWrapper:
    """File-like wrapper that reports bytes read to a Rich progress bar.

    Used for streaming JSON parsing with ijson, which reads from a binary
    file object in chunks. Without this wrapper the JSON reader couldn't show
    progress because it never sees line boundaries.
    """

    def __init__(self, f: BinaryIO, progress: Progress, task_id: TaskID):
        """Initialise the object."""
        self.f = f
        self.progress = progress
        self.task_id = task_id

    def read(self, size: int = -1) -> bytes:
        """Read up to ``size`` bytes and advance the progress bar."""
        data = self.f.read(size)
        # progress may be None (or a nullcontext stand-in) when the bar is
        # disabled; guard the update so callers don't have to care.
        if data and self.progress is not None:
            self.progress.update(self.task_id, advance=len(data))
        return data


# ---------------------------------------------------------------------------
# Regex-based extraction
# ---------------------------------------------------------------------------


def parse_ipv4(text: str) -> List[str]:
    """Return all IPv4-looking tokens (with optional /mask) found in ``text``.

    The regex is intentionally permissive; validity is checked later by
    :mod:`ipaddress`. This means the function happily extracts candidates from
    log lines, configs and other noisy text.
    """
    ipv4_pattern = r"(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?"
    matches = re.findall(ipv4_pattern, text)
    return [match.strip() for match in matches]


def parse_ipv6(text: str) -> List[str]:
    """Return all IPv6-looking tokens (with optional /mask) found in ``text``."""
    ipv6_pattern = r"(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}(?:/\d{1,3})?"
    matches = re.findall(ipv6_pattern, text)
    return [match.strip() for match in matches]


def parse_ipv4_ranges(text: str) -> List[IPv4Network]:
    """Parse ``start - end`` IPv4 ranges into CIDR networks.

    Example:
        ``"192.168.1.1 - 192.168.1.3"`` -> two /32s (because the range isn't
        aligned to a single CIDR boundary).

    Uses :func:`ipaddress.summarize_address_range`, which returns the minimal
    set of CIDRs covering the interval. Reversed ranges are auto-corrected.
    """
    range_pattern = (
        r"((?:\d{1,3}\.){3}\d{1,3})\s*-\s*((?:\d{1,3}\.){3}\d{1,3})"
    )
    matches = re.findall(range_pattern, text)

    cidr_results: List[IPv4Network] = []
    for start_str, end_str in matches:
        try:
            start_ip = ipaddress.IPv4Address(start_str)
            end_ip = ipaddress.IPv4Address(end_str)

            # Tolerate reversed ranges: 10.0.0.5 - 10.0.0.1 -> swap them.
            if start_ip > end_ip:
                start_ip, end_ip = end_ip, start_ip

            subnets = ipaddress.summarize_address_range(start_ip, end_ip)
            cidr_results.extend(subnets)
        except ValueError:
            # Garbage in, silently ignore - the rest of the line is still parsed.
            pass
    return cidr_results


def normalize_single_ip(
    candidate: str, strict: bool = False
) -> Union[IPv4Network, IPv6Network, None]:
    """Convert one candidate string into a network, or ``None`` if invalid.

    Unlike :func:`core.ip_utils.normalize_prefix`, this function returns
    ``None`` for unparseable input (rather than raising) because file parsing
    is expected to skip junk lines. It also works around Python CVE-2021-29921
    by stripping leading zeros in IPv4 octets.

    Args:
        candidate: Raw token such as ``"10.0.0.1/24"`` or ``"010.0.0.1"``.
        strict:    When ``True``, networks with host bits set raise an error
                   with a "Did you mean ...?" hint.

    Returns:
        A network object or ``None``.
    """
    if strict:
        if "/" in candidate:
            try:
                return ipaddress.ip_network(candidate, strict=True)
            except ValueError as exc:
                try:
                    corrected = ipaddress.ip_network(candidate, strict=False)
                except ValueError:
                    return None
                raise ValueError(
                    f"Invalid network '{candidate}': host bits are set. "
                    f"Did you mean '{corrected}'?"
                ) from exc
        else:
            # No mask => treat as a host route (/32 or /128).
            try:
                ip = ipaddress.ip_address(candidate)
                if ip.version == 4:
                    return ipaddress.IPv4Network(f"{ip}/32", strict=False)
                return ipaddress.IPv6Network(f"{ip}/128", strict=False)
            except ValueError:
                return None

    # Lenient: try direct conversion first.
    try:
        return ipaddress.ip_network(candidate, strict=False)
    except ValueError:
        pass

    # CVE-2021-29921 workaround: some platforms interpret leading zeros as
    # octal. Strip them by coercing each octet through int().
    if "." in candidate and ":" not in candidate:
        try:
            parts = candidate.split("/")
            ip_part = parts[0]
            mask_part = f"/{parts[1]}" if len(parts) > 1 else ""
            clean_ip = ".".join(str(int(octet)) for octet in ip_part.split("."))
            clean_candidate = f"{clean_ip}{mask_part}"
            return ipaddress.ip_network(clean_candidate, strict=False)
        except (ValueError, IndexError):
            pass

    # Last attempt: treat the token as a bare address.
    try:
        if "." in candidate and ":" not in candidate:
            clean_ip = ".".join(str(int(octet)) for octet in candidate.split("."))
            ip = ipaddress.ip_address(clean_ip)
        else:
            ip = ipaddress.ip_address(candidate)

        if ip.version == 4:
            return ipaddress.IPv4Network(f"{ip}/32", strict=False)
        return ipaddress.IPv6Network(f"{ip}/128", strict=False)
    except ValueError:
        return None


def extract_prefixes_from_text(
    text: str, strict: bool = False
) -> List[Union[IPv4Network, IPv6Network]]:
    """Extract every IP/prefix/range found in a free-form text line.

    Ranges (``a - b``) are extracted first, then individual IPv4/IPv6 tokens.
    Duplicates or invalid matches are naturally filtered by the normaliser.
    """
    prefixes: List[Union[IPv4Network, IPv6Network]] = []
    seen: set = set()

    def _add(net):
        # De-duplicate by (version, network address, prefix length). Range
        # parsing and individual-token parsing can both match the same IPs.
        key = (net.version, int(net.network_address), net.prefixlen)
        if key not in seen:
            seen.add(key)
            prefixes.append(net)

    # Ranges are handled separately because they span two addresses. Add them
    # first so their CIDR fragments win over the individual-token regex below.
    for net in parse_ipv4_ranges(text):
        _add(net)

    # Then collect individual v4/v6 candidates.
    all_candidates = parse_ipv4(text) + parse_ipv6(text)
    for candidate in all_candidates:
        if not candidate:
            continue
        network = normalize_single_ip(candidate, strict=strict)
        if network is not None:
            _add(network)

    return prefixes


# ---------------------------------------------------------------------------
# Line-oriented generators
# ---------------------------------------------------------------------------


def _parse_lines_generator(
    line_iterator: Iterator[str],
    progress: Union[Progress, None] = None,
    task_id: Union[TaskID, None] = None,
    strict: bool = False,
) -> Generator[Union[IPv4Network, IPv6Network], None, None]:
    """Yield networks parsed from arbitrary lines (comments ignored).

    Used for plain text inputs (files and STDIN). Lines that look like free
    text are searched for IPs with regex; if none are found we try parsing the
    whole line as a single network. Lines beginning with ``#`` are skipped.
    """
    for line_num, line in enumerate(line_iterator, 1):
        if line_num > MAX_LINE_COUNT:
            raise ValueError(
                f"Input exceeds the safety limit of {MAX_LINE_COUNT} lines."
            )

        if progress and task_id is not None:
            line_bytes = len(line.encode("utf-8")) + 1
            if progress is not None:
                progress.update(task_id, advance=line_bytes)

        line = line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            prefixes = extract_prefixes_from_text(line, strict=strict)
        except ValueError as exc:
            # Re-raise with line number so the user can locate bad input.
            raise ValueError(f"Line {line_num}: {exc}") from exc

        if prefixes:
            yield from prefixes
        else:
            # Fallback: the whole line might itself be a network (and contain
            # no characters the regex recognises).
            try:
                yield ipaddress.ip_network(line, strict=strict)
            except ValueError:
                # Unparseable line - silently skip.
                pass


def _parse_comments_generator(
    line_iterator: Iterator[str],
    strict: bool = False,
) -> Generator[Tuple[Union[IPv4Network, IPv6Network], str], None, None]:
    """Like :func:`_parse_lines_generator` but yields ``(network, comment)``.

    Everything after the first ``#`` on a line is treated as that prefix's
    comment and returned verbatim (with a canonical ``# `` prefix added).
    """
    for line_num, line in enumerate(line_iterator, 1):
        if line_num > MAX_LINE_COUNT:
            raise ValueError(
                f"Input exceeds safety limit of {MAX_LINE_COUNT} lines."
            )

        line_stripped = line.strip()
        if not line_stripped:
            continue

        if "#" in line:
            # Split only once: comments may themselves contain '#'.
            content, comment_raw = line.split("#", 1)
            cleaned_comment = comment_raw.strip()
            comment = f"# {cleaned_comment}" if cleaned_comment else ""
        else:
            content = line
            comment = ""

        try:
            prefixes = extract_prefixes_from_text(content, strict=strict)
        except ValueError as exc:
            raise ValueError(f"Line {line_num}: {exc}") from exc

        for p in prefixes:
            yield (p, comment)


# ---------------------------------------------------------------------------
# Format-specific file readers
# ---------------------------------------------------------------------------


def _read_txt_generator(
    path: Path,
    progress: Progress,
    task_id: TaskID,
    strict: bool = False,
) -> Generator[Union[IPv4Network, IPv6Network], None, None]:
    """Stream networks from a plain text file."""
    with open(path, "r", encoding="utf-8") as f:
        yield from _parse_lines_generator(f, progress, task_id, strict=strict)


def _read_csv_generator(
    path: Path,
    progress: Progress,
    task_id: TaskID,
    column_name: str = "prefix",
    strict: bool = False,
) -> Generator[Union[IPv4Network, IPv6Network], None, None]:
    """Stream networks from a CSV file's ``prefix`` column (configurable)."""
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            count += 1
            if count > MAX_LINE_COUNT:
                raise ValueError(
                    f"CSV exceeds limit of {MAX_LINE_COUNT} rows."
                )

            if progress is not None:
                progress.update(task_id, advance=50)

            prefix_text = row.get(column_name, "").strip()
            if not prefix_text:
                continue

            extracted = extract_prefixes_from_text(prefix_text)
            if extracted:
                yield from extracted
            else:
                try:
                    yield ipaddress.ip_network(prefix_text, strict=strict)
                except ValueError:
                    pass


def _read_json_generator(
    path: Path,
    progress: Progress,
    task_id: TaskID,
    key_name: str = "prefixes",
    strict: bool = False,
) -> Generator[Union[IPv4Network, IPv6Network], None, None]:
    """Stream elements of a JSON array (default key ``prefixes``) using ijson.

    Streaming avoids loading an entire large JSON document into memory. A
    trailing/garbage JSON structure is tolerated (ijson.JSONError ends reading).
    """
    with open(path, "rb") as f:
        import ijson  # lazy: heavy native dep, only needed for JSON
        wrapped_file = ProgressFileWrapper(f, progress, task_id)
        parser_path = f"{key_name}.item"
        count = 0
        try:
            for item in ijson.items(wrapped_file, parser_path):
                count += 1
                if count > MAX_LINE_COUNT:
                    raise ValueError(
                        f"JSON array exceeds the limit of {MAX_LINE_COUNT} items."
                    )

                prefix_text = str(item).strip()
                extracted = extract_prefixes_from_text(
                    prefix_text, strict=strict
                )
                if extracted:
                    yield from extracted
                else:
                    try:
                        yield ipaddress.ip_network(
                            prefix_text, strict=strict
                        )
                    except ValueError:
                        print(
                            f"Warning: Invalid prefix '{prefix_text}' in JSON",
                            file=sys.stderr,
                        )
        except ijson.JSONError:
            # Truncated/invalid JSON - stop reading gracefully.
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_stream(
    stream: TextIO, strict: bool = False
) -> Iterator[Union[IPv4Network, IPv6Network]]:
    """Read networks from an open text stream (typically STDIN)."""
    yield from _parse_lines_generator(stream, strict=strict)


def read_stream_with_comments(
    stream: TextIO, strict: bool = False
) -> Generator[Tuple[Union[IPv4Network, IPv6Network], str], None, None]:
    """Read ``(network, comment)`` pairs from an open text stream."""
    yield from _parse_comments_generator(stream, strict=strict)


def read_networks(
    file_path: Union[str, Path],
    show_progress: bool = True,
    strict: bool = False,
) -> Iterator[Union[IPv4Network, IPv6Network]]:
    """Read networks from a file, auto-detecting format by extension.

    Args:
        file_path:     Path to the input file.
        show_progress: Show a Rich progress bar for files larger than 1 MiB.
        strict:        Forwarded to the parser (reject host bits).

    Yields:
        IPv4/IPv6 networks.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the file exceeds the configured size limit.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File size exceeds safety limit ({MAX_FILE_SIZE_MB} MB)."
        )

    # Avoid the overhead of a progress bar for tiny files/interactive runs.
    import sys as _sys
    is_tty = False
    try:
        is_tty = _sys.stderr.isatty()
    except Exception:
        is_tty = False
    should_show = show_progress and is_tty and file_size > 1024 * 1024
    extension = path.suffix.lower()

    # A disabled Rich Progress context still emits a newline on exit, which
    # corrupts piped/redirected stdout. So only construct Progress when it will
    # actually be shown (interactive TTY and a file large enough to warrant it).
    if should_show:
        progress_cm = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            transient=True,
        )
    else:
        progress_cm = contextlib.nullcontext()

    with progress_cm as progress:
        # When the progress bar is disabled, pass a dummy progress object that
        # ignores updates so the reader generators can call progress.update().
        if should_show:
            task_id = progress.add_task(
                f"Reading {path.name}", total=file_size
            )
        else:
            task_id = -1

        # JSON is streamed via ijson; everything else is treated as text.
        if extension == ".json":
            yield from _read_json_generator(
                path, progress, task_id, strict=strict
            )
        else:
            yield from _read_txt_generator(
                path, progress, task_id, strict=strict
            )


def read_prefixes_with_comments(
    file_path: Path, strict: bool = False
) -> Generator[Tuple[Union[IPv4Network, IPv6Network], str], None, None]:
    """Read a file preserving inline ``# comments``.

    Used by comment-aware operations (merge, exclude). Plain text only; CSV
    and JSON are not supported in this mode because comments are not a natural
    fit for those formats.
    """
    path = Path(file_path)
    if path.stat().st_size > MAX_FILE_SIZE_BYTES:
        raise ValueError("File too large for merge with comments.")

    with open(file_path, "r", encoding="utf-8") as f:
        yield from _parse_comments_generator(f, strict=strict)
