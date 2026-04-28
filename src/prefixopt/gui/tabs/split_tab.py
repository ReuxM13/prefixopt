"""
Split tab.
"""
from PySide6.QtWidgets import QLabel, QPushButton, QHBoxLayout, QSpinBox, QFormLayout
from PySide6.QtCore import QThreadPool

from .base_operation_tab import BaseOperationTab
from ..widgets.input_panel import InputPanel
from ..widgets.options_group import OptionsGroup
from ..workers import Worker
from ..services import run_split
from ..models import SplitResult
from ..output_formatter import format_prefixes


class SplitTab(BaseOperationTab):
    def __init__(self) -> None:
        super().__init__()
        self._init_ui()
        self.threadpool = QThreadPool.globalInstance()

    def _init_ui(self) -> None:
        self.control_layout.addWidget(QLabel(
            "Split a network or a list of networks into smaller subnets."
        ))

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
        form = QFormLayout()
        form.addRow("Target prefix length:", self.target_length)
        options.add_layout(form)
        self.control_layout.addWidget(options)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Split")
        run_row.addStretch()
        run_row.addWidget(self.run_button)
        self.control_layout.addLayout(run_row)

        self._setup_splitter(self.output_panel)

        self.run_button.clicked.connect(self._run_split)
        self.input_panel.source_changed.connect(self._update_state)
        self._update_state()

    def _update_state(self, _=None) -> None:
        self.run_button.setEnabled(self.input_panel.get_data_source() is not None)

    def _run_split(self) -> None:
        source = self.input_panel.get_data_source()
        if source is None:
            return

        target_len = self.target_length.value()
        self.run_button.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status("Splitting...")

        worker = Worker(run_split, source, target_len)
        worker.signals.result.connect(self._on_split_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_split_result(self, result: SplitResult) -> None:
        text = format_prefixes(result.subnets, fmt="list")
        self.output_panel.set_text(text)
        self.progress_panel.set_status(f"Done. Generated {result.total_count} subnets")

    def _on_error(self, error_msg: str) -> None:
        self.output_panel.set_text(f"Error: {error_msg}")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.progress_panel.set_busy(False)

    def save_settings(self) -> dict:
        return {
            'target_length': self.target_length.value(),
        }

    def load_settings(self, state: dict) -> None:
        if not state:
            return
        self.target_length.setValue(int(state.get('target_length', 24)))