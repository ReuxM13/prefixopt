"""
Главное окно GUI-приложения prefixopt с горячими клавишами.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QTabWidget, QApplication

from .tabs.optimize_tab import OptimizeTab
from .tabs.filter_tab import FilterTab
from .tabs.merge_tab import MergeTab
from .tabs.intersect_tab import IntersectTab
from .tabs.diff_tab import DiffTab
from .tabs.exclude_tab import ExcludeTab
from .tabs.split_tab import SplitTab
from .tabs.stats_tab import StatsTab
from .tabs.check_tab import CheckTab
from .settings_manager import SettingsManager


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("prefixopt GUI")
        
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        width = min(1350, int(screen_geometry.width() * 0.9))
        height = min(900, int(screen_geometry.height() * 0.9))
        self.resize(width, height)
        self.setMinimumSize(640, 480)
        
        self._init_ui()

    def _init_ui(self) -> None:
        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        tabs.addTab(OptimizeTab(), "Optimize")
        tabs.addTab(FilterTab(), "Filter")
        tabs.addTab(MergeTab(), "Merge")
        tabs.addTab(IntersectTab(), "Intersect")
        tabs.addTab(DiffTab(), "Diff")
        tabs.addTab(ExcludeTab(), "Exclude")
        tabs.addTab(SplitTab(), "Split")
        tabs.addTab(StatsTab(), "Stats")
        tabs.addTab(CheckTab(), "Check")

        self.setCentralWidget(tabs)

    def _setup_shortcuts(self) -> None:
        self.shortcut_open = QShortcut(QKeySequence("Ctrl+O"), self)
        self.shortcut_open.activated.connect(self._on_open_file)

        self.shortcut_run = QShortcut(QKeySequence("Ctrl+R"), self)
        self.shortcut_run.activated.connect(self._on_run)

        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self._on_save)

        self.shortcut_copy = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        self.shortcut_copy.activated.connect(self._on_copy)

        self.shortcut_quit = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.shortcut_quit.activated.connect(self.close)

    def _current_tab(self):
        return self.tabs.currentWidget()

    def _on_open_file(self):
        tab = self._current_tab()
        input_panel = getattr(tab, 'input_panel', None) or \
                     getattr(tab, 'optimize_input', None) or \
                     getattr(tab, 'source_input', None) or \
                     getattr(tab, 'new_input', None)
        if input_panel and hasattr(input_panel, 'browse_button'):
            input_panel.browse_button.click()

    def _on_run(self):
        tab = self._current_tab()
        run_btn = getattr(tab, 'run_button', None) or \
                  getattr(tab, 'optimize_run_button', None) or \
                  getattr(tab, 'add_run_button', None)
        if run_btn and run_btn.isEnabled():
            run_btn.click()

    def _on_save(self):
        tab = self._current_tab()
        output_panel = getattr(tab, 'output_panel', None)
        if output_panel and hasattr(output_panel, 'save_button'):
            output_panel.save_button.click()

    def _on_copy(self):
        tab = self._current_tab()
        output_panel = getattr(tab, 'output_panel', None)
        if output_panel and hasattr(output_panel, 'copy_button'):
            output_panel.copy_button.click()