"""
Модуль чтения и парсинга файлов.

Отвечает за извлечение данных из внешнего мира.
Реализует:
1. Ленивую загрузку - чтение файлов любого размера без OOM.
2. Извлечение IP из мусора (Regex) и исправление ошибок ввода (010 -> 10).
3. Защиту - жесткие лимиты на размер данных.
4. Поддержку STDIN - чтение из пайпов (cat file | prefixopt).
"""
import sys
import csv
import ijson
import re
import ipaddress
from pathlib import Path
from typing import List, Union, Generator, Iterator, Tuple, TextIO, BinaryIO

from ipaddress import IPv4Network, IPv6Network
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, TaskID

# --- CONSTANTS ---
# Лимиты безопасности. Если данные превышают эти значения, мы аварийно останавливаемся,
# чтобы не положить сервер или рабочую станцию бесконечным циклом или переполнением RAM.
MAX_FILE_SIZE_MB = 700
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_LINE_COUNT = 8_000_000


class ProgressFileWrapper:
    """
    Прокси-обертка для файлового объекта.
    Работает с БАЙТАМИ для совместимости с ijson.
    """
    def __init__(self, f: BinaryIO, progress: Progress, task_id: TaskID):
        self.f = f
        self.progress = progress
        self.task_id = task_id

    def read(self, size: int = -1) -> bytes:
        data = self.f.read(size)
        if data:
            self.progress.update(self.task_id, advance=len(data))
        return data


# --- Ядро парсинга ---

def parse_ipv4(text: str) -> List[str]:
    """
    Ищет IPv4 адреса в тексте с помощью регулярных выражений.
    
    Args:
        text: Любая строка (лог, конфиг, json-фрагмент).
        
    Returns:
        Список найденных строк, похожих на IP (например, ['192.168.1.1', '10.0.0.0/8']).
    """
    # Регулярка ищет 4 группы цифр через точку, опционально с маской
    ipv4_pattern = r'(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?'
    matches = re.findall(ipv4_pattern, text)
    return [match.strip() for match in matches]


def parse_ipv6(text: str) -> List[str]:
    """
    Ищет IPv6 адреса.
    
    Args:
        text: Входная строка.
        
    Returns:
        Список найденных IPv6 кандидатов.
    """
    # Регулярка для IPv6 сложная, покрывает сжатые (::) и полные форматы
    ipv6_pattern = r'(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}(?:/\d{1,3})?'
    matches = re.findall(ipv6_pattern, text)
    return [match.strip() for match in matches]


def parse_ipv4_ranges(text: str) -> List[IPv4Network]:
    """
    Ищет диапазоны IP (например, "192.168.1.1 - 192.168.1.10") 
    и преобразует их в список CIDR подсетей.
    """
    # Regex ищет: IP <пробелы> - <пробелы> IP
    # Группы захвата: (Start IP), (End IP)
    range_pattern = r'((?:\d{1,3}\.){3}\d{1,3})\s*-\s*((?:\d{1,3}\.){3}\d{1,3})'
    matches = re.findall(range_pattern, text)
    
    cidr_results = []
    
    for start_str, end_str in matches:
        try:
            start_ip = ipaddress.IPv4Address(start_str)
            end_ip = ipaddress.IPv4Address(end_str)
            
            # ipaddress требует, чтобы start <= end
            if start_ip > end_ip:
                # Если перепутаны местами, меняем
                start_ip, end_ip = end_ip, start_ip
            
            # summarize_address_range возвращает итератор сетей, покрывающих диапазон
            subnets = ipaddress.summarize_address_range(start_ip, end_ip)
            cidr_results.extend(subnets)
            
        except ValueError:
            # Если IP некорректен (напр. 999.999.999.999), пропускаем
            pass
            
    return cidr_results


