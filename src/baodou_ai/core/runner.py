"""
统一控制循环 Runner。

负责串联正式截图、模型决策、动作执行、稳定检测和停滞保护，
供 API 与 GUI 两条入口共同使用。
"""

import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import cv2
import numpy as np

from baodou_ai.agent.protocol import get_agent_response_branch
from baodou_ai.agent.tool_executor import ToolExecutor
from baodou_ai.agent.tool_registry import comparable_tool_args, extract_tool_points
from baodou_ai.ai.client import AIClient
from baodou_ai.ai.parser import ResponseParser
from baodou_ai.code_agent.manager import JobManager
from baodou_ai.core.automation import (
    AutomationController,
    DOCUMENT_EXTRACT_DIR,
    DOCUMENT_ANCHOR_DIR,
    MEMORY_FILE,
    PAGE_EXTRACT_DIR,
)
from baodou_ai.core.config import Config
from baodou_ai.core.context_window import ContextWindowManager
from baodou_ai.core.error_envelope import CODE_MODEL_API_KEY_MISSING
from baodou_ai.core.observation import ObservationService
from baodou_ai.core.process_report_policy import ProcessReportPolicy
from baodou_ai.core.runtime_artifact_store import RuntimeArtifactStore
from baodou_ai.core.runner_state import RunnerLoopState
from baodou_ai.core.runner_events import (
    build_invalid_model_output_feedback,
    build_iteration_payload,
)
from baodou_ai.core.runner_metrics import (
    apply_model_metrics_to_state,
    build_iteration_token_log,
    build_task_token_summary,
    coerce_optional_int,
    did_model_request_execute,
)
from baodou_ai.core.runner_turns import (
    BranchExecutionContext,
    RunnerBranchExecutor,
)
from baodou_ai.core.screenshot import ScreenCaptureBundle, ScreenshotCapture
from baodou_ai.core.stall_policy import StallPolicy
from baodou_ai.core.task_memory_store import TaskMemoryStore
from baodou_ai.core.tool_feedback import (
    append_remember_feedback,
    build_document_extraction_notice,
    build_page_extraction_notice,
    is_copy_or_paste_hotkey,
)


