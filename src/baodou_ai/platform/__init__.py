"""平台适配模块。"""

import platform as platform_module
from typing import Any, Type

from baodou_ai.platform.base import PlatformAdapter, UnsupportedPlatformError
from baodou_ai.platform.mouse_motion import cancel_current_mouse_motion


def _get_adapter_class(current_os: str) -> Type[PlatformAdapter]:
    if current_os == "Windows":
        from baodou_ai.platform.windows import WindowsAdapter

        return WindowsAdapter
    if current_os == "Darwin":
        from baodou_ai.platform.macos import MacOSAdapter

        return MacOSAdapter
    raise UnsupportedPlatformError(f"Unsupported platform: {current_os}")


def get_platform_adapter() -> PlatformAdapter:
    """获取当前平台的适配器实例。"""
    current_os = platform_module.system()
    adapter_cls = _get_adapter_class(current_os)
    return adapter_cls()


def __getattr__(name: str) -> Any:
    if name == "WindowsAdapter":
        from baodou_ai.platform.windows import WindowsAdapter

        return WindowsAdapter
    if name == "MacOSAdapter":
        from baodou_ai.platform.macos import MacOSAdapter

        return MacOSAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "PlatformAdapter",
    "UnsupportedPlatformError",
    "WindowsAdapter",
    "MacOSAdapter",
    "get_platform_adapter",
    "cancel_current_mouse_motion",
]
