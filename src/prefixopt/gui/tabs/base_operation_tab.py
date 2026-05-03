"""
Базовый класс для вкладок операций графического интерфейса.

Обеспечивает стандартную компоновку элементов: область управления с прокруткой,
панель прогресса и область вывода. Содержит глобальный пул потоков для 
выполнения ресурсоемких задач без блокировки основного потока приложения.
"""

from typing import Optional

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter, QScrollArea

from ..widgets.output_panel import OutputPanel
from ..widgets.progress_panel import ProgressPanel


class BaseOperationTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Инициализирует базовую вкладку операций.

        Создает основные контейнеры компоновки, область прокрутки 
        для элементов управления и инициализирует глобальный пул потоков.

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

    def _setup_splitter(self, output_widget: QWidget) -> None:
        """
        Настраивает вертикальный разделитель.

        Размещает область управления и виджет вывода в разделителе 
        с базовым соотношением пропорций 40% на 60%.

        Args:
            output_widget: Виджет для отображения результатов работы.
        """
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.scroll_area)
        self.splitter.addWidget(output_widget)
        
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 6)
        
        self.root_layout.addWidget(self.splitter)
        self.root_layout.addWidget(self.progress_panel)

    def _show_placeholder(self, title: str) -> None:
        """
        Выводит временное сообщение-заглушку в панель результатов.

        Применяется для обозначения функционала, находящегося в разработке.

        Args:
            title: Название операции или вкладки.
        """
        self.output_panel.set_text(
            f"{title} is wired into the GUI shell.\n"
            f"Business logic will be connected in the next implementation stage."
        )

    def save_settings(self) -> dict:
        """
        Сохраняет текущие параметры вкладки.

        Метод предназначен для переопределения в классах-наследниках.

        Returns:
            Словарь с конфигурацией параметров интерфейса.
        """
        return {}

    def load_settings(self, state: dict) -> None:
        """
        Загружает параметры вкладки из словаря.

        Метод предназначен для переопределения в классах-наследниках.

        Args:
            state: Словарь с сохраненной конфигурацией.
        """
        pass

    def trigger_open(self) -> None:
        """
        Инициирует действие выбора входного файла.

        Метод предназначен для переопределения в классах-наследниках.
        Обеспечивает унифицированный интерфейс для глобальных горячих клавиш.
        """
        pass

    def trigger_run(self) -> None:
        """
        Инициирует выполнение основной операции вкладки.

        Метод предназначен для переопределения в классах-наследниках.
        Обеспечивает унифицированный интерфейс для глобальных горячих клавиш.
        """
        pass

    def trigger_save(self) -> None:
        """
        Инициирует сохранение результатов работы.

        Базовая реализация вызывает метод сохранения у панели вывода.
        """
        if hasattr(self.output_panel, 'save_button'):
            self.output_panel.save_button.click()

    def trigger_copy(self) -> None:
        """
        Инициирует копирование результатов в буфер обмена.

        Базовая реализация вызывает метод копирования у панели вывода.
        """
        if hasattr(self.output_panel, 'copy_button'):
            self.output_panel.copy_button.click()