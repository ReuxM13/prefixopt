"""
Набор тестов для проекта prefixopt.

Покрывает модульные тесты для алгоритмов ядра (core), интеграционные тесты
для CLI команд, проверки парсинга (data), а также тесты безопасности и
граничных случаев.
"""
import ipaddress
from pathlib import Path

import pytest
from typer.testing import CliRunner

from prefixopt.main import app
from prefixopt.core.operations.sorter import sort_networks
from prefixopt.core.operations.nested import remove_nested
from prefixopt.core.operations.aggregator import aggregate
from prefixopt.core.operations.subnetter import split_network
from prefixopt.data.file_reader import read_networks, normalize_single_ip

# Глобальный раннер для CLI-тестов
runner = CliRunner()


# ==============================================================================
# 1. Логика ядра и алгоритмов
# ==============================================================================

def test_core_sorting_broadest_first() -> None:
    """
    Проверяет корректность сортировки (Broadest First).
    
    Ожидаемый порядок:
    1. Версия IP (v4 -> v6).
    2. Сетевой адрес (asc).
    3. Длина префикса (asc, т.е. от широких /8 к узким /24).
    """
    input_strs = ["10.0.0.0/24", "10.0.0.0/8", "2001:db8::/32", "192.168.1.1/32"]
    nets = [ipaddress.ip_network(p, strict=False) for p in input_strs]
    
    sorted_nets = sort_networks(nets)
    result = [str(n) for n in sorted_nets]
    
    expected = [
        "10.0.0.0/8",       # Широкая v4
        "10.0.0.0/24",      # Узкая v4 (тот же адрес)
        "192.168.1.1/32",   # Другой адрес v4
        "2001:db8::/32"     # v6
    ]
    assert result == expected


def test_core_remove_nested() -> None:
    """
    Проверяет удаление вложенных сетей.
    
    Тест проверяет, что функция корректно обрабатывает несортированный ввод
    (так как внутри remove_nested есть своя сортировка по умолчанию).
    10.0.0.0/8 должна поглотить все подсети внутри.
    """
    input_strs = ["10.1.1.1/32", "10.0.0.0/8", "10.50.0.0/16"]
    nets = [ipaddress.ip_network(p, strict=False) for p in input_strs]
    
    optimized = remove_nested(nets)
    result = [str(n) for n in optimized]
    
    assert len(result) == 1
    assert result[0] == "10.0.0.0/8"


def test_core_aggregation() -> None:
    """
    Проверяет агрегацию смежных сетей.
    
    Четыре последовательных /24 должны объединиться в одну /22.
    192.168.0.0/24 ... 192.168.3.0/24 -> 192.168.0.0/22.
    """
    input_strs = [
        "192.168.0.0/24",
        "192.168.1.0/24", 
        "192.168.2.0/24",
        "192.168.3.0/24"
    ]
    nets = [ipaddress.ip_network(p, strict=False) for p in input_strs]
    
    aggregated = aggregate(nets)
    assert len(aggregated) == 1
    assert str(aggregated[0]) == "192.168.0.0/22"


def test_core_aggregation_gaps() -> None:
    """
    Проверяет, что агрегация не склеивает сети, если между ними есть разрыв.
    """
    # Пропущена сеть 192.168.1.0/24
    input_strs = ["192.168.0.0/24", "192.168.2.0/24"]
    nets = [ipaddress.ip_network(p, strict=False) for p in input_strs]
    
    aggregated = aggregate(nets)
    assert len(aggregated) == 2


def test_subnetter_split() -> None:
    """Проверяет разбиение сети на более мелкие подсети."""
    network = ipaddress.ip_network("192.168.1.0/24", strict=False)
    # Разбиваем /24 на /25
    subnets = split_network(network, 25)
    
    subnets_str = [str(n) for n in subnets]
    assert len(subnets_str) == 2
    assert "192.168.1.0/25" in subnets_str
    assert "192.168.1.128/25" in subnets_str


