"""
Progress panel shown at the bottom of each operation tab.

Contains a status label, an indeterminate progress bar (busy indicator) and a
Cancel button. The progress bar uses a range of (0, 0) which Qt renders as a
continuous "marquee" animation suitable for tasks without percentage progress.
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
    """Bottom status/progress/cancel bar shared by all operation tabs."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialise the component."""
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Construct and lay out the child widgets."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self.status_label = QLabel("Ready")
        # 0..0 range = indeterminate/busy mode.
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
        """Update the textual status message."""
        self.status_label.setText(text)

    def set_busy(self, busy: bool) -> None:
        """Toggle the busy indicator and the Cancel button's enabled state."""
        self.progress_bar.setVisible(busy)
        self.cancel_button.setEnabled(busy)

    def reset(self) -> None:
        """Return the panel to its initial idle state."""
        self.set_status("Ready")
        self.set_busy(False)
