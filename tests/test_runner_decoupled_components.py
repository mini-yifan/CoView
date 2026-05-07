from types import SimpleNamespace

from baodou_ai.core.context_window import ContextWindowManager
from baodou_ai.core.observation import ObservationService
from baodou_ai.core.process_report_policy import ProcessReportPolicy
from baodou_ai.core.runner_metrics import apply_model_metrics_to_state, build_iteration_token_log
from baodou_ai.core.runner_state import RunnerLoopState
from baodou_ai.core.stall_policy import StallPolicy
from baodou_ai.core.tool_feedback import (
    build_document_extraction_notice,
    build_page_loading_feedback,
    build_page_extraction_notice,
    build_tool_feedback,
)


def test_runner_loop_state_updates_step_history_and_report_flags():
    state = RunnerLoopState()

    state.bump_step()
    state.push_effective_history("hash-a", {"tool_name": "click", "args": {}, "points": [[1, 2]]}, keep_last=2)
    state.push_effective_history("hash-b", {"tool_name": "click", "args": {}, "points": [[3, 4]]}, keep_last=2)
    state.push_effective_history("hash-c", {"tool_name": "click", "args": {}, "points": [[5, 6]]}, keep_last=2)
    state.on_report_consumed(has_report=False, report_requested=True)

    assert state.step_index == 1
    assert len(state.recent_effective_history) == 2
    assert state.recent_effective_history[0]["screen_hash"] == "hash-b"
    assert state.pending_required_report is True

    state.on_report_consumed(has_report=True, report_requested=False)
    assert state.pending_required_report is False
    assert state.last_process_report_step == 1


def test_runner_metrics_apply_token_usage_and_missing_usage():
    state = RunnerLoopState()

    first = apply_model_metrics_to_state(
        state,
        {"token_usage_available": True, "prompt_tokens": "10", "completion_tokens": 5},
    )

    assert first.total_tokens == 15
    assert first.metrics["task_total_tokens"] == 15
    assert state.model_request_count == 1
    assert state.any_token_usage_available is True
    assert build_iteration_token_log(0, first.metrics) == "[第 1 轮 Token] 输入 10 | 输出 5 | 合计 15 | 累计 15"

    second = apply_model_metrics_to_state(state, {"token_usage_available": False})

    assert second.metrics["task_token_usage_complete"] is False
    assert second.metrics["task_total_tokens"] == 15
    assert state.model_request_count == 2


def test_tool_feedback_builds_fallback_and_reader_notices():
    feedback = build_tool_feedback(
        "read_current_page",
        {"mode": "extract"},
        {
            "ok": False,
            "summary": "不是浏览器",
            "error": "Chrome not frontmost",
            "fallback": {"type": "read_current_page_not_browser", "app_name": "Finder"},
        },
    )

    assert "Executed read_current_page tool" in feedback
    assert 'current frontmost app is "Finder"' in feedback

    page_notice = build_page_extraction_notice({
        "fallback": {"type": "read_current_page_need_extract_first"},
        "error": "missing context",
    })
    assert "read_current_page(mode=\"extract\") first" in page_notice
    assert "missing context" in page_notice

    document_notice = build_document_extraction_notice({
        "fallback": {"type": "read_current_document_not_supported_app"},
    })
    assert "does not support read_current_document" in document_notice


def test_tool_feedback_shortens_click_and_copy_paste_guidance():
    click_feedback = build_tool_feedback(
        "click",
        {"screen_index": 0, "position": [100, 200]},
        {"ok": True, "summary": "点击成功"},
    )
    assert click_feedback.startswith("点击成功")
    assert "use input_text directly" in click_feedback
    assert "pre-input steps" not in click_feedback
    assert "screen_index" not in click_feedback
    assert "position" not in click_feedback

    copy_feedback = build_tool_feedback(
        "hotkey",
        {"keys": ["command", "c"]},
        {"ok": True, "summary": "已复制"},
    )
    assert "text is already in context" in copy_feedback
    assert "GUI copy or paste" in copy_feedback
    assert "current screenshot, webpage context, document context, or remember" not in copy_feedback


