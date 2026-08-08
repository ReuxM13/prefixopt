"""
Split tab: de-aggregate each input network into subnets of a chosen prefix
length, with optional comment inheritance/annotation.
"""


from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QLineEdit,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
)

from .base_operation_tab import BaseOperationTab
from ..models import SplitResult
from ..services import run_split
from ..widgets.input_panel import InputPanel
from ..widgets.options_group import OptionsGroup
from ..widgets.comment_options import CommentAnnotationMixin
from ..workers import Worker


class SplitTab(BaseOperationTab, CommentAnnotationMixin):

    """De-aggregate networks into smaller subnets of a chosen length."""

    def __init__(self) -> None:
        """Set up the widget, build its UI and wire up signals."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Construct and lay out all child widgets for this tab."""
        desc = QLabel(
            "Split a network or a list of networks into smaller subnets."
        )
        desc.setProperty("role", "description")
        desc.setWordWrap(True)
        self.control_layout.addWidget(desc)

        self.input_panel = InputPanel(
            title="Source",
            file_label="Input file",
            text_placeholder="Paste prefixes here...",
        )
        self.control_layout.addWidget(self.input_panel)

        options = OptionsGroup("Split options")

        self.target_length = QSpinBox()
        self.target_length.setRange(0, 128)
        self.target_length.setValue(24)

        self.keep_comments = QCheckBox("Keep comments")
        self.keep_comments.setToolTip("Inherit comments from parent networks")
        self.append_comment = QLineEdit()
        self.append_comment.setPlaceholderText("Optional comment for generated subnets")
        self.keep_existing_comments = QCheckBox("Keep existing comments and append to the end")

        self.output_format = QComboBox()
        self.output_format.addItems(["list", "csv"])

        self.target_length.setToolTip(
            "Target CIDR prefix length (e.g. 24 for /24 subnets)"
        )
        self.output_format.setToolTip(
            "Output format: one prefix per line or comma-separated"
        )

        form = QFormLayout()
        form.addRow("Target prefix length:", self.target_length)
        form.addRow(self.keep_comments)
        form.addRow("Append comment:", self.append_comment)
        form.addRow(self.keep_existing_comments)
        form.addRow("Output format:", self.output_format)
        options.add_layout(form)

        self.control_layout.addWidget(options)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Split")
        self.run_button.setProperty("primary", True)
        self.run_button.setToolTip("Ctrl+R")
        run_row.addStretch()
        run_row.addWidget(self.run_button)

        self.control_layout.addLayout(run_row)

        self._setup_splitter(self.output_panel)

        self.run_button.clicked.connect(self._run_split)
        self.input_panel.source_changed.connect(self._update_state)
        self.keep_comments.toggled.connect(self._update_comment_options)
        self.append_comment.textChanged.connect(self._update_comment_options)

        self._update_state()

    def _update_state(self, _: Any = None) -> None:
        """Enable/disable the Run button based on current input validity."""
        self.run_button.setEnabled(
            self.input_panel.get_data_source() is not None
        )

    def _update_comment_options(self, _: Any = None) -> None:
        self.update_comment_options_state(
            self.keep_comments.isChecked(), append_requires_keep=False
        )
        if (self.keep_comments.isChecked() or self.append_comment.text().strip()) and self.output_format.currentText() == "csv":
            self.output_format.setCurrentText("list")
        idx = self.output_format.findText("csv")
        if idx >= 0:
            model = self.output_format.model()
            if model:
                item = model.item(idx)
                if item:
                    item.setEnabled(not (self.keep_comments.isChecked() or bool(self.append_comment.text().strip())))

    def _run_split(self) -> None:
        """Collect options and launch the background worker."""
        source = self.input_panel.get_data_source()
        if source is None:
            return

        fmt = self.output_format.currentText()
        keep_comments = self.keep_comments.isChecked()
        append_comment = self.get_append_comment()
        if (keep_comments or append_comment) and fmt == "csv":
            self.output_panel.set_text("Error: Cannot use comments with CSV format.")
            self.progress_panel.set_status("Error")
            return
        worker = Worker(
            run_split,
            source,
            self.target_length.value(),
            fmt,
            keep_comments,
            append_comment,
            self.keep_existing_comments.isChecked(),
        )
        worker.signals.result.connect(self._on_split_result)
        worker.signals.error.connect(self._on_error)
        self._start_worker(worker, "Splitting...")

    def _on_split_result(self, result: SplitResult) -> None:
        """Handle the split result event."""
        self._expand_output()
        self.output_panel.set_text(result.formatted_text)
        self.progress_panel.set_status(
            f"Done. Generated {result.total_count} subnets"
        )
        result.subnets.clear()

    def trigger_open(self) -> None:
        """Programmatically open a file for this tab (used by Ctrl+O)."""
        self.input_panel.browse_button.click()

    def trigger_run(self) -> None:
        """Programmatically run this tab's operation (used by Ctrl+R)."""
        if self.run_button.isEnabled():
            self.run_button.click()

    def save_settings(self) -> dict:
        """Serialise this tab's widget state for persistence."""
        return {
            "target_length": self.target_length.value(),
            "keep_comments": self.keep_comments.isChecked(),
            "append_comment": self.append_comment.text(),
            "keep_existing_comments": self.keep_existing_comments.isChecked(),
            "output_format": self.output_format.currentText(),
        }

    def load_settings(self, state: dict) -> None:
        """Restore widget state previously saved by save_settings."""
        if not state:
            return

        self.target_length.setValue(int(state.get("target_length", 24)))
        self.keep_comments.setChecked(state.get("keep_comments", False))
        self.append_comment.setText(state.get("append_comment", ""))
        self.keep_existing_comments.setChecked(state.get("keep_existing_comments", False))

        fmt = state.get("output_format", "list")
        idx = self.output_format.findText(fmt)
        if idx >= 0:
            self.output_format.setCurrentIndex(idx)