"""
Intersect tab with multi-source support and presence matrix.
"""
from pathlib import Path
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QLabel, QPushButton, QCheckBox, QHBoxLayout, QVBoxLayout, QScrollArea, QWidget
)

from .base_operation_tab import BaseOperationTab
from ..widgets.input_panel import InputPanel
from ..widgets.split_output_panel import SplitOutputPanel
from ..workers import Worker
from ..services import run_intersect, run_multi_intersect
from ..models import IntersectReport, MultiIntersectReport
from ..output_formatter import format_prefixes
from prefixopt.core.ip_counter import count_unique_ips
from prefixopt.core.operations.sorter import sort_networks
from prefixopt.data.file_reader import read_networks, extract_prefixes_from_text
from prefixopt.core.pipeline import process_prefixes


def _find_overlaps_linear(list1, list2):
    overlaps = []
    i, j = 0, 0
    len1, len2 = len(list1), len(list2)
    while i < len1 and j < len2:
        net1, net2 = list1[i], list2[j]
        if net1.version < net2.version:
            i += 1
            continue
        if net1.version > net2.version:
            j += 1
            continue
        start1, end1 = int(net1.network_address), int(net1.broadcast_address)
        start2, end2 = int(net2.network_address), int(net2.broadcast_address)
        if max(start1, start2) <= min(end1, end2):
            overlaps.append((net1, net2))
            if end1 < end2:
                i += 1
            elif end2 < end1:
                j += 1
            else:
                i += 1
                j += 1
        elif end1 < start2:
            i += 1
        else:
            j += 1
    return overlaps


