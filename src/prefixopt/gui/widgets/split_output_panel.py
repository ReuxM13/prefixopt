"""
A two-pane output panel used by reports that have both a narrative report and
a plain prefix list (Intersect, Check).

The top pane shows HTML or rich text (the report), while the bottom pane is a
regular :class:`OutputPanel` for the machine-readable prefix list. The class
also implements the ``_error_display_widget``/``set_report_text`` interface
expected by :class:`BaseOperationTab` so error handling works uniformly.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .output_panel import OutputPanel


class SplitOutputPanel(QWidget):
    """Vertically split panel: HTML report on top, output panel below."""

    def __init__(
        self,
        report_title: str = "Report",
        output_title: str = "Output",
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialise the component."""
        super().__init__(parent)
        self._report_title = report_title
        self._output_title = output_title
        self._init_ui()

    def _init_ui(self) -> None:
        """Construct and lay out the child widgets."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # QSplitter lets the user resize the two panes.
        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Vertical)

        # ---- Report pane ----
        report_widget = QWidget()
        report_layout = QVBoxLayout(report_widget)
        report_layout.addWidget(QLabel(self._report_title))
        self.report_edit = QTextBrowser()
        self.report_edit.setOpenExternalLinks(True)
        report_layout.addWidget(self.report_edit)
        self.splitter.addWidget(report_widget)

        # ---- Output pane ----
        self.output_panel = OutputPanel(title=self._output_title)
        self.splitter.addWidget(self.output_panel)

        # Give the report more room by default.
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)

        root.addWidget(self.splitter)

    def set_report_text(self, text: str) -> None:
        """Show plain text in the report pane."""
        self.report_edit.setPlainText(text)

    def set_report_html(self, html: str) -> None:
        """Show HTML in the report pane."""
        self.report_edit.setHtml(html)

    def set_output_text(self, text: str) -> None:
        """Forward text to the lower output panel."""
        self.output_panel.set_text(text)

    def get_output_panel(self) -> OutputPanel:
        """Return the underlying OutputPanel (used by save/copy shortcuts)."""
        return self.output_panel

    def get_nested_splitter(self) -> Optional[QSplitter]:
        """Return the internal report/output splitter so its size can persist."""
        return self.splitter

    def clear_output(self) -> None:
        """Clear both panes."""
        self.report_edit.clear()
        self.output_panel.clear()