class ControlLoopRunner:
    """统一的纯视觉控制循环执行器"""

    _REPORT_REQUEST_PROMPT = "A brief process report is required for this turn."
    _AUTO_SKIP_REPORT_PROMPT = (
        "By default, do not output a report for this turn. There is no obvious anomaly, no significant progress, "
        "and no important information that must be immediately communicated to a user who is not looking at the screen; "
        "unless you have indeed discovered new circumstances that are clearly important to a user who cannot see the screen, omit the report field."
    )
    _OFF_SKIP_REPORT_PROMPT = (
        "Process reporting is currently disabled. Do not output a process report except for the final respond.report; "
        "only provide a process report when the system explicitly requests one for this turn."
    )
    _LOOP_REPORT_REQUEST_PROMPT = (
        "It appears you may be repeating similar operations. Please provide a brief report for this turn, "
        "explaining what you are currently doing and why you are still trying; "
        "if the reason is uncertain, do not pretend to be certain."
    )
    _FOCUS_FALLBACK_PROMPT = (
        "The current keyboard focus is not on an operable external application. "
        "If the next step depends on focus, click the target window or input area first to gain focus."
    )
    _PAGE_EXTRACTION_FAILURE_NOTICE = (
        "The current webpage extraction failed; the previous webpage extraction content has been invalidated and cleared. "
        "Do not rely on read_current_page results to judge the current webpage content; "
        "you must extract information strictly by analyzing the screenshot."
    )
    _PAGE_EXTRACTION_NEED_EXTRACT_FIRST_NOTICE = (
        "There is no full webpage text available for chunked reading for the current task. "
        "If you need to continue reading the webpage, call read_current_page(mode=\"extract\") first."
    )
    _PAGE_EXTRACTION_SEARCH_NO_RESULTS_NOTICE = (
        "The current webpage search found no relevant results; the previous webpage extraction content has been invalidated and cleared. "
        "Try different keywords, shorter query terms, or use read_current_page(mode=\"chunk\") / "
        "read_current_page(mode=\"next\") to continue reading the full text."
    )
    _PAGE_EXTRACTION_NO_MORE_CHUNKS_NOTICE = (
        "You have reached the end of the webpage; there are no more chunks. "
        "Do not continue calling read_current_page(mode=\"next\"); "
        "if you still need to reference the current chunk, proceed based on the existing webpage context."
    )
    _DOCUMENT_EXTRACTION_FOCUS_RETRY_NOTICE = (
        "The current document extraction failed; the previous document extraction content has been invalidated and cleared. "
        "The result appears to come from a toolbar, font size bar, style bar, or other non-body area. "
        "If you still need to extract the current document, observe the screenshot first and provide the body area coordinates "
        "in the next read_current_document call; "
        "do not call again without coordinates."
    )
    _DOCUMENT_EXTRACTION_IDE_POSITION_NOTICE = (
        "The current document extraction failed; the previous document extraction content has been invalidated and cleared. "
        "The current frontmost app is a programming IDE / editor. When calling read_current_document you must provide "
        "screen_index and position; click the code or text body area first; "
        "no extraction operation was performed this time."
    )
    _DOCUMENT_EXTRACTION_FAILURE_NOTICE = (
        "The current document extraction failed; the previous document extraction content has been invalidated and cleared. "
        "Do not rely on read_current_document results to judge the current document content; "
        "you must extract information strictly by analyzing the screenshot."
    )
    _DOCUMENT_EXTRACTION_UNSUPPORTED_NOTICE = (
        "The current frontmost app or platform does not support read_current_document; the previous document extraction content has been invalidated and cleared. "
        "This tool should only be used when Microsoft Word, Microsoft Excel, TextEdit, Preview, WPS, "
        "as well as Visual Studio Code, Cursor, Windsurf, IntelliJ IDEA, PyCharm, WebStorm, GoLand, CLion, "
        "Android Studio, Sublime Text, Xcode, TRAE, TRAE CN, TRAE SOLO CN is in the foreground on a supported platform."
    )
    _DOCUMENT_EXTRACTION_NEED_EXTRACT_FIRST_NOTICE = (
        "There is no full document text available for chunked reading for the current task. "
        "If you need to continue reading the document, call read_current_document(mode=\"extract\") first."
    )
    _DOCUMENT_EXTRACTION_SEARCH_NO_RESULTS_NOTICE = (
        "The current document search found no relevant results; the previous document extraction content has been invalidated and cleared. "
        "Try different keywords, shorter query terms, or use read_current_document(mode=\"chunk\") / "
        "read_current_document(mode=\"next\") to continue reading the full text."
    )
    _DOCUMENT_EXTRACTION_NO_MORE_CHUNKS_NOTICE = (
        "You have reached the end of the document; there are no more chunks. "
        "Do not continue calling read_current_document(mode=\"next\"); "
        "if you still need to reference the current chunk, proceed based on the existing document context."
    )

    @staticmethod
    def build_user_content(task: str, now: Optional[float] = None, history_context: Optional[str] = None) -> str:
        """统一构造传给模型的用户输入。"""
        if now is None:
            current_time = time.localtime()
        else:
            current_time = time.localtime(now)
        time_str = time.strftime("%Y-%m-%d %H:%M", current_time)
        parts = [f"Current time: {time_str}"]
        if history_context:
            parts.append(history_context)
        parts.append(f"User task: {task}")
        return "\n".join(parts)

    def __init__(self, config: Optional[Config] = None, job_manager: Optional[JobManager] = None) -> None:
        self._config = config or Config()
        self._screenshot = ScreenshotCapture(self._config)
        self._automation = AutomationController(self._config)
        self._job_manager = job_manager or JobManager(self._config)
        self._automation.set_job_manager(self._job_manager)
        self._tool_executor = ToolExecutor(self._automation)
        self._ai_client = AIClient(self._config)
        self._task_memory_store = TaskMemoryStore(memory_file_resolver=lambda: MEMORY_FILE)
        self._runtime_artifact_store = RuntimeArtifactStore(
            page_extract_dir_resolver=lambda: PAGE_EXTRACT_DIR,
            document_extract_dir_resolver=lambda: DOCUMENT_EXTRACT_DIR,
            document_anchor_dir_resolver=lambda: DOCUMENT_ANCHOR_DIR,
        )
        set_artifact_store = getattr(self._ai_client, "set_runtime_artifact_store", None)
        if callable(set_artifact_store):
            set_artifact_store(self._runtime_artifact_store)
        self._parser = ResponseParser()
        self._memory_content_cache: Optional[str] = None
        self._stall_policy = StallPolicy(
            action_signature_tolerance_px=self._config.execution_config.get("action_signature_tolerance_px", 15)
        )
        self._process_report_policy = ProcessReportPolicy(
            config=self._config,
            stall_policy=self._stall_policy,
            report_request_prompt=self._REPORT_REQUEST_PROMPT,
            auto_skip_report_prompt=self._AUTO_SKIP_REPORT_PROMPT,
            off_skip_report_prompt=self._OFF_SKIP_REPORT_PROMPT,
            loop_report_request_prompt=self._LOOP_REPORT_REQUEST_PROMPT,
        )
        self._observation = ObservationService(
            screenshot=self._screenshot,
            automation=self._automation,
            focus_fallback_prompt=self._FOCUS_FALLBACK_PROMPT,
        )
        self._branch_executor = RunnerBranchExecutor(self)
        self._gray_frame_cache: Dict[str, np.ndarray] = {}

    def _reset_runtime_caches(self) -> None:
        """重置单次任务级缓存。"""
        self._memory_content_cache = None
        self._observation.clear_frame_cache()
        self._gray_frame_cache = {}

    def _get_memory_content(self) -> str:
        """读取 remember 内容，并在单次任务内复用缓存。"""
        if self._memory_content_cache is None:
            self._memory_content_cache = self._read_memory_content()
        return self._memory_content_cache

    def _append_memory_content_cache(self, remember_content: str) -> None:
        """将 remember 成功写入的内容同步到运行态缓存。"""
        normalized = str(remember_content or "").strip()
        if not normalized:
            return

        current = self._get_memory_content()
        if not current:
            self._memory_content_cache = normalized
            return

        self._memory_content_cache = f"{current}\n{normalized}"

    @staticmethod
    def _coerce_optional_int(value: Any) -> Optional[int]:
        return coerce_optional_int(value)

    @classmethod
    def _did_model_request_execute(cls, ai_metrics: Dict[str, Any]) -> bool:
        return did_model_request_execute(ai_metrics)

    @classmethod
    def _build_iteration_token_log(
        cls,
        iteration_index: int,
        ai_metrics: Dict[str, Any],
    ) -> str:
        return build_iteration_token_log(iteration_index, ai_metrics)

    @classmethod
    def _build_task_token_summary(
        cls,
        model_request_count: int,
        any_token_usage_available: bool,
        task_token_usage_complete: bool,
        task_prompt_tokens: int,
        task_completion_tokens: int,
        task_total_tokens: int,
    ) -> str:
        return build_task_token_summary(
            model_request_count=model_request_count,
            any_token_usage_available=any_token_usage_available,
            task_token_usage_complete=task_token_usage_complete,
            task_prompt_tokens=task_prompt_tokens,
            task_completion_tokens=task_completion_tokens,
            task_total_tokens=task_total_tokens,
        )

    def _get_bundle_gray(self, bundle: ScreenCaptureBundle) -> Optional[np.ndarray]:
        """获取 bundle 的灰度图缓存，避免重复解码 PNG。"""
        cached = self._gray_frame_cache.get(bundle.frame_hash)
        if cached is not None:
            return cached

        gray = cv2.imdecode(
            np.frombuffer(bundle.png_bytes, dtype=np.uint8),
            cv2.IMREAD_GRAYSCALE,
        )
        if gray is not None:
            self._gray_frame_cache[bundle.frame_hash] = gray
        return gray

    def _retain_gray_frame_cache(self, bundles: List[ScreenCaptureBundle]) -> None:
        """仅保留最近两轮相关的灰度图缓存。"""
        keep_hashes = {bundle.frame_hash for bundle in bundles}
        self._gray_frame_cache = {
            frame_hash: gray
            for frame_hash, gray in self._gray_frame_cache.items()
            if frame_hash in keep_hashes
        }

    @staticmethod
    def _capture_with_hidden_windows(
        screenshot: ScreenshotCapture,
        on_transparent_enter: Optional[Callable[[], Any]] = None,
        on_transparent_exit: Optional[Callable[[], Any]] = None,
    ) -> tuple:
        """截图前先隐藏 GUI 窗口，避免窗口出现在截图或变成黑块。"""
        return ObservationService.capture_with_hidden_windows(
            screenshot=screenshot,
            on_transparent_enter=on_transparent_enter,
            on_transparent_exit=on_transparent_exit,
        )

    @staticmethod
    def _sleep_interruptibly(
        delay_ms: float,
        should_stop: Callable[[], bool],
        step_ms: float = 20.0,
    ) -> bool:
        """支持中断的短步进等待。"""
        if delay_ms <= 0:
            return True

        deadline = time.perf_counter() + (delay_ms / 1000.0)
        while True:
            if should_stop():
                return False

            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return True

            sleep_seconds = min(remaining, step_ms / 1000.0)
            time.sleep(max(sleep_seconds, 0.0))

    def _wait_before_next_capture(self, should_stop: Callable[[], bool]) -> bool:
        """在工具执行结束后，为下一轮正式截图留出额外缓冲。"""
        delay_ms = float(self._config.execution_config.get("post_tool_capture_delay_ms", 0) or 0)
        if delay_ms <= 0:
            return True

        print(f"工具后截图缓冲: {delay_ms:.0f}ms")
        return self._sleep_interruptibly(delay_ms=delay_ms, should_stop=should_stop)

    def _get_minimum_tool_interval_ms(self) -> float:
        """获取连续桌面工具启动之间的最小间隔，快模型下用于给系统 UI 留出余量。"""
        try:
            interval_ms = float(self._config.execution_config.get("minimum_tool_interval_ms", 0) or 0)
        except (TypeError, ValueError):
            interval_ms = 0.0
        return max(interval_ms, 0.0)

    def _wait_for_tool_pacing(
        self,
        last_tool_started_at: Optional[float],
        should_stop: Callable[[], bool],
    ) -> bool:
        """当模型返回过快时，避免连续桌面工具过密导致鼠标和窗口动画卡顿。"""
        if last_tool_started_at is None:
            return True

        interval_ms = self._get_minimum_tool_interval_ms()
        if interval_ms <= 0:
            return True

        elapsed_ms = (time.perf_counter() - last_tool_started_at) * 1000.0
        remaining_ms = interval_ms - elapsed_ms
        if remaining_ms <= 0:
            return True

        print(f"工具节拍缓冲: {remaining_ms:.0f}ms")
        return self._sleep_interruptibly(delay_ms=remaining_ms, should_stop=should_stop)

    def _normalize_report_mode(self) -> str:
        return self._process_report_policy.normalize_report_mode()

    def _get_report_interval_steps(self) -> int:
        return self._process_report_policy.get_report_interval_steps()

    def _get_held_modifier_auto_release_steps(self) -> int:
        try:
            steps = int(self._config.execution_config.get("held_modifier_auto_release_steps", 5))
        except (TypeError, ValueError):
            steps = 5
        return max(steps, 1)

    def _get_held_modifier_auto_release_seconds(self) -> float:
        try:
            seconds = float(self._config.execution_config.get("held_modifier_auto_release_seconds", 10))
        except (TypeError, ValueError):
            seconds = 10.0
        return max(seconds, 0.1)

    @staticmethod
    def _build_held_modifier_prompt(
        held_keys: List[str],
        auto_release_notice: str = "",
    ) -> str:
        parts: List[str] = []
        if auto_release_notice:
            parts.append(auto_release_notice.strip())
        if held_keys:
            parts.append(f"Currently held modifier keys: {', '.join(held_keys)}.")
            parts.append("If held modifiers are no longer needed for the next step, prioritize calling release_modifier_keys.")
        else:
            parts.append("No modifier keys are currently held.")
        return "\n".join(part for part in parts if part)

    @staticmethod
    def _normalize_frontmost_app_info(app_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return ObservationService.normalize_frontmost_app_info(app_info)

    def _is_external_frontmost_app(
        self,
        app_info: Optional[Dict[str, Any]],
        agent_process_pid: int,
    ) -> bool:
        return self._observation.is_external_frontmost_app(
            app_info=app_info,
            agent_process_pid=agent_process_pid,
        )

    def _prepare_external_frontmost_app_before_capture(
        self,
        last_external_frontmost_app: Optional[Dict[str, Any]],
        agent_process_pid: int,
        should_stop: Callable[[], bool],
    ) -> Optional[Dict[str, Any]]:
        return self._observation.prepare_external_frontmost_app_before_capture(
            last_external_frontmost_app=last_external_frontmost_app,
            agent_process_pid=agent_process_pid,
            should_stop=should_stop,
            sleep_interruptibly=self._sleep_interruptibly,
        )

    def _build_frontmost_app_prompt(
        self,
        frontmost_app_info: Optional[Dict[str, Any]],
        agent_process_pid: int,
    ) -> str:
        return self._observation.build_frontmost_app_prompt(
            frontmost_app_info=frontmost_app_info,
            agent_process_pid=agent_process_pid,
        )

    def _build_process_report_request(
        self,
        report_mode: str,
        step_index: int,
        last_process_report_step: int,
        pending_required_report: bool,
        current_screen_hash: str,
        recent_effective_history: List[Dict[str, Any]],
    ) -> tuple:
        return self._process_report_policy.build_process_report_request(
            report_mode=report_mode,
            step_index=step_index,
            last_process_report_step=last_process_report_step,
            pending_required_report=pending_required_report,
            current_screen_hash=current_screen_hash,
            recent_effective_history=recent_effective_history,
        )

    def _is_loop_report_required(
        self,
        current_screen_hash: str,
        recent_effective_history: List[Dict[str, Any]],
    ) -> bool:
        return self._stall_policy.is_loop_report_required(
            current_screen_hash=current_screen_hash,
            recent_effective_history=recent_effective_history,
        )

    def _has_repeated_same_action_loop(
        self,
        current_screen_hash: str,
        recent_effective_history: List[Dict[str, Any]],
    ) -> bool:
        return self._stall_policy.has_repeated_same_action_loop(
            current_screen_hash=current_screen_hash,
            recent_effective_history=recent_effective_history,
        )

    def _has_back_and_forth_loop(
        self,
        current_screen_hash: str,
        recent_effective_history: List[Dict[str, Any]],
    ) -> bool:
        return self._stall_policy.has_back_and_forth_loop(
            current_screen_hash=current_screen_hash,
            recent_effective_history=recent_effective_history,
        )

    @staticmethod
    def _wait_for_tts(tts_event: Optional[threading.Event], should_stop: Callable[[], bool]) -> None:
        if tts_event is None:
            return
        while not tts_event.wait(timeout=0.1):
            if should_stop():
                break

    def run(
        self,
        user_content: str,
        max_iterations: Optional[int] = None,
        on_iteration: Optional[Callable[[int, Dict[str, Any]], Any]] = None,
        on_model_stream: Optional[Callable[[int, str], Any]] = None,
        on_transparent_enter: Optional[Callable[[], Any]] = None,
        on_transparent_exit: Optional[Callable[[], Any]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        initial_external_frontmost_app: Optional[Dict[str, Any]] = None,
        agent_process_pid: Optional[int] = None,
        history_context: Optional[str] = None,
        on_report: Optional[Callable[[str], Optional[threading.Event]]] = None,
        respond_language_override: str = "",
    ) -> str:
        """执行统一控制循环"""
        should_stop = should_stop or (lambda: False)
        if history_context:
            user_content = user_content.replace("\nUser task:", f"\n{history_context}\nUser task:")
        if on_transparent_enter or on_transparent_exit:
            self._automation.set_window_callbacks(
                on_transparent_enter or (lambda: None),
                on_transparent_exit or (lambda: None),
            )
        self._tool_executor = ToolExecutor(self._automation)
        self._observation = ObservationService(
            screenshot=self._screenshot,
            automation=self._automation,
            focus_fallback_prompt=self._FOCUS_FALLBACK_PROMPT,
        )

        self._ai_client.clear_memory()
        self._runtime_artifact_store.clear_context_debug()
        print("已清空 AI 记忆")

        if max_iterations is None:
            max_iterations = self._config.execution_config.get("default_max_iterations", 15)
        if agent_process_pid is None:
            agent_process_pid = os.getpid()

        state = RunnerLoopState()
        total_loop_time = 0.0
        report_mode = self._process_report_policy.normalize_report_mode()
        state.last_external_frontmost_app = self._observation.normalize_frontmost_app_info(initial_external_frontmost_app)
        context_window = ContextWindowManager()

        try:
            self._reset_runtime_caches()
            for i in range(max_iterations):
                if should_stop():
                    print("检测到退出标记，停止循环...")
                    return "Task interrupted by user"

                print(f"\n=================第 {i} 次循环==============")
                if i == 0:
                    self._clear_extract_files()
                    reset_page_extract_sequence = getattr(self._automation, "reset_page_extract_sequence", None)
                    if callable(reset_page_extract_sequence):
                        reset_page_extract_sequence()
                    reset_document_extract_sequence = getattr(self._automation, "reset_document_extract_sequence", None)
                    if callable(reset_document_extract_sequence):
                        reset_document_extract_sequence()
                    context_window.reset()
                    self._memory_content_cache = None
                    self._observation.clear_frame_cache()
                    self._gray_frame_cache = {}

                if context_window.reader_cleanup_pending:
                    print("[Context Warning] Token usage reached 80% threshold, clearing page/document context.")
                    context_window.apply_pending_cleanup(self._automation)

                loop_start = time.perf_counter()
                memory_content = self._get_memory_content()
                if memory_content:
                    print(f"当前记忆内容: {memory_content[:200]}...")

                auto_release_notice = self._automation.auto_release_stale_modifier_keys(
                    current_step=state.step_index,
                    max_steps=self._get_held_modifier_auto_release_steps(),
                    max_seconds=self._get_held_modifier_auto_release_seconds(),
                )
                if auto_release_notice:
                    state.held_modifier_notice = auto_release_notice
                held_modifier_prompt = self._build_held_modifier_prompt(
                    held_keys=self._automation.get_held_modifier_keys(),
                    auto_release_notice=state.held_modifier_notice,
                )
                state.held_modifier_notice = ""

                prepared_frontmost = self._prepare_external_frontmost_app_before_capture(
                    last_external_frontmost_app=state.last_external_frontmost_app,
                    agent_process_pid=agent_process_pid,
                    should_stop=should_stop,
                )
                if self._is_external_frontmost_app(prepared_frontmost, agent_process_pid):
                    state.last_external_frontmost_app = self._normalize_frontmost_app_info(prepared_frontmost)
                else:
                    state.last_external_frontmost_app = {}

                capture_start = time.perf_counter()
                success, bundles = self._capture_with_hidden_windows(
                    screenshot=self._screenshot,
                    on_transparent_enter=on_transparent_enter,
                    on_transparent_exit=on_transparent_exit,
                )
                capture_ms = (time.perf_counter() - capture_start) * 1000.0
                if not success or not bundles:
                    print("屏幕截图失败")
                    get_capture_error = getattr(self._screenshot, "get_last_capture_error_envelope", None)
                    if callable(get_capture_error):
                        capture_error_envelope = get_capture_error() or {}
                        if capture_error_envelope:
                            print(f"[ERROR_ENVELOPE] {capture_error_envelope}")
                    total_loop_time += time.perf_counter() - loop_start
                    continue

                current_frontmost = self._normalize_frontmost_app_info(
                    self._automation.get_frontmost_app_info()
                )
                if self._is_external_frontmost_app(current_frontmost, agent_process_pid):
                    state.last_external_frontmost_app = current_frontmost
                frontmost_app_prompt = self._build_frontmost_app_prompt(
                    current_frontmost,
                    agent_process_pid=agent_process_pid,
                )
                print(f"[Frontmost App]\n{frontmost_app_prompt}")

                screen_info = self._build_screen_info(bundles)
                screen_group_hash = self._build_screen_group_hash(bundles)
                changed_pixels_ratio = self._calculate_changed_pixels_ratio(state.last_bundles, bundles)
                background_jobs_prompt = self._build_background_jobs_prompt()
                pending_reports_prompt = self._build_pending_reports_prompt()
                (
                    process_report_request_prompt,
                    report_requested,
                    report_request_reason,
                    loop_report_requested,
                ) = self._build_process_report_request(
                    report_mode=report_mode,
                    step_index=state.step_index,
                    last_process_report_step=state.last_process_report_step,
                    pending_required_report=state.pending_required_report,
                    current_screen_hash=screen_group_hash,
                    recent_effective_history=state.recent_effective_history,
                )

                stream_callback = None
                if on_model_stream is not None:
                    def stream_callback(chunk: str, iteration_index: int = i) -> None:
                        on_model_stream(iteration_index, chunk)

                ai_result, ai_metrics = self._ai_client.get_next_action_from_capture(
                    captures=bundles,
                    user_content=user_content if i == 0 else "",
                    should_exit_check=should_stop,
                    action_feedback=state.last_tool_feedback,
                    screen_info=screen_info,
                    memory_content=memory_content,
                    page_context=context_window.ephemeral_page_context,
                    page_extraction_notice=context_window.page_extraction_notice,
                    document_context=context_window.ephemeral_document_context,
                    document_extraction_notice=context_window.document_extraction_notice,
                    context_warning_prompt=context_window.context_warning_prompt,
                    replan_feedback=state.replan_feedback,
                    process_report_mode=report_mode,
                    process_report_request_prompt=process_report_request_prompt,
                    held_modifier_prompt=held_modifier_prompt,
                    frontmost_app_prompt=frontmost_app_prompt,
                    background_jobs_prompt=background_jobs_prompt,
                    pending_reports_prompt=pending_reports_prompt,
                    on_stream_chunk=stream_callback,
                    respond_language_override=respond_language_override,
                )
                state.replan_feedback = ""
                context_window.context_warning_prompt = ""

                if self._did_model_request_execute(ai_metrics):
                    metrics_update = apply_model_metrics_to_state(state, ai_metrics)
                    ai_metrics = metrics_update.metrics
                    print(self._build_iteration_token_log(i, ai_metrics))

                    context_token_limit = self._config.get("execution_config.context_token_limit", 120000)
                    if context_window.maybe_schedule_cleanup_on_tokens(
                        round_prompt_tokens=metrics_update.prompt_tokens,
                        context_token_limit=context_token_limit,
                    ):
                        print(f"[Context Warning] prompt_tokens={metrics_update.prompt_tokens}, limit={context_token_limit}, "
                              f"ratio={metrics_update.prompt_tokens / context_token_limit:.1%}")

                if should_stop():
                    return "Task interrupted by user"

                if not ai_result:
                    parse_error = ""
                    parse_error_envelope: Dict[str, Any] = {}
                    request_error_envelope: Dict[str, Any] = {}
                    get_last_request_error_envelope = getattr(self._ai_client, "get_last_request_error_envelope", None)
                    if callable(get_last_request_error_envelope):
                        try:
                            request_error_envelope = dict(get_last_request_error_envelope() or {})
                        except Exception:
                            request_error_envelope = {}
                    if request_error_envelope:
                        print(f"[ERROR_ENVELOPE] {request_error_envelope}")
                        user_message = str(request_error_envelope.get("user_message") or "").strip()
                        error_code = str(request_error_envelope.get("code") or "").strip()
                        retryable = bool(request_error_envelope.get("retryable"))
                        if error_code == CODE_MODEL_API_KEY_MISSING or (user_message and not retryable):
                            print(f"错误：{user_message or '模型请求失败'}")
                            return user_message or "模型请求失败"
                    get_last_parse_error = getattr(self._ai_client, "get_last_parse_error", None)
                    if callable(get_last_parse_error):
                        try:
                            parse_error = str(get_last_parse_error() or "").strip()
                        except Exception:
                            parse_error = ""
                    get_last_parse_error_envelope = getattr(self._ai_client, "get_last_parse_error_envelope", None)
                    if callable(get_last_parse_error_envelope):
                        try:
                            parse_error_envelope = dict(get_last_parse_error_envelope() or {})
                        except Exception:
                            parse_error_envelope = {}
                    if parse_error:
                        print(f"错误：模型响应解析失败 - {parse_error}")
                        state.last_tool_feedback = self._build_invalid_model_output_feedback(parse_error)
                        if parse_error_envelope:
                            print(f"[ERROR_ENVELOPE] {parse_error_envelope}")
                    else:
                        print("错误：未收到模型响应")
                    total_loop_time += time.perf_counter() - loop_start
                    state.last_bundles = bundles
                    state.last_screen_group_hash = screen_group_hash
                    continue

                agent_response = self._parser.extract_agent_response(ai_result)
                branch = get_agent_response_branch(agent_response)
                state.thinking = agent_response.get("thinking", "")
                branch_result = self._branch_executor.handle_branch(
                    branch=branch,
                    agent_response=agent_response,
                    state=state,
                    context_window=context_window,
                    context=BranchExecutionContext(
                        iteration_index=i,
                        loop_start=loop_start,
                        capture_ms=capture_ms,
                        changed_pixels_ratio=changed_pixels_ratio,
                        screen_info=screen_info,
                        bundles=bundles,
                        screen_group_hash=screen_group_hash,
                        ai_metrics=ai_metrics,
                        report_mode=report_mode,
                        report_requested=report_requested,
                        report_request_reason=report_request_reason,
                        loop_report_requested=loop_report_requested,
                        held_modifier_prompt=held_modifier_prompt,
                        on_iteration=on_iteration,
                        on_report=on_report,
                        should_stop=should_stop,
                    ),
                )
                if branch_result.final_response is not None:
                    total_loop_time += time.perf_counter() - loop_start
                    return branch_result.final_response
                if branch_result.continue_loop:
                    total_loop_time += time.perf_counter() - loop_start
                    continue

                total_loop_time += time.perf_counter() - loop_start

            return state.thinking
        finally:
            try:
                self._automation.release_all_held_modifier_keys()
            except Exception as exc:
                print(f"释放长按修饰键失败: {exc}")
            task_token_summary = self._build_task_token_summary(
                model_request_count=state.model_request_count,
                any_token_usage_available=state.any_token_usage_available,
                task_token_usage_complete=state.task_token_usage_complete,
                task_prompt_tokens=state.task_prompt_tokens,
                task_completion_tokens=state.task_completion_tokens,
                task_total_tokens=state.task_total_tokens,
            )
            if task_token_summary:
                print(task_token_summary)
            print(f"完成当前指令总循环耗时: {total_loop_time:.2f}秒")

    def _clear_extract_files(self) -> None:
        self._memory_content_cache = None
        self._runtime_artifact_store.clear_reader_artifacts()

    def _clear_memory_file(self) -> None:
        self._memory_content_cache = None
        self._task_memory_store.clear()

    def _clear_memory_files(self) -> None:
        self._clear_extract_files()
        self._clear_memory_file()

    def _read_memory_content(self) -> str:
        """读取 remember 文本内容"""
        return self._task_memory_store.read()

    def _build_background_jobs_prompt(self) -> str:
        try:
            return self._job_manager.build_running_jobs_prompt()
        except Exception as exc:
            print(f"构建后台任务上下文失败: {exc}")
            return ""

    def _build_pending_reports_prompt(self) -> str:
        try:
            return self._job_manager.build_pending_reports_prompt()
        except Exception as exc:
            print(f"构建待汇报任务上下文失败: {exc}")
            return ""

    @staticmethod
    def _build_screen_info(bundles: List[ScreenCaptureBundle]) -> List[Dict[str, Any]]:
        return ObservationService.build_screen_info(bundles)

    @staticmethod
    def _build_screen_group_hash(bundles: List[ScreenCaptureBundle]) -> str:
        return ObservationService.build_screen_group_hash(bundles)

    def _calculate_changed_pixels_ratio(
        self,
        previous_bundles: Optional[List[ScreenCaptureBundle]],
        current_bundles: List[ScreenCaptureBundle],
    ) -> float:
        if not previous_bundles:
            self._retain_gray_frame_cache([])
            return 1.0

        previous_map = {bundle.index: bundle for bundle in previous_bundles}
        self._retain_gray_frame_cache(previous_bundles + current_bundles)
        ratios: List[float] = []
        for bundle in current_bundles:
            previous = previous_map.get(bundle.index)
            if previous is None:
                ratios.append(1.0)
                continue

            previous_gray = self._get_bundle_gray(previous)
            current_gray = self._get_bundle_gray(bundle)
            if previous_gray is None or current_gray is None:
                ratios.append(1.0)
                continue
            ratios.append(self._screenshot.calculate_image_difference(previous_gray, current_gray))

        return max(ratios) if ratios else 1.0

    def _is_stalled(
        self,
        previous_hash: Optional[str],
        current_hash: str,
        previous_signature: Optional[Dict[str, Any]],
        current_signature: Dict[str, Any],
    ) -> bool:
        return self._stall_policy.is_stalled(
            previous_hash=previous_hash,
            current_hash=current_hash,
            previous_signature=previous_signature,
            current_signature=current_signature,
        )

    def _is_same_tool_signature(
        self,
        previous_signature: Dict[str, Any],
        current_signature: Dict[str, Any],
    ) -> bool:
        return self._stall_policy.is_same_tool_signature(previous_signature, current_signature)

    @staticmethod
    def _build_tool_signature(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "tool_name": tool_name,
            "args": comparable_tool_args(tool_name, tool_args),
            "points": extract_tool_points(tool_name, tool_args),
        }

    @staticmethod
    def _build_page_loading_signature(page_loading_args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "tool_name": "page_loading",
            "args": dict(page_loading_args or {}),
            "points": [],
        }

    @staticmethod
    def _wait_for_long_page_loading(wait_seconds: int, should_stop: Callable[[], bool]) -> bool:
        deadline = time.monotonic() + max(1, int(wait_seconds))
        while True:
            if should_stop():
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(0.1, remaining))

    @staticmethod
    def _build_invalid_model_output_feedback(parse_error: str = "") -> str:
        return build_invalid_model_output_feedback(parse_error)

    @staticmethod
    def _is_copy_or_paste_hotkey(tool_name: str, tool_args: Dict[str, Any]) -> bool:
        return is_copy_or_paste_hotkey(tool_name, tool_args)

    def _execute_optional_remember(
        self,
        agent_response: Dict[str, Any],
        screen_info: Optional[List[Dict[str, Any]]],
    ) -> tuple[Optional[Dict[str, Any]], bool]:
        remember_payload = agent_response.get("remember")
        if not remember_payload:
            return None, False

        remember_result = self._automation.tool_remember(
            content=remember_payload["content"],
            screen_info=screen_info,
        )
        remember_written = bool(remember_result.get("ok"))
        if remember_written:
            self._append_memory_content_cache(remember_payload["content"])
        return remember_result, remember_written

    @staticmethod
    def _append_remember_feedback(
        base_feedback: str,
        remember_result: Dict[str, Any],
        remember_content: str,
    ) -> str:
        return append_remember_feedback(base_feedback, remember_result, remember_content)

    def _build_page_extraction_notice(self, tool_result: Dict[str, Any]) -> str:
        return build_page_extraction_notice(tool_result)

    def _build_document_extraction_notice(self, tool_result: Dict[str, Any]) -> str:
        return build_document_extraction_notice(tool_result)

    @staticmethod
    def _build_iteration_payload(
        agent_response: Dict[str, Any],
        action_result: str,
        capture_ms: float,
        settle_ms: float,
        execute_ms: float,
        loop_total_ms: float,
        changed_pixels_ratio: float,
        screen_count: int,
        ai_metrics: Dict[str, Any],
        report_mode: str,
        report_requested: bool,
        report_request_reason: str,
        loop_report_requested: bool,
        held_modifier_keys: Optional[List[str]] = None,
        held_modifier_notice: str = "",
        tool_result: Optional[Dict[str, Any]] = None,
        remember_content: str = "",
        remember_written: bool = False,
    ) -> Dict[str, Any]:
        return build_iteration_payload(
            agent_response=agent_response,
            action_result=action_result,
            capture_ms=capture_ms,
            settle_ms=settle_ms,
            execute_ms=execute_ms,
            loop_total_ms=loop_total_ms,
            changed_pixels_ratio=changed_pixels_ratio,
            screen_count=screen_count,
            ai_metrics=ai_metrics,
            report_mode=report_mode,
            report_requested=report_requested,
            report_request_reason=report_request_reason,
            loop_report_requested=loop_report_requested,
            held_modifier_keys=held_modifier_keys,
            held_modifier_notice=held_modifier_notice,
            tool_result=tool_result,
            remember_content=remember_content,
            remember_written=remember_written,
        )
