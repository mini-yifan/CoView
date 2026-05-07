"""Shared automation runtime helpers."""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from baodou_ai.core.error_envelope import (
    CODE_TOOL_EXEC_FAILED,
    KIND_EXECUTION_FAILED,
    SOURCE_TOOL,
    from_exception,
)
from baodou_ai.core.settler import SettleResult


@dataclass(frozen=True)
class ToolContext:
    """Tool execution runtime context."""

    screen_info: Optional[List[Dict[str, Any]]] = None


@dataclass
class ToolOutcome:
    """Internal standard result for tool execution."""

    ok: bool
    summary: str
    error: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_result(self) -> Dict[str, Any]:
        result = {
            "ok": self.ok,
            "summary": self.summary,
            "error": self.error,
        }
        result.update(self.extras)
        return result


class ToolInterrupted(Exception):
    """Raised when the user stops the current task while a tool is running."""


class RuntimeMixin:
    _INTERRUPTED_SUMMARY = "工具执行已中断"
    _INTERRUPTED_ERROR = "用户已停止当前任务"

    @classmethod
    def _raise_if_stopped(cls, should_stop: Optional[Callable[[], bool]] = None) -> None:
        if should_stop is not None and should_stop():
            raise ToolInterrupted(cls._INTERRUPTED_ERROR)

    def _get_smooth_move_duration(self, duration: float) -> float:
        """统一计算鼠标平滑移动时长，避免直接闪现到目标位置。"""
        try:
            configured = float(duration)
        except (TypeError, ValueError):
            configured = 0.0
        try:
            min_duration = float(self._config.mouse_config.get("min_move_duration", 0.35))
        except (TypeError, ValueError):
            min_duration = 0.35
        return max(configured, max(min_duration, 0.0))

    def _move_cursor_smooth(self, x: float, y: float, duration: float) -> None:
        """平滑移动鼠标到指定坐标。"""
        move_duration = self._get_smooth_move_duration(duration)
        self._platform_adapter.move_cursor(x, y, duration=move_duration)

    @staticmethod
    def _call_with_optional_should_stop(
        func: Callable,
        *args: Any,
        should_stop: Optional[Callable[[], bool]] = None,
        **kwargs: Any,
    ) -> Any:
        """调用可选支持 should_stop 的内部 helper，兼容测试替身和旧 helper。"""
        if should_stop is None:
            return func(*args, **kwargs)
        try:
            signature = inspect.signature(func)
            if "should_stop" in signature.parameters:
                return func(*args, should_stop=should_stop, **kwargs)
        except (TypeError, ValueError):
            pass
        return func(*args, **kwargs)

    @staticmethod
    def _sleep_interruptibly(
        seconds: float,
        should_stop: Optional[Callable[[], bool]] = None,
        step_seconds: float = 0.05,
    ) -> bool:
        """按小步等待，返回 False 表示等待期间收到停止信号。"""
        try:
            delay = float(seconds)
        except (TypeError, ValueError):
            delay = 0.0
        if delay <= 0:
            return True

        should_stop = should_stop or (lambda: False)
        deadline = time.monotonic() + delay
        while True:
            if should_stop():
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(max(step_seconds, 0.001), remaining))

    @staticmethod
    def _pick_target_screen(
        screen_index: int,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """按索引选择目标屏幕，越界时回退到第一个屏幕。"""
        if screen_info and 0 <= screen_index < len(screen_info):
            return screen_info[screen_index]
        if screen_info:
            return screen_info[0]
        return None

    _SCROLL_LEVEL_TO_MULTIPLIER = {
        1: 0.2,
        2: 0.4,
        3: 0.6,
        4: 0.8,
        5: 1.0,
        6: 2.0,
        7: 3.0,
        8: 5.0,
        9: 7.0,
        10: 10.0,
    }

    def _resolve_scroll_amount(self, scroll_level: int = 5) -> int:
        """根据当前平台默认值和档位计算实际滚动量。"""
        try:
            normalized_level = int(scroll_level)
        except (TypeError, ValueError) as exc:
            raise ValueError("scroll_level 必须是整数") from exc

        if normalized_level < 1 or normalized_level > 10:
            raise ValueError("scroll_level 必须在 1-10 之间")

        base_amount = 10 if self._current_os == "Darwin" else 500
        multiplier = self._SCROLL_LEVEL_TO_MULTIPLIER[normalized_level]
        return max(1, int(round(base_amount * multiplier)))
    
    def set_window_callbacks(self, hide_callback: Callable, show_callback: Callable) -> None:
        """设置窗口隐藏和显示的回调函数"""
        self._hide_windows_callback = hide_callback
        self._show_windows_callback = show_callback

    def set_job_manager(self, job_manager: Optional[JobManager]) -> None:
        """注入后台 Code Agent 任务管理器。"""
        self._job_manager = job_manager
    
    def _hide_windows(self) -> None:
        """隐藏窗口"""
        if self._hide_windows_callback:
            try:
                self._hide_windows_callback()
            except Exception as e:
                print(f"隐藏窗口时出错: {e}")
    
    def _show_windows(self) -> None:
        """显示窗口"""
        if self._show_windows_callback:
            try:
                self._show_windows_callback()
            except Exception as e:
                print(f"显示窗口时出错: {e}")

    def wait_for_stability(
        self,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> SettleResult:
        """等待页面稳定，并记录最近一次稳定检测结果"""
        self._raise_if_stopped(should_stop)
        self._last_settle_result = self._settler.wait_until_stable(
            screen_info=screen_info,
            should_stop=should_stop,
        )
        self._raise_if_stopped(should_stop)
        return self._last_settle_result

    def get_last_settle_result(self) -> Optional[SettleResult]:
        """获取最近一次稳定检测结果"""
        return self._last_settle_result

    def reset_page_extract_sequence(self) -> None:
        """在新任务开始时重置网页解析文件序号。"""
        self._page_extract_sequence = 0
        self._page_reader_state = {}

    def clear_page_reader_state(self) -> None:
        """清除当前网页读取状态（用于 token 预警清理），不重置序号。"""
        self._page_reader_state = {}

    def reset_document_extract_sequence(self) -> None:
        """在新任务开始时重置文档解析文件序号。"""
        self._document_extract_sequence = 0
        self._document_anchor_sequence = 0
        self._document_reader_state = {}

    def clear_document_reader_state(self) -> None:
        """清除当前文档读取状态（用于 token 预警清理），不重置序号。"""
        self._document_reader_state = {}

    @staticmethod
    def _build_tool_context(
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> ToolContext:
        """构建工具执行上下文。"""
        return ToolContext(screen_info=screen_info)

    @staticmethod
    def _build_tool_outcome(
        ok: bool,
        summary: str,
        error: Optional[str] = None,
        fallback: Optional[Dict[str, Any]] = None,
        **extras: Any,
    ) -> ToolOutcome:
        merged_extras = dict(extras)
        if fallback is not None:
            merged_extras["fallback"] = fallback
        return ToolOutcome(
            ok=ok,
            summary=summary,
            error=error,
            extras=merged_extras,
        )

    @staticmethod
    def _result_from_tool_outcome(outcome: ToolOutcome) -> Dict[str, Any]:
        """将内部标准结果转换为现有 dict 结构。"""
        return outcome.to_result()

    @staticmethod
    def _build_tool_result(
        ok: bool,
        summary: str,
        error: Optional[str] = None,
        fallback: Optional[Dict[str, Any]] = None,
        **extras: Any,
    ) -> Dict[str, Any]:
        """构建统一工具返回结构。"""
        outcome = RuntimeMixin._build_tool_outcome(
            ok=ok,
            summary=summary,
            error=error,
            fallback=fallback,
            **extras,
        )
        return RuntimeMixin._result_from_tool_outcome(outcome)

    def _execute_tool_runtime(
        self,
        context: ToolContext,
        operation: Callable[[ToolContext], ToolOutcome],
        failure_summary: str,
        wait_for_stability: bool = True,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """统一执行工具语义，并在成功后等待界面稳定。"""
        try:
            self._raise_if_stopped(should_stop)
            self._hide_windows()
            try:
                outcome = operation(context)
                if not isinstance(outcome, ToolOutcome):
                    raise TypeError("工具操作必须返回 ToolOutcome")
                if wait_for_stability and outcome.ok:
                    self._call_with_optional_should_stop(
                        self.wait_for_stability,
                        context.screen_info,
                        should_stop=should_stop,
                    )
            finally:
                self._show_windows()
            return self._result_from_tool_outcome(outcome)
        except ToolInterrupted:
            return self._build_tool_result(False, self._INTERRUPTED_SUMMARY, self._INTERRUPTED_ERROR)
        except Exception as exc:
            envelope = from_exception(
                exc,
                source=SOURCE_TOOL,
                kind=KIND_EXECUTION_FAILED,
                user_message=failure_summary,
                code=CODE_TOOL_EXEC_FAILED,
                retryable=True,
            )
            return envelope.to_tool_result(failure_summary, ok=False, error=str(exc))

    def get_held_modifier_keys(self) -> List[str]:
        """获取当前仍处于长按状态的修饰键。"""
        return list(self._held_modifier_keys)

    def get_frontmost_app_info(self) -> Dict[str, Any]:
        """获取当前前台应用信息。"""
        try:
            return self._platform_adapter.get_frontmost_app_info()
        except Exception as exc:
            print(f"获取当前前台应用信息失败: {exc}")
            return {}

    def activate_app(self, app_info: Dict[str, Any]) -> bool:
        """将指定应用激活到前台。"""
        try:
            return bool(self._platform_adapter.activate_app(app_info))
        except Exception as exc:
            print(f"激活前台应用失败: {exc}")
            return False

    def mark_held_modifier_state_active(self, current_step: int) -> None:
        """刷新长按修饰键状态的步数与时间基线。"""
        if not self._held_modifier_keys:
            self._held_modifier_since_step = None
            self._held_modifier_since_time = None
            return
        self._held_modifier_since_step = int(current_step)
        self._held_modifier_since_time = time.monotonic()

    def _release_modifier_keys(self, keys: Optional[List[str]] = None) -> List[str]:
        """释放指定或全部修饰键，并返回实际释放的键。"""
        if not self._held_modifier_keys:
            self._held_modifier_since_step = None
            self._held_modifier_since_time = None
            return []

        held_set = set(self._held_modifier_keys)
        if not keys:
            keys_to_release = list(self._held_modifier_keys)
        else:
            keys_to_release = [key for key in self._held_modifier_keys if key in set(keys)]

        if not keys_to_release:
            return []

        for key in reversed(keys_to_release):
            self._platform_adapter.key_up(key)

        self._held_modifier_keys = [key for key in self._held_modifier_keys if key not in set(keys_to_release)]
        if self._held_modifier_keys:
            self._held_modifier_since_time = time.monotonic()
        else:
            self._held_modifier_since_step = None
            self._held_modifier_since_time = None
        return keys_to_release

    def release_all_held_modifier_keys(self) -> List[str]:
        """释放全部长按中的修饰键。"""
        return self._release_modifier_keys()

    def auto_release_stale_modifier_keys(
        self,
        current_step: int,
        max_steps: int,
        max_seconds: float,
    ) -> Optional[str]:
        """当长按修饰键超时或超步数时自动释放。"""
        if not self._held_modifier_keys:
            return None

        by_steps = (
            self._held_modifier_since_step is not None
            and max_steps > 0
            and (int(current_step) - int(self._held_modifier_since_step)) >= max_steps
        )
        by_time = (
            self._held_modifier_since_time is not None
            and max_seconds > 0
            and (time.monotonic() - float(self._held_modifier_since_time)) >= max_seconds
        )
        if not by_steps and not by_time:
            return None

        released = self.release_all_held_modifier_keys()
        if not released:
            return None
        return "先前长按状态已自动解除。"

    def _execute_single_point_tool(
        self,
        screen_index: int,
        position: List[float],
        action: str,
        success_summary: str,
        failure_summary: str,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        scroll_level: Optional[int] = None,
        long_press_duration_seconds: Optional[float] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        context = self._build_tool_context(screen_info)

        def operation(tool_context: ToolContext) -> ToolOutcome:
            duration = self._config.mouse_config.get("move_duration", 0.1)
            target_screen = self._pick_target_screen(screen_index, tool_context.screen_info)
            scroll_amount = (
                self._resolve_scroll_amount(scroll_level)
                if scroll_level is not None
                else None
            )
            self._handle_single_point(
                position,
                action,
                duration,
                target_screen,
                scroll_amount=scroll_amount,
                long_press_duration_seconds=long_press_duration_seconds,
                should_stop=should_stop,
            )
            return self._build_tool_outcome(True, success_summary)

        return self._execute_tool_runtime(
            context=context,
            operation=operation,
            failure_summary=failure_summary,
            should_stop=should_stop,
        )

    def _execute_drag_tool(
        self,
        start_screen_index: int,
        start_position: List[float],
        end_screen_index: int,
        end_position: List[float],
        success_summary: str,
        failure_summary: str,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        context = self._build_tool_context(screen_info)

        def operation(tool_context: ToolContext) -> ToolOutcome:
            duration = self._config.mouse_config.get("move_duration", 0.1)
            target_screen = self._pick_target_screen(start_screen_index, tool_context.screen_info)
            end_screen = self._pick_target_screen(end_screen_index, tool_context.screen_info)
            self._handle_drag(
                [start_position, end_position],
                duration,
                target_screen,
                end_screen,
            )
            return self._build_tool_outcome(True, success_summary)

        return self._execute_tool_runtime(
            context=context,
            operation=operation,
            failure_summary=failure_summary,
        )

    def _execute_text_tool(
        self,
        text: str,
        replace: bool = False,
        submit: bool = False,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        screen_index: Optional[int] = None,
        position: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        context = self._build_tool_context(screen_info)
        success_summary, failure_summary = self._build_input_text_summaries(
            replace=replace,
            submit=submit,
        )

        def operation(tool_context: ToolContext) -> ToolOutcome:
            mapped_coordinates = None
            if position is not None:
                duration = self._config.mouse_config.get("move_duration", 0.1)
                target_screen = self._pick_target_screen(screen_index or 0, tool_context.screen_info)
                mapped_coordinates, _ = self._move_to_position(
                    position,
                    duration,
                    target_screen=target_screen,
                    label="坐标",
                )
            self._handle_type_input(
                text,
                mapped_coordinates,
                replace=replace,
                submit=submit,
            )
            return self._build_tool_outcome(True, success_summary)

        return self._execute_tool_runtime(
            context=context,
            operation=operation,
            failure_summary=failure_summary,
        )

    @staticmethod
    def _build_input_text_summaries(replace: bool, submit: bool) -> Tuple[str, str]:
        if replace and submit:
            return "已替换输入内容并提交", "替换输入内容并提交失败"
        if replace:
            return "已替换输入内容", "替换输入内容失败"
        if submit:
            return "已输入文本并提交", "输入文本并提交失败"
        return "已输入文本", "输入文本失败"

    def tool_hold_modifier_keys(
        self,
        keys: List[str],
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        context = self._build_tool_context(screen_info)

        def operation(_context: ToolContext) -> ToolOutcome:
            translated_keys = self._platform_adapter.translate_hotkey_keys(keys)
            missing_keys = [key for key in translated_keys if key not in self._held_modifier_keys]
            self._last_settle_result = None
            for key in missing_keys:
                self._platform_adapter.key_down(key)
                self._held_modifier_keys.append(key)
            self._held_modifier_since_time = time.monotonic()
            return self._build_tool_outcome(True, "已进入修饰键长按状态")

        return self._execute_tool_runtime(
            context=context,
            operation=operation,
            failure_summary="进入修饰键长按状态失败",
            wait_for_stability=False,
        )

    def tool_release_modifier_keys(
        self,
        keys: Optional[List[str]] = None,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        context = self._build_tool_context(screen_info)

        def operation(_context: ToolContext) -> ToolOutcome:
            translated_keys = self._platform_adapter.translate_hotkey_keys(keys or []) if keys else None
            self._last_settle_result = None
            self._release_modifier_keys(translated_keys)
            return self._build_tool_outcome(True, "已释放修饰键长按状态")

        return self._execute_tool_runtime(
            context=context,
            operation=operation,
            failure_summary="释放修饰键长按状态失败",
            wait_for_stability=False,
        )

    def tool_input_text(
        self,
        text: str,
        screen_index: Optional[int] = None,
        position: Optional[List[float]] = None,
        replace: bool = False,
        submit: bool = False,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        try:
            has_position = position is not None or screen_index is not None
            if has_position and (position is None or screen_index is None):
                raise ValueError("input_text 传入坐标时必须同时提供 screen_index 和 position")
            if replace and not has_position:
                raise ValueError("input_text(replace=true) 必须同时提供 screen_index 和 position")
            return self._execute_text_tool(
                text=text,
                replace=replace,
                submit=submit,
                screen_info=screen_info,
                screen_index=screen_index,
                position=position,
            )
        except Exception as exc:
            return self._build_tool_result(False, "输入文本失败", str(exc))
