from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QTabWidget, QApplication, QWidget

from .tabs.optimize_tab import OptimizeTab
from .tabs.filter_tab import FilterTab
from .tabs.merge_tab import MergeTab
from .tabs.intersect_tab import IntersectTab
from .tabs.diff_tab import DiffTab
from .tabs.exclude_tab import ExcludeTab
from .tabs.split_tab import SplitTab
from .tabs.stats_tab import StatsTab
from .tabs.check_tab import CheckTab
# from .settings_manager import SettingsManager  # TODO: Использовать для сохранения геометрии окна


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("prefixopt")
        
        self._setup_window_geometry()
        self._init_ui()
        self._setup_shortcuts()

    def _setup_window_geometry(self) -> None:
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        width = min(1350, int(screen_geometry.width() * 0.9))
        height = min(900, int(screen_geometry.height() * 0.9))
        
        self.resize(width, height)
        self.setMinimumSize(640, 480)

    def _init_ui(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.tabs.addTab(OptimizeTab(), "Optimize")
        self.tabs.addTab(FilterTab(), "Filter")
        self.tabs.addTab(MergeTab(), "Merge")
        self.tabs.addTab(IntersectTab(), "Intersect")
        self.tabs.addTab(DiffTab(), "Diff")
        self.tabs.addTab(ExcludeTab(), "Exclude")
        self.tabs.addTab(SplitTab(), "Split")
        self.tabs.addTab(StatsTab(), "Stats")
        self.tabs.addTab(CheckTab(), "Check")

        self.setCentralWidget(self.tabs)

    def _setup_shortcuts(self) -> None:
        # Используем лямбды для передачи типа действия в единый диспетчер.
        # Это избавляет от необходимости писать 5 разных методов-обработчиков.
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(
            lambda: self._dispatch_tab_action('browse')
        )
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(
            lambda: self._dispatch_tab_action('run')
        )
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(
            lambda: self._dispatch_tab_action('save')
        )
        QShortcut(QKeySequence("Ctrl+Shift+C"), self).activated.connect(
            lambda: self._dispatch_tab_action('copy')
        )
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.close)

    def _current_tab(self) -> QWidget | None:
        return self.tabs.currentWidget()

    def _dispatch_tab_action(self, action_type: str) -> None:
        tab = self._current_tab()
        if not tab:
            return

        if action_type == 'browse':
            panels = ['input_panel', 'optimize_input', 'source_input', 'new_input']
            target_button = 'browse_button'
        elif action_type == 'run':
            panels = [None]
            target_button = ['run_button', 'optimize_run_button', 'add_run_button']
        elif action_type == 'save':
            panels = ['output_panel']
            target_button = 'save_button'
        elif action_type == 'copy':
            panels = ['output_panel']
            target_button = 'copy_button'
        else:
            return

        for panel_name in panels:
            container = getattr(tab, panel_name) if panel_name else tab
            
            if not container:
                continue

            buttons = target_button if isinstance(target_button, list) else [target_button]
            
            for btn_name in buttons:
                btn = getattr(container, btn_name, None)
                if btn and hasattr(btn, 'click') and btn.isEnabled():
                    btn.click()
                    return