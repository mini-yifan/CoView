"""Suggestion overlay shown below the floating ball."""

from __future__ import annotations

from typing import List

from PyQt5.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from baodou_ai.core.screenshot import CAPTURE_EXCLUDE_PROPERTY
from baodou_ai.gui.floating.overlay_utils import screen_at, setup_overlay_window
from baodou_ai.gui.floating.theme import PALETTE


class SuggestionWindow(QWidget):
    """Two clickable suggestions shown below the floating ball."""

    clicked = pyqtSignal(str)
    _WINDOW_OPACITY = 0.9
    _MIN_WIDTH = 140
    _MAX_WIDTH = 520

    def __init__(self, controller: "FloatingController"):
        super().__init__()
        self.controller = controller
        self._suggestions: List[str] = []
        self._buttons: List[QPushButton] = []
        self._privacy_notice_visible = False
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(220)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

        setup_overlay_window(self, no_activate=True)
        self.setProperty(CAPTURE_EXCLUDE_PROPERTY, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: rgba(0, 0, 0, 0);
            }}
            QPushButton {{
                background-color: {PALETTE['panel_bg']};
                border: 1px solid {PALETTE['border']};
                border-radius: 12px;
                color: {PALETTE['text']};
                padding: 8px 10px;
                text-align: left;
                font-size: 12px;
            }}
            QPushButton:hover {{
                border-color: {PALETTE['border_dark']};
                background-color: {PALETTE['input_bg']};
            }}
            QPushButton[privacyNotice="true"],
            QPushButton[privacyNotice="true"]:disabled,
            QPushButton[privacyNotice="true"]:hover {{
                background-color: {PALETTE['black']};
                border: 1px solid {PALETTE['black']};
                color: {PALETTE['white']};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Two rows of suggestion buttons.
        for _ in range(2):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            btn = QPushButton("")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setFixedHeight(38)
            btn.clicked.connect(lambda _checked=False, b=btn: self._on_button_clicked(b))
            row.addWidget(btn, 1)
            root.addLayout(row)
            self._buttons.append(btn)

        self.setWindowOpacity(self._WINDOW_OPACITY)
        self.resize(self._MIN_WIDTH, 94)

    def _on_button_clicked(self, button: QPushButton) -> None:
        try:
            text = button.text().strip()
        except Exception:
            text = ""
        if not text:
            return
        self.clicked.emit(text)

    def show_suggestions(self, anchor: QPoint, suggestions: List[str]) -> None:
        self._privacy_notice_visible = False
        self._suggestions = [str(s or "").strip() for s in (suggestions or [])][:2]
        while len(self._suggestions) < 2:
            self._suggestions.append("")

        for idx, btn in enumerate(self._buttons):
            btn.setProperty("privacyNotice", False)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.show()
            text = self._suggestions[idx] if idx < len(self._suggestions) else ""
            btn.setText(text)
            btn.setEnabled(bool(text))

        self._show_with_fade(anchor)

    def show_privacy_notice(self, anchor: QPoint, text: str = "当前窗口禁用智能推荐") -> None:
        self._privacy_notice_visible = True
        self._suggestions = []
        for idx, btn in enumerate(self._buttons):
            if idx == 0:
                btn.setText(str(text or "当前窗口禁用智能推荐"))
                btn.setEnabled(False)
                btn.setProperty("privacyNotice", True)
                btn.show()
            else:
                btn.setText("")
                btn.setEnabled(False)
                btn.setProperty("privacyNotice", False)
                btn.hide()
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self._show_with_fade(anchor)

    def hide_suggestions(self) -> None:
        self._privacy_notice_visible = False
        self._suggestions = []
        self._fade_anim.stop()
        self.setWindowOpacity(self._WINDOW_OPACITY)
        self.hide()

    def _show_with_fade(self, anchor: QPoint) -> None:
        self._update_size_for_content(anchor)
        self._reposition_for_anchor(anchor)
        self.clearFocus()
        self._fade_anim.stop()
        self.setWindowOpacity(0.0)
        self.show()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(self._WINDOW_OPACITY)
        self._fade_anim.start()
        self.update()

    def reposition(self, anchor: QPoint) -> None:
        if not self.isVisible():
            return
        self._reposition_for_anchor(anchor)

    def _reposition_for_anchor(self, anchor: QPoint) -> None:
        # Place under the ball with small gap, clamp to current screen.
        ball_size = int(getattr(self.controller, "ball_size", 72) or 72)
        gap = 8
        x = int(anchor.x())
        y = int(anchor.y() + ball_size + gap)

        screen = screen_at(anchor + QPoint(ball_size // 2, ball_size // 2))
        if screen is None:
            screen = screen_at(QPoint(x, y))
        if screen is not None:
            sg = screen.geometry()
        else:
            sg = QRect(0, 0, 1920, 1080)

        w = int(self.width() or 240)
        h = int(self.height() or 90)

        # Keep the suggestion window inside the screen bounds.
        x = max(sg.x() + 4, min(x, sg.x() + sg.width() - w - 4))
        y = max(sg.y() + 4, min(y, sg.y() + sg.height() - h - 4))
        self.setGeometry(x, y, w, h)

    def _update_size_for_content(self, anchor: QPoint) -> None:
        screen = screen_at(anchor)
        max_width = self._MAX_WIDTH
        if screen is not None:
            max_width = max(self._MIN_WIDTH, min(self._MAX_WIDTH, screen.geometry().width() - 24))

        longest = 0
        visible_buttons = [btn for btn in self._buttons if not btn.isHidden()]
        if not visible_buttons:
            visible_buttons = self._buttons[:1]

        for btn in visible_buttons:
            text = btn.text().strip()
            metrics = btn.fontMetrics()
            text_width = metrics.horizontalAdvance(text) if text else 0
            longest = max(longest, text_width)

        # Width should be just enough to fully show the longest suggestion:
        # - text pixel width
        # - plus stylesheet padding left/right (10px each)
        # - plus a small buffer for font rendering and borders
        button_width = longest + 10 * 2 + 12
        button_width = max(self._MIN_WIDTH - 12, min(max_width - 12, button_width))
        for btn in visible_buttons:
            btn.setFixedWidth(button_width)

        total_width = button_width + 12
        row_count = len(visible_buttons)
        total_height = 6 + row_count * 38 + max(0, row_count - 1) * 6 + 6
        self.resize(total_width, total_height)