def test_subnetter_protection() -> None:
    """Проверяет защиту от создания слишком большого количества подсетей (OOM protection)."""
    network = ipaddress.ip_network("10.0.0.0/8", strict=False)
    # Попытка разбить /8 на /32 создаст 16 млн подсетей, что должно вызвать ошибку
    with pytest.raises(ValueError, match="exceeds the maximum"):
        split_network(network, 32, max_subnets=100)


def test_ipv6_handling(tmp_path: Path) -> None:
    """Проверяет корректность обработки и вывода IPv6."""
    f = tmp_path / "v6.txt"
    f.write_text("2001:db8::1\nfe80::1")
    
    result = runner.invoke(app, ["optimize", str(f), "--ipv6-only"])
    assert result.exit_code == 0
    assert "2001:db8::1/128" in result.stdout


# ==============================================================================
# 2. Парсинг и проверка ввода данных
# ==============================================================================

def test_parsing_dirty_data(tmp_path: Path) -> None:
    """
    Проверяет парсинг (Regex).
    Парсер должен извлекать IP-адреса из произвольного текста (логи, конфиги).
    Строки-комментарии, ничинающиеся с #, не обрабатываются.
    """
    f = tmp_path / "dirty.log"
    f.write_text("""
    [INFO] Connection from 1.1.1.1 port 80
    junk data 999.999.999.999 invalid ip
    Valid IPv6: 2001:db8::1/64 detected
    # Commented line 8.8.8.8
    Config: ip address 192.168.1.1 255.255.255.0
    """, encoding="utf-8")
    
    # read_networks возвращает генератор, поэтому оборачиваем в list()
    results = list(read_networks(f))
    str_results = {str(r) for r in results}
    
    assert "1.1.1.1/32" in str_results
    assert "2001:db8::/64" in str_results
    assert "192.168.1.1/32" in str_results 


def test_parsing_leading_zeros() -> None:
    """
    Проверяет защиту от CVE-2021-29921.
    Адреса с ведущими нулями (010.x.x.x) должны интерпретироваться как decimal.
    """
    bad_ip = "010.0.0.1"
    net = normalize_single_ip(bad_ip)
    assert str(net) == "10.0.0.1/32"
    
    bad_net = "192.168.001.001/24"
    net2 = normalize_single_ip(bad_net)
    assert str(net2) == "192.168.1.0/24"


# ==============================================================================
# 3. CLI
# ==============================================================================

def test_cli_optimize_full_cycle(tmp_path: Path) -> None:
    """
    Интеграционный тест команды optimize.
    Проверяет полный цикл: Чтение -> Сортировка -> Nested -> Aggregate -> Вывод.
    """
    f = tmp_path / "in.txt"
    f.write_text("192.168.0.0/24\n192.168.1.0/24\n10.0.0.0/24\n10.0.0.0/8\n", encoding="utf-8")
    
    result = runner.invoke(app, ["optimize", str(f)])
    assert result.exit_code == 0
    
    out = result.stdout
    # Проверка агрегации (две /24 стали /23)
    assert "192.168.0.0/23" in out
    # Проверка вложенности (/8 поглотила /24)
    assert "10.0.0.0/8" in out
    assert "10.0.0.0/24" not in out


def test_cli_csv_format(tmp_path: Path) -> None:
    """Проверяет корректность вывода в формате CSV."""
    f = tmp_path / "in.txt"
    f.write_text("1.1.1.1\n2.2.2.2", encoding="utf-8")
    
    result = runner.invoke(app, ["optimize", str(f), "--format", "csv"])
    assert result.exit_code == 0
    # Проверяем наличие запятой и отсутствие лишних переносов строк
    assert "1.1.1.1/32,2.2.2.2/32" in result.stdout
    assert "\n" not in result.stdout.strip()


