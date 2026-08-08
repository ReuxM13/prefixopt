"""
InputPanel: a reusable source selector used by every operation tab.

It supports two input modes:
    * File mode - a path selected via Browse, the Recent menu, or drag-and-drop.
    * Text mode - a free-form text area for pasting prefixes directly.

The panel exposes :meth:`get_data_source`, which returns either a ``Path``
(file mode) or a ``str`` (text mode). That value is then consumed by
:mod:`prefixopt.gui.services`, which knows how to load either kind of source.
"""

from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..settings_manager import SettingsManager
from .detachable_manager import DetachableWidgetManager

# Type returned by get_data_source: a file path, raw text, or None if empty.
InputSource = Union[Path, str, None]


class InputPanel(QWidget):
    """Widget for picking a prefix source (file or pasted text)."""

    # Emitted whenever the selected source changes (mode switch, file chosen,
    # text edited, etc.). Tabs use it to enable/disable the Run button.
    source_changed = Signal()

    def __init__(
        self,
        title: str = "Input",
        file_label: str = "Input file",
        text_placeholder: str = "Paste prefixes here...",
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialise the component."""
        super().__init__(parent)
        self._title = title
        self._file_label = file_label
        self._text_placeholder = text_placeholder
        self._selected_file: Optional[Path] = None
        self._detach_btn: Optional[QPushButton] = None
        self._detach_manager: Optional[DetachableWidgetManager] = None
        self._group_box: Optional[QGroupBox] = None
        self._init_ui()

    def title(self) -> str:
        """Return the panel's current group-box title."""
        return self._group_box.title() if self._group_box else self._title

    def set_title(self, new_title: str) -> None:
        """Update the panel's title (used to show a selected file name)."""
        if self._group_box:
            self._group_box.setTitle(new_title)

    def display_name(self) -> Optional[str]:
        """Return the file name of the selected file, or None in text mode."""
        if self._selected_file:
            return self._selected_file.name
        return None

    def _init_ui(self) -> None:
        """Build the child widgets and layout."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._group_box = QGroupBox(self._title)
        group_layout = QVBoxLayout(self._group_box)

        # Top-right "pop out" button that detaches the panel into a window.
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        self._detach_btn = QPushButton("↗ Pop out")
        toolbar.addWidget(self._detach_btn)

        # Mode switch: File vs Text.
        mode_layout = QHBoxLayout()
        self.file_mode_radio = QRadioButton("File")
        self.text_mode_radio = QRadioButton("Text")
        self.file_mode_radio.setChecked(True)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.file_mode_radio)
        self.mode_group.addButton(self.text_mode_radio)

        mode_layout.addWidget(QLabel("Input mode:"))
        mode_layout.addWidget(self.file_mode_radio)
        mode_layout.addWidget(self.text_mode_radio)
        mode_layout.addStretch()

        # QStackedWidget shows either the file page or the text page.
        self.stack = QStackedWidget()

        # ---- File page ----
        self.file_page = QWidget()
        file_layout = QVBoxLayout(self.file_page)

        file_row = QHBoxLayout()
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setPlaceholderText("No file selected")

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._browse_file)

        self.recent_button = QPushButton("Recent")
        self.recent_button.clicked.connect(self._show_recent_menu)

        file_row.addWidget(self.file_path_edit)
        file_row.addWidget(self.browse_button)
        file_row.addWidget(self.recent_button)

        self.drop_hint = QLabel("You can drag and drop a file here.")
        self.drop_hint.setStyleSheet("color: gray;")

        file_layout.addWidget(QLabel(self._file_label))
        file_layout.addLayout(file_row)
        file_layout.addWidget(self.drop_hint)

        # ---- Text page ----
        self.text_page = QWidget()
        text_layout = QVBoxLayout(self.text_page)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(self._text_placeholder)
        # Any keystroke counts as a source change.
        self.text_edit.textChanged.connect(self.source_changed.emit)

        text_layout.addWidget(self.text_edit)

        self.stack.addWidget(self.file_page)
        self.stack.addWidget(self.text_page)

        group_layout.addLayout(toolbar)
        group_layout.addLayout(mode_layout)
        group_layout.addWidget(self.stack)
        root.addWidget(self._group_box)

        self.file_mode_radio.toggled.connect(self._update_mode)
        # Enable OS drag-and-drop of files onto the panel.
        self.setAcceptDrops(True)
        self._update_mode()

        # The detach manager handles the pop-out/in behaviour.
        self._detach_manager = DetachableWidgetManager(self, self._detach_btn)

    def _update_mode(self) -> None:
        """Switch the stacked page based on the selected radio button."""
        if self.file_mode_radio.isChecked():
            self.stack.setCurrentWidget(self.file_page)
        else:
            self.stack.setCurrentWidget(self.text_page)
        self.source_changed.emit()

    def _browse_file(self) -> None:
        """Open a file dialog and select a file."""
        file_name, _ = QFileDialog.getOpenFileName(self, "Select file")
        if file_name:
            self.set_file(Path(file_name))

    def _show_recent_menu(self) -> None:
        """Pop up the recent-files menu under the Recent button."""
        menu = QMenu(self)
        recent_files = SettingsManager.instance().recent_files()
        if not recent_files:
            menu.addAction("(empty)").setEnabled(False)
        else:
            for path_str in recent_files:
                action = menu.addAction(path_str)
                # Default-arg capture is needed to bind the correct path in
                # the loop's lambda.
                action.triggered.connect(
                    lambda checked, p=path_str: self.set_file(Path(p))
                )
        menu.exec(
            self.recent_button.mapToGlobal(
                self.recent_button.rect().bottomLeft()
            )
        )

    def set_file(self, path: Path) -> None:
        """Programmatically select a file and record it in recent files."""
        self._selected_file = path
        self.file_path_edit.setText(str(path))
        SettingsManager.instance().add_recent_file(str(path))
        self.source_changed.emit()

    def get_data_source(self) -> InputSource:
        """Return the current source for use by the service layer.

        Returns a Path in file mode, a non-empty string in text mode, or
        None when no source is configured.
        """
        if self.file_mode_radio.isChecked():
            return self._selected_file
        text = self.text_edit.toPlainText().strip()
        return text if text else None

    def clear(self) -> None:
        """Reset the panel to an empty state."""
        self._selected_file = None
        self.file_path_edit.clear()
        self.text_edit.clear()
        self.source_changed.emit()

    # ---- Drag and drop ----

    def dragEnterEvent(self, event) -> None:
        """Accept a drag only when it carries a single local file."""
        mime = event.mimeData()
        if mime.hasUrls():
            urls = mime.urls()
            if len(urls) == 1 and urls[0].isLocalFile():
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event) -> None:
        """Handle a dropped file by switching to file mode and selecting it."""
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.file_mode_radio.setChecked(True)
            self.set_file(Path(urls[0].toLocalFile()))
            event.acceptProposedAction()
        else:
            event.ignore()

    def set_text_content(self, text: str) -> None:
        """Switch to text mode and fill the text area with ``text``."""
        self.text_mode_radio.setChecked(True)
        self.text_edit.setPlainText(text)

    # ---- State save/restore (used by swap and settings) ----

    def save_state(self) -> dict:
        """Serialise the panel's state to a plain dictionary."""
        return {
            "is_file_mode": self.file_mode_radio.isChecked(),
            "selected_file": self._selected_file,
            "file_path": self.file_path_edit.text(),
            "text_content": self.text_edit.toPlainText(),
        }

    def restore_state(self, state: dict) -> None:
        """Restore state previously produced by :meth:`save_state`."""
        try:
            # Block signals while restoring so we don't fire source_changed
            # repeatedly for every intermediate widget update.
            self.text_edit.blockSignals(True)
            self.file_mode_radio.blockSignals(True)
            self.text_mode_radio.blockSignals(True)

            was_file_mode = state.get("is_file_mode", True)
            self._selected_file = state.get("selected_file")
            self.file_path_edit.setText(state.get("file_path", ""))
            self.text_edit.setPlainText(state.get("text_content", ""))

            if was_file_mode:
                self.file_mode_radio.setChecked(True)
            else:
                self.text_mode_radio.setChecked(True)
        finally:
            self.text_edit.blockSignals(False)
            self.file_mode_radio.blockSignals(False)
            self.text_mode_radio.blockSignals(False)

        self.source_changed.emit()
