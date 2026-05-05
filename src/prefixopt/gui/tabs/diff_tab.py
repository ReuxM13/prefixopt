"""
Вкладка семантического сравнения двух источников префиксов.
"""

from typing import Any

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from .base_operation_tab import BaseOperationTab
from ..models import DiffReport
from ..services import run_diff
from ..widgets.input_panel import InputPanel
from ..widgets.options_group import OptionsGroup
from ..workers import Worker


class DiffTab(BaseOperationTab):
    """Вкладка сравнения двух источников и отображения различий."""

    def __init__(self) -> None:
        """Инициализирует вкладку и создает элементы интерфейса."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Создает элементы управления вкладки и подключает сигналы."""
        desc = QLabel(
            "Compare two sources and show added, removed "
            "and unchanged prefixes."
        )
        desc.setProperty("role", "description")
        desc.setWordWrap(True)
        self.control_layout.addWidget(desc)

        self.new_input = InputPanel(
            title="New source",
            file_label="New file",
            text_placeholder="Paste new source prefixes here...",
        )
        self.old_input = InputPanel(
            title="Old source",
            file_label="Old file",
            text_placeholder="Paste old source prefixes here...",
        )

        self.control_layout.addWidget(self.new_input)
        self.control_layout.addWidget(self.old_input)

        options = OptionsGroup("Diff options")

        self.mode = QComboBox()
        self.mode.addItems(["changes", "added", "removed", "unchanged", "all"])
        self.mode.setToolTip("Select which categories of changes to display")

        self.summary_only = QCheckBox("Summary only")
        self.summary_only.setToolTip("Show only counts, not individual prefixes")

        self.ipv4_only = QCheckBox("IPv4 only")
        self.ipv4_only.setToolTip("Process only IPv4 prefixes, skip IPv6")

        self.ipv6_only = QCheckBox("IPv6 only")
        self.ipv6_only.setToolTip("Process only IPv6 prefixes, skip IPv4")

        self.strict = QCheckBox("Strict mode")
        self.strict.setToolTip(
            "Reject prefixes with incorrect subnet masks"
        )

        form = QFormLayout()
        form.addRow("Mode:", self.mode)
        form.addRow(self.summary_only)
        form.addRow(self.ipv4_only)
        form.addRow(self.ipv6_only)
        form.addRow(self.strict)

        options.add_layout(form)
        self.control_layout.addWidget(options)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Diff")
        self.run_button.setProperty("primary", True)
        self.run_button.setToolTip("Ctrl+R")
        run_row.addStretch()
        run_row.addWidget(self.run_button)

        self.control_layout.addLayout(run_row)

        self._setup_splitter(self.output_panel)

        self.new_input.source_changed.connect(self._update_state)
        self.old_input.source_changed.connect(self._update_state)
        self.run_button.clicked.connect(self._run_diff)

        self._update_state()

    def _is_dark_theme(self) -> bool:
        """
        Определяет активную тему по яркости фона палитры.

        Returns:
            True для тёмной темы.
        """
        bg = self.palette().color(QPalette.ColorRole.Window)
        luminance = 0.299 * bg.redF() + 0.587 * bg.greenF() + 0.114 * bg.blueF()
        return luminance < 0.5

    def _get_diff_colors(self) -> dict:
        """
        Возвращает набор цветов для diff-отчета, адаптированный к текущей теме.

        Returns:
            Словарь с ключами added, removed, unchanged.
        """
        if self._is_dark_theme():
            return {
                "added": "#4ec9b0",
                "removed": "#f44747",
                "unchanged": "#569cd6",
            }
        return {
            "added": "#22863a",
            "removed": "#cb2431",
            "unchanged": "#0366d6",
        }

    def _update_state(self, _: Any = None) -> None:
        """Обновляет доступность кнопки запуска."""
        self.run_button.setEnabled(
            self.new_input.get_data_source() is not None
            and self.old_input.get_data_source() is not None
        )

    def _run_diff(self) -> None:
        """Запускает задачу сравнения в фоновом потоке."""
        new_source = self.new_input.get_data_source()
        old_source = self.old_input.get_data_source()

        if new_source is None or old_source is None:
            return

        worker = Worker(
            run_diff,
            new_source,
            old_source,
            ipv4_only=self.ipv4_only.isChecked(),
            ipv6_only=self.ipv6_only.isChecked(),
            strict=self.strict.isChecked(),
        )
        worker.signals.result.connect(self._on_diff_result)
        worker.signals.error.connect(self._on_error)
        self._start_worker(worker, "Calculating diff...")

    def _on_diff_result(self, result: DiffReport) -> None:
        """
        Формирует и отображает отчет diff.

        Args:
            result: Результат сравнения источников.
        """
        self._expand_output()

        mode = self.mode.currentText()
        summary_only = self.summary_only.isChecked()
        colors = self._get_diff_colors()

        show_added = mode in ("changes", "added", "all")
        show_removed = mode in ("changes", "removed", "all")
        show_unchanged = mode in ("unchanged", "all")

        if summary_only:
            html_parts = []

            if show_added:
                html_parts.append(
                    f'<b style="color:{colors["added"]}">Added:</b> '
                    f"{len(result.added)}<br>"
                )
            if show_removed:
                html_parts.append(
                    f'<b style="color:{colors["removed"]}">Removed:</b> '
                    f"{len(result.removed)}<br>"
                )
            if show_unchanged:
                html_parts.append(
                    f'<b style="color:{colors["unchanged"]}">Unchanged:</b> '
                    f"{len(result.unchanged)}<br>"
                )

            if not html_parts:
                html_parts.append("No differences in selected mode.")

            self.output_panel.set_html("".join(html_parts))
        else:
            body_parts = []

            if show_added and result.added:
                body_parts.append(
                    f'<p><b style="color:{colors["added"]};">'
                    f"+++ Added ({len(result.added)}):</b></p>"
                )
                for net in result.added:
                    body_parts.append(
                        f'<span style="color:{colors["added"]};">'
                        f"+ {net}</span><br>"
                    )
                body_parts.append("<br>")

            if show_removed and result.removed:
                body_parts.append(
                    f'<p><b style="color:{colors["removed"]};">'
                    f"--- Removed ({len(result.removed)}):</b></p>"
                )
                for net in result.removed:
                    body_parts.append(
                        f'<span style="color:{colors["removed"]};">'
                        f"- {net}</span><br>"
                    )
                body_parts.append("<br>")

            if show_unchanged and result.unchanged:
                body_parts.append(
                    f'<p><b style="color:{colors["unchanged"]};">'
                    f"=== Unchanged ({len(result.unchanged)}):</b></p>"
                )
                for net in result.unchanged:
                    body_parts.append(
                        f'<span style="color:{colors["unchanged"]};">'
                        f"= {net}</span><br>"
                    )
                body_parts.append("<br>")

            if not body_parts:
                body_parts.append("<p>No differences in selected mode.</p>")

            html = (
                '<html><body style="font-family: Consolas, '
                "'Courier New', monospace;\">"
                f'{"".join(body_parts)}'
                "</body></html>"
            )
            self.output_panel.set_html(html)

        self.progress_panel.set_status(
            f"Done. Added: {len(result.added)}, "
            f"Removed: {len(result.removed)}, "
            f"Unchanged: {len(result.unchanged)}"
        )

    def trigger_open(self) -> None:
        """Открывает диалог выбора файла для первого незаполненного источника."""
        if self.new_input.get_data_source() is None:
            self.new_input.browse_button.click()
            return
        self.old_input.browse_button.click()

    def trigger_run(self) -> None:
        """Запускает сравнение."""
        if self.run_button.isEnabled():
            self.run_button.click()

    def save_settings(self) -> dict:
        """
        Сохраняет параметры вкладки.

        Returns:
            Словарь с текущими настройками.
        """
        return {
            "mode": self.mode.currentText(),
            "summary_only": self.summary_only.isChecked(),
            "ipv4_only": self.ipv4_only.isChecked(),
            "ipv6_only": self.ipv6_only.isChecked(),
            "strict": self.strict.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        """
        Восстанавливает параметры вкладки.

        Args:
            state: Словарь с сохраненными настройками.
        """
        if not state:
            return

        mode = state.get("mode", "changes")
        index = self.mode.findText(mode)
        if index >= 0:
            self.mode.setCurrentIndex(index)

        self.summary_only.setChecked(state.get("summary_only", False))
        self.ipv4_only.setChecked(state.get("ipv4_only", False))
        self.ipv6_only.setChecked(state.get("ipv6_only", False))
        self.strict.setChecked(state.get("strict", False))