def test_cli_merge_comments(tmp_path: Path) -> None:
    """
    Тест режима merge --keep-comments.
    Проверяет, что комментарии сохраняются, дубликаты удаляются, но агрегация НЕ происходит.
    """
    f1 = tmp_path / "list1.txt"
    f1.write_text("10.0.0.1 # Server A\n10.0.0.2 # Server B\n")
    f2 = tmp_path / "list2.txt"
    f2.write_text("10.0.0.3 # Server C\n10.0.0.1 # Duplicate\n") 
    
    result = runner.invoke(app, ["merge", str(f1), str(f2), "--keep-comments"])
    assert result.exit_code == 0
    out = result.stdout
    
    # Проверка сохранения комментариев
    assert "10.0.0.1/32 # Server A" in out
    assert "10.0.0.2/32 # Server B" in out
    assert "10.0.0.3/32 # Server C" in out
    
    # Проверка дедупликации
    assert out.count("10.0.0.1/32") == 1
    
    # Проверка отсутствия агрегации (они смежные, но должны остаться /32)
    assert "10.0.0.0/" not in out


def test_cli_filter_bogons(tmp_path: Path) -> None:
    """
    Тест фильтрации (filter --bogons).
    Проверяет удаление частных, link-local и других специальных сетей.
    """
    f = tmp_path / "mixed.txt"
    f.write_text("8.8.8.8\n127.0.0.1\n169.254.1.1\n224.0.0.1\n0.0.0.0/0\n")
    
    result = runner.invoke(app, ["filter", str(f), "--bogons"])
    assert result.exit_code == 0
    
    # Публичный IP должен остаться
    assert "8.8.8.8/32" in result.stdout
    
    # Мусор должен быть удален
    assert "127.0.0.1" not in result.stdout
    assert "169.254.1.1" not in result.stdout
    
    assert "0.0.0.0/0" not in result.stdout


def test_cli_diff_basic(tmp_path: Path) -> None:
    """
    Проверка базовой логики команды diff: Added, Removed.
    """
    f_old = tmp_path / "old.txt"
    f_new = tmp_path / "new.txt"
    
    # Old: 10.0.0.0/8 (останется), 1.1.1.1/32 (удалится)
    f_old.write_text("10.0.0.0/8\n1.1.1.1/32", encoding="utf-8")
    
    # New: 10.0.0.0/8 (остался), 2.2.2.2/32 (добавился)
    f_new.write_text("10.0.0.0/8\n2.2.2.2/32", encoding="utf-8")
    
    result = runner.invoke(app, ["diff", str(f_new), str(f_old)])
    
    assert result.exit_code == 0
    # Проверка вывода
    assert "+ 2.2.2.2/32" in result.stdout
    assert "- 1.1.1.1/32" in result.stdout
    # Unchanged по умолчанию скрыты
    assert "10.0.0.0/8" not in result.stdout


def test_cli_diff_semantic(tmp_path: Path) -> None:
    """
    Проверка семантического сравнения в diff.
    Утилита должна понимать, что две /24 равны одной /23 перед сравнением.
    """
    f_old = tmp_path / "old.txt"
    f_new = tmp_path / "new.txt"
    
    # Old: Агрегированная сеть
    f_old.write_text("192.168.0.0/23", encoding="utf-8")
    
    # New: Две подсети, составляющие ту же /23
    f_new.write_text("192.168.0.0/24\n192.168.1.0/24", encoding="utf-8")
    
    result = runner.invoke(app, ["diff", str(f_new), str(f_old)])
    
    assert result.exit_code == 0
    assert "Files are identical" in result.stdout


