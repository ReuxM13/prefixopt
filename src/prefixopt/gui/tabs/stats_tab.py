"""
Stats tab: displays summary statistics (counts, unique IPs, compression ratio,
duplicates) in an HTML report.
"""


from typing import Any

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from .base_operation_tab import BaseOperationTab
from ..models import StatsResult
from ..services import run_stats
from ..widgets.input_panel import InputPanel
from ..workers import Worker

_STATS_CSS = """
<style>
    body {{
        font-family: Consolas, "Courier New", monospace;
        font-size: 10pt;
        color: {text};
        background-color: {bg};
        margin: 6px;
    }}
    h2 {{
        color: {heading};
        margin: 8px 0 6px 0;
        font-size: 11pt;
        border-bottom: 1px solid {border};
        padding-bottom: 4px;
    }}
    h3 {{
        color: {subheading};
        margin: 8px 0 4px 0;
        font-size: 10pt;
    }}
    table {{
        border-collapse: collapse;
        width: 100%;
        margin-bottom: 10px;
    }}
    th {{
        background-color: {th_bg};
        color: {th_text};
        text-align: left;
        padding: 4px 10px;
        border: 1px solid {border};
        font-weight: bold;
    }}
    td {{
        padding: 3px 10px;
        border: 1px solid {cell_border};
    }}
    td.metric {{ color: {metric}; }}
    td.value {{ color: {value}; font-weight: bold; text-align: right; }}
    tr:nth-child(even) {{ background-color: {row_even}; }}
    tr:nth-child(odd) {{ background-color: {row_odd}; }}
    .dup {{ color: {dup}; font-family: Consolas, monospace; }}
    .muted {{ color: {muted}; }}
    p {{ margin: 2px 0; }}
</style>
"""


