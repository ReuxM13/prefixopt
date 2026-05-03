"""
GUI-модуль prefixopt.

Содержит графический интерфейс на PySide6,
сервисный слой и модели данных.
"""

import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "log"


def _setup_logging() -> None:
    """
    Настраивает файловое логирование для GUI-модуля.

    Лог-файл размещается в <корень_проекта>/log/prefixopt_gui.log.
    Используется ротация по размеру: максимум 2 МБ, хранится 3 файла.
    """
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

    root_logger = logging.getLogger("prefixopt.gui")
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)
    root_logger.propagate = False


_setup_logging()