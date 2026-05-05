"""
Вкладка оптимизации списков префиксов.

Поддерживает два режима: полная оптимизация списка
и добавление нового префикса с реоптимизацией.
Режимы визуально разделены вложенными вкладками.
"""

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .base_operation_tab import BaseOperationTab
from ..models import OptimizeResult
from ..services import run_add, run_optimize
from ..widgets.input_panel import InputPanel
from ..widgets.options_group import OptionsGroup
from ..widgets.prefix_input_widget import PrefixInputWidget
from ..workers import Worker


class OptimizeTab(BaseOperationTab):
    """Вкладка оптимизации списков префиксов и добавления нового префикса."""

    def __init__(self) -> None:
        """Инициализирует вкладку и создает элементы интерфейса."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Создает структуру вкладки с вложенными вкладками режимов."""
        desc = QLabel(
            "Optimize prefix lists or add a new prefix into an existing list."
        )
        desc.setProperty("role", "description")
        desc.setWordWrap(True)
        self.control_layout.addWidget(desc)

        self.mode_tabs = QTabWidget()
        self.mode_tabs.setDocumentMode(False)

        self._build_optimize_mode()
        self._build_add_mode()

        self.mode_tabs.addTab(self.optimize_page, "⚡ Optimize list")
        self.mode_tabs.addTab(self.add_page, "➕ Add prefix")

        self.control_layout.addWidget(self.mode_tabs)

        self._setup_splitter(self.output_panel)

    def _build_optimize_mode(self) -> None:
        """Создает страницу режима полной оптимизации."""
        self.optimize_page = QWidget()
        layout = QVBoxLayout(self.optimize_page)

        self.optimize_input = InputPanel(
            title="Source",
            file_label="Input file",
            text_placeholder="Paste prefixes here...",
        )

        options = OptionsGroup("Options")

        self.opt_ipv4_only = QCheckBox("IPv4 only")
        self.opt_ipv4_only.setToolTip(
            "Process only IPv4 prefixes, skip IPv6"
        )

        self.opt_ipv6_only = QCheckBox("IPv6 only")
        self.opt_ipv6_only.setToolTip(
            "Process only IPv6 prefixes, skip IPv4"
        )

        self.opt_keep_comments = QCheckBox("Keep comments")
        self.opt_keep_comments.setToolTip(
            "Preserve line comments (#). Disables aggregation and CSV output"
        )

        self.opt_strict = QCheckBox("Strict")
        self.opt_strict.setToolTip(
            "Reject prefixes with incorrect subnet masks "
            "(e.g., 10.0.0.1/24 → error, expected 10.0.0.0/24)"
        )

        self.opt_format = QComboBox()
        self.opt_format.addItems(["list", "csv"])
        self.opt_format.setToolTip(
            "Output format: one prefix per line or comma-separated"
        )

        form = QFormLayout()
        form.addRow(self.opt_ipv4_only)
        form.addRow(self.opt_ipv6_only)
        form.addRow(self.opt_keep_comments)
        form.addRow(self.opt_strict)
        form.addRow("Output format:", self.opt_format)

        options.add_layout(form)

        run_row = QHBoxLayout()
        self.optimize_run_button = QPushButton("Run Optimize")
        self.optimize_run_button.setProperty("primary", True)
        self.optimize_run_button.setToolTip("Ctrl+R")
        run_row.addStretch()
        run_row.addWidget(self.optimize_run_button)

        layout.addWidget(self.optimize_input)
        layout.addWidget(options)
        layout.addLayout(run_row)

        self.optimize_input.source_changed.connect(
            self._update_optimize_state
        )
        self.opt_keep_comments.toggled.connect(
            self._update_optimize_format_state
        )
        self.optimize_run_button.clicked.connect(self._run_optimize)

        self._update_optimize_state()
        self._update_optimize_format_state()

    def _build_add_mode(self) -> None:
        """Создает страницу режима добавления нового префикса."""
        self.add_page = QWidget()
        layout = QVBoxLayout(self.add_page)

        self.add_input = InputPanel(
            title="Existing list",
            file_label="Input file",
            text_placeholder="Paste existing prefixes here...",
        )

        self.add_prefix_widget = PrefixInputWidget(
            title="New prefix",
            label="Prefix to add",
            placeholder="e.g. 10.0.0.1/32",
        )

        options = OptionsGroup("Options")

        self.add_keep_comments = QCheckBox("Keep comments")
        self.add_keep_comments.setToolTip(
            "Preserve line comments (#). Disables aggregation and CSV output"
        )

        self.add_format = QComboBox()
        self.add_format.addItems(["list", "csv"])
        self.add_format.setToolTip(
            "Output format: one prefix per line or comma-separated"
        )

        form = QFormLayout()
        form.addRow(self.add_keep_comments)
        form.addRow("Output format:", self.add_format)

        options.add_layout(form)

        run_row = QHBoxLayout()
        self.add_run_button = QPushButton("▶ Run Add")
        self.add_run_button.setProperty("primary", True)
        self.add_run_button.setToolTip("Ctrl+R")
        run_row.addStretch()
        run_row.addWidget(self.add_run_button)

        layout.addWidget(self.add_input)
        layout.addWidget(self.add_prefix_widget)
        layout.addWidget(options)
        layout.addLayout(run_row)

        self.add_input.source_changed.connect(self._update_add_state)
        self.add_prefix_widget.value_changed.connect(self._update_add_state)
        self.add_keep_comments.toggled.connect(
            self._update_add_format_state
        )
        self.add_run_button.clicked.connect(self._run_add)

        self._update_add_state()
        self._update_add_format_state()

    def _sync_format_state(
        self,
        keep_checkbox: QCheckBox,
        format_combo: QComboBox,
    ) -> None:
        """
        Синхронизирует доступность форматов с режимом комментариев.

        При активном keep-comments формат CSV блокируется.
        """
        keep_comments = keep_checkbox.isChecked()
        csv_index = format_combo.findText("csv")

        if csv_index >= 0:
            model = format_combo.model()
            if model is not None:
                item = model.item(csv_index)
                if item is not None:
                    item.setEnabled(not keep_comments)

        if keep_comments and format_combo.currentText() == "csv":
            format_combo.setCurrentText("list")

    def _update_optimize_state(self, _: Any = None) -> None:
        """Обновляет доступность кнопки запуска режима оптимизации."""
        self.optimize_run_button.setEnabled(
            self.optimize_input.get_data_source() is not None
        )

    def _update_optimize_format_state(self, _: Any = None) -> None:
        """Обновляет доступность форматов для режима оптимизации."""
        self._sync_format_state(self.opt_keep_comments, self.opt_format)

    def _update_add_state(self, _: Any = None) -> None:
        """Обновляет доступность кнопки запуска режима добавления."""
        self.add_run_button.setEnabled(
            self.add_input.get_data_source() is not None
            and self.add_prefix_widget.get_value() is not None
        )

    def _update_add_format_state(self, _: Any = None) -> None:
        """Обновляет доступность форматов для режима добавления."""
        self._sync_format_state(self.add_keep_comments, self.add_format)

    def _run_optimize(self) -> None:
        """Собирает параметры и запускает оптимизацию в фоновом потоке."""
        source = self.optimize_input.get_data_source()
        if source is None:
            return

        output_format = self.opt_format.currentText()
        keep_comments = self.opt_keep_comments.isChecked()

        if keep_comments and output_format == "csv":
            self.output_panel.set_text(
                "Error: Cannot use keep-comments with CSV format."
            )
            self.progress_panel.set_status("Error")
            return

        worker = Worker(
            run_optimize,
            source,
            output_format,
            self.opt_ipv4_only.isChecked(),
            self.opt_ipv6_only.isChecked(),
            keep_comments,
            self.opt_strict.isChecked(),
        )
        worker.signals.result.connect(self._render_result)
        worker.signals.error.connect(self._on_error)
        self._start_worker(worker, "Running optimize...")

    def _run_add(self) -> None:
        """Собирает параметры и запускает добавление в фоновом потоке."""
        source = self.add_input.get_data_source()
        new_prefix = self.add_prefix_widget.get_value()
        if source is None or new_prefix is None:
            return

        output_format = self.add_format.currentText()
        keep_comments = self.add_keep_comments.isChecked()

        if keep_comments and output_format == "csv":
            self.output_panel.set_text(
                "Error: Cannot use keep-comments with CSV format."
            )
            self.progress_panel.set_status("Error")
            return

        worker = Worker(
            run_add,
            source,
            new_prefix,
            output_format,
            keep_comments,
        )
        worker.signals.result.connect(self._render_result)
        worker.signals.error.connect(self._on_error)
        self._start_worker(worker, "Adding prefix...")

    def _render_result(self, result: OptimizeResult) -> None:
        """
        Отображает результат операции.

        Args:
            result: Результат с готовой строкой formatted_text.
        """
        self._expand_output()
        self.output_panel.set_text(result.formatted_text)
        self.progress_panel.set_status(
            f"Done. Input: {result.input_count}, "
            f"Output: {result.output_count}"
        )

    def trigger_open(self) -> None:
        """Открывает диалог выбора файла для активного режима."""
        if self.mode_tabs.currentWidget() is self.optimize_page:
            if hasattr(self.optimize_input, "browse_button"):
                self.optimize_input.browse_button.click()
            return
        if hasattr(self.add_input, "browse_button"):
            self.add_input.browse_button.click()

    def trigger_run(self) -> None:
        """Запускает операцию активного режима."""
        if self.mode_tabs.currentWidget() is self.optimize_page:
            if self.optimize_run_button.isEnabled():
                self.optimize_run_button.click()
            return
        if self.add_run_button.isEnabled():
            self.add_run_button.click()

    def save_settings(self) -> dict:
        """
        Сохраняет состояние элементов управления.

        Returns:
            Словарь с параметрами обоих режимов.
        """
        return {
            "mode_index": self.mode_tabs.currentIndex(),
            "opt_ipv4_only": self.opt_ipv4_only.isChecked(),
            "opt_ipv6_only": self.opt_ipv6_only.isChecked(),
            "opt_keep_comments": self.opt_keep_comments.isChecked(),
            "opt_strict": self.opt_strict.isChecked(),
            "opt_format": self.opt_format.currentText(),
            "add_keep_comments": self.add_keep_comments.isChecked(),
            "add_format": self.add_format.currentText(),
        }

    def load_settings(self, state: dict) -> None:
        """
        Восстанавливает состояние элементов управления.

        Args:
            state: Словарь с сохраненными параметрами.
        """
        if not state:
            return

        mode_index = state.get("mode_index", 0)
        if 0 <= mode_index < self.mode_tabs.count():
            self.mode_tabs.setCurrentIndex(mode_index)

        self.opt_ipv4_only.setChecked(state.get("opt_ipv4_only", False))
        self.opt_ipv6_only.setChecked(state.get("opt_ipv6_only", False))
        self.opt_keep_comments.setChecked(
            state.get("opt_keep_comments", False)
        )
        self.opt_strict.setChecked(state.get("opt_strict", False))

        optimize_format = state.get("opt_format", "list")
        optimize_index = self.opt_format.findText(optimize_format)
        if optimize_index >= 0:
            self.opt_format.setCurrentIndex(optimize_index)

        self.add_keep_comments.setChecked(
            state.get("add_keep_comments", False)
        )

        add_format = state.get("add_format", "list")
        add_index = self.add_format.findText(add_format)
        if add_index >= 0:
            self.add_format.setCurrentIndex(add_index)