"""Floating ball and edge bar widgets."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QAbstractAnimation, QEasingCurve, QPoint, QPropertyAnimation, QRect, QTimer, Qt
from PyQt5.QtGui import QColor, QCursor, QMovie, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PyQt5.QtWidgets import QApplication, QWidget

from baodou_ai.core.screenshot import CAPTURE_EXCLUDE_PROPERTY
from baodou_ai.gui.floating.overlay_utils import (
    apply_native_borderless_hints,
    enter_overlay_transparent_mode,
    exit_overlay_transparent_mode,
    screen_at,
    setup_overlay_window,
)
from baodou_ai.gui.floating.theme import PALETTE


class BallWindow(QWidget):
    """绿色悬浮球。"""

    def __init__(self, controller: "FloatingController"):
        super().__init__()
        self.controller = controller
        self.ball_size = controller.ball_size
        self.shadow_margin = 5
        self.drag_offset = QPoint()
        self.is_dragging = False
        self._asset_path = ""
        self._static_pixmap: Optional[QPixmap] = None
        self._movie: Optional[QMovie] = None
        self._animation_always_play = False
        self._reset_animation_on_leave = True
        self._hovered = False
        self._press_started_at = 0.0
        self._press_global_pos = QPoint()
        self._voice_indicator_state = "off"
        self._voice_indicator_level = 0.0

        self.long_press_timer = QTimer(self)
        self.long_press_timer.setInterval(200)
        self.long_press_timer.setSingleShot(True)
        self.long_press_timer.timeout.connect(self._on_long_press)

        setup_overlay_window(self, no_activate=True)
        self.setMouseTracking(True)
        self._apply_window_mode()
        self.setProperty(CAPTURE_EXCLUDE_PROPERTY, True)

        total = self.ball_size + self.shadow_margin * 2
        self.resize(total, total)
        self._apply_shape()
        self.reload_asset()

    def _apply_window_mode(self) -> None:
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        if hasattr(Qt, "WindowDoesNotAcceptFocus"):
            flags |= Qt.WindowDoesNotAcceptFocus
        current_flags = self.windowFlags()
        if current_flags & flags == flags:
            if hasattr(Qt, "WA_ShowWithoutActivating") and not self.testAttribute(Qt.WA_ShowWithoutActivating):
                self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            return
        geometry = self.geometry()
        was_visible = self.isVisible()
        self.setWindowFlags(current_flags | flags)
        if hasattr(Qt, "WA_ShowWithoutActivating"):
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        if was_visible:
            self.setGeometry(geometry)
            self.show()

    def _surface_rect(self) -> QRect:
        return QRect(self.shadow_margin, self.shadow_margin, self.ball_size, self.ball_size)

    def _apply_shape(self) -> None:
        surface = self._surface_rect()
        region = QRegion(surface, QRegion.Ellipse)
        for extra in (2, 4):
            region = region.united(QRegion(surface.adjusted(-extra, -extra, extra, extra), QRegion.Ellipse))
        self.setMask(region)

    def move_to_anchor(self, anchor: QPoint) -> None:
        self.setGeometry(anchor.x() - self.shadow_margin, anchor.y() - self.shadow_margin, self.width(), self.height())

    def global_ball_rect(self) -> QRect:
        return QRect(self.x() + self.shadow_margin, self.y() + self.shadow_margin, self.ball_size, self.ball_size)

    def reload_asset(self) -> None:
        self._clear_asset()
        config = getattr(self.controller, "_config", None)
        asset_config = config.floating_ball_config if config is not None else {}
        self._animation_always_play = bool(asset_config.get("animation_always_play", False))
        self._reset_animation_on_leave = bool(asset_config.get("reset_animation_on_leave", True))
        asset_path = str(asset_config.get("asset_path") or "").strip()
        if not asset_path:
            # Default to the bundled/working-directory GIF if the user did not configure one.
            adapter = getattr(self.controller, "_platform_adapter", None)
            resolver = getattr(adapter, "get_resource_path", None)
            if callable(resolver):
                resolved = resolver("defaultgif.gif")
                if resolved:
                    asset_path = str(resolved)

        if not asset_path:
            self.update()
            return

        path = Path(asset_path).expanduser()
        if not path.is_absolute():
            adapter = getattr(self.controller, "_platform_adapter", None)
            resolver = getattr(adapter, "get_resource_path", None)
            if callable(resolver):
                resolved = resolver(str(path))
                if resolved:
                    path = Path(resolved)
        if not path.exists() or not path.is_file():
            self.update()
            return

        suffix = path.suffix.lower()
        self._asset_path = str(path)
        if suffix == ".gif":
            movie = QMovie(str(path))
            if movie.isValid():
                movie.setCacheMode(QMovie.CacheAll)
                movie.frameChanged.connect(lambda _frame: self.update())
                movie.jumpToFrame(0)
                self._movie = movie
                self.sync_animation_state(reset_if_stopping=False)
                self.update()
                return

        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            self._static_pixmap = pixmap
        self.update()

    def _clear_asset(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        self._static_pixmap = None
        self._asset_path = ""

    def _controller_task_active(self) -> bool:
        task_active = getattr(self.controller, "_task_active", None)
        return bool(task_active()) if callable(task_active) else False

    def sync_animation_state(self, reset_if_stopping: bool = True) -> None:
        if self._movie is None:
            return

        should_play = self.isVisible() and (
            self._animation_always_play or self._hovered or self._controller_task_active()
        )
        if should_play:
            self._movie.start()
            return

        self._movie.stop()
        if reset_if_stopping and self._reset_animation_on_leave:
            self._movie.jumpToFrame(0)
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_window_mode()
        apply_native_borderless_hints(self)
        self._apply_shape()
        self.controller.protect_window(self)
        self.sync_animation_state(reset_if_stopping=False)

    def hideEvent(self, event) -> None:
        self._hovered = False
        self.sync_animation_state(reset_if_stopping=True)
        super().hideEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        surface = self._surface_rect()
        bx, by, bs = float(surface.x()), float(surface.y()), float(self.ball_size)

        painter.setPen(Qt.NoPen)
        pixmap = self._current_asset_pixmap()
        if pixmap is not None and not pixmap.isNull():
            self._draw_asset(painter, surface, pixmap)
        else:
            painter.setBrush(QColor(PALETTE["black"]))
            painter.drawEllipse(int(bx), int(by), int(bs), int(bs))

        if self.controller.is_pinned:
            painter.setPen(QPen(QColor(PALETTE["border_dark"]), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(surface.adjusted(1, 1, -1, -1))

        self._paint_voice_indicator(painter, surface)

    def set_voice_indicator(self, state: str, level: float = 0.0) -> None:
        self._voice_indicator_state = str(state or "off")
        self._voice_indicator_level = max(0.0, min(1.0, float(level or 0.0)))
        self.update()

    def _paint_voice_indicator(self, painter: QPainter, surface: QRect) -> None:
        state = self._voice_indicator_state
        if state == "off":
            return
        config = getattr(self.controller, "_config", None)
        is_wake_state = state.startswith("wake_")
        if is_wake_state:
            if config is not None and not bool(config.get("wake_word_config.show_indicator", True)):
                return
        elif config is not None and not bool(config.get("voice_interaction_config.show_voice_recording_indicator", True)):
            return

        level = max(0.0, min(1.0, self._voice_indicator_level))
        if state == "error":
            color = QColor("#D83B3B")
            radius = 6
        elif state == "wake_error":
            color = QColor("#D83B3B")
            radius = 6
        elif state == "processing":
            color = QColor("#555555")
            radius = 6
        elif state == "wake_triggered":
            color = QColor("#10B981")
            radius = 7
        elif state == "wake_cooldown":
            color = QColor("#F59E0B")
            radius = 6
        elif state == "speaking":
            color = QColor(PALETTE["white"])
            radius = int(5 + level * 5)
            painter.setPen(QPen(QColor(PALETTE["white"]), max(1, int(1 + level * 3))))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(surface.adjusted(5, 5, -5, -5))
        else:
            color = QColor("#D9D9D9")
            radius = 5

        dot_center_x = surface.right() - 10
        dot_center_y = surface.bottom() - 10
        painter.setPen(QPen(QColor(PALETTE["black"]), 1))
        painter.setBrush(color)
        painter.drawEllipse(
            dot_center_x - radius,
            dot_center_y - radius,
            radius * 2,
            radius * 2,
        )

    def _current_asset_pixmap(self) -> Optional[QPixmap]:
        if self._movie is not None:
            pixmap = self._movie.currentPixmap()
            return pixmap if not pixmap.isNull() else None
        return self._static_pixmap

    def _draw_asset(self, painter: QPainter, surface: QRect, pixmap: QPixmap) -> None:
        path = QPainterPath()
        path.addEllipse(float(surface.x()), float(surface.y()), float(surface.width()), float(surface.height()))
        painter.save()
        painter.setClipPath(path)

        target_aspect = surface.width() / max(1, surface.height())
        source_width = pixmap.width()
        source_height = pixmap.height()
        source_aspect = source_width / max(1, source_height)
        if source_aspect > target_aspect:
            crop_width = int(source_height * target_aspect)
            source = QRect((source_width - crop_width) // 2, 0, crop_width, source_height)
        else:
            crop_height = int(source_width / target_aspect)
            source = QRect(0, (source_height - crop_height) // 2, source_width, crop_height)
        painter.drawPixmap(surface, pixmap, source)
        painter.restore()

    def enterEvent(self, event) -> None:
        self._hovered = True
        begin = getattr(self.controller, "begin_interaction", None)
        if callable(begin):
            begin("pointer")
        on_hover = getattr(self.controller, "on_ball_hover_enter", None)
        if callable(on_hover):
            on_hover()
        self.sync_animation_state(reset_if_stopping=False)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        defer = getattr(self.controller, "defer_pointer_interaction_end", None)
        if callable(defer):
            defer()
        self.sync_animation_state(reset_if_stopping=True)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton and self._surface_rect().contains(event.pos()):
            self.controller.show_ball_context_menu(event.globalPos())
            event.accept()
            return

        if event.button() != Qt.LeftButton or not self._surface_rect().contains(event.pos()):
            super().mousePressEvent(event)
            return

        self.drag_offset = event.globalPos() - self.controller.ball_anchor
        self._press_started_at = time.monotonic()
        self._press_global_pos = QPoint(event.globalPos())
        begin = getattr(self.controller, "begin_interaction", None)
        if callable(begin):
            begin("pointer")
        self.long_press_timer.start()
        event.accept()

    def _on_long_press(self) -> None:
        if self.is_dragging:
            return
        self.is_dragging = True
        self.controller.on_ball_long_press()

    def _should_start_drag_from_move(self, global_pos: QPoint) -> bool:
        if self._press_started_at <= 0:
            return False
        elapsed_ms = (time.monotonic() - self._press_started_at) * 1000
        moved = (global_pos - self._press_global_pos).manhattanLength()
        return elapsed_ms >= 200 or moved >= 8

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() != Qt.LeftButton or not self.is_dragging:
            if (
                event.buttons() == Qt.LeftButton
                and self.long_press_timer.isActive()
                and not self.is_dragging
                and self._should_start_drag_from_move(event.globalPos())
            ):
                self.long_press_timer.stop()
                self._on_long_press()
                self.controller.on_ball_drag(event.globalPos() - self.drag_offset)
                event.accept()
                return
            if self.long_press_timer.isActive() and not self.is_dragging:
                event.accept()
            else:
                super().mouseMoveEvent(event)
            return
        self.controller.on_ball_drag(event.globalPos() - self.drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            if self.long_press_timer.isActive() and not self.is_dragging:
                self.controller.on_ball_click()
            elif self.is_dragging:
                self.controller.on_ball_drag_finished()
        self.long_press_timer.stop()
        self.drag_offset = QPoint()
        self._press_started_at = 0.0
        self._press_global_pos = QPoint()
        self.is_dragging = False
        defer = getattr(self.controller, "defer_pointer_interaction_end", None)
        if callable(defer):
            defer()
        event.accept()

    def enter_transparent_mode(self) -> None:
        platform_adapter = getattr(self.controller, "platform_adapter", getattr(self.controller, "_platform_adapter", None))
        enter_overlay_transparent_mode(self, platform_adapter)

    def exit_transparent_mode(self) -> None:
        platform_adapter = getattr(self.controller, "platform_adapter", getattr(self.controller, "_platform_adapter", None))
        exit_overlay_transparent_mode(self, platform_adapter)


class EdgeBarWindow(QWidget):
    """吸边后显示的细条。"""

    def __init__(self, controller: "FloatingController"):
        super().__init__()
        self.controller = controller
        self.ball_size = controller.ball_size
        self.edge_side = "right"
        self.bar_thickness = 6
        self._drag_pos = None

        setup_overlay_window(self, no_activate=True)
        self.setProperty(CAPTURE_EXCLUDE_PROPERTY, True)

        self._breath_anim = QPropertyAnimation(self, b"windowOpacity")
        self._breath_anim.setDuration(1800)
        self._breath_anim.setStartValue(0.5)
        self._breath_anim.setEndValue(1.0)
        self._breath_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._breath_anim.finished.connect(self._toggle_breath)

        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(110)
        self._hover_timer.timeout.connect(self._check_hover)
        self._hover_tracking_enabled = False

        self.hide()

    def _toggle_breath(self) -> None:
        self._breath_anim.setDirection(
            QAbstractAnimation.Backward if self._breath_anim.direction() == QAbstractAnimation.Forward else QAbstractAnimation.Forward
        )
        self._breath_anim.start()

    def _check_hover(self) -> None:
        if not self.isVisible():
            self._hover_timer.stop()
            return
        screen = screen_at(self.geometry().center()) or QApplication.primaryScreen()
        sg = screen.geometry()
        margin = 20
        geo = self.geometry()
        if self.edge_side == "left":
            zone = QRect(sg.x(), geo.y(), margin + geo.width(), geo.height())
        elif self.edge_side == "right":
            zone = QRect(sg.x() + sg.width() - geo.width() - margin, geo.y(), geo.width() + margin, geo.height())
        elif self.edge_side == "top":
            zone = QRect(geo.x(), sg.y(), geo.width(), margin + geo.height())
        else:
            zone = QRect(geo.x(), sg.y() + sg.height() - geo.height() - margin, geo.width(), geo.height() + margin)
        if zone.contains(QCursor.pos()):
            self.controller.unsnap_from_edge(QCursor.pos())
            self._hover_timer.stop()

    def _enable_hover_tracking(self) -> None:
        if self.isVisible() and self._hover_tracking_enabled:
            self._hover_timer.start()

    def show_at_edge(self, edge_side: str, anchor: QPoint) -> None:
        self.edge_side = edge_side
        screen = screen_at(anchor + QPoint(self.ball_size // 2, self.ball_size // 2)) or QApplication.primaryScreen()
        sg = screen.geometry()
        gm = 8
        vertical = edge_side in ("left", "right")

        if vertical:
            w, h = self.bar_thickness + gm * 2, self.ball_size + gm * 2
            y = max(sg.y(), min(anchor.y(), sg.y() + sg.height() - self.ball_size)) - gm
            x = sg.x() - gm if edge_side == "left" else sg.x() + sg.width() - self.bar_thickness - gm
        else:
            w, h = self.ball_size + gm * 2, self.bar_thickness + gm * 2
            x = max(sg.x(), min(anchor.x(), sg.x() + sg.width() - self.ball_size)) - gm
            y = sg.y() - gm if edge_side == "top" else sg.y() + sg.height() - self.bar_thickness - gm

        self.setGeometry(x, y, w, h)
        self.setWindowOpacity(0.5)
        self.show()
        self.raise_()
        self.controller.protect_window(self)
        self._breath_anim.start()
        self._hover_tracking_enabled = True
        self._hover_timer.stop()
        QTimer.singleShot(800, self._enable_hover_tracking)

    def hide_bar(self) -> None:
        self._breath_anim.stop()
        self._hover_tracking_enabled = False
        self._hover_timer.stop()
        self.setWindowOpacity(1.0)
        self.hide()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        gm = 8
        vertical = self.edge_side in ("left", "right")
        bw = self.bar_thickness if vertical else self.ball_size
        bh = self.ball_size if vertical else self.bar_thickness

        for extra, alpha in ((6, 18), (4, 32), (2, 50)):
            color = QColor(PALETTE["scrollbar"])
            color.setAlpha(alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            rx = bw + extra * 2
            painter.drawRoundedRect(gm - extra, gm - extra, rx, bh + extra * 2, rx / 2, rx / 2)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(PALETTE["scrollbar"]))
        painter.drawRoundedRect(gm, gm, bw, bh, bw / 2, bw / 2)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() != Qt.LeftButton or not self._drag_pos:
            return
        screen = screen_at(event.globalPos()) or QApplication.primaryScreen()
        sg = screen.geometry()
        threshold = self.ball_size // 3
        gp = event.globalPos()
        unsnap = (
            (self.edge_side == "left" and gp.x() > sg.x() + threshold)
            or (self.edge_side == "right" and gp.x() < sg.x() + sg.width() - threshold)
            or (self.edge_side == "top" and gp.y() > sg.y() + threshold)
            or (self.edge_side == "bottom" and gp.y() < sg.y() + sg.height() - threshold)
        )
        if unsnap:
            self.controller.unsnap_from_edge(gp)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        event.accept()

    def enter_transparent_mode(self) -> None:
        platform_adapter = getattr(self.controller, "platform_adapter", getattr(self.controller, "_platform_adapter", None))
        enter_overlay_transparent_mode(self, platform_adapter)

    def exit_transparent_mode(self) -> None:
        platform_adapter = getattr(self.controller, "platform_adapter", getattr(self.controller, "_platform_adapter", None))
        exit_overlay_transparent_mode(self, platform_adapter)
