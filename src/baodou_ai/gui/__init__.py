"""GUI 模块懒加载导出，避免顶层循环依赖。"""

__all__ = [
    "AIWorker",
    "ControlConsoleWindow",
    "FloatingController",
    "LogWindow",
    "RuntimeLogBuffer",
    "init_runtime_log_buffer",
    "get_runtime_log_buffer",
    "Styles",
]


def __getattr__(name):
    if name == "AIWorker":
        from baodou_ai.gui.main_window import AIWorker

        return AIWorker
    if name == "ControlConsoleWindow":
        from baodou_ai.gui.control_console import ControlConsoleWindow

        return ControlConsoleWindow
    if name == "FloatingController":
        from baodou_ai.gui.floating.controller import FloatingController

        return FloatingController
    if name == "LogWindow":
        from baodou_ai.gui.log_window import LogWindow

        return LogWindow
    if name in {"RuntimeLogBuffer", "get_runtime_log_buffer", "init_runtime_log_buffer"}:
        from baodou_ai.gui.runtime_log import (
            RuntimeLogBuffer,
            get_runtime_log_buffer,
            init_runtime_log_buffer,
        )

        return {
            "RuntimeLogBuffer": RuntimeLogBuffer,
            "get_runtime_log_buffer": get_runtime_log_buffer,
            "init_runtime_log_buffer": init_runtime_log_buffer,
        }[name]
    if name == "Styles":
        from baodou_ai.gui.styles import Styles

        return Styles
    raise AttributeError(name)
