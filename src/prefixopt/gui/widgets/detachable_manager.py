"""
Менеджер для отсоединения виджета в отдельное окно и возврата обратно.
Корректно работает с QSplitter, обрабатывает закрытие окна.
"""
from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QFrame, QSplitter


class DetachablePopup(QFrame):
    """Внутренний класс окна, перехватывает событие закрытия."""
    def __init__(self, manager, widget, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.widget = widget
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self and event.type() == QEvent.Close:
            self.manager.attach()
            return True
        return super().eventFilter(obj, event)


class DetachableWidgetManager:
    """
    Управляет отделением виджета в независимое окно.
    """

    def __init__(self, widget: QWidget, button: QPushButton) -> None:
        self.widget = widget
        self.button = button
        self.popup_window = None

        self.original_parent = widget.parentWidget()
        self.is_splitter = False
        self.original_splitter = None
        self.original_layout = None
        self.original_index = -1

        self.button.clicked.connect(self._toggle)

    def _toggle(self) -> None:
        if self.popup_window is not None:
            self.attach()
        else:
            self.detach()

    def detach(self) -> None:
        parent_widget = self.widget.parentWidget()
        if parent_widget:
            if isinstance(parent_widget, QSplitter):
                self.is_splitter = True
                self.original_splitter = parent_widget
                self.original_index = parent_widget.indexOf(self.widget)
                self.widget.hide()
                self.widget.setParent(None)
            else:
                self.is_splitter = False
                self.original_layout = parent_widget.layout()
                if self.original_layout:
                    self.original_index = self.original_layout.indexOf(self.widget)
                    self.original_layout.removeWidget(self.widget)

        # Создаём окно с перехватом закрытия
        self.popup_window = DetachablePopup(self, self.widget)
        self.popup_window.setWindowTitle(self.widget.windowTitle() or "Detached")
        self.popup_window.setWindowFlags(Qt.Window)
        self.popup_window.resize(self.widget.size().expandedTo(self.popup_window.minimumSizeHint()))

        layout = QVBoxLayout(self.popup_window)
        layout.addWidget(self.widget)

        dock_btn = QPushButton("⮌ Dock back")
        dock_btn.clicked.connect(self.attach)
        layout.addWidget(dock_btn)

        self.widget.show()  # гарантированно показываем виджет
        self.popup_window.show()
        self.button.setText("⮌ Dock")
        self.button.setToolTip("Return panel to original place")

    def attach(self) -> None:
        if self.popup_window is None:
            return

        # Убираем виджет из окна
        popup_layout = self.popup_window.layout()
        if popup_layout:
            popup_layout.removeWidget(self.widget)

        self.widget.setParent(None)

        # Закрываем окно
        self.popup_window.close()
        self.popup_window = None

        # Возвращаем в исходный контейнер
        if self.is_splitter and self.original_splitter:
            self.original_splitter.insertWidget(self.original_index, self.widget)
            self.widget.show()
            self.original_splitter = None
        elif self.original_layout:
            if self.original_index < 0 or self.original_index > self.original_layout.count():
                self.original_index = -1
            self.original_layout.insertWidget(self.original_index, self.widget)
            self.widget.show()
            self.original_layout.invalidate()
            self.original_layout.activate()
            self.original_layout = None

        self.button.setText("↗ Pop out")
        self.button.setToolTip("Open in separate window")