"""
Базовые worker-классы для запуска задач в фоне.

Worker выполняет функцию в потоке из QThreadPool.
Поддерживает мягкую отмену: результат игнорируется,
интерфейс может быть разблокирован немедленно.
"""

from typing import Any, Callable

import traceback

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    """
    Сигналы фоновой задачи.
    """

    finished = Signal()
    error = Signal(str)
    result = Signal(object)
    status = Signal(str)
    cancelled = Signal()


class Worker(QRunnable):
    """
    Универсальный worker для запуска функции в пуле потоков.

    После вызова cancel() вычисление не прерывается физически,
    но его результат и ошибка больше не передаются в GUI.
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Инициализирует worker.

        Args:
            fn: Функция для выполнения.
            *args: Позиционные аргументы функции.
            **kwargs: Именованные аргументы функции.
        """
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._cancelled = False

    def cancel(self) -> None:
        """
        Устанавливает флаг отмены.

        Выполняемая функция продолжит работу до завершения,
        но её результат будет проигнорирован.
        """
        self._cancelled = True

    def is_cancelled(self) -> bool:
        """
        Возвращает состояние флага отмены.

        Returns:
            True, если отмена была запрошена.
        """
        return self._cancelled

    def run(self) -> None:
        """
        Выполняет функцию и отправляет результат через сигналы.

        Если отмена была запрошена до завершения функции,
        результат и ошибка не передаются.
        """
        if self._cancelled:
            self.signals.cancelled.emit()
            self.signals.finished.emit()
            return

        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception:
            if self._cancelled:
                self.signals.cancelled.emit()
            else:
                self.signals.error.emit(traceback.format_exc())
        else:
            if self._cancelled:
                self.signals.cancelled.emit()
            else:
                self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()