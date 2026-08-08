"""
Background-task primitives for running core operations off the Qt GUI thread.

Long-running work (optimising huge files, hole punching, etc.) must never
block the event loop, otherwise the UI freezes. Each tab wraps its service
call in a :class:`Worker`, submits it to the global ``QThreadPool`` and
connects to the signals below to receive results, errors or cancellation
notices on the main thread.
"""

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    """Qt signals emitted by a :class:`Worker`.

    Attributes:
        finished:  Always emitted when the worker ends (success/error/cancel).
        error:     Emitted with a traceback string on unhandled exceptions.
        result:    Emitted with the return value of the wrapped callable.
        status:    Reserved for progress messages (not currently used).
        cancelled: Emitted if the worker was cancelled before/while running.
    """

    finished = Signal()
    error = Signal(str)
    result = Signal(object)
    status = Signal(str)
    cancelled = Signal()


class Worker(QRunnable):
    """A runnable that calls ``fn(*args, **kwargs)`` on a thread-pool thread.

    Cancellation is cooperative: callers set a flag via :meth:`cancel` and
    long-running callables may check :meth:`is_cancelled` to abort early.
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialise the component."""
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation (cooperative; checked in :meth:`run`)."""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._cancelled

    def run(self) -> None:
        """Execute the wrapped callable and emit the appropriate signal."""
        # If the task was cancelled before it even started, short-circuit.
        if self._cancelled:
            self.signals.cancelled.emit()
            self.signals.finished.emit()
            return

        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception:
            # A race where the user cancels exactly during an exception: treat
            # it as a cancellation rather than surfacing a traceback.
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
