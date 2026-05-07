"""Native Win32 helpers for floating overlay windows."""

from __future__ import annotations

from typing import Optional


GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020


class WindowsOverlayHelper:
    """Encapsulates Win32 calls needed by floating overlay windows."""

    def __init__(self, user32, gdi32=None):
        self._user32 = user32
        self._gdi32 = gdi32

    @staticmethod
    def _normalized_opacity(opacity: Optional[float], default: float = 0.9) -> float:
        if opacity is None:
            return max(0.0, min(1.0, float(default)))
        return max(0.0, min(1.0, float(opacity)))

    def hwnd(self, window) -> int:
        return window.winId().__int__()

    def remember_opacity(self, window, opacity: Optional[float]) -> float:
        normalized = self._normalized_opacity(opacity)
        setattr(window, "_windows_overlay_restore_opacity", normalized)
        return normalized

    def restore_opacity(self, window, default: float = 0.9) -> float:
        stored = getattr(window, "_windows_overlay_restore_opacity", None)
        return self._normalized_opacity(stored, default=default)

    def _refresh_frame(self, hwnd: int) -> None:
        if hasattr(self._user32, "SetWindowPos"):
            self._user32.SetWindowPos(
                hwnd,
                0,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )

    def ensure_overlay_window(self, window, opacity: Optional[float] = None) -> int:
        hwnd = self.hwnd(window)
        current_style = self._user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        new_style = current_style | WS_EX_TOOLWINDOW
        if new_style != current_style:
            self._user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            self._refresh_frame(hwnd)
        if opacity is not None and opacity > 0:
            self.remember_opacity(window, opacity)
        return hwnd

    def set_opacity(self, window, opacity: Optional[float]) -> float:
        if opacity is None:
            normalized = self.restore_opacity(window)
        else:
            normalized = self._normalized_opacity(opacity)
            if normalized > 0:
                self.remember_opacity(window, normalized)
        return normalized

    def set_click_through(self, window, enabled: bool, opacity: Optional[float] = None) -> None:
        hwnd = self.ensure_overlay_window(window, opacity=opacity)
        current_style = self._user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if enabled:
            new_style = current_style | WS_EX_TRANSPARENT
        else:
            new_style = current_style & ~WS_EX_TRANSPARENT
        if new_style != current_style:
            self._user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            self._refresh_frame(hwnd)

    def clear_region(self, window) -> bool:
        return False

    def apply_ellipse_region(self, window, inset: int = 0) -> bool:
        return False

    def apply_round_rect_region(self, window, radius: int) -> bool:
        return False
