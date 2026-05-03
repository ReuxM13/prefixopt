"""
Check tab with split output.
"""
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QLabel, QPushButton, QHBoxLayout

from .base_operation_tab import BaseOperationTab
from ..widgets.input_panel import InputPanel
from ..widgets.prefix_input_widget import PrefixInputWidget
from ..widgets.split_output_panel import SplitOutputPanel
from ..workers import Worker
from ..services import run_check
from ..models import CheckResult
from ..output_formatter import format_prefixes


class CheckTab(BaseOperationTab):
    def __init__(self) -> None:
        super().__init__()
        self._init_ui()
        self.threadpool = QThreadPool.globalInstance()

    def _init_ui(self) -> None:
        self.control_layout.addWidget(QLabel(
            "Check whether an IP address or subnet is contained in the source list."
        ))

        self.target_input = PrefixInputWidget(
            title="Target",
            label="IP address or prefix",
            placeholder="e.g. 10.1.1.1 or 10.0.0.0/24",
        )
        self.control_layout.addWidget(self.target_input)

        self.source_input = InputPanel(
            title="Source",
            file_label="Input file",
            text_placeholder="Paste prefixes here...",
        )
        self.control_layout.addWidget(self.source_input)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Check")
        run_row.addStretch()
        run_row.addWidget(self.run_button)
        self.control_layout.addLayout(run_row)

        self.split_output = SplitOutputPanel(
            report_title="Check result",
            output_title="Output (containing networks)"
        )
        self._setup_splitter(self.split_output)

        self.target_input.value_changed.connect(self._update_state)
        self.source_input.source_changed.connect(self._update_state)
        self.run_button.clicked.connect(self._run_check)

        self._update_state()

    def _update_state(self, _=None) -> None:
        self.run_button.setEnabled(
            self.target_input.get_value() is not None and
            self.source_input.get_data_source() is not None
        )

    def _run_check(self) -> None:
        target = self.target_input.get_value()
        source = self.source_input.get_data_source()
        if target is None or source is None:
            return

        self.run_button.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status("Checking...")

        worker = Worker(run_check, target, source)
        worker.signals.result.connect(self._on_check_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_check_result(self, result: CheckResult) -> None:
        self._expand_output()
        if result.found:
            report_lines = [f"✓ '{result.target}' is contained in the following networks:"]
            for net in result.containing_networks:
                report_lines.append(f"  {net}")
            report_text = "\n".join(report_lines)
            self.split_output.set_report_text(report_text)
            output_text = format_prefixes(result.containing_networks, fmt="list")
            self.split_output.set_output_text(output_text)
            self.progress_panel.set_status(f"Found in {len(result.containing_networks)} network(s)")
        else:
            self.split_output.set_report_text(f"✗ '{result.target}' is NOT contained in any network from the source.")
            self.split_output.set_output_text("")
            self.progress_panel.set_status("Not found")

    def _on_error(self, error_msg: str) -> None:
        self.split_output.set_report_text(f"Error: {error_msg}")
        self.split_output.set_output_text("")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.progress_panel.set_busy(False)

    def save_settings(self) -> dict:
        return {}

    def load_settings(self, state: dict) -> None:
        pass