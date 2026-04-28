"""
Exclude tab with worker integration.
"""
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QLabel, QPushButton, QCheckBox, QComboBox, QFormLayout, QHBoxLayout,
    QRadioButton, QButtonGroup, QStackedWidget, QWidget, QVBoxLayout
)

from .base_operation_tab import BaseOperationTab
from ..widgets.input_panel import InputPanel
from ..widgets.prefix_input_widget import PrefixInputWidget
from ..widgets.options_group import OptionsGroup
from ..workers import Worker
from ..services import run_exclude
from ..models import ExcludeResult
from ..output_formatter import format_prefixes


class ExcludeTab(BaseOperationTab):
    def __init__(self) -> None:
        super().__init__()
        self._init_ui()
        self.threadpool = QThreadPool.globalInstance()

    def _init_ui(self) -> None:
        self.control_layout.addWidget(QLabel(
            "Subtract one target from a source list. Target may be a single prefix or a list."
        ))

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
        if self.single_target_radio.isChecked():
            self.target_stack.setCurrentWidget(self.single_target_widget)
        else:
            self.target_stack.setCurrentWidget(self.multi_target_widget)
        self._update_state()

    def _update_state(self, _=None) -> None:
        source_ok = self.source_input.get_data_source() is not None
        if self.single_target_radio.isChecked():
            target_ok = self.single_target_widget.get_value() is not None
        else:
            target_ok = self.multi_target_widget.get_data_source() is not None
        self.run_button.setEnabled(source_ok and target_ok)

    def _run_exclude(self) -> None:
        source = self.source_input.get_data_source()
        if source is None:
            return

        if self.single_target_radio.isChecked():
            target = self.single_target_widget.get_value()
            if target is None:
                return
        else:
            target = self.multi_target_widget.get_data_source()
            if target is None:
                return

        keep_comments = self.keep_comments.isChecked()
        ipv4_only = self.ipv4_only.isChecked()
        ipv6_only = self.ipv6_only.isChecked()
        strict = self.strict.isChecked()
        fmt = self.output_format.currentText()

        if keep_comments and fmt == "csv":
            self.output_panel.set_text("Error: Cannot use keep-comments with CSV format.")
            return

        self.run_button.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status("Excluding...")

        worker = Worker(
            run_exclude,
            source,
            target,
            keep_comments=keep_comments,
            ipv4_only=ipv4_only,
            ipv6_only=ipv6_only,
            strict=strict
        )
        worker.signals.result.connect(self._on_exclude_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_exclude_result(self, result: ExcludeResult) -> None:
        fmt = self.output_format.currentText()
        try:
            if result.keep_comments and result.commented_prefixes:
                text = format_prefixes([], fmt, commented=result.commented_prefixes)
            else:
                text = format_prefixes(result.prefixes, fmt)
            self.output_panel.set_text(text)
            self.progress_panel.set_status(f"Done. Fragments: {result.total_count}")
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
            'single_target': self.single_target_radio.isChecked(),
            'keep_comments': self.keep_comments.isChecked(),
            'ipv4_only': self.ipv4_only.isChecked(),
            'ipv6_only': self.ipv6_only.isChecked(),
            'output_format': self.output_format.currentText(),
            'strict': self.strict.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        if not state:
            return
        if state.get('single_target', True):
            self.single_target_radio.setChecked(True)
        else:
            self.multi_target_radio.setChecked(True)
        self.keep_comments.setChecked(state.get('keep_comments', False))
        self.ipv4_only.setChecked(state.get('ipv4_only', False))
        self.ipv6_only.setChecked(state.get('ipv6_only', False))
        fmt = state.get('output_format', 'list')
        idx = self.output_format.findText(fmt)
        if idx >= 0:
            self.output_format.setCurrentIndex(idx)
        self.strict.setChecked(state.get('strict', False))