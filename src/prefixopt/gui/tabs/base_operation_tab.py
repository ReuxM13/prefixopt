from typing import Optional

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter, QScrollArea

from ..widgets.output_panel import OutputPanel
from ..widgets.progress_panel import ProgressPanel


class BaseOperationTab(QWidget):
    """
    Базовая вкладка с вертикальным сплиттером и прокруткой области управления.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.root_layout = QVBoxLayout(self)
        
        # Область управления с прокруткой
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        
        self.control_widget = QWidget()
        self.control_layout = QVBoxLayout(self.control_widget)
        self.control_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area.setWidget(self.control_widget)
        
        self.progress_panel = ProgressPanel()
        self.output_panel = OutputPanel()
        self.threadpool = QThreadPool.globalInstance()
        self.splitter = None

    def _setup_splitter(self, output_widget: QWidget) -> None:
        """
        Создаёт вертикальный сплиттер между областью управления (с прокруткой)
        и output_widget (может быть OutputPanel или SplitOutputPanel).
        """
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.scroll_area)
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