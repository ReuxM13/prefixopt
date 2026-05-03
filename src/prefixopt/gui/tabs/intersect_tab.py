"""
Вкладка поиска пересечений между списками префиксов.

Поддерживает три режима работы:
- 1 источник — поиск внутренних пересечений (self-intersect);
- 2 источника — попарное сравнение с покрытием;
- 3+ источников — матрица присутствия с попарным анализом.
"""

from pathlib import Path
from typing import Any, List, Tuple

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .base_operation_tab import BaseOperationTab
from ..models import IntersectReport, MultiIntersectReport
from ..output_formatter import format_prefixes
from ..services import run_intersect, run_multi_intersect
from ..widgets.input_panel import InputPanel
from ..widgets.split_output_panel import SplitOutputPanel
from ..workers import Worker

from prefixopt.core.ip_counter import count_unique_ips
from prefixopt.core.ip_utils import IPNet
from prefixopt.core.operations.sorter import sort_networks
from prefixopt.core.pipeline import process_prefixes
from prefixopt.data.file_reader import read_networks, extract_prefixes_from_text


_REPORT_CSS = """
<style>
    body {
        font-family: Consolas, "Courier New", monospace;
        font-size: 10pt;
        color: #e0e0e0;
        background-color: #1e1e1e;
        margin: 6px;
    }
    h2 {
        color: #569cd6;
        margin: 10px 0 6px 0;
        font-size: 11pt;
        border-bottom: 1px solid #444;
        padding-bottom: 4px;
    }
    h3 {
        color: #4ec9b0;
        margin: 8px 0 4px 0;
        font-size: 10pt;
    }
    table {
        border-collapse: collapse;
        margin: 4px 0 10px 0;
        width: 100%;
    }
    th {
        background-color: #2d2d30;
        color: #9cdcfe;
        text-align: left;
        padding: 4px 8px;
        border: 1px solid #444;
        font-weight: bold;
    }
    td {
        padding: 3px 8px;
        border: 1px solid #3a3a3a;
    }
    tr:nth-child(even) { background-color: #252526; }
    tr:nth-child(odd) { background-color: #1e1e1e; }
    .yes { color: #4ec9b0; font-weight: bold; }
    .no { color: #666; }
    .exact { color: #569cd6; }
    .partial { color: #ce9178; }
    .info { color: #b5cea8; }
    .warn { color: #d7ba7d; }
    .stat-value { color: #b5cea8; font-weight: bold; }
    .muted { color: #808080; }
    p { margin: 3px 0; }
</style>
"""


def _find_overlaps_linear(
    list1: List[IPNet],
    list2: List[IPNet],
) -> List[Tuple[IPNet, IPNet]]:
    """
    Линейный поиск пересечений между двумя отсортированными списками.

    Использует two-pointer алгоритм по диапазонам адресов.

    Args:
        list1: Первый отсортированный список сетей.
        list2: Второй отсортированный список сетей.

    Returns:
        Список пар пересекающихся сетей.
    """
    overlaps: List[Tuple[IPNet, IPNet]] = []
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

        start1 = int(net1.network_address)
        end1 = int(net1.broadcast_address)
        start2 = int(net2.network_address)
        end2 = int(net2.broadcast_address)

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


def _format_ip_count(count: int) -> str:
    """
    Форматирует числовое значение с разделителями разрядов.

    Args:
        count: Число для форматирования.

    Returns:
        Отформатированная строка.
    """
    return f"{count:,}"


