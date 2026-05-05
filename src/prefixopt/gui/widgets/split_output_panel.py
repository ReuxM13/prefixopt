"""
Панель с вертикальным разделителем для структурированного отчета и вывода.

Верхняя область поддерживает HTML-рендеринг.
Нижняя область — OutputPanel с действиями Save/Copy/Clear.
"""

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .detachable_manager import DetachableWidgetManager
from .output_panel import OutputPanel


class SplitOutputPanel(QWidget):
    """Панель из двух областей: HTML-отчет и текстовый вывод со счётчиком строк."""

    def __init__(
        self,
        report_title: str = "Structured report",
        output_title: str = "Output",
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Инициализирует двойную панель вывода.

        Args:
            report_title: Заголовок верхней области отчета.
            output_title: Заголовок нижней области вывода.
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._report_title = report_title
        self._output_title = output_title
        self._detach_btn: Optional[QPushButton] = None
        self._detach_manager: Optional[DetachableWidgetManager] = None
        self._init_ui()

    def _init_ui(self) -> None:
        """Создает структуру панели с разделителем и счётчиком строк."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        self.report_line_count = QLabel("Lines: 0")
        toolbar.addWidget(self.report_line_count)
        toolbar.addStretch()
        self._detach_btn = QPushButton("↗ Pop out")
        toolbar.addWidget(self._detach_btn)
        layout.addLayout(toolbar)

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)

        self.report_edit = QTextEdit()
        self.report_edit.setReadOnly(True)
        self.report_edit.setPlaceholderText(
            f"{self._report_title} will appear here."
        )
        self.report_edit.textChanged.connect(self._update_report_line_count)
        self.splitter.addWidget(self.report_edit)

        self.output_panel = OutputPanel(title=self._output_title)
        self.splitter.addWidget(self.output_panel)

        self.report_edit.setMinimumHeight(0)
        self.output_panel.setMinimumHeight(0)

        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 7)

        QTimer.singleShot(0, lambda: self.splitter.setSizes([0, 0]))

        layout.addWidget(self.splitter)

        self._detach_manager = DetachableWidgetManager(self, self._detach_btn)

    def _update_report_line_count(self) -> None:
        """Обновляет счётчик строк области отчёта."""
        text = self.report_edit.toPlainText()
        count = len(text.splitlines()) if text else 0
        self.report_line_count.setText(f"Report lines: {count:,}")

    def set_report_text(self, text: str) -> None:
        """
        Устанавливает plain text в область отчета.

        Args:
            text: Текст отчета.
        """
        self.report_edit.setPlainText(text)

    def set_report_html(self, html: str) -> None:
        """
        Устанавливает HTML-содержимое в область отчета.

        Args:
            html: HTML-текст отчета.
        """
        self.report_edit.setHtml(html)

    def append_report_text(self, text: str) -> None:
        """
        Добавляет plain text в конец области отчета.

        Args:
            text: Текст для добавления.
        """
        current = self.report_edit.toPlainText()
        if current:
            self.report_edit.setPlainText(f"{current}\n{text}")
            return
        self.report_edit.setPlainText(text)

    def clear_report(self) -> None:
        """Очищает область отчета."""
        self.report_edit.clear()

    def get_output_panel(self) -> OutputPanel:
        """
        Возвращает ссылку на OutputPanel.

        Returns:
            OutputPanel нижней области.
        """
        return self.output_panel

    def set_output_text(self, text: str) -> None:
        """
        Устанавливает plain text в область вывода.

        Args:
            text: Текст для отображения.
        """
        self.output_panel.set_text(text)

    def clear_output(self) -> None:
        """Очищает область вывода."""
        self.output_panel.clear()