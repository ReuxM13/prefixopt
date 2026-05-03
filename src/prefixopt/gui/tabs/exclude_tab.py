"""
Вкладка вычитания префиксов (hole punching).
"""

from typing import Any

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .base_operation_tab import BaseOperationTab
from ..models import ExcludeResult
from ..services import run_exclude
from ..widgets.input_panel import InputPanel
from ..widgets.options_group import OptionsGroup
from ..widgets.prefix_input_widget import PrefixInputWidget
from ..workers import Worker


class ExcludeTab(BaseOperationTab):
    """Вкладка вычитания префиксов из исходного списка."""

    def __init__(self) -> None:
        """Инициализирует вкладку и создает элементы интерфейса."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Создает структуру вкладки."""
        self.control_layout.addWidget(
            QLabel(
                "Subtract one target from a source list. "
                "Target may be a single prefix or a list."
            )
        )

        self.source_input = InputPanel(
            title="Source",
            file_label="Source file",
            text_placeholder="Paste source prefixes here...",
        )
        self.control_layout.addWidget(self.source_input)

        target_mode_group = OptionsGroup("Target mode")
        target_mode_row = QHBoxLayout()
        self.single_target_radio = QRadioButton("Single prefix")
        self.multi_target_radio = QRadioButton("File / Text")
        self.single_target_radio.setChecked(True)

        self.target_mode_buttons = QButtonGroup(self)
        self.target_mode_buttons.addButton(self.single_target_radio)
        self.target_mode_buttons.addButton(self.multi_target_radio)
        target_mode_row.addWidget(self.single_target_radio)
        target_mode_row.addWidget(self.multi_target_radio)
        target_mode_row.addStretch()
        target_mode_group.add_layout(target_mode_row)
        self.control_layout.addWidget(target_mode_group)

        self.target_stack = QStackedWidget()
        self.single_target_widget = PrefixInputWidget(
            title="Target prefix",
            label="Prefix to exclude",
            placeholder="e.g. 10.0.0.1/32",
        )
        self.multi_target_widget = InputPanel(
            title="Target list",
            file_label="Target file",
            text_placeholder="Paste prefixes to exclude here...",
        )
        self.target_stack.addWidget(self.single_target_widget)
        self.target_stack.addWidget(self.multi_target_widget)
        self.control_layout.addWidget(self.target_stack)

        options = OptionsGroup("Exclude options")
        self.keep_comments = QCheckBox("Keep comments")
        self.ipv4_only = QCheckBox("IPv4 only")
        self.ipv6_only = QCheckBox("IPv6 only")
        self.output_format = QComboBox()
        self.output_format.addItems(["list", "csv"])
        self.strict = QCheckBox("Strict mode")

        form = QFormLayout()
        form.addRow(self.keep_comments)
        form.addRow(self.ipv4_only)
        form.addRow(self.ipv6_only)
        form.addRow("Output format:", self.output_format)
        form.addRow(self.strict)
        options.add_layout(form)
        self.control_layout.addWidget(options)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Exclude")
        self.run_button.setProperty("primary", True)
        run_row.addStretch()
        run_row.addWidget(self.run_button)
        self.control_layout.addLayout(run_row)

        self._setup_splitter(self.output_panel)

        self.single_target_radio.toggled.connect(self._update_target_mode)
        self.source_input.source_changed.connect(self._update_state)
        self.single_target_widget.value_changed.connect(self._update_state)
        self.multi_target_widget.source_changed.connect(self._update_state)
        self.run_button.clicked.connect(self._run_exclude)

        self._update_target_mode()
        self._update_state()

    def _update_target_mode(self) -> None:
        """Переключает виджет ввода цели."""
        if self.single_target_radio.isChecked():
            self.target_stack.setCurrentWidget(self.single_target_widget)
        else:
            self.target_stack.setCurrentWidget(self.multi_target_widget)
        self._update_state()

    def _update_state(self, _: Any = None) -> None:
        """Обновляет доступность кнопки запуска."""
        source_ok = self.source_input.get_data_source() is not None
        if self.single_target_radio.isChecked():
            target_ok = self.single_target_widget.get_value() is not None
        else:
            target_ok = self.multi_target_widget.get_data_source() is not None
        self.run_button.setEnabled(source_ok and target_ok)

    def _run_exclude(self) -> None:
        """Собирает параметры и запускает вычитание в фоновом потоке."""
        source = self.source_input.get_data_source()
        if source is None:
            return

        if self.single_target_radio.isChecked():
            target = self.single_target_widget.get_value()
        else:
            target = self.multi_target_widget.get_data_source()

        if target is None:
            return

        keep_comments = self.keep_comments.isChecked()
        fmt = self.output_format.currentText()

        if keep_comments and fmt == "csv":
            self.output_panel.set_text(
                "Error: Cannot use keep-comments with CSV format."
            )
            self.progress_panel.set_status("Error")
            return

        self._set_running_state("Excluding...")

        worker = Worker(
            run_exclude,
            source,
            target,
            fmt,
            keep_comments=keep_comments,
            ipv4_only=self.ipv4_only.isChecked(),
            ipv6_only=self.ipv6_only.isChecked(),
            strict=self.strict.isChecked(),
        )
        worker.signals.result.connect(self._on_exclude_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_exclude_result(self, result: ExcludeResult) -> None:
        """
        Отображает результат вычитания.

        Args:
            result: Результат с готовой строкой formatted_text.
        """
        self._expand_output()
        self.output_panel.set_text(result.formatted_text)
        self.progress_panel.set_status(
            f"Done. Fragments: {result.total_count}"
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
        self._restore_idle_state()

    def trigger_open(self) -> None:
        """Открывает диалог выбора файла для источника."""
        self.source_input.browse_button.click()

    def trigger_run(self) -> None:
        """Запускает вычитание."""
        if self.run_button.isEnabled():
            self.run_button.click()

    def save_settings(self) -> dict:
        """
        Сохраняет параметры вкладки.

        Returns:
            Словарь с настройками.
        """
        return {
            "single_target": self.single_target_radio.isChecked(),
            "keep_comments": self.keep_comments.isChecked(),
            "ipv4_only": self.ipv4_only.isChecked(),
            "ipv6_only": self.ipv6_only.isChecked(),
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
        if state.get("single_target", True):
            self.single_target_radio.setChecked(True)
        else:
            self.multi_target_radio.setChecked(True)
        self.keep_comments.setChecked(state.get("keep_comments", False))
        self.ipv4_only.setChecked(state.get("ipv4_only", False))
        self.ipv6_only.setChecked(state.get("ipv6_only", False))
        fmt = state.get("output_format", "list")
        idx = self.output_format.findText(fmt)
        if idx >= 0:
            self.output_format.setCurrentIndex(idx)
        self.strict.setChecked(state.get("strict", False))