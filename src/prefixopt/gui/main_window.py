"""
Главное окно GUI-приложения prefixopt с горячими клавишами.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QTabWidget

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
        self.resize(1350, 900)

        self._settings = SettingsManager.instance()

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.optimize_tab = OptimizeTab()
        self.filter_tab = FilterTab()
        self.merge_tab = MergeTab()
        self.intersect_tab = IntersectTab()
        self.diff_tab = DiffTab()
        self.exclude_tab = ExcludeTab()
        self.split_tab = SplitTab()
        self.stats_tab = StatsTab()
        self.check_tab = CheckTab()

        self.tabs.addTab(self.optimize_tab, "Optimize")
        self.tabs.addTab(self.filter_tab, "Filter")
        self.tabs.addTab(self.merge_tab, "Merge")
        self.tabs.addTab(self.intersect_tab, "Intersect")
        self.tabs.addTab(self.diff_tab, "Diff")
        self.tabs.addTab(self.exclude_tab, "Exclude")
        self.tabs.addTab(self.split_tab, "Split")
        self.tabs.addTab(self.stats_tab, "Stats")
        self.tabs.addTab(self.check_tab, "Check")

        self.setCentralWidget(self.tabs)

        # Регистрация вкладок в менеджере настроек
        for idx in range(self.tabs.count()):
            tab = self.tabs.widget(idx)
            name = self.tabs.tabText(idx)
            self._settings.register_tab(name, tab)

        self._setup_shortcuts()
        self._settings.load_all()

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

    def closeEvent(self, event):
        self._settings.save_all()
        super().closeEvent(event)