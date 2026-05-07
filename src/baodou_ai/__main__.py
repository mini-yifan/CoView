"""
CoView 同窗 - 主入口文件

启动应用程序的悬浮球主界面。
"""

import faulthandler
import sys

faulthandler.enable()

_original_stderr = sys.stderr
_original_stdout = sys.stdout


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
