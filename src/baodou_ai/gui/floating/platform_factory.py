"""Platform-aware constructors for floating overlay widgets."""

from __future__ import annotations

import platform

from baodou_ai.gui.floating.ball import BallWindow, EdgeBarWindow
from baodou_ai.gui.floating.panel import PanelWindow
from baodou_ai.gui.floating.suggestion_window import SuggestionWindow
from baodou_ai.gui.floating.toast_window import ToastWindow
from baodou_ai.gui.floating.windows_taskbar_host import WindowsTaskbarHostWindow
from baodou_ai.gui.floating.windows_widgets import (
    WindowsBallWindow,
    WindowsEdgeBarWindow,
    WindowsPanelWindow,
    WindowsSuggestionWindow,
    WindowsToastWindow,
)


def create_ball_window(controller):
    if platform.system() == "Windows":
        return WindowsBallWindow(controller)
    return BallWindow(controller)


def create_panel_window(controller):
    if platform.system() == "Windows":
        return WindowsPanelWindow(controller)
    return PanelWindow(controller)


def create_edge_bar_window(controller):
    if platform.system() == "Windows":
        return WindowsEdgeBarWindow(controller)
    return EdgeBarWindow(controller)


def create_suggestion_window(controller):
    if platform.system() == "Windows":
        return WindowsSuggestionWindow(controller)
    return SuggestionWindow(controller)


def create_toast_window(controller):
    if platform.system() == "Windows":
        return WindowsToastWindow(controller)
    return ToastWindow(controller)


def create_taskbar_host_window(controller):
    if platform.system() == "Windows":
        return WindowsTaskbarHostWindow(controller)
    return None
