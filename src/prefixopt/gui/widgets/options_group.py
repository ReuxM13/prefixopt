"""
Простой контейнер для группировки опций.
"""
from typing import Optional

from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QWidget


class OptionsGroup(QGroupBox):
    """
    Универсальная группа опций.
    """

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(title, parent)
        self._layout = QVBoxLayout(self)

    def add_widget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)