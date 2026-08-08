"""
Detach/attach behaviour for panels that can be "popped out" into a window.

Used by InputPanel's "Pop out" button. The manager remembers where the widget
lived (a plain layout or a QSplitter index) so it can be re-inserted at the
same place when the user closes the popup or clicks "Dock back".
"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QFrame,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


class DetachablePopup(QFrame):
    """Floating top-level window that hosts the detached widget."""

    def __init__(self, manager, widget, parent=None):
        """Initialise the component."""
        super().__init__(parent)
        self.manager = manager
        self.widget = widget
        # Don't destroy the widget when the popup closes - we re-parent it back.
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        """When the popup is closed by the user, dock the widget back."""
        if obj == self and event.type() == QEvent.Close:
            self.manager.attach()
            return True
        return super().eventFilter(obj, event)


class DetachableWidgetManager:
    """Toggles a widget between its parent container and a floating window."""

    def __init__(self, widget: QWidget, button: QPushButton) -> None:
        """Initialise the component."""
        self.widget = widget
        # The button's label/text is updated to reflect the current state.
        self.button = button
        self.popup_window = None

        # Remember the original insertion point so we can restore it exactly.
        self.original_parent = widget.parentWidget()
        self.is_splitter = False
        self.original_splitter = None
        self.original_layout = None
        self.original_index = -1

        self.button.clicked.connect(self._toggle)

    def _toggle(self) -> None:
        """Switch between detached and attached state."""
        if self.popup_window is not None:
            self.attach()
        else:
            self.detach()

    def detach(self) -> None:
        """Reparent the widget into a new floating window."""
        parent_widget = self.widget.parentWidget()
        if parent_widget:
            if isinstance(parent_widget, QSplitter):
                # For splitters we remember the index rather than a layout.
                self.is_splitter = True
                self.original_splitter = parent_widget
                self.original_index = parent_widget.indexOf(self.widget)
                self.widget.hide()
                self.widget.setParent(None)
            else:
                # Plain QLayout: record the index, then remove the widget.
                self.is_splitter = False
                self.original_layout = parent_widget.layout()
                if self.original_layout:
                    self.original_index = self.original_layout.indexOf(
                        self.widget
                    )
                    self.original_layout.removeWidget(self.widget)

        self.popup_window = DetachablePopup(self, self.widget)
        self.popup_window.setWindowTitle(
            self.widget.windowTitle() or "Detached"
        )
        self.popup_window.setWindowFlags(Qt.Window)
        self.popup_window.resize(
            self.widget.size().expandedTo(
                self.popup_window.minimumSizeHint()
            )
        )

        layout = QVBoxLayout(self.popup_window)
        layout.addWidget(self.widget)

        dock_btn = QPushButton("⮌ Dock back")
        dock_btn.clicked.connect(self.attach)
        layout.addWidget(dock_btn)

        self.widget.show()
        self.popup_window.show()
        self.button.setText("⮌ Dock")
        self.button.setToolTip("Return panel to original place")

    def attach(self) -> None:
        """Return the widget to its original container and close the popup."""
        if self.popup_window is None:
            return

        # Remove the widget from the popup layout before re-parenting it.
        popup_layout = self.popup_window.layout()
        if popup_layout:
            popup_layout.removeWidget(self.widget)

        self.widget.setParent(None)

        self.popup_window.close()
        self.popup_window = None

        # Re-insert at the remembered location.
        if self.is_splitter and self.original_splitter:
            self.original_splitter.insertWidget(
                self.original_index, self.widget
            )
            self.widget.show()
            self.original_splitter = None
        elif self.original_layout:
            # Clamp the index in case other widgets were added meanwhile.
            if (
                self.original_index < 0
                or self.original_index > self.original_layout.count()
            ):
                self.original_index = -1
            self.original_layout.insertWidget(
                self.original_index, self.widget
            )
            self.widget.show()
            self.original_layout.invalidate()
            self.original_layout.activate()
            self.original_layout = None

        self.button.setText("↗ Pop out")
        self.button.setToolTip("Open in separate window")
