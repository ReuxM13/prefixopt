"""Набор тестов для проекта prefixopt.

Покрывает модульные тесты для алгоритмов ядра (core), интеграционные тесты
для CLI команд, проверки парсинга (data), тесты безопасности, граничные случаи,
а также smoke-тесты для публичного API.
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
    """Проверяет корректность сортировки (Broadest First)."""
    input_strs = ["10.0.0.0/24", "10.0.0.0/8", "2001:db8::/32", "192.168.1.1/32"]
    nets = [ipaddress.ip_network(p, strict=False) for p in input_strs]

    sorted_nets = sort_networks(nets)
    result = [str(n) for n in sorted_nets]

    expected = [
        "10.0.0.0/8",
        "10.0.0.0/24",
        "192.168.1.1/32",
        "2001:db8::/32",
    ]
    assert result == expected


def test_core_remove_nested() -> None:
    """Проверяет удаление вложенных сетей."""
    input_strs = ["10.1.1.1/32", "10.0.0.0/8", "10.50.0.0/16"]
    nets = [ipaddress.ip_network(p, strict=False) for p in input_strs]

    optimized = remove_nested(nets)
    result = [str(n) for n in optimized]

    assert len(result) == 1
    assert result[0] == "10.0.0.0/8"


def test_core_aggregation() -> None:
    """Проверяет агрегацию смежных сетей (после сортировки)."""
    input_strs = [
        "192.168.0.0/24",
        "192.168.1.0/24",
        "192.168.2.0/24",
        "192.168.3.0/24",
    ]
    nets = [ipaddress.ip_network(p, strict=False) for p in input_strs]
    # aggregate требует отсортированный и очищенный от вложений список
    sorted_nets = sort_networks(nets)
    clean_nets = remove_nested(sorted_nets, assume_sorted=True)
    aggregated = aggregate(clean_nets)

    assert len(aggregated) == 1
    assert str(aggregated[0]) == "192.168.0.0/22"


def test_core_aggregation_gaps() -> None:
    """Проверяет, что агрегация не склеивает сети, если между ними есть разрыв."""
    input_strs = ["192.168.0.0/24", "192.168.2.0/24"]
    nets = [ipaddress.ip_network(p, strict=False) for p in input_strs]
    sorted_nets = sort_networks(nets)
    clean_nets = remove_nested(sorted_nets, assume_sorted=True)
    aggregated = aggregate(clean_nets)

    assert len(aggregated) == 2


def test_subnetter_split() -> None:
    """Проверяет разбиение сети на более мелкие подсети."""
    network = ipaddress.ip_network("192.168.1.0/24", strict=False)
    subnets = split_network(network, 25)

    subnets_str = [str(n) for n in subnets]
    assert len(subnets_str) == 2
    assert "192.168.1.0/25" in subnets_str
    assert "192.168.1.128/25" in subnets_str


def test_subnetter_protection() -> None:
    """Проверяет защиту от создания слишком большого количества подсетей."""
    network = ipaddress.ip_network("10.0.0.0/8", strict=False)
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
    """Проверяет извлечение IP из мусора."""
    f = tmp_path / "dirty.log"
    f.write_text(
        """
    [INFO] Connection from 1.1.1.1 port 80
    junk data 999.999.999.999 invalid ip
    Valid IPv6: 2001:db8::1/64 detected
    # Commented line 8.8.8.8
    Config: ip address 192.168.1.1 255.255.255.0
    """,
        encoding="utf-8",
    )
    results = list(read_networks(f))
    str_results = {str(r) for r in results}
    assert "1.1.1.1/32" in str_results
    assert "2001:db8::/64" in str_results
    assert "192.168.1.1/32" in str_results


def test_parsing_leading_zeros() -> None:
    """Проверяет защиту от CVE-2021-29921."""
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
    """Интеграционный тест команды optimize."""
    f = tmp_path / "in.txt"
    f.write_text(
        "192.168.0.0/24\n192.168.1.0/24\n10.0.0.0/24\n10.0.0.0/8\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["optimize", str(f)])
    assert result.exit_code == 0
    out = result.stdout
    assert "192.168.0.0/23" in out
    assert "10.0.0.0/8" in out
    assert "10.0.0.0/24" not in out


def test_cli_csv_format(tmp_path: Path) -> None:
    """Проверяет вывод в CSV."""
    f = tmp_path / "in.txt"
    f.write_text("1.1.1.1\n2.2.2.2", encoding="utf-8")
    result = runner.invoke(app, ["optimize", str(f), "--format", "csv"])
    assert result.exit_code == 0
    assert "1.1.1.1/32,2.2.2.2/32" in result.stdout
    assert "\n" not in result.stdout.strip()


def test_cli_merge_comments(tmp_path: Path) -> None:
    """Тест merge --keep-comments."""
    f1 = tmp_path / "list1.txt"
    f1.write_text("10.0.0.1 # Server A\n10.0.0.2 # Server B\n")
    f2 = tmp_path / "list2.txt"
    f2.write_text("10.0.0.3 # Server C\n10.0.0.1 # Duplicate\n")
    result = runner.invoke(app, ["merge", str(f1), str(f2), "--keep-comments"])
    assert result.exit_code == 0
    out = result.stdout
    assert "10.0.0.1/32 # Server A" in out
    assert "10.0.0.2/32 # Server B" in out
    assert "10.0.0.3/32 # Server C" in out
    assert out.count("10.0.0.1/32") == 1
    assert "10.0.0.0/" not in out


def test_cli_merge_append_comment(tmp_path: Path) -> None:
    """Тест merge с --append-comment (требует --keep-comments)."""
    f1 = tmp_path / "new.txt"
    f1.write_text("10.0.0.1\n")
    f2 = tmp_path / "base.txt"
    f2.write_text("10.0.0.2 # Original\n")
    result = runner.invoke(
        app,
        [
            "merge", str(f1), str(f2),
            "--keep-comments", "--append-comment", "New data",
        ],
    )
    assert result.exit_code == 0
    out = result.stdout
    # новый префикс из f1 должен получить комментарий
    assert "10.0.0.1/32 # New data" in out
    # существующий префикс из f2 не должен потерять свой комментарий
    assert "10.0.0.2/32 # Original" in out


def test_cli_merge_append_comment_no_keep_errors(tmp_path: Path) -> None:
    """--append-comment без --keep-comments должно выдавать ошибку."""
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("1.1.1.1")
    f2.write_text("2.2.2.2")
    result = runner.invoke(
        app,
        ["merge", str(f1), str(f2), "--append-comment", "test"],
    )
    assert result.exit_code == 1
    assert "Error" in result.output


def test_cli_filter_bogons(tmp_path: Path) -> None:
    """Тест filter --bogons."""
    f = tmp_path / "mixed.txt"
    f.write_text("8.8.8.8\n127.0.0.1\n169.254.1.1\n224.0.0.1\n0.0.0.0/0\n")
    result = runner.invoke(app, ["filter", str(f), "--bogons"])
    assert result.exit_code == 0
    assert "8.8.8.8/32" in result.stdout
    assert "127.0.0.1" not in result.stdout
    assert "0.0.0.0/0" not in result.stdout


def test_cli_diff_basic(tmp_path: Path) -> None:
    """Проверка diff: Added и Removed."""
    f_old = tmp_path / "old.txt"
    f_new = tmp_path / "new.txt"
    f_old.write_text("10.0.0.0/8\n1.1.1.1/32", encoding="utf-8")
    f_new.write_text("10.0.0.0/8\n2.2.2.2/32", encoding="utf-8")
    result = runner.invoke(app, ["diff", str(f_new), str(f_old)])
    assert result.exit_code == 0
    assert "+ 2.2.2.2/32" in result.stdout
    assert "- 1.1.1.1/32" in result.stdout
    assert "10.0.0.0/8" not in result.stdout


def test_cli_diff_semantic(tmp_path: Path) -> None:
    """Семантическое сравнение в diff."""
    f_old = tmp_path / "old.txt"
    f_new = tmp_path / "new.txt"
    f_old.write_text("192.168.0.0/23", encoding="utf-8")
    f_new.write_text("192.168.0.0/24\n192.168.1.0/24", encoding="utf-8")
    result = runner.invoke(app, ["diff", str(f_new), str(f_old)])
    assert result.exit_code == 0
    assert "Files are identical" in result.stdout


def test_cli_diff_show_unchanged(tmp_path: Path) -> None:
    """Проверка режима unchanged."""
    f_old = tmp_path / "old.txt"
    f_new = tmp_path / "new.txt"
    f_old.write_text("10.0.0.0/8", encoding="utf-8")
    f_new.write_text("10.0.0.0/8", encoding="utf-8")
    result = runner.invoke(app, ["diff", str(f_new), str(f_old), "--mode", "unchanged"])
    assert result.exit_code == 0
    assert "= 10.0.0.0/8" in result.stdout


def test_cli_diff_summary(tmp_path: Path) -> None:
    """Проверка флага --summary."""
    f_old = tmp_path / "old.txt"
    f_new = tmp_path / "new.txt"
    f_old.write_text("1.1.1.1", encoding="utf-8")
    f_new.write_text("2.2.2.2", encoding="utf-8")
    result = runner.invoke(app, ["diff", str(f_new), str(f_old), "--summary"])
    assert result.exit_code == 0
    assert "Added: 1" in result.stdout
    assert "Removed: 1" in result.stdout
    assert "1.1.1.1" not in result.stdout


def test_cli_exclude_single_target(tmp_path: Path) -> None:
    """CLI: исключение одиночного префикса."""
    f = tmp_path / "list.txt"
    f.write_text("10.0.0.0/29", encoding="utf-8")
    result = runner.invoke(app, ["exclude", "10.0.0.3/32", str(f)])
    assert result.exit_code == 0
    assert "10.0.0.3/32" not in result.stdout
    assert "10.0.0.0/31" in result.stdout
    assert "10.0.0.2/32" in result.stdout
    assert "10.0.0.4/30" in result.stdout


def test_cli_exclude_from_file(tmp_path: Path) -> None:
    """CLI: исключение списка из файла."""
    input_file = tmp_path / "allow.txt"
    input_file.write_text("10.0.0.0/24", encoding="utf-8")
    blacklist_file = tmp_path / "deny.txt"
    blacklist_file.write_text("10.0.0.0/25", encoding="utf-8")
    result = runner.invoke(app, ["exclude", str(blacklist_file), str(input_file)])
    assert result.exit_code == 0
    assert "10.0.0.128/25" in result.stdout
    assert "10.0.0.0/25" not in result.stdout


def test_cli_exclude_invalid_target(tmp_path: Path) -> None:
    """Проверка ошибки при некорректном таргете."""
    f = tmp_path / "list.txt"
    f.write_text("1.1.1.1")
    result = runner.invoke(app, ["exclude", "NotAnIP", str(f)])
    assert result.exit_code == 1
    assert "Error" in result.output


def test_cli_exclude_keep_comments(tmp_path: Path) -> None:
    """exclude --keep-comments с наследованием комментариев."""
    f_in = tmp_path / "source.txt"
    f_in.write_text(
        "10.0.0.0/24 # Dept A\n"
        "192.168.1.0/24 # Dept B\n"
        "172.16.0.0/24\n"
        "10.10.10.10 # Host C\n",
        encoding="utf-8",
    )
    f_exclude = tmp_path / "deny.txt"
    f_exclude.write_text("10.0.0.1\n192.168.0.0/16", encoding="utf-8")
    result = runner.invoke(
        app, ["exclude", str(f_exclude), str(f_in), "--keep-comments"]
    )
    assert result.exit_code == 0
    out = result.stdout
    assert "10.0.0.0/32 # Dept A" in out
    assert "10.0.0.2/31 # Dept A" in out
    assert "192.168.1.0" not in out
    assert "Dept B" not in out
    assert "172.16.0.0/24" in out
    assert "172.16.0.0/24 #" not in out
    assert "10.10.10.10/32 # Host C" in out


def test_cli_exclude_keep_comments_edge_case(tmp_path: Path) -> None:
    """Граничный случай: исключение совпадает с началом сети."""
    f_in = tmp_path / "edge.txt"
    f_in.write_text("10.0.0.0/30 # Edge Test", encoding="utf-8")
    result = runner.invoke(app, ["exclude", "10.0.0.0", str(f_in), "--keep-comments"])
    assert result.exit_code == 0
    out = result.stdout
    assert "10.0.0.0" not in out
    assert "10.0.0.1/32 # Edge Test" in out
    assert "10.0.0.2/31 # Edge Test" in out


# ==============================================================================
# 4. STDIN (PIPE) тесты
# ==============================================================================

def test_stdin_optimize() -> None:
    """Оптимизация через пайп."""
    input_data = "10.0.0.0/24\n10.0.0.0/8\n"
    result = runner.invoke(app, ["optimize"], input=input_data)
    assert result.exit_code == 0
    assert "10.0.0.0/8" in result.stdout
    assert "10.0.0.0/24" not in result.stdout


def test_stdin_filter() -> None:
    """Фильтрация через пайп."""
    input_data = "8.8.8.8\n10.0.0.1\n"
    result = runner.invoke(app, ["filter", "--no-private"], input=input_data)
    assert result.exit_code == 0
    assert "8.8.8.8/32" in result.stdout
    assert "10.0.0.1" not in result.stdout


def test_stdin_stats() -> None:
    """Статистика через пайп."""
    input_data = "1.1.1.1\n2.2.2.2\n"
    result = runner.invoke(app, ["stats"], input=input_data)
    assert result.exit_code == 0
    assert "Original prefix count" in result.stdout
    assert "2" in result.stdout


def test_stdin_check() -> None:
    """Проверка через пайп."""
    input_data = "10.0.0.0/8\n"
    result = runner.invoke(app, ["check", "10.1.1.1"], input=input_data)
    assert result.exit_code == 0
    assert "is contained in" in result.stdout


def test_cli_optimize_keep_comments_stdin() -> None:
    """keep-comments при работе через пайп."""
    input_data = "192.168.1.10 # Web Server\n192.168.1.11 # DB Server"
    result = runner.invoke(app, ["optimize", "--keep-comments"], input=input_data)
    assert result.exit_code == 0
    assert "192.168.1.10/32 # Web Server" in result.stdout
    assert "192.168.1.11/32 # DB Server" in result.stdout
    assert "/31" not in result.stdout
    pos_web = result.stdout.find("192.168.1.10")
    pos_db = result.stdout.find("192.168.1.11")
    assert pos_web < pos_db


# ==============================================================================
# 5. Безопасность
# ==============================================================================

def test_security_max_line_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Проверка лимита строк."""
    monkeypatch.setattr("prefixopt.data.file_reader.MAX_LINE_COUNT", 2)
    f = tmp_path / "huge.txt"
    f.write_text("1.1.1.1\n2.2.2.2\n3.3.3.3\n4.4.4.4", encoding="utf-8")
    result = runner.invoke(app, ["optimize", str(f)])
    assert result.exit_code == 1
    assert "exceeds" in result.output
    assert "limit" in result.output


