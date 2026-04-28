"""
Optimize tab with two modes: Optimize list and Add prefix.
"""
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QLabel, QPushButton, QCheckBox, QComboBox, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QWidget, QFormLayout, QRadioButton, QButtonGroup
)

from .base_operation_tab import BaseOperationTab
from ..widgets.input_panel import InputPanel
from ..widgets.prefix_input_widget import PrefixInputWidget
from ..widgets.options_group import OptionsGroup
from ..workers import Worker
from ..services import run_optimize, run_add
from ..models import OptimizeResult
from ..output_formatter import format_prefixes


class OptimizeTab(BaseOperationTab):
    def __init__(self) -> None:
        super().__init__()
        self._init_ui()
        self.threadpool = QThreadPool.globalInstance()

    def _init_ui(self) -> None:
        self.control_layout.addWidget(QLabel(
            "Optimize prefix lists or add a new prefix into an existing list."
        ))

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
        if self.optimize_radio.isChecked():
            self.mode_stack.setCurrentWidget(self.optimize_page)
        else:
            self.mode_stack.setCurrentWidget(self.add_page)

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

    def _update_optimize_state(self, _=None) -> None:
        self.optimize_run_button.setEnabled(self.optimize_input.get_data_source() is not None)

    def _update_optimize_format_state(self, _=None) -> None:
        keep = self.opt_keep_comments.isChecked()
        idx = self.opt_format.findText("csv")
        if idx >= 0:
            model = self.opt_format.model()
            if model:
                item = model.item(idx)
                item.setEnabled(not keep)
        if keep and self.opt_format.currentText() == "csv":
            self.opt_format.setCurrentText("list")

    def _run_optimize(self) -> None:
        source = self.optimize_input.get_data_source()
        if source is None:
            return

        ipv4_only = self.opt_ipv4_only.isChecked()
        ipv6_only = self.opt_ipv6_only.isChecked()
        keep_comments = self.opt_keep_comments.isChecked()
        strict = self.opt_strict.isChecked()
        fmt = self.opt_format.currentText()

        if keep_comments and fmt == "csv":
            self.output_panel.set_text("Error: Cannot use keep-comments with CSV format.")
            return

        self.optimize_run_button.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status("Running optimize...")

        worker = Worker(run_optimize, source, ipv4_only, ipv6_only, keep_comments, strict)
        worker.signals.result.connect(self._on_optimize_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_optimize_result(self, result: OptimizeResult) -> None:
        fmt = self.opt_format.currentText()
        try:
            if result.keep_comments:
                text = format_prefixes([], fmt, commented=result.commented_prefixes)
            else:
                text = format_prefixes(result.prefixes, fmt)
            self.output_panel.set_text(text)
            self.progress_panel.set_status(
                f"Done. Input: {result.input_count}, Output: {result.output_count}"
            )
        except Exception as e:
            self.output_panel.set_text(f"Formatting error: {e}")

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

    def _update_add_state(self, _=None) -> None:
        self.add_run_button.setEnabled(
            self.add_input.get_data_source() is not None and
            self.add_prefix_widget.get_value() is not None
        )

    def _update_add_format_state(self, _=None) -> None:
        keep = self.add_keep_comments.isChecked()
        idx = self.add_format.findText("csv")
        if idx >= 0:
            model = self.add_format.model()
            if model:
                item = model.item(idx)
                item.setEnabled(not keep)
        if keep and self.add_format.currentText() == "csv":
            self.add_format.setCurrentText("list")

    def _run_add(self) -> None:
        source = self.add_input.get_data_source()
        new_prefix = self.add_prefix_widget.get_value()
        if source is None or new_prefix is None:
            return

        keep_comments = self.add_keep_comments.isChecked()
        fmt = self.add_format.currentText()

        if keep_comments and fmt == "csv":
            self.output_panel.set_text("Error: Cannot use keep-comments with CSV format.")
            return

        self.add_run_button.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status("Adding prefix...")

        worker = Worker(run_add, source, new_prefix, keep_comments)
        worker.signals.result.connect(self._on_add_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_add_result(self, result: OptimizeResult) -> None:
        fmt = self.add_format.currentText()
        try:
            if result.keep_comments:
                text = format_prefixes([], fmt, commented=result.commented_prefixes)
            else:
                text = format_prefixes(result.prefixes, fmt)
            self.output_panel.set_text(text)
            self.progress_panel.set_status(
                f"Done. Input: {result.input_count}, Output: {result.output_count}"
            )
        except Exception as e:
            self.output_panel.set_text(f"Formatting error: {e}")

    def _on_error(self, error_msg: str) -> None:
        self.output_panel.set_text(f"Error: {error_msg}")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        if self.optimize_radio.isChecked():
            self.optimize_run_button.setEnabled(True)
        else:
            self.add_run_button.setEnabled(True)
        self.progress_panel.set_busy(False)

    def save_settings(self) -> dict:
        return {
            'mode': 'optimize' if self.optimize_radio.isChecked() else 'add',
            'opt_ipv4_only': self.opt_ipv4_only.isChecked(),
            'opt_ipv6_only': self.opt_ipv6_only.isChecked(),
            'opt_keep_comments': self.opt_keep_comments.isChecked(),
            'opt_strict': self.opt_strict.isChecked(),
            'opt_format': self.opt_format.currentText(),
            'add_keep_comments': self.add_keep_comments.isChecked(),
            'add_format': self.add_format.currentText(),
        }

    def load_settings(self, state: dict) -> None:
        if not state:
            return
        mode = state.get('mode', 'optimize')
        if mode == 'add':
            self.add_radio.setChecked(True)
        else:
            self.optimize_radio.setChecked(True)
        self.opt_ipv4_only.setChecked(state.get('opt_ipv4_only', False))
        self.opt_ipv6_only.setChecked(state.get('opt_ipv6_only', False))
        self.opt_keep_comments.setChecked(state.get('opt_keep_comments', False))
        self.opt_strict.setChecked(state.get('opt_strict', False))
        opt_fmt = state.get('opt_format', 'list')
        idx = self.opt_format.findText(opt_fmt)
        if idx >= 0:
            self.opt_format.setCurrentIndex(idx)
        self.add_keep_comments.setChecked(state.get('add_keep_comments', False))
        add_fmt = state.get('add_format', 'list')
        idx2 = self.add_format.findText(add_fmt)
        if idx2 >= 0:
            self.add_format.setCurrentIndex(idx2)