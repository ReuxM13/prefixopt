"""
Optional PySide6 desktop GUI for prefixopt.

This package is only imported when the user runs ``prefixopt gui`` or imports
``prefixopt.gui`` directly; the CLI can run without PySide6 installed.

Submodule overview:
    app.py              - QApplication bootstrap, theming and entry point.
    main_window.py      - top-level window, tab bar, menus/shortcuts.
    models.py           - dataclasses returned by the service layer.
    services.py         - bridges the core algorithms to GUI operations.
    output_formatter.py - turns result networks/models into display text.
    settings_manager.py - persistent UI settings (QSettings wrapper).
    workers.py          - QRunnable-based background tasks.
    tabs/               - one QWidget per operation (optimize, merge, ...).
    widgets/            - reusable composite widgets (input/output panels).

On import the package configures a rotating log file under ``<repo>/log``.
"""

import logging
import logging.handlers
from pathlib import Path

# Logs live next to the source tree under /log so they are easy to find when
# running from a checkout. Three rotated files at 2 MiB keep disk use bounded.
LOG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "log"


def _setup_logging() -> None:
    """Configure the ``prefixopt.gui`` logger with a rotating file handler."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_file = LOG_DIR / "prefixopt_gui.log"

    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    # Capture everything from the GUI subtree; internal errors are logged here
    # and a short message is shown to the user by BaseOperationTab.
    root_logger = logging.getLogger("prefixopt.gui")
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)
    # Prevent messages from bubbling to the root logger/stderr twice.
    root_logger.propagate = False


_setup_logging()
