"""
Виджет с вертикальным сплиттером для отчёта и вывода, с возможностью отделения.
"""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QPlainTextEdit, QPushButton

from .output_panel import OutputPanel
from .detachable_manager import DetachableWidgetManager


class SplitOutputPanel(QWidget):
    """
    Панель, содержащая две области: верхнюю для структурированного отчёта (только текст)
    и нижнюю — OutputPanel с кнопками Save/Copy/Clear.
    """

    def __init__(
        self,
        report_title: str = "Structured report",
        output_title: str = "Output",
        parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._report_title = report_title
        self._output_title = output_title
        self._detach_btn: Optional[QPushButton] = None
        self._detach_manager: Optional[DetachableWidgetManager] = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ---- Toolbar с кнопкой Pop out ----
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        self._detach_btn = QPushButton("↗ Pop out")
        toolbar.addWidget(self._detach_btn)
        layout.addLayout(toolbar)

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)

        self.report_edit = QPlainTextEdit()
        self.report_edit.setReadOnly(True)
        self.report_edit.setPlaceholderText(f"{self._report_title} will appear here.")
        self.splitter.addWidget(self.report_edit)

        self.output_panel = OutputPanel(title=self._output_title)
        self.splitter.addWidget(self.output_panel)

        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 3)

        layout.addWidget(self.splitter)

        self._detach_manager = DetachableWidgetManager(self, self._detach_btn)

    # Методы для отчёта и вывода остаются без изменений
    def set_report_text(self, text: str) -> None:
        self.report_edit.setPlainText(text)

    def append_report_text(self, text: str) -> None:
        current = self.report_edit.toPlainText()
        if current:
            self.report_edit.setPlainText(current + "\n" + text)
        else:
            self.report_edit.setPlainText(text)

    def clear_report(self) -> None:
        self.report_edit.clear()

    def get_output_panel(self) -> OutputPanel:
        return self.output_panel

    def set_output_text(self, text: str) -> None:
        self.output_panel.set_text(text)

    def clear_output(self) -> None:
        self.output_panel.clear()