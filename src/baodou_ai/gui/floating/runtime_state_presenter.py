"""Runtime state presenter for floating panel and console."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from baodou_ai.gui.control_console import ControlConsoleWindow
    from baodou_ai.gui.floating.controller import FloatingController
    from baodou_ai.gui.floating.task_session_state import UITaskSessionState


class RuntimeStatePresenter:
    """统一将状态同步到 panel/console/ball。"""

    def __init__(self, owner: "FloatingController", state: "UITaskSessionState") -> None:
        self._owner = owner
        self._state = state

    def apply_runtime_state(self, status_key: str, status_text: str) -> None:
        self._state.status_key = status_key
        self._state.status_text = status_text
        self._sync_console()
        self._sync_ball_animation()

    def sync_console_window(self, console_window: "ControlConsoleWindow") -> None:
        console_window.update_runtime_state(
            status_key=self._state.status_key,
            status_text=self._state.status_text,
            iteration=self._state.iteration,
            max_iterations=self._state.max_iterations,
            token_total=self._state.token_total,
        )

    def _sync_console(self) -> None:
        console_window = getattr(self._owner, "_console_window", None)
        if console_window is not None:
            self.sync_console_window(console_window)

    def _sync_ball_animation(self) -> None:
        ball_window = getattr(self._owner, "ball_window", None)
        if ball_window is not None and hasattr(ball_window, "sync_animation_state"):
            ball_window.sync_animation_state()
