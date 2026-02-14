"""
Публичный API библиотеки prefixopt.

Этот модуль предоставляет высокоуровневые функции для использования prefixopt
в сторонних Python-скриптах.

Основные принципы:
1. Все функции принимают гибкий ввод (InputSource): пути к файлам, строки или списки.
2. Функции возвращают чистые объекты (List[IPv4Network], и т.д.), а не печатают в консоль.
3. Прогресс-бары и цветной вывод отключены по умолчанию.
"""

import ipaddress
import itertools
from pathlib import Path
from typing import Union, Iterable, Iterator, List, Tuple, Dict, Optional, Any

# Импорт базовых типов
from .core.ip_utils import IPNet, normalize_prefix, is_subnet_of

# Импорт функционала чтения данных
from .data.file_reader import (
    read_networks, 
    extract_prefixes_from_text, 
    read_prefixes_with_comments
)

# Импорт логики ядра
from .core.pipeline import process_prefixes
from .core.operations.subtractor import subtract_networks
from .core.operations.diff import calculate_diff
from .core.operations.subnetter import split_network
from .core.ip_counter import get_prefix_statistics


# Определяем тип входных данных: 
# Это может быть путь (Path), строка (str) или итератор (список, генератор).
InputSource = Union[str, Path, Iterable[Union[str, IPNet]]]


