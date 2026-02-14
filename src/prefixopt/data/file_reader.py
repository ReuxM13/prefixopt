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


def normalize_single_ip(candidate: str) -> Union[IPv4Network, IPv6Network, None]:
    """
    Превращает грязную строку в чистый объект IP-сети.
    
    Исправляет известную проблему Python (CVE-2021-29921), когда адреса с 
    ведущими нулями (010.0.0.1) считаются ошибочными, хотя в сетевом мире это норма.

    Args:
        candidate: Строка-кандидат (например, "010.0.0.1" или "1.1.1.1/32").

    Returns:
        Объект сети или None, если парсинг невозможен.
    """
    # 1. Счастливый путь: пробуем стандартный парсер
    try:
        return ipaddress.ip_network(candidate, strict=False)
    except ValueError:
        pass

    # 2. Чистим ведущие нули
    if '.' in candidate and ':' not in candidate:
        try:
            parts = candidate.split('/')
            ip_part = parts[0]
            mask_part = f"/{parts[1]}" if len(parts) > 1 else ""
            
            # Разбиваем по точкам, превращаем в int (убирает 0), собираем обратно
            clean_ip = ".".join(str(int(octet)) for octet in ip_part.split('.'))
            clean_candidate = f"{clean_ip}{mask_part}"
            
            return ipaddress.ip_network(clean_candidate, strict=False)
        except (ValueError, IndexError):
            pass

    # 3. Одиночные IP без маски
    try:
        # Повторяем чистку нулей для хоста
        if '.' in candidate and ':' not in candidate:
             clean_ip = ".".join(str(int(octet)) for octet in candidate.split('.'))
             ip = ipaddress.ip_address(clean_ip)
        else:
             ip = ipaddress.ip_address(candidate)

        # Превращаем хост в сеть /32 или /128
        if ip.version == 4:
            return ipaddress.IPv4Network(f"{ip}/32", strict=False)
        else:
            return ipaddress.IPv6Network(f"{ip}/128", strict=False)
    except ValueError:
        # Это точно не IP (например, "Version 1.0")
        return None


def extract_prefixes_from_text(text: str) -> List[Union[IPv4Network, IPv6Network]]:
    """
    Универсальный экстрактор.
    
    Вытаскивает все IP-адреса из строки, игнорируя текст вокруг.
    Это основа всеядности утилиты.
    """
    prefixes = []
    all_candidates = parse_ipv4(text) + parse_ipv6(text)

    for candidate in all_candidates:
        if not candidate:
            continue
        network = normalize_single_ip(candidate)
        if network is not None:
            prefixes.append(network)

    return prefixes


# --- Универсальный читатель ---

def _parse_lines_generator(
    line_iterator: Iterator[str], 
    progress: Union[Progress, None] = None, 
    task_id: Union[TaskID, None] = None
) -> Generator[Union[IPv4Network, IPv6Network], None, None]:
    """
    Ядро чтения. Берет любой поток строк (файл или STDIN) и выдает объекты IP.
    
    Args:
        line_iterator: Итерируемый объект, выдающий строки (файл или stdin).
        progress: Объект прогресс-бара (опционально).
        task_id: ID задачи в прогресс-баре (опционально).
        
    Yields:
        Объекты IPv4Network / IPv6Network.
    """
    for line_num, line in enumerate(line_iterator, 1):
        
        # Если кто-то загнал в пайп бесконечный /dev/urandom
        if line_num > MAX_LINE_COUNT:
            raise ValueError(f"Input exceeds the safety limit of {MAX_LINE_COUNT} lines.")

        # Обновляем прогресс
        if progress and task_id is not None:
            # Считаем байты приблизительно, так как line может быть декодирована
            line_bytes = len(line.encode('utf-8')) + 1
            progress.update(task_id, advance=line_bytes)
        
        line = line.strip()
        # Игнорируем пустые строки и комментарии
        if not line or line.startswith('#'):
            continue

        # Используем экстрактор. Он найдет IP даже если это строка JSON или CSV
        prefixes = extract_prefixes_from_text(line)
        
        if prefixes:
            for prefix in prefixes:
                yield prefix
        else:
            # Если regex не справился (очень редкий случай),
            # пробуем скормить строку целиком в ipaddress
            try:
                yield ipaddress.ip_network(line, strict=False)
            except ValueError:
                # Молча пропускаем мусор, но можно раскомментировать для отладки
                # print(f"Warning: Invalid line {line_num}", file=sys.stderr)
                pass


# --- File Specific Readers ---

def _read_txt_generator(path: Path, progress: Progress, task_id: TaskID) -> Generator[Union[IPv4Network, IPv6Network], None, None]:
    """Обертка для чтения TXT файлов."""
    with open(path, 'r', encoding='utf-8') as f:
        yield from _parse_lines_generator(f, progress, task_id)


