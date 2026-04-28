"""
Базовые worker-классы для запуска задач в фоне.
"""
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    """
    Сигналы фоновой задачи.
    """

    finished = Signal()
    error = Signal(str)
    result = Signal(object)
    status = Signal(str)


class Worker(QRunnable):
    """
    Универсальный worker для запуска функции в пуле потоков.
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            self.signals.error.emit(str(e))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()