def test_cli_diff_show_unchanged(tmp_path: Path) -> None:
    """
    Проверка режима отображения unchanged через --mode.
    """
    f_old = tmp_path / "old.txt"
    f_new = tmp_path / "new.txt"
    
    # Общая сеть
    f_old.write_text("10.0.0.0/8", encoding="utf-8")
    f_new.write_text("10.0.0.0/8", encoding="utf-8")
    
    # 1. По умолчанию (mode=changes)
    result = runner.invoke(app, ["diff", str(f_new), str(f_old)])
    assert result.exit_code == 0
    # Неизмененное скрыто
    assert "= 10.0.0.0/8" not in result.stdout
    
    # 2. Режим --mode unchanged
    # Должен показать только неизмененные
    result_unchanged = runner.invoke(app, ["diff", str(f_new), str(f_old), "--mode", "unchanged"])
    assert result_unchanged.exit_code == 0
    assert "= 10.0.0.0/8" in result_unchanged.stdout
    
    # 3. Режим --mode all
    # Должен показать всё (включая неизмененные)
    result_all = runner.invoke(app, ["diff", str(f_new), str(f_old), "--mode", "all"])
    assert result_all.exit_code == 0
    assert "= 10.0.0.0/8" in result_all.stdout


def test_cli_diff_summary(tmp_path: Path) -> None:
    """Проверка флага --summary в diff (только цифры)."""
    f_old = tmp_path / "old.txt"
    f_new = tmp_path / "new.txt"
    
    f_old.write_text("1.1.1.1", encoding="utf-8")
    f_new.write_text("2.2.2.2", encoding="utf-8")
    
    result = runner.invoke(app, ["diff", str(f_new), str(f_old), "--summary"])
    
    assert result.exit_code == 0
    assert "Added: 1" in result.stdout
    assert "Removed: 1" in result.stdout
    assert "1.1.1.1" not in result.stdout


# ==============================================================================
# 4. Безопасность
# ==============================================================================

def test_security_max_line_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Проверка Hard Limit на количество строк.
    """
    monkeypatch.setattr("prefixopt.data.file_reader.MAX_LINE_COUNT", 2)
    
    f = tmp_path / "huge.txt"
    f.write_text("1.1.1.1\n2.2.2.2\n3.3.3.3\n4.4.4.4", encoding="utf-8")
    
    result = runner.invoke(app, ["optimize", str(f)])
    assert result.exit_code == 1
    # Проверяем наличие ключевых слов, не привязываясь к точному артикли
    assert "exceeds" in result.stdout
    assert "limit" in result.stdout
    assert "lines" in result.stdout

def test_security_max_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Проверка Hard Limit на размер файла.
    """
    monkeypatch.setattr("prefixopt.data.file_reader.MAX_FILE_SIZE_BYTES", 10)
    
    f = tmp_path / "fat.txt"
    f.write_text("1.1.1.1\n2.2.2.2\n3.3.3.3", encoding="utf-8") # > 10 байт
    
    result = runner.invoke(app, ["optimize", str(f)])
    assert result.exit_code == 1
    # Проверяем ключевые слова
    assert "exceeds" in result.stdout
    assert "safety limit" in result.stdout

# ==============================================================================
# 5. Исключения
# ==============================================================================

def test_exclude_hole_punching():
    """
    Тест Дырка от бублика.
    Проверка сложной математики: вычитание маленькой сети из большой.
    """
    from prefixopt.core.operations.subtractor import subtract_networks
    
    # Исходная: 10.0.0.0/30 (IPs: .0, .1, .2, .3)
    source = [ipaddress.ip_network("10.0.0.0/30")]
    # Исключаем: 10.0.0.1/32
    exclude = [ipaddress.ip_network("10.0.0.1/32")]
    
    # Ожидаемый результат:
    # 10.0.0.0/32 (остался)
    # 10.0.0.1/32 (вырезан)
    # 10.0.0.2/31 (остаток .2 и .3 объединился)
    
    result = subtract_networks(source, exclude)
    # Прогоняем через агрегатор для чистоты эксперимента (хотя subtractor не агрегирует результат сам, но CLI агрегирует)
    # Но subtractor возвращает фрагменты.
    
    res_str = {str(n) for n in result}
    assert "10.0.0.0/32" in res_str
    assert "10.0.0.2/31" in res_str
    assert "10.0.0.1/32" not in res_str
    assert len(res_str) == 2

