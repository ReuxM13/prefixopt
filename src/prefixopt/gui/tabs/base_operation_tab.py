"""
Базовый класс для вкладок операций графического интерфейса.

Обеспечивает стандартную компоновку: область управления с прокруткой,
панель прогресса и область вывода. Содержит глобальный пул потоков
для выполнения ресурсоемких задач без блокировки основного потока.
"""

import logging
from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import QScrollArea, QSplitter, QVBoxLayout, QWidget

from .. import LOG_DIR
from ..widgets.output_panel import OutputPanel
from ..widgets.progress_panel import ProgressPanel
from ..workers import Worker

logger = logging.getLogger("prefixopt.gui.tab")


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
        self._current_worker: Optional[Worker] = None

        self.progress_panel.cancel_button.clicked.connect(
            self._cancel_current_worker
        )

    @property
    def _error_display_widget(self) -> Union[OutputPanel, QWidget]:
        """
        Возвращает виджет для отображения сообщений об ошибках.

        По умолчанию используется output_panel.
        Переопределяется во вкладках, использующих SplitOutputPanel.

        Returns:
            Виджет для отображения ошибок.
        """
        return self.output_panel

    def _on_error_cleanup(self) -> None:
        """
        Дополнительные действия после отображения ошибки.

        Переопределяется во вкладках, требующих дополнительной очистки
        (например, SplitOutputPanel).
        """
        pass

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

    def _set_running_state(self, status_text: str) -> bool:
        """
        Переводит вкладку в состояние выполнения фоновой задачи.

        Args:
            status_text: Текст статуса для панели прогресса.

        Returns:
            True, если состояние успешно установлено.
            False, если задача уже выполняется.
        """
        if self._is_running:
            return False

        self._is_running = True
        self.control_widget.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status(status_text)
        return True

    def _restore_idle_state(self) -> None:
        """
        Восстанавливает доступность элементов управления после завершения задачи.
        """
        self._is_running = False
        self._current_worker = None
        self.control_widget.setEnabled(True)
        self.progress_panel.set_busy(False)

    def _start_worker(self, worker: Worker, status_text: str) -> bool:
        """
        Регистрирует worker, подключает стандартные сигналы и запускает задачу.

        Сигналы result и error подключаются во вкладке до вызова этого метода.

        Args:
            worker: Подготовленный worker с подключенными result/error.
            status_text: Текст статуса на время выполнения.

        Returns:
            True, если запуск выполнен.
            False, если задача уже выполняется.
        """
        if not self._set_running_state(status_text):
            return False

        self._current_worker = worker
        worker.signals.cancelled.connect(self._on_worker_cancelled)
        worker.signals.finished.connect(self._on_worker_finished)
        self.threadpool.start(worker)
        return True

    def _cancel_current_worker(self) -> None:
        """
        Запрашивает мягкую отмену текущей задачи.

        Интерфейс разблокируется сразу. Результат задачи игнорируется.
        """
        if self._current_worker is None or not self._is_running:
            return

        worker = self._current_worker
        worker.cancel()

        self.progress_panel.set_status("Cancelled")
        self._restore_idle_state()

    def _on_worker_cancelled(self) -> None:
        """
        Обрабатывает сигнал отмены worker'а.
        """
        self.progress_panel.set_status("Cancelled")

    def _on_worker_finished(self) -> None:
        """
        Завершает жизненный цикл текущей фоновой задачи.
        """
        if self._is_running:
            self._restore_idle_state()

    def _graceful_shutdown(self) -> None:
        """
        Выполняет мягкое завершение активной задачи при закрытии вкладки.

        Отменяет текущий worker и ожидает завершения пула потоков
        с таймаутом 3 секунды, чтобы не блокировать закрытие приложения.
        """
        if self._current_worker is not None and self._is_running:
            self._current_worker.cancel()

        self.threadpool.waitForDone(3000)

    def _on_error(self, error_msg: str) -> None:
        """
        Обрабатывает ошибку фоновой задачи.

        Ошибки валидации входных данных отображаются пользователю напрямую.
        Внутренние ошибки логируются в файл, пользователю показывается
        краткое уведомление.

        Для вывода используется _error_display_widget, что позволяет
        дочерним вкладкам (IntersectTab, CheckTab) переопределять
        целевой виджет без дублирования логики.

        Args:
            error_msg: Полный traceback от worker'а.
        """
        user_message = self._extract_user_message(error_msg)
        widget = self._error_display_widget

        if user_message:
            if hasattr(widget, "set_report_text"):
                widget.set_report_text(user_message)
            else:
                widget.set_text(user_message)
        else:
            logger.error(
                "Unhandled error in background task:\n%s", error_msg
            )
            log_path = LOG_DIR / "prefixopt_gui.log"
            msg = (
                "An internal error occurred.\n"
                f"Details have been written to:\n{log_path}"
            )
            if hasattr(widget, "set_report_text"):
                widget.set_report_text(msg)
            else:
                widget.set_text(msg)

        self._on_error_cleanup()
        self.progress_panel.set_status("Error")

    @staticmethod
    def _extract_user_message(traceback_text: str) -> str:
        """
        Извлекает понятное пользователю сообщение из traceback.

        Распознает ValueError, FileNotFoundError, PermissionError, OSError
        как пользовательские ошибки.

        Args:
            traceback_text: Полный traceback.

        Returns:
            Сообщение об ошибке или пустая строка для внутренних ошибок.
        """
        user_exceptions = (
            "ValueError:",
            "FileNotFoundError:",
            "PermissionError:",
            "OSError:",
        )

        lines = traceback_text.strip().splitlines()
        if not lines:
            return ""

        last_line = lines[-1].strip()

        for prefix in user_exceptions:
            if last_line.startswith(prefix):
                return last_line[len(prefix):].strip()

        return ""

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
    def get_splitter_widget(self) -> Optional[QSplitter]:
        """
        Возвращает основной разделитель вкладки.

        Returns:
            QSplitter или None, если разделитель не настроен.
        """
        return getattr(self, "splitter", None)

    def get_split_output_panel(self):
        """
        Возвращает SplitOutputPanel, если он используется.

        По умолчанию возвращает None. Переопределяется во вкладках,
        использующих двойную панель вывода (IntersectTab, CheckTab).

        Returns:
            SplitOutputPanel или None.
        """
        return None
