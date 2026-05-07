"""Shared mouse motion coordination."""

from __future__ import annotations

import threading
from dataclasses import dataclass


class MouseMotionCancelled(RuntimeError):
    """Raised when an in-flight mouse motion is superseded or cancelled."""


@dataclass(frozen=True)
class MouseMotionToken:
    """Cancellation token for one mouse motion."""

    generation: int


class MouseMotionCoordinator:
    """Process-wide coordinator for foreground mouse motion."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._generation = 0
        self._active_generation: int | None = None

    def begin_motion(self) -> MouseMotionToken:
        """Cancel previous motion and reserve the motion lane for a new one."""
        with self._condition:
            self._generation += 1
            generation = self._generation
            self._active_generation = generation
            self._condition.notify_all()
            return MouseMotionToken(generation=generation)

    def end_motion(self, token: MouseMotionToken) -> None:
        """Release the motion lane if it is still owned by token."""
        with self._condition:
            if self._active_generation == token.generation:
                self._active_generation = None
            self._condition.notify_all()

    def cancel_current(self) -> None:
        """Cancel the current motion, if any."""
        with self._condition:
            self._generation += 1
            self._active_generation = None
            self._condition.notify_all()

    def check_active(self, token: MouseMotionToken) -> None:
        """Raise if token no longer represents the active motion."""
        with self._condition:
            if self._active_generation != token.generation or self._generation != token.generation:
                raise MouseMotionCancelled("Mouse motion was cancelled")

    def wait_active(self, token: MouseMotionToken, timeout: float) -> None:
        """Sleep interruptibly while token remains active."""
        if timeout <= 0:
            self.check_active(token)
            return
        with self._condition:
            if self._active_generation != token.generation or self._generation != token.generation:
                raise MouseMotionCancelled("Mouse motion was cancelled")
            self._condition.wait(timeout=timeout)
            if self._active_generation != token.generation or self._generation != token.generation:
                raise MouseMotionCancelled("Mouse motion was cancelled")


_COORDINATOR = MouseMotionCoordinator()


def get_mouse_motion_coordinator() -> MouseMotionCoordinator:
    return _COORDINATOR


def cancel_current_mouse_motion() -> None:
    _COORDINATOR.cancel_current()
