"""
Базовый класс для вкладок операций графического интерфейса.

Обеспечивает стандартную компоновку: область управления с прокруткой,
панель прогресса и область вывода. Содержит глобальный пул потоков
для выполнения ресурсоемких задач без блокировки основного потока.
"""

from typing import Optional

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import QScrollArea, QSplitter, QVBoxLayout, QWidget

from ..widgets.output_panel import OutputPanel
from ..widgets.progress_panel import ProgressPanel


class BaseOperationTab(QWidget):
    """Базовая вкладка операций с адаптивным разделителем и управлением состоянием."""

    _CONTROL_INITIAL_RATIO = 95
    _OUTPUT_INITIAL_RATIO = 5
    _CONTROL_RESULT_RATIO = 40
    _OUTPUT_RESULT_RATIO = 60

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Инициализирует базовую вкладку операций.

        Args:
            parent: Родительский виджет.
        """
        super().__init__(parent)

        self.root_layout = QVBoxLayout(self)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)

        self.control_widget = QWidget()
        self.control_layout = QVBoxLayout(self.control_widget)
        self.control_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area.setWidget(self.control_widget)

        self.progress_panel = ProgressPanel()
        self.output_panel = OutputPanel()

        self.threadpool = QThreadPool.globalInstance()
        self.splitter: Optional[QSplitter] = None
        self._result_received = False
        self._is_running = False

    def _setup_splitter(self, output_widget: QWidget) -> None:
        """
        Настраивает вертикальный разделитель между областью управления и выводом.

        При инициализации область управления занимает большую часть пространства,
        область вывода сжата до минимума. После первого получения результата
        пропорции перераспределяются.

        Args:
            output_widget: Виджет для отображения результатов.
        """
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.scroll_area)
        self.splitter.addWidget(output_widget)

        self.splitter.setStretchFactor(0, self._CONTROL_INITIAL_RATIO)
        self.splitter.setStretchFactor(1, self._OUTPUT_INITIAL_RATIO)

        self.root_layout.addWidget(self.splitter)
        self.root_layout.addWidget(self.progress_panel)

        QTimer.singleShot(0, self._apply_initial_sizes)

    def _apply_initial_sizes(self) -> None:
        """
        Устанавливает начальные пропорции разделителя.

        Область управления получает почти всю доступную высоту,
        область вывода остается минимальной.
        """
        if self.splitter is None:
            return

        total = self.splitter.height()
        if total <= 0:
            return

        control_height = int(total * self._CONTROL_INITIAL_RATIO / 100)
        output_height = total - control_height
        self.splitter.setSizes([control_height, output_height])

    def _expand_output(self) -> None:
        """
        Перераспределяет пропорции разделителя в пользу области вывода.

        Метод вызывается однократно после первого успешного получения результата.
        """
        if self._result_received or self.splitter is None:
            return

        self._result_received = True

        total = self.splitter.height()
        if total <= 0:
            return

        control_height = int(total * self._CONTROL_RESULT_RATIO / 100)
        output_height = total - control_height
        self.splitter.setSizes([control_height, output_height])

    def _set_running_state(self, status_text: str) -> None:
        """
        Переводит вкладку в состояние выполнения фоновой задачи.

        Блокирует все элементы управления во избежание изменения
        параметров и повторного запуска во время обработки.

        Args:
            status_text: Текст статуса для панели прогресса.
        """
        if self._is_running:
            return

        self._is_running = True
        self.control_widget.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status(status_text)

    def _restore_idle_state(self) -> None:
        """
        Восстанавливает доступность элементов управления после завершения задачи.
        """
        self._is_running = False
        self.control_widget.setEnabled(True)
        self.progress_panel.set_busy(False)

    def _show_placeholder(self, title: str) -> None:
        """
        Выводит временное сообщение-заглушку в панель результатов.

        Args:
            title: Название операции.
        """
        self.output_panel.set_text(
            f"{title} is wired into the GUI shell.\n"
            f"Business logic will be connected in the next implementation stage."
        )

    def save_settings(self) -> dict:
        """
        Сохраняет параметры вкладки.

        Returns:
            Словарь с конфигурацией вкладки.
        """
        return {}

    def load_settings(self, state: dict) -> None:
        """
        Загружает параметры вкладки.

        Args:
            state: Словарь с сохраненной конфигурацией.
        """
        pass

    def trigger_open(self) -> None:
        """
        Инициирует выбор входного файла.

        Метод предназначен для переопределения в наследниках.
        """
        pass

    def trigger_run(self) -> None:
        """
        Инициирует выполнение основной операции.

        Метод предназначен для переопределения в наследниках.
        """
        pass

    def trigger_save(self) -> None:
        """Инициирует сохранение результата через панель вывода."""
        if hasattr(self.output_panel, "save_button"):
            self.output_panel.save_button.click()

    def trigger_copy(self) -> None:
        """Инициирует копирование результата через панель вывода."""
        if hasattr(self.output_panel, "copy_button"):
            self.output_panel.copy_button.click()