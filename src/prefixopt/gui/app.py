"""
QApplication bootstrap for the desktop GUI.

Responsibilities: apply the dark/light stylesheet, set application metadata,
create the :class:`MainWindow`, wire up global keyboard shortcuts and run the
Qt event loop. The :func:`run_gui` function is called by the ``prefixopt gui``
CLI command.
"""


import logging
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow

logger = logging.getLogger("prefixopt.gui.app")


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "prefixopt.gui"
        )
    except Exception:
        logger.exception("Failed to set Windows AppUserModelID")


def _get_icon_path() -> Path | None:
    base_dir = Path(__file__).parent

    if sys.platform == "win32":
        ico_path = base_dir / "icon.ico"
        if ico_path.exists():
            return ico_path

    png_path = base_dir / "icon.png"
    if png_path.exists():
        return png_path

    return None


def _is_dark_theme_windows() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return value == 0
    except Exception:
        return False


def _is_dark_theme(app: QApplication) -> bool:
    if sys.platform == "win32":
        return _is_dark_theme_windows()

    bg = app.palette().color(QPalette.ColorRole.Window)
    luminance = 0.299 * bg.redF() + 0.587 * bg.greenF() + 0.114 * bg.blueF()
    return luminance < 0.5


def _apply_dark_palette(app: QApplication) -> None:
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(212, 212, 212))
    palette.setColor(QPalette.ColorRole.Base, QColor(45, 45, 48))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(37, 37, 38))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(45, 45, 48))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(212, 212, 212))
    palette.setColor(QPalette.ColorRole.Text, QColor(212, 212, 212))
    palette.setColor(QPalette.ColorRole.Button, QColor(60, 60, 60))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(212, 212, 212))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Link, QColor(0, 120, 212))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 212))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(128, 128, 128))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(128, 128, 128))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(128, 128, 128))
    app.setPalette(palette)


def _apply_light_palette(app: QApplication) -> None:
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(245, 245, 245))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.Text, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.Button, QColor(232, 232, 232))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.Link, QColor(0, 120, 212))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 212))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(160, 160, 160))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(160, 160, 160))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(160, 160, 160))
    app.setPalette(palette)


def _build_stylesheet(dark: bool) -> str:
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
            "bg_button_danger": "#6b2020",
            "bg_button_danger_hover": "#8b2a2a",
            "border": "#3f3f46",
            "border_focus": "#0078d4",
            "border_input_inset": "#2a2a2a",
            "text": "#d4d4d4",
            "text_muted": "#808080",
            "text_desc": "#9e9e9e",
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
            "statusbar_bg": "#1e1e1e",
            "statusbar_border": "#3f3f46",
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
            "bg_button_danger": "#d32f2f",
            "bg_button_danger_hover": "#e53935",
            "border": "#d0d0d0",
            "border_focus": "#0078d4",
            "border_input_inset": "#c0c0c0",
            "text": "#1e1e1e",
            "text_muted": "#6e6e6e",
            "text_desc": "#888888",
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
            "statusbar_bg": "#f5f5f5",
            "statusbar_border": "#d0d0d0",
        }

    return f"""
        * {{
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 10pt;
        }}

        QMainWindow {{
            background-color: {c["bg"]};
        }}

        /* --- Statusbar --- */

        QStatusBar {{
            background-color: {c["statusbar_bg"]};
            border-top: 1px solid {c["statusbar_border"]};
            color: {c["text_muted"]};
            font-size: 9pt;
            padding: 2px 8px;
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
            font-size: 10pt;
            font-weight: bold;
        }}

        /* --- Description labels --- */

        QLabel[role="description"] {{
            color: {c["text_desc"]};
            font-size: 9pt;
            padding: 0 0 4px 0;
        }}

        /* --- Inputs with inset --- */

        QLineEdit, QPlainTextEdit, QTextEdit {{
            background-color: {c["bg_input"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-top: 1px solid {c["border_input_inset"]};
            border-left: 1px solid {c["border_input_inset"]};
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
            color: {c["text_muted"]};
        }}

        QPushButton[primary="true"] {{
            background-color: {c["bg_button_primary"]};
            color: #ffffff;
            border: none;
            font-weight: bold;
            font-size: 10pt;
            padding: 7px 24px;
            min-height: 28px;
        }}

        QPushButton[primary="true"]:hover {{
            background-color: {c["bg_button_primary_hover"]};
        }}

        QPushButton[primary="true"]:pressed {{
            background-color: {c["bg_button_primary_pressed"]};
        }}

        QPushButton[danger="true"] {{
            background-color: {c["bg_button_danger"]};
            color: #ffffff;
            border: none;
        }}

        QPushButton[danger="true"]:hover {{
            background-color: {c["bg_button_danger_hover"]};
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

        /* --- SpinBox --- */

        QSpinBox {{
            background-color: {c["bg_input"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 4px;
            padding: 4px 8px;
        }}

        QSpinBox:focus {{
            border: 1px solid {c["border_focus"]};
        }}

        /* --- Labels --- */

        QLabel {{
            color: {c["text"]};
        }}

        /* --- Table --- */

        QTableWidget {{
            background-color: {c["bg_input"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            gridline-color: {c["border"]};
        }}

        QHeaderView::section {{
            background-color: {c["bg_group"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            padding: 4px;
            font-weight: bold;
        }}

        /* --- Splitter --- */

        QSplitter::handle {{
            background: {c["splitter"]};
            border-radius: 2px;
        }}

        QSplitter::handle:vertical {{
            height: 6px;
            image: none;
        }}

        QSplitter::handle:horizontal {{
            width: 6px;
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
    """Create the QApplication, main window and start the event loop."""
    _set_windows_app_id()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("prefixopt")
    app.setOrganizationName("prefixopt")

    icon_path = _get_icon_path()
    if icon_path is not None:
        app_icon = QIcon(str(icon_path))
        app.setWindowIcon(app_icon)
        logger.info("Using application icon: %s", icon_path)

    dark = _is_dark_theme(app)

    if dark:
        _apply_dark_palette(app)
    else:
        _apply_light_palette(app)

    app.setStyleSheet(_build_stylesheet(dark))

    logger.info("GUI started (dark=%s)", dark)

    window = MainWindow()

    if icon_path is not None:
        window.setWindowIcon(QIcon(str(icon_path)))

    window.show()
    app.exec()

    logger.info("GUI closed")