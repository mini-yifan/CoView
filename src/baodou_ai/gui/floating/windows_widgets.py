"""Windows-specific floating overlay widgets."""

from __future__ import annotations

from PyQt5.QtCore import QTimer

from baodou_ai.gui.floating.ball import BallWindow, EdgeBarWindow
from baodou_ai.gui.floating.panel import PanelWindow
from baodou_ai.gui.floating.suggestion_window import SuggestionWindow
from baodou_ai.gui.floating.toast_window import ToastWindow


class _WindowsOverlayMixin:
    def _adapter(self):
        controller = getattr(self, "controller", None)
        return getattr(controller, "_platform_adapter", None)

    def _schedule_native_overlay_refresh(self) -> None:
        if not self.isVisible():
            return
        if bool(getattr(self, "_overlay_refresh_pending", False)):
            return
        setattr(self, "_overlay_refresh_pending", True)
        QTimer.singleShot(0, self._flush_native_overlay_refresh)

    def _flush_native_overlay_refresh(self) -> None:
        setattr(self, "_overlay_refresh_pending", False)
        self._refresh_native_overlay()

    def _refresh_native_overlay(self) -> None:
        if not self.isVisible():
            return
        adapter = self._adapter()
        if adapter is None:
            return
        prepare = getattr(adapter, "prepare_overlay_window", None)
        if callable(prepare):
            prepare(self)


class WindowsBallWindow(_WindowsOverlayMixin, BallWindow):
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._schedule_native_overlay_refresh()

    def exit_transparent_mode(self) -> None:
        super().exit_transparent_mode()
        self._schedule_native_overlay_refresh()


class WindowsEdgeBarWindow(_WindowsOverlayMixin, EdgeBarWindow):
    def __init__(self, controller: "FloatingController"):
        super().__init__(controller)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._schedule_native_overlay_refresh()

    def show_at_edge(self, edge_side: str, anchor) -> None:
        super().show_at_edge(edge_side, anchor)
        self._schedule_native_overlay_refresh()

    def exit_transparent_mode(self) -> None:
        super().exit_transparent_mode()
        self._schedule_native_overlay_refresh()


class WindowsPanelWindow(_WindowsOverlayMixin, PanelWindow):
    def __init__(self, controller: "FloatingController"):
        super().__init__(controller)
        self.geo_anim.finished.connect(self._schedule_native_overlay_refresh)
        self.opacity_anim.finished.connect(self._schedule_native_overlay_refresh)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._schedule_native_overlay_refresh()

    def exit_transparent_mode(self) -> None:
        super().exit_transparent_mode()
        self._schedule_native_overlay_refresh()


class WindowsSuggestionWindow(_WindowsOverlayMixin, SuggestionWindow):
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._schedule_native_overlay_refresh()


class WindowsToastWindow(_WindowsOverlayMixin, ToastWindow):
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._schedule_native_overlay_refresh()
