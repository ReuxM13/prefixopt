"""
Панель вывода результата с поддержкой plain text, HTML и пейджинации.

При превышении порога отображаемых строк показывается предупреждение.
Полный результат доступен через кнопку Save.
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

_PAGE_SIZE = 10_000


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
    """Панель вывода с пейджинацией, сохранением, копированием и отделением."""

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
        self._full_text: str = ""
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

        group_layout.addLayout(toolbar)
        group_layout.addWidget(self.output_edit)
        root.addWidget(group)

        self._detach_manager = DetachableWidgetManager(self, self._detach_btn)
        self._update_line_count()

    def set_text(self, text: str) -> None:
        """
        Устанавливает plain text с применением пейджинации.

        Первые _PAGE_SIZE строк отображаются сразу. При превышении
        порога добавляется уведомление. Полный текст сохраняется
        для операции Save.

        Args:
            text: Текст для отображения.
        """
        clean = strip_rich_tags(text)
        self._full_text = clean

        lines = clean.splitlines()
        total = len(lines)

        if total > _PAGE_SIZE:
            preview = "\n".join(lines[:_PAGE_SIZE])
            notice = (
                f"\n\n--- Showing {_PAGE_SIZE:,} of {total:,} lines. "
                f'Use "Save..." to export the full result. ---'
            )
            self.output_edit.setPlainText(preview + notice)
        else:
            self.output_edit.setPlainText(clean)

        self._update_line_count(total)

    def set_html(self, html: str) -> None:
        """
        Устанавливает HTML-содержимое в область вывода.

        Args:
            html: HTML-текст для отображения.
        """
        self._full_text = self.output_edit.toPlainText()
        self.output_edit.setHtml(html)
        self._update_line_count()

    def append_text(self, text: str) -> None:
        """
        Добавляет plain text в конец текущего содержимого.

        Args:
            text: Текст для добавления.
        """
        clean = strip_rich_tags(text)
        current = self._full_text

        combined = f"{current}\n{clean}" if current else clean
        self.set_text(combined)

    def get_text(self) -> str:
        """
        Возвращает полное содержимое как plain text.

        Returns:
            Полный текст без ограничений пейджинации.
        """
        return self._full_text

    def clear(self) -> None:
        """Очищает область вывода и внутренний буфер."""
        self._full_text = ""
        self.output_edit.clear()
        self._update_line_count(0)

    def _update_line_count(self, total: Optional[int] = None) -> None:
        """
        Обновляет счетчик строк.

        Args:
            total: Общее количество строк полного текста.
                   Если None, подсчитывается из текущего содержимого.
        """
        if total is None:
            text = self._full_text
            total = len(text.splitlines()) if text else 0

        self.line_count_label.setText(f"Lines: {total:,}")

    def _copy_to_clipboard(self) -> None:
        """Копирует полный текст в буфер обмена."""
        QApplication.clipboard().setText(self._full_text)

    def _save_to_file(self) -> None:
        """Сохраняет полный текст в файл."""
        if not self._full_text:
            QMessageBox.information(
                self,
                "Nothing to save",
                "There is no output to save.",
            )
            return

        file_name, _ = QFileDialog.getSaveFileName(self, "Save output")
        if not file_name:
            return

        Path(file_name).write_text(self._full_text, encoding="utf-8")