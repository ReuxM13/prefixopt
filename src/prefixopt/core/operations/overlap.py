"""
Модуль для поиска пересечений между списками IP-сетей.

Содержит линейные алгоритмы для поиска точных и частичных перекрытий
в отсортированных списках. Сложность O(N+M).
"""
from typing import List, Tuple

from ..ip_utils import IPNet


def find_two_list_overlaps(
    sorted_a: List[IPNet],
    sorted_b: List[IPNet],
) -> List[Tuple[IPNet, IPNet]]:
    """
    Линейный поиск пересечений между двумя отсортированными списками.

    Использует two-pointer алгоритм по диапазонам адресов.
    Требует сортировки обоих списков в порядке Broadest First.

    Args:
        sorted_a: Первый отсортированный список.
        sorted_b: Второй отсортированный список.

    Returns:
        Список кортежей (net_a, net_b) с перекрывающимися парами.
    """
    overlaps: List[Tuple[IPNet, IPNet]] = []
    i, j = 0, 0
    len_a, len_b = len(sorted_a), len(sorted_b)

    while i < len_a and j < len_b:
        n1, n2 = sorted_a[i], sorted_b[j]

        if n1.version < n2.version:
            i += 1
            continue
        if n1.version > n2.version:
            j += 1
            continue

        s1 = int(n1.network_address)
        e1 = int(n1.broadcast_address)
        s2 = int(n2.network_address)
        e2 = int(n2.broadcast_address)

        if max(s1, s2) <= min(e1, e2):
            overlaps.append((n1, n2))
            if e1 < e2:
                i += 1
            elif e2 < e1:
                j += 1
            else:
                i += 1
                j += 1
        elif e1 < s2:
            i += 1
        else:
            j += 1

    return overlaps


def find_self_overlaps(
    sorted_list: List[IPNet],
) -> List[Tuple[IPNet, IPNet]]:
    """
    Поиск пересечений внутри одного отсортированного списка.

    Для каждого элемента проверяются последующие до выхода
    за broadcast-границу. Требует сортировки Broadest First.

    Args:
        sorted_list: Отсортированный список.

    Returns:
        Список кортежей (net_i, net_j) с перекрывающимися парами.
    """
    overlaps: List[Tuple[IPNet, IPNet]] = []
    length = len(sorted_list)

    for i in range(length):
        net_i = sorted_list[i]
        end_i = int(net_i.broadcast_address)

        for j in range(i + 1, length):
            net_j = sorted_list[j]

            if net_i.version != net_j.version:
                break
            if int(net_j.network_address) > end_i:
                break

            overlaps.append((net_i, net_j))

    return overlaps
