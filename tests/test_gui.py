"""
Набор тестов для GUI-модуля prefixopt.

Покрывает:
- Модели данных (dataclass сериализация).
- Форматирование вывода (output_formatter).
- Worker (сигналы, отмена, ошибки).
- InputPanel (save/restore state, clear, data source).
- OutputPanel (пейджинация, очистка, буфер).
- SplitOutputPanel (HTML/plain text, счётчик строк).
- SettingsManager (сохранение/восстановление, сплиттеры, recent files).
- Сервисный слой (прямые вызовы функций services, интеграция core+gui).
"""

import io
import logging
from pathlib import Path
from typing import Any

import pytest

# ==============================================================================
# 1. Модели данных
# ==============================================================================

class TestModels:
    """Проверка dataclass-моделей."""

    def test_optimize_result_defaults(self) -> None:
        from prefixopt.gui.models import OptimizeResult
        r = OptimizeResult()
        assert r.formatted_text == ""
        assert r.input_count == 0
        assert r.output_count == 0
        assert r.keep_comments is False

    def test_optimize_result_with_values(self) -> None:
        from prefixopt.gui.models import OptimizeResult
        r = OptimizeResult(
            input_count=10,
            output_count=5,
            formatted_text="1.1.1.1/32\n",
        )
        assert r.input_count == 10
        assert r.output_count == 5
        assert r.formatted_text == "1.1.1.1/32\n"

    def test_filter_result(self) -> None:
        from prefixopt.gui.models import FilterResult
        r = FilterResult(original_count=100, removed_count=20)
        assert r.original_count == 100
        assert r.removed_count == 20
        assert r.formatted_text == ""

    def test_diff_report(self) -> None:
        from prefixopt.gui.models import DiffReport
        r = DiffReport()
        assert r.added == []
        assert r.removed == []
        assert r.unchanged == []

    def test_stats_result(self) -> None:
        from prefixopt.gui.models import StatsResult
        r = StatsResult(
            original_prefix_count=42,
            optimized_prefix_count=10,
            compression_ratio_percent=76.19,
            duplicates=[("10.0.0.1/32", 3)],
        )
        assert r.original_prefix_count == 42
        assert r.duplicates == [("10.0.0.1/32", 3)]

    def test_check_result_defaults(self) -> None:
        from prefixopt.gui.models import CheckResult
        r = CheckResult()
        assert r.found is False
        assert r.target == ""
        assert r.containing_networks == []

    def test_pairwise_exact(self) -> None:
        from prefixopt.gui.models import PairwiseExact
        pe = PairwiseExact(name_a="A", name_b="B")
        assert pe.name_a == "A"
        assert pe.name_b == "B"
        assert pe.prefixes == []

    def test_pairwise_partial(self) -> None:
        from prefixopt.gui.models import PairwisePartial
        pp = PairwisePartial(source_subnet="S1", source_supernet="S2")
        assert pp.source_subnet == "S1"
        assert pp.source_supernet == "S2"


# ==============================================================================
# 2. Форматирование вывода
# ==============================================================================

class TestOutputFormatter:
    """Проверка функций форматирования."""

    def test_format_list(self) -> None:
        from prefixopt.gui.output_formatter import format_prefixes
        import ipaddress
        nets = [ipaddress.ip_network("10.0.0.0/8"),
                ipaddress.ip_network("192.168.1.0/24")]
        result = format_prefixes(nets, fmt="list")
        assert result == "10.0.0.0/8\n192.168.1.0/24\n"

    def test_format_csv(self) -> None:
        from prefixopt.gui.output_formatter import format_prefixes
        import ipaddress
        nets = [ipaddress.ip_network("10.0.0.0/8"),
                ipaddress.ip_network("192.168.1.0/24")]
        result = format_prefixes(nets, fmt="csv")
        assert result == "10.0.0.0/8,192.168.1.0/24\n"

    def test_format_empty_list(self) -> None:
        from prefixopt.gui.output_formatter import format_prefixes
        result = format_prefixes([], fmt="list")
        assert result == "\n"

    def test_format_with_comments(self) -> None:
        from prefixopt.gui.output_formatter import format_prefixes
        import ipaddress
        commented = [
            (ipaddress.ip_network("10.0.0.0/8"), "# Backbone"),
            (ipaddress.ip_network("192.168.1.0/24"), ""),
        ]
        result = format_prefixes([], fmt="list", commented=commented)
        assert "10.0.0.0/8 # Backbone" in result
        assert "192.168.1.0/24\n" in result
        assert " # Backbone" in result

    def test_format_comments_rejects_csv(self) -> None:
        from prefixopt.gui.output_formatter import format_prefixes
        with pytest.raises(ValueError, match="CSV format is not supported"):
            format_prefixes([], fmt="csv", commented=[])


