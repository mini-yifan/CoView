from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from baodou_ai.agent.protocol import is_tool_branch
from baodou_ai.core.context_window import ContextWindowManager
from baodou_ai.core.runner_state import RunnerLoopState
from baodou_ai.core.screenshot import ScreenCaptureBundle
from baodou_ai.core.tool_feedback import (
    append_remember_feedback,
    build_page_loading_feedback,
    build_tool_feedback,
)


@dataclass
class BranchExecutionContext:
    iteration_index: int
    loop_start: float
    capture_ms: float
    changed_pixels_ratio: float
    screen_info: List[Dict[str, Any]]
    bundles: List[ScreenCaptureBundle]
    screen_group_hash: str
    ai_metrics: Dict[str, Any]
    report_mode: str
    report_requested: bool
    report_request_reason: str
    loop_report_requested: bool
    held_modifier_prompt: str
    on_iteration: Optional[Callable[[int, Dict[str, Any]], Any]]
    on_report: Optional[Callable[[str], Optional[threading.Event]]]
    should_stop: Callable[[], bool]


@dataclass
class BranchExecutionResult:
    final_response: Optional[str] = None
    continue_loop: bool = False


class RunnerBranchExecutor:
    def __init__(self, runner: Any) -> None:
        self._runner = runner

    def handle_branch(
        self,
        *,
        branch: str,
        agent_response: Dict[str, Any],
        state: RunnerLoopState,
        context_window: ContextWindowManager,
        context: BranchExecutionContext,
    ) -> BranchExecutionResult:
        if is_tool_branch(branch):
            return self._handle_tool_branch(
                tool_name=branch,
                agent_response=agent_response,
                state=state,
                context_window=context_window,
                context=context,
            )
        if branch == "page_loading":
            return self._handle_page_loading_branch(
                agent_response=agent_response,
                state=state,
                context=context,
            )
        if branch == "respond":
            return self._handle_respond_branch(
                agent_response=agent_response,
                state=state,
                context=context,
            )
        raise ValueError(f"Unknown agent branch: {branch}")

    def _handle_tool_branch(
        self,
        *,
        tool_name: str,
        agent_response: Dict[str, Any],
        state: RunnerLoopState,
        context_window: ContextWindowManager,
        context: BranchExecutionContext,
    ) -> BranchExecutionResult:
        tool_args = agent_response[tool_name]
        current_signature = self._runner._build_tool_signature(tool_name, tool_args)
        remember_content = agent_response.get("remember", {}).get("content", "")

        report_text = str(agent_response.get("report") or "").strip()
        tts_event = context.on_report(report_text) if (report_text and context.on_report) else None

        if self._runner._is_stalled(
            previous_hash=state.last_screen_group_hash,
            current_hash=context.screen_group_hash,
            previous_signature=state.last_tool_signature,
            current_signature=current_signature,
        ):
            state.stalled_loop_count += 1
        else:
            state.stalled_loop_count = 0

        if state.stalled_loop_count >= self._runner._config.execution_config.get("stalled_difficult_threshold", 4):
            self._runner._wait_for_tts(tts_event, context.should_stop)
            return BranchExecutionResult(final_response="Task is difficult; user needs to adjust strategy or provide help")

        if state.stalled_loop_count >= self._runner._config.execution_config.get("stalled_replan_threshold", 2):
            state.replan_feedback = (
                "The previous tool call did not produce a visible interface change. Please replan and do not repeat the same tool and position; "
                "prioritize trying new elements, new screens, or different tools."
            )
            state.on_report_consumed(
                has_report=bool(agent_response.get("report")),
                report_requested=context.report_requested,
            )
            self._emit_iteration(
                context=context,
                agent_response=agent_response,
                action_result="Replan triggered, no action executed",
                settle_ms=0.0,
                execute_ms=0.0,
                tool_result=None,
                remember_content=remember_content,
                remember_written=False,
            )
            state.last_bundles = context.bundles
            state.last_screen_group_hash = context.screen_group_hash
            state.last_tool_signature = current_signature
            self._runner._wait_for_tts(tts_event, context.should_stop)
            return BranchExecutionResult(continue_loop=True)

        remember_result, remember_written = self._runner._execute_optional_remember(
            agent_response=agent_response,
            screen_info=context.screen_info,
        )
        if not self._runner._wait_for_tool_pacing(state.last_tool_started_at, context.should_stop):
            return BranchExecutionResult(final_response="Task interrupted by user")

        execute_start = time.perf_counter()
        state.last_tool_started_at = execute_start
        tool_result = self._runner._tool_executor.execute(
            tool_name=tool_name,
            tool_args=tool_args,
            screen_info=context.screen_info,
            should_stop=context.should_stop,
        )
        execute_total_ms = (time.perf_counter() - execute_start) * 1000.0
        if context.should_stop():
            return BranchExecutionResult(final_response="Task interrupted by user")

        settle_result = self._runner._automation.get_last_settle_result()
        settle_ms = settle_result.elapsed_ms if settle_result else 0.0
        execute_ms = max(execute_total_ms - settle_ms, 0.0)

        if tool_name == "read_current_page":
            context_window.update_after_page_tool(
                tool_result=tool_result,
                build_page_extraction_notice=self._runner._build_page_extraction_notice,
            )
        if tool_name == "read_current_document":
            context_window.update_after_document_tool(
                tool_result=tool_result,
                build_document_extraction_notice=self._runner._build_document_extraction_notice,
            )

        state.last_tool_feedback = build_tool_feedback(
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            remember_result=remember_result,
            remember_content=remember_content,
        )

        if tool_name == "code_agent" and tool_result.get("ok"):
            state.bump_step()
            state.push_effective_history(context.screen_group_hash, current_signature, keep_last=6)
            state.on_report_consumed(
                has_report=bool(agent_response.get("report")),
                report_requested=context.report_requested,
            )
            state.last_bundles = context.bundles
            state.last_screen_group_hash = context.screen_group_hash
            state.last_tool_signature = current_signature

            launch_report = str(
                tool_result.get("launch_report")
                or agent_response.get("report")
                or "我已经在后台启动代码任务，你可以继续使用电脑。我完成后会向你汇报结果。"
            ).strip()

            self._emit_iteration(
                context=context,
                agent_response=agent_response,
                action_result=tool_result["summary"],
                settle_ms=settle_ms,
                execute_ms=execute_ms,
                tool_result=tool_result,
                remember_content=remember_content,
                remember_written=remember_written,
            )
            if tts_event is not None:
                self._runner._wait_for_tts(tts_event, context.should_stop)
            elif launch_report and context.on_report:
                launch_tts_event = context.on_report(launch_report)
                self._runner._wait_for_tts(launch_tts_event, context.should_stop)
            else:
                self._runner._wait_for_tts(None, context.should_stop)
            return BranchExecutionResult(final_response=launch_report)

        if tool_result.get("ok") and not self._runner._wait_before_next_capture(context.should_stop):
            return BranchExecutionResult(final_response="Task interrupted by user")

        if tool_result.get("ok"):
            state.bump_step()
            if tool_name == "hold_modifier_keys":
                self._runner._automation.mark_held_modifier_state_active(state.step_index)
            state.push_effective_history(context.screen_group_hash, current_signature, keep_last=6)

        state.on_report_consumed(
            has_report=bool(agent_response.get("report")),
            report_requested=context.report_requested,
        )
        state.last_bundles = context.bundles
        state.last_screen_group_hash = context.screen_group_hash
        state.last_tool_signature = current_signature

        self._emit_iteration(
            context=context,
            agent_response=agent_response,
            action_result=tool_result["summary"],
            settle_ms=settle_ms,
            execute_ms=execute_ms,
            tool_result=tool_result,
            remember_content=remember_content,
            remember_written=remember_written,
        )
        self._runner._wait_for_tts(tts_event, context.should_stop)
        return BranchExecutionResult()

    def _handle_page_loading_branch(
        self,
        *,
        agent_response: Dict[str, Any],
        state: RunnerLoopState,
        context: BranchExecutionContext,
    ) -> BranchExecutionResult:
        page_loading_args = dict(agent_response.get("page_loading") or {})
        page_loading_mode = str(page_loading_args.get("mode") or "short_wait").strip().lower()
        current_signature = self._runner._build_page_loading_signature(page_loading_args)
        remember_content = agent_response.get("remember", {}).get("content", "")

        report_text = str(agent_response.get("report") or "").strip()
        tts_event = context.on_report(report_text) if (report_text and context.on_report) else None

        if self._runner._is_stalled(
            previous_hash=state.last_screen_group_hash,
            current_hash=context.screen_group_hash,
            previous_signature=state.last_tool_signature,
            current_signature=current_signature,
        ):
            state.stalled_loop_count += 1
        else:
            state.stalled_loop_count = 0

        if state.stalled_loop_count >= self._runner._config.execution_config.get("stalled_difficult_threshold", 4):
            self._runner._wait_for_tts(tts_event, context.should_stop)
            return BranchExecutionResult(final_response="Task is difficult; user needs to adjust strategy or provide help")

        if state.stalled_loop_count >= self._runner._config.execution_config.get("stalled_replan_threshold", 2):
            state.replan_feedback = (
                "The previous wait for page stability did not produce new progress. Please replan and do not repeatedly return only page_loading; "
                "prioritize judging whether the page is already operable, or try a new interface action."
            )
            state.on_report_consumed(
                has_report=bool(agent_response.get("report")),
                report_requested=context.report_requested,
            )
            self._emit_iteration(
                context=context,
                agent_response=agent_response,
                action_result="Replan triggered, no wait executed",
                settle_ms=0.0,
                execute_ms=0.0,
                tool_result=None,
                remember_content=remember_content,
                remember_written=False,
            )
            state.last_bundles = context.bundles
            state.last_screen_group_hash = context.screen_group_hash
            state.last_tool_signature = current_signature
            self._runner._wait_for_tts(tts_event, context.should_stop)
            return BranchExecutionResult(continue_loop=True)

        remember_result, remember_written = self._runner._execute_optional_remember(
            agent_response=agent_response,
            screen_info=context.screen_info,
        )
        if not self._runner._wait_for_tool_pacing(state.last_tool_started_at, context.should_stop):
            return BranchExecutionResult(final_response="Task interrupted by user")

        execute_start = time.perf_counter()
        state.last_tool_started_at = execute_start
        if page_loading_mode == "long_wait":
            wait_seconds = int(page_loading_args.get("wait_seconds") or 3)
            long_wait_completed = self._runner._wait_for_long_page_loading(
                wait_seconds=wait_seconds,
                should_stop=context.should_stop,
            )
            if not long_wait_completed:
                return BranchExecutionResult(final_response="Task interrupted by user")
            page_loading_result = {
                "ok": True,
                "summary": f"已长等待 {wait_seconds} 秒",
                "error": None,
                "mode": "long_wait",
                "wait_seconds": wait_seconds,
            }
        else:
            page_loading_result = self._runner._automation.tool_page_loading(screen_info=context.screen_info)
            page_loading_result = dict(page_loading_result or {})
            page_loading_result.setdefault("mode", "short_wait")
        execute_total_ms = (time.perf_counter() - execute_start) * 1000.0
        if context.should_stop():
            return BranchExecutionResult(final_response="Task interrupted by user")

        settle_result = None if page_loading_mode == "long_wait" else self._runner._automation.get_last_settle_result()
        settle_ms = settle_result.elapsed_ms if settle_result else 0.0
        execute_ms = max(execute_total_ms - settle_ms, 0.0)

        state.last_tool_feedback = build_page_loading_feedback(
            page_loading_result,
            remember_result=remember_result,
            remember_content=remember_content,
        )

        if page_loading_result.get("ok"):
            state.bump_step()
            state.push_effective_history(context.screen_group_hash, current_signature, keep_last=6)

        state.on_report_consumed(
            has_report=bool(agent_response.get("report")),
            report_requested=context.report_requested,
        )
        state.last_bundles = context.bundles
        state.last_screen_group_hash = context.screen_group_hash
        state.last_tool_signature = current_signature

        self._emit_iteration(
            context=context,
            agent_response=agent_response,
            action_result=page_loading_result["summary"],
            settle_ms=settle_ms,
            execute_ms=execute_ms,
            tool_result=page_loading_result,
            remember_content=remember_content,
            remember_written=remember_written,
        )
        self._runner._wait_for_tts(tts_event, context.should_stop)
        return BranchExecutionResult()

    def _handle_respond_branch(
        self,
        *,
        agent_response: Dict[str, Any],
        state: RunnerLoopState,
        context: BranchExecutionContext,
    ) -> BranchExecutionResult:
        respond_payload = agent_response["respond"]
        respond_report = str(respond_payload.get("report") or "").strip()
        remember_content = agent_response.get("remember", {}).get("content", "")
        remember_result, remember_written = self._runner._execute_optional_remember(
            agent_response=agent_response,
            screen_info=context.screen_info,
        )
        if remember_result is not None:
            state.last_tool_feedback = append_remember_feedback(
                base_feedback="Appended memory write was performed before ending this turn.",
                remember_result=remember_result,
                remember_content=remember_content,
            )
        self._emit_iteration(
            context=context,
            agent_response=agent_response,
            action_result=respond_payload["report"],
            settle_ms=0.0,
            execute_ms=0.0,
            tool_result=None,
            remember_content=remember_content,
            remember_written=remember_written,
        )
        if respond_report and context.on_report:
            context.on_report(respond_report)
        return BranchExecutionResult(final_response=respond_payload["report"])

    def _emit_iteration(
        self,
        *,
        context: BranchExecutionContext,
        agent_response: Dict[str, Any],
        action_result: str,
        settle_ms: float,
        execute_ms: float,
        tool_result: Optional[Dict[str, Any]],
        remember_content: str,
        remember_written: bool,
    ) -> None:
        if context.on_iteration is None:
            return
        loop_total_ms = (time.perf_counter() - context.loop_start) * 1000.0
        context.on_iteration(
            context.iteration_index,
            self._runner._build_iteration_payload(
                agent_response=agent_response,
                action_result=action_result,
                capture_ms=context.capture_ms,
                settle_ms=settle_ms,
                execute_ms=execute_ms,
                loop_total_ms=loop_total_ms,
                changed_pixels_ratio=context.changed_pixels_ratio,
                screen_count=len(context.bundles),
                ai_metrics=context.ai_metrics,
                tool_result=tool_result,
                remember_content=remember_content,
                remember_written=remember_written,
                report_mode=context.report_mode,
                report_requested=context.report_requested,
                report_request_reason=context.report_request_reason,
                loop_report_requested=context.loop_report_requested,
                held_modifier_keys=self._runner._automation.get_held_modifier_keys(),
                held_modifier_notice=context.held_modifier_prompt,
            ),
        )