def test_page_loading_feedback_is_summary_only():
    feedback = build_page_loading_feedback({"summary": "短暂等待完成", "ok": True})
    assert feedback == "短暂等待完成"

    error_feedback = build_page_loading_feedback(
        {"summary": "等待失败", "ok": False, "error": "timeout"}
    )
    assert error_feedback == "等待失败. Error: timeout"


def test_stall_policy_detects_stalled_and_loop():
    policy = StallPolicy(action_signature_tolerance_px=10)
    previous_signature = {"tool_name": "click", "args": {"a": 1}, "points": [(100, 200)]}
    current_signature = {"tool_name": "click", "args": {"a": 1}, "points": [(105, 209)]}

    assert policy.is_stalled("same", "same", previous_signature, current_signature) is True
    assert policy.is_stalled("same", "diff", previous_signature, current_signature) is False

    history = [
        {"screen_hash": "same", "signature": previous_signature},
        {"screen_hash": "same", "signature": current_signature},
    ]
    assert policy.has_repeated_same_action_loop("same", history) is True


def test_process_report_policy_respects_mode_and_loop_priority():
    config = SimpleNamespace(execution_config={"process_report_interval_steps": 3})
    stall_policy = StallPolicy(action_signature_tolerance_px=15)
    policy = ProcessReportPolicy(
        config=config,
        stall_policy=stall_policy,
        report_request_prompt="REQ",
        auto_skip_report_prompt="SKIP",
        off_skip_report_prompt="OFF",
        loop_report_request_prompt="LOOP",
    )

    req = policy.build_process_report_request(
        report_mode="auto",
        step_index=0,
        last_process_report_step=0,
        pending_required_report=False,
        current_screen_hash="h",
        recent_effective_history=[],
    )
    assert req == ("REQ", True, "mode", False)

    skip = policy.build_process_report_request(
        report_mode="auto",
        step_index=1,
        last_process_report_step=0,
        pending_required_report=False,
        current_screen_hash="h",
        recent_effective_history=[],
    )
    assert skip == ("SKIP", False, "mode", False)

    loop_req = policy.build_process_report_request(
        report_mode="off",
        step_index=5,
        last_process_report_step=5,
        pending_required_report=False,
        current_screen_hash="h",
        recent_effective_history=[
            {"screen_hash": "h", "signature": {"tool_name": "click", "args": {}, "points": [(1, 1)]}},
            {"screen_hash": "h", "signature": {"tool_name": "click", "args": {}, "points": [(1, 1)]}},
        ],
    )
    assert loop_req == ("LOOP", True, "loop", True)


def test_context_window_manager_schedules_warning_and_cleanup():
    manager = ContextWindowManager()
    manager.ephemeral_page_context = {"content": "page"}
    manager.ephemeral_document_context = {"content": "doc"}

    scheduled = manager.maybe_schedule_cleanup_on_tokens(round_prompt_tokens=800, context_token_limit=1000)
    assert scheduled is True
    assert "80%" in manager.context_warning_prompt

    calls = {"page": 0, "doc": 0}

    class FakeAutomation:
        def clear_page_reader_state(self):
            calls["page"] += 1

        def clear_document_reader_state(self):
            calls["doc"] += 1

    applied = manager.apply_pending_cleanup(FakeAutomation())
    assert applied is True
    assert calls == {"page": 1, "doc": 1}
    assert manager.ephemeral_page_context is None
    assert manager.ephemeral_document_context is None


def test_observation_service_normalization_and_hidden_capture_callbacks():
    normalized = ObservationService.normalize_frontmost_app_info({"app_name": "Chrome", "pid": "123"})
    assert normalized["app_name"] == "Chrome"
    assert normalized["pid"] == 123

    events = []

    class FakeScreenshot:
        def capture_all_screens_bundle(self):
            events.append("capture")
            return True, ["bundle"]

    ok, bundles = ObservationService.capture_with_hidden_windows(
        screenshot=FakeScreenshot(),
        on_transparent_enter=lambda: events.append("hide"),
        on_transparent_exit=lambda: events.append("show"),
    )
    assert ok is True
    assert bundles == ["bundle"]
    assert events == ["hide", "capture", "show"]
