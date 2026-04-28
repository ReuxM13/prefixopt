"""
Инициализация и запуск GUI-приложения.
"""
import sys
from PySide6.QtWidgets import QApplication
from .main_window import MainWindow


def run_gui() -> None:
    """
    Создает QApplication и запускает главное окно.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("prefixopt")
    app.setOrganizationName("prefixopt")

    # Глобальный стиль для всех QSplitter
    app.setStyleSheet("""
        QSplitter::handle {
            background: #b0b0b0;
        }
        QSplitter::handle:vertical {
            height: 4px;
        }
        QSplitter::handle:horizontal {
            width: 4px;
        }
        QSplitter::handle:hover {
            background: #808080;
        }
        QSplitter::handle:pressed {
            background: #606060;
        }
    """)

    window = MainWindow()
    window.show()

    app.exec()