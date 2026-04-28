"""
Модуль для статистического анализа IP-префиксов.

Содержит функции для подсчета количества адресов, уникальных IP,
а также расчета коэффициента сжатия списков.
"""
from typing import List, Dict, Union, Iterable, Tuple
from collections import Counter

from ipaddress import IPv4Network, IPv6Network

from .operations.aggregator import aggregate
from .operations.sorter import sort_networks
from .operations.nested import remove_nested


def count_unique_ips(prefixes: Iterable[Union[IPv4Network, IPv6Network]]) -> int:
    """
    Подсчитывает количество уникальных IP-адресов, покрываемых списком префиксов.

    Для корректного подсчета необходимо устранить пересечения сетей.
    Поэтому функция выполняет полный цикл оптимизации (сортировка,
    удаление вложенности, агрегация) перед подсчетом.

    Args:
        prefixes: Итератор или список объектов IP сетей.

    Returns:
        Общее количество уникальных IP-адресов (int).
    """
    # 1. Сортировка (Broadest First) - необходима для корректной работы remove_nested
    sorted_prefixes = sort_networks(prefixes)
    
    # 2. Удаление вложенных сетей - устраняет дублирование адресов в подсетях.
    # Используем assume_sorted=True для оптимизации, так как только что отсортировали.
    clean_prefixes = remove_nested(sorted_prefixes, assume_sorted=True)
    
    # 3. Агрегация - объединяет смежные блоки для минимизации списка.
    # На количество уникальных IP это не влияет, но ускоряет итерацию.
    aggregated_prefixes = aggregate(clean_prefixes)

    total_ips = 0
    for network in aggregated_prefixes:
        # num_addresses возвращает общее число адресов в подсети (включая network и broadcast)
        total_ips += int(network.num_addresses)

    return total_ips


def count_total_ips_in_prefixes(prefixes: Iterable[Union[IPv4Network, IPv6Network]]) -> int:
    """
    Подсчитывает сырую сумму IP-адресов во всех префиксах.

    Не учитывает пересечения. Если один адрес входит в две сети,
    он будет посчитан дважды. Используется для сравнения До и После.

    Args:
        prefixes: Итератор или список объектов IP сетей.

    Returns:
        Суммарное количество адресов.
    """
    total_ips = 0
    for network in prefixes:
        total_ips += int(network.num_addresses)

    return total_ips


def get_prefix_statistics(prefixes: List[Union[IPv4Network, IPv6Network]]) -> Dict[str, Union[int, float]]:
    """
    Генерирует полный отчет со статистикой по списку префиксов.

    Рассчитывает метрики до и после оптимизации, включая коэффициент сжатия.

    Args:
        prefixes: Список объектов IP сетей.

    Returns:
        Словарь с метриками:
        - original_prefix_count: Исходное количество сетей.
        - optimized_prefix_count: Количество сетей после оптимизации.
        - compression_ratio_percent: Процент сжатия таблицы.
        - original_total_ips: "Сырая" сумма адресов.
        - unique_ips: Реальное количество уникальных адресов.
        - addresses_saved: Разница (пересечения/дубликаты).
    """
    original_count = len(prefixes)
    original_total_ips = count_total_ips_in_prefixes(prefixes)

    # Эмуляция полного цикла оптимизации для получения метрик После
    sorted_prefixes = sort_networks(prefixes)
    clean_prefixes = remove_nested(sorted_prefixes, assume_sorted=True)
    optimized_prefixes = aggregate(clean_prefixes)
    
    optimized_count = len(optimized_prefixes)
    
    # Подсчет уникальных IP (функция сама выполнит оптимизацию внутри)
    unique_ips = count_unique_ips(prefixes)

    # Расчет коэффициента сжатия (насколько уменьшилось количество строк)
    compression_ratio = 0.0
    if original_count > 0:
        compression_ratio = (original_count - optimized_count) / original_count * 100

    return {
        "original_prefix_count": original_count,
        "optimized_prefix_count": optimized_count,
        "compression_ratio_percent": round(compression_ratio, 2),
        "original_total_ips": original_total_ips,
        "unique_ips": unique_ips,
        "addresses_saved": original_total_ips - unique_ips
    }


def get_duplicate_prefixes(
    prefixes: Iterable[Union[IPv4Network, IPv6Network]]
) -> List[Tuple[str, int]]:
    """
    Возвращает список дубликатов (префикс, количество повторений) для префиксов,
    встреченных более одного раза.
    """
    counts = Counter(str(p) for p in prefixes)
    return [(prefix, count) for prefix, count in counts.items() if count > 1]