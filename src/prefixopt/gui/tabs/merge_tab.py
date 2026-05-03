"""
Merge tab.
"""
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QLabel, QPushButton, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLineEdit
)

from .base_operation_tab import BaseOperationTab
from ..widgets.input_panel import InputPanel
from ..widgets.options_group import OptionsGroup
from ..workers import Worker
from ..services import run_merge
from ..models import MergeResult
from ..output_formatter import format_prefixes


class MergeTab(BaseOperationTab):
    def __init__(self) -> None:
        super().__init__()
        self._init_ui()
        self.threadpool = QThreadPool.globalInstance()

    def _init_ui(self) -> None:
        self.control_layout.addWidget(QLabel(
            "Merge two sources. Supports keep-comments mode and annotation for source 1."
        ))

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
        self.append_comment.setPlaceholderText("Optional annotation for Source 1")
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
        keep = self.keep_comments.isChecked()
        self.append_comment.setEnabled(keep)
        idx = self.output_format.findText("csv")
        if idx >= 0:
            model = self.output_format.model()
            if model:
                item = model.item(idx)
                item.setEnabled(not keep)
        if keep and self.output_format.currentText() == "csv":
            self.output_format.setCurrentText("list")

    def _update_run_state(self, _=None) -> None:
        self.run_button.setEnabled(
            self.input_a.get_data_source() is not None and
            self.input_b.get_data_source() is not None
        )

    def _run_merge(self) -> None:
        source1 = self.input_a.get_data_source()
        source2 = self.input_b.get_data_source()
        if source1 is None or source2 is None:
            return

        keep_comments = self.keep_comments.isChecked()
        append_comment = self.append_comment.text().strip()
        if not append_comment:
            append_comment = None
        fmt = self.output_format.currentText()
        strict = self.strict.isChecked()

        if keep_comments and fmt == "csv":
            self.output_panel.set_text("Error: Cannot use keep-comments with CSV format.")
            return

        self.run_button.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status("Merging...")

        worker = Worker(run_merge, source1, source2, keep_comments, append_comment, strict)
        worker.signals.result.connect(self._on_merge_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_merge_result(self, result: MergeResult) -> None:
        self._expand_output()
        fmt = self.output_format.currentText()
        try:
            if result.keep_comments:
                text = format_prefixes([], fmt, commented=result.commented_prefixes)
            else:
                text = format_prefixes(result.prefixes, fmt)
            self.output_panel.set_text(text)
            self.progress_panel.set_status(f"Done. Total prefixes: {result.total_count}")
        except Exception as e:
            self.output_panel.set_text(f"Formatting error: {e}")

    def _on_error(self, error_msg: str) -> None:
        self.output_panel.set_text(f"Error: {error_msg}")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.progress_panel.set_busy(False)

    def save_settings(self) -> dict:
        return {
            'keep_comments': self.keep_comments.isChecked(),
            'append_comment': self.append_comment.text(),
            'output_format': self.output_format.currentText(),
            'strict': self.strict.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        if not state:
            return
        self.keep_comments.setChecked(state.get('keep_comments', False))
        self.append_comment.setText(state.get('append_comment', ''))
        fmt = state.get('output_format', 'list')
        idx = self.output_format.findText(fmt)
        if idx >= 0:
            self.output_format.setCurrentIndex(idx)
        self.strict.setChecked(state.get('strict', False))