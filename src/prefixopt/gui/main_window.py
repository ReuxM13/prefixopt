"""
Top-level main window: tab bar, menus, global shortcuts and settings wiring.

Hosts one tab per operation (Optimize, Filter, Merge, Exclude, ...), manages
the recent-files menu, persists/restores window geometry and tab state through
:class:`SettingsManager`, and routes ``Ctrl+R``/``Ctrl+O``/``Ctrl+S`` to the
active tab.
"""


from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QTimer, QUrl, Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent, QKeySequence, QShortcut, QShowEvent
try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    _MULTIMEDIA_AVAILABLE = True
except ImportError:  # pragma: no cover - backend missing on minimal systems
    QAudioOutput = QMediaPlayer = None  # type: ignore
    _MULTIMEDIA_AVAILABLE = False
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QWidget,
)

from .settings_manager import SettingsManager
from .tabs.base_operation_tab import BaseOperationTab
from .tabs.check_tab import CheckTab
from .tabs.diff_tab import DiffTab
from .tabs.exclude_tab import ExcludeTab
from .tabs.filter_tab import FilterTab
from .tabs.intersect_tab import IntersectTab
from .tabs.merge_tab import MergeTab
from .tabs.optimize_tab import OptimizeTab
from .tabs.split_tab import SplitTab
from .tabs.stats_tab import StatsTab

_EASTER_EGG_WORD = "sraka"
_EASTER_EGG_BG = "#5C4033"
_EASTER_EGG_DURATION_MS = 30000