def test_exclude_full_removal():
    """Если исключение больше или равно сети - сеть должна исчезнуть."""
    from prefixopt.core.operations.subtractor import subtract_networks
    
    source = [ipaddress.ip_network("192.168.1.1/32")]
    exclude = [ipaddress.ip_network("192.168.0.0/16")] # Широкое исключение
    
    result = subtract_networks(source, exclude)
    assert len(result) == 0

def test_exclude_no_overlap():
    """Если пересечения нет - сеть должна остаться нетронутой."""
    from prefixopt.core.operations.subtractor import subtract_networks
    
    source = [ipaddress.ip_network("10.0.0.0/8")]
    exclude = [ipaddress.ip_network("192.168.0.0/16")]
    
    result = subtract_networks(source, exclude)
    assert len(result) == 1
    assert str(result[0]) == "10.0.0.0/8"

def test_exclude_mixed_versions_safety():
    """
    Проверка безопасности типов.
    Попытка исключить IPv6 из списка IPv4 не должна ломать программу.
    """
    from prefixopt.core.operations.subtractor import subtract_networks
    
    source = [ipaddress.ip_network("10.0.0.0/24")]
    exclude = [ipaddress.ip_network("2001:db8::/32")]
    
    # IPv6 должно быть проигнорировано при проверке против IPv4
    result = subtract_networks(source, exclude)
    assert len(result) == 1
    assert str(result[0]) == "10.0.0.0/24"

def test_cli_exclude_single_target(tmp_path):
    """CLI: Исключение одиночного префикса"""
    f = tmp_path / "list.txt"
    f.write_text("10.0.0.0/29", encoding="utf-8") # .0 - .7
    
    # Исключаем .3
    result = runner.invoke(app, ["exclude", "10.0.0.3/32", str(f)])
    
    assert result.exit_code == 0
    assert "10.0.0.3/32" not in result.stdout
    
    # 10.0.0.0/29 минус .3 -> 
    # .0/32 + .1/32 -> .0/31 (Агрегатор склеил)
    # .2/32 (остался один)
    # .4/30 (остался кусок)
    assert "10.0.0.0/31" in result.stdout
    assert "10.0.0.2/32" in result.stdout
    assert "10.0.0.4/30" in result.stdout

def test_cli_exclude_from_file(tmp_path):
    """CLI: Исключение списка сетей из файла (Blacklist)"""
    input_file = tmp_path / "allow.txt"
    input_file.write_text("10.0.0.0/24", encoding="utf-8")
    
    blacklist_file = tmp_path / "deny.txt"
    # Исключаем половину сети
    blacklist_file.write_text("10.0.0.0/25", encoding="utf-8")
    
    # Передаем файл как аргумент target
    result = runner.invoke(app, ["exclude", str(blacklist_file), str(input_file)])
    
    assert result.exit_code == 0
    # Осталась вторая половина
    assert "10.0.0.128/25" in result.stdout
    assert "10.0.0.0/25" not in result.stdout

def test_cli_exclude_invalid_target(tmp_path):
    """CLI: Проверка ошибки на некорректный таргет"""
    f = tmp_path / "list.txt"
    f.write_text("1.1.1.1")
    
    result = runner.invoke(app, ["exclude", "NotAnIP", str(f)])
    
    assert result.exit_code == 1
    assert "Error" in result.stdout


# ==============================================================================
# 6. STDIN (PIPE) TESTS
# ==============================================================================

def test_stdin_optimize():
    """Проверка работы optimize через pipe (без input_file)"""
    input_data = "10.0.0.0/24\n10.0.0.0/8\n"
    # runner.invoke(app, args, input=...) эмулирует stdin
    result = runner.invoke(app, ["optimize"], input=input_data)
    
    assert result.exit_code == 0
    # Должен остаться только /8 (оптимизация сработала)
    assert "10.0.0.0/8" in result.stdout
    assert "10.0.0.0/24" not in result.stdout

