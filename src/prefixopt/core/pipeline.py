"""
Модуль центрального пайплайна обработки.

Этот модуль служит оркестратором для всех операций над IP-префиксами.
Он выстраивает процесс обработки в эффективную цепочку:
1. Фильтрация на лету (без загрузки в память).
2. Сортировка и тяжелые алгоритмы (с загрузкой в память по требованию).
"""
from typing import Iterable

from .ip_utils import IPNet
# Импортируем операции с алиасами, чтобы избежать конфликта имен
# между аргументами функции (флагами) и самими вызываемыми функциями.
from .operations import aggregate as aggregate_op
from .operations import remove_nested as remove_nested_op
from .operations import sort_networks as sort_networks_op
from .operations import filter_special as filter_special_op


def process_prefixes(
    networks: Iterable[IPNet],
    sort: bool = True,
    remove_nested: bool = True,
    aggregate: bool = True,
    ipv4_only: bool = False,
    ipv6_only: bool = False,
    exclude_private: bool = False,
    exclude_loopback: bool = False,
    exclude_link_local: bool = False,
    exclude_multicast: bool = False,
    exclude_reserved: bool = False,
    exclude_unspecified: bool = False,
    bogons: bool = False
) -> Iterable[IPNet]:
    """
    Главная функция обработки префиксов.

    Принимает на вход поток (итератор) сетей и пропускает его через серию
    преобразований. Логика построена так, чтобы максимально долго сохранять
    ленивость и не загружать данные в оперативную память без необходимости.

    Порядок выполнения:
    1. Дедупликация и фильтрация (версии, bogons). Работает потоково.
    2. Сортировка (Broadest First). Загружает данные в память.
    3. Удаление вложенных сетей. Требует сортировки.
    4. Агрегация смежных сетей. Требует сортировки.

    Args:
        networks: Входной итератор объектов IP сетей.
        sort: Включить сортировку (обязательно для оптимизации).
        remove_nested: Удалять подсети, входящие в более крупные (10.1.1.1 в 10.0.0.0/8).
        aggregate: Объединять соседние сети (10.0.0.0/24 + 10.0.1.0/24 -> /23).
        ipv4_only: Оставить только IPv4.
        ipv6_only: Оставить только IPv6.
        exclude_private: Исключить частные сети (RFC 1918).
        exclude_loopback: Исключить Loopback (127.0.0.0/8).
        exclude_link_local: Исключить Link-Local (169.254.0.0/16).
        exclude_multicast: Исключить Multicast.
        exclude_reserved: Исключить зарезервированные сети.
        exclude_unspecified: Исключить 0.0.0.0 и ::.
        bogons: Включить все фильтры исключения мусора сразу.

    Returns:
        Итератор (или список) обработанных IP сетей.
    """
    
    # --- ЭТАП 1: ЛЕНИВАЯ ФИЛЬТРАЦИЯ ---
    # На этом этапе работаем с генераторами. Данные читаются с диска по одной строке,
    # проверяются и передаются дальше. Память почти не расходуется.
    
    current_data = networks

    # Фильтры по версии протокола
    if ipv4_only:
        current_data = (n for n in current_data if n.version == 4)
    elif ipv6_only:
        current_data = (n for n in current_data if n.version == 6)

    # Активация группы фильтров, если передан флаг --bogons
    if bogons:
        exclude_private = exclude_loopback = exclude_link_local = \
            exclude_multicast = exclude_reserved = exclude_unspecified = True

    # Применение специальных фильтров
    if any([exclude_private, exclude_loopback, exclude_link_local,
            exclude_multicast, exclude_reserved, exclude_unspecified]):
        current_data = filter_special_op(
            current_data,
            exclude_private=exclude_private,
            exclude_loopback=exclude_loopback,
            exclude_link_local=exclude_link_local,
            exclude_multicast=exclude_multicast,
            exclude_reserved=exclude_reserved,
            exclude_unspecified=exclude_unspecified
        )

    # --- ЭТАП 2: ТЯЖЕЛЫЕ ОПЕРАЦИИ ---
    # Операции ниже требуют анализа всей совокупности данных (сравнение всех со всеми
    # или с соседями), поэтому поток будет загружен в память (List) при первом вызове.
    
    is_sorted_broadest = False

    if sort:
        # Функция сортировки внутри себя сделает list(current_data),
        # загрузив отфильтрованные данные в RAM.
        current_data = sort_networks_op(current_data)
        is_sorted_broadest = True
    
    if remove_nested:
        # Удаляем вложенные сети.
        # Если данные уже отсортированы (is_sorted_broadest=True), алгоритм работает за O(N).
        # Если нет — функция сама отсортирует их внутри.
        current_data = remove_nested_op(current_data, assume_sorted=is_sorted_broadest)
        # Результат этой операции гарантированно отсортирован
        is_sorted_broadest = True
        
    if aggregate:
        # Агрегация критически зависит от порядка следования.
        # Если мы пропустили шаги выше, нужно принудительно отсортировать данные сейчас.
        if not is_sorted_broadest:
            current_data = sort_networks_op(current_data)
            is_sorted_broadest = True
        
        current_data = aggregate_op(current_data)

    # Возвращаем результат. Это может быть генератор (если только фильтровали)
    # или список (если оптимизировали). Вызывающий код (CLI) обработает оба варианта.
    return current_data