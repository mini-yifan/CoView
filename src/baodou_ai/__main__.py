"""
CoView 同窗 - 主入口文件

启动应用程序的悬浮球主界面。
"""

import faulthandler
import os
import sys
import tempfile
from pathlib import Path
from typing import TextIO


def _resolve_diagnostic_stream() -> TextIO:
    """在 windowed 打包环境中为 stderr 缺失提供可写诊断流。"""
    for candidate in (sys.stderr, sys.__stderr__):
        if candidate is not None:
            return candidate

    log_dir = Path(tempfile.gettempdir()) / "CoView"
    log_dir.mkdir(parents=True, exist_ok=True)
    return (log_dir / "startup-error.log").open("a", encoding="utf-8")


_diagnostic_stream = _resolve_diagnostic_stream()
_original_stderr = _diagnostic_stream
_original_stdout = sys.stdout if sys.stdout is not None else sys.__stdout__

if sys.stderr is None:
    sys.stderr = _diagnostic_stream
if sys.stdout is None and _original_stdout is not None:
    sys.stdout = _original_stdout

try:
    faulthandler.enable(file=_diagnostic_stream)
except Exception:
    pass


def _crash_excepthook(exc_type, exc_value, exc_tb):
    import traceback
    traceback.print_exception(exc_type, exc_value, exc_tb, file=_original_stderr)
    _original_stderr.flush()


sys.excepthook = _crash_excepthook

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont

from baodou_ai.code_agent.session_files import clear_session_root as clear_code_agent_session_root
from baodou_ai.core.config import Config
from baodou_ai.gui.floating.controller import FloatingController
from baodou_ai.gui.floating.windows_taskbar_host import resolve_windows_app_icon
from baodou_ai.gui.runtime_log import init_runtime_log_buffer


def main():
    clear_code_agent_session_root()

    if hasattr(QApplication, "setAttribute"):
        from PyQt5.QtCore import Qt

        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, "AA_UseHighDpiPixmaps"):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("CoView")
    app.setApplicationDisplayName("CoView")
    if sys.platform.startswith("win"):
        icon = resolve_windows_app_icon()
        if not icon.isNull():
            app.setWindowIcon(icon)
    app.setFont(QFont("PingFang SC", 11))

    config = Config()
    log_buffer = init_runtime_log_buffer()
    controller = FloatingController(app, config=config, log_buffer=log_buffer)
    controller.start()

    try:
        sys.exit(app.exec_())
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc(file=_original_stderr)
        _original_stderr.flush()
        raise


if __name__ == "__main__":
    main()
