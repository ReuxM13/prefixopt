"""
Diff tab with worker integration and color output.
"""
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QLabel, QPushButton, QCheckBox, QComboBox, QFormLayout, QHBoxLayout
)

from .base_operation_tab import BaseOperationTab
from ..widgets.input_panel import InputPanel
from ..widgets.options_group import OptionsGroup
from ..workers import Worker
from ..services import run_diff
from ..models import DiffReport


class DiffTab(BaseOperationTab):
    """
    Compare two sources and show added, removed and unchanged prefixes.
    """

    def __init__(self) -> None:
        super().__init__()
        self._init_ui()
        self.threadpool = QThreadPool.globalInstance()

    def _init_ui(self) -> None:
        self.control_layout.addWidget(QLabel(
            "Compare two sources and show added, removed and unchanged prefixes."
        ))

        self.new_input = InputPanel(
            title="New source",
            file_label="New file",
            text_placeholder="Paste new source prefixes here...",
        )
        self.old_input = InputPanel(
            title="Old source",
            file_label="Old file",
            text_placeholder="Paste old source prefixes here...",
        )
        self.control_layout.addWidget(self.new_input)
        self.control_layout.addWidget(self.old_input)

        options = OptionsGroup("Diff options")
        self.mode = QComboBox()
        self.mode.addItems(["changes", "added", "removed", "unchanged", "all"])
        self.summary_only = QCheckBox("Summary only")
        self.ipv4_only = QCheckBox("IPv4 only")
        self.ipv6_only = QCheckBox("IPv6 only")
        self.strict = QCheckBox("Strict mode")

        form = QFormLayout()
        form.addRow("Mode:", self.mode)
        form.addRow(self.summary_only)
        form.addRow(self.ipv4_only)
        form.addRow(self.ipv6_only)
        form.addRow(self.strict)
        options.add_layout(form)
        self.control_layout.addWidget(options)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Diff")
        run_row.addStretch()
        run_row.addWidget(self.run_button)
        self.control_layout.addLayout(run_row)

        self._setup_splitter(self.output_panel)

        self.new_input.source_changed.connect(self._update_state)
        self.old_input.source_changed.connect(self._update_state)
        self.run_button.clicked.connect(self._run_diff)
        self._update_state()

    def _update_state(self, _=None) -> None:
        self.run_button.setEnabled(
            self.new_input.get_data_source() is not None and
            self.old_input.get_data_source() is not None
        )

    def _run_diff(self) -> None:
        new_source = self.new_input.get_data_source()
        old_source = self.old_input.get_data_source()
        if new_source is None or old_source is None:
            return

        ipv4_only = self.ipv4_only.isChecked()
        ipv6_only = self.ipv6_only.isChecked()
        strict = self.strict.isChecked()

        self.run_button.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status("Calculating diff...")

        worker = Worker(
            run_diff,
            new_source,
            old_source,
            ipv4_only=ipv4_only,
            ipv6_only=ipv6_only,
            strict=strict
        )
        worker.signals.result.connect(self._on_diff_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_diff_result(self, result: DiffReport) -> None:
        mode = self.mode.currentText()
        summary = self.summary_only.isChecked()

        show_added = mode in ("changes", "added", "all")
        show_removed = mode in ("changes", "removed", "all")
        show_unchanged = mode in ("unchanged", "all")

        if summary:
            lines = []
            if show_added:
                lines.append(f"<b>Added:</b> {len(result.added)}<br>")
            if show_removed:
                lines.append(f"<b>Removed:</b> {len(result.removed)}<br>")
            if show_unchanged:
                lines.append(f"<b>Unchanged:</b> {len(result.unchanged)}<br>")
            self.output_panel.set_html("".join(lines))
        else:
            html_parts = ['<html><body style="font-family: Consolas, monospace;">']
            if show_added and result.added:
                html_parts.append(f'<p><b style="color:green;">+++ Added ({len(result.added)}):</b></p>')
                for net in result.added:
                    html_parts.append(f'<span style="color:green;">+ {net}</span><br>')
                html_parts.append('<br>')
            if show_removed and result.removed:
                html_parts.append(f'<p><b style="color:red;">--- Removed ({len(result.removed)}):</b></p>')
                for net in result.removed:
                    html_parts.append(f'<span style="color:red;">- {net}</span><br>')
                html_parts.append('<br>')
            if show_unchanged and result.unchanged:
                html_parts.append(f'<p><b style="color:blue;">=== Unchanged ({len(result.unchanged)}):</b></p>')
                for net in result.unchanged:
                    html_parts.append(f'<span style="color:blue;">= {net}</span><br>')
                html_parts.append('<br>')
            if not html_parts:
                html_parts.append('No differences in selected mode.')
            html_parts.append('</body></html>')
            self.output_panel.set_html("".join(html_parts))

        self.progress_panel.set_status(
            f"Done. Added: {len(result.added)}, Removed: {len(result.removed)}, Unchanged: {len(result.unchanged)}"
        )

    def _on_error(self, error_msg: str) -> None:
        self.output_panel.set_text(f"Error: {error_msg}")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.progress_panel.set_busy(False)

    def save_settings(self) -> dict:
        return {
            'mode': self.mode.currentText(),
            'summary_only': self.summary_only.isChecked(),
            'ipv4_only': self.ipv4_only.isChecked(),
            'ipv6_only': self.ipv6_only.isChecked(),
            'strict': self.strict.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        if not state:
            return
        mode = state.get('mode', 'changes')
        idx = self.mode.findText(mode)
        if idx >= 0:
            self.mode.setCurrentIndex(idx)
        self.summary_only.setChecked(state.get('summary_only', False))
        self.ipv4_only.setChecked(state.get('ipv4_only', False))
        self.ipv6_only.setChecked(state.get('ipv6_only', False))
        self.strict.setChecked(state.get('strict', False))