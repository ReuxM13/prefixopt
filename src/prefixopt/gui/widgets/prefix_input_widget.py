"""
A labelled single-line input for one IP/prefix (used by Add and Exclude tabs).

Wraps a QGroupBox + QLabel + QLineEdit and emits :attr:`value_changed` on every
keystroke so tabs can enable/disable their Run button reactively.
"""

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class PrefixInputWidget(QWidget):
    """A compact labelled line edit for a prefix string."""

    # Emitted with the current (untrimmed) text whenever it changes.
    value_changed = Signal(str)

    def __init__(
        self,
        title: str,
        label: str,
        placeholder: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialise the component."""
        super().__init__(parent)
        self._title = title
        self._label = label
        self._placeholder = placeholder
        self._init_ui()

    def _init_ui(self) -> None:
        """Construct and lay out the child widgets."""
        root = QVBoxLayout(self)

        group = QGroupBox(self._title)
        layout = QVBoxLayout(group)

        layout.addWidget(QLabel(self._label))

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(self._placeholder)
        self.line_edit.textChanged.connect(self._on_text_changed)

        layout.addWidget(self.line_edit)
        root.addWidget(group)

    def _on_text_changed(self, text: str) -> None:
        """Forward the QLineEdit's textChanged signal."""
        self.value_changed.emit(text)

    def get_value(self) -> Optional[str]:
        """Return the trimmed text, or None if empty."""
        value = self.line_edit.text().strip()
        return value if value else None

    def set_value(self, value: str) -> None:
        """Programmatically set the line-edit text."""
        self.line_edit.setText(value)

    def clear(self) -> None:
        """Clear the line-edit contents."""
        self.line_edit.clear()
