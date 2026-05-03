"""
Вкладка слияния двух списков префиксов.
"""

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from .base_operation_tab import BaseOperationTab
from ..models import MergeResult
from ..services import run_merge
from ..widgets.input_panel import InputPanel
from ..widgets.options_group import OptionsGroup
from ..workers import Worker


class MergeTab(BaseOperationTab):
    """Вкладка слияния двух источников."""

    def __init__(self) -> None:
        """Инициализирует вкладку и создает элементы интерфейса."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Создает структуру вкладки."""
        self.control_layout.addWidget(
            QLabel(
                "Merge two sources. Supports keep-comments mode "
                "and annotation for source 1."
            )
        )

        self.input_a = InputPanel(
            title="Source 1",
            file_label="Source 1 file",
            text_placeholder="Paste source 1 prefixes here...",
        )
        self.input_b = InputPanel(
            title="Source 2",
            file_label="Source 2 file",
            text_placeholder="Paste source 2 prefixes here...",
        )
        self.control_layout.addWidget(self.input_a)
        self.control_layout.addWidget(self.input_b)

        options = OptionsGroup("Merge options")
        self.keep_comments = QCheckBox("Keep comments")
        self.output_format = QComboBox()
        self.output_format.addItems(["list", "csv"])
        self.append_comment = QLineEdit()
        self.append_comment.setPlaceholderText(
            "Optional annotation for Source 1"
        )
        self.strict = QCheckBox("Strict mode")

        form = QFormLayout()
        form.addRow(self.keep_comments)
        form.addRow("Append comment:", self.append_comment)
        form.addRow("Output format:", self.output_format)
        form.addRow(self.strict)
        options.add_layout(form)
        self.control_layout.addWidget(options)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Merge")
        self.run_button.setProperty("primary", True)
        run_row.addStretch()
        run_row.addWidget(self.run_button)
        self.control_layout.addLayout(run_row)

        self._setup_splitter(self.output_panel)

        self.keep_comments.toggled.connect(self._update_options_state)
        self.input_a.source_changed.connect(self._update_run_state)
        self.input_b.source_changed.connect(self._update_run_state)
        self.run_button.clicked.connect(self._run_merge)

        self._update_options_state()
        self._update_run_state()

    def _update_options_state(self) -> None:
        """Синхронизирует доступность опций с режимом комментариев."""
        keep = self.keep_comments.isChecked()
        self.append_comment.setEnabled(keep)
        idx = self.output_format.findText("csv")
        if idx >= 0:
            model = self.output_format.model()
            if model:
                item = model.item(idx)
                if item:
                    item.setEnabled(not keep)
        if keep and self.output_format.currentText() == "csv":
            self.output_format.setCurrentText("list")

    def _update_run_state(self, _: Any = None) -> None:
        """Обновляет доступность кнопки запуска."""
        self.run_button.setEnabled(
            self.input_a.get_data_source() is not None
            and self.input_b.get_data_source() is not None
        )

    def _run_merge(self) -> None:
        """Собирает параметры и запускает слияние в фоновом потоке."""
        source1 = self.input_a.get_data_source()
        source2 = self.input_b.get_data_source()
        if source1 is None or source2 is None:
            return

        keep_comments = self.keep_comments.isChecked()
        append_comment = self.append_comment.text().strip() or None
        fmt = self.output_format.currentText()
        strict = self.strict.isChecked()

        if keep_comments and fmt == "csv":
            self.output_panel.set_text(
                "Error: Cannot use keep-comments with CSV format."
            )
            self.progress_panel.set_status("Error")
            return

        worker = Worker(
            run_merge,
            source1,
            source2,
            fmt,
            keep_comments,
            append_comment,
            strict,
        )
        worker.signals.result.connect(self._on_merge_result)
        worker.signals.error.connect(self._on_error)
        # worker.signals.finished.connect(self._on_finished)
        self._start_worker(worker, "...")

    def _on_merge_result(self, result: MergeResult) -> None:
        """
        Отображает результат слияния.

        Args:
            result: Результат с готовой строкой formatted_text.
        """
        self._expand_output()
        self.output_panel.set_text(result.formatted_text)
        self.progress_panel.set_status(
            f"Done. Total prefixes: {result.total_count}"
        )



    def trigger_open(self) -> None:
        """Открывает диалог выбора файла для первого незаполненного источника."""
        if self.input_a.get_data_source() is None:
            self.input_a.browse_button.click()
            return
        self.input_b.browse_button.click()

    def trigger_run(self) -> None:
        """Запускает слияние."""
        if self.run_button.isEnabled():
            self.run_button.click()

    def save_settings(self) -> dict:
        """
        Сохраняет параметры вкладки.

        Returns:
            Словарь с настройками.
        """
        return {
            "keep_comments": self.keep_comments.isChecked(),
            "append_comment": self.append_comment.text(),
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
        self.keep_comments.setChecked(state.get("keep_comments", False))
        self.append_comment.setText(state.get("append_comment", ""))
        fmt = state.get("output_format", "list")
        idx = self.output_format.findText(fmt)
        if idx >= 0:
            self.output_format.setCurrentIndex(idx)
        self.strict.setChecked(state.get("strict", False))