def test_stdin_filter():
    """Проверка работы filter через pipe"""
    input_data = "8.8.8.8\n10.0.0.1\n"
    # Фильтруем приватные сети
    result = runner.invoke(app, ["filter", "--no-private"], input=input_data)
    
    assert result.exit_code == 0
    assert "8.8.8.8/32" in result.stdout
    assert "10.0.0.1" not in result.stdout

def test_stdin_stats():
    """Проверка stats через pipe"""
    input_data = "1.1.1.1\n2.2.2.2\n"
    result = runner.invoke(app, ["stats"], input=input_data)
    
    assert result.exit_code == 0
    # Проверяем, что статистика посчиталась
    assert "Original prefix count" in result.stdout
    assert "2" in result.stdout # Count

def test_stdin_check():
    """Проверка check через pipe"""
    input_data = "10.0.0.0/8\n"
    # Проверяем, входит ли 10.1.1.1 в поток, поданный на вход
    result = runner.invoke(app, ["check", "10.1.1.1"], input=input_data)
    
    assert result.exit_code == 0
    assert "is contained in" in result.stdout


# ==============================================================================
# 5. JSON STREAMING TESTS (ijson)
# ==============================================================================

def test_json_streaming_basic(tmp_path):
    """
    Проверка потокового чтения корректного JSON.
    """
    f = tmp_path / "test.json"
    # Стандартная структура { "prefixes": [...] }
    json_content = """
    {
        "meta": "some info",
        "prefixes": [
            "10.0.0.1",
            "192.168.1.0/24"
        ]
    }
    """
    f.write_text(json_content, encoding="utf-8")
    
    # Читаем
    results = list(read_networks(f))
    
    assert len(results) == 2
    # Проверка, что объекты создались
    assert ipaddress.ip_network("10.0.0.1/32") in results
    assert ipaddress.ip_network("192.168.1.0/24") in results

def test_json_streaming_limit(tmp_path, monkeypatch):
    """
    Проверка Hard Limit внутри JSON массива.
    Даже если файл маленький (байты), но в массиве миллиард элементов - мы должны остановиться.
    """
    # Ставим лимит в 2 элемента
    monkeypatch.setattr("prefixopt.data.file_reader.MAX_LINE_COUNT", 2)
    
    f = tmp_path / "huge_array.json"
    f.write_text('{"prefixes": ["1.1.1.1", "2.2.2.2", "3.3.3.3"]}', encoding="utf-8")
    
    # Должен упасть, так как элементов 3, а лимит 2
    with pytest.raises(ValueError, match="JSON array exceeds"):
        list(read_networks(f))

def test_json_malformed(tmp_path):
    """
    Проверка устойчивости к битому JSON.
    ijson может выбросить ошибку в середине потока. Мы должны её погасить или обработать.
    В текущей реализации мы ловим ijson.JSONError и выходим.
    """
    f = tmp_path / "broken.json"
    # Обрывается посередине
    f.write_text('{"prefixes": ["1.1.1.1", "2.2.2', encoding="utf-8")
    
    # Не должно быть крэша (Exception)
    results = list(read_networks(f))
    
    # Он успел прочитать первый элемент
    assert len(results) == 1
    assert str(results[0]) == "1.1.1.1/32"

def test_json_garbage_values(tmp_path):
    """
    JSON валидный, но внутри массива мусор вместо IP.
    """
    f = tmp_path / "garbage.json"
    f.write_text('{"prefixes": ["1.1.1.1", "NotAnIP", "10.0.0.1"]}', encoding="utf-8")
    
    results = list(read_networks(f))
    
    # Должен пропустить мусор и вернуть только валидные
    assert len(results) == 2
    assert ipaddress.ip_network("1.1.1.1/32") in results
    assert ipaddress.ip_network("10.0.0.1/32") in results