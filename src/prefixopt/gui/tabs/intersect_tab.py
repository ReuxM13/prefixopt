"""
Вкладка поиска пересечений между списками префиксов.

Поддерживает три режима работы:
- 1 источник — поиск внутренних пересечений (self-intersect);
- 2 источника — попарное сравнение с покрытием;
- 3+ источников — матрица присутствия с попарным анализом.
"""

from typing import Any, List, Tuple
from .. import LOG_DIR
import logging
from pathlib import Path

from PySide6.QtGui import QPalette
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

from ...core.ip_utils import IPNet

logger = logging.getLogger("prefixopt.gui.tab.intersect")


def _build_report_css(dark: bool) -> str:
    """
    Формирует CSS для отчёта пересечений, адаптированный к текущей теме.

    Args:
        dark: True для тёмной темы.

    Returns:
        CSS-строка.
    """
    if dark:
        c = {
            "body_bg": "#1e1e1e",
            "body_text": "#e0e0e0",
            "h2": "#569cd6",
            "h3": "#4ec9b0",
            "th_bg": "#2d2d30",
            "th_text": "#9cdcfe",
            "td_border": "#3a3a3a",
            "th_border": "#444",
            "row_even": "#252526",
            "row_odd": "#1e1e1e",
            "yes": "#4ec9b0",
            "no": "#666",
            "exact": "#569cd6",
            "partial": "#ce9178",
            "warn": "#d7ba7d",
            "stat_value": "#b5cea8",
            "muted": "#808080",
        }
    else:
        c = {
            "body_bg": "#ffffff",
            "body_text": "#1e1e1e",
            "h2": "#0078d4",
            "h3": "#107c10",
            "th_bg": "#f0f0f0",
            "th_text": "#0078d4",
            "td_border": "#e0e0e0",
            "th_border": "#d0d0d0",
            "row_even": "#f9f9f9",
            "row_odd": "#ffffff",
            "yes": "#107c10",
            "no": "#b0b0b0",
            "exact": "#0078d4",
            "partial": "#a31515",
            "warn": "#d7ba7d",
            "stat_value": "#107c10",
            "muted": "#6e6e6e",
        }

    return f"""
<style>
    body {{
        font-family: Consolas, "Courier New", monospace;
        font-size: 10pt;
        color: {c["body_text"]};
        background-color: {c["body_bg"]};
        margin: 6px;
    }}
    h2 {{
        color: {c["h2"]};
        margin: 10px 0 6px 0;
        font-size: 11pt;
        border-bottom: 1px solid #444;
        padding-bottom: 4px;
    }}
    h3 {{
        color: {c["h3"]};
        margin: 8px 0 4px 0;
        font-size: 10pt;
    }}
    table {{
        border-collapse: collapse;
        margin: 4px 0 10px 0;
        width: 100%;
    }}
    th {{
        background-color: {c["th_bg"]};
        color: {c["th_text"]};
        text-align: left;
        padding: 4px 8px;
        border: 1px solid {c["th_border"]};
        font-weight: bold;
    }}
    td {{
        padding: 3px 8px;
        border: 1px solid {c["td_border"]};
    }}
    tr:nth-child(even) {{ background-color: {c["row_even"]}; }}
    tr:nth-child(odd) {{ background-color: {c["row_odd"]}; }}
    .yes {{ color: {c["yes"]}; font-weight: bold; }}
    .no {{ color: {c["no"]}; }}
    .exact {{ color: {c["exact"]}; }}
    .partial {{ color: {c["partial"]}; }}
    .warn {{ color: {c["warn"]}; }}
    .stat-value {{ color: {c["stat_value"]}; font-weight: bold; }}
    .muted {{ color: {c["muted"]}; }}
    p {{ margin: 3px 0; }}
</style>
"""


