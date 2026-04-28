"""
Универсальная панель выбора одного источника данных с возможностью отделения и списком недавних файлов.
"""
from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QRadioButton,
    QButtonGroup, QFileDialog, QLineEdit, QPlainTextEdit, QStackedWidget, QGroupBox,
    QMenu
)

from .detachable_manager import DetachableWidgetManager
from ..settings_manager import SettingsManager

InputSource = Union[Path, str, None]


class InputPanel(QWidget):
    source_changed = Signal()

    def __init__(
        self,
        title: str = "Input",
        file_label: str = "Input file",
        text_placeholder: str = "Paste prefixes here...",
        parent: Optional[QWidget] = None,
    ) -> None:
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
        return self._group_box.title() if self._group_box else self._title

    def set_title(self, new_title: str) -> None:
        """Меняет заголовок группы."""
        if self._group_box:
            self._group_box.setTitle(new_title)

    def display_name(self) -> Optional[str]:
        """Возвращает имя файла (без пути), если выбран файл, иначе None."""
        if self._selected_file:
            return self._selected_file.name
        return None

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._group_box = QGroupBox(self._title)
        group_layout = QVBoxLayout(self._group_box)

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        self._detach_btn = QPushButton("↗ Pop out")
        toolbar.addWidget(self._detach_btn)

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

        self.stack = QStackedWidget()

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

        self.text_page = QWidget()
        text_layout = QVBoxLayout(self.text_page)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(self._text_placeholder)
        self.text_edit.textChanged.connect(self.source_changed.emit)

        text_layout.addWidget(self.text_edit)

        self.stack.addWidget(self.file_page)
        self.stack.addWidget(self.text_page)

        group_layout.addLayout(toolbar)
        group_layout.addLayout(mode_layout)
        group_layout.addWidget(self.stack)
        root.addWidget(self._group_box)

        self.file_mode_radio.toggled.connect(self._update_mode)
        self.setAcceptDrops(True)
        self._update_mode()

        self._detach_manager = DetachableWidgetManager(self, self._detach_btn)

    def _update_mode(self) -> None:
        if self.file_mode_radio.isChecked():
            self.stack.setCurrentWidget(self.file_page)
        else:
            self.stack.setCurrentWidget(self.text_page)
        self.source_changed.emit()

    def _browse_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, "Select file")
        if file_name:
            self.set_file(Path(file_name))

    def _show_recent_menu(self) -> None:
        menu = QMenu(self)
        recent_files = SettingsManager.instance().recent_files()
        if not recent_files:
            menu.addAction("(empty)").setEnabled(False)
        else:
            for path_str in recent_files:
                action = menu.addAction(path_str)
                action.triggered.connect(lambda checked, p=path_str: self.set_file(Path(p)))
        menu.exec(self.recent_button.mapToGlobal(self.recent_button.rect().bottomLeft()))

    def set_file(self, path: Path) -> None:
        self._selected_file = path
        self.file_path_edit.setText(str(path))
        SettingsManager.instance().add_recent_file(str(path))
        self.source_changed.emit()

    def get_data_source(self) -> InputSource:
        if self.file_mode_radio.isChecked():
            return self._selected_file
        text = self.text_edit.toPlainText().strip()
        return text if text else None

    def clear(self) -> None:
        self._selected_file = None
        self.file_path_edit.clear()
        self.text_edit.clear()
        self.source_changed.emit()

    def dragEnterEvent(self, event) -> None:
        mime = event.mimeData()
        if mime.hasUrls():
            urls = mime.urls()
            if len(urls) == 1 and urls[0].isLocalFile():
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.file_mode_radio.setChecked(True)
            self.set_file(Path(urls[0].toLocalFile()))
            event.acceptProposedAction()
        else:
            event.ignore()