"""Windows taskbar host window for the floating app."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import QEvent, QTimer, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QLabel, QMainWindow, QWidget


def _candidate_icon_paths() -> list[Path]:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / "app_icons" / "AppIcon.ico")
    exe_dir = Path(sys.executable).resolve().parent
    candidates.append(exe_dir / "app_icons" / "AppIcon.ico")
    candidates.append(Path(__file__).resolve().parents[4] / "app_icons" / "AppIcon.ico")
    return candidates


def resolve_windows_app_icon() -> QIcon:
    for candidate in _candidate_icon_paths():
        if candidate.exists():
            return QIcon(str(candidate))
    return QIcon()


class WindowsTaskbarHostWindow(QMainWindow):
    """A minimal normal window whose taskbar button represents the whole app."""

    def __init__(self, controller) -> None:
        super().__init__()
        self._controller = controller
        self._allow_close = False
        self._suppress_restore_action = False

        self.setWindowTitle("CoView")
        icon = resolve_windows_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setMinimumSize(360, 120)
        self.resize(420, 140)
        self.setCentralWidget(self._build_placeholder())

    def _build_placeholder(self) -> QWidget:
        label = QLabel("CoView is running.")
        label.setAlignment(Qt.AlignCenter)
        container = QWidget()
        label.setParent(container)
        label.setGeometry(0, 0, 420, 140)
        return container

    def show_for_taskbar(self) -> None:
        self.showMinimized()

    def allow_shutdown_close(self) -> None:
        self._allow_close = True

    def closeEvent(self, event) -> None:
        if self._allow_close:
            event.accept()
            super().closeEvent(event)
            return
        event.ignore()
        shutdown = getattr(self._controller, "shutdown", None)
        if callable(shutdown):
            shutdown()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() != QEvent.WindowStateChange:
            return
        if self._allow_close or self._suppress_restore_action:
            return
        if self.isMinimized():
            return
        self._suppress_restore_action = True
        QTimer.singleShot(0, self._open_settings_and_reminimize)

    def _open_settings_and_reminimize(self) -> None:
        try:
            opener = getattr(self._controller, "open_console_page", None)
            if callable(opener):
                opener("general")
            self.showMinimized()
        finally:
            self._suppress_restore_action = False
