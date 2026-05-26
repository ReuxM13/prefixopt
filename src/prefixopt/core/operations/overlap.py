"""
Модуль для поиска пересечений между списками IP-сетей.

Содержит линейные алгоритмы для поиска точных и частичных перекрытий
в отсортированных списках. Сложность O(N+M).
"""
from typing import Dict, List, Tuple, Set

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


# ---------------------------------------------------------------------------
# Shared helpers for classifying overlap results.
# Эти функции используются повторно в GUI-сервисах и CLI,
# чтобы избежать дублирования паттерна классификации.
# ---------------------------------------------------------------------------


def classify_overlap_pair(
    net_a: IPNet,
    net_b: IPNet,
    name_a: str,
    name_b: str,
) -> Tuple[bool, IPNet, IPNet, str, str]:
    """
    Классифицирует пару перекрывающихся сетей и возвращает кортеж.

    Определяет, какая сеть является подсетью, а какая — суперсетью.
    При частичном перекрытии (без вложенности) сохраняется исходный порядок.

    Args:
        net_a: Первая сеть.
        net_b: Вторая сеть.
        name_a: Имя источника первой сети.
        name_b: Имя источника второй сети.

    Returns:
        Кортеж (is_identical, subnet, supernet, source_subnet, source_supernet).
        Если сети идентичны, возвращается (True, net_a, net_b, name_a, name_b).
    """
    if net_a == net_b:
        return True, net_a, net_b, name_a, name_b

    if net_a.subnet_of(net_b):
        return False, net_a, net_b, name_a, name_b

    if net_b.subnet_of(net_a):
        return False, net_b, net_a, name_b, name_a

    return False, net_a, net_b, name_a, name_b


def build_intersection_fragments(
    exact_matches: Set[IPNet],
    raw_overlaps: List[Tuple[IPNet, IPNet]],
) -> List[IPNet]:
    """
    Собирает список всех сетей, участвующих в пересечениях.

    Включает точные совпадения (exact_matches) и подсети из частичных
    перекрытий. Используется для расчёта объёма пересечения.

    Args:
        exact_matches: Множество точных совпадений.
        raw_overlaps: Сырые перекрытия из find_two_list_overlaps/self.

    Returns:
        Список сетей, входящих в пересечение.
    """
    fragments: List[IPNet] = list(exact_matches)
    for net1, net2 in raw_overlaps:
        if net1 == net2:
            continue
        if net1.subnet_of(net2):
            fragments.append(net1)
        elif net2.subnet_of(net1):
            fragments.append(net2)
    return fragments
