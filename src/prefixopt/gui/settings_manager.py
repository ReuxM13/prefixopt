"""
Persistent settings for the GUI, built on top of :class:`QSettings`.

A single :class:`SettingsManager` singleton holds:
    * per-tab state (checkboxes, combo boxes, recent text, etc.);
    * main-window geometry and the active tab;
    * splitter sizes;
    * the recent-files list.

Tabs participate by implementing ``save_settings``/``load_settings`` and
registering themselves with :meth:`register_tab`. Storage uses the platform's
native backend (Registry on Windows, plist on macOS, INI files on Linux).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSettings


class SettingsManager:
    """Singleton wrapper around QSettings with tab-specific helpers."""

    _instance: "SettingsManager | None" = None

    def __init__(self) -> None:
        # Organization/application names determine where QSettings stores data.
        """Initialise the component."""
        self.settings = QSettings("prefixopt", "gui")
        self._tabs: dict[str, object] = {}

    @classmethod
    def instance(cls) -> "SettingsManager":
        """Return the process-wide singleton, creating it on first use."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_tab(self, name: str, widget: object) -> None:
        """Register a tab so its settings can be saved/loaded by name."""
        self._tabs[name] = widget

    def unregister_tab(self, name: str) -> None:
        """Remove a previously registered tab."""
        self._tabs.pop(name, None)

    def save_tab_settings(self, name: str) -> None:
        """Ask a tab to serialise its state, then persist the dict."""
        widget = self._tabs.get(name)
        if widget and hasattr(widget, "save_settings"):
            try:
                state = widget.save_settings()
                self.settings.setValue(f"tabs/{name}", state)
            except Exception:
                # Settings errors must never crash the application.
                pass

    def load_tab_settings(self, name: str) -> None:
        """Restore a tab's previously saved state, if any."""
        widget = self._tabs.get(name)
        if widget and hasattr(widget, "load_settings"):
            try:
                state = self.settings.value(f"tabs/{name}")
                if state is not None:
                    widget.load_settings(state)
            except Exception:
                pass

    def save_all(self) -> None:
        """Persist the state of every registered tab."""
        for name in self._tabs:
            self.save_tab_settings(name)
        self.settings.sync()

    def load_all(self) -> None:
        """Restore the state of every registered tab."""
        for name in self._tabs:
            self.load_tab_settings(name)

    # ---- Main window ----

    def save_main_window(
        self,
        geometry: Any,
        maximized: bool,
        current_tab: int,
    ) -> None:
        """Save window geometry, maximized state and active tab."""
        self.settings.setValue("main_window/geometry", geometry)
        self.settings.setValue("main_window/maximized", maximized)
        self.settings.setValue("main_window/current_tab", current_tab)

    def load_main_window_geometry(self) -> Any:
        """Return the saved window geometry (QByteArray) or None."""
        return self.settings.value("main_window/geometry")

    def load_main_window_maximized(self) -> bool:
        """Return whether the window was maximized when last closed."""
        value = self.settings.value("main_window/maximized", False)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes"}
        return bool(value)

    def load_main_window_current_tab(self) -> int:
        """Return the index of the tab that was active on last close."""
        value = self.settings.value("main_window/current_tab", 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    # ---- Splitters ----

    def save_splitter_sizes(self, key: str, sizes: list[int]) -> None:
        """Persist the sizes of a named QSplitter."""
        self.settings.setValue(f"splitters/{key}", sizes)

    def load_splitter_sizes(self, key: str) -> list[int]:
        """Load previously saved splitter sizes for ``key``."""
        value = self.settings.value(f"splitters/{key}", [])
        if value is None:
            return []

        if isinstance(value, list):
            result: list[int] = []
            for item in value:
                try:
                    result.append(int(item))
                except (TypeError, ValueError):
                    continue
            return result

        try:
            return [int(value)]
        except (TypeError, ValueError):
            return []

    # ---- Recent files ----

    def add_recent_file(self, path: str) -> None:
        """Add ``path`` to the top of the recent-files list (max 10)."""
        recent = self.recent_files()
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self.settings.setValue("recent_files", recent[:10])

    def recent_files(self) -> list[str]:
        """Return the list of recently opened file paths."""
        value = self.settings.value("recent_files", [])
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]
