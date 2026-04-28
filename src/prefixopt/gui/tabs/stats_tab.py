"""
Stats tab.
"""
from PySide6.QtWidgets import QLabel, QPushButton, QCheckBox, QHBoxLayout, QGroupBox, QVBoxLayout, QTableWidget, QTableWidgetItem
from PySide6.QtCore import QThreadPool

from .base_operation_tab import BaseOperationTab
from ..widgets.input_panel import InputPanel
from ..workers import Worker
from ..services import run_stats
from ..models import StatsResult


class StatsTab(BaseOperationTab):
    def __init__(self) -> None:
        super().__init__()
        self._init_ui()
        self.threadpool = QThreadPool.globalInstance()

    def _init_ui(self) -> None:
        self.control_layout.addWidget(QLabel(
            "Show statistics for a prefix list."
        ))

        self.input_panel = InputPanel(
            title="Source",
            file_label="Input file",
            text_placeholder="Paste prefixes here...",
        )
        self.control_layout.addWidget(self.input_panel)

        controls_row = QHBoxLayout()
        self.show_details = QCheckBox("Show details")
        controls_row.addWidget(self.show_details)
        controls_row.addStretch()
        self.run_button = QPushButton("Run Stats")
        controls_row.addWidget(self.run_button)
        self.control_layout.addLayout(controls_row)

        table_group = QGroupBox("Statistics preview")
        table_layout = QVBoxLayout(table_group)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Metric", "Value"])
        table_layout.addWidget(self.table)
        self.control_layout.addWidget(table_group)

        self._setup_splitter(self.output_panel)

        self.run_button.clicked.connect(self._run_stats)
        self.input_panel.source_changed.connect(self._update_state)
        self._update_state()

    def _update_state(self, _=None) -> None:
        self.run_button.setEnabled(self.input_panel.get_data_source() is not None)

    def _run_stats(self) -> None:
        source = self.input_panel.get_data_source()
        if source is None:
            return

        self.run_button.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status("Calculating stats...")

        worker = Worker(run_stats, source)
        worker.signals.result.connect(self._on_stats_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_stats_result(self, result: StatsResult) -> None:
        self.table.setRowCount(7)
        self.table.setItem(0, 0, QTableWidgetItem("Original prefix count"))
        self.table.setItem(0, 1, QTableWidgetItem(str(result.original_prefix_count)))
        self.table.setItem(1, 0, QTableWidgetItem("Optimized prefix count"))
        self.table.setItem(1, 1, QTableWidgetItem(str(result.optimized_prefix_count)))
        self.table.setItem(2, 0, QTableWidgetItem("Compression ratio"))
        self.table.setItem(2, 1, QTableWidgetItem(f"{result.compression_ratio_percent}%"))
        self.table.setItem(3, 0, QTableWidgetItem("Original total IPs"))
        self.table.setItem(3, 1, QTableWidgetItem(f"{result.original_total_ips:,}"))
        self.table.setItem(4, 0, QTableWidgetItem("Unique IPs"))
        self.table.setItem(4, 1, QTableWidgetItem(f"{result.unique_ips:,}"))
        self.table.setItem(5, 0, QTableWidgetItem("Addresses saved"))
        self.table.setItem(5, 1, QTableWidgetItem(f"{result.addresses_saved:,}"))
        self.table.setItem(6, 0, QTableWidgetItem("IPv4 / IPv6 count"))
        self.table.setItem(6, 1, QTableWidgetItem(f"{result.ipv4_count} / {result.ipv6_count}"))
        self.table.resizeColumnsToContents()

        self.output_panel.set_text(f"Stats computed. {result.original_prefix_count} prefixes -> {result.optimized_prefix_count} after optimization.")
        self.progress_panel.set_status("Done")

    def _on_error(self, error_msg: str) -> None:
        self.output_panel.set_text(f"Error: {error_msg}")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.progress_panel.set_busy(False)

    def save_settings(self) -> dict:
        return {
            'show_details': self.show_details.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        if not state:
            return
        self.show_details.setChecked(state.get('show_details', False))