class MainWindow(QMainWindow):

    """Top-level window hosting the operation tabs, menus and shortcuts."""

    def __init__(self) -> None:
        """Set up the widget, build its UI and wire up signals."""
        super().__init__()
        self.setWindowTitle("prefixopt")
        self.setMinimumSize(640, 480)

        self._settings = SettingsManager.instance()
        self._tab_widgets: dict[str, BaseOperationTab] = {}
        self._splitters_restored = False

        self._key_buffer: list[str] = []
        self._saved_stylesheet: str = ""
        self._easter_active = False

        self._media_player: Optional[QMediaPlayer] = None
        self._audio_output: Optional[QAudioOutput] = None

        self._setup_default_geometry()
        self._init_ui()
        self._setup_statusbar()
        self._setup_shortcuts()
        self._restore_saved_state()
        QTimer.singleShot(100, self._do_install_key_spy)

    def _setup_default_geometry(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1350, 900)
            return

        geometry = screen.availableGeometry()
        width = min(1350, int(geometry.width() * 0.9))
        height = min(900, int(geometry.height() * 0.9))
        self.resize(width, height)

    def _init_ui(self) -> None:
        """Construct and lay out all child widgets for this tab."""
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

    def _setup_statusbar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Ready - Ctrl+R to run, Ctrl+O to open file")

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        """Handle the tab changed event."""
        tab_name = self.tabs.tabText(index)
        self._statusbar.showMessage(
            f"{tab_name} - Ctrl+R to run, Ctrl+O to open, "
            f"Ctrl+S to save, Ctrl+Q to quit"
        )
        QTimer.singleShot(50, self._do_install_key_spy)

    def _setup_shortcuts(self) -> None:
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

        QShortcut(QKeySequence("Ctrl+Tab"), self).activated.connect(
            self._next_tab
        )
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self).activated.connect(
            self._prev_tab
        )

    def _next_tab(self) -> None:
        current = self.tabs.currentIndex()
        total = self.tabs.count()
        self.tabs.setCurrentIndex((current + 1) % total)

    def _prev_tab(self) -> None:
        current = self.tabs.currentIndex()
        total = self.tabs.count()
        self.tabs.setCurrentIndex((current - 1) % total)

    def _restore_saved_state(self) -> None:
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
        self._settings.save_main_window(
            geometry=self.saveGeometry(),
            maximized=self.isMaximized(),
            current_tab=self.tabs.currentIndex(),
        )
        self._save_splitters()
        self._settings.save_all()

    def _save_splitters(self) -> None:
        for key, tab in self._tab_widgets.items():
            main_splitter = tab.get_splitter_widget()
            if main_splitter is not None:
                self._settings.save_splitter_sizes(
                    f"{key}/main",
                    main_splitter.sizes(),
                )

            split_output = tab.get_split_output_panel()
            if split_output is not None:
                nested_splitter = split_output.get_nested_splitter()
                if nested_splitter is not None:
                    self._settings.save_splitter_sizes(
                        f"{key}/nested",
                        nested_splitter.sizes(),
                    )

    def _restore_splitters(self) -> None:
        for key, tab in self._tab_widgets.items():
            main_splitter = tab.get_splitter_widget()
            if main_splitter is not None:
                sizes = self._settings.load_splitter_sizes(f"{key}/main")
                if len(sizes) >= 2:
                    main_splitter.setSizes(sizes)

            split_output = tab.get_split_output_panel()
            if split_output is not None:
                nested_splitter = split_output.get_nested_splitter()
                if nested_splitter is not None:
                    sizes = self._settings.load_splitter_sizes(
                        f"{key}/nested"
                    )
                    if len(sizes) >= 2:
                        nested_splitter.setSizes(sizes)

    def _current_tab(self) -> Optional[BaseOperationTab]:
        widget = self.tabs.currentWidget()
        if isinstance(widget, BaseOperationTab):
            return widget
        return None

    def _dispatch_tab_action(self, action_type: str) -> None:
        tab = self._current_tab()
        if tab is None:
            return

        if action_type == "browse":
            tab.trigger_open()
            return

        if action_type == "run":
            tab.trigger_run()
            return

        if action_type == "save":
            tab.trigger_save()
            return

        if action_type == "copy":
            tab.trigger_copy()

    def _do_install_key_spy(self) -> None:
        from PySide6.QtWidgets import (
            QAbstractButton,
            QAbstractScrollArea,
            QComboBox,
            QLineEdit,
            QPlainTextEdit,
            QSpinBox,
            QTabBar,
            QTextEdit,
        )

        target_types = (
            QLineEdit,
            QPlainTextEdit,
            QTextEdit,
            QComboBox,
            QSpinBox,
            QTabBar,
            QAbstractButton,
            QAbstractScrollArea,
        )

        for widget in self.findChildren(QWidget):
            if isinstance(widget, target_types):
                widget.installEventFilter(self)

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        """Perform eventFilter."""
        if event.type() == QEvent.Type.KeyPress:
            key_event: QKeyEvent = event

            if key_event.isAutoRepeat():
                return False

            text = key_event.text().lower()

            if text and text.isalpha():
                self._key_buffer.append(text)
                buffer_len = len(_EASTER_EGG_WORD)

                if len(self._key_buffer) > buffer_len:
                    self._key_buffer = self._key_buffer[-buffer_len:]

                if "".join(self._key_buffer) == _EASTER_EGG_WORD:
                    self._key_buffer.clear()
                    self._trigger_easter_egg()

        return False

    def _trigger_easter_egg(self) -> None:
        if self._easter_active:
            return

        self._easter_active = True

        app = QApplication.instance()
        self._saved_stylesheet = app.styleSheet()

        app.setStyleSheet(
            self._saved_stylesheet
            + f"\n* {{ background-color: {_EASTER_EGG_BG} !important; }}"
        )

        self._play_sound()

        QTimer.singleShot(
            _EASTER_EGG_DURATION_MS, self._deactivate_easter_egg
        )

    def _deactivate_easter_egg(self) -> None:
        app = QApplication.instance()
        app.setStyleSheet(self._saved_stylesheet)
        self._easter_active = False

    def _play_sound(self) -> None:
        """Play the easter-egg sound if QtMultimedia is available."""
        if not _MULTIMEDIA_AVAILABLE:
            return
        sound_path = Path(__file__).parent / "m.mp3"
        if not sound_path.exists():
            return

        self._audio_output = QAudioOutput()
        self._audio_output.setVolume(1.0)

        self._media_player = QMediaPlayer()
        self._media_player.setAudioOutput(self._audio_output)
        self._media_player.setSource(QUrl.fromLocalFile(str(sound_path)))
        self._media_player.play()

    def showEvent(self, event: QShowEvent) -> None:
        """Perform showEvent."""
        super().showEvent(event)

        if self._splitters_restored:
            return

        self._splitters_restored = True
        QTimer.singleShot(0, self._restore_splitters)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Perform closeEvent."""
        for widget in self._tab_widgets.values():
            widget._graceful_shutdown()

        self._save_state()
        super().closeEvent(event)