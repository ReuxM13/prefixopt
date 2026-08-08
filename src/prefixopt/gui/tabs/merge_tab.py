"""
Merge tab: combine two sources. Supports comment preservation and a Source-1
annotation via the append-comment controls.
"""


from typing import Any
from pathlib import Path

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
from ..widgets.comment_options import CommentAnnotationMixin
from ..widgets.input_panel import InputPanel
from ..widgets.options_group import OptionsGroup
from ..workers import Worker


class MergeTab(BaseOperationTab, CommentAnnotationMixin):

    """Combine two prefix lists with comment preservation/annotation."""

    def __init__(self) -> None:
        """Set up the widget, build its UI and wire up signals."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Construct and lay out all child widgets for this tab."""
        desc = QLabel(
            "Merge two prefix lists.\n"
            "- Source 1 - the NEW list. Its prefixes receive the Append "
            "comment you type below.\n"
            "- Source 2 - the OLD list. Its existing comments are kept "
            "as-is.\n"
            "To merge a new list into an old list that already has comments, "
            "paste the OLD list into Source 2 and the NEW list into Source 1."
        )
        desc.setProperty("role", "description")
        desc.setWordWrap(True)
        self.control_layout.addWidget(desc)

        self.input_a = InputPanel(
            title="Source 1 - NEW list (comment will be applied here)",
            file_label="Source 1 (NEW list)",
            text_placeholder="Paste the NEW prefixes here. They will get the Append comment below.",
        )
        self.input_b = InputPanel(
            title="Source 2 - OLD list (existing comments are preserved)",
            file_label="Source 2 (OLD list)",
            text_placeholder="Paste the OLD prefixes here. Their comments are kept unchanged.",
        )
        self.control_layout.addWidget(self.input_a)
        swap_row = QHBoxLayout()
        swap_row.addStretch()
        self.swap_button = QPushButton("⇄ Swap")
        self.swap_button.setToolTip("Swap sources (1 ↔ 2)")
        self.swap_button.clicked.connect(self._swap_sources)
        swap_row.addWidget(self.swap_button)
        swap_row.addStretch()
        self.control_layout.addLayout(swap_row)
        self.control_layout.addWidget(self.input_b)

        options = OptionsGroup("Merge options")
        self.keep_comments = QCheckBox("Keep comments")
        self.keep_comments.setToolTip(
            "Preserve line comments (#). Disables aggregation and CSV output"
        )

        self.output_format = QComboBox()
        self.output_format.addItems(["list", "csv"])
        self.output_format.setToolTip(
            "Output format: one prefix per line or comma-separated"
        )

        self.append_comment = QLineEdit()
        self.append_comment.setPlaceholderText(
            "Optional annotation for Source 1"
        )
        self.append_comment.setToolTip(
            "This comment is added to every prefix from Source 1 (the NEW list). "
            "Source 2 (the OLD list) keeps its own comments unchanged. "
            "Old Source 1 comments are replaced unless the next option is checked."
        )
        self.keep_existing_comments = QCheckBox(
            "Keep existing Source 1 comments and append to the end"
        )

        self.strict = QCheckBox("Strict mode")
        self.strict.setToolTip(
            "Reject prefixes with incorrect subnet masks"
        )

        form = QFormLayout()
        form.addRow(self.keep_comments)
        form.addRow("Append comment:", self.append_comment)
        form.addRow(self.keep_existing_comments)
        form.addRow("Output format:", self.output_format)
        form.addRow(self.strict)
        options.add_layout(form)
        self.control_layout.addWidget(options)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Merge")
        self.run_button.setProperty("primary", True)
        self.run_button.setToolTip("Ctrl+R")
        run_row.addStretch()
        run_row.addWidget(self.run_button)
        self.control_layout.addLayout(run_row)

        self._setup_splitter(self.output_panel)

        self.keep_comments.toggled.connect(self._update_options_state)
        self.append_comment.textChanged.connect(self._update_options_state)
        self.input_a.source_changed.connect(self._update_run_state)
        self.input_b.source_changed.connect(self._update_run_state)
        self.run_button.clicked.connect(self._run_merge)

        self._update_options_state()
        self._update_run_state()

    def _update_options_state(self) -> None:
        keep = self.keep_comments.isChecked()
        self.update_comment_options_state(keep, append_requires_keep=True)
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
        """Enable/disable the Run button based on current input validity."""
        self.run_button.setEnabled(
            self.input_a.get_data_source() is not None
            and self.input_b.get_data_source() is not None
        )

    def _run_merge(self) -> None:
        """Collect options and launch the background worker."""
        source1 = self.input_a.get_data_source()
        source2 = self.input_b.get_data_source()
        if source1 is None or source2 is None:
            return

        keep_comments = self.keep_comments.isChecked()
        append_comment = self.get_append_comment()
        keep_existing = self.keep_existing_comments.isChecked()
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
            keep_existing,
            strict,
        )
        worker.signals.result.connect(self._on_merge_result)
        worker.signals.error.connect(self._on_error)
        self._start_worker(worker, "Merging...")

    def _on_merge_result(self, result: MergeResult) -> None:
        """Handle the merge result event."""
        self._expand_output()
        self.output_panel.set_text(result.formatted_text)
        self.progress_panel.set_status(
            f"Done. Total prefixes: {result.total_count}"
        )
        # The large intermediate list is no longer needed once the text is
        # displayed; drop it so the garbage collector can free the networks.
        result.commented_prefixes.clear()


    def _swap_sources(self) -> None:
        state_a = self.input_a.save_state()
        state_b = self.input_b.save_state()
        self.input_a.restore_state(state_b)
        self.input_b.restore_state(state_a)
        self._update_run_state()

    def trigger_open(self) -> None:
        """Programmatically open a file for this tab (used by Ctrl+O)."""
        if self.input_a.get_data_source() is None:
            self.input_a.browse_button.click()
            return
        self.input_b.browse_button.click()

    def trigger_run(self) -> None:
        """Programmatically run this tab's operation (used by Ctrl+R)."""
        if self.run_button.isEnabled():
            self.run_button.click()

    def save_settings(self) -> dict:
        """Serialise this tab's widget state for persistence."""
        return {
            "keep_comments": self.keep_comments.isChecked(),
            "append_comment": self.append_comment.text(),
            "keep_existing_comments": self.keep_existing_comments.isChecked(),
            "output_format": self.output_format.currentText(),
            "strict": self.strict.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        """Restore widget state previously saved by save_settings."""
        if not state:
            return
        self.keep_comments.setChecked(state.get("keep_comments", False))
        self.append_comment.setText(state.get("append_comment", ""))
        self.keep_existing_comments.setChecked(state.get("keep_existing_comments", False))
        fmt = state.get("output_format", "list")
        idx = self.output_format.findText(fmt)
        if idx >= 0:
            self.output_format.setCurrentIndex(idx)
        self.strict.setChecked(state.get("strict", False))