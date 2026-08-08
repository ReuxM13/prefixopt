"""
Exclude tab: subtract a single prefix or a whole target list from a source
list (hole punching). Supports inheritance/appending of comments to fragments.
"""


from typing import Any

from PySide6.QtWidgets import (
    QLineEdit,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QStackedWidget,
)

from .base_operation_tab import BaseOperationTab
from ..models import ExcludeResult
from ..services import run_exclude
from ..widgets.input_panel import InputPanel
from ..widgets.options_group import OptionsGroup
from ..widgets.prefix_input_widget import PrefixInputWidget
from ..widgets.comment_options import CommentAnnotationMixin
from ..workers import Worker


class ExcludeTab(BaseOperationTab, CommentAnnotationMixin):

    """Subtract networks from a source list (hole punching)."""

    def __init__(self) -> None:
        """Set up the widget, build its UI and wire up signals."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Construct and lay out all child widgets for this tab."""
        desc = QLabel(
            "Subtract one target from a source list. "
            "Target may be a single prefix or a list."
        )
        desc.setProperty("role", "description")
        desc.setWordWrap(True)
        self.control_layout.addWidget(desc)

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
        self.append_comment = QLineEdit()
        self.append_comment.setPlaceholderText("Optional comment for remaining fragments")
        self.keep_existing_comments = QCheckBox("Keep existing comments and append to the end")
        self.ipv4_only = QCheckBox("IPv4 only")
        self.ipv6_only = QCheckBox("IPv6 only")
        self.output_format = QComboBox()
        self.output_format.addItems(["list", "csv"])
        self.strict = QCheckBox("Strict mode")
        self.keep_comments.setToolTip(
            "Inherit comments from parent networks to fragments"
        )
        self.ipv4_only.setToolTip("Process only IPv4 prefixes, skip IPv6")
        self.ipv6_only.setToolTip("Process only IPv6 prefixes, skip IPv4")
        self.output_format.setToolTip(
            "Output format: one prefix per line or comma-separated"
        )
        self.strict.setToolTip(
            "Reject prefixes with incorrect subnet masks"
        )

        form = QFormLayout()
        form.addRow(self.keep_comments)
        form.addRow("Append comment:", self.append_comment)
        form.addRow(self.keep_existing_comments)
        form.addRow(self.ipv4_only)
        form.addRow(self.ipv6_only)
        form.addRow("Output format:", self.output_format)
        form.addRow(self.strict)
        options.add_layout(form)
        self.control_layout.addWidget(options)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Exclude")
        self.run_button.setProperty("primary", True)
        self.run_button.setToolTip("Ctrl+R")
        run_row.addStretch()
        run_row.addWidget(self.run_button)
        self.control_layout.addLayout(run_row)

        self._setup_splitter(self.output_panel)

        self.single_target_radio.toggled.connect(self._update_target_mode)
        self.source_input.source_changed.connect(self._update_state)
        self.keep_comments.toggled.connect(self._update_comment_options)
        self.append_comment.textChanged.connect(self._update_comment_options)
        self.single_target_widget.value_changed.connect(self._update_state)
        self.multi_target_widget.source_changed.connect(self._update_state)
        self.run_button.clicked.connect(self._run_exclude)

        self._update_target_mode()
        self._update_state()

    def _update_target_mode(self) -> None:
        if self.single_target_radio.isChecked():
            self.target_stack.setCurrentWidget(self.single_target_widget)
        else:
            self.target_stack.setCurrentWidget(self.multi_target_widget)
        self._update_state()

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

    def _update_state(self, _: Any = None) -> None:
        """Enable/disable the Run button based on current input validity."""
        source_ok = self.source_input.get_data_source() is not None
        if self.single_target_radio.isChecked():
            target_ok = self.single_target_widget.get_value() is not None
        else:
            target_ok = self.multi_target_widget.get_data_source() is not None
        self.run_button.setEnabled(source_ok and target_ok)

    def _run_exclude(self) -> None:
        """Collect options and launch the background worker."""
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
        append_comment = self.get_append_comment()
        keep_existing = self.keep_existing_comments.isChecked()
        fmt = self.output_format.currentText()

        if (keep_comments or append_comment) and fmt == "csv":
            self.output_panel.set_text(
                "Error: Cannot use comments with CSV format."
            )
            self.progress_panel.set_status("Error")
            return

        worker = Worker(
            run_exclude,
            source,
            target,
            fmt,
            keep_comments=keep_comments,
            append_comment=append_comment,
            keep_existing_comments=keep_existing,
            ipv4_only=self.ipv4_only.isChecked(),
            ipv6_only=self.ipv6_only.isChecked(),
            strict=self.strict.isChecked(),
        )
        worker.signals.result.connect(self._on_exclude_result)
        worker.signals.error.connect(self._on_error)
        self._start_worker(worker, "Excluding...")

    def _on_exclude_result(self, result: ExcludeResult) -> None:
        """Handle the exclude result event."""
        self._expand_output()
        self.output_panel.set_text(result.formatted_text)
        self.progress_panel.set_status(
            f"Done. Fragments: {result.total_count}"
        )
        result.commented_prefixes.clear()

    def trigger_open(self) -> None:
        """Programmatically open a file for this tab (used by Ctrl+O)."""
        self.source_input.browse_button.click()

    def trigger_run(self) -> None:
        """Programmatically run this tab's operation (used by Ctrl+R)."""
        if self.run_button.isEnabled():
            self.run_button.click()

    def save_settings(self) -> dict:
        """Serialise this tab's widget state for persistence."""
        return {
            "single_target": self.single_target_radio.isChecked(),
            "keep_comments": self.keep_comments.isChecked(),
            "append_comment": self.append_comment.text(),
            "keep_existing_comments": self.keep_existing_comments.isChecked(),
            "ipv4_only": self.ipv4_only.isChecked(),
            "ipv6_only": self.ipv6_only.isChecked(),
            "output_format": self.output_format.currentText(),
            "strict": self.strict.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        """Restore widget state previously saved by save_settings."""
        if not state:
            return
        if state.get("single_target", True):
            self.single_target_radio.setChecked(True)
        else:
            self.multi_target_radio.setChecked(True)
        self.keep_comments.setChecked(state.get("keep_comments", False))
        self.append_comment.setText(state.get("append_comment", ""))
        self.keep_existing_comments.setChecked(state.get("keep_existing_comments", False))
        self.ipv4_only.setChecked(state.get("ipv4_only", False))
        self.ipv6_only.setChecked(state.get("ipv6_only", False))
        fmt = state.get("output_format", "list")
        idx = self.output_format.findText(fmt)
        if idx >= 0:
            self.output_format.setCurrentIndex(idx)
        self.strict.setChecked(state.get("strict", False))