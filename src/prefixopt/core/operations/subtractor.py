"""
Модуль вычитания сетей (Subnet Subtraction).

Реализует высокопроизводительный алгоритм исключения.
Использует предварительную сортировку и технику скользящего окна для
достижения линейной сложности O(N+M) вместо квадратичной.
"""
from typing import List, Iterable

from ..ip_utils import IPNet, is_subnet_of

# Операции для подготовки списков
from .sorter import sort_networks
from .nested import remove_nested
from .aggregator import aggregate

# Лимит на количество фрагментов (защита от OOM)
MAX_OUTPUT_FRAGMENTS = 2_000_000


def subtract_networks(
    sources: Iterable[IPNet],
    excludes: Iterable[IPNet]
) -> List[IPNet]:
    """
    Subtracts the list of excludes from the list of sources.

    Алгоритм:
    1. Excludes: Сортируются, очищаются от вложенности и агрегируются.
       Это создает упорядоченный список непересекающихся интервалов.
    2. Sources: Сортируются.
    3. Используется указатель (exclude_idx), который движется только вперед.
       Мы пропускаем исключения, которые находятся слева от текущей сети.

    Args:
        sources: Исходные сети.
        excludes: Сети, которые нужно удалить/вырезать.

    Returns:
        Список сетей, оставшихся после вычитания.
    """
    # 1. Подготовка списка исключений
    # Превращаем его в плоский список отсортированных, непересекающихся блоков.
    # Это критически важно для работы алгоритма скользящего окна.
    excludes_list = list(excludes)
    if not excludes_list:
        return list(sources)

    excludes_list = sort_networks(excludes_list)
    # assume_sorted=True, т.к. только что отсортировали
    excludes_list = remove_nested(excludes_list, assume_sorted=True)
    excludes_list = aggregate(excludes_list)

    # 2. Подготовка исходного списка
    # Сортировка sources позволяет нам двигать указатель excludes только вперед
    sources_list = sort_networks(sources)

    final_results: List[IPNet] = []
    
    # Указатель на текущее положение в списке исключений
    exclude_idx = 0
    num_excludes = len(excludes_list)

    for source in sources_list:
        # Получаем числовые границы текущей сети для быстрых проверок
        src_start = int(source.network_address)
        src_end = int(source.broadcast_address)
        src_ver = source.version

        # ШАГ A: Прокручиваем исключения, которые закончились ДО начала этой сети
        # (Они слева, они нам больше никогда не понадобятся, т.к. sources отсортированы)
        while exclude_idx < num_excludes:
            curr_exc = excludes_list[exclude_idx]
            
            # Если версии разные, и v4 < v6 (стандартная сортировка), то v4 исключения
            # нужно пропустить, если мы уже на v6 источниках.
            if curr_exc.version < src_ver:
                exclude_idx += 1
                continue
            
            if curr_exc.version > src_ver:
                # Исключения ушли вперед (v6), а мы еще на v4. Не трогаем индекс.
                break

            # Версии совпадают. Проверяем границы.
            exc_end = int(curr_exc.broadcast_address)
            
            # Если конец исключения меньше начала источника, то исключение полностью слева
            if exc_end < src_start:
                exclude_idx += 1
            else:
                # Исключение пересекается или находится справа. Останавливаемся.
                break

        # ШАГ B: Проходим по актуальным исключениям
        # Копируем текущую сеть в список фрагментов для обработки
        current_fragments = [source]
        
        # Запускаем временный итератор от текущего exclude_idx
        local_idx = exclude_idx
        
        while local_idx < num_excludes:
            exc = excludes_list[local_idx]
            
            # Оптимизация выхода:
            # Если начало исключения больше конца источника, то исключение полностью справа.
            # Так как оба списка отсортированы, все следующие исключения тоже будут справа.
            # Можно переходить к следующему источнику.
            if exc.version > src_ver:
                break
            if exc.version == src_ver and int(exc.network_address) > src_end:
                break

            # Если здесь, значит есть потенциальное пересечение
            next_pass_fragments = []
            for frag in current_fragments:
                # Быстрая проверка на пересечение
                # Pylance ignore: версии гарантированно совпадают благодаря логике выше
                if not frag.overlaps(exc): # type: ignore
                    next_pass_fragments.append(frag)
                    continue

                # Сценарий 1: Фрагмент внутри исключения - Удаляем
                if is_subnet_of(frag, exc):
                    continue 

                # Сценарий 2: Исключение внутри фрагмента - Режем
                if is_subnet_of(exc, frag):
                    try:
                        # address_exclude возвращает генератор
                        remaining = list(frag.address_exclude(exc)) # type: ignore
                        next_pass_fragments.extend(remaining)
                    except ValueError:
                        next_pass_fragments.append(frag)
                
                # Сценарий 3: Частичное перекрытие без вложенности
                # В нашей модели, где excludes агрегированы и очищены, а sources сортированы,
                # и мы используем CIDR, сложные частичные перекрытия обычно сводятся
                # к одному из вариантов выше или последовательной обработке.

            current_fragments = next_pass_fragments
            if not current_fragments:
                break # Источник полностью уничтожен
            
            local_idx += 1

        final_results.extend(current_fragments)

        # Safety Fuse
        if len(final_results) > MAX_OUTPUT_FRAGMENTS:
            raise ValueError(
                f"Subtraction resulted in too many fragments (> {MAX_OUTPUT_FRAGMENTS}). "
                "Operation stopped."
            )

    return final_results