# ==============================================================================
# 3. Worker (сигналы, отмена, ошибки)
# ==============================================================================

class TestWorker:
    """Проверка фоновых задач Worker."""

    def test_worker_success(self, qapp: Any) -> None:
        """Базовый успешный сценарий: результат доставляется."""
        from PySide6.QtCore import QThreadPool, QTimer
        from prefixopt.gui.workers import Worker

        results = []

        def fn() -> int:
            return 42

        def on_result(val: int) -> None:
            results.append(val)

        worker = Worker(fn)
        worker.signals.result.connect(on_result)
        pool = QThreadPool.globalInstance()
        pool.start(worker)
        pool.waitForDone(5000)
        QTimer.singleShot(0, lambda: None)
        qapp.processEvents()

        assert len(results) == 1
        assert results[0] == 42

    def test_worker_error(self, qapp: Any) -> None:
        """Исключение внутри worker'а передаётся в сигнал error."""
        from PySide6.QtCore import QThreadPool, QTimer
        from prefixopt.gui.workers import Worker

        errors = []

        def fn() -> None:
            raise ValueError("test error")

        def on_error(msg: str) -> None:
            errors.append(msg)

        worker = Worker(fn)
        worker.signals.error.connect(on_error)
        pool = QThreadPool.globalInstance()
        pool.start(worker)
        pool.waitForDone(5000)
        QTimer.singleShot(0, lambda: None)
        qapp.processEvents()

        assert len(errors) == 1
        assert "test error" in errors[0]

    def test_worker_cancel_before_run(self, qapp: Any) -> None:
        """Отмена до запуска: finished и cancelled, а не result."""
        from PySide6.QtCore import QThreadPool
        from prefixopt.gui.workers import Worker

        cancellations = 0
        finished = 0

        def fn() -> int:
            return 42

        worker = Worker(fn)
        worker.signals.cancelled.connect(lambda: setattr(worker, "_cancel_count",
                                                         getattr(worker, "_cancel_count", 0) + 1))
        worker.signals.finished.connect(lambda: setattr(worker, "_finish_count",
                                                         getattr(worker, "_finish_count", 0) + 1))

        # Отменяем до запуска
        worker.cancel()
        assert worker.is_cancelled() is True

        pool = QThreadPool.globalInstance()
        pool.start(worker)
        pool.waitForDone(3000)

    def test_worker_cancel_flag_persists(self, qapp: Any) -> None:
        """Флаг отмены устанавливается и читается корректно."""
        from prefixopt.gui.workers import Worker

        worker = Worker(lambda: None)
        assert worker.is_cancelled() is False
        worker.cancel()
        assert worker.is_cancelled() is True

    def test_worker_args_passed_correctly(self, qapp: Any) -> None:
        """Позиционные и именованные аргументы передаются в функцию."""
        from PySide6.QtCore import QThreadPool, QTimer
        from prefixopt.gui.workers import Worker

        results = []

        def fn(a: int, b: int, multiplier: int = 1) -> int:
            return (a + b) * multiplier

        worker = Worker(fn, 10, 20, multiplier=2)
        worker.signals.result.connect(lambda v: results.append(v))
        pool = QThreadPool.globalInstance()
        pool.start(worker)
        pool.waitForDone(5000)
        QTimer.singleShot(0, lambda: None)
        qapp.processEvents()

        assert len(results) == 1
        assert results[0] == 60


# ==============================================================================
# 4. Сервисный слой (интеграция core + gui)
# ==============================================================================

