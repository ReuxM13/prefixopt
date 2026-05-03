"""
Вкладка фильтрации списков префиксов.

Удаляет private, loopback, multicast, reserved и bogon префиксы.
"""

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from .base_operation_tab import BaseOperationTab
from ..models import FilterResult
from ..services import run_filter
from ..widgets.input_panel import InputPanel
from ..widgets.options_group import OptionsGroup
from ..workers import Worker


class FilterTab(BaseOperationTab):
    """Вкладка фильтрации списков префиксов."""

    def __init__(self) -> None:
        """Инициализирует вкладку и создает элементы интерфейса."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Создает структуру вкладки."""
        self.control_layout.addWidget(
            QLabel(
                "Filter out private, loopback, multicast, reserved "
                "and bogon prefixes."
            )
        )

        self.input_panel = InputPanel(
            title="Source",
            file_label="Input file",
            text_placeholder="Paste prefixes here...",
        )
        self.control_layout.addWidget(self.input_panel)

        options = OptionsGroup("Filter options")
        self.no_private = QCheckBox("Exclude private (RFC 1918, ULA)")
        self.no_loopback = QCheckBox("Exclude loopback (127.0.0.0/8, ::1)")
        self.no_link_local = QCheckBox(
            "Exclude link-local (169.254.0.0/16, fe80::/10)"
        )
        self.no_multicast = QCheckBox(
            "Exclude multicast (224.0.0.0/4, ff00::/8)"
        )
        self.no_reserved = QCheckBox("Exclude reserved (IETF special use)")
        self.bogons = QCheckBox("Bogons (all of the above)")
        self.output_format = QComboBox()
        self.output_format.addItems(["list", "csv"])
        self.strict = QCheckBox("Strict mode")

        form = QFormLayout()
        form.addRow(self.no_private)
        form.addRow(self.no_loopback)
        form.addRow(self.no_link_local)
        form.addRow(self.no_multicast)
        form.addRow(self.no_reserved)
        form.addRow(self.bogons)
        form.addRow("Output format:", self.output_format)
        form.addRow(self.strict)
        options.add_layout(form)
        self.control_layout.addWidget(options)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Filter")
        self.run_button.setProperty("primary", True)
        run_row.addStretch()
        run_row.addWidget(self.run_button)
        self.control_layout.addLayout(run_row)

        self._setup_splitter(self.output_panel)

        self.run_button.clicked.connect(self._run_filter)
        self.input_panel.source_changed.connect(self._update_state)
        self.bogons.toggled.connect(self._on_bogons_toggled)
        self._update_state()

    def _update_state(self, _: Any = None) -> None:
        """Обновляет доступность кнопки запуска."""
        self.run_button.setEnabled(
            self.input_panel.get_data_source() is not None
        )

    def _on_bogons_toggled(self, checked: bool) -> None:
        """
        Блокирует индивидуальные чекбоксы при активации bogons.

        Args:
            checked: Состояние чекбокса bogons.
        """
        self.no_private.setEnabled(not checked)
        self.no_loopback.setEnabled(not checked)
        self.no_link_local.setEnabled(not checked)
        self.no_multicast.setEnabled(not checked)
        self.no_reserved.setEnabled(not checked)

    def _run_filter(self) -> None:
        """Собирает параметры и запускает фильтрацию в фоновом потоке."""
        source = self.input_panel.get_data_source()
        if source is None:
            return

        fmt = self.output_format.currentText()

        self.run_button.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status("Running filter...")

        worker = Worker(
            run_filter,
            source,
            fmt,
            self.no_private.isChecked() or self.bogons.isChecked(),
            self.no_loopback.isChecked() or self.bogons.isChecked(),
            self.no_link_local.isChecked() or self.bogons.isChecked(),
            self.no_multicast.isChecked() or self.bogons.isChecked(),
            self.no_reserved.isChecked() or self.bogons.isChecked(),
            self.bogons.isChecked(),
            self.strict.isChecked(),
        )
        worker.signals.result.connect(self._on_filter_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_filter_result(self, result: FilterResult) -> None:
        """
        Отображает результат фильтрации.

        Args:
            result: Результат с готовой строкой formatted_text.
        """
        self._expand_output()
        self.output_panel.set_text(result.formatted_text)
        remaining = result.original_count - result.removed_count
        self.progress_panel.set_status(
            f"Done. Removed: {result.removed_count}, "
            f"Remaining: {remaining}"
        )

    def _on_error(self, error_msg: str) -> None:
        """
        Отображает сообщение об ошибке.

        Args:
            error_msg: Текст ошибки.
        """
        self.output_panel.set_text(f"Error: {error_msg}")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        """Восстанавливает интерфейс."""
        self.run_button.setEnabled(True)
        self.progress_panel.set_busy(False)

    def trigger_open(self) -> None:
        """Открывает диалог выбора файла."""
        self.input_panel.browse_button.click()

    def trigger_run(self) -> None:
        """Запускает фильтрацию."""
        if self.run_button.isEnabled():
            self.run_button.click()

    def save_settings(self) -> dict:
        """
        Сохраняет параметры вкладки.

        Returns:
            Словарь с настройками.
        """
        return {
            "no_private": self.no_private.isChecked(),
            "no_loopback": self.no_loopback.isChecked(),
            "no_link_local": self.no_link_local.isChecked(),
            "no_multicast": self.no_multicast.isChecked(),
            "no_reserved": self.no_reserved.isChecked(),
            "bogons": self.bogons.isChecked(),
            "output_format": self.output_format.currentText(),
            "strict": self.strict.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        """
        Восстанавливает параметры вкладки.

        Args:
            state: Словарь с настройками.
        """
        if not state:
            return
        self.no_private.setChecked(state.get("no_private", False))
        self.no_loopback.setChecked(state.get("no_loopback", False))
        self.no_link_local.setChecked(state.get("no_link_local", False))
        self.no_multicast.setChecked(state.get("no_multicast", False))
        self.no_reserved.setChecked(state.get("no_reserved", False))
        self.bogons.setChecked(state.get("bogons", False))
        fmt = state.get("output_format", "list")
        idx = self.output_format.findText(fmt)
        if idx >= 0:
            self.output_format.setCurrentIndex(idx)
        self.strict.setChecked(state.get("strict", False))