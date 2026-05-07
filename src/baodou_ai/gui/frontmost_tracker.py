"""
前台应用跟踪器。

用于在 GUI 常驻期间轻量记录最近一次可操作的外部前台应用，
供任务开始前恢复外部焦点使用。
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class FrontmostAppTracker:
    """轻量跟踪最近一次外部前台应用。"""

    def __init__(self, platform_adapter, own_pid: int):
        self._platform_adapter = platform_adapter
        self._own_pid = int(own_pid)
        self._last_external_frontmost_app: Optional[Dict[str, Any]] = None

    def observe_current_frontmost(self) -> Dict[str, Any]:
        """读取当前前台应用，并在其不是当前进程时刷新快照。"""
        app_info = self._normalize_app_info(self._platform_adapter.get_frontmost_app_info())
        if self._is_external_app(app_info):
            window_getter = getattr(self._platform_adapter, "get_frontmost_window_info", None)
            if callable(window_getter):
                try:
                    window_info = window_getter() or {}
                    hwnd = int(window_info.get("hwnd") or 0)
                    if hwnd > 0:
                        app_info["hwnd"] = hwnd
                except Exception:
                    pass
        if self._is_external_app(app_info):
            self._last_external_frontmost_app = dict(app_info)
        return app_info

    def snapshot_last_external_frontmost_app(self) -> Optional[Dict[str, Any]]:
        """获取最近一次外部前台应用快照。"""
        if not self._last_external_frontmost_app:
            return None
        return dict(self._last_external_frontmost_app)

    def _is_external_app(self, app_info: Dict[str, Any]) -> bool:
        if not app_info:
            return False
        try:
            pid = int(app_info.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid <= 0 or pid == self._own_pid:
            return False
        return bool(app_info.get("app_name") or app_info.get("bundle_id") or app_info.get("identifier"))

    @staticmethod
    def _normalize_app_info(app_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(app_info, dict):
            return {}
        normalized = {
            "app_name": str(app_info.get("app_name") or "").strip(),
            "bundle_id": str(app_info.get("bundle_id") or "").strip(),
            "identifier": str(app_info.get("identifier") or "").strip(),
            "pid": 0,
            "hwnd": 0,
        }
        try:
            normalized["pid"] = int(app_info.get("pid") or 0)
        except (TypeError, ValueError):
            normalized["pid"] = 0
        try:
            normalized["hwnd"] = int(app_info.get("hwnd") or 0)
        except (TypeError, ValueError):
            normalized["hwnd"] = 0
        return normalized
