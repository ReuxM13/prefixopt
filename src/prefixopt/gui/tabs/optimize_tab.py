"""
Вкладка графического интерфейса для выполнения операций оптимизации.

Поддерживает два режима работы:
- оптимизация списка префиксов (агрегация, удаление дубликатов, вложенных);
- добавление нового префикса в существующий список с последующей реоптимизацией.
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
        """Создает структуру вкладки: переключатель режимов, стек страниц, сплиттер."""
        self.control_layout.addWidget(
            QLabel(
                "Optimize prefix lists or add a new prefix into an existing list."
            )
        )

        mode_row = QHBoxLayout()

        self.optimize_radio = QRadioButton("Optimize list")
        self.add_radio = QRadioButton("Add prefix")
        self.optimize_radio.setChecked(True)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.optimize_radio)
        self.mode_group.addButton(self.add_radio)

        mode_row.addWidget(self.optimize_radio)
        mode_row.addWidget(self.add_radio)
        mode_row.addStretch()

        self.control_layout.addLayout(mode_row)

        self.mode_stack = QStackedWidget()
        self.control_layout.addWidget(self.mode_stack)

        self._build_optimize_mode()
        self._build_add_mode()
        self._setup_splitter(self.output_panel)

        self.optimize_radio.toggled.connect(self._switch_mode)
        self._switch_mode()

    def _switch_mode(self) -> None:
        """Переключает активную страницу в стеке режимов."""
        if self.optimize_radio.isChecked():
            self.mode_stack.setCurrentWidget(self.optimize_page)
            return
        self.mode_stack.setCurrentWidget(self.add_page)

    def _build_optimize_mode(self) -> None:
        """Создает страницу режима полной оптимизации списка."""
        self.optimize_page = QWidget()
        layout = QVBoxLayout(self.optimize_page)

        self.optimize_input = InputPanel(
            title="Source",
            file_label="Input file",
            text_placeholder="Paste prefixes here...",
        )

        options = OptionsGroup("Options")

        self.opt_ipv4_only = QCheckBox("IPv4 only")
        self.opt_ipv6_only = QCheckBox("IPv6 only")
        self.opt_keep_comments = QCheckBox("Keep comments")
        self.opt_strict = QCheckBox("Strict")

        self.opt_format = QComboBox()
        self.opt_format.addItems(["list", "csv"])

        form = QFormLayout()
        form.addRow(self.opt_ipv4_only)
        form.addRow(self.opt_ipv6_only)
        form.addRow(self.opt_keep_comments)
        form.addRow(self.opt_strict)
        form.addRow("Output format:", self.opt_format)

        options.add_layout(form)

        run_row = QHBoxLayout()
        self.optimize_run_button = QPushButton("Run Optimize")
        run_row.addStretch()
        run_row.addWidget(self.optimize_run_button)

        layout.addWidget(self.optimize_input)
        layout.addWidget(options)
        layout.addLayout(run_row)

        self.mode_stack.addWidget(self.optimize_page)

        self.optimize_input.source_changed.connect(self._update_optimize_state)
        self.opt_keep_comments.toggled.connect(self._update_optimize_format_state)
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

        self.add_format = QComboBox()
        self.add_format.addItems(["list", "csv"])

        form = QFormLayout()
        form.addRow(self.add_keep_comments)
        form.addRow("Output format:", self.add_format)

        options.add_layout(form)

        run_row = QHBoxLayout()
        self.add_run_button = QPushButton("Run Add")
        run_row.addStretch()
        run_row.addWidget(self.add_run_button)

        layout.addWidget(self.add_input)
        layout.addWidget(self.add_prefix_widget)
        layout.addWidget(options)
        layout.addLayout(run_row)

        self.mode_stack.addWidget(self.add_page)

        self.add_input.source_changed.connect(self._update_add_state)
        self.add_prefix_widget.value_changed.connect(self._update_add_state)
        self.add_keep_comments.toggled.connect(self._update_add_format_state)
        self.add_run_button.clicked.connect(self._run_add)

        self._update_add_state()
        self._update_add_format_state()

    def _sync_format_state(
        self,
        keep_checkbox: QCheckBox,
        format_combo: QComboBox,
    ) -> None:
        """
        Синхронизирует доступность форматов с режимом сохранения комментариев.

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

    def _set_running_state(self, status_text: str) -> None:
        """
        Переводит вкладку в состояние выполнения.

        Блокирует кнопки запуска и переключатели режимов.
        """
        self.optimize_run_button.setEnabled(False)
        self.add_run_button.setEnabled(False)
        self.optimize_radio.setEnabled(False)
        self.add_radio.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status(status_text)

    def _restore_idle_state(self) -> None:
        """Восстанавливает доступность элементов управления после завершения задачи."""
        self.optimize_radio.setEnabled(True)
        self.add_radio.setEnabled(True)
        self.progress_panel.set_busy(False)
        self._update_optimize_state()
        self._update_add_state()

    def _run_optimize(self) -> None:
        """Собирает параметры и запускает задачу оптимизации в фоновом потоке."""
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

        self._set_running_state("Running optimize...")

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
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _run_add(self) -> None:
        """Собирает параметры и запускает задачу добавления в фоновом потоке."""
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

        self._set_running_state("Adding prefix...")

        worker = Worker(
            run_add,
            source,
            new_prefix,
            output_format,
            keep_comments,
        )
        worker.signals.result.connect(self._render_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _render_result(self, result: OptimizeResult) -> None:
        """
        Отображает предварительно отформатированный результат.

        Args:
            result: Результат с готовой строкой formatted_text.
        """
        self._expand_output()
        self.output_panel.set_text(result.formatted_text)
        self.progress_panel.set_status(
            f"Done. Input: {result.input_count}, Output: {result.output_count}"
        )

    def _on_error(self, error_msg: str) -> None:
        """
        Отображает сообщение об ошибке фоновой задачи.

        Args:
            error_msg: Текст ошибки.
        """
        self.output_panel.set_text(f"Error: {error_msg}")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        """Восстанавливает интерфейс после завершения задачи."""
        self._restore_idle_state()

    def trigger_open(self) -> None:
        """Открывает диалог выбора файла для активного режима."""
        if self.optimize_radio.isChecked():
            if hasattr(self.optimize_input, "browse_button"):
                self.optimize_input.browse_button.click()
            return
        if hasattr(self.add_input, "browse_button"):
            self.add_input.browse_button.click()

    def trigger_run(self) -> None:
        """Запускает операцию активного режима."""
        if self.optimize_radio.isChecked():
            if self.optimize_run_button.isEnabled():
                self.optimize_run_button.click()
            return
        if self.add_run_button.isEnabled():
            self.add_run_button.click()

    def save_settings(self) -> dict:
        """
        Сохраняет состояние элементов управления вкладки.

        Returns:
            Словарь с параметрами обоих режимов.
        """
        return {
            "mode": "optimize" if self.optimize_radio.isChecked() else "add",
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
        Восстанавливает состояние элементов управления из словаря.

        Args:
            state: Словарь с сохраненными параметрами.
        """
        if not state:
            return

        mode = state.get("mode", "optimize")
        if mode == "add":
            self.add_radio.setChecked(True)
        else:
            self.optimize_radio.setChecked(True)

        self.opt_ipv4_only.setChecked(state.get("opt_ipv4_only", False))
        self.opt_ipv6_only.setChecked(state.get("opt_ipv6_only", False))
        self.opt_keep_comments.setChecked(state.get("opt_keep_comments", False))
        self.opt_strict.setChecked(state.get("opt_strict", False))

        optimize_format = state.get("opt_format", "list")
        optimize_index = self.opt_format.findText(optimize_format)
        if optimize_index >= 0:
            self.opt_format.setCurrentIndex(optimize_index)

        self.add_keep_comments.setChecked(state.get("add_keep_comments", False))

        add_format = state.get("add_format", "list")
        add_index = self.add_format.findText(add_format)
        if add_index >= 0:
            self.add_format.setCurrentIndex(add_index)