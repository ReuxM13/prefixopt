"""
Виджет для ввода одного префикса, IP или произвольного короткого значения.
"""
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QGroupBox


class PrefixInputWidget(QWidget):
    """
    Виджет одиночного текстового аргумента.
    """

    value_changed = Signal(str)  # ← изменено с Signal() на Signal(str)

    def __init__(
        self,
        title: str,
        label: str,
        placeholder: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._label = label
        self._placeholder = placeholder
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)

        group = QGroupBox(self._title)
        layout = QVBoxLayout(group)

        layout.addWidget(QLabel(self._label))

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(self._placeholder)
        self.line_edit.textChanged.connect(self._on_text_changed)  # ← промежуточный слот

        layout.addWidget(self.line_edit)
        root.addWidget(group)

    def _on_text_changed(self, text: str) -> None:
        self.value_changed.emit(text)

    def get_value(self) -> Optional[str]:
        value = self.line_edit.text().strip()
        return value if value else None

    def set_value(self, value: str) -> None:
        self.line_edit.setText(value)

    def clear(self) -> None:
        self.line_edit.clear()