"""
Инициализация и запуск GUI-приложения.

Определяет системную тему оформления и применяет глобальную стилизацию.
"""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def _is_dark_theme(app: QApplication) -> bool:
    """
    Определяет текущую системную тему по яркости фона палитры.

    Args:
        app: Экземпляр приложения.

    Returns:
        True если активна тёмная тема.
    """
    bg = app.palette().color(QPalette.ColorRole.Window)
    luminance = 0.299 * bg.redF() + 0.587 * bg.greenF() + 0.114 * bg.blueF()
    return luminance < 0.5


def _build_stylesheet(dark: bool) -> str:
    """
    Формирует глобальный stylesheet для приложения.

    Args:
        dark: True для тёмной темы, False для светлой.

    Returns:
        CSS-строка.
    """
    if dark:
        c = {
            "bg": "#1e1e1e",
            "bg_alt": "#252526",
            "bg_input": "#2d2d30",
            "bg_group": "#2d2d30",
            "bg_button": "#3c3c3c",
            "bg_button_hover": "#4a4a4d",
            "bg_button_pressed": "#555558",
            "bg_button_primary": "#0e639c",
            "bg_button_primary_hover": "#1177bb",
            "bg_button_primary_pressed": "#0d5689",
            "border": "#3f3f46",
            "border_focus": "#0078d4",
            "text": "#d4d4d4",
            "text_muted": "#808080",
            "text_placeholder": "#5a5a5a",
            "text_button": "#ffffff",
            "text_group_title": "#9cdcfe",
            "scrollbar_bg": "#1e1e1e",
            "scrollbar_handle": "#424242",
            "scrollbar_handle_hover": "#555555",
            "splitter": "#3f3f46",
            "splitter_hover": "#0078d4",
            "splitter_pressed": "#005a9e",
            "progress_chunk": "#0078d4",
            "progress_bg": "#2d2d30",
            "tab_selected_bg": "#1e1e1e",
            "tab_bg": "#2d2d30",
            "tab_hover_bg": "#383838",
            "tab_border": "#3f3f46",
            "radio_indicator": "#0078d4",
        }
    else:
        c = {
            "bg": "#ffffff",
            "bg_alt": "#f5f5f5",
            "bg_input": "#ffffff",
            "bg_group": "#fafafa",
            "bg_button": "#e8e8e8",
            "bg_button_hover": "#d6d6d6",
            "bg_button_pressed": "#c4c4c4",
            "bg_button_primary": "#0078d4",
            "bg_button_primary_hover": "#1a88dd",
            "bg_button_primary_pressed": "#005a9e",
            "border": "#d0d0d0",
            "border_focus": "#0078d4",
            "text": "#1e1e1e",
            "text_muted": "#6e6e6e",
            "text_placeholder": "#a0a0a0",
            "text_button": "#1e1e1e",
            "text_group_title": "#0078d4",
            "scrollbar_bg": "#f0f0f0",
            "scrollbar_handle": "#c1c1c1",
            "scrollbar_handle_hover": "#a0a0a0",
            "splitter": "#d0d0d0",
            "splitter_hover": "#0078d4",
            "splitter_pressed": "#005a9e",
            "progress_chunk": "#0078d4",
            "progress_bg": "#e8e8e8",
            "tab_selected_bg": "#ffffff",
            "tab_bg": "#f0f0f0",
            "tab_hover_bg": "#e5e5e5",
            "tab_border": "#d0d0d0",
            "radio_indicator": "#0078d4",
        }

    return f"""
        * {{
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 10pt;
        }}

        QMainWindow {{
            background-color: {c["bg"]};
        }}

        /* --- Tabs --- */

        QTabWidget::pane {{
            border: 1px solid {c["tab_border"]};
            border-top: 2px solid {c["border_focus"]};
            background-color: {c["bg"]};
        }}

        QTabBar::tab {{
            background-color: {c["tab_bg"]};
            color: {c["text_muted"]};
            border: 1px solid {c["tab_border"]};
            border-bottom: none;
            padding: 6px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }}

        QTabBar::tab:selected {{
            background-color: {c["tab_selected_bg"]};
            color: {c["text"]};
            border-bottom: 2px solid {c["border_focus"]};
        }}

        QTabBar::tab:hover:!selected {{
            background-color: {c["tab_hover_bg"]};
            color: {c["text"]};
        }}

        /* --- Group boxes --- */

        QGroupBox {{
            background-color: {c["bg_group"]};
            border: 1px solid {c["border"]};
            border-radius: 6px;
            margin-top: 8px;
            padding: 12px 8px 8px 8px;
            font-weight: bold;
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 2px 8px;
            color: {c["text_group_title"]};
        }}

        /* --- Inputs --- */

        QLineEdit, QPlainTextEdit, QTextEdit {{
            background-color: {c["bg_input"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 4px;
            padding: 4px 6px;
            selection-background-color: {c["border_focus"]};
        }}

        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
            border: 1px solid {c["border_focus"]};
        }}

        QLineEdit[readOnly="true"] {{
            background-color: {c["bg_alt"]};
        }}

        /* --- Buttons --- */

        QPushButton {{
            background-color: {c["bg_button"]};
            color: {c["text_button"]};
            border: 1px solid {c["border"]};
            border-radius: 4px;
            padding: 5px 14px;
            min-width: 60px;
        }}

        QPushButton:hover {{
            background-color: {c["bg_button_hover"]};
        }}

        QPushButton:pressed {{
            background-color: {c["bg_button_pressed"]};
        }}

        QPushButton:disabled {{
            opacity: 0.5;
            color: {c["text_muted"]};
        }}

        QPushButton[primary="true"] {{
            background-color: {c["bg_button_primary"]};
            color: #ffffff;
            border: none;
            font-weight: bold;
        }}

        QPushButton[primary="true"]:hover {{
            background-color: {c["bg_button_primary_hover"]};
        }}

        QPushButton[primary="true"]:pressed {{
            background-color: {c["bg_button_primary_pressed"]};
        }}

        /* --- Checkboxes & Radio --- */

        QCheckBox, QRadioButton {{
            color: {c["text"]};
            spacing: 6px;
        }}

        QCheckBox::indicator, QRadioButton::indicator {{
            width: 16px;
            height: 16px;
        }}

        /* --- ComboBox --- */

        QComboBox {{
            background-color: {c["bg_input"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 4px;
            padding: 4px 8px;
            min-width: 80px;
        }}

        QComboBox:hover {{
            border: 1px solid {c["border_focus"]};
        }}

        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {c["bg_input"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            selection-background-color: {c["border_focus"]};
            selection-color: #ffffff;
        }}

        /* --- Labels --- */

        QLabel {{
            color: {c["text"]};
        }}

        /* --- Splitter --- */

        QSplitter::handle {{
            background: {c["splitter"]};
        }}

        QSplitter::handle:vertical {{
            height: 4px;
        }}

        QSplitter::handle:horizontal {{
            width: 4px;
        }}

        QSplitter::handle:hover {{
            background: {c["splitter_hover"]};
        }}

        QSplitter::handle:pressed {{
            background: {c["splitter_pressed"]};
        }}

        /* --- Progress bar --- */

        QProgressBar {{
            background-color: {c["progress_bg"]};
            border: 1px solid {c["border"]};
            border-radius: 4px;
            text-align: center;
            color: {c["text"]};
            height: 18px;
        }}

        QProgressBar::chunk {{
            background-color: {c["progress_chunk"]};
            border-radius: 3px;
        }}

        /* --- Scrollbar --- */

        QScrollBar:vertical {{
            background: {c["scrollbar_bg"]};
            width: 10px;
            margin: 0;
        }}

        QScrollBar::handle:vertical {{
            background: {c["scrollbar_handle"]};
            min-height: 30px;
            border-radius: 5px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: {c["scrollbar_handle_hover"]};
        }}

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0;
        }}

        QScrollBar:horizontal {{
            background: {c["scrollbar_bg"]};
            height: 10px;
            margin: 0;
        }}

        QScrollBar::handle:horizontal {{
            background: {c["scrollbar_handle"]};
            min-width: 30px;
            border-radius: 5px;
        }}

        QScrollBar::handle:horizontal:hover {{
            background: {c["scrollbar_handle_hover"]};
        }}

        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {{
            width: 0;
        }}

        /* --- Scroll area --- */

        QScrollArea {{
            border: none;
            background-color: transparent;
        }}

        /* --- Menu --- */

        QMenu {{
            background-color: {c["bg_input"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            padding: 4px;
        }}

        QMenu::item:selected {{
            background-color: {c["border_focus"]};
            color: #ffffff;
        }}
    """


def run_gui() -> None:
    """Точка входа для запуска графического интерфейса."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("prefixopt")
    app.setOrganizationName("prefixopt")

    icon_path = Path(__file__).parent / "icon.png"

    if icon_path.exists():
        app_icon = QIcon(str(icon_path))
        app.setWindowIcon(app_icon)

    dark = _is_dark_theme(app)
    app.setStyleSheet(_build_stylesheet(dark))

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