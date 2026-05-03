"""
Вкладка проверки вхождения адреса или подсети в список.
"""

from typing import Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from .base_operation_tab import BaseOperationTab
from ..models import CheckResult
from ..services import run_check
from ..widgets.input_panel import InputPanel
from ..widgets.prefix_input_widget import PrefixInputWidget
from ..widgets.split_output_panel import SplitOutputPanel
from ..workers import Worker


class CheckTab(BaseOperationTab):
    """Вкладка проверки вхождения адреса в список."""

    def __init__(self) -> None:
        """Инициализирует вкладку и создает элементы интерфейса."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Создает структуру вкладки."""
        self.control_layout.addWidget(
            QLabel(
                "Check whether an IP address or subnet is contained "
                "in the source list."
            )
        )

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

        self._set_running_state("Checking...")

        worker = Worker(run_check, target, source)
        worker.signals.result.connect(self._on_check_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_check_result(self, result: CheckResult) -> None:
        """
        Отображает результат проверки.

        Args:
            result: Результат с информацией о вхождении.
        """
        self._expand_output()

        if result.found:
            report_lines = [
                f"✓ '{result.target}' is contained in the "
                f"following networks:"
            ]
            for net in result.containing_networks:
                report_lines.append(f"  {net}")
            self.split_output.set_report_text("\n".join(report_lines))
            self.split_output.set_output_text(result.formatted_text)
            self.progress_panel.set_status(
                f"Found in {len(result.containing_networks)} network(s)"
            )
        else:
            self.split_output.set_report_text(
                f"✗ '{result.target}' is NOT contained in any "
                f"network from the source."
            )
            self.split_output.set_output_text("")
            self.progress_panel.set_status("Not found")

    def _on_error(self, error_msg: str) -> None:
        """
        Отображает сообщение об ошибке.

        Args:
            error_msg: Текст ошибки.
        """
        self.split_output.set_report_text(f"Error: {error_msg}")
        self.split_output.set_output_text("")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        """Восстанавливает интерфейс."""
        self._restore_idle_state()

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