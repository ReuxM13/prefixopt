"""Tiny wrapper around QGroupBox that exposes a simple vertical layout."""

from typing import Optional

from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QWidget


class OptionsGroup(QGroupBox):
    """A titled group box with a vertical box layout for option controls."""

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        """Initialise the component."""
        super().__init__(title, parent)
        self._layout = QVBoxLayout(self)

    def add_widget(self, widget: QWidget) -> None:
        """Append a widget to the group's layout."""
        self._layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        """Append a nested layout to the group's layout."""
        self._layout.addLayout(layout)