def normalize_single_ip(candidate: str, strict: bool = False) -> Union[IPv4Network, IPv6Network, None]:
    """
    Превращает грязную строку в чистый объект IP-сети.
    
    Исправляет известную проблему Python (CVE-2021-29921), когда адреса с 
    ведущими нулями (010.0.0.1) считаются ошибочными, хотя в сетевом мире это норма.

    Args:
        candidate: Строка-кандидат (например, "010.0.0.1" или "1.1.1.1/32").

    Returns:
        Объект сети или None, если парсинг невозможен.
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
            try:
                ip = ipaddress.ip_address(candidate)
                if ip.version == 4:
                    return ipaddress.IPv4Network(f"{ip}/32", strict=False)
                return ipaddress.IPv6Network(f"{ip}/128", strict=False)
            except ValueError:
                return None

    try:
        return ipaddress.ip_network(candidate, strict=False)
    except ValueError:
        pass

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
    text: str,
    strict: bool = False
) -> List[Union[IPv4Network, IPv6Network]]:
    prefixes: List[Union[IPv4Network, IPv6Network]] = []

    ranges = parse_ipv4_ranges(text)
    prefixes.extend(ranges)

    all_candidates = parse_ipv4(text) + parse_ipv6(text)

    for candidate in all_candidates:
        if not candidate:
            continue
        network = normalize_single_ip(candidate, strict=strict)
        if network is not None:
            prefixes.append(network)

    return prefixes

# --- Универсальный читатель ---

def _parse_lines_generator(
    line_iterator: Iterator[str],
    progress: Union[Progress, None] = None,
    task_id: Union[TaskID, None] = None,
    strict: bool = False,
) -> Generator[Union[IPv4Network, IPv6Network], None, None]:
    for line_num, line in enumerate(line_iterator, 1):
        if line_num > MAX_LINE_COUNT:
            raise ValueError(f"Input exceeds the safety limit of {MAX_LINE_COUNT} lines.")

        if progress and task_id is not None:
            line_bytes = len(line.encode("utf-8")) + 1
            progress.update(task_id, advance=line_bytes)

        line = line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            prefixes = extract_prefixes_from_text(line, strict=strict)
        except ValueError as exc:
            raise ValueError(f"Line {line_num}: {exc}") from exc

        if prefixes:
            for prefix in prefixes:
                yield prefix
        else:
            try:
                yield ipaddress.ip_network(line, strict=strict)
            except ValueError:
                pass


def _parse_comments_generator(
    line_iterator: Iterator[str],
    strict: bool = False,
) -> Generator[Tuple[Union[IPv4Network, IPv6Network], str], None, None]:
    for line_num, line in enumerate(line_iterator, 1):
        if line_num > MAX_LINE_COUNT:
            raise ValueError(f"Input exceeds safety limit of {MAX_LINE_COUNT} lines.")

        line_stripped = line.strip()
        if not line_stripped:
            continue

        if "#" in line:
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


# --- File Specific Readers ---

def _read_txt_generator(
    path: Path,
    progress: Progress,
    task_id: TaskID,
    strict: bool = False
) -> Generator[Union[IPv4Network, IPv6Network], None, None]:
    with open(path, 'r', encoding='utf-8') as f:
        yield from _parse_lines_generator(f, progress, task_id, strict=strict)


def _read_csv_generator(path: Path, progress: Progress, task_id: TaskID, column_name: str = 'prefix', strict: bool = False) -> Generator[Union[IPv4Network, IPv6Network], None, None]:
    """Обертка для чтения CSV (учитывает колонки)."""
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            count += 1
            if count > MAX_LINE_COUNT:
                raise ValueError(f"CSV exceeds limit of {MAX_LINE_COUNT} rows.")
            
            progress.update(task_id, advance=50) # Примерный прогресс
            
            prefix_text = row.get(column_name, '').strip()
            if not prefix_text:
                continue

            extracted = extract_prefixes_from_text(prefix_text)
            if extracted:
                for network in extracted:
                    yield network
            else:
                try:
                    yield ipaddress.ip_network(prefix_text, strict=strict)
                except ValueError:
                    pass


def _read_json_generator(
    path: Path,
    progress: Progress,
    task_id: TaskID,
    key_name: str = 'prefixes',
    strict: bool = False
) -> Generator[Union[IPv4Network, IPv6Network], None, None]:
    """Потоковое чтение JSON."""
    with open(path, 'rb') as f:
        wrapped_file = ProgressFileWrapper(f, progress, task_id)
        parser_path = f"{key_name}.item"
        count = 0
        try:
            for item in ijson.items(wrapped_file, parser_path):
                count += 1
                if count > MAX_LINE_COUNT:
                    raise ValueError(f"JSON array exceeds the limit of {MAX_LINE_COUNT} items.")
                
                prefix_text = str(item).strip()
                extracted = extract_prefixes_from_text(prefix_text, strict=strict)
                if extracted:
                    for network in extracted:
                        yield network
                else:
                    try:
                        yield ipaddress.ip_network(prefix_text, strict=strict)
                    except ValueError:
                        print(f"Warning: Invalid prefix '{prefix_text}' in JSON", file=sys.stderr)
        except ijson.JSONError:
            pass


# --- Public API ---

def read_stream(stream: TextIO, strict: bool = False) -> Iterator[Union[IPv4Network, IPv6Network]]:
    yield from _parse_lines_generator(stream, strict=strict)


def read_stream_with_comments(
    stream: TextIO,
    strict: bool = False
) -> Generator[Tuple[Union[IPv4Network, IPv6Network], str], None, None]:
    """
    Чтение из STDIN с сохранением комментариев.
    
    Используется для команд optimize --keep-comments и merge, 
    когда данные поступают через пайп.
    """
    yield from _parse_comments_generator(stream, strict=strict)


def read_networks(
    file_path: Union[str, Path],
    show_progress: bool = True,
    strict: bool = False
) -> Iterator[Union[IPv4Network, IPv6Network]]:
    """
    Чтение из файла на диске с автоматическим определением формата.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File size exceeds safety limit ({MAX_FILE_SIZE_MB} MB).")

    should_show = show_progress and file_size > 1024 * 1024
    extension = path.suffix.lower()

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        transient=True,
        disable=not should_show
    ) as progress:
        
        task_id = progress.add_task(f"Reading {path.name}", total=file_size)

        if extension == ".json":
            yield from _read_json_generator(path, progress, task_id, strict=strict)
        else:
            yield from _read_txt_generator(path, progress, task_id, strict=strict)


def read_prefixes_with_comments(
    file_path: Path,
    strict: bool = False
) -> Generator[Tuple[Union[IPv4Network, IPv6Network], str], None, None]:
    """
    Чтение файла с сохранением комментариев.
    """
    path = Path(file_path)
    if path.stat().st_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File too large for merge with comments.")

    with open(file_path, "r", encoding="utf-8") as f:
        yield from _parse_comments_generator(f, strict=strict)