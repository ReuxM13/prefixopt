"""
Optimize tab: combines two sub-modes in nested tabs - "Optimize list" and
"Add prefix". Reuses the same output panel and comment options.
"""


from typing import Any

from PySide6.QtWidgets import (
    QLineEdit,
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
from ..widgets.comment_options import CommentAnnotationMixin
from ..workers import Worker


class OptimizeTab(BaseOperationTab, CommentAnnotationMixin):

    """Optimise (and add prefixes to) a list, with comment options."""

    def __init__(self) -> None:
        """Set up the widget, build its UI and wire up signals."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Construct and lay out all child widgets for this tab."""
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
        self.opt_append_comment = QLineEdit()
        self.opt_append_comment.setPlaceholderText("Optional comment for all output prefixes")
        self.opt_append_comment.setToolTip(
            "Append this comment to output. Existing comments are replaced unless the next option is checked."
        )
        self.opt_keep_existing_comments = QCheckBox("Keep existing comments and append to the end")
        self.opt_keep_existing_comments.setToolTip(
            "Preserve old comments and place the new comment after them"
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
        form.addRow("Append comment:", self.opt_append_comment)
        form.addRow(self.opt_keep_existing_comments)
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
        self.opt_append_comment.textChanged.connect(
            self._update_optimize_format_state
        )
        self.optimize_run_button.clicked.connect(self._run_optimize)

        self._update_optimize_state()
        self._update_optimize_format_state()

    def _build_add_mode(self) -> None:
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
        self.add_append_comment = QLineEdit()
        self.add_append_comment.setPlaceholderText("Optional comment for all output prefixes")
        self.add_append_comment.setToolTip(
            "Append this comment to output. Existing comments are replaced unless the next option is checked."
        )
        self.add_keep_existing_comments = QCheckBox("Keep existing comments and append to the end")

        self.add_format = QComboBox()
        self.add_format.addItems(["list", "csv"])
        self.add_format.setToolTip(
            "Output format: one prefix per line or comma-separated"
        )

        form = QFormLayout()
        form.addRow(self.add_keep_comments)
        form.addRow("Append comment:", self.add_append_comment)
        form.addRow(self.add_keep_existing_comments)
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
        self.add_append_comment.textChanged.connect(
            self._update_add_format_state
        )
        self.add_run_button.clicked.connect(self._run_add)

        self._update_add_state()
        self._update_add_format_state()

    def _sync_format_state(
        self,
        keep_checkbox: QCheckBox,
        format_combo: QComboBox,
        comments_active: bool = False,
    ) -> None:
        keep_comments = keep_checkbox.isChecked() or comments_active
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
        self.optimize_run_button.setEnabled(
            self.optimize_input.get_data_source() is not None
        )

    def _update_optimize_format_state(self, _: Any = None) -> None:
        keep = self.opt_keep_comments.isChecked() or bool(self.opt_append_comment.text().strip())
        self._sync_format_state(
            self.opt_keep_comments,
            self.opt_format,
            bool(self.opt_append_comment.text().strip()),
        )
        self.append_comment = self.opt_append_comment
        self.keep_existing_comments = self.opt_keep_existing_comments
        self.update_comment_options_state(
            self.opt_keep_comments.isChecked(), append_requires_keep=False
        )

    def _update_add_state(self, _: Any = None) -> None:
        self.add_run_button.setEnabled(
            self.add_input.get_data_source() is not None
            and self.add_prefix_widget.get_value() is not None
        )

    def _update_add_format_state(self, _: Any = None) -> None:
        if self.add_append_comment.text().strip() and not self.add_keep_comments.isChecked():
            self.add_keep_comments.setChecked(True)
        self._sync_format_state(
            self.add_keep_comments,
            self.add_format,
            bool(self.add_append_comment.text().strip()),
        )
        self.append_comment = self.add_append_comment
        self.keep_existing_comments = self.add_keep_existing_comments
        self.update_comment_options_state(
            self.add_keep_comments.isChecked(), append_requires_keep=False
        )

    def _run_optimize(self) -> None:
        """Collect options and launch the background worker."""
        source = self.optimize_input.get_data_source()
        if source is None:
            return

        output_format = self.opt_format.currentText()
        keep_comments = self.opt_keep_comments.isChecked()

        append_comment = self.opt_append_comment.text().strip() or None
        keep_existing = self.opt_keep_existing_comments.isChecked()
        if (keep_comments or append_comment) and output_format == "csv":
            self.output_panel.set_text(
                "Error: Cannot use comments with CSV format."
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
            append_comment,
            keep_existing,
            self.opt_strict.isChecked(),
        )
        worker.signals.result.connect(self._render_result)
        worker.signals.error.connect(self._on_error)
        self._start_worker(worker, "Running optimize...")

    def _run_add(self) -> None:
        """Collect options and launch the background worker."""
        source = self.add_input.get_data_source()
        new_prefix = self.add_prefix_widget.get_value()
        if source is None or new_prefix is None:
            return

        output_format = self.add_format.currentText()
        keep_comments = self.add_keep_comments.isChecked()

        append_comment = self.add_append_comment.text().strip() or None
        keep_existing = self.add_keep_existing_comments.isChecked()
        if (keep_comments or append_comment) and output_format == "csv":
            self.output_panel.set_text(
                "Error: Cannot use comments with CSV format."
            )
            self.progress_panel.set_status("Error")
            return

        worker = Worker(
            run_add,
            source,
            new_prefix,
            output_format,
            keep_comments,
            append_comment,
            keep_existing,
            self.opt_strict.isChecked(),
        )
        worker.signals.result.connect(self._render_result)
        worker.signals.error.connect(self._on_error)
        self._start_worker(worker, "Adding prefix...")

    def _render_result(self, result: OptimizeResult) -> None:
        self._expand_output()
        self.output_panel.set_text(result.formatted_text)
        self.progress_panel.set_status(
            f"Done. Input: {result.input_count}, "
            f"Output: {result.output_count}"
        )
        # Free the large intermediate list once it has been rendered.
        result.commented_prefixes.clear()

    def trigger_open(self) -> None:
        """Programmatically open a file for this tab (used by Ctrl+O)."""
        if self.mode_tabs.currentWidget() is self.optimize_page:
            if hasattr(self.optimize_input, "browse_button"):
                self.optimize_input.browse_button.click()
            return
        if hasattr(self.add_input, "browse_button"):
            self.add_input.browse_button.click()

    def trigger_run(self) -> None:
        """Programmatically run this tab's operation (used by Ctrl+R)."""
        if self.mode_tabs.currentWidget() is self.optimize_page:
            if self.optimize_run_button.isEnabled():
                self.optimize_run_button.click()
            return
        if self.add_run_button.isEnabled():
            self.add_run_button.click()

    def save_settings(self) -> dict:
        """Serialise this tab's widget state for persistence."""
        return {
            "mode_index": self.mode_tabs.currentIndex(),
            "opt_ipv4_only": self.opt_ipv4_only.isChecked(),
            "opt_ipv6_only": self.opt_ipv6_only.isChecked(),
            "opt_keep_comments": self.opt_keep_comments.isChecked(),
            "opt_append_comment": self.opt_append_comment.text(),
            "opt_keep_existing_comments": self.opt_keep_existing_comments.isChecked(),
            "opt_strict": self.opt_strict.isChecked(),
            "opt_format": self.opt_format.currentText(),
            "add_keep_comments": self.add_keep_comments.isChecked(),
            "add_append_comment": self.add_append_comment.text(),
            "add_keep_existing_comments": self.add_keep_existing_comments.isChecked(),
            "add_format": self.add_format.currentText(),
        }

    def load_settings(self, state: dict) -> None:
        """Restore widget state previously saved by save_settings."""
        if not state:
            return

        mode_index = state.get("mode_index", 0)
        if 0 <= mode_index < self.mode_tabs.count():
            self.mode_tabs.setCurrentIndex(mode_index)

        self.opt_append_comment.blockSignals(True)
        self.add_append_comment.blockSignals(True)
        self.opt_ipv4_only.setChecked(state.get("opt_ipv4_only", False))
        self.opt_ipv6_only.setChecked(state.get("opt_ipv6_only", False))
        self.opt_keep_comments.setChecked(
            state.get("opt_keep_comments", False)
        )
        self.opt_append_comment.setText(state.get("opt_append_comment", ""))
        self.opt_keep_existing_comments.setChecked(
            state.get("opt_keep_existing_comments", False)
        )
        self.opt_strict.setChecked(state.get("opt_strict", False))
        self.opt_append_comment.blockSignals(False)

        optimize_format = state.get("opt_format", "list")
        optimize_index = self.opt_format.findText(optimize_format)
        if optimize_index >= 0:
            self.opt_format.setCurrentIndex(optimize_index)

        self.add_keep_comments.setChecked(
            state.get("add_keep_comments", False)
        )
        self.add_append_comment.setText(state.get("add_append_comment", ""))
        self.add_keep_existing_comments.setChecked(
            state.get("add_keep_existing_comments", False)
        )
        self.add_append_comment.blockSignals(False)

        add_format = state.get("add_format", "list")
        add_index = self.add_format.findText(add_format)
        if add_index >= 0:
            self.add_format.setCurrentIndex(add_index)

        self._update_optimize_format_state()
        self._update_add_format_state()