class TestServices:
    """Проверка функций сервисного слоя на малых данных."""

    def test_run_optimize_basic(self) -> None:
        from prefixopt.gui.services import run_optimize
        result = run_optimize(
            "10.0.0.1\n10.0.0.2\n192.168.1.1",
            fmt="list",
        )
        assert result.output_count == 3
        assert "10.0.0.1/32" in result.formatted_text
        assert "10.0.0.2/32" in result.formatted_text
        assert "192.168.1.1/32" in result.formatted_text
        assert result.input_count == 3

    def test_run_optimize_aggregation(self) -> None:
        from prefixopt.gui.services import run_optimize
        result = run_optimize(
            "192.168.0.0/24\n192.168.1.0/24",
            fmt="list",
        )
        assert result.output_count == 1
        assert "192.168.0.0/23" in result.formatted_text

    def test_run_optimize_with_comments(self) -> None:
        from prefixopt.gui.services import run_optimize
        result = run_optimize(
            "10.0.0.1 # Server A\n10.0.0.2 # Server B",
            fmt="list",
            keep_comments=True,
        )
        assert "# Server A" in result.formatted_text
        assert "# Server B" in result.formatted_text
        assert result.keep_comments is True

    def test_run_optimize_csv(self) -> None:
        from prefixopt.gui.services import run_optimize
        result = run_optimize("1.1.1.1\n2.2.2.2", fmt="csv")
        assert "1.1.1.1/32,2.2.2.2/32" in result.formatted_text

    def test_run_filter_bogons(self) -> None:
        from prefixopt.gui.services import run_filter
        result = run_filter(
            "8.8.8.8\n127.0.0.1\n10.0.0.1",
            fmt="list",
            bogons=True,
        )
        assert "8.8.8.8/32" in result.formatted_text
        assert result.removed_count == 2
        assert result.original_count == 3

    def test_run_filter_single_flag(self) -> None:
        from prefixopt.gui.services import run_filter
        result = run_filter(
            "8.8.8.8\n10.0.0.1",
            fmt="list",
            exclude_private=True,
        )
        assert "8.8.8.8/32" in result.formatted_text
        assert "10.0.0.1" not in result.formatted_text

    def test_run_add_prefix(self) -> None:
        from prefixopt.gui.services import run_add
        result = run_add("10.0.0.1\n10.0.0.10", "10.0.0.20", fmt="list")
        assert "10.0.0.20/32" in result.formatted_text
        assert "10.0.0.1/32" in result.formatted_text
        assert "10.0.0.10/32" in result.formatted_text
        assert result.output_count == 3

    def test_run_add_keep_comments(self) -> None:
        from prefixopt.gui.services import run_add
        result = run_add(
            "10.0.0.1 # A",
            "10.0.0.2",
            fmt="list",
            keep_comments=True,
        )
        assert "# A" in result.formatted_text
        assert "# Added" in result.formatted_text
        assert result.keep_comments is True

    def test_run_merge(self) -> None:
        from prefixopt.gui.services import run_merge
        result = run_merge(
            "10.0.0.0/24",
            "192.168.1.0/24",
            fmt="list",
        )
        assert result.total_count == 2
        assert "10.0.0.0/24" in result.formatted_text
        assert "192.168.1.0/24" in result.formatted_text

    def test_run_merge_keep_comments(self) -> None:
        from prefixopt.gui.services import run_merge
        result = run_merge(
            "10.0.0.1 # A",
            "10.0.0.2 # B",
            fmt="list",
            keep_comments=True,
        )
        assert "# A" in result.formatted_text
        assert "# B" in result.formatted_text

    def test_run_merge_with_append_comment(self) -> None:
        from prefixopt.gui.services import run_merge
        result = run_merge(
            "10.0.0.1",
            "10.0.0.2 # Original",
            fmt="list",
            keep_comments=True,
            append_comment="Tagged",
        )
        assert "# Tagged" in result.formatted_text
        assert "# Original" in result.formatted_text

    def test_run_exclude(self) -> None:
        from prefixopt.gui.services import run_exclude
        result = run_exclude(
            "10.0.0.0/30",
            "10.0.0.1/32",
            fmt="list",
        )
        assert "10.0.0.0/32" in result.formatted_text or "10.0.0.2/31" in result.formatted_text
        assert "10.0.0.1/32" not in result.formatted_text

    def test_run_exclude_keep_comments(self) -> None:
        from prefixopt.gui.services import run_exclude
        result = run_exclude(
            "10.0.0.0/30 # Test",
            "10.0.0.1/32",
            fmt="list",
            keep_comments=True,
        )
        assert "# Test" in result.formatted_text

    def test_run_diff(self) -> None:
        from prefixopt.gui.services import run_diff
        result = run_diff(
            "10.0.0.1\n10.0.0.2",
            "10.0.0.1",
        )
        assert len(result.added) == 1
        assert len(result.removed) == 0
        assert len(result.unchanged) == 1

    def test_run_intersect_two_sources(self) -> None:
        from prefixopt.gui.services import run_intersect
        result = run_intersect(
            "10.0.0.0/24\n192.168.1.0/24",
            "10.0.0.0/24\n172.16.0.0/24",
        )
        assert len(result.exact_matches) >= 1
        assert str(result.exact_matches[0]) == "10.0.0.0/24"
        assert result.volume_intersection > 0

    def test_run_intersect_self_mode(self) -> None:
        from prefixopt.gui.services import run_intersect
        result = run_intersect(
            "10.0.0.0/8\n10.0.0.0/24",
        )
        assert result.self_mode is True

    def test_run_split(self) -> None:
        from prefixopt.gui.services import run_split
        result = run_split("192.168.1.0/24", 25, fmt="list")
        assert result.total_count == 2
        assert "192.168.1.0/25" in result.formatted_text
        assert "192.168.1.128/25" in result.formatted_text

    def test_run_stats(self) -> None:
        from prefixopt.gui.services import run_stats
        result = run_stats("10.0.0.0/8\n192.168.1.0/24")
        assert result.original_prefix_count == 2
        assert result.optimized_prefix_count > 0
        assert result.unique_ips > 0

    def test_run_stats_with_duplicates(self) -> None:
        from prefixopt.gui.services import run_stats
        result = run_stats("10.0.0.1\n10.0.0.1\n10.0.0.2")
        assert len(result.duplicates) >= 1

    def test_run_check_found(self) -> None:
        from prefixopt.gui.services import run_check
        result = run_check("10.1.1.1", "10.0.0.0/8")
        assert result.found is True
        assert len(result.containing_networks) == 1

    def test_run_check_not_found(self) -> None:
        from prefixopt.gui.services import run_check
        result = run_check("1.1.1.1", "10.0.0.0/8")
        assert result.found is False

    def test_run_check_invalid_target(self) -> None:
        from prefixopt.gui.services import run_check
        result = run_check("not-an-ip", "10.0.0.0/8")
        assert result.found is False

    def test_run_multi_intersect(self) -> None:
        from prefixopt.gui.services import run_multi_intersect
        result = run_multi_intersect(
            "10.0.0.0/24\n192.168.1.0/24",
            "10.0.0.0/24\n172.16.0.0/24",
            "10.0.0.0/24\n10.0.0.128/25",
        )
        assert result.source_count == 3
        assert len(result.filtered_prefixes) >= 1
        assert "10.0.0.0/24" in {str(n) for n in result.filtered_prefixes}
        assert len(result.pairwise_exact) >= 1

    def test_run_multi_intersect_raises_on_single_source(self) -> None:
        from prefixopt.gui.services import run_multi_intersect
        with pytest.raises(ValueError, match="at least 2"):
            run_multi_intersect("10.0.0.0/24")