def _fmt_count(count: int) -> str:
    """
    Форматирует число с разделителями разрядов.

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

    @property
    def _error_display_widget(self) -> QWidget:
        """Возвращает split_output для отображения ошибок."""
        return self.split_output

    def get_split_output_panel(self):
        """Возвращает split_output для вкладок с двойной панелью."""

    def _on_error_cleanup(self) -> None:
        """Очищает область вывода после ошибки."""
        self.split_output.set_output_text("")

    def _init_ui(self) -> None:
        """Создает структуру вкладки с динамическими панелями источников."""
        desc = QLabel(
            "Find common prefixes across multiple sources.\n"
            "1 source - self-check (internal overlaps)\n"
            "2 sources - side-by-side comparison with coverage\n"
            "3+ sources - presence matrix"
        )
        desc.setProperty("role", "description")
        desc.setWordWrap(True)
        self.control_layout.addWidget(desc)

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
        self.strict.setToolTip(
            "Reject prefixes with incorrect subnet masks"
        )
        self.control_layout.addWidget(self.strict)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Intersect")
        self.run_button.setProperty("primary", True)
        self.run_button.setToolTip("Ctrl+R")
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

    def _is_dark_theme(self) -> bool:
        """
        Определяет активную тему по яркости фона палитры.

        Returns:
            True для тёмной темы.
        """
        bg = self.palette().color(QPalette.ColorRole.Window)
        luminance = 0.299 * bg.redF() + 0.587 * bg.greenF() + 0.114 * bg.blueF()
        return luminance < 0.5

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
        Обрабатывает изменение источника в панели.

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
        self._start_worker(worker, "Calculating intersections...")

    def _build_self_intersect_html(self, report: IntersectReport) -> str:
        """
        Формирует HTML-отчет для режима self-intersect.

        Args:
            report: Результат анализа пересечений.

        Returns:
            HTML-строка отчета.
        """
        css = _build_report_css(self._is_dark_theme())
        parts = [css]
        parts.append(f"<h2>Self-Intersection Report: {report.name1}</h2>")
        parts.append(
            f'<p>Unique IPs: <span class="stat-value">'
            f"{_fmt_count(report.volume1)}</span></p>"
        )
        parts.append(
            '<p class="muted">Exact matches are not calculated '
            "in self-check mode.</p>"
        )

        if report.partial_overlaps:
            parts.append(
                f"<h3>Partial Overlaps ({len(report.partial_overlaps)})</h3>"
            )
            parts.append(
                "<table><tr>"
                "<th>Subnet</th><th>Source</th>"
                "<th>Supernet</th><th>Source</th>"
                "</tr>"
            )
            for sub, parent, src_sub, src_parent in report.partial_overlaps:
                parts.append(
                    f"<tr>"
                    f'<td class="partial">{sub}</td><td>{src_sub}</td>'
                    f'<td class="partial">{parent}</td><td>{src_parent}</td>'
                    f"</tr>"
                )
            parts.append("</table>")
        else:
            parts.append(
                '<p class="muted">No internal overlaps found.</p>'
            )

        return "".join(parts)

    def _build_two_source_html(self, report: IntersectReport) -> str:
        """
        Формирует HTML-отчет для режима сравнения двух источников.

        Args:
            report: Результат анализа пересечений.

        Returns:
            HTML-строка отчета.
        """
        css = _build_report_css(self._is_dark_theme())
        parts = [css]
        parts.append("<h2>Intersection Report</h2>")

        parts.append(
            "<table><tr>"
            "<th>Metric</th>"
            f"<th>{report.name1}</th>"
            f"<th>{report.name2}</th>"
            "<th>Intersection</th>"
            "</tr>"
        )
        parts.append(
            f"<tr><td>Unique IPs</td>"
            f'<td class="stat-value">{_fmt_count(report.volume1)}</td>'
            f'<td class="stat-value">{_fmt_count(report.volume2)}</td>'
            f'<td class="stat-value">'
            f"{_fmt_count(report.volume_intersection)}</td></tr>"
        )
        parts.append(
            f"<tr><td>Coverage</td>"
            f'<td class="stat-value">{report.coverage1:.2f}%</td>'
            f'<td class="stat-value">{report.coverage2:.2f}%</td>'
            f"<td></td></tr>"
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
            parts.append(
                "<table><tr>"
                "<th>Subnet</th><th>Source</th>"
                "<th>Supernet</th><th>Source</th>"
                "</tr>"
            )
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

    def _build_multi_html(self, report: MultiIntersectReport) -> str:
        """
        Формирует HTML-отчет для режима 3+ источников.

        Использует предрасчитанные данные из report без повторной
        загрузки источников.

        Args:
            report: Результат мульти-пересечения.

        Returns:
            HTML-строка отчета.
        """
        css = _build_report_css(self._is_dark_theme())
        parts = [css]
        parts.append("<h2>Multi-Intersection Report</h2>")
        parts.append(
            f'<p>Sources: <span class="stat-value">'
            f"{', '.join(report.source_names)}</span></p>"
        )
        parts.append("<p>Threshold: present in ≥2 sources</p>")
        parts.append(
            f'<p>Matched prefixes: <span class="stat-value">'
            f"{len(report.filtered_prefixes)}</span></p>"
        )

        if report.filtered_prefixes:
            parts.append(
                f'<p>Total unique IPs: <span class="stat-value">'
                f"{_fmt_count(report.filtered_unique_ips)}</span></p>"
            )
            parts.append("<h3>Presence Matrix</h3>")
            parts.append("<table><tr><th>Prefix</th>")
            for name in report.source_names:
                parts.append(f"<th>{name}</th>")
            parts.append("</tr>")

            for net in report.filtered_prefixes:
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

        parts.append("<h3>Pairwise Exact Matches</h3>")

        if report.pairwise_exact:
            for pe in report.pairwise_exact:
                parts.append(
                    f"<p>{pe.name_a} ∩ {pe.name_b}: "
                    f'<span class="stat-value">{len(pe.prefixes)}</span></p>'
                )
                parts.append("<table><tr><th>Prefix</th></tr>")
                for net in pe.prefixes:
                    parts.append(f'<tr><td class="exact">{net}</td></tr>')
                parts.append("</table>")
        else:
            parts.append(
                '<p class="muted">No exact matches between any pair.</p>'
            )

        if report.pairwise_partial:
            parts.append(
                f"<h3>Partial Overlaps ({len(report.pairwise_partial)})</h3>"
            )
            parts.append(
                "<table><tr>"
                "<th>Subnet</th><th>Source</th>"
                "<th>Supernet</th><th>Source</th>"
                "</tr>"
            )
            for pp in report.pairwise_partial:
                parts.append(
                    f"<tr>"
                    f'<td class="partial">{pp.subnet}</td>'
                    f"<td>{pp.source_subnet}</td>"
                    f'<td class="partial">{pp.supernet}</td>'
                    f"<td>{pp.source_supernet}</td>"
                    f"</tr>"
                )
            parts.append("</table>")
        else:
            parts.append(
                '<p class="muted">No partial overlaps between any pair.</p>'
            )

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
        self.split_output.set_output_text(
            format_prefixes(report.all_results, "list")
            if report.all_results
            else ""
        )
        self.progress_panel.set_status(
            f"Done. Exact: {len(report.exact_matches)}, "
            f"Partial: {len(report.partial_overlaps)}"
        )

    def _on_multi_result(self, report: MultiIntersectReport) -> None:
        """
        Обрабатывает результат для 3+ источников.

        Рендерит HTML из предрасчитанных данных без повторной загрузки.

        Args:
            report: Результат мульти-пересечения.
        """
        self._expand_output()
        self.split_output.set_report_html(self._build_multi_html(report))
        self.split_output.set_output_text(
            format_prefixes(report.output_prefixes, "list")
            if report.output_prefixes
            else ""
        )
        self.progress_panel.set_status(
            f"Done. {len(report.filtered_prefixes)} shared prefixes, "
            f"pairwise analysis complete"
        )

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