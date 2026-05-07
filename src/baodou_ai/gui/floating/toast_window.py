"""Transient status toast shown above the floating ball."""

from __future__ import annotations

from PyQt5.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QTimer, Qt
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from baodou_ai.core.screenshot import CAPTURE_EXCLUDE_PROPERTY
from baodou_ai.gui.floating.overlay_utils import screen_at, setup_overlay_window
from baodou_ai.gui.floating.theme import PALETTE


class ToastWindow(QWidget):
    _WINDOW_OPACITY = 0.94

    def __init__(self, controller: "FloatingController"):
        super().__init__()
        self.controller = controller

        setup_overlay_window(self, no_activate=True)
        self.setProperty(CAPTURE_EXCLUDE_PROPERTY, True)

        self._label = QLabel("", self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(
            f"""
            QLabel {{
                background-color: rgba(17, 17, 17, 235);
                border: 1px solid rgba(255, 255, 255, 36);
                border-radius: 14px;
                color: {PALETTE["white"]};
                font-size: 12px;
                padding: 8px 14px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(260)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.finished.connect(self._on_fade_finished)

        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._start_fade_out)

        self.hide()

    def show_message(self, anchor: QPoint, text: str) -> None:
        message = str(text or "").strip()
        if not message:
            return
        self._hold_timer.stop()
        self._fade_anim.stop()
        self._label.setText(message)
        self._label.adjustSize()
        width = self._label.sizeHint().width()
        height = self._label.sizeHint().height()
        self.resize(width, height)
        self._reposition(anchor)
        self.setWindowOpacity(self._WINDOW_OPACITY)
        self.show()
        self.update()
        self._hold_timer.start(1000)

    def hide_message(self) -> None:
        self._hold_timer.stop()
        self._fade_anim.stop()
        self.hide()
        self.setWindowOpacity(self._WINDOW_OPACITY)

    def reposition(self, anchor: QPoint) -> None:
        if self.isVisible():
            self._reposition(anchor)

    def _reposition(self, anchor: QPoint) -> None:
        ball_size = int(getattr(self.controller, "ball_size", 72) or 72)
        gap = 10
        x = int(anchor.x() + (ball_size - self.width()) / 2)
        y = int(anchor.y() - self.height() - gap)

        screen = screen_at(anchor + QPoint(ball_size // 2, ball_size // 2))
        if screen is None:
            screen = screen_at(QPoint(x, y))
        sg = screen.geometry() if screen is not None else QRect(0, 0, 1920, 1080)

        x = max(sg.x() + 4, min(x, sg.x() + sg.width() - self.width() - 4))
        y = max(sg.y() + 4, min(y, sg.y() + sg.height() - self.height() - 4))
        self.setGeometry(x, y, self.width(), self.height())

    def _start_fade_out(self) -> None:
        self._fade_anim.stop()
        self._fade_anim.setStartValue(float(self.windowOpacity()))
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()

    def _on_fade_finished(self) -> None:
        if float(self.windowOpacity()) <= 0.01:
            self.hide()
            self.setWindowOpacity(self._WINDOW_OPACITY)