def test_security_max_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Проверка лимита размера файла."""
    monkeypatch.setattr("prefixopt.data.file_reader.MAX_FILE_SIZE_BYTES", 10)
    f = tmp_path / "fat.txt"
    f.write_text("1.1.1.1\n2.2.2.2\n3.3.3.3", encoding="utf-8")
    result = runner.invoke(app, ["optimize", str(f)])
    assert result.exit_code == 1
    assert "exceeds" in result.output
    assert "safety limit" in result.output


# ==============================================================================
# 6. Исключения
# ==============================================================================

def test_exclude_hole_punching() -> None:
    """Вычитание маленькой сети из большой."""
    from prefixopt.core.operations.subtractor import subtract_networks

    source = [ipaddress.ip_network("10.0.0.0/30")]
    exclude = [ipaddress.ip_network("10.0.0.1/32")]
    result = subtract_networks(source, exclude)
    res_str = {str(n) for n in result}
    assert "10.0.0.0/32" in res_str
    assert "10.0.0.2/31" in res_str
    assert "10.0.0.1/32" not in res_str
    assert len(res_str) == 2


def test_exclude_full_removal() -> None:
    """Исключение, перекрывающее всю сеть."""
    from prefixopt.core.operations.subtractor import subtract_networks

    source = [ipaddress.ip_network("192.168.1.1/32")]
    exclude = [ipaddress.ip_network("192.168.0.0/16")]
    result = subtract_networks(source, exclude)
    assert len(result) == 0


def test_exclude_no_overlap() -> None:
    """Отсутствие пересечения."""
    from prefixopt.core.operations.subtractor import subtract_networks

    source = [ipaddress.ip_network("10.0.0.0/8")]
    exclude = [ipaddress.ip_network("192.168.0.0/16")]
    result = subtract_networks(source, exclude)
    assert len(result) == 1
    assert str(result[0]) == "10.0.0.0/8"


def test_exclude_mixed_versions_safety() -> None:
    """Безопасное смешение IPv4/IPv6."""
    from prefixopt.core.operations.subtractor import subtract_networks

    source = [ipaddress.ip_network("10.0.0.0/24")]
    exclude = [ipaddress.ip_network("2001:db8::/32")]
    result = subtract_networks(source, exclude)
    assert len(result) == 1
    assert str(result[0]) == "10.0.0.0/24"


# ==============================================================================
# 7. JSON потоковое чтение
# ==============================================================================

def test_json_streaming_basic(tmp_path: Path) -> None:
    """Потоковое чтение корректного JSON."""
    f = tmp_path / "test.json"
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
    results = list(read_networks(f))
    assert len(results) == 2
    assert ipaddress.ip_network("10.0.0.1/32") in results
    assert ipaddress.ip_network("192.168.1.0/24") in results


def test_json_streaming_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Лимит элементов внутри JSON."""
    monkeypatch.setattr("prefixopt.data.file_reader.MAX_LINE_COUNT", 2)
    f = tmp_path / "huge_array.json"
    f.write_text(
        '{"prefixes": ["1.1.1.1", "2.2.2.2", "3.3.3.3"]}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="JSON array exceeds"):
        list(read_networks(f))


def test_json_malformed(tmp_path: Path) -> None:
    """Устойчивость к битому JSON."""
    f = tmp_path / "broken.json"
    f.write_text('{"prefixes": ["1.1.1.1", "2.2.2', encoding="utf-8")
    results = list(read_networks(f))
    assert len(results) == 1
    assert str(results[0]) == "1.1.1.1/32"


def test_json_garbage_values(tmp_path: Path) -> None:
    """Мусорные значения внутри корректного JSON."""
    f = tmp_path / "garbage.json"
    f.write_text(
        '{"prefixes": ["1.1.1.1", "NotAnIP", "10.0.0.1"]}', encoding="utf-8"
    )
    results = list(read_networks(f))
    assert len(results) == 2
    assert ipaddress.ip_network("1.1.1.1/32") in results
    assert ipaddress.ip_network("10.0.0.1/32") in results


# ==============================================================================
# 8. Strict mode (host bits)
# ==============================================================================

def test_cli_optimize_strict_rejects_host_bits_from_file(tmp_path: Path) -> None:
    """optimize --strict должен выдать ошибку при host bits."""
    f = tmp_path / "bad.txt"
    f.write_text("109.234.11.96/26\n", encoding="utf-8")
    result = runner.invoke(app, ["optimize", str(f), "--strict"])
    assert result.exit_code == 1
    assert "host bits are set" in result.output


def test_cli_optimize_strict_rejects_host_bits_from_stdin() -> None:
    """optimize --strict из STDIN."""
    input_data = "109.234.11.96/26\n"
    result = runner.invoke(app, ["optimize", "--strict"], input=input_data)
    assert result.exit_code == 1
    assert "host bits are set" in result.output


def test_cli_optimize_strict_accepts_valid_networks(tmp_path: Path) -> None:
    """optimize --strict с валидными сетями."""
    f = tmp_path / "good.txt"
    f.write_text("109.234.11.64/26\n109.234.11.128/25\n", encoding="utf-8")
    result = runner.invoke(app, ["optimize", str(f), "--strict"])
    assert result.exit_code == 0
    assert "109.234.11.64/26" in result.stdout
    assert "109.234.11.128/25" in result.stdout


def test_cli_intersect_strict_rejects_invalid_first_file(tmp_path: Path) -> None:
    """intersect --strict с невалидным первым файлом."""
    f1 = tmp_path / "bad_a.txt"
    f2 = tmp_path / "good_b.txt"
    f1.write_text("109.234.11.96/26\n", encoding="utf-8")
    f2.write_text("109.234.11.64/26\n", encoding="utf-8")
    result = runner.invoke(app, ["intersect", str(f1), str(f2), "--strict"])
    assert result.exit_code == 1
    assert "host bits are set" in result.output


def test_cli_intersect_strict_rejects_invalid_second_file(tmp_path: Path) -> None:
    """intersect --strict с невалидным вторым файлом."""
    f1 = tmp_path / "good_a.txt"
    f2 = tmp_path / "bad_b.txt"
    f1.write_text("109.234.11.64/26\n", encoding="utf-8")
    f2.write_text("109.234.11.96/26\n", encoding="utf-8")
    result = runner.invoke(app, ["intersect", str(f1), str(f2), "--strict"])
    assert result.exit_code == 1
    assert "host bits are set" in result.output


def test_cli_intersect_self_mode_strict_accepts_valid_file(tmp_path: Path) -> None:
    """intersect с одним файлом и --strict с валидными данными."""
    f = tmp_path / "self_good.txt"
    f.write_text(
        "10.0.0.0/8\n10.0.0.0/24\n192.168.1.0/24\n", encoding="utf-8"
    )
    result = runner.invoke(app, ["intersect", str(f), "--strict"])
    assert result.exit_code == 0
    assert "Self-Intersection Report" in result.output or "Internal Overlaps" in result.output


def test_cli_intersect_self_mode_strict_rejects_invalid_file(tmp_path: Path) -> None:
    """intersect с одним файлом и --strict с host bits."""
    f = tmp_path / "self_bad.txt"
    f.write_text("109.234.11.96/26\n", encoding="utf-8")
    result = runner.invoke(app, ["intersect", str(f), "--strict"])
    assert result.exit_code == 1
    assert "host bits are set" in result.output


# ==============================================================================
# 9. Smoke-тесты публичного API
# ==============================================================================

import prefixopt
from prefixopt import api


def test_api_load_flexible_input(tmp_path: Path) -> None:
    """api.load с разными источниками."""
    # список
    assert len(list(api.load(["1.1.1.1", "2.2.2.2"]))) == 2
    # строка
    assert len(list(api.load("10.0.0.1 10.0.0.2"))) == 2
    # файл
    f = tmp_path / "test.txt"
    f.write_text("192.168.1.1", encoding="utf-8")
    assert len(list(api.load(f))) == 1


def test_api_optimize() -> None:
    """api.optimize без комментариев."""
    res = api.optimize(["10.0.0.0/8", "10.0.0.0/24"])
    assert len(res) == 1
    assert str(res[0]) == "10.0.0.0/8"


def test_api_optimize_keep_comments(tmp_path: Path) -> None:
    """api.optimize с keep_comments=True."""
    f = tmp_path / "comments.txt"
    f.write_text("10.0.0.1 # A\n10.0.0.2 # B", encoding="utf-8")
    result = api.optimize(f, keep_comments=True)
    assert isinstance(result, list)
    assert len(result) > 0
    ip, comment = result[0]
    assert str(ip) == "10.0.0.1/32"
    assert comment == "# A"


def test_api_add_keep_comments(tmp_path: Path) -> None:
    """api.add с keep_comments=True."""
    f = tmp_path / "inventory.txt"
    f.write_text("192.168.1.10 # Printer", encoding="utf-8")
    result = api.add(f, "192.168.1.11", keep_comments=True)
    found_new = any(
        str(ip) == "192.168.1.11/32" and "# Added" in comment
        for ip, comment in result
    )
    found_old = any(
        str(ip) == "192.168.1.10/32" and "# Printer" in comment
        for ip, comment in result
    )
    assert found_new and found_old


def test_api_merge_keep_comments(tmp_path: Path) -> None:
    """api.merge с keep_comments=True."""
    f1 = tmp_path / "f1.txt"
    f1.write_text("1.1.1.1 # Src1")
    f2 = tmp_path / "f2.txt"
    f2.write_text("2.2.2.2 # Src2")
    result = api.merge(f1, f2, keep_comments=True)
    ips = [str(ip) for ip, _ in result]
    comments = [c for _, c in result]
    assert "1.1.1.1/32" in ips
    assert "2.2.2.2/32" in ips
    assert "# Src1" in comments
    assert "# Src2" in comments



def test_api_filter() -> None:
    """api.filter с флагами."""
    clean = api.filter(["10.0.0.1", "8.8.8.8"], bogons=True, exclude_private=True)
    clean_strs = [str(ip) for ip in clean]
    assert "8.8.8.8/32" in clean_strs
    assert "10.0.0.1/32" not in clean_strs


def test_api_exclude_smoke() -> None:
    """api.exclude (дымовой тест)."""
    src = ["10.0.0.0/24"]
    rem = api.exclude(src, "10.0.0.1/32")
    # удалён один хост, должно появиться несколько фрагментов
    assert len(rem) > 1
    assert "10.0.0.1/32" not in {str(n) for n in rem}


def test_api_diff_smoke() -> None:
    """api.diff (дымовой тест)."""
    added, removed, unchanged = api.diff(["10.0.0.1", "10.0.0.2"], ["10.0.0.1"])
    assert len(added) == 1
    assert len(removed) == 0
    assert len(unchanged) == 1


def test_api_intersect_smoke() -> None:
    """api.intersect (дымовой тест)."""
    common = api.intersect(["10.0.0.0/24", "192.168.1.0/24"], ["10.0.0.0/8"])
    assert len(common) > 0


def test_api_split_smoke() -> None:
    """api.split (дымовой тест)."""
    parts = api.split("10.0.0.0/30", 32)
    assert len(parts) == 4


def test_api_stats_smoke() -> None:
    """api.stats (дымовой тест)."""
    s = api.stats(["10.0.0.0/24"])
    assert s["original_prefix_count"] == 1
    assert s["unique_ips"] == 256


def test_api_check_smoke() -> None:
    """api.check (дымовой тест)."""
    cont = api.check("10.0.0.5", ["10.0.0.0/24"])
    assert len(cont) == 1


# ==============================================================================
# 10. Интеграционные сценарии API
# ==============================================================================

def test_integration_simple_json_list() -> None:
    """Сценарий: внешний API возвращает список IP."""
    raw = ["192.168.1.10", "192.168.1.12", "10.0.0.1/24"]
    optimized = api.optimize(raw)
    # не смежные → останутся как есть
    assert len(optimized) == 3
    assert "10.0.0.0/24" in [str(n) for n in optimized]


def test_integration_complex_json_structure() -> None:
    """Сценарий: внешний API возвращает список словарей."""
    api_response = [
        {"host": "10.0.0.1", "region": "us-east"},
        {"host": "10.0.0.2", "region": "us-west"},
        {"host": "invalid-ip", "region": "null"},
    ]
    ip_list = [item["host"] for item in api_response]
    result = api.optimize(ip_list)
    assert len(result) == 2  # мусор проигнорирован
    assert str(result[0]) == "10.0.0.1/32"


def test_integration_dirty_security_feed() -> None:
    """Сценарий: фид с мусорными адресами."""
    threat_feed = [
        "200.1.1.1",
        "150.2.2.2",
        "127.0.0.1",
        "192.168.1.1",
        "   8.8.8.8   ",
    ]
    clean = api.filter(threat_feed, bogons=True, exclude_private=True)
    clean_strs = {str(ip) for ip in clean}
    assert "200.1.1.1/32" in clean_strs
    assert "150.2.2.2/32" in clean_strs
    assert "8.8.8.8/32" in clean_strs
    assert "127.0.0.1/32" not in clean_strs
    assert "192.168.1.1/32" not in clean_strs


def test_integration_pipeline_merge_diff() -> None:
    """Сценарий: мерж и сравнение."""
    api_a = ["10.0.0.1", "10.0.0.2"]
    api_b = ["10.0.0.4", "10.0.0.1"]
    local = ["10.0.0.1", "10.0.0.5"]
    merged = api.merge(api_a, api_b)
    added, removed, unchanged = api.diff(merged, local)
    added_str = {str(i) for i in added}
    removed_str = {str(i) for i in removed}
    unchanged_str = {str(i) for i in unchanged}
    assert "10.0.0.2/32" in added_str
    assert "10.0.0.4/32" in added_str
    assert "10.0.0.5/32" in removed_str
    assert "10.0.0.1/32" in unchanged_str


def test_parsing_ip_ranges() -> None:
    """Парсинг диапазонов IP."""
    from prefixopt.api import load

    # Идеальный CIDR
    res1 = list(load("192.168.1.0 - 192.168.1.3"))
    assert "192.168.1.0/30" in [str(r) for r in res1]

    # Невыровненный диапазон
    res2 = list(load("10.0.0.1 - 10.0.0.2"))
    cidr_strs = [str(r) for r in res2]
    assert "10.0.0.1/32" in cidr_strs
    assert "10.0.0.2/32" in cidr_strs
    for r in cidr_strs:
        assert "/31" not in r


def test_package_exposure() -> None:
    """Проверка доступности функций из корня пакета."""
    assert hasattr(prefixopt, "optimize")
    assert hasattr(prefixopt, "load")
    assert hasattr(prefixopt, "merge")


def test_cli_intersect_multi_files(tmp_path: Path) -> None:
    """Проверка пересечения трёх файлов."""
    f1 = tmp_path / "a.txt"
    f1.write_text("10.0.0.0/24\n10.0.0.128/25\n")
    f2 = tmp_path / "b.txt"
    f2.write_text("10.0.0.0/24\n192.168.1.0/24\n")
    f3 = tmp_path / "c.txt"
    f3.write_text("10.0.0.0/24\n10.0.0.128/25\n")
    result = runner.invoke(app, ["intersect", str(f1), str(f2), str(f3)])
    assert result.exit_code == 0
    # Общий префикс: только 10.0.0.0/24
    assert "10.0.0.0/24" in result.stdout
    assert "10.0.0.128/25" not in result.stdout  # отсутствует в f2
    assert "192.168.1.0/24" not in result.stdout
    # Проверяем присутствие матрицы
    assert "Presence Matrix" in result.stdout
    assert "Y" in result.stdout  # символ присутствия


def test_cli_intersect_multi_no_common(tmp_path: Path) -> None:
    """Если нет общих префиксов — должно быть сообщение."""
    f1 = tmp_path / "a.txt"
    f1.write_text("1.1.1.1\n")
    f2 = tmp_path / "b.txt"
    f2.write_text("2.2.2.2\n")
    f3 = tmp_path / "c.txt"
    f3.write_text("3.3.3.3\n")
    result = runner.invoke(app, ["intersect", str(f1), str(f2), str(f3)])
    assert result.exit_code == 0
    assert "No prefixes appear in at least 2 sources." in result.stdout


def test_cli_intersect_multi_partial_coverage(tmp_path: Path) -> None:
    """Проверка трёх файлов: общий для двух из трёх префикс попадает в отчёт."""
    f1 = tmp_path / "a.txt"
    f1.write_text("10.0.0.0/24\n192.168.1.0/24\n")
    f2 = tmp_path / "b.txt"
    f2.write_text("10.0.0.0/24\n172.16.0.0/24\n")
    f3 = tmp_path / "c.txt"
    f3.write_text("10.0.0.0/24\n10.0.0.128/25\n")
    result = runner.invoke(app, ["intersect", str(f1), str(f2), str(f3)])
    assert result.exit_code == 0
    # 10.0.0.0/24 есть во всех трёх попадёт
    assert "10.0.0.0/24" in result.stdout
    # 192.168.1.0/24 только в f1 не попадёт (порог 2)
    assert "192.168.1.0/24" not in result.stdout
    # Должна быть таблица присутствия
    assert "Presence Matrix" in result.stdout
    assert "Y" in result.stdout               # символ Y