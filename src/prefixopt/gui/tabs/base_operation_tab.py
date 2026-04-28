"""
Базовый класс для всех вкладок с вертикальным сплиттером между управлением и выводом.
"""
from typing import Optional

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter

from ..widgets.output_panel import OutputPanel
from ..widgets.progress_panel import ProgressPanel


class BaseOperationTab(QWidget):
    """
    Базовая вкладка с вертикальным сплиттером.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.root_layout = QVBoxLayout(self)
        self.control_widget = QWidget()
        self.control_layout = QVBoxLayout(self.control_widget)
        self.control_layout.setContentsMargins(0, 0, 0, 0)
        
        self.progress_panel = ProgressPanel()
        self.output_panel = OutputPanel()
        self.threadpool = QThreadPool.globalInstance()
        self.splitter = None

    def _setup_splitter(self, output_widget: QWidget) -> None:
        """
        Создаёт вертикальный сплиттер между control_widget и output_widget.
        """
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.control_widget)
        self.splitter.addWidget(output_widget)
        
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 6)
        
        self.root_layout.addWidget(self.splitter)
        self.root_layout.addWidget(self.progress_panel)

    def _show_placeholder(self, title: str) -> None:
        self.output_panel.set_text(
            f"{title} is wired into the GUI shell.\n"
            f"Business logic will be connected in the next implementation stage."
        )

    def save_settings(self) -> dict:
        """Переопределяется в наследниках."""
        return {}

    def load_settings(self, state: dict) -> None:
        """Переопределяется в наследниках."""
        pass