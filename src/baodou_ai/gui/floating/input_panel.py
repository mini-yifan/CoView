"""Input controls used by the floating panel."""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QLineEdit, QPushButton

from baodou_ai.gui.floating.theme import PALETTE, input_style
from baodou_ai.gui.i18n import t


class StopButton(QPushButton):
    """White/gray stop button for the monochrome floating panel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setText("")
        self.setFixedSize(44, 44)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        outer_rect = self.rect().adjusted(2, 2, -2, -2)
        painter.setPen(QPen(QColor(PALETTE["border_dark"]), 1))
        painter.setBrush(QColor(PALETTE["white"]))
        painter.drawEllipse(outer_rect)

        inner_rect = outer_rect.adjusted(8, 8, -8, -8)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(PALETTE["black"]))
        painter.drawEllipse(inner_rect)




class FloatingInputPanel(QLineEdit):
    """Single-line task input for the floating panel."""

    submitted = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(t("input_placeholder"))
        self.setStyleSheet(input_style())
        self.returnPressed.connect(self._emit_submit)

    def _emit_submit(self) -> None:
        text = self.text().strip()
        if not text:
            return
        self.clear()
        self.submitted.emit(text)
