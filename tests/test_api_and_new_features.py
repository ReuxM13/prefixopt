"""
Тесты для нового API-фасада и функционала keep-comments.
Включает сценарии интеграции с внешними данными (JSON API).
"""
import ipaddress
import json
from pathlib import Path
from typing import List, Tuple, Union, Any

import pytest
from typer.testing import CliRunner

# Импортируем пакет
import prefixopt
from prefixopt import api
from prefixopt.main import app
from prefixopt.core.ip_utils import IPNet

runner = CliRunner()


def test_package_exposure():
    """Проверка доступности функций из корня пакета."""
    assert hasattr(prefixopt, "optimize")
    assert hasattr(prefixopt, "load")
    assert hasattr(prefixopt, "merge")

def test_api_load_flexible_input(tmp_path: Path):
    """Проверка api.load на разных типах данных."""
    # 1. Список
    data_list = ["1.1.1.1", "2.2.2.2"]
    res1 = list(api.load(data_list))
    assert len(res1) == 2

    # 2. Строка
    res2 = list(api.load("10.0.0.1 10.0.0.2"))
    assert len(res2) == 2

    # 3. Файл
    f = tmp_path / "test.txt"
    f.write_text("192.168.1.1", encoding="utf-8")
    res3 = list(api.load(f))
    assert len(res3) == 1

def test_api_optimize_keep_comments(tmp_path: Path):
    """Тест api.optimize(keep_comments=True)."""
    f = tmp_path / "comments.txt"
    f.write_text("10.0.0.1 # A\n10.0.0.2 # B", encoding="utf-8")

    result = api.optimize(f, keep_comments=True)

    # Type Guard для Pylance и проверки логики
    assert isinstance(result, list)
    assert len(result) > 0
    # Проверяем, что первый элемент - это кортеж
    first_item = result[0]
    assert isinstance(first_item, tuple)
    
    ip, comment = first_item
    assert str(ip) == "10.0.0.1/32"
    assert comment == "# A"

def test_api_add_keep_comments(tmp_path: Path):
    """Тест api.add(keep_comments=True)."""
    f = tmp_path / "inventory.txt"
    f.write_text("192.168.1.10 # Printer", encoding="utf-8")

    result = api.add(f, "192.168.1.11", keep_comments=True)

    # Ищем добавленный элемент
    found_new = False
    found_old = False
    
    for item in result:
        if isinstance(item, tuple):
            ip, comment = item
            if str(ip) == "192.168.1.11/32":
                assert "# Added" in comment
                found_new = True
            if str(ip) == "192.168.1.10/32":
                assert "# Printer" in comment
                found_old = True
    
    assert found_new, "New IP not found or missing comment"
    assert found_old, "Old IP lost comment"

def test_api_merge_keep_comments(tmp_path: Path):
    """Тест api.merge(keep_comments=True)."""
    f1 = tmp_path / "f1.txt"
    f1.write_text("1.1.1.1 # Src1")
    f2 = tmp_path / "f2.txt"
    f2.write_text("2.2.2.2 # Src2")

    result = api.merge(f1, f2, keep_comments=True)
    
    ips = []
    comments = []
    
    for item in result:
        if isinstance(item, tuple):
            ips.append(str(item[0]))
            comments.append(item[1])
            
    assert "1.1.1.1/32" in ips
    assert "2.2.2.2/32" in ips
    assert "# Src1" in comments
    assert "# Src2" in comments


def test_integration_simple_json_list():
    """
    Сценарий 1: Внешний API возвращает простой список IP-адресов.
    """
    # .10 и .12 не являются смежными, поэтому не агрегируются.
    # Это позволяет проверить количество элементов без поправки на склейку.
    api_response_data = ["192.168.1.10", "192.168.1.12", "10.0.0.1/24"]
    
    optimized = api.optimize(api_response_data)
    
    # Ожидаем 3 объекта: .10/32, .12/32, 10.0.0.0/24
    assert len(optimized) == 3
    assert isinstance(optimized[0], (ipaddress.IPv4Network, ipaddress.IPv6Network))
    
    str_results = [str(x) for x in optimized]
    assert "10.0.0.0/24" in str_results
    assert "192.168.1.10/32" in str_results

def test_integration_complex_json_structure():
    """
    Сценарий 2: Внешний API возвращает список словарей.
    """
    api_response = [
        {"host": "10.0.0.1", "region": "us-east"},
        {"host": "10.0.0.2", "region": "us-west"},
        {"host": "invalid-ip", "region": "null"}
    ]
    
    ip_list = [item["host"] for item in api_response]
    result = api.optimize(ip_list)
    
    # 10.0.0.1 и .2 склеятся в 10.0.0.0/30 (или /31, зависит от выравнивания, но здесь /30 блок начинается с .0)
    # .1 и .2 -> это 01 и 10. Они НЕ склеятся в /31 (так как /31 это .0+.1 или .2+.3).
    # Они склеятся только если были бы .0 и .1, или .2 и .3.
    # Проверим просто количество валидных IP.
    
    assert len(result) == 2
    assert str(result[0]) == "10.0.0.1/32"

def test_integration_dirty_security_feed():
    """
    Сценарий 3: Feed с IP-адресами.
    """
    # Исправлено: Используем реальные публичные IP, которые НЕ являются Reserved.
    threat_feed = [
        "200.1.1.1",     # Random Public
        "150.2.2.2",     # Random Public
        "127.0.0.1",     # Bogon (Loopback)
        "192.168.1.1",   # Bogon (Private)
        "   8.8.8.8   "  # Плохое форматирование
    ]
    
    clean_feed = api.filter(
        threat_feed,
        bogons=True, 
        exclude_private=True
    )
    
    clean_strs = [str(ip) for ip in clean_feed]
    
    assert "200.1.1.1/32" in clean_strs
    assert "150.2.2.2/32" in clean_strs
    assert "8.8.8.8/32" in clean_strs
    
    assert "127.0.0.1/32" not in clean_strs
    assert "192.168.1.1/32" not in clean_strs

def test_integration_pipeline_merge_diff():
    """
    Сценарий 4: Сложный пайплайн.
    """
    api_a = ["10.0.0.1", "10.0.0.2"]
    # Исправлено: .4 вместо .3, чтобы избежать агрегации (.2 + .3 = /31)
    api_b = ["10.0.0.4", "10.0.0.1"] 
    local_whitelist = ["10.0.0.1", "10.0.0.5"]
    
    # 1. Merge
    merged_remote = api.merge(api_a, api_b)
    
    # 2. Diff
    added, removed, unchanged = api.diff(merged_remote, local_whitelist)
    
    added_str = {str(i) for i in added}
    removed_str = {str(i) for i in removed}
    unchanged_str = {str(i) for i in unchanged}
    
    # Added: .2 и .4
    assert "10.0.0.2/32" in added_str
    assert "10.0.0.4/32" in added_str
    
    # Removed: .5 (был локально, нет удаленно)
    assert "10.0.0.5/32" in removed_str
    
    # Unchanged: .1
    assert "10.0.0.1/32" in unchanged_str