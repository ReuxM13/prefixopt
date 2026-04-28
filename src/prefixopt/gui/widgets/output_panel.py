"""
Панель вывода результата с очисткой rich-тегов и возможностью отделения.
"""
import re
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QFileDialog, QLabel, QPlainTextEdit,
    QApplication, QMessageBox
)

from .detachable_manager import DetachableWidgetManager


def strip_rich_tags(text: str) -> str:
    """Удаляет теги форматирования rich вида [color]...[/color]."""
    return re.sub(r'\[/?[a-zA-Z]+\]', '', text)


class OutputPanel(QWidget):
    """
    Панель preview результата с действиями Save / Copy / Clear и Pop out.
    """

    def __init__(self, title: str = "Output", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._title = title
        self._detach_btn: Optional[QPushButton] = None
        self._detach_manager: Optional[DetachableWidgetManager] = None
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox(self._title)
        group_layout = QVBoxLayout(group)

        # ---- Toolbar ----
        toolbar = QHBoxLayout()

        self.save_button = QPushButton("Save...")
        self.copy_button = QPushButton("Copy")
        self.clear_button = QPushButton("Clear")

        # Кнопка отделения
        self._detach_btn = QPushButton("↗ Pop out")
        self._detach_btn.setCheckable(False)

        self.save_button.clicked.connect(self._save_to_file)
        self.copy_button.clicked.connect(self._copy_to_clipboard)
        self.clear_button.clicked.connect(self.clear)

        toolbar.addWidget(self.save_button)
        toolbar.addWidget(self.copy_button)
        toolbar.addWidget(self.clear_button)
        toolbar.addStretch()
        toolbar.addWidget(self._detach_btn)

        self.line_count_label = QLabel("Lines: 0")

        # ---- Output area ----
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)

        group_layout.addLayout(toolbar)
        group_layout.addWidget(self.output_edit)
        root.addWidget(group)

        self._detach_manager = DetachableWidgetManager(self, self._detach_btn)

        self._update_line_count()

    def set_text(self, text: str) -> None:
        """Устанавливает текст, предварительно удалив rich-теги."""
        clean_text = strip_rich_tags(text)
        self.output_edit.setPlainText(clean_text)
        self._update_line_count()

    def append_text(self, text: str) -> None:
        current = self.output_edit.toPlainText()
        clean_text = strip_rich_tags(text)
        if current:
            self.output_edit.setPlainText(current + "\n" + clean_text)
        else:
            self.output_edit.setPlainText(clean_text)
        self._update_line_count()

    def get_text(self) -> str:
        return self.output_edit.toPlainText()

    def clear(self) -> None:
        self.output_edit.clear()
        self._update_line_count()

    def _update_line_count(self) -> None:
        text = self.output_edit.toPlainText()
        if not text:
            self.line_count_label.setText("Lines: 0")
            return
        self.line_count_label.setText(f"Lines: {len(text.splitlines())}")

    def _copy_to_clipboard(self) -> None:
        QApplication.clipboard().setText(self.output_edit.toPlainText())

    def _save_to_file(self) -> None:
        text = self.output_edit.toPlainText()
        if not text:
            QMessageBox.information(self, "Nothing to save", "There is no output to save.")
            return
        file_name, _ = QFileDialog.getSaveFileName(self, "Save output")
        if not file_name:
            return
        Path(file_name).write_text(text, encoding="utf-8")