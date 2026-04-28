"""
Панель статуса и прогресса.
"""
from typing import Optional

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar, QPushButton


class ProgressPanel(QWidget):
    """
    Панель состояния выполнения.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)

        self.status_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar, 1)
        layout.addWidget(self.cancel_button)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_busy(self, busy: bool) -> None:
        self.progress_bar.setVisible(busy)
        self.cancel_button.setEnabled(busy)

    def reset(self) -> None:
        self.set_status("Ready")
        self.set_busy(False)