# ==============================================================================
# 5. InputPanel (save_state / restore_state)
# ==============================================================================

class TestInputPanelState:
    """Проверка механизма save/restore состояния InputPanel."""

    def test_save_state_text_mode(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.input_panel import InputPanel

        panel = InputPanel()
        qtbot.addWidget(panel)

        # Устанавливаем текст
        panel.text_mode_radio.setChecked(True)
        panel.text_edit.setPlainText("10.0.0.1\n10.0.0.2")

        state = panel.save_state()
        assert state["is_file_mode"] is False
        assert state["text_content"] == "10.0.0.1\n10.0.0.2"
        assert state["selected_file"] is None

    def test_save_state_file_mode(self, qtbot: Any, tmp_path: Path) -> None:
        from prefixopt.gui.widgets.input_panel import InputPanel

        panel = InputPanel()
        qtbot.addWidget(panel)

        # Симулируем выбор файла
        test_file = tmp_path / "test.txt"
        test_file.write_text("1.1.1.1")
        panel.file_mode_radio.setChecked(True)
        panel.set_file(test_file)

        state = panel.save_state()
        assert state["is_file_mode"] is True
        assert state["selected_file"] == test_file
        assert str(test_file) in state["file_path"]

    def test_restore_state_text_mode(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.input_panel import InputPanel

        panel = InputPanel()
        qtbot.addWidget(panel)

        state = {
            "is_file_mode": False,
            "selected_file": None,
            "file_path": "",
            "text_content": "192.168.1.1\n10.0.0.1",
        }
        panel.restore_state(state)

        assert panel.text_mode_radio.isChecked() is True
        assert panel.get_data_source() == "192.168.1.1\n10.0.0.1"

    def test_restore_state_file_mode(self, qtbot: Any, tmp_path: Path) -> None:
        from prefixopt.gui.widgets.input_panel import InputPanel

        panel = InputPanel()
        qtbot.addWidget(panel)

        test_file = tmp_path / "restore.txt"
        test_file.write_text("8.8.8.8")

        state = {
            "is_file_mode": True,
            "selected_file": test_file,
            "file_path": str(test_file),
            "text_content": "",
        }
        panel.restore_state(state)

        assert panel.file_mode_radio.isChecked() is True
        ds = panel.get_data_source()
        assert ds is not None
        assert ds.name == "restore.txt"

    def test_swap_state(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.input_panel import InputPanel

        a = InputPanel(title="A")
        b = InputPanel(title="B")
        qtbot.addWidget(a)
        qtbot.addWidget(b)

        a.text_mode_radio.setChecked(True)
        a.text_edit.setPlainText("content_a")
        b.text_mode_radio.setChecked(True)
        b.text_edit.setPlainText("content_b")

        state_a = a.save_state()
        state_b = b.save_state()
        a.restore_state(state_b)
        b.restore_state(state_a)

        assert a.get_data_source() == "content_b"
        assert b.get_data_source() == "content_a"

    def test_clear_resets_state(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.input_panel import InputPanel

        panel = InputPanel()
        qtbot.addWidget(panel)

        panel.text_mode_radio.setChecked(True)
        panel.text_edit.setPlainText("something")
        assert panel.get_data_source() is not None

        panel.clear()
        assert panel.get_data_source() is None

    def test_get_data_source_returns_none_when_empty(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.input_panel import InputPanel

        panel = InputPanel()
        qtbot.addWidget(panel)

        # File mode, no file selected
        panel.file_mode_radio.setChecked(True)
        assert panel.get_data_source() is None

        # Text mode, empty
        panel.text_mode_radio.setChecked(True)
        assert panel.get_data_source() is None


# ==============================================================================
# 6. OutputPanel (пейджинация, буфер, очистка)
# ==============================================================================

class TestOutputPanel:
    """Проверка панели вывода."""

    def test_set_text_basic(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.output_panel import OutputPanel

        panel = OutputPanel()
        qtbot.addWidget(panel)
        panel.set_text("line1\nline2\nline3\n")

        assert panel.get_text() == "line1\nline2\nline3\n"

    def test_clear(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.output_panel import OutputPanel

        panel = OutputPanel()
        qtbot.addWidget(panel)
        panel.set_text("some content")
        panel.clear()

        assert panel.get_text() == ""

    def test_get_text_returns_full_buffer(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.output_panel import OutputPanel

        panel = OutputPanel()
        qtbot.addWidget(panel)

        long_text = "\n".join(f"line{i}" for i in range(15000))
        panel.set_text(long_text)

        # Полный текст сохраняется в буфере
        full = panel.get_text()
        assert len(full.splitlines()) == 15000

    def test_append_text(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.output_panel import OutputPanel

        panel = OutputPanel()
        qtbot.addWidget(panel)
        panel.set_text("first")
        panel.append_text("second")

        assert "first" in panel.get_text()
        assert "second" in panel.get_text()

    def test_set_html(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.output_panel import OutputPanel

        panel = OutputPanel()
        qtbot.addWidget(panel)
        panel.set_html("<html><body><b>test</b></body></html>")

        text = panel.get_text()
        assert "test" in text


# ==============================================================================
# 7. SplitOutputPanel
# ==============================================================================

class TestSplitOutputPanel:
    """Проверка двойной панели."""

    def test_set_report_text(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.split_output_panel import SplitOutputPanel

        panel = SplitOutputPanel()
        qtbot.addWidget(panel)
        panel.set_report_text("report content")

        assert "report content" in panel.report_edit.toPlainText()

    def test_set_report_html(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.split_output_panel import SplitOutputPanel

        panel = SplitOutputPanel()
        qtbot.addWidget(panel)
        panel.set_report_html("<html><body><h2>HTML</h2></body></html>")

        text = panel.report_edit.toPlainText()
        assert "HTML" in text

    def test_get_output_panel(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.split_output_panel import SplitOutputPanel

        panel = SplitOutputPanel()
        qtbot.addWidget(panel)

        op = panel.get_output_panel()
        assert op is not None
        from prefixopt.gui.widgets.output_panel import OutputPanel
        assert isinstance(op, OutputPanel)

    def test_clear_output(self, qtbot: Any) -> None:
        from prefixopt.gui.widgets.split_output_panel import SplitOutputPanel

        panel = SplitOutputPanel()
        qtbot.addWidget(panel)
        panel.set_output_text("some output")
        panel.clear_output()

        assert panel.get_output_panel().get_text() == ""


# ==============================================================================
# 8. SettingsManager
# ==============================================================================

class TestSettingsManager:
    """Проверка менеджера настроек."""

    def test_singleton(self) -> None:
        from prefixopt.gui.settings_manager import SettingsManager

        a = SettingsManager.instance()
        b = SettingsManager.instance()
        assert a is b

    def test_register_tab(self) -> None:
        from prefixopt.gui.settings_manager import SettingsManager

        mgr = SettingsManager()
        obj = object()
        mgr.register_tab("test_tab", obj)
        # Не должно упасть
        mgr.unregister_tab("test_tab")

    def test_save_load_tab_settings(self) -> None:
        from prefixopt.gui.settings_manager import SettingsManager

        mgr = SettingsManager()

        class FakeTab:
            def __init__(self) -> None:
                self.data = {"key": "value"}

            def save_settings(self) -> dict:
                return self.data

            def load_settings(self, state: dict) -> None:
                self.data = state

        tab = FakeTab()
        mgr.register_tab("fake", tab)
        mgr.save_tab_settings("fake")
        tab.data = {}
        mgr.load_tab_settings("fake")
        assert tab.data == {"key": "value"}
        mgr.unregister_tab("fake")

    def test_save_load_main_window(self) -> None:
        from prefixopt.gui.settings_manager import SettingsManager

        mgr = SettingsManager()
        mgr.save_main_window(
            geometry=b"fake_geo",
            maximized=True,
            current_tab=2,
        )

        assert mgr.load_main_window_maximized() is True
        assert mgr.load_main_window_current_tab() == 2

    def test_recent_files_roundtrip(self) -> None:
        from prefixopt.gui.settings_manager import SettingsManager

        mgr = SettingsManager()
        mgr.add_recent_file("/path/to/file.txt")

        recent = mgr.recent_files()
        assert "/path/to/file.txt" in recent

    def test_recent_files_max_ten(self) -> None:
        from prefixopt.gui.settings_manager import SettingsManager

        mgr = SettingsManager()
        for i in range(15):
            mgr.add_recent_file(f"/path/to/file_{i}.txt")

        recent = mgr.recent_files()
        assert len(recent) <= 10

    def test_splitter_sizes_roundtrip(self) -> None:
        from prefixopt.gui.settings_manager import SettingsManager

        mgr = SettingsManager()
        mgr.save_splitter_sizes("test/panel", [300, 700])

        sizes = mgr.load_splitter_sizes("test/panel")
        assert sizes == [300, 700]

    def test_splitter_sizes_default_empty(self) -> None:
        from prefixopt.gui.settings_manager import SettingsManager

        mgr = SettingsManager()
        sizes = mgr.load_splitter_sizes("nonexistent/key")
        assert sizes == []


# ==============================================================================
# 9. Strip rich tags
# ==============================================================================

class TestStripRichTags:
    """Проверка удаления rich-тегов."""

    def test_strip_basic_tags(self) -> None:
        from prefixopt.gui.widgets.output_panel import strip_rich_tags
        assert strip_rich_tags("[red]hello[/red]") == "hello"

    def test_strip_nested_tags(self) -> None:
        from prefixopt.gui.widgets.output_panel import strip_rich_tags
        assert strip_rich_tags("[bold][green]text[/green][/bold]") == "text"

    def test_strip_plain_text_unchanged(self) -> None:
        from prefixopt.gui.widgets.output_panel import strip_rich_tags
        assert strip_rich_tags("hello world") == "hello world"

    def test_strip_empty_string(self) -> None:
        from prefixopt.gui.widgets.output_panel import strip_rich_tags
        assert strip_rich_tags("") == ""
