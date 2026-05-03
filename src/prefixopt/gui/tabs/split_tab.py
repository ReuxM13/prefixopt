"""
Вкладка разбиения сетей на подсети.
"""

from typing import Any

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
)

from .base_operation_tab import BaseOperationTab
from ..models import SplitResult
from ..services import run_split
from ..widgets.input_panel import InputPanel
from ..widgets.options_group import OptionsGroup
from ..workers import Worker


class SplitTab(BaseOperationTab):
    """Вкладка разбиения сетей на подсети."""

    def __init__(self) -> None:
        """Инициализирует вкладку и создает элементы интерфейса."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Создает структуру вкладки."""
        self.control_layout.addWidget(
            QLabel(
                "Split a network or a list of networks into smaller subnets."
            )
        )

        self.input_panel = InputPanel(
            title="Source",
            file_label="Input file",
            text_placeholder="Paste prefixes here...",
        )
        self.control_layout.addWidget(self.input_panel)

        options = OptionsGroup("Split options")
        self.target_length = QSpinBox()
        self.target_length.setRange(0, 128)
        self.target_length.setValue(24)

        form = QFormLayout()
        form.addRow("Target prefix length:", self.target_length)
        options.add_layout(form)

        self.control_layout.addWidget(options)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Split")
        self.run_button.setProperty("primary", True)
        run_row.addStretch()
        run_row.addWidget(self.run_button)

        self.control_layout.addLayout(run_row)

        self._setup_splitter(self.output_panel)

        self.run_button.clicked.connect(self._run_split)
        self.input_panel.source_changed.connect(self._update_state)

        self._update_state()

    def _update_state(self, _: Any = None) -> None:
        """Обновляет доступность кнопки запуска."""
        self.run_button.setEnabled(
            self.input_panel.get_data_source() is not None
        )

    def _run_split(self) -> None:
        """Собирает параметры и запускает разбиение в фоновом потоке."""
        source = self.input_panel.get_data_source()
        if source is None:
            return

        worker = Worker(run_split, source, self.target_length.value())
        worker.signals.result.connect(self._on_split_result)
        worker.signals.error.connect(self._on_error)
        self._start_worker(worker, "Splitting...")

    def _on_split_result(self, result: SplitResult) -> None:
        """
        Отображает результат разбиения.

        Args:
            result: Результат операции.
        """
        self._expand_output()
        self.output_panel.set_text(result.formatted_text)
        self.progress_panel.set_status(
            f"Done. Generated {result.total_count} subnets"
        )

    def trigger_open(self) -> None:
        """Открывает диалог выбора файла."""
        self.input_panel.browse_button.click()

    def trigger_run(self) -> None:
        """Запускает операцию разбиения."""
        if self.run_button.isEnabled():
            self.run_button.click()

    def save_settings(self) -> dict:
        """
        Сохраняет параметры вкладки.

        Returns:
            Словарь с настройками вкладки.
        """
        return {
            "target_length": self.target_length.value(),
        }

    def load_settings(self, state: dict) -> None:
        """
        Восстанавливает параметры вкладки.

        Args:
            state: Словарь с сохраненными настройками.
        """
        if not state:
            return
        self.target_length.setValue(int(state.get("target_length", 24)))