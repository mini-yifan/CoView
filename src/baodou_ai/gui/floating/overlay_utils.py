"""Shared helpers for floating overlay windows."""

from __future__ import annotations

import sys
from typing import Optional

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtWidgets import QApplication, QWidget


def screen_at(point: QPoint):
    app = QApplication.instance()
    if app is None:
        return QApplication.primaryScreen()
    for screen in app.screens():
        if screen.geometry().contains(point):
            return screen
    return QApplication.primaryScreen()


def apply_native_borderless_hints(widget: QWidget) -> None:
    """Apply platform-native overlay window preparation when available."""
    if not sys.platform.startswith("win"):
        return

    controller = getattr(widget, "controller", None)
    platform_adapter = getattr(controller, "_platform_adapter", None)
    if platform_adapter is None:
        platform_adapter = getattr(widget, "_platform_adapter", None)
    prepare = getattr(platform_adapter, "prepare_overlay_window", None)
    if callable(prepare) and widget.isVisible():
        prepare(widget)


def setup_overlay_window(widget: QWidget, no_activate: bool = False) -> None:
    flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    if no_activate and hasattr(Qt, "WindowDoesNotAcceptFocus"):
        flags |= Qt.WindowDoesNotAcceptFocus
    widget.setWindowFlags(flags)
    widget.setAttribute(Qt.WA_TranslucentBackground)
    if hasattr(Qt, "WA_MacAlwaysShowToolWindow"):
        widget.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
    if no_activate and hasattr(Qt, "WA_ShowWithoutActivating"):
        widget.setAttribute(Qt.WA_ShowWithoutActivating, True)


def enter_overlay_transparent_mode(widget: QWidget, platform_adapter) -> None:
    was_visible = widget.isVisible()
    setattr(widget, "_transparent_mode_restore_needed", was_visible)
    if not was_visible:
        return
    widget.clearFocus()
    platform_adapter.enter_transparent_mode(widget)


def exit_overlay_transparent_mode(widget: QWidget, platform_adapter) -> None:
    restore_needed = bool(getattr(widget, "_transparent_mode_restore_needed", False))
    setattr(widget, "_transparent_mode_restore_needed", False)
    if not restore_needed:
        return
    platform_adapter.exit_transparent_mode(widget)


def edge_anchor(edge: str, sg: QRect, ball_size: int, off: int = 2, anchor: Optional[QPoint] = None) -> QPoint:
    if edge == "left":
        x = sg.x() - ball_size - off
        y = anchor.y() if anchor else sg.y()
    elif edge == "right":
        x = sg.x() + sg.width() + off
        y = anchor.y() if anchor else sg.y()
    elif edge == "top":
        x = anchor.x() if anchor else sg.x()
        y = sg.y() - ball_size - off
    else:
        x = anchor.x() if anchor else sg.x()
        y = sg.y() + sg.height() + off
    return QPoint(x, y)


def edge_anchor_in(edge: str, sg: QRect, ball_size: int, pad: int = 5) -> QPoint:
    if edge == "left":
        return QPoint(sg.x() + pad, 0)
    if edge == "right":
        return QPoint(sg.x() + sg.width() - ball_size - pad, 0)
    if edge == "top":
        return QPoint(0, sg.y() + pad)
    return QPoint(0, sg.y() + sg.height() - ball_size - pad)
