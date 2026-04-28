"""
Менеджер сохранения и восстановления настроек вкладок.
Использует QSettings. Синглтон.
"""
from PySide6.QtCore import QSettings


class SettingsManager:
    _instance = None

    def __init__(self):
        self.settings = QSettings("prefixopt", "gui")
        self._tabs = {}  # имя вкладки -> widget

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_tab(self, name: str, widget):
        self._tabs[name] = widget

    def unregister_tab(self, name: str):
        self._tabs.pop(name, None)

    def save_tab_settings(self, name: str):
        """Сохраняет настройки вкладки (если есть метод save_settings)"""
        widget = self._tabs.get(name)
        if widget and hasattr(widget, 'save_settings'):
            try:
                state = widget.save_settings()
                self.settings.setValue(f"tabs/{name}", state)
            except Exception:
                pass

    def load_tab_settings(self, name: str):
        """Загружает и применяет настройки, если есть метод load_settings"""
        widget = self._tabs.get(name)
        if widget and hasattr(widget, 'load_settings'):
            try:
                state = self.settings.value(f"tabs/{name}")
                if state is not None:
                    widget.load_settings(state)
            except Exception:
                pass

    def save_all(self):
        for name in self._tabs:
            self.save_tab_settings(name)
        self.settings.sync()

    def load_all(self):
        for name in self._tabs:
            self.load_tab_settings(name)

    # Работа с Recent Files
    def add_recent_file(self, path: str):
        recent = self.recent_files()
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:10]  # максимум 10
        self.settings.setValue("recent_files", recent)

    def recent_files(self):
        return self.settings.value("recent_files", []) or []