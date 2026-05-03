"""
Главное окно GUI-приложения prefixopt.

Инициализирует вкладки, горячие клавиши и восстанавливает
сохраненное состояние окна и пользовательских настроек.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget

from .settings_manager import SettingsManager
from .tabs.check_tab import CheckTab
from .tabs.diff_tab import DiffTab
from .tabs.exclude_tab import ExcludeTab
from .tabs.filter_tab import FilterTab
from .tabs.intersect_tab import IntersectTab
from .tabs.merge_tab import MergeTab
from .tabs.optimize_tab import OptimizeTab
from .tabs.split_tab import SplitTab
from .tabs.stats_tab import StatsTab


class MainWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(self) -> None:
        """
        Инициализирует окно приложения.
        """
        super().__init__()
        self.setWindowTitle("prefixopt")
        self.setMinimumSize(640, 480)

        self._settings = SettingsManager.instance()
        self._tab_widgets: dict[str, QWidget] = {}
        self._splitters_restored = False

        self._setup_default_geometry()
        self._init_ui()
        self._setup_shortcuts()
        self._restore_saved_state()

    def _setup_default_geometry(self) -> None:
        """
        Устанавливает размеры окна по умолчанию.
        """
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1350, 900)
            return

        geometry = screen.availableGeometry()
        width = min(1350, int(geometry.width() * 0.9))
        height = min(900, int(geometry.height() * 0.9))
        self.resize(width, height)

    def _init_ui(self) -> None:
        """
        Создает вкладки и регистрирует их в менеджере настроек.
        """
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        tab_definitions = [
            ("optimize", "Optimize", OptimizeTab()),
            ("filter", "Filter", FilterTab()),
            ("merge", "Merge", MergeTab()),
            ("intersect", "Intersect", IntersectTab()),
            ("diff", "Diff", DiffTab()),
            ("exclude", "Exclude", ExcludeTab()),
            ("split", "Split", SplitTab()),
            ("stats", "Stats", StatsTab()),
            ("check", "Check", CheckTab()),
        ]

        for key, title, widget in tab_definitions:
            self._tab_widgets[key] = widget
            self._settings.register_tab(key, widget)
            self.tabs.addTab(widget, title)

        self.setCentralWidget(self.tabs)

    def _setup_shortcuts(self) -> None:
        """
        Настраивает глобальные горячие клавиши окна.
        """
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(
            lambda: self._dispatch_tab_action("browse")
        )
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(
            lambda: self._dispatch_tab_action("run")
        )
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(
            lambda: self._dispatch_tab_action("save")
        )
        QShortcut(QKeySequence("Ctrl+Shift+C"), self).activated.connect(
            lambda: self._dispatch_tab_action("copy")
        )
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.close)

    def _restore_saved_state(self) -> None:
        """
        Восстанавливает состояние окна и настроек вкладок.
        """
        geometry = self._settings.load_main_window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)

        self._settings.load_all()

        current_tab = self._settings.load_main_window_current_tab()
        if 0 <= current_tab < self.tabs.count():
            self.tabs.setCurrentIndex(current_tab)

        if self._settings.load_main_window_maximized():
            self.setWindowState(self.windowState() | Qt.WindowMaximized)

    def _save_state(self) -> None:
        """
        Сохраняет состояние окна, вкладок и сплиттеров.
        """
        self._settings.save_main_window(
            geometry=self.saveGeometry(),
            maximized=self.isMaximized(),
            current_tab=self.tabs.currentIndex(),
        )
        self._save_splitters()
        self._settings.save_all()

    def _save_splitters(self) -> None:
        """
        Сохраняет размеры сплиттеров всех вкладок.
        """
        for key, tab in self._tab_widgets.items():
            main_splitter = getattr(tab, "splitter", None)
            if main_splitter is not None:
                self._settings.save_splitter_sizes(
                    f"{key}/main",
                    main_splitter.sizes(),
                )

            split_output = getattr(tab, "split_output", None)
            if split_output is not None:
                nested_splitter = getattr(split_output, "splitter", None)
                if nested_splitter is not None:
                    self._settings.save_splitter_sizes(
                        f"{key}/nested",
                        nested_splitter.sizes(),
                    )

    def _restore_splitters(self) -> None:
        """
        Восстанавливает размеры сплиттеров всех вкладок.
        """
        for key, tab in self._tab_widgets.items():
            main_splitter = getattr(tab, "splitter", None)
            if main_splitter is not None:
                sizes = self._settings.load_splitter_sizes(f"{key}/main")
                if len(sizes) >= 2:
                    main_splitter.setSizes(sizes)

            split_output = getattr(tab, "split_output", None)
            if split_output is not None:
                nested_splitter = getattr(split_output, "splitter", None)
                if nested_splitter is not None:
                    sizes = self._settings.load_splitter_sizes(
                        f"{key}/nested"
                    )
                    if len(sizes) >= 2:
                        nested_splitter.setSizes(sizes)

    def _current_tab(self) -> Optional[QWidget]:
        """
        Возвращает активную вкладку.

        Returns:
            Текущий виджет вкладки или None.
        """
        return self.tabs.currentWidget()

    def _get_output_panel(self, tab: QWidget) -> Optional[QWidget]:
        """
        Возвращает панель вывода для вкладки.

        Args:
            tab: Виджет вкладки.

        Returns:
            Панель вывода или None.
        """
        split_output = getattr(tab, "split_output", None)
        if split_output is not None and hasattr(split_output, "get_output_panel"):
            return split_output.get_output_panel()

        return getattr(tab, "output_panel", None)

    def _dispatch_tab_action(self, action_type: str) -> None:
        """
        Выполняет действие для активной вкладки.

        Args:
            action_type: Тип действия.
        """
        tab = self._current_tab()
        if tab is None:
            return

        if action_type == "browse":
            method = getattr(tab, "trigger_open", None)
            if callable(method):
                method()
                return

        if action_type == "run":
            method = getattr(tab, "trigger_run", None)
            if callable(method):
                method()
                return

        output_panel = self._get_output_panel(tab)

        if action_type == "save" and output_panel is not None:
            save_button = getattr(output_panel, "save_button", None)
            if save_button is not None and save_button.isEnabled():
                save_button.click()
            return

        if action_type == "copy" and output_panel is not None:
            copy_button = getattr(output_panel, "copy_button", None)
            if copy_button is not None and copy_button.isEnabled():
                copy_button.click()

    def showEvent(self, event: QShowEvent) -> None:
        """
        Восстанавливает размеры сплиттеров после первого показа окна.

        Args:
            event: Событие показа окна.
        """
        super().showEvent(event)

        if self._splitters_restored:
            return

        self._splitters_restored = True
        QTimer.singleShot(0, self._restore_splitters)

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Сохраняет состояние окна перед закрытием.

        Args:
            event: Событие закрытия окна.
        """
        self._save_state()
        super().closeEvent(event)