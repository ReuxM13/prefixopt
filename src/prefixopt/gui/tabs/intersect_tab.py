"""
Intersect tab with split output.
"""
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QLabel, QPushButton, QCheckBox, QHBoxLayout
)

from .base_operation_tab import BaseOperationTab
from ..widgets.input_panel import InputPanel
from ..widgets.split_output_panel import SplitOutputPanel
from ..workers import Worker
from ..services import run_intersect
from ..models import IntersectReport
from ..output_formatter import format_prefixes


class IntersectTab(BaseOperationTab):
    def __init__(self) -> None:
        super().__init__()
        self._init_ui()
        self.threadpool = QThreadPool.globalInstance()

    def _init_ui(self) -> None:
        self.control_layout.addWidget(QLabel(
            "Find exact matches and overlaps between two sources or within one source."
        ))

        self.input_a = InputPanel(
            title="Source A",
            file_label="Source A file",
            text_placeholder="Paste source A prefixes here...",
        )
        self.input_b = InputPanel(
            title="Source B",
            file_label="Source B file",
            text_placeholder="Paste source B prefixes here...",
        )
        self.input_b.setEnabled(True)
        self.control_layout.addWidget(self.input_a)
        self.control_layout.addWidget(self.input_b)

        controls_row = QHBoxLayout()
        self.self_check = QCheckBox("Self-check Source A only")
        self.strict = QCheckBox("Strict mode")
        controls_row.addWidget(self.self_check)
        controls_row.addWidget(self.strict)
        controls_row.addStretch()
        self.control_layout.addLayout(controls_row)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Intersect")
        run_row.addStretch()
        run_row.addWidget(self.run_button)
        self.control_layout.addLayout(run_row)

        self.split_output = SplitOutputPanel(
            report_title="Structured report",
            output_title="Output (flat list)"
        )
        self._setup_splitter(self.split_output)

        self.self_check.toggled.connect(self._update_mode)
        self.input_a.source_changed.connect(self._update_run_state)
        self.input_b.source_changed.connect(self._update_run_state)
        self.run_button.clicked.connect(self._run_intersect)

        self._update_mode()
        self._update_run_state()

    def _update_mode(self) -> None:
        self.input_b.setEnabled(not self.self_check.isChecked())
        self._update_run_state()

    def _update_run_state(self, _=None) -> None:
        if self.self_check.isChecked():
            enabled = self.input_a.get_data_source() is not None
        else:
            enabled = (
                self.input_a.get_data_source() is not None and
                self.input_b.get_data_source() is not None
            )
        self.run_button.setEnabled(enabled)

    def _run_intersect(self) -> None:
        source1 = self.input_a.get_data_source()
        self_mode = self.self_check.isChecked()
        source2 = None if self_mode else self.input_b.get_data_source()

        if source1 is None:
            return
        if not self_mode and source2 is None:
            return

        strict = self.strict.isChecked()
        name1 = self.input_a.title()
        name2 = self.input_b.title() if not self_mode else name1

        self.run_button.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status("Calculating intersections...")

        worker = Worker(run_intersect, source1, source2, strict, name1, name2)
        worker.signals.result.connect(self._on_intersect_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_intersect_result(self, report: IntersectReport) -> None:
        # ... (код генерации отчёта без изменений) ...
        # для краткости оставлю тот же, что был ранее
        lines = []
        if report.self_mode:
            lines.append(f"Self-Intersection Report for {report.name1}")
            lines.append(f"Unique IPs: {report.volume1:,}")
            lines.append("")
        else:
            lines.append("Intersection Report")
            lines.append("")
            lines.append(f"Metric                     | {report.name1:<20} | {report.name2:<20} | Intersection")
            lines.append("-" * 70)
            lines.append(f"Unique IPs                 | {report.volume1:>20,} | {report.volume2:>20,} | {report.volume_intersection:>20,}")
            lines.append(f"Coverage                   | {report.coverage1:>19.2f}% | {report.coverage2:>19.2f}% |")
            lines.append("")
            if report.all_a_in_b:
                lines.append(f"✓ All unique IPs from {report.name1} are present in {report.name2}")
            elif report.volume1 > 0:
                lines.append(f"✗ Only {report.coverage1:.2f}% of {report.name1} is covered by {report.name2}")
            if report.all_b_in_a and not report.self_mode:
                lines.append(f"✓ All unique IPs from {report.name2} are present in {report.name1}")
            lines.append("")

        if report.exact_matches:
            lines.append(f"=== Exact Matches ({len(report.exact_matches)}) ===")
            for p in report.exact_matches:
                lines.append(f"= {p}")
        else:
            lines.append("No exact matches found.")
        lines.append("")

        if report.partial_overlaps:
            lines.append(f"=== Partial Overlaps ({len(report.partial_overlaps)}) ===")
            for sub, parent, src_sub, src_parent in report.partial_overlaps:
                lines.append(f"  {sub} ({src_sub}) is inside {parent} ({src_parent})")
        else:
            lines.append("No partial overlaps found.")

        report_text = "\n".join(lines)
        self.split_output.set_report_text(report_text)

        if report.all_results:
            flat_text = format_prefixes(report.all_results, fmt="list")
            self.split_output.set_output_text(flat_text)
        else:
            self.split_output.set_output_text("No intersecting prefixes found.")

        self.progress_panel.set_status(f"Done. Exact matches: {len(report.exact_matches)}, Partial overlaps: {len(report.partial_overlaps)}")

    def _on_error(self, error_msg: str) -> None:
        self.split_output.set_report_text(f"Error: {error_msg}")
        self.split_output.set_output_text(f"Error: {error_msg}")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.progress_panel.set_busy(False)

    def save_settings(self) -> dict:
        return {
            'self_check': self.self_check.isChecked(),
            'strict': self.strict.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        if not state:
            return
        self.self_check.setChecked(state.get('self_check', False))
        self.strict.setChecked(state.get('strict', False))