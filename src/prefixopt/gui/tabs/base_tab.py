"""
Базовая вкладка GUI.
"""
from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
)

from ..widgets.input_panel import InputPanel
from ..widgets.output_panel import OutputPanel
from ..widgets.progress_panel import ProgressPanel


class BaseTab(QWidget):
    """
    Базовая вкладка для всех операций GUI.

    На текущем этапе обработка еще не подключена.
    """

    def __init__(
        self,
        title: str,
        description: str,
        button_text: str = "Run",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.title = title
        self.description = description
        self.button_text = button_text

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.description_label = QLabel(self.description)
        self.description_label.setWordWrap(True)

        self.input_panel = InputPanel(
            title="Input",
            text_placeholder="Paste prefixes or text here..."
        )

        self.run_button = QPushButton(self.button_text)
        self.run_button.setEnabled(False)

        self.progress_panel = ProgressPanel()
        self.output_panel = OutputPanel()

        layout.addWidget(self.description_label)
        layout.addWidget(self.input_panel)
        layout.addWidget(self.run_button)
        layout.addWidget(self.progress_panel)
        layout.addWidget(self.output_panel, 1)

        self.input_panel.source_changed.connect(self._update_run_state)
        self.run_button.clicked.connect(self._not_implemented_yet)

    def _update_run_state(self) -> None:
        self.run_button.setEnabled(self.input_panel.get_data_source() is not None)

    def _not_implemented_yet(self) -> None:
        self.output_panel.set_text(
            f"{self.title} is wired into the GUI shell.\n"
            f"Business logic will be connected in the next implementation stage."
        )