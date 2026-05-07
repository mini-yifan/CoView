"""Compatibility delegate for companion controller."""

from __future__ import annotations

from typing import List


class LegacyCompanionDelegate:
    """Compatibility shim for existing tests/call sites."""

    def __init__(self, controller) -> None:
        self._controller = controller

    def can_show_companion(self) -> bool:
        checker = getattr(self._controller, "can_show_companion", None)
        if callable(checker):
            return bool(checker())
        if bool(getattr(self._controller, "is_edge_hidden", False)):
            return False
        task_active = getattr(self._controller, "_task_active", None)
        if callable(task_active) and bool(task_active()):
            return False
        waiting_tts = getattr(self._controller, "_is_waiting_for_tts", None)
        if callable(waiting_tts) and bool(waiting_tts()):
            return False
        return True

    def hide_suggestions(self) -> None:
        hide = getattr(self._controller, "hide_suggestions", None)
        if callable(hide):
            hide()
            return
        window = getattr(self._controller, "suggestion_window", None)
        if window is not None:
            try:
                window.hide_suggestions()
            except Exception:
                pass

    def show_suggestions(self, suggestions: List[str]) -> None:
        show = getattr(self._controller, "show_suggestions", None)
        if callable(show):
            show(suggestions)
            return
        window = getattr(self._controller, "suggestion_window", None)
        anchor = getattr(self._controller, "ball_anchor", None)
        if window is None:
            return
        try:
            window.show_suggestions(anchor, suggestions)
        except Exception:
            return

    def show_privacy_notice(self, text: str) -> None:
        show_notice = getattr(self._controller, "show_privacy_notice", None)
        if callable(show_notice):
            show_notice(text)
            return
        window = getattr(self._controller, "suggestion_window", None)
        anchor = getattr(self._controller, "ball_anchor", None)
        if window is None:
            return
        try:
            legacy = getattr(window, "show_privacy_notice", None)
            if callable(legacy):
                legacy(anchor, text)
        except Exception:
            return

    def reposition_suggestions(self) -> None:
        reposition = getattr(self._controller, "reposition_suggestions", None)
        if callable(reposition):
            reposition()
            return
        window = getattr(self._controller, "suggestion_window", None)
        if window is None:
            return
        try:
            window.reposition(getattr(self._controller, "ball_anchor", None))
        except Exception:
            pass

    def is_interaction_busy(self) -> bool:
        checker = getattr(self._controller, "is_interaction_busy", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                return False
        return False

    def enter_capture_mode(self) -> None:
        handler = getattr(self._controller, "enter_capture_mode", None)
        if callable(handler):
            handler()
            return
        try:
            managed = getattr(self._controller, "_managed_windows", None)
            if callable(managed):
                for w in managed():
                    if hasattr(w, "enter_transparent_mode"):
                        w.enter_transparent_mode()
        except Exception:
            pass

    def exit_capture_mode(self) -> None:
        handler = getattr(self._controller, "exit_capture_mode", None)
        if callable(handler):
            handler()
            return
        try:
            managed = getattr(self._controller, "_managed_windows", None)
            if callable(managed):
                for w in managed():
                    if hasattr(w, "exit_transparent_mode"):
                        w.exit_transparent_mode()
        except Exception:
            pass
