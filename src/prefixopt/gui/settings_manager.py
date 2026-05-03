"""
Менеджер сохранения и восстановления настроек GUI.

Использует QSettings. Реализован как синглтон.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSettings


class SettingsManager:
    """Менеджер настроек приложения и вкладок."""

    _instance: "SettingsManager | None" = None

    def __init__(self) -> None:
        self.settings = QSettings("prefixopt", "gui")
        self._tabs: dict[str, object] = {}

    @classmethod
    def instance(cls) -> "SettingsManager":
        """
        Возвращает экземпляр менеджера настроек.

        Returns:
            Экземпляр SettingsManager.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_tab(self, name: str, widget: object) -> None:
        """
        Регистрирует вкладку для сохранения настроек.

        Args:
            name: Ключ вкладки.
            widget: Экземпляр виджета вкладки.
        """
        self._tabs[name] = widget

    def unregister_tab(self, name: str) -> None:
        """
        Удаляет вкладку из регистрации.

        Args:
            name: Ключ вкладки.
        """
        self._tabs.pop(name, None)

    def save_tab_settings(self, name: str) -> None:
        """
        Сохраняет настройки одной вкладки.

        Args:
            name: Ключ вкладки.
        """
        widget = self._tabs.get(name)
        if widget and hasattr(widget, "save_settings"):
            try:
                state = widget.save_settings()
                self.settings.setValue(f"tabs/{name}", state)
            except Exception:
                pass

    def load_tab_settings(self, name: str) -> None:
        """
        Загружает настройки одной вкладки.

        Args:
            name: Ключ вкладки.
        """
        widget = self._tabs.get(name)
        if widget and hasattr(widget, "load_settings"):
            try:
                state = self.settings.value(f"tabs/{name}")
                if state is not None:
                    widget.load_settings(state)
            except Exception:
                pass

    def save_all(self) -> None:
        """
        Сохраняет настройки всех зарегистрированных вкладок.
        """
        for name in self._tabs:
            self.save_tab_settings(name)
        self.settings.sync()

    def load_all(self) -> None:
        """
        Загружает настройки всех зарегистрированных вкладок.
        """
        for name in self._tabs:
            self.load_tab_settings(name)

    def save_main_window(
        self,
        geometry: Any,
        maximized: bool,
        current_tab: int,
    ) -> None:
        """
        Сохраняет геометрию и состояние главного окна.

        Args:
            geometry: QByteArray из saveGeometry().
            maximized: Признак максимизированного окна.
            current_tab: Индекс активной вкладки.
        """
        self.settings.setValue("main_window/geometry", geometry)
        self.settings.setValue("main_window/maximized", maximized)
        self.settings.setValue("main_window/current_tab", current_tab)

    def load_main_window_geometry(self) -> Any:
        """
        Возвращает сохраненную геометрию окна.

        Returns:
            QByteArray геометрии или None.
        """
        return self.settings.value("main_window/geometry")

    def load_main_window_maximized(self) -> bool:
        """
        Возвращает признак максимизированного окна.

        Returns:
            True, если окно было максимизировано.
        """
        value = self.settings.value("main_window/maximized", False)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes"}
        return bool(value)

    def load_main_window_current_tab(self) -> int:
        """
        Возвращает индекс последней активной вкладки.

        Returns:
            Индекс вкладки.
        """
        value = self.settings.value("main_window/current_tab", 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def save_splitter_sizes(self, key: str, sizes: list[int]) -> None:
        """
        Сохраняет размеры сплиттера.

        Args:
            key: Ключ сплиттера.
            sizes: Список размеров.
        """
        self.settings.setValue(f"splitters/{key}", sizes)

    def load_splitter_sizes(self, key: str) -> list[int]:
        """
        Загружает размеры сплиттера.

        Args:
            key: Ключ сплиттера.

        Returns:
            Список размеров сплиттера.
        """
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

    def add_recent_file(self, path: str) -> None:
        """
        Добавляет файл в список недавних.

        Args:
            path: Путь к файлу.
        """
        recent = self.recent_files()
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self.settings.setValue("recent_files", recent[:10])

    def recent_files(self) -> list[str]:
        """
        Возвращает список недавних файлов.

        Returns:
            Список путей.
        """
        value = self.settings.value("recent_files", [])
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]