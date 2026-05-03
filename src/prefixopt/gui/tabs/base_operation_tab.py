"""
Базовый класс для вкладок операций графического интерфейса.

Обеспечивает стандартную компоновку: область управления с прокруткой,
панель прогресса и область вывода. Содержит глобальный пул потоков
для выполнения ресурсоемких задач без блокировки основного потока.
"""

from typing import Optional

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter, QScrollArea

from ..widgets.output_panel import OutputPanel
from ..widgets.progress_panel import ProgressPanel


class BaseOperationTab(QWidget):
    """Базовая вкладка операций с адаптивным разделителем."""

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

        Область управления получает 95% доступной высоты,
        область вывода — 5% (минимальная полоска).
        """
        if self.splitter is None:
            return

        total = self.splitter.height()
        if total <= 0:
            return

        control_h = int(total * self._CONTROL_INITIAL_RATIO / 100)
        output_h = total - control_h
        self.splitter.setSizes([control_h, output_h])

    def _expand_output(self) -> None:
        """
        Перераспределяет пропорции разделителя в пользу области вывода.

        Вызывается однократно при первом получении результата.
        Последующие результаты не изменяют пропорции, чтобы
        не сбрасывать позицию, настроенную пользователем вручную.
        """
        if self._result_received or self.splitter is None:
            return

        self._result_received = True
        total = self.splitter.height()
        if total <= 0:
            return

        control_h = int(total * self._CONTROL_RESULT_RATIO / 100)
        output_h = total - control_h
        self.splitter.setSizes([control_h, output_h])

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

        Предназначен для переопределения в наследниках.

        Returns:
            Словарь с конфигурацией.
        """
        return {}

    def load_settings(self, state: dict) -> None:
        """
        Загружает параметры вкладки.

        Предназначен для переопределения в наследниках.

        Args:
            state: Словарь с сохраненной конфигурацией.
        """
        pass

    def trigger_open(self) -> None:
        """
        Инициирует выбор входного файла.

        Предназначен для переопределения в наследниках.
        """
        pass

    def trigger_run(self) -> None:
        """
        Инициирует выполнение основной операции.

        Предназначен для переопределения в наследниках.
        """
        pass

    def trigger_save(self) -> None:
        """Инициирует сохранение результатов через панель вывода."""
        if hasattr(self.output_panel, "save_button"):
            self.output_panel.save_button.click()

    def trigger_copy(self) -> None:
        """Инициирует копирование результатов через панель вывода."""
        if hasattr(self.output_panel, "copy_button"):
            self.output_panel.copy_button.click()