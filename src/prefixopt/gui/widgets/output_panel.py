"""
Панель вывода результата с поддержкой plain text и HTML.
"""

import re
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .detachable_manager import DetachableWidgetManager


def strip_rich_tags(text: str) -> str:
    """
    Удаляет теги форматирования вида [tag]...[/tag].

    Args:
        text: Исходный текст.

    Returns:
        Текст без rich-тегов.
    """
    return re.sub(r"\[/?[a-zA-Z]+\]", "", text)


class OutputPanel(QWidget):
    """Панель вывода с действиями сохранения, копирования, очистки и отделения."""

    def __init__(
        self,
        title: str = "Output",
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Инициализирует панель вывода.

        Args:
            title: Заголовок панели.
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._title = title
        self._detach_btn: Optional[QPushButton] = None
        self._detach_manager: Optional[DetachableWidgetManager] = None
        self._init_ui()

    def _init_ui(self) -> None:
        """Создает структуру панели и подключает действия."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox(self._title)
        group_layout = QVBoxLayout(group)

        toolbar = QHBoxLayout()

        self.save_button = QPushButton("Save...")
        self.copy_button = QPushButton("Copy")
        self.clear_button = QPushButton("Clear")
        self.line_count_label = QLabel("Lines: 0")

        self._detach_btn = QPushButton("↗ Pop out")
        self._detach_btn.setCheckable(False)

        self.save_button.clicked.connect(self._save_to_file)
        self.copy_button.clicked.connect(self._copy_to_clipboard)
        self.clear_button.clicked.connect(self.clear)

        toolbar.addWidget(self.save_button)
        toolbar.addWidget(self.copy_button)
        toolbar.addWidget(self.clear_button)
        toolbar.addStretch()
        toolbar.addWidget(self.line_count_label)
        toolbar.addWidget(self._detach_btn)

        self.output_edit = QTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.textChanged.connect(self._update_line_count)

        group_layout.addLayout(toolbar)
        group_layout.addWidget(self.output_edit)
        root.addWidget(group)

        self._detach_manager = DetachableWidgetManager(self, self._detach_btn)
        self._update_line_count()

    def set_text(self, text: str) -> None:
        """
        Устанавливает plain text в область вывода.

        Args:
            text: Текст для отображения.
        """
        self.output_edit.setPlainText(strip_rich_tags(text))

    def set_html(self, html: str) -> None:
        """
        Устанавливает HTML-содержимое в область вывода.

        Args:
            html: HTML-текст для отображения.
        """
        self.output_edit.setHtml(html)

    def append_text(self, text: str) -> None:
        """
        Добавляет plain text в конец текущего содержимого.

        Args:
            text: Текст для добавления.
        """
        clean_text = strip_rich_tags(text)
        current = self.output_edit.toPlainText()

        if current:
            self.output_edit.setPlainText(f"{current}\n{clean_text}")
            return

        self.output_edit.setPlainText(clean_text)

    def get_text(self) -> str:
        """
        Возвращает текущее содержимое как plain text.

        Returns:
            Текст из области вывода.
        """
        return self.output_edit.toPlainText()

    def clear(self) -> None:
        """Очищает область вывода."""
        self.output_edit.clear()

    def _update_line_count(self) -> None:
        """Обновляет счетчик строк."""
        text = self.output_edit.toPlainText()
        if not text:
            self.line_count_label.setText("Lines: 0")
            return
        self.line_count_label.setText(f"Lines: {len(text.splitlines())}")

    def _copy_to_clipboard(self) -> None:
        """Копирует содержимое в буфер обмена как plain text."""
        QApplication.clipboard().setText(self.output_edit.toPlainText())

    def _save_to_file(self) -> None:
        """Сохраняет содержимое в файл."""
        text = self.output_edit.toPlainText()
        if not text:
            QMessageBox.information(
                self,
                "Nothing to save",
                "There is no output to save.",
            )
            return

        file_name, _ = QFileDialog.getSaveFileName(self, "Save output")
        if not file_name:
            return

        Path(file_name).write_text(text, encoding="utf-8")