class StatsTab(BaseOperationTab):

    """Show summary statistics and duplicates for a prefix list."""

    def __init__(self) -> None:
        """Set up the widget, build its UI and wire up signals."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Construct and lay out all child widgets for this tab."""
        desc = QLabel("Show statistics for a prefix list.")
        desc.setProperty("role", "description")
        desc.setWordWrap(True)
        self.control_layout.addWidget(desc)

        self.input_panel = InputPanel(
            title="Source",
            file_label="Input file",
            text_placeholder="Paste prefixes here...",
        )
        self.control_layout.addWidget(self.input_panel)

        controls_row = QHBoxLayout()
        self.show_details = QCheckBox("Show details")
        self.show_details.setToolTip(
            "Show IPv4/IPv6 breakdown and duplicate prefixes"
        )
        controls_row.addWidget(self.show_details)
        controls_row.addStretch()
        self.run_button = QPushButton("Run Stats")
        self.run_button.setProperty("primary", True)
        self.run_button.setToolTip("Ctrl+R")
        controls_row.addWidget(self.run_button)
        self.control_layout.addLayout(controls_row)

        self._setup_splitter(self.output_panel)

        self.run_button.clicked.connect(self._run_stats)
        self.input_panel.source_changed.connect(self._update_state)
        self._update_state()

    def _is_dark_theme(self) -> bool:
        bg = self.palette().color(QPalette.ColorRole.Window)
        luminance = (
            0.299 * bg.redF()
            + 0.587 * bg.greenF()
            + 0.114 * bg.blueF()
        )
        return luminance < 0.5

    def _build_html(self, result: StatsResult) -> str:
        dark = self._is_dark_theme()

        if dark:
            c = {
                "text": "#d4d4d4",
                "bg": "#1e1e1e",
                "heading": "#569cd6",
                "subheading": "#4ec9b0",
                "border": "#444",
                "cell_border": "#3a3a3a",
                "th_bg": "#2d2d30",
                "th_text": "#9cdcfe",
                "metric": "#d4d4d4",
                "value": "#b5cea8",
                "row_even": "#252526",
                "row_odd": "#1e1e1e",
                "dup": "#ce9178",
                "muted": "#808080",
            }
        else:
            c = {
                "text": "#1e1e1e",
                "bg": "#ffffff",
                "heading": "#0078d4",
                "subheading": "#107c10",
                "border": "#d0d0d0",
                "cell_border": "#e0e0e0",
                "th_bg": "#f0f0f0",
                "th_text": "#0078d4",
                "metric": "#1e1e1e",
                "value": "#107c10",
                "row_even": "#f9f9f9",
                "row_odd": "#ffffff",
                "dup": "#a31515",
                "muted": "#6e6e6e",
            }

        css = _STATS_CSS.format(**c)
        show = self.show_details.isChecked()

        parts = [css, "<h2>Prefix List Statistics</h2>"]

        metrics = [
            ("Original prefix count", f"{result.original_prefix_count:,}"),
            ("Optimized prefix count", f"{result.optimized_prefix_count:,}"),
            ("Compression ratio", f"{result.compression_ratio_percent:.2f}%"),
            ("Original total IPs", f"{result.original_total_ips:,}"),
            ("Unique IPs", f"{result.unique_ips:,}"),
            ("Addresses saved", f"{result.addresses_saved:,}"),
        ]

        if show:
            metrics.append(
                ("IPv4 prefixes", f"{result.ipv4_count:,}")
            )
            metrics.append(
                ("IPv6 prefixes", f"{result.ipv6_count:,}")
            )
            if result.duplicates:
                metrics.append(
                    ("Duplicate prefixes", f"{len(result.duplicates):,}")
                )

        parts.append("<table>")
        parts.append(
            "<tr><th>Metric</th><th style='text-align:right;'>Value</th></tr>"
        )
        for metric, value in metrics:
            parts.append(
                f"<tr>"
                f'<td class="metric">{metric}</td>'
                f'<td class="value">{value}</td>'
                f"</tr>"
            )
        parts.append("</table>")

        if show and result.duplicates:
            parts.append(f"<h3>Duplicate Prefixes ({len(result.duplicates):,})</h3>")
            parts.append("<table>")
            parts.append(
                "<tr><th>Prefix</th>"
                "<th style='text-align:right;'>Count</th></tr>"
            )
            for prefix, count in result.duplicates:
                parts.append(
                    f"<tr>"
                    f'<td class="dup">{prefix}</td>'
                    f'<td class="value">{count}</td>'
                    f"</tr>"
                )
            parts.append("</table>")

        if not show:
            parts.append(
                '<p class="muted">Enable "Show details" to see '
                "IPv4/IPv6 breakdown and duplicate prefixes.</p>"
            )

        return "".join(parts)

    def _update_state(self, _: Any = None) -> None:
        """Enable/disable the Run button based on current input validity."""
        self.run_button.setEnabled(
            self.input_panel.get_data_source() is not None
        )

    def _run_stats(self) -> None:
        """Collect options and launch the background worker."""
        source = self.input_panel.get_data_source()
        if source is None:
            return

        worker = Worker(run_stats, source)
        worker.signals.result.connect(self._on_stats_result)
        worker.signals.error.connect(self._on_error)
        self._start_worker(worker, "Calculating stats...")

    def _on_stats_result(self, result: StatsResult) -> None:
        """Handle the stats result event."""
        self._expand_output()
        self.output_panel.set_html(self._build_html(result))
        self.progress_panel.set_status(
            f"Done. {result.original_prefix_count:,} prefixes analyzed"
        )

    def trigger_open(self) -> None:
        """Programmatically open a file for this tab (used by Ctrl+O)."""
        self.input_panel.browse_button.click()

    def trigger_run(self) -> None:
        """Programmatically run this tab's operation (used by Ctrl+R)."""
        if self.run_button.isEnabled():
            self.run_button.click()

    def save_settings(self) -> dict:
        """Serialise this tab's widget state for persistence."""
        return {
            "show_details": self.show_details.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        """Restore widget state previously saved by save_settings."""
        if not state:
            return
        self.show_details.setChecked(state.get("show_details", False))