class IntersectTab(BaseOperationTab):
    """Вкладка поиска пересечений между списками префиксов."""

    def __init__(self) -> None:
        """Инициализирует вкладку и создает элементы интерфейса."""
        super().__init__()
        self._source_panels: list[InputPanel] = []
        self._sources: list = []
        self._names: list[str] = []
        self._init_ui()

    def _init_ui(self) -> None:
        """Создает структуру вкладки с динамическими панелями источников."""
        self.control_layout.addWidget(
            QLabel(
                "Find common prefixes across multiple sources.\n"
                "• 1 source → self-check (internal overlaps)\n"
                "• 2 sources → side-by-side comparison with coverage\n"
                "• 3+ sources → presence matrix (prefixes in ≥2 sources)"
            )
        )

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
            output_title="Common prefixes",
        )
        self._setup_splitter(self.split_output)

        self.splitter.setStretchFactor(0, 9)
        self.splitter.setStretchFactor(1, 1)

        self._add_source_panel()
        self._add_source_panel()

        self.run_button.clicked.connect(self._run_intersect)
        self._update_run_state()

    def _update_panel_title(self, panel: InputPanel) -> None:
        """
        Обновляет заголовок панели на имя файла или порядковый номер.

        Args:
            panel: Панель ввода.
        """
        file_name = panel.display_name()
        if file_name:
            panel.set_title(file_name)
            return

        idx = self._source_panels.index(panel) + 1
        panel.set_title(f"Source {idx}")

    def _add_source_panel(self) -> None:
        """Добавляет новую панель источника."""
        initial_title = f"Source {len(self._source_panels) + 1}"
        panel = InputPanel(
            title=initial_title,
            file_label="Source file",
            text_placeholder="Paste prefixes here...",
        )
        panel.source_changed.connect(
            lambda p=panel: self._on_panel_source_changed(p)
        )
        self._source_panels.append(panel)
        self.source_layout.addWidget(panel)
        self._update_remove_button_state()
        self._update_run_state()

    def _on_panel_source_changed(self, panel: InputPanel) -> None:
        """
        Обработчик изменения источника в панели.

        Args:
            panel: Панель, в которой изменился источник.
        """
        self._update_panel_title(panel)
        self._update_run_state()

    def _remove_source_panel(self) -> None:
        """Удаляет последнюю панель источника."""
        if len(self._source_panels) <= 1:
            return

        panel = self._source_panels.pop()
        self.source_layout.removeWidget(panel)
        panel.deleteLater()

        for i, p in enumerate(self._source_panels):
            if not p.display_name():
                p.set_title(f"Source {i + 1}")

        self._update_remove_button_state()
        self._update_run_state()

    def _update_remove_button_state(self) -> None:
        """Обновляет доступность кнопки удаления панели."""
        self.remove_btn.setEnabled(len(self._source_panels) > 1)

    def _update_run_state(self, _: Any = None) -> None:
        """Обновляет доступность кнопки запуска."""
        if not self._source_panels:
            self.run_button.setEnabled(False)
            return

        for panel in self._source_panels:
            if panel.get_data_source() is None:
                self.run_button.setEnabled(False)
                return

        self.run_button.setEnabled(True)

    def _run_intersect(self) -> None:
        """Собирает параметры и запускает задачу в фоновом потоке."""
        self._sources = []
        self._names = []

        for i, panel in enumerate(self._source_panels):
            src = panel.get_data_source()
            if src is None:
                return
            self._sources.append(src)
            name = panel.display_name() or f"Source {i + 1}"
            self._names.append(name)

        strict = self.strict.isChecked()

        self.run_button.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status("Calculating intersections...")

        n = len(self._sources)

        if n <= 2:
            source2 = self._sources[1] if n == 2 else None
            name2 = self._names[1] if n == 2 else self._names[0]
            worker = Worker(
                run_intersect,
                self._sources[0],
                source2,
                strict,
                self._names[0],
                name2,
            )
            worker.signals.result.connect(self._on_two_source_result)
        else:
            worker = Worker(
                run_multi_intersect,
                *self._sources,
                strict=strict,
                source_names=self._names,
            )
            worker.signals.result.connect(self._on_multi_result)

        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _build_self_intersect_html(self, report: IntersectReport) -> str:
        """
        Формирует HTML-отчет для режима self-intersect.

        Args:
            report: Результат анализа пересечений.

        Returns:
            HTML-строка отчета.
        """
        parts = [_REPORT_CSS]

        parts.append(f"<h2>Self-Intersection Report: {report.name1}</h2>")
        parts.append(
            f'<p>Unique IPs: <span class="stat-value">'
            f"{_format_ip_count(report.volume1)}</span></p>"
        )
        parts.append(
            '<p class="muted">Exact matches are not calculated '
            "in self-check mode.</p>"
        )

        if report.partial_overlaps:
            parts.append(
                f"<h3>Partial Overlaps ({len(report.partial_overlaps)})</h3>"
            )
            parts.append("<table><tr>")
            parts.append("<th>Subnet</th><th>Source</th>")
            parts.append("<th>Supernet</th><th>Source</th>")
            parts.append("</tr>")

            for sub, parent, src_sub, src_parent in report.partial_overlaps:
                parts.append(
                    f"<tr>"
                    f'<td class="partial">{sub}</td><td>{src_sub}</td>'
                    f'<td class="partial">{parent}</td><td>{src_parent}</td>'
                    f"</tr>"
                )
            parts.append("</table>")
        else:
            parts.append('<p class="info">No internal overlaps found.</p>')

        return "".join(parts)

    def _build_two_source_html(self, report: IntersectReport) -> str:
        """
        Формирует HTML-отчет для режима сравнения двух источников.

        Args:
            report: Результат анализа пересечений.

        Returns:
            HTML-строка отчета.
        """
        parts = [_REPORT_CSS]

        parts.append("<h2>Intersection Report</h2>")

        parts.append("<table><tr>")
        parts.append("<th>Metric</th>")
        parts.append(f"<th>{report.name1}</th>")
        parts.append(f"<th>{report.name2}</th>")
        parts.append("<th>Intersection</th>")
        parts.append("</tr>")

        parts.append(
            f"<tr>"
            f"<td>Unique IPs</td>"
            f'<td class="stat-value">{_format_ip_count(report.volume1)}</td>'
            f'<td class="stat-value">{_format_ip_count(report.volume2)}</td>'
            f'<td class="stat-value">'
            f"{_format_ip_count(report.volume_intersection)}</td>"
            f"</tr>"
        )

        parts.append(
            f"<tr>"
            f"<td>Coverage</td>"
            f'<td class="stat-value">{report.coverage1:.2f}%</td>'
            f'<td class="stat-value">{report.coverage2:.2f}%</td>'
            f"<td></td>"
            f"</tr>"
        )
        parts.append("</table>")

        if report.all_a_in_b:
            parts.append(
                f'<p class="yes">✔ All IPs from {report.name1} '
                f"are present in {report.name2}</p>"
            )
        elif report.volume1 > 0:
            parts.append(
                f'<p class="warn">✘ Only {report.coverage1:.2f}% of '
                f"{report.name1} is covered by {report.name2}</p>"
            )

        if report.all_b_in_a:
            parts.append(
                f'<p class="yes">✔ All IPs from {report.name2} '
                f"are present in {report.name1}</p>"
            )

        if report.exact_matches:
            parts.append(
                f"<h3>Exact Matches ({len(report.exact_matches)})</h3>"
            )
            parts.append("<table><tr><th>Prefix</th></tr>")
            for net in report.exact_matches:
                parts.append(f'<tr><td class="exact">{net}</td></tr>')
            parts.append("</table>")
        else:
            parts.append('<p class="muted">No exact matches found.</p>')

        if report.partial_overlaps:
            parts.append(
                f"<h3>Partial Overlaps ({len(report.partial_overlaps)})</h3>"
            )
            parts.append("<table><tr>")
            parts.append("<th>Subnet</th><th>Source</th>")
            parts.append("<th>Supernet</th><th>Source</th>")
            parts.append("</tr>")
            for sub, parent, src_sub, src_parent in report.partial_overlaps:
                parts.append(
                    f"<tr>"
                    f'<td class="partial">{sub}</td><td>{src_sub}</td>'
                    f'<td class="partial">{parent}</td><td>{src_parent}</td>'
                    f"</tr>"
                )
            parts.append("</table>")
        else:
            parts.append('<p class="muted">No partial overlaps found.</p>')

        return "".join(parts)

    def _on_two_source_result(self, report: IntersectReport) -> None:
        """
        Обрабатывает результат для 1-2 источников.

        Args:
            report: Результат анализа пересечений.
        """
        self._expand_output()

        if report.self_mode:
            html = self._build_self_intersect_html(report)
        else:
            html = self._build_two_source_html(report)

        self.split_output.set_report_html(html)

        if report.all_results:
            flat = format_prefixes(report.all_results, "list")
        else:
            flat = ""
        self.split_output.set_output_text(flat)

        self.progress_panel.set_status(
            f"Done. Exact: {len(report.exact_matches)}, "
            f"Partial: {len(report.partial_overlaps)}"
        )

    def _on_multi_result(self, report: MultiIntersectReport) -> None:
        """
        Обрабатывает результат для 3+ источников.

        Args:
            report: Результат мульти-пересечения.
        """
        self._expand_output()

        filtered = [
            net for net in report.common_prefixes
            if len(report.presence_map.get(str(net), [])) >= 2
        ]

        parts = [_REPORT_CSS]
        parts.append("<h2>Multi-Intersection Report</h2>")
        parts.append(
            f'<p>Sources: <span class="stat-value">'
            f"{', '.join(report.source_names)}</span></p>"
        )
        parts.append(
            f'<p>Threshold: present in ≥2 sources</p>'
        )
        parts.append(
            f'<p>Matched prefixes: <span class="stat-value">'
            f"{len(filtered)}</span></p>"
        )

        if filtered:
            vol = count_unique_ips(filtered)
            parts.append(
                f'<p>Total unique IPs: <span class="stat-value">'
                f"{_format_ip_count(vol)}</span></p>"
            )

            parts.append("<h3>Presence Matrix</h3>")
            parts.append("<table><tr><th>Prefix</th>")
            for name in report.source_names:
                parts.append(f"<th>{name}</th>")
            parts.append("</tr>")

            for net in filtered:
                str_net = str(net)
                indices = report.presence_map.get(str_net, [])
                parts.append(f"<tr><td>{str_net}</td>")
                for idx in range(report.source_count):
                    if idx in indices:
                        parts.append('<td class="yes">✔</td>')
                    else:
                        parts.append('<td class="no">—</td>')
                parts.append("</tr>")
            parts.append("</table>")
        else:
            parts.append(
                '<p class="muted">No prefixes appear in ≥2 sources.</p>'
            )

        optimized_lists = self._load_optimized_lists()
        sets = [set(lst) for lst in optimized_lists]

        parts.append("<h3>Pairwise Exact Matches</h3>")
        has_exact = False

        for i in range(len(optimized_lists)):
            for j in range(i + 1, len(optimized_lists)):
                exact = sets[i] & sets[j]
                if not exact:
                    continue
                has_exact = True
                parts.append(
                    f"<p>{report.source_names[i]} ∩ "
                    f"{report.source_names[j]}: "
                    f'<span class="stat-value">{len(exact)}</span></p>'
                )
                parts.append("<table><tr><th>Prefix</th></tr>")
                for net in sort_networks(list(exact)):
                    parts.append(f'<tr><td class="exact">{net}</td></tr>')
                parts.append("</table>")

        if not has_exact:
            parts.append(
                '<p class="muted">No exact matches between any pair.</p>'
            )

        sorted_lists = [sort_networks(lst) for lst in optimized_lists]
        all_partial: List[Tuple[IPNet, IPNet, str, str]] = []

        for i in range(len(optimized_lists)):
            for j in range(i + 1, len(optimized_lists)):
                raw_overlaps = _find_overlaps_linear(
                    sorted_lists[i], sorted_lists[j]
                )
                for net1, net2 in raw_overlaps:
                    if net1 == net2:
                        continue
                    if net1.subnet_of(net2):
                        all_partial.append(
                            (net1, net2,
                             report.source_names[i],
                             report.source_names[j])
                        )
                    elif net2.subnet_of(net1):
                        all_partial.append(
                            (net2, net1,
                             report.source_names[j],
                             report.source_names[i])
                        )
                    else:
                        all_partial.append(
                            (net1, net2,
                             report.source_names[i],
                             report.source_names[j])
                        )

        if all_partial:
            all_partial.sort(
                key=lambda x: (x[0].version, int(x[0].network_address))
            )
            parts.append(
                f"<h3>Partial Overlaps ({len(all_partial)})</h3>"
            )
            parts.append("<table><tr>")
            parts.append("<th>Subnet</th><th>Source</th>")
            parts.append("<th>Supernet</th><th>Source</th>")
            parts.append("</tr>")

            for sub, parent, src_sub, src_parent in all_partial:
                parts.append(
                    f"<tr>"
                    f'<td class="partial">{sub}</td><td>{src_sub}</td>'
                    f'<td class="partial">{parent}</td><td>{src_parent}</td>'
                    f"</tr>"
                )
            parts.append("</table>")
        else:
            parts.append(
                '<p class="muted">No partial overlaps between any pair.</p>'
            )

        self.split_output.set_report_html("".join(parts))

        out_set: set[IPNet] = set(filtered)
        for i in range(len(optimized_lists)):
            for j in range(i + 1, len(optimized_lists)):
                out_set.update(sets[i] & sets[j])
        for sub, parent, _, _ in all_partial:
            out_set.update([sub, parent])

        if out_set:
            flat = format_prefixes(sort_networks(list(out_set)), "list")
        else:
            flat = ""

        self.split_output.set_output_text(flat)
        self.progress_panel.set_status(
            f"Done. {len(filtered)} shared prefixes, "
            f"pairwise analysis complete"
        )

    def _load_optimized_lists(self) -> List[List[IPNet]]:
        """
        Загружает и оптимизирует списки из сохраненных источников.

        Returns:
            Список оптимизированных списков сетей.
        """
        result = []
        for src in self._sources:
            if isinstance(src, Path):
                raw = read_networks(src)
            else:
                raw = extract_prefixes_from_text(src)
            opt = list(
                process_prefixes(
                    raw, sort=True, remove_nested=True, aggregate=True
                )
            )
            result.append(opt)
        return result

    def _on_error(self, error_msg: str) -> None:
        """
        Отображает сообщение об ошибке.

        Args:
            error_msg: Текст ошибки.
        """
        self.split_output.set_report_text(f"Error: {error_msg}")
        self.split_output.set_output_text("")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        """Восстанавливает состояние интерфейса."""
        self.run_button.setEnabled(True)
        self.progress_panel.set_busy(False)

    def trigger_open(self) -> None:
        """Открывает диалог выбора файла для первой незаполненной панели."""
        for panel in self._source_panels:
            if panel.get_data_source() is None:
                panel.browse_button.click()
                return
        if self._source_panels:
            self._source_panels[0].browse_button.click()

    def trigger_run(self) -> None:
        """Запускает анализ, если кнопка доступна."""
        if self.run_button.isEnabled():
            self.run_button.click()

    def save_settings(self) -> dict:
        """
        Сохраняет параметры вкладки.

        Returns:
            Словарь с текущими настройками.
        """
        return {
            "strict": self.strict.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        """
        Восстанавливает параметры вкладки.

        Args:
            state: Словарь с сохраненными настройками.
        """
        if not state:
            return
        self.strict.setChecked(state.get("strict", False))