"""
AI 工作线程模块

提供 AIWorker 线程类，封装 ControlLoopRunner 的异步执行。
"""

import threading
import traceback
from typing import Any, Dict, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from baodou_ai.code_agent.manager import JobManager
from baodou_ai.core.config import Config
from baodou_ai.core.runner import ControlLoopRunner
from baodou_ai.platform import cancel_current_mouse_motion

FRIENDLY_API_ERROR_MESSAGE = "当前api链接出现异常，可能是网络不稳定"


class AIWorker(QThread):
    """AI工作线程"""

    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    stream_chunk = pyqtSignal(int, str)
    iteration_update = pyqtSignal(int, object)
    enter_transparent_mode = pyqtSignal(object)
    exit_transparent_mode = pyqtSignal(object)

    def __init__(
        self,
        user_content: str,
        config: Config,
        parent=None,
        initial_external_frontmost_app: Optional[Dict[str, Any]] = None,
        history_context: Optional[str] = None,
        on_report=None,
        job_manager: Optional[JobManager] = None,
        respond_language_override: str = "",
    ):
        super().__init__(parent)
        self.user_content = user_content
        self._config = config
        self._job_manager = job_manager
        self._should_exit = False
        self._initial_external_frontmost_app = dict(initial_external_frontmost_app or {})
        self.history_context = history_context
        self._on_report = on_report
        self._respond_language_override = str(respond_language_override or "").strip()

    def stop(self) -> None:
        """停止执行"""
        self._should_exit = True
        cancel_current_mouse_motion()

    def run(self) -> None:
        """运行AI控制逻辑"""
        try:
            user_content = ControlLoopRunner.build_user_content(self.user_content)
            print(f"=============用户输入内容为:{user_content}")

            if self._job_manager is None:
                runner = ControlLoopRunner(self._config)
            else:
                runner = ControlLoopRunner(self._config, job_manager=self._job_manager)
            result = runner.run(
                user_content=user_content,
                max_iterations=self._config.execution_config.get("default_max_iterations", 15),
                on_iteration=self._emit_iteration_update,
                on_model_stream=self._emit_stream_chunk,
                on_transparent_enter=self._enter_transparent_mode_callback,
                on_transparent_exit=self._exit_transparent_mode_callback,
                should_stop=lambda: self._should_exit,
                initial_external_frontmost_app=self._initial_external_frontmost_app,
                history_context=self.history_context,
                on_report=self._on_report,
                respond_language_override=self._respond_language_override,
            )
            self.finished.emit(result)
        except Exception as e:
            traceback.print_exc()
            self.error.emit(self._normalize_user_visible_error(e))

    def _enter_transparent_mode_callback(self) -> None:
        """进入透明穿透模式回调"""
        self._wait_for_window_transition(self.enter_transparent_mode)

    def _exit_transparent_mode_callback(self) -> None:
        """退出透明穿透模式回调"""
        self._wait_for_window_transition(self.exit_transparent_mode)

    @staticmethod
    def _wait_for_window_transition(signal: pyqtSignal) -> None:
        """等待主线程完成窗口状态切换，避免鼠标动作抢跑。"""
        completed = threading.Event()
        signal.emit(completed)
        completed.wait(timeout=1.0)

    def _emit_stream_chunk(self, iteration: int, chunk: str) -> None:
        """转发模型流式输出到主线程。"""
        self.stream_chunk.emit(iteration, chunk)

    def _emit_iteration_update(self, iteration: int, payload: dict) -> None:
        """转发结构化迭代信息到主线程。"""
        self.iteration_update.emit(iteration, payload)

    @staticmethod
    def _normalize_user_visible_error(exc: Exception) -> str:
        """将可识别的上游 API 异常转换为友好提示，避免 traceback 直接上屏。"""
        combined = " ".join(
            part for part in (exc.__class__.__module__, exc.__class__.__name__, str(exc)) if part
        ).lower()
        api_error_markers = (
            "openai",
            "apierror",
            "apiconnectionerror",
            "apitimeouterror",
            "internalerror.algo",
            "datainspectionfailed",
        )
        if any(marker in combined for marker in api_error_markers):
            return FRIENDLY_API_ERROR_MESSAGE
        return traceback.format_exc()
