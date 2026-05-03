"""
Вкладка статистики по списку префиксов.
"""

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .base_operation_tab import BaseOperationTab
from ..models import StatsResult
from ..services import run_stats
from ..widgets.input_panel import InputPanel
from ..workers import Worker


class StatsTab(BaseOperationTab):
    """Вкладка сбора и отображения статистики."""

    def __init__(self) -> None:
        """Инициализирует вкладку и создает элементы интерфейса."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Создает структуру вкладки."""
        self.control_layout.addWidget(
            QLabel("Show statistics for a prefix list.")
        )

        self.input_panel = InputPanel(
            title="Source",
            file_label="Input file",
            text_placeholder="Paste prefixes here...",
        )
        self.control_layout.addWidget(self.input_panel)

        controls_row = QHBoxLayout()
        self.show_details = QCheckBox("Show details")
        controls_row.addWidget(self.show_details)
        controls_row.addStretch()
        self.run_button = QPushButton("Run Stats")
        self.run_button.setProperty("primary", True)
        controls_row.addWidget(self.run_button)
        self.control_layout.addLayout(controls_row)

        table_group = QGroupBox("Statistics preview")
        table_layout = QVBoxLayout(table_group)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Metric", "Value"])
        table_layout.addWidget(self.table)
        self.control_layout.addWidget(table_group)

        self._setup_splitter(self.output_panel)

        self.run_button.clicked.connect(self._run_stats)
        self.input_panel.source_changed.connect(self._update_state)
        self._update_state()

    def _update_state(self, _: Any = None) -> None:
        """Обновляет доступность кнопки запуска."""
        self.run_button.setEnabled(
            self.input_panel.get_data_source() is not None
        )

    def _run_stats(self) -> None:
        """Запускает сбор статистики в фоновом потоке."""
        source = self.input_panel.get_data_source()
        if source is None:
            return

        self._set_running_state("Calculating stats...")

        worker = Worker(run_stats, source)
        worker.signals.result.connect(self._on_stats_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_stats_result(self, result: StatsResult) -> None:
        """
        Заполняет таблицу статистикой и выводит детали.

        Args:
            result: Результат сбора статистики.
        """
        self._expand_output()
        show = self.show_details.isChecked()

        row_count = 6
        if show:
            row_count += 1
            if result.duplicates:
                row_count += 1

        self.table.setRowCount(row_count)
        self.table.setItem(
            0, 0, QTableWidgetItem("Original prefix count")
        )
        self.table.setItem(
            0, 1, QTableWidgetItem(str(result.original_prefix_count))
        )
        self.table.setItem(
            1, 0, QTableWidgetItem("Optimized prefix count")
        )
        self.table.setItem(
            1, 1, QTableWidgetItem(str(result.optimized_prefix_count))
        )
        self.table.setItem(2, 0, QTableWidgetItem("Compression ratio"))
        self.table.setItem(
            2,
            1,
            QTableWidgetItem(f"{result.compression_ratio_percent}%"),
        )
        self.table.setItem(3, 0, QTableWidgetItem("Original total IPs"))
        self.table.setItem(
            3, 1, QTableWidgetItem(f"{result.original_total_ips:,}")
        )
        self.table.setItem(4, 0, QTableWidgetItem("Unique IPs"))
        self.table.setItem(
            4, 1, QTableWidgetItem(f"{result.unique_ips:,}")
        )
        self.table.setItem(5, 0, QTableWidgetItem("Addresses saved"))
        self.table.setItem(
            5, 1, QTableWidgetItem(f"{result.addresses_saved:,}")
        )

        detail_lines = []

        if show:
            self.table.setItem(
                6, 0, QTableWidgetItem("IPv4 / IPv6 count")
            )
            self.table.setItem(
                6,
                1,
                QTableWidgetItem(
                    f"{result.ipv4_count} / {result.ipv6_count}"
                ),
            )
            if result.duplicates:
                self.table.setItem(
                    7, 0, QTableWidgetItem("Duplicate prefixes")
                )
                self.table.setItem(
                    7, 1, QTableWidgetItem(str(len(result.duplicates)))
                )
                detail_lines.append("Duplicate Prefixes:")
                for prefix, count in result.duplicates:
                    detail_lines.append(f"  {prefix}  ({count} times)")
            else:
                self.table.setRowCount(row_count - 1)
        else:
            detail_lines.append(
                "Details hidden. Enable 'Show details' to see "
                "IPv4/IPv6 counts and duplicate prefixes."
            )

        self.table.resizeColumnsToContents()

        if detail_lines:
            self.output_panel.set_text("\n".join(detail_lines))
        else:
            self.output_panel.clear()

        self.progress_panel.set_status("Done")

    def _on_error(self, error_msg: str) -> None:
        """
        Отображает сообщение об ошибке.

        Args:
            error_msg: Текст ошибки.
        """
        self.output_panel.set_text(f"Error: {error_msg}")
        self.progress_panel.set_status("Error")

    def _on_finished(self) -> None:
        """Восстанавливает интерфейс."""
        self._restore_idle_state()

    def trigger_open(self) -> None:
        """Открывает диалог выбора файла."""
        self.input_panel.browse_button.click()

    def trigger_run(self) -> None:
        """Запускает сбор статистики."""
        if self.run_button.isEnabled():
            self.run_button.click()

    def save_settings(self) -> dict:
        """
        Сохраняет параметры вкладки.

        Returns:
            Словарь с настройками.
        """
        return {
            "show_details": self.show_details.isChecked(),
        }

    def load_settings(self, state: dict) -> None:
        """
        Восстанавливает параметры вкладки.

        Args:
            state: Словарь с настройками.
        """
        if not state:
            return
        self.show_details.setChecked(state.get("show_details", False))