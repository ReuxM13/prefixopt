"""
Модуль вычитания сетей (Subnet Subtraction).

Реализует логику исключения одного списка сетей (excludes) из другого (sources).
Если исключаемая сеть находится внутри исходной, исходная сеть разбивается
на более мелкие подсети (дефрагментация), чтобы исключить указанный диапазон.
"""
from typing import List, Iterable
from ..ip_utils import IPNet, is_subnet_of

from .sorter import sort_networks
from .nested import remove_nested
from .aggregator import aggregate

# Лимит на количество фрагментов. 
# Если в результате вычитания получается больше 2 млн сетей - останавливаемся.
MAX_OUTPUT_FRAGMENTS = 2_000_000

def subtract_networks(
    sources: Iterable[IPNet],
    excludes: Iterable[IPNet]
) -> List[IPNet]:
    """
    Subtracts the list of excludes from the list of sources.

    Алгоритм:
    1. Список excludes оптимизируется (сортируется, склеивается), чтобы минимизировать
       количество операций разрезания.
    2. Каждая сеть из sources проверяется на пересечение с каждым исключением.
    3. Если есть пересечение:
       - Если source внутри exclude -> source удаляется.
       - Если exclude внутри source -> source разбивается на мелкие части.

    Args:
        sources: Исходные сети.
        excludes: Сети, которые нужно удалить/вырезать.

    Returns:
        Список сетей, оставшихся после вычитания.
    """
    # 1. Подготовка списка исключений
    excludes_list = list(excludes)
    if not excludes_list:
        return list(sources)

    excludes_list = sort_networks(excludes_list)
    excludes_list = remove_nested(excludes_list, assume_sorted=True)
    excludes_list = aggregate(excludes_list)

    final_results: List[IPNet] = []

    # 2. Проход по исходным сетям
    for source in sources:
        # Текущие фрагменты этой сети
        current_fragments = [source]

        for exclude in excludes_list:
            next_pass_fragments = []
            
            for frag in current_fragments:
                # Разные версии IP не пересекаются
                if frag.version != exclude.version:
                    next_pass_fragments.append(frag)
                    continue

                # Если не пересекаются вообще - оставляем как есть
                if not frag.overlaps(exclude): 
                    next_pass_fragments.append(frag)
                    continue

                # Сценарий A: Фрагмент полностью внутри исключения
                # Используем безопасную утилиту is_subnet_of
                if is_subnet_of(frag, exclude):
                    continue

                # Сценарий B: Исключение внутри фрагмента (Дырка в бублике)
                if is_subnet_of(exclude, frag):
                    try:
                        # address_exclude возвращает генератор подсетей
                        remaining = list(frag.address_exclude(exclude)) # type: ignore
                        next_pass_fragments.extend(remaining)
                    except ValueError:
                        # Защита от странных ошибок ipaddress
                        next_pass_fragments.append(frag)
                
                # Сценарий C: Частичное перекрытие (невозможно в строгом CIDR без вложенности)
                # Если overlaps=True и не A и не B, код просто не сработает, 
                # но для IPv4Network это математически невозможно.

            current_fragments = next_pass_fragments
            
            if not current_fragments:
                break

        final_results.extend(current_fragments)
        
        # Проверка размера результирующего списка
        if len(final_results) > MAX_OUTPUT_FRAGMENTS:
            raise ValueError(
                f"Subtraction resulted in too many fragments (> {MAX_OUTPUT_FRAGMENTS}). "
                "Operation stopped to prevent Memory Overflow. "
                "Try optimizing your input lists or excluding larger blocks."
            )

    return final_results