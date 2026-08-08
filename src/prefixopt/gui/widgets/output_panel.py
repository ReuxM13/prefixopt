"""
Output panel with Save/Copy/Clear actions and large-result paging.

Rich's console markup uses tags like ``[green]...[/green]``. Because results may
be rendered into a plain QTextEdit, those tags are stripped before display.
To keep the UI responsive on huge outputs, only the first ``_PAGE_SIZE`` lines
are rendered; the full text is retained in memory for Save/Copy.
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

# Maximum number of lines rendered in the widget. The full text is still
# available via get_text()/Save.
_PAGE_SIZE = 10_000
_PLACEHOLDER = "Results will appear here after running the operation."


def strip_rich_tags(text: str) -> str:
    """Remove Rich console markup tags (``[tag]`` / ``[/tag]``) from ``text``."""
    return re.sub(r"\[/?[a-zA-Z]+\]", "", text)


class OutputPanel(QWidget):
    """Read-only text output panel with a toolbar and line counter."""

    def __init__(
        self,
        title: str = "Output",
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialise the component."""
        super().__init__(parent)
        self._title = title
        # Full, untruncated text for copy/save operations.
        self._full_text: str = ""
        self._detach_btn: Optional[QPushButton] = None
        self._detach_manager: Optional[DetachableWidgetManager] = None
        self._init_ui()

    def _init_ui(self) -> None:
        """Construct and lay out the child widgets."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox(self._title)
        group_layout = QVBoxLayout(group)

        toolbar = QHBoxLayout()

        self.save_button = QPushButton("💾 Save...")
        self.copy_button = QPushButton("📋 Copy")
        self.clear_button = QPushButton("🗑 Clear")
        self.clear_button.setProperty("danger", True)
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
        self.output_edit.setPlaceholderText(_PLACEHOLDER)

        group_layout.addLayout(toolbar)
        group_layout.addWidget(self.output_edit)
        root.addWidget(group)

        self._detach_manager = DetachableWidgetManager(
            self, self._detach_btn
        )
        self._update_line_count(0)

    def set_text(self, text: str) -> None:
        """Set the displayed result, paging when there are too many lines."""
        clean = strip_rich_tags(text)
        self._full_text = clean

        lines = clean.splitlines()
        total = len(lines)

        if total > _PAGE_SIZE:
            # Show only the first page in the widget to stay responsive.
            preview = "\n".join(lines[:_PAGE_SIZE])
            notice = (
                f"\n\n--- Showing {_PAGE_SIZE:,} of {total:,} lines. "
                'Use "Save..." to export the full result. ---'
            )
            self.output_edit.setPlainText(preview + notice)
        else:
            self.output_edit.setPlainText(clean)

        self._update_line_count(total)

    def set_html(self, html: str) -> None:
        """Render HTML content (used by some rich reports)."""
        self.output_edit.setHtml(html)
        text = self.output_edit.toPlainText()
        self._full_text = text
        self._update_line_count()

    def append_text(self, text: str) -> None:
        """Append text to the current output."""
        clean = strip_rich_tags(text)
        current = self._full_text
        combined = f"{current}\n{clean}" if current else clean
        self.set_text(combined)

    def get_text(self) -> str:
        """Return the full (untruncated) output text."""
        return self._full_text

    def clear(self) -> None:
        """Empty the output."""
        self._full_text = ""
        self.output_edit.clear()
        self._update_line_count(0)

    def _update_line_count(self, total: Optional[int] = None) -> None:
        """Refresh the ``Lines: N`` label."""
        if total is None:
            text = self._full_text
            total = len(text.splitlines()) if text else 0
        self.line_count_label.setText(f"Lines: {total:,}")

    def _copy_to_clipboard(self) -> None:
        """Copy the full output text to the system clipboard."""
        QApplication.clipboard().setText(self._full_text)

    def _save_to_file(self) -> None:
        """Prompt for a path and write the full output there."""
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