def _read_csv_generator(path: Path, progress: Progress, task_id: TaskID, column_name: str = 'prefix') -> Generator[Union[IPv4Network, IPv6Network], None, None]:
    """Обертка для чтения CSV (учитывает колонки)."""
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            # CSV специфичная логика подсчета (так как enumerate внутри не сработает на reader напрямую)
            count += 1
            if count > MAX_LINE_COUNT:
                raise ValueError(f"CSV exceeds limit of {MAX_LINE_COUNT} rows.")
            
            progress.update(task_id, advance=50) # Примерный прогресс
            
            prefix_text = row.get(column_name, '').strip()
            if not prefix_text:
                continue

            # Используем тот же экстрактор
            extracted = extract_prefixes_from_text(prefix_text)
            if extracted:
                for network in extracted:
                    yield network
            else:
                try:
                    yield ipaddress.ip_network(prefix_text, strict=False)
                except ValueError:
                    pass


def _read_json_generator(path: Path, progress: Progress, task_id: TaskID, key_name: str = 'prefixes') -> Generator[Union[IPv4Network, IPv6Network], None, None]:
    """
    Потоковое чтение JSON с помощью ijson.
    Использует бинарный режим ('rb') для максимальной производительности.
    """
    # Открываем в BINARY режиме ('rb')
    with open(path, 'rb') as f:
        # Оборачиваем файл в прокси для прогресс-бара
        wrapped_file = ProgressFileWrapper(f, progress, task_id)
        
        parser_path = f"{key_name}.item"
        
        count = 0
        try:
            for item in ijson.items(wrapped_file, parser_path):
                count += 1
                if count > MAX_LINE_COUNT:
                    raise ValueError(f"JSON array exceeds the limit of {MAX_LINE_COUNT} items.")
                
                # ijson сам декодирует байты в строки/числа Python
                prefix_text = str(item).strip()
                
                extracted = extract_prefixes_from_text(prefix_text)
                if extracted:
                    for network in extracted:
                        yield network
                else:
                    try:
                        yield ipaddress.ip_network(prefix_text, strict=False)
                    except ValueError:
                        print(f"Warning: Invalid prefix '{prefix_text}' in JSON", file=sys.stderr)
                        
        except ijson.JSONError:
            pass


# --- Public API ---

def read_stream(stream: TextIO) -> Iterator[Union[IPv4Network, IPv6Network]]:
    """
    Чтение из стандартного ввода (STDIN / Pipe).
    
    Для потоков мы используем стратегию всеядного парсинга:
    Мы не пытаемся угадать формат (JSON или CSV), а просто читаем поток
    построчно и ищем в каждой строке IP-адреса с помощью Regex.
    Это работает надежно для 99% случаев (логи, дампы, списки).
    
    Args:
        stream: Объект потока (sys.stdin).
        
    Yields:
        Объекты IP сетей.
    """
    # Прогресс-бар для STDIN невозможен (не знаем длину), поэтому просто читаем
    yield from _parse_lines_generator(stream)


def read_networks(file_path: Union[str, Path], show_progress: bool = True) -> Iterator[Union[IPv4Network, IPv6Network]]:
    """
    Чтение из файла на диске. Автоматически выбирает парсер по расширению.
    
    Args:
        file_path: Путь к файлу.
        show_progress: Показывать ли бар (для больших файлов).
        
    Returns:
        Итератор объектов сетей.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Проверка размера файла
    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File size exceeds safety limit ({MAX_FILE_SIZE_MB} MB).")

    # Включаем прогресс-бар только если файл ощутимый (> 1MB)
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

        if extension == '.csv':
            yield from _read_csv_generator(path, progress, task_id)
        elif extension == '.json':
            yield from _read_json_generator(path, progress, task_id)
        else:
            yield from _read_txt_generator(path, progress, task_id)


def read_prefixes_with_comments(file_path: Path) -> Generator[Tuple[Union[IPv4Network, IPv6Network], str], None, None]:
    """
    Специальный режим чтения для merge --keep-comments.
    Сохраняет комментарии, привязанные к строкам.
    
    Returns:
        Генератор кортежей (Сеть, Текст Комментария).
    """
    path = Path(file_path)
    
    if path.stat().st_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File too large for merge with comments.")

    # Используем простую логику чтения, так как нам нужна привязка к строке
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line_num > MAX_LINE_COUNT:
                raise ValueError(f"File exceeds {MAX_LINE_COUNT} lines.")

            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Парсинг комментария
            if '#' in line:
                content, comment_raw = line.split('#', 1)
                cleaned_comment = comment_raw.strip()
                comment = f"# {cleaned_comment}" if cleaned_comment else ""
            else:
                content = line
                comment = ""

            # Извлечение IP из контентной части
            prefixes = extract_prefixes_from_text(content)
            for p in prefixes:
                yield (p, comment)