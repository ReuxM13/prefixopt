"""
Модуль утилит для работы с IP-адресами и сетями.

Содержит вспомогательные функции для конвертации, нормализации
и сравнения объектов ipaddress. Служит базовым слоем для операций ядра.
"""
import ipaddress
from typing import Union, Literal

from ipaddress import IPv4Network, IPv6Network

# Alias для упрощения аннотаций типов
IPNet = Union[IPv4Network, IPv6Network]


def normalize_prefix(s: str, strict: bool = False) -> IPNet:
    s = s.strip()

    if strict:
        if "/" in s:
            try:
                return ipaddress.ip_network(s, strict=True)
            except ValueError as exc:
                try:
                    corrected = ipaddress.ip_network(s, strict=False)
                except ValueError:
                    raise ValueError(f"Cannot normalize '{s}' to an IP network") from exc

                raise ValueError(
                    f"Invalid network '{s}': host bits are set. Did you mean '{corrected}'?"
                ) from exc

        try:
            ip = ipaddress.ip_address(s)
        except ValueError as exc:
            raise ValueError(f"Cannot normalize '{s}' to an IP network") from exc

        if ip.version == 4:
            return ipaddress.IPv4Network(f"{ip}/32", strict=False)
        return ipaddress.IPv6Network(f"{ip}/128", strict=False)

    try:
        return ipaddress.ip_network(s, strict=False)
    except ValueError:
        try:
            ip = ipaddress.ip_address(s)
        except ValueError as exc:
            raise ValueError(f"Cannot normalize '{s}' to an IP network") from exc

        if ip.version == 4:
            return ipaddress.IPv4Network(f"{ip}/32", strict=False)
        return ipaddress.IPv6Network(f"{ip}/128", strict=False)


def get_version(net: IPNet) -> Literal[4, 6]:
    """
    Возвращает версию IP-протокола для сети (4 или 6).

    Args:
        net: Объект IP сети.

    Returns:
        4 или 6.
    """
    # type: ignore - Pylance иногда теряет атрибут version в Union, но он гарантированно есть
    return net.version  


def is_subnet_of(a: IPNet, b: IPNet) -> bool:
    """
    Безопасная проверка: является ли 'a' подсетью 'b'.

    Обертка над стандартным subnet_of, которая корректно обрабатывает
    сравнение разных версий протоколов (IPv4 vs IPv6), возвращая False
    вместо ошибки TypeError.

    Args:
        a: Потенциальная подсеть.
        b: Потенциальная суперсеть.

    Returns:
        True, если 'a' входит в 'b', иначе False.
    """
    if a.version != b.version:
        return False
    
    # Явная проверка типов для удовлетворения статического анализатора (Pylance/Mypy)
    if isinstance(a, IPv4Network) and isinstance(b, IPv4Network):
        return a.subnet_of(b)
    if isinstance(a, IPv6Network) and isinstance(b, IPv6Network):
        return a.subnet_of(b)
    
    return False