class IntersectTab(BaseOperationTab):
    def __init__(self) -> None:
        super().__init__()
        self._source_panels: list[InputPanel] = []
        self._init_ui()
        self.threadpool = QThreadPool.globalInstance()

    def _init_ui(self) -> None:
        self.control_layout.addWidget(QLabel(
            "Find common prefixes across multiple sources.\n"
            "• 1 source → self‑check (internal overlaps)\n"
            "• 2 sources → side‑by‑side comparison with coverage\n"
            "• 3+ sources → presence matrix (prefixes in ≥2 sources)"
        ))

        scroll = QScrollArea()
        scroll_widget = QWidget()
        self.source_layout = QVBoxLayout(scroll_widget)
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        self.control_layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add Source")
        self.add_btn.clicked.connect(self._add_source_panel)
        self.remove_btn = QPushButton("Remove Source")
        self.remove_btn.clicked.connect(self._remove_source_panel)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addStretch()
        self.control_layout.addLayout(btn_layout)

        self.strict = QCheckBox("Strict mode")
        self.control_layout.addWidget(self.strict)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Intersect")
        run_row.addStretch()
        run_row.addWidget(self.run_button)
        self.control_layout.addLayout(run_row)

        self.split_output = SplitOutputPanel(
            report_title="Intersection report",
            output_title="Common prefixes"
        )
        self._setup_splitter(self.split_output)

        self.splitter.setStretchFactor(0, 9)
        self.splitter.setStretchFactor(1, 1)

        self._add_source_panel()
        self._add_source_panel()

        self.run_button.clicked.connect(self._run_intersect)
        for panel in self._source_panels:
            panel.source_changed.connect(self._update_run_state)
        self._update_run_state()

    def _update_panel_title(self, panel: InputPanel) -> None:
        """Устанавливает заголовок панели: имя файла или 'Source N'."""
        file_name = panel.display_name()
        if file_name:
            panel.set_title(file_name)
        else:
            idx = self._source_panels.index(panel) + 1
            panel.set_title(f"Source {idx}")

    def _add_source_panel(self) -> None:
        initial_title = f"Source {len(self._source_panels) + 1}"
        panel = InputPanel(
            title=initial_title,
            file_label="Source file",
            text_placeholder="Paste prefixes here...",
        )
        panel.source_changed.connect(lambda p=panel: self._on_panel_source_changed(p))
        self._source_panels.append(panel)
        self.source_layout.addWidget(panel)
        self._update_remove_button_state()
        self._update_run_state()

    def _on_panel_source_changed(self, panel: InputPanel) -> None:
        self._update_panel_title(panel)
        self._update_run_state()

    def _remove_source_panel(self) -> None:
        if len(self._source_panels) <= 1:
            return
        panel = self._source_panels.pop()
        self.source_layout.removeWidget(panel)
        panel.deleteLater()
        # Обновляем заголовки оставшихся панелей (нумерация может сбиться)
        for i, p in enumerate(self._source_panels):
            if not p.display_name():
                p.set_title(f"Source {i+1}")
            # иначе имя файла остаётся
        self._update_remove_button_state()
        self._update_run_state()

    def _update_remove_button_state(self) -> None:
        self.remove_btn.setEnabled(len(self._source_panels) > 1)

    def _update_run_state(self, _=None) -> None:
        if len(self._source_panels) == 0:
            self.run_button.setEnabled(False)
            return
        for panel in self._source_panels:
            if panel.get_data_source() is None:
                self.run_button.setEnabled(False)
                return
        self.run_button.setEnabled(True)

    def _run_intersect(self) -> None:
        self._sources = []
        self._names = []
        for i, panel in enumerate(self._source_panels):
            src = panel.get_data_source()
            if src is None:
                return
            self._sources.append(src)
            # Имя: файл (без пути) или Source N
            name = panel.display_name() or f"Source {i+1}"
            self._names.append(name)

        strict = self.strict.isChecked()
        self.run_button.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status("Calculating intersections...")

        n = len(self._sources)
        if n == 1:
            worker = Worker(run_intersect, self._sources[0], None, strict, self._names[0], self._names[0])
            worker.signals.result.connect(self._on_two_file_result)
        elif n == 2:
            worker = Worker(run_intersect, self._sources[0], self._sources[1], strict, self._names[0], self._names[1])
            worker.signals.result.connect(self._on_two_file_result)
        else:
            worker = Worker(run_multi_intersect, *self._sources, strict=strict, source_names=self._names)
            worker.signals.result.connect(self._on_multi_result)

        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_two_file_result(self, report: IntersectReport) -> None:
        lines = []
        if report.self_mode:
            lines.append(f"Self-Intersection Report for {report.name1}")
            lines.append(f"Unique IPs: {report.volume1:,}")
            lines.append("")
            lines.append("Exact matches are not calculated in self‑check mode.")
            lines.append("Only internal overlaps are shown below.")
        else:
            lines.append("Intersection Report")
            lines.append("")
            lines.append(f"Metric                     | {report.name1:<20} | {report.name2:<20} | Intersection")
            lines.append("-" * 70)
            lines.append(f"Unique IPs                 | {report.volume1:>20,} | {report.volume2:>20,} | {report.volume_intersection:>20,}")
            lines.append(f"Coverage                   | {report.coverage1:>19.2f}% | {report.coverage2:>19.2f}% |")
            lines.append("")
            if report.all_a_in_b:
                lines.append(f"Y All unique IPs from {report.name1} are present in {report.name2}")
            elif report.volume1 > 0:
                lines.append(f"N Only {report.coverage1:.2f}% of {report.name1} is covered by {report.name2}")
            if report.all_b_in_a and not report.self_mode:
                lines.append(f"Y All unique IPs from {report.name2} are present in {report.name1}")
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

        flat = format_prefixes(report.all_results, "list") if report.all_results else ""
        self.split_output.set_output_text(flat)
        self.progress_panel.set_status(f"Done. Exact matches: {len(report.exact_matches)}, Partial overlaps: {len(report.partial_overlaps)}")

    def _on_multi_result(self, report: MultiIntersectReport) -> None:
        filtered = []
        for net in report.common_prefixes:
            indices = report.presence_map.get(str(net), [])
            if len(indices) >= 2:
                filtered.append(net)

        lines = []
        lines.append("Multi-Intersection Report")
        lines.append(f"Sources: {', '.join(report.source_names)}")
        lines.append(f"Threshold: present in at least 2 sources")
        lines.append(f"Shown prefixes: {len(filtered)}")
        if filtered:
            vol = count_unique_ips(filtered)
            lines.append(f"Total unique IPs in shown prefixes: {vol:,}")
            lines.append("")
            header = "Prefix".ljust(20)
            for name in report.source_names:
                header += f" | {name[:15].ljust(15)}"
            lines.append(header)
            lines.append("-" * (20 + 18 * len(report.source_names)))
            for net in filtered:
                str_net = str(net)
                row = str_net.ljust(20)
                for idx in range(report.source_count):
                    present = "Y" if idx in report.presence_map.get(str_net, []) else "N"
                    row += f" | {present.ljust(15)}"
                lines.append(row)
        else:
            lines.append("No prefixes appear in at least 2 sources.")

        # Загружаем оптимизированные списки ещё раз для pairwise exact и partial overlaps
        optimized_lists = []
        for src in self._sources:
            if isinstance(src, Path):
                raw = read_networks(src)
            else:
                raw = extract_prefixes_from_text(src)
            opt = list(process_prefixes(raw, sort=True, remove_nested=True, aggregate=True))
            optimized_lists.append(opt)

        sets = [set(lst) for lst in optimized_lists]
        # Попарные точные совпадения
        lines.append("\nPairwise Exact Matches:")
        has_any_exact = False
        for i in range(len(optimized_lists)):
            for j in range(i + 1, len(optimized_lists)):
                exact = sets[i] & sets[j]
                if exact:
                    has_any_exact = True
                    lines.append(f"  Between {report.source_names[i]} and {report.source_names[j]}: {len(exact)} prefix(es)")
                    for net in sort_networks(list(exact)):
                        lines.append(f"    = {net}")
        if not has_any_exact:
            lines.append("  No exact matches between any pair of sources.")

        # Попарные частичные перекрытия
        all_pairs_partial = []
        sorted_opt_lists = [sort_networks(lst) for lst in optimized_lists]
        for i in range(len(optimized_lists)):
            for j in range(i + 1, len(optimized_lists)):
                raw_overlaps = _find_overlaps_linear(sorted_opt_lists[i], sorted_opt_lists[j])
                for net1, net2 in raw_overlaps:
                    if net1 == net2:
                        continue
                    if net1.subnet_of(net2):
                        all_pairs_partial.append((net1, net2, report.source_names[i], report.source_names[j]))
                    elif net2.subnet_of(net1):
                        all_pairs_partial.append((net2, net1, report.source_names[j], report.source_names[i]))
                    else:
                        all_pairs_partial.append((net1, net2, report.source_names[i], report.source_names[j]))

        if all_pairs_partial:
            all_pairs_partial.sort(key=lambda x: (x[0].version, int(x[0].network_address)))
            lines.append(f"\n=== Partial Overlaps ({len(all_pairs_partial)}) ===")
            for sub, parent, src_sub, src_parent in all_pairs_partial:
                lines.append(f"  {sub} ({src_sub}) is inside {parent} ({src_parent})")
        else:
            lines.append("\nNo partial overlaps found between any pair of sources.")

        report_text = "\n".join(lines)
        self.split_output.set_report_text(report_text)

        out_set = set(filtered)
        for i in range(len(optimized_lists)):
            for j in range(i + 1, len(optimized_lists)):
                out_set.update(sets[i] & sets[j])
        for sub, parent, _, _ in all_pairs_partial:
            out_set.update([sub, parent])
        flat = format_prefixes(sort_networks(list(out_set)), "list") if out_set else ""
        self.split_output.set_output_text(flat)
        self.progress_panel.set_status(f"Done. {len(filtered)} prefixes, exact/partial matches shown")

    def _on_error(self, error_msg: str) -> None:
        self.split_output.set_report_text(f"Error: {error_msg}")
        self.split_output.set_output_text("")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.progress_panel.set_busy(False)

    def save_settings(self) -> dict:
        return {
            'strict': self.strict.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        if not state:
            return
        self.strict.setChecked(state.get('strict', False))