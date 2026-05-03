"""
Инициализация и запуск GUI-приложения.
"""
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def run_gui() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("prefixopt")
    app.setOrganizationName("prefixopt")


    icon_path = Path(__file__).parent / "icon.png"

    if icon_path.exists():
        app_icon = QIcon(str(icon_path))
        app.setWindowIcon(app_icon) 

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

    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))

    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "prefixopt.gui"
            )
        except Exception:
            pass

    window.show()
    app.exec()