def load(source: InputSource) -> Iterator[IPNet]:
    """
    Универсальный загрузчик данных.

    Преобразует входные данные любого поддерживаемого формата в поток объектов IP-сетей.
    Автоматически определяет, является ли источник файлом, сырой строкой или списком.

    Args:
        source: Источник данных. Может быть:
            - pathlib.Path: Путь к файлу.
            - str: Путь к файлу (строкой) ИЛИ текст с IP-адресами.
            - Iterable: Список строк или объектов IPNet.

    Yields:
        IPNet: Объекты IPv4Network или IPv6Network по одному.

    Raises:
        ValueError: Если тип источника не поддерживается.
    """
    # 1. Если передан объект Path — проверяем наличие файла
    if isinstance(source, Path):
        if source.exists() and source.is_file():
            # show_progress=False отключает визуальный шум (UI)
            yield from read_networks(source, show_progress=False)
            return

    # 2. Если передана строка
    if isinstance(source, str):
        try:
            # Пытаемся понять, путь ли это
            path_obj = Path(source)
            # Ограничение длины < 255 — защита от передачи огромного текста в конструктор Path
            if len(source) < 255 and path_obj.exists() and path_obj.is_file():
                yield from read_networks(path_obj, show_progress=False)
                return
        except OSError:
            # Если ОС ругается на недопустимые символы в пути — значит это просто текст
            pass
        
        # Если это не файл, считаем, что это сырой текст (CSV, JSON-фрагмент, лог)
        yield from extract_prefixes_from_text(source)
        return

    # 3. Если передан итерируемый объект (список, кортеж, генератор)
    if isinstance(source, Iterable) and not isinstance(source, bytes):
        for item in source:
            if isinstance(item, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
                yield item
            else:
                # Если элементы списка — строки, извлекаем из них IP
                yield from extract_prefixes_from_text(str(item))
        return
    
    raise ValueError(f"Unsupported input type: {type(source)}")


def _optimize_with_comments(source: InputSource) -> List[Tuple[IPNet, str]]:
    """
    Внутренняя функция для обработки списков с сохранением комментариев.
    
    Используется, когда нельзя применять агрегацию (склейку сетей), так как
    это уничтожило бы привязку комментария к конкретной подсети.
    Выполняет только дедупликацию и сортировку.
    """
    data_iter: Iterator[Tuple[IPNet, str]]
    
    # Пытаемся использовать специальный читатель, если это файл
    is_file = False
    if isinstance(source, Path) and source.exists():
        is_file = True
    elif isinstance(source, str):
        try:
            p = Path(source)
            if len(source) < 255 and p.exists() and p.is_file():
                is_file = True
        except OSError:
            pass

    if is_file:
        # Читаем файл построчно, сохраняя комментарии после символа #
        path_ref = Path(str(source))
        data_iter = read_prefixes_with_comments(path_ref)
    else:
        # Если источник не файл (например, список строк), мы не можем гарантированно
        # восстановить комментарии. Возвращаем пустые строки вместо комментов.
        data_iter = ((net, "") for net in load(source))

    # Дедупликация через словарь. Ключ - строковый IP.
    # Это позволяет убрать полные дубликаты.
    unique_map: Dict[str, str] = {}
    
    for ip, comment in data_iter:
        ip_str = str(ip)
        if ip_str not in unique_map:
            unique_map[ip_str] = comment
        else:
            # Если дубликат имеет комментарий, а оригинал нет — обновляем
            if not unique_map[ip_str] and comment:
                unique_map[ip_str] = comment

    # Превращаем словарь обратно в список кортежей
    merged_list = []
    for ip_str_key, comm in unique_map.items():
        net_obj = ipaddress.ip_network(ip_str_key, strict=False)
        merged_list.append((net_obj, comm))

    # Сортировка Broadest First (Версия -> IP -> Маска)
    merged_list.sort(key=lambda item: (
        item[0].version, 
        int(item[0].network_address), 
        item[0].prefixlen
    ))
    return merged_list


def optimize(
    source: InputSource,
    ipv4_only: bool = False,
    ipv6_only: bool = False,
    remove_nested: bool = True,
    aggregate: bool = True,
    bogons: bool = False,
    keep_comments: bool = False
) -> Union[List[IPNet], List[Tuple[IPNet, str]]]:
    """
    Основная функция оптимизации.

    Args:
        source: Входные данные.
        ipv4_only: Оставить только IPv4.
        ipv6_only: Оставить только IPv6.
        remove_nested: Удалять вложенные подсети (например, 10.1.1.1/32 внутри 10.0.0.0/8).
        aggregate: Объединять смежные сети (CIDR summarization).
        bogons: Удалить частные, локальные и зарезервированные сети.
        keep_comments: Если True, возвращает список кортежей (IP, Comment). 
                       При этом отключается агрегация и удаление вложенных.

    Returns:
        List[IPNet]: Список оптимизированных сетей (по умолчанию).
        List[Tuple[IPNet, str]]: Если включен keep_comments.
    """
    if keep_comments:
        return _optimize_with_comments(source)

    # Стандартный путь через Pipeline
    iterator = load(source)
    result_iter = process_prefixes(
        iterator,
        sort=True, # Для API всегда сортируем результат
        remove_nested=remove_nested,
        aggregate=aggregate,
        ipv4_only=ipv4_only,
        ipv6_only=ipv6_only,
        bogons=bogons
    )
    return list(result_iter)


def add(
    source: InputSource, 
    new_prefix: str, 
    keep_comments: bool = False
) -> Union[List[IPNet], List[Tuple[IPNet, str]]]:
    """
    Добавляет новый префикс в список и возвращает обновленный набор данных.
    
    Args:
        source: Исходный список.
        new_prefix: Строка с новым префиксом (например, "10.0.0.1/32").
        keep_comments: Сохранять ли комментарии (см. optimize).
    """
    net = normalize_prefix(new_prefix)
    
    if keep_comments:
        data = _optimize_with_comments(source)
        # Проверяем, есть ли уже такой IP в списке
        exists = any(item[0] == net for item in data)
        if not exists:
            # Добавляем новый IP с авто-комментарием
            data.append((net, f"# Added: {new_prefix}"))
            # Пересортируем список
            data.sort(key=lambda item: (
                item[0].version, 
                int(item[0].network_address), 
                item[0].prefixlen
            ))
        return data

    # Стандартный путь
    data_list = list(load(source))
    if net not in data_list:
        data_list.append(net)
        
    return optimize(data_list)


def filter(
    source: InputSource,
    exclude_private: bool = False,
    bogons: bool = False,
) -> List[IPNet]:
    """
    Фильтрует список сетей по критериям (без агрегации).
    
    Используется для очистки списка от "мусорных" адресов (private, multicast и т.д.),
    сохраняя при этом структуру исходных сетей.
    """
    iterator = load(source)
    result_iter = process_prefixes(
        iterator,
        sort=False, # Фильтр старается сохранить исходный порядок
        remove_nested=False,
        aggregate=False,
        exclude_private=exclude_private,
        bogons=bogons,
        exclude_unspecified=True
    )
    return list(result_iter)


def merge(
    *sources: InputSource,
    keep_comments: bool = False
) -> Union[List[IPNet], List[Tuple[IPNet, str]]]:
    """
    Объединяет несколько источников данных в один оптимизированный список.
    
    Пример:
        api.merge("list1.txt", ["1.1.1.1"], "list2.csv")
        api.merge("conf1.txt", "conf2.txt", keep_comments=True)
        
    Args:
        *sources: Произвольное количество источников (пути или списки).
        keep_comments: Сохранять комментарии (отключает агрегацию).
    """
    if keep_comments:
        # 1. Загружаем все источники с комментариями по отдельности
        all_data: List[Tuple[IPNet, str]] = []
        for src in sources:
            all_data.extend(_optimize_with_comments(src))
            
        # 2. Глобальная дедупликация
        unique_map: Dict[str, str] = {}
        for ip, comment in all_data:
            ip_str = str(ip)
            # Если IP уже был, обновляем коммент, только если старый был пуст, а новый нет
            if ip_str not in unique_map:
                unique_map[ip_str] = comment
            elif not unique_map[ip_str] and comment:
                unique_map[ip_str] = comment
                
        # 3. Конвертация обратно
        merged_list = []
        for ip_str_key, comm in unique_map.items():
            net_obj = ipaddress.ip_network(ip_str_key, strict=False)
            merged_list.append((net_obj, comm))
            
        # 4. Глобальная сортировка
        merged_list.sort(key=lambda item: (
            item[0].version, 
            int(item[0].network_address), 
            item[0].prefixlen
        ))
        return merged_list

    else:
        # Стандартный путь: объединяем все потоки и прогоняем через пайплайн
        combined_iter = itertools.chain.from_iterable(load(src) for src in sources)
        result_iter = process_prefixes(
            combined_iter,
            sort=True,
            remove_nested=True,
            aggregate=True
        )
        return list(result_iter)


def intersect(source_a: InputSource, source_b: InputSource) -> List[IPNet]:
    """
    Находит пересечение двух списков.
    """
    set_a = set(load(source_a))
    set_b = set(load(source_b))
    
    common = set_a.intersection(set_b)
    
    list_a = list(set_a)
    list_b = list(set_b)
    
    for net1 in list_a:
        for net2 in list_b:
            if net1 in common or net2 in common:
                continue
            
            if net1.overlaps(net2):
                if net1.version == net2.version:
                    common.add(net1)
                    common.add(net2)

    return optimize(list(common)) # type: ignore


def split(target: str, length: int) -> List[IPNet]:
    """
    Разбивает сеть на подсети заданной длины (CIDR).
    """
    net = normalize_prefix(target)
    return split_network(net, length)


def exclude(source: InputSource, target: InputSource) -> List[IPNet]:
    """
    Вычитает сети (target) из источника (source).
    """
    src_iter = load(source)
    dst_iter = load(target)

    raw_result = subtract_networks(src_iter, dst_iter)

    final_iter = process_prefixes(
        raw_result,
        sort=True,
        remove_nested=True,
        aggregate=True
    )
    return list(final_iter)


def diff(
    new_source: InputSource,
    old_source: InputSource
) -> Tuple[List[IPNet], List[IPNet], List[IPNet]]:
    """
    Сравнивает два набора данных.

    Returns:
        Кортеж (Added, Removed, Unchanged).
    """
    def prepare(src):
        return list(process_prefixes(load(src), sort=True, remove_nested=True, aggregate=True))

    new_list = prepare(new_source)
    old_list = prepare(old_source)

    added, removed, unchanged = calculate_diff(new_list, old_list)

    def to_sorted_list(data_set):
        return list(process_prefixes(data_set, sort=True, remove_nested=False, aggregate=False))

    return (
        to_sorted_list(added),
        to_sorted_list(removed),
        to_sorted_list(unchanged)
    )


def stats(source: InputSource) -> Dict[str, Union[int, float]]:
    """
    Возвращает словарь со статистикой.
    """
    data_list = list(load(source))
    return get_prefix_statistics(data_list)


def check(target: str, source: InputSource) -> List[IPNet]:
    """
    Проверяет, входит ли target (IP или сеть) в список source.
    """
    try:
        check_item = ipaddress.ip_network(target, strict=False)
    except ValueError:
        try:
            check_item = ipaddress.ip_address(target) # type: ignore
        except ValueError:
            return []

    containing = []
    
    for net in load(source):
        if net.version != check_item.version:
            continue
        
        if isinstance(check_item, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            if check_item in net:
                containing.append(net)
        else: 
            if is_subnet_of(check_item, net):
                containing.append(net)
    
    return containing


def merge_with_comments(
    file1: Union[str, Path], 
    file2: Union[str, Path]
) -> List[Tuple[IPNet, str]]:
    """
    Устаревшая функция для совместимости.
    Использует новую реализацию merge с флагом keep_comments.
    """
    # Результат merge с keep_comments=True гарантированно List[Tuple]
    return merge(file1, file2, keep_comments=True) # type: ignore