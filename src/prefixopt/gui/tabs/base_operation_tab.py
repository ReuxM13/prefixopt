"""
Base class for all operation tabs in the GUI.

It provides the standard tab skeleton:
    * a scrollable control area at the top (where subclasses add inputs);
    * an output widget (OutputPanel or SplitOutputPanel);
    * a ProgressPanel with status and Cancel at the bottom;
    * a QSplitter that initially favours controls, then expands the output
      once the first result arrives.

It also owns the background-task lifecycle: subclasses build a
:class:`~prefixopt.gui.workers.Worker`, connect its signals and call
:meth:`_start_worker`. Only one task per tab runs at a time.
"""

import logging
from typing import Optional, Union

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import (
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import LOG_DIR
from ..widgets.output_panel import OutputPanel
from ..widgets.progress_panel import ProgressPanel
from ..workers import Worker

logger = logging.getLogger("prefixopt.gui.tab")


class BaseOperationTab(QWidget):
    """Common scaffold and worker lifecycle for operation tabs."""

    # Initial splitter ratios (controls vs output) as percentages.
    _CONTROL_INITIAL_RATIO = 95
    _OUTPUT_INITIAL_RATIO = 5
    # Ratios applied after the first successful result.
    _CONTROL_RESULT_RATIO = 40
    _OUTPUT_RESULT_RATIO = 60

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialise the component."""
        super().__init__(parent)

        self.root_layout = QVBoxLayout(self)

        # Scrollable host for subclass-provided controls.
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)

        self.control_widget = QWidget()
        self.control_layout = QVBoxLayout(self.control_widget)
        self.control_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area.setWidget(self.control_widget)

        self.progress_panel = ProgressPanel()
        # Default output panel; tabs can replace it via _setup_splitter.
        self.output_panel = OutputPanel()

        # All background work shares the process-wide thread pool.
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
        """Widget used to display an error message.

        Tabs using a SplitOutputPanel override this to target the report pane.
        """
        return self.output_panel

    def _on_error_cleanup(self) -> None:
        """Hook for subclasses to reset state after an error."""
        pass

    def _setup_splitter(self, output_widget: QWidget) -> None:
        """Create the vertical splitter between controls and output.

        Called by subclasses at the end of their UI construction.
        """
        self.splitter = QSplitter(Qt.Vertical)
        # Prevent the user from completely hiding a pane.
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.scroll_area)
        self.splitter.addWidget(output_widget)

        self.splitter.setStretchFactor(0, self._CONTROL_INITIAL_RATIO)
        self.splitter.setStretchFactor(1, self._OUTPUT_INITIAL_RATIO)

        self.root_layout.addWidget(self.splitter)
        self.root_layout.addWidget(self.progress_panel)

        # Defer size application until the widget has been laid out.
        QTimer.singleShot(0, self._apply_initial_sizes)

    def _apply_initial_sizes(self) -> None:
        """Apply the initial controls-heavy splitter ratio."""
        if self.splitter is None:
            return
        total = self.splitter.height()
        if total <= 0:
            return
        control_height = int(total * self._CONTROL_INITIAL_RATIO / 100)
        output_height = total - control_height
        self.splitter.setSizes([control_height, output_height])

    def _expand_output(self) -> None:
        """Give the output pane more room after the first result arrives."""
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
        """Disable controls and show the busy indicator.

        Returns False if a task is already running (caller should abort).
        """
        if self._is_running:
            return False
        self._is_running = True
        self.control_widget.setEnabled(False)
        self.progress_panel.set_busy(True)
        self.progress_panel.set_status(status_text)
        return True

    def _restore_idle_state(self) -> None:
        """Re-enable controls and hide the busy indicator."""
        self._is_running = False
        self._current_worker = None
        self.control_widget.setEnabled(True)
        self.progress_panel.set_busy(False)

    def _start_worker(self, worker: Worker, status_text: str) -> bool:
        """Connect standard signals and start ``worker`` on the thread pool."""
        if not self._set_running_state(status_text):
            return False
        self._current_worker = worker
        worker.signals.cancelled.connect(self._on_worker_cancelled)
        worker.signals.finished.connect(self._on_worker_finished)
        self.threadpool.start(worker)
        return True

    def _cancel_current_worker(self) -> None:
        """Request cooperative cancellation of the running worker."""
        if self._current_worker is None or not self._is_running:
            return
        worker = self._current_worker
        worker.cancel()
        # Unlock the UI immediately; results from this worker are ignored.
        self.progress_panel.set_status("Cancelled")
        self._restore_idle_state()

    def _on_worker_cancelled(self) -> None:
        """Update the status when the worker is cancelled."""
        self.progress_panel.set_status("Cancelled")

    def _on_worker_finished(self) -> None:
        # Restore idle state only if we're still marked as running (a manual
        # cancel already restores it).
        """Restore the idle state once the worker finishes, if still running."""
        if self._is_running:
            self._restore_idle_state()
        # Release the finished worker (and its captured result) so large
        # intermediate lists don't linger until the next run.
        self._current_worker = None

    def _graceful_shutdown(self) -> None:
        """Cancel active work and wait briefly for the pool to finish.

        Called when the tab/window is closing to avoid tearing down Qt while
        a worker is still emitting signals.
        """
        if self._current_worker is not None and self._is_running:
            self._current_worker.cancel()
        self.threadpool.waitForDone(3000)

    def _on_error(self, error_msg: str) -> None:
        """Display a worker's error in the output panel.

        Expected user-facing exceptions (ValueError, OSError, ...) have their
        message shown directly; unexpected exceptions are logged and the user
        is pointed at the log file.
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
        """Pull a human-readable message from the last line of a traceback.

        Only a small set of exception types are treated as user errors;
        anything else returns "" so it is handled as an internal error.
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

    # ---- Hooks for main-window shortcuts/menus; subclasses override. ----

    def save_settings(self) -> dict:
        """Serialise tab settings; overridden by subclasses."""
        return {}

    def load_settings(self, state: dict) -> None:
        """Restore tab settings; overridden by subclasses."""
        pass

    def trigger_open(self) -> None:
        """Open-file hook invoked by Ctrl+O; overridden by subclasses."""
        pass

    def trigger_run(self) -> None:
        """Run hook invoked by Ctrl+R; overridden by subclasses."""
        pass

    def trigger_save(self) -> None:
        """Click the output panel's Save button."""
        if hasattr(self.output_panel, "save_button"):
            self.output_panel.save_button.click()

    def trigger_copy(self) -> None:
        """Click the output panel's Copy button."""
        if hasattr(self.output_panel, "copy_button"):
            self.output_panel.copy_button.click()

    def get_splitter_widget(self) -> Optional[QSplitter]:
        """Return the tab's main splitter (used for persistence)."""
        return getattr(self, "splitter", None)

    def get_split_output_panel(self):
        """Return a SplitOutputPanel if the tab uses one, else None."""
        return None
