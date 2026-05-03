"""
Панель статуса и индикации прогресса выполнения.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QWidget,
)


class ProgressPanel(QWidget):
    """Панель состояния с индикатором прогресса и кнопкой отмены."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Инициализирует панель прогресса.

        Args:
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Создает элементы панели."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self.status_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(16)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar, 1)
        layout.addWidget(self.cancel_button)

    def set_status(self, text: str) -> None:
        """
        Устанавливает текст статуса.

        Args:
            text: Текст для отображения.
        """
        self.status_label.setText(text)

    def set_busy(self, busy: bool) -> None:
        """
        Переключает состояние индикатора и кнопки отмены.

        Args:
            busy: True для активного состояния, False для покоя.
        """
        self.progress_bar.setVisible(busy)
        self.cancel_button.setEnabled(busy)

    def reset(self) -> None:
        """Сбрасывает панель в начальное состояние."""
        self.set_status("Ready")
        self.set_busy(False)