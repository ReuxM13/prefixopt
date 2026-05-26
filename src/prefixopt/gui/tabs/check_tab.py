"""
Вкладка проверки вхождения адреса или подсети в список.
"""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from .. import LOG_DIR
from .base_operation_tab import BaseOperationTab
from ..models import CheckResult
from ..services import run_check
from ..widgets.input_panel import InputPanel
from ..widgets.prefix_input_widget import PrefixInputWidget
from ..widgets.split_output_panel import SplitOutputPanel
from ..workers import Worker

logger = logging.getLogger("prefixopt.gui.tab.check")


class CheckTab(BaseOperationTab):
    """Вкладка проверки вхождения адреса в список."""

    def __init__(self) -> None:
        """Инициализирует вкладку и создает элементы интерфейса."""
        super().__init__()
        self._init_ui()

    @property
    def _error_display_widget(self) -> SplitOutputPanel:
        """Возвращает split_output для отображения ошибок."""
        return self.split_output

    def _on_error_cleanup(self) -> None:
        """Очищает область вывода после ошибки."""
        self.split_output.set_output_text("")

    def get_split_output_panel(self):
        """Возвращает split_output для вкладок с двойной панелью."""
        return self.split_output

    def _init_ui(self) -> None:
        """Создает структуру вкладки."""
        desc = QLabel(
            "Check whether an IP address or subnet is contained "
            "in the source list."
        )
        desc.setProperty("role", "description")
        desc.setWordWrap(True)
        self.control_layout.addWidget(desc)

        self.target_input = PrefixInputWidget(
            title="Target",
            label="IP address or prefix",
            placeholder="e.g. 10.1.1.1 or 10.0.0.0/24",
        )
        self.control_layout.addWidget(self.target_input)

        self.source_input = InputPanel(
            title="Source",
            file_label="Input file",
            text_placeholder="Paste prefixes here...",
        )
        self.control_layout.addWidget(self.source_input)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Check")
        self.run_button.setProperty("primary", True)
        self.run_button.setToolTip("Ctrl+R")
        run_row.addStretch()
        run_row.addWidget(self.run_button)
        self.control_layout.addLayout(run_row)

        self.split_output = SplitOutputPanel(
            report_title="Check result",
            output_title="Output (containing networks)",
        )
        self._setup_splitter(self.split_output)

        self.target_input.value_changed.connect(self._update_state)
        self.source_input.source_changed.connect(self._update_state)
        self.run_button.clicked.connect(self._run_check)

        self._update_state()

    def _is_dark_theme(self) -> bool:
        """
        Определяет активную тему по яркости фона палитры.

        Returns:
            True для тёмной темы.
        """
        bg = self.palette().color(QPalette.ColorRole.Window)
        luminance = (
            0.299 * bg.redF()
            + 0.587 * bg.greenF()
            + 0.114 * bg.blueF()
        )
        return luminance < 0.5

    def _build_found_html(self, result: CheckResult) -> str:
        """
        Формирует HTML-отчёт для успешного результата поиска.

        Args:
            result: Результат проверки.

        Returns:
            HTML-строка отчёта.
        """
        dark = self._is_dark_theme()

        if dark:
            color_found = "#4ec9b0"
            color_net = "#569cd6"
            color_bg = "#1e1e1e"
            color_text = "#d4d4d4"
        else:
            color_found = "#107c10"
            color_net = "#0078d4"
            color_bg = "#ffffff"
            color_text = "#1e1e1e"

        parts = [
            f'<html><body style="font-family: Consolas, monospace; '
            f'font-size: 10pt; color: {color_text}; '
            f'background-color: {color_bg}; margin: 6px;">'
        ]

        parts.append(
            f'<p style="font-size: 11pt; color: {color_found}; '
            f'font-weight: bold;">'
            f"✔ '{result.target}' is contained in the source list</p>"
        )
        parts.append(
            f"<p>Found in "
            f'<b style="color: {color_found};">'
            f"{len(result.containing_networks)}</b> network(s):</p>"
        )

        parts.append("<ul style='margin: 4px 0;'>")
        for net in result.containing_networks:
            parts.append(
                f'<li style="color: {color_net};">{net}</li>'
            )
        parts.append("</ul>")

        parts.append("</body></html>")
        return "".join(parts)

    def _build_not_found_html(self, result: CheckResult) -> str:
        """
        Формирует HTML-отчёт для отрицательного результата поиска.

        Args:
            result: Результат проверки.

        Returns:
            HTML-строка отчёта.
        """
        dark = self._is_dark_theme()
        color_not = "#f44747" if dark else "#cb2431"
        color_bg = "#1e1e1e" if dark else "#ffffff"
        color_text = "#d4d4d4" if dark else "#1e1e1e"

        return (
            f'<html><body style="font-family: Consolas, monospace; '
            f'font-size: 10pt; color: {color_text}; '
            f'background-color: {color_bg}; margin: 6px;">'
            f'<p style="font-size: 11pt; color: {color_not}; '
            f'font-weight: bold;">'
            f"✘ '{result.target}' is NOT contained in any network "
            f"from the source.</p>"
            f"</body></html>"
        )

    def _update_state(self, _: Any = None) -> None:
        """Обновляет доступность кнопки запуска."""
        self.run_button.setEnabled(
            self.target_input.get_value() is not None
            and self.source_input.get_data_source() is not None
        )

    def _run_check(self) -> None:
        """Собирает параметры и запускает проверку в фоновом потоке."""
        target = self.target_input.get_value()
        source = self.source_input.get_data_source()
        if target is None or source is None:
            return

        worker = Worker(run_check, target, source)
        worker.signals.result.connect(self._on_check_result)
        worker.signals.error.connect(self._on_error)
        self._start_worker(worker, "Checking...")

    def _on_check_result(self, result: CheckResult) -> None:
        """
        Отображает результат проверки.

        Args:
            result: Результат с информацией о вхождении.
        """
        self._expand_output()

        if result.found:
            self.split_output.set_report_html(
                self._build_found_html(result)
            )
            self.split_output.set_output_text(result.formatted_text)
            self.progress_panel.set_status(
                f"Found in {len(result.containing_networks)} network(s)"
            )
        else:
            self.split_output.set_report_html(
                self._build_not_found_html(result)
            )
            self.split_output.set_output_text("")
            self.progress_panel.set_status("Not found")

    def trigger_open(self) -> None:
        """Открывает диалог выбора файла."""
        self.source_input.browse_button.click()

    def trigger_run(self) -> None:
        """Запускает проверку."""
        if self.run_button.isEnabled():
            self.run_button.click()

    def save_settings(self) -> dict:
        """
        Сохраняет параметры вкладки.

        Returns:
            Словарь с настройками.
        """
        return {}

    def load_settings(self, state: dict) -> None:
        """
        Восстанавливает параметры вкладки.

        Args:
            state: Словарь с настройками.
        """
        pass