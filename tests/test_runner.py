import time
from types import SimpleNamespace

import cv2
import numpy as np

from baodou_ai.core.config import Config
from baodou_ai.core.runner import ControlLoopRunner
from baodou_ai.core.screenshot import ScreenCaptureBundle


def _coerce_test_response(response):
    if not isinstance(response, dict) or "status" not in response:
        return response

    thinking = response.get("thinking", "测试")
    status = response["status"]
    top_report = response.get("report")

    if status == "tool_call":
        tool_info = response["tool"]
        payload = {
            "thinking": thinking,
            tool_info["name"]: tool_info["args"],
        }
        if top_report:
            payload["report"] = top_report
        return payload

    if status == "remember":
        payload = {
            "thinking": thinking,
            "remember": {
                "content": response["content"],
            },
            "page_loading": {},
        }
        if top_report:
            payload["report"] = top_report
        return payload

    if status == "page_loading":
        payload = {
            "thinking": thinking,
            "page_loading": {},
        }
        if top_report:
            payload["report"] = top_report
        return payload

    if status == "respond":
        return {
            "thinking": thinking,
            "respond": {
                "outcome": response["outcome"],
                "report": response["report"],
            },
        }

    raise ValueError(f"unsupported test status: {status}")


def make_bundle(index: int = 0, value: int = 0) -> ScreenCaptureBundle:
    image = np.full((8, 8, 3), value, dtype=np.uint8)
    success, buffer = cv2.imencode(".png", image)
    assert success
    png_bytes = buffer.tobytes()
    return ScreenCaptureBundle(
        index=index,
        x=0,
        y=0,
        width=1920,
        height=1080,
        logical_width=1920,
        logical_height=1080,
        is_primary=True,
        png_bytes=png_bytes,
        data_url="data:image/png;base64,test",
        frame_hash=f"frame-{index}-{value}",
        path=None,
    )


def test_is_copy_or_paste_hotkey_detects_common_shortcuts():
    assert ControlLoopRunner._is_copy_or_paste_hotkey("hotkey", {"keys": ["command", "c"]}) is True
    assert ControlLoopRunner._is_copy_or_paste_hotkey("hotkey", {"keys": ["ctrl", "v"]}) is True
    assert ControlLoopRunner._is_copy_or_paste_hotkey("hotkey", {"keys": ["command", "a"]}) is False
    assert ControlLoopRunner._is_copy_or_paste_hotkey("click", {"keys": ["command", "c"]}) is False


class FakeScreenshot:
    def __init__(self, bundle_groups):
        self.bundle_groups = list(bundle_groups)
        self.index = 0

    def capture_all_screens_bundle(self):
        current_index = min(self.index, len(self.bundle_groups) - 1)
        self.index += 1
        return True, self.bundle_groups[current_index]

    @staticmethod
    def calculate_image_difference(previous_gray, current_gray):
        diff = np.abs(previous_gray.astype(np.float32) - current_gray.astype(np.float32))
        return float(diff.mean() / 255.0)


class FakePlatformAdapter:
    def get_active_document_path(self, app_name):
        return None

    def move_to_trash(self, path):
        return {"ok": True, "error": None}

    def get_frontmost_app_info(self):
        return {"app_name": "Finder"}


class FakeAutomation:
    def __init__(self, memory_state=None, frontmost_sequence=None, activate_result=True):
        self.executed = []
        self._last_settle_result = SimpleNamespace(elapsed_ms=123.0)
        self._memory_state = memory_state
        self._held_modifier_keys = []
        self.auto_release_notice = None
        self.release_all_calls = 0
        self.marked_steps = []
        self._frontmost_sequence = list(frontmost_sequence or [])
        self._frontmost_index = 0
        self.activate_calls = []
        self.activate_result = activate_result
        self._platform_adapter = FakePlatformAdapter()
        self.clear_page_reader_state_calls = 0
        self.clear_document_reader_state_calls = 0

    def set_window_callbacks(self, hide_callback, show_callback):
        return None

    def tool_click(self, screen_index, position, screen_info=None):
        self.executed.append(("click", {"screen_index": screen_index, "position": position}))
        return {"ok": True, "summary": "已点击", "error": None}

    def tool_input_text(
        self,
        text,
        screen_index=None,
        position=None,
        replace=False,
        submit=False,
        screen_info=None,
    ):
        self.executed.append((
            "input_text",
            {
                "text": text,
                "screen_index": screen_index,
                "position": position,
                "replace": replace,
                "submit": submit,
            },
        ))
        return {"ok": True, "summary": "已输入文本", "error": None}

    def tool_launch_app(self, app_name, screen_info=None):
        self.executed.append(("launch_app", {"app_name": app_name}))
        return {"ok": True, "summary": "已启动应用", "error": None}

    def tool_page_loading(self, screen_info=None):
        self.executed.append(("page_loading", {}))
        return {"ok": True, "summary": "已等待页面稳定", "error": None}

    def tool_read_current_page(self, mode="extract", chunk_index=None, query=None, top_k=3, screen_info=None):
        self.executed.append(("read_current_page", {"mode": mode}))
        return {
            "ok": True,
            "summary": "已读取当前网页（可能不完整）：Example Domain。链接：https://example.com。内容已写入网页解析记录并进入临时网页上下文。",
            "error": None,
            "quality": "best_effort",
            "url": "https://example.com",
            "page_context": {
                "url": "https://example.com",
                "title": "Example Domain",
                "quality": "best_effort",
                "content": "示例网页正文",
                "chunk_index": 0,
                "total_chunks": 1,
                "source_mode": mode,
                "has_more": False,
            },
            "page_record_path": "imgs/page_extract/page_20260407_000001_001.txt",
        }

    def tool_read_current_document(
        self,
        mode="extract",
        follow_view=False,
        chunk_index=None,
        query=None,
        top_k=3,
        screen_index=None,
        position=None,
        screen_info=None,
    ):
        self.executed.append((
            "read_current_document",
            {
                "mode": mode,
                "follow_view": follow_view,
                "chunk_index": chunk_index,
                "query": query,
                "top_k": top_k,
                "screen_index": screen_index,
                "position": position,
            },
        ))
        result = {
            "ok": True,
            "summary": "已读取当前文档（可能不完整）：Microsoft Word。内容已写入文档解析记录并进入临时文档上下文。 当前块：第 1/3 块。",
            "error": None,
            "document_context": {
                "app_name": "Microsoft Word",
                "content": "示例文档正文",
                "chunk_index": 0,
                "total_chunks": 3,
                "source_mode": mode,
                "has_more": True,
            },
            "document_record_path": "imgs/doc_extract/document_20260407_000001_001.txt",
        }
        if mode != "extract":
            result["summary"] += " 已尝试将文档视图跳到当前块附近。"
            result["view_follow_attempted"] = True
            result["view_followed"] = True
            result["view_follow_message"] = "已尝试将文档视图跳到当前块附近。"
        return result

    def tool_remember(self, content, screen_info=None):
        self.executed.append(("remember", {"content": content}))
        if self._memory_state is not None:
            self._memory_state["content"] = content
        return {"ok": True, "summary": "已记录重要信息", "error": None}

    def tool_hold_modifier_keys(self, keys, screen_info=None):
        for key in keys:
            if key not in self._held_modifier_keys:
                self._held_modifier_keys.append(key)
        self.executed.append(("hold_modifier_keys", {"keys": keys}))
        return {"ok": True, "summary": "已进入修饰键长按状态", "error": None}

    def tool_release_modifier_keys(self, keys=None, screen_info=None):
        if not keys:
            self._held_modifier_keys = []
        else:
            self._held_modifier_keys = [key for key in self._held_modifier_keys if key not in set(keys)]
        self.executed.append(("release_modifier_keys", {"keys": keys or []}))
        return {"ok": True, "summary": "已释放修饰键长按状态", "error": None}

    def get_held_modifier_keys(self):
        return list(self._held_modifier_keys)

    def release_all_held_modifier_keys(self):
        released = list(self._held_modifier_keys)
        self._held_modifier_keys = []
        self.release_all_calls += 1
        return released

    def auto_release_stale_modifier_keys(self, current_step, max_steps, max_seconds):
        notice = self.auto_release_notice
        self.auto_release_notice = None
        if notice:
            self._held_modifier_keys = []
        return notice

    def mark_held_modifier_state_active(self, current_step):
        self.marked_steps.append(current_step)

    def get_last_settle_result(self):
        return self._last_settle_result

    def get_frontmost_app_info(self):
        if not self._frontmost_sequence:
            return {}
        current_index = min(self._frontmost_index, len(self._frontmost_sequence) - 1)
        self._frontmost_index += 1
        current = self._frontmost_sequence[current_index]
        return dict(current) if isinstance(current, dict) else {}

    def activate_app(self, app_info):
        self.activate_calls.append(dict(app_info))
        return self.activate_result

    def clear_page_reader_state(self):
        self.clear_page_reader_state_calls += 1

    def clear_document_reader_state(self):
        self.clear_document_reader_state_calls += 1


class FakeAIClient:
    def __init__(self, responses, stream_chunks=None, metrics_per_call=None, parse_errors_per_call=None):
        self.responses = [_coerce_test_response(response) for response in responses]
        self.stream_chunks = list(stream_chunks or [])
        self.metrics_per_call = list(metrics_per_call or [])
        self.parse_errors_per_call = list(parse_errors_per_call or [])
        self.index = 0
        self.calls = []
        self._last_parse_error = ""

    def clear_memory(self):
        self._last_parse_error = ""
        return None

    def get_last_parse_error(self):
        return self._last_parse_error

    def get_next_action_from_capture(
        self,
        captures,
        user_content,
        should_exit_check=None,
        action_feedback="",
        screen_info=None,
        memory_content="",
        page_context=None,
        page_extraction_notice="",
        document_context=None,
        document_extraction_notice="",
        context_warning_prompt="",
        replan_feedback="",
        process_report_mode="auto",
        process_report_request_prompt="",
        held_modifier_prompt="",
        frontmost_app_prompt="",
        background_jobs_prompt="",
        pending_reports_prompt="",
        on_stream_chunk=None,
    ):
        current_index = min(self.index, len(self.responses) - 1)
        self.index += 1
        if current_index < len(self.parse_errors_per_call):
            self._last_parse_error = self.parse_errors_per_call[current_index] or ""
        else:
            self._last_parse_error = ""
        self.calls.append({
            "action_feedback": action_feedback,
            "memory_content": memory_content,
            "page_context": page_context,
            "page_extraction_notice": page_extraction_notice,
            "document_context": document_context,
            "document_extraction_notice": document_extraction_notice,
            "context_warning_prompt": context_warning_prompt,
            "replan_feedback": replan_feedback,
            "screen_count": len(captures),
            "process_report_mode": process_report_mode,
            "process_report_request_prompt": process_report_request_prompt,
            "held_modifier_prompt": held_modifier_prompt,
            "frontmost_app_prompt": frontmost_app_prompt,
            "background_jobs_prompt": background_jobs_prompt,
            "pending_reports_prompt": pending_reports_prompt,
        })
        if on_stream_chunk and current_index < len(self.stream_chunks):
            for chunk in self.stream_chunks[current_index]:
                on_stream_chunk(chunk)
        metrics = {
            "encode_ms": 1.0,
            "request_prepare_ms": 2.0,
            "model_latency_ms": 3.0,
        }
        if current_index < len(self.metrics_per_call):
            metrics.update(self.metrics_per_call[current_index])
        return self.responses[current_index], metrics


def test_runner_returns_respond_report_without_executing_action():
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([{
        "thinking": "现在已经可以结束并向用户汇报结果。",
        "status": "respond",
        "outcome": "completed",
        "report": "任务完成",
    }])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert runner._automation.executed == []


def test_runner_on_iteration_exposes_respond_report_and_outcome():
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([{
        "thinking": "当前需要向用户说明阻塞情况。",
        "status": "respond",
        "outcome": "needs_user",
        "report": "我需要你先登录。",
    }])
    iterations = []

    result = runner.run("task", max_iterations=1, on_iteration=lambda idx, info: iterations.append((idx, info)))

    assert result == "我需要你先登录。"
    assert iterations[0][1]["status"] == "respond"
    assert iterations[0][1]["thinking"] == "当前需要向用户说明阻塞情况。"
    assert iterations[0][1]["outcome"] == "needs_user"
    assert iterations[0][1]["report"] == ""
    assert iterations[0][1]["type_information"] == "我需要你先登录。"


def test_runner_on_iteration_includes_round_and_task_token_usage():
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient(
        [{
            "thinking": "现在已经可以结束并向用户汇报结果。",
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        }],
        metrics_per_call=[{
            "prompt_tokens": 12,
            "completion_tokens": 5,
            "total_tokens": 17,
            "token_usage_available": True,
        }],
    )
    iterations = []

    result = runner.run("task", max_iterations=1, on_iteration=lambda idx, info: iterations.append((idx, info)))

    assert result == "任务完成"
    info = iterations[0][1]
    assert info["prompt_tokens"] == 12
    assert info["completion_tokens"] == 5
    assert info["total_tokens"] == 17
    assert info["task_prompt_tokens"] == 12
    assert info["task_completion_tokens"] == 5
    assert info["task_total_tokens"] == 17
    assert info["task_token_usage_complete"] is True
    assert info["model_request_count"] == 1


def test_runner_feeds_parse_validation_error_back_to_next_round():
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient(
        [
            None,
            {
                "thinking": "需要拆分批次后再执行。",
                "status": "respond",
                "outcome": "completed",
                "report": "我会按每批最多 20 个来继续处理。",
            },
        ],
        parse_errors_per_call=["单次最多删除 20 个条目", ""],
    )

    result = runner.run("task", max_iterations=2)

    assert result == "我会按每批最多 20 个来继续处理。"
    assert "单次最多删除 20 个条目" in runner._ai_client.calls[1]["action_feedback"]
    assert "split them into multiple manage_files calls with at most 20 items per call" in runner._ai_client.calls[1]["action_feedback"]


def test_runner_prints_iteration_and_task_token_usage_summary(capsys):
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient(
        [{
            "thinking": "现在已经可以结束并向用户汇报结果。",
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        }],
        metrics_per_call=[{
            "prompt_tokens": 20,
            "completion_tokens": 7,
            "total_tokens": 27,
            "token_usage_available": True,
        }],
    )

    result = runner.run("task", max_iterations=1)

    assert result == "任务完成"
    captured = capsys.readouterr().out
    assert "[第 1 轮 Token] 输入 20 | 输出 7 | 合计 27 | 累计 27" in captured
    assert "[任务 Token 汇总] 轮数 1 | 输入 20 | 输出 7 | 合计 27" in captured


def test_runner_auto_mode_requests_process_report_on_first_step():
    config = Config()
    config.set("execution_config.process_report_mode", "auto")
    config.set("execution_config.process_report_interval_steps", 3)
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "先点击",
            "report": "我先开始执行。",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 200],
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert runner._ai_client.calls[0]["process_report_mode"] == "auto"
    assert "A brief process report is required for this turn." in runner._ai_client.calls[0]["process_report_request_prompt"]
    assert "By default, do not output a report" in runner._ai_client.calls[1]["process_report_request_prompt"]


def test_runner_auto_mode_repeats_request_until_process_report_is_provided():
    config = Config()
    config.set("execution_config.process_report_mode", "auto")
    config.set("execution_config.process_report_interval_steps", 3)
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)], [make_bundle(value=2)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "先点击",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 200],
                },
            },
        },
        {
            "status": "tool_call",
            "thinking": "继续点击",
            "report": "我还在尝试点击这个区域。",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [150, 250],
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])

    result = runner.run("task", max_iterations=3)

    assert result == "任务完成"
    assert "A brief process report is required for this turn." in runner._ai_client.calls[0]["process_report_request_prompt"]
    assert "A brief process report is required for this turn." in runner._ai_client.calls[1]["process_report_request_prompt"]


def test_runner_launch_app_app_launcher_fallback_is_injected_into_next_feedback():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._automation.tool_launch_app = lambda app_name, screen_info=None: {
        "ok": False,
        "summary": "启动应用失败",
        "error": "系统级启动未找到该应用。请调用 open_app_launcher 打开启动台，并在其中搜索“备忘录”尝试启动。",
        "fallback": {
            "type": "app_launcher_search",
            "app_name": "备忘录",
        },
    }
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "先尝试启动备忘录",
            "tool": {
                "name": "launch_app",
                "args": {
                    "app_name": "备忘录",
                },
            },
        },
        {
            "status": "respond",
            "outcome": "needs_user",
            "report": "测试结束",
        },
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "测试结束"
    assert "launch_app did not find the app" in runner._ai_client.calls[1]["action_feedback"]
    assert "open_app_launcher" in runner._ai_client.calls[1]["action_feedback"]
    assert "search for \"备忘录\"" in runner._ai_client.calls[1]["action_feedback"]
    assert "备忘录" in runner._ai_client.calls[1]["action_feedback"]


def test_runner_auto_mode_requests_again_after_three_steps_since_last_report():
    config = Config()
    config.set("execution_config.process_report_mode", "auto")
    config.set("execution_config.process_report_interval_steps", 3)
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([
        [make_bundle(value=0)],
        [make_bundle(value=1)],
        [make_bundle(value=2)],
        [make_bundle(value=3)],
        [make_bundle(value=4)],
        [make_bundle(value=5)],
    ])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "第一步",
            "report": "我先开始操作。",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 100],
                },
            },
        },
        {
            "status": "tool_call",
            "thinking": "第二步",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [120, 120],
                },
            },
        },
        {
            "status": "tool_call",
            "thinking": "第三步",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [140, 140],
                },
            },
        },
        {
            "status": "tool_call",
            "thinking": "第四步",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [160, 160],
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])

    result = runner.run("task", max_iterations=5)

    assert result == "任务完成"
    assert "A brief process report is required for this turn." in runner._ai_client.calls[0]["process_report_request_prompt"]
    assert "By default, do not output a report" in runner._ai_client.calls[1]["process_report_request_prompt"]
    assert "By default, do not output a report" in runner._ai_client.calls[2]["process_report_request_prompt"]
    assert "By default, do not output a report" in runner._ai_client.calls[3]["process_report_request_prompt"]
    assert "A brief process report is required for this turn." in runner._ai_client.calls[4]["process_report_request_prompt"]


def test_runner_every_step_mode_requests_report_every_round():
    config = Config()
    config.set("execution_config.process_report_mode", "every_step")
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)], [make_bundle(value=2)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "第一步",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 100],
                },
            },
        },
        {
            "status": "tool_call",
            "thinking": "第二步",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [200, 200],
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])

    result = runner.run("task", max_iterations=3)

    assert result == "任务完成"
    assert all(
        "A brief process report is required for this turn." in call["process_report_request_prompt"]
        for call in runner._ai_client.calls
    )


def test_runner_off_mode_skips_regular_report_requests():
    config = Config()
    config.set("execution_config.process_report_mode", "off")
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "先点击",
            "report": "我先打开这个入口。",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 100],
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])
    iterations = []

    result = runner.run("task", max_iterations=2, on_iteration=lambda idx, info: iterations.append((idx, info)))

    assert result == "任务完成"
    assert runner._ai_client.calls[0]["process_report_mode"] == "off"
    assert "Process reporting is currently disabled" in runner._ai_client.calls[0]["process_report_request_prompt"]
    assert iterations[0][1]["report"] == "我先打开这个入口。"
    assert iterations[0][1]["report_requested"] is False
    assert iterations[0][1]["report_request_reason"] == "off"


def test_runner_invalid_report_mode_falls_back_to_auto():
    config = Config()
    config.set("execution_config.process_report_mode", "unexpected_mode")
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "先点击",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 100],
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert runner._ai_client.calls[0]["process_report_mode"] == "auto"
    assert "A brief process report is required for this turn." in runner._ai_client.calls[0]["process_report_request_prompt"]


def test_runner_loop_detection_requests_report_even_in_off_mode():
    config = Config()
    config.set("execution_config.process_report_mode", "off")
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    config.set("execution_config.stalled_replan_threshold", 10)
    config.set("execution_config.stalled_difficult_threshold", 10)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    repeated_bundle = [make_bundle(value=9)]
    runner._screenshot = FakeScreenshot([repeated_bundle] * 4)
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "第一次点击",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 200],
                },
            },
        },
        {
            "status": "tool_call",
            "thinking": "第二次点击",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 200],
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])

    result = runner.run("task", max_iterations=3)

    assert result == "任务完成"
    assert runner._ai_client.calls[2]["process_report_mode"] == "off"
    assert "repeating similar operations" in runner._ai_client.calls[2]["process_report_request_prompt"]


def test_runner_replans_and_stops_after_repeated_stalls():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    config.set("execution_config.stalled_replan_threshold", 2)
    config.set("execution_config.stalled_difficult_threshold", 4)
    config.set("execution_config.action_signature_tolerance_px", 15)

    repeated_bundle = [make_bundle(value=50)]
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([repeated_bundle] * 6)
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([{
        "status": "tool_call",
        "thinking": "continue",
        "tool": {
            "name": "click",
            "args": {
                "screen_index": 0,
                "position": [100, 200],
            },
        },
    }] * 6)

    result = runner.run("task", max_iterations=6)

    assert "difficult" in result
    assert len(runner._automation.executed) == 2
    assert len(runner._ai_client.calls) >= 4
    assert any(call["replan_feedback"] for call in runner._ai_client.calls[2:])


def test_runner_forwards_model_stream_chunks():
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient(
        [{
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        }],
        stream_chunks=[["part-1", "part-2"]],
    )
    streamed = []

    result = runner.run(
        "task",
        max_iterations=1,
        on_model_stream=lambda iteration, chunk: streamed.append((iteration, chunk)),
    )

    assert result == "任务完成"
    assert streamed == [(0, "part-1"), (0, "part-2")]


def test_runner_hides_windows_before_capture_and_restores_afterwards():
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    events = []

    class OrderedScreenshot(FakeScreenshot):
        def capture_all_screens_bundle(self):
            events.append("capture")
            return super().capture_all_screens_bundle()

    runner._screenshot = OrderedScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([{
        "status": "respond",
        "outcome": "completed",
        "report": "任务完成",
    }])

    result = runner.run(
        "task",
        max_iterations=1,
        on_transparent_enter=lambda: events.append("hide"),
        on_transparent_exit=lambda: events.append("show"),
    )

    assert result == "任务完成"
    assert events == ["hide", "capture", "show"]


def test_runner_on_iteration_contains_new_and_legacy_fields():
    config = Config()
    config.set("execution_config.process_report_mode", "auto")
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "需要先输入文本",
            "tool": {
                "name": "input_text",
                "args": {
                    "screen_index": 1,
                    "position": [300, 200],
                    "text": "张三",
                    "replace": True,
                    "submit": True,
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])
    iterations = []

    result = runner.run("task", max_iterations=2, on_iteration=lambda idx, info: iterations.append((idx, info)))

    assert result == "任务完成"
    assert iterations[0][1]["status"] == "input_text"
    assert iterations[0][1]["tool_name"] == "input_text"
    assert iterations[0][1]["tool_args"]["text"] == "张三"
    assert iterations[0][1]["action"] == "input_text"
    assert iterations[0][1]["screen_index"] == 1
    assert iterations[0][1]["type_information"] == "张三"
    assert iterations[0][1]["report"] == ""
    assert iterations[0][1]["report_mode"] == "auto"
    assert iterations[0][1]["report_requested"] is True
    assert iterations[0][1]["report_request_reason"] == "mode"
    assert iterations[0][1]["loop_report_requested"] is False


def test_build_user_content_formats_task_with_timestamp(monkeypatch):
    fixed_time = time.struct_time((2026, 4, 9, 10, 11, 0, 3, 99, -1))

    monkeypatch.setattr("baodou_ai.core.runner.time.localtime", lambda *_args: fixed_time)
    monkeypatch.setattr(
        "baodou_ai.core.runner.time.strftime",
        lambda _fmt, _value: "2026-04-09 10:11",
    )

    content = ControlLoopRunner.build_user_content("打开微信", now=123.0)

    assert content == "Current time: 2026-04-09 10:11\nUser task: 打开微信"


def test_runner_click_feedback_guides_agent_to_use_input_text():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "先点击",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 200],
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert "input_text" in runner._ai_client.calls[1]["action_feedback"]


def test_runner_on_iteration_maps_input_text_without_position_to_legacy_input_text():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "直接输入",
            "tool": {
                "name": "input_text",
                "args": {
                    "text": "hello",
                    "replace": False,
                    "submit": False,
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])
    iterations = []

    result = runner.run("task", max_iterations=2, on_iteration=lambda idx, info: iterations.append((idx, info)))

    assert result == "任务完成"
    assert iterations[0][1]["tool_name"] == "input_text"
    assert iterations[0][1]["action"] == "input_text"
    assert iterations[0][1]["type_information"] == "hello"


def test_runner_on_iteration_maps_positioned_input_text_to_legacy_input_text():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "先点后输",
            "tool": {
                "name": "input_text",
                "args": {
                    "screen_index": 1,
                    "position": [250, 350],
                    "text": "hello",
                    "replace": False,
                    "submit": False,
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])
    iterations = []

    result = runner.run("task", max_iterations=2, on_iteration=lambda idx, info: iterations.append((idx, info)))

    assert result == "任务完成"
    assert iterations[0][1]["tool_name"] == "input_text"
    assert iterations[0][1]["action"] == "input_text"
    assert iterations[0][1]["coordinates"] == [250.0, 350.0]
    assert iterations[0][1]["screen_index"] == 1


def test_runner_remember_status_writes_memory_and_continues():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    memory_state = {"content": ""}
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: memory_state["content"]
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation(memory_state)
    runner._ai_client = FakeAIClient([
        {
            "status": "remember",
            "content": "任务内容",
            "report": "我先记住任务。",
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])
    iterations = []

    result = runner.run("task", max_iterations=2, on_iteration=lambda idx, info: iterations.append((idx, info)))

    assert result == "任务完成"
    assert runner._automation.executed[0] == ("remember", {"content": "任务内容"})
    assert runner._automation.executed[1] == ("page_loading", {})
    assert runner._ai_client.calls[1]["memory_content"] == "任务内容"
    assert iterations[0][1]["status"] == "page_loading"
    assert iterations[0][1]["content"] == "任务内容"
    assert iterations[0][1]["remember_content"] == "任务内容"
    assert iterations[0][1]["remember_written"] is True
    assert iterations[0][1]["report"] == "我先记住任务。"
    assert iterations[0][1]["action"] == "page_loading"


def test_runner_memory_content_is_cached_between_iterations():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    read_calls = []

    def fake_read_memory():
        read_calls.append("read")
        return "缓存记忆"

    runner._clear_memory_files = lambda: None
    runner._read_memory_content = fake_read_memory
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "thinking": "先点击一次。",
            "click": {
                "screen_index": 0,
                "position": [100, 200],
            },
        },
        {
            "thinking": "现在可以结束。",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert read_calls == ["read"]
    assert runner._ai_client.calls[0]["memory_content"] == "缓存记忆"
    assert runner._ai_client.calls[1]["memory_content"] == "缓存记忆"


def test_runner_remember_updates_memory_cache_without_repeated_disk_read():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    read_calls = []

    def fake_read_memory():
        read_calls.append("read")
        return ""

    runner._clear_memory_files = lambda: None
    runner._read_memory_content = fake_read_memory
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "remember",
            "content": "任务内容",
            "report": "我先记住任务。",
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert read_calls == ["read"]
    assert runner._ai_client.calls[1]["memory_content"] == "任务内容"


def test_runner_remember_failure_does_not_block_main_branch():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._automation.tool_remember = lambda content, screen_info=None: {
        "ok": False,
        "summary": "记忆写入失败",
        "error": "磁盘不可写",
    }
    runner._ai_client = FakeAIClient([
        {
            "thinking": "先记住任务，再点击按钮。",
            "remember": {
                "content": "任务内容",
            },
            "click": {
                "screen_index": 0,
                "position": [100, 200],
            },
        },
        {
            "thinking": "现在已经可以结束。",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])
    iterations = []

    result = runner.run("task", max_iterations=2, on_iteration=lambda idx, info: iterations.append((idx, info)))

    assert result == "任务完成"
    assert runner._automation.executed[0] == ("click", {"screen_index": 0, "position": [100.0, 200.0]})
    assert iterations[0][1]["status"] == "click"
    assert iterations[0][1]["remember_content"] == "任务内容"
    assert iterations[0][1]["remember_written"] is False
    assert "Remember result:" in runner._ai_client.calls[1]["action_feedback"]
    assert "任务内容" not in runner._ai_client.calls[1]["action_feedback"]
    assert "Memory write error: 磁盘不可写" in runner._ai_client.calls[1]["action_feedback"]


def test_runner_respond_with_remember_writes_memory_before_returning():
    config = Config()
    runner = ControlLoopRunner(config)
    memory_state = {"content": ""}
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: memory_state["content"]
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation(memory_state)
    runner._ai_client = FakeAIClient([
        {
            "thinking": "现在可以结束，并顺手记住最终链接。",
            "remember": {
                "content": "最终链接: https://example.com",
            },
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])
    iterations = []

    result = runner.run("task", max_iterations=1, on_iteration=lambda idx, info: iterations.append((idx, info)))

    assert result == "任务完成"
    assert memory_state["content"] == "最终链接: https://example.com"
    assert runner._automation.executed[0] == ("remember", {"content": "最终链接: https://example.com"})
    assert iterations[0][1]["status"] == "respond"
    assert iterations[0][1]["remember_content"] == "最终链接: https://example.com"
    assert iterations[0][1]["remember_written"] is True


def test_runner_changed_pixels_ratio_reuses_cached_gray_frames(monkeypatch):
    config = Config()
    runner = ControlLoopRunner(config)
    first = make_bundle(value=0)
    second = make_bundle(value=1)
    third = make_bundle(value=2)
    original_imdecode = cv2.imdecode
    decode_calls = []

    def counting_imdecode(buffer, flags):
        decode_calls.append(flags)
        return original_imdecode(buffer, flags)

    monkeypatch.setattr("baodou_ai.core.runner.cv2.imdecode", counting_imdecode)

    first_ratio = runner._calculate_changed_pixels_ratio([first], [second])
    second_ratio = runner._calculate_changed_pixels_ratio([second], [third])

    assert first_ratio > 0.0
    assert second_ratio > 0.0
    assert len(decode_calls) == 3
    assert set(runner._gray_frame_cache) == {second.frame_hash, third.frame_hash}


def test_runner_passes_page_context_after_successful_read_current_page():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "thinking": "先快速读取当前网页。",
            "read_current_page": {},
        },
        {
            "thinking": "现在已经可以结束。",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert runner._automation.executed[0][0] == "read_current_page"
    page_ctx = runner._ai_client.calls[1]["page_context"]
    assert page_ctx["url"] == "https://example.com"
    assert page_ctx["title"] == "Example Domain"
    assert page_ctx["quality"] == "best_effort"
    assert page_ctx["content"] == "示例网页正文"
    assert runner._ai_client.calls[1]["page_extraction_notice"] == ""


def test_runner_appends_page_content_to_action_feedback_after_successful_read_current_page():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "thinking": "先快速读取当前网页。",
            "read_current_page": {},
        },
        {
            "thinking": "现在已经可以结束。",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    feedback = runner._ai_client.calls[1]["action_feedback"]
    assert "--- Page Content ---" in feedback
    assert "示例网页正文" in feedback
    assert "--- End of Page Content ---" in feedback
    assert 'call read_current_page(mode="next")' not in feedback


def test_runner_page_feedback_prompts_next_when_more_chunks_available():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._automation.tool_read_current_page = lambda mode="extract", chunk_index=None, query=None, top_k=3, screen_info=None: {
        "ok": True,
        "summary": "已读取当前网页第 1/2 块：Example Domain。链接：https://example.com。当前块已进入临时网页上下文。",
        "error": None,
        "quality": "best_effort",
        "url": "https://example.com",
        "page_context": {
            "url": "https://example.com",
            "title": "Example Domain",
            "quality": "best_effort",
            "content": "示例网页正文",
            "chunk_index": 0,
            "total_chunks": 2,
            "source_mode": mode,
            "has_more": True,
        },
    }
    runner._ai_client = FakeAIClient([
        {"thinking": "先快速读取当前网页。", "read_current_page": {}},
        {"thinking": "现在已经可以结束。", "respond": {"outcome": "completed", "report": "任务完成"}},
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    feedback = runner._ai_client.calls[1]["action_feedback"]
    assert 'call read_current_page(mode="next") to continue' in feedback
    assert 'call read_current_page(mode="search", query="...")' in feedback
    assert "Chunk 1/2" in feedback


def test_runner_clears_previous_page_context_and_sets_notice_after_read_current_page_failure():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)], [make_bundle(value=2)]])
    runner._automation = FakeAutomation()
    read_results = iter([
        {
            "ok": True,
            "summary": "已读取当前网页（可能不完整）：Example Domain。链接：https://example.com。内容已写入网页解析记录并进入临时网页上下文。",
            "error": None,
            "quality": "best_effort",
            "url": "https://example.com",
            "page_context": {
                "url": "https://example.com",
                "title": "Example Domain",
                "quality": "best_effort",
                "content": "示例网页正文",
            },
        },
        {
            "ok": False,
            "summary": "读取当前网页失败",
            "error": "read_current_page 仅支持在浏览器前台页面使用，当前前台应用为：Finder。",
            "fallback": {
                "type": "read_current_page_not_browser",
                "app_name": "Finder",
            },
        },
    ])
    runner._automation.tool_read_current_page = lambda mode="extract", chunk_index=None, query=None, top_k=3, screen_info=None: next(read_results)
    runner._ai_client = FakeAIClient([
        {
            "thinking": "先读取当前网页。",
            "read_current_page": {},
        },
        {
            "thinking": "再尝试读取当前网页。",
            "read_current_page": {},
        },
        {
            "thinking": "现在已经可以结束。",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])

    result = runner.run("task", max_iterations=3)

    assert result == "任务完成"
    page_ctx_1 = runner._ai_client.calls[1]["page_context"]
    assert page_ctx_1["url"] == "https://example.com"
    assert page_ctx_1["title"] == "Example Domain"
    assert page_ctx_1["quality"] == "best_effort"
    assert page_ctx_1["content"] == "示例网页正文"
    assert runner._ai_client.calls[1]["page_extraction_notice"] == ""
    assert runner._ai_client.calls[2]["page_context"] is None
    assert "The current webpage extraction failed; the previous webpage extraction content has been invalidated and cleared." in runner._ai_client.calls[2]["page_extraction_notice"]
    assert "has been invalidated and cleared" in runner._ai_client.calls[2]["page_extraction_notice"]
    assert "strictly by analyzing the screenshot" in runner._ai_client.calls[2]["page_extraction_notice"]


def test_runner_preserves_page_context_when_read_current_page_reaches_end():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)], [make_bundle(value=2)]])
    runner._automation = FakeAutomation()
    read_results = iter([
        {
            "ok": True,
            "summary": "已读取当前网页第 2/2 块：Example Domain。链接：https://example.com。当前块已进入临时网页上下文。",
            "error": None,
            "quality": "best_effort",
            "url": "https://example.com",
            "page_context": {
                "url": "https://example.com",
                "title": "Example Domain",
                "quality": "best_effort",
                "content": "第二块网页正文",
                "chunk_index": 1,
                "total_chunks": 2,
                "source_mode": "next",
                "has_more": False,
            },
        },
        {
            "ok": False,
            "summary": "读取当前网页失败",
            "error": "当前已经是最后一块，没有更多分块。",
            "fallback": {
                "type": "read_current_page_no_more_chunks",
            },
        },
    ])
    runner._automation.tool_read_current_page = (
        lambda mode="extract", chunk_index=None, query=None, top_k=3, screen_info=None: next(read_results)
    )
    runner._ai_client = FakeAIClient([
        {
            "thinking": "先读取当前网页最后一块。",
            "read_current_page": {
                "mode": "next",
            },
        },
        {
            "thinking": "再尝试读取下一块。",
            "read_current_page": {
                "mode": "next",
            },
        },
        {
            "thinking": "现在已经可以结束。",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])

    result = runner.run("task", max_iterations=3)

    assert result == "任务完成"
    assert runner._ai_client.calls[1]["page_context"] == {
        "url": "https://example.com",
        "title": "Example Domain",
        "quality": "best_effort",
        "content": "第二块网页正文",
        "chunk_index": 1,
        "total_chunks": 2,
        "source_mode": "next",
        "has_more": False,
    }
    assert runner._ai_client.calls[2]["page_context"] == {
        "url": "https://example.com",
        "title": "Example Domain",
        "quality": "best_effort",
        "content": "第二块网页正文",
        "chunk_index": 1,
        "total_chunks": 2,
        "source_mode": "next",
        "has_more": False,
    }
    assert "You have reached the end of the webpage; there are no more chunks." in runner._ai_client.calls[2]["page_extraction_notice"]


def test_runner_warns_and_clears_page_context_when_prompt_tokens_reach_threshold():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    config.set("execution_config.context_token_limit", 1000)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)], [make_bundle(value=2)], [make_bundle(value=3)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient(
        [
            {"thinking": "先读取当前网页。", "read_current_page": {}},
            {"thinking": "继续观察。", "page_loading": {}},
            {
                "thinking": "收到预警后先记住网页重点。",
                "remember": {"content": "网页重点摘要"},
                "respond": {"outcome": "completed", "report": "任务完成"},
            },
        ],
        metrics_per_call=[
            {"token_usage_available": True, "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            {"token_usage_available": True, "prompt_tokens": 850, "completion_tokens": 20, "total_tokens": 870},
            {"token_usage_available": True, "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        ],
    )

    result = runner.run("task", max_iterations=3)

    assert result == "任务完成"
    assert "page/document content will be cleared in the next turn" in runner._ai_client.calls[2]["context_warning_prompt"]
    assert runner._ai_client.calls[2]["page_context"] is None
    assert runner._automation.clear_page_reader_state_calls == 1


def test_runner_warns_and_clears_page_and_document_context_when_prompt_tokens_reach_threshold():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    config.set("execution_config.context_token_limit", 1000)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([
        [make_bundle()],
        [make_bundle(value=1)],
        [make_bundle(value=2)],
        [make_bundle(value=3)],
    ])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient(
        [
            {"thinking": "先读取当前网页。", "read_current_page": {}},
            {"thinking": "再读取当前文档。", "read_current_document": {}},
            {"thinking": "继续观察。", "page_loading": {}},
            {
                "thinking": "收到预警后结束。",
                "respond": {"outcome": "completed", "report": "任务完成"},
            },
        ],
        metrics_per_call=[
            {"token_usage_available": True, "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            {"token_usage_available": True, "prompt_tokens": 110, "completion_tokens": 20, "total_tokens": 130},
            {"token_usage_available": True, "prompt_tokens": 850, "completion_tokens": 20, "total_tokens": 870},
            {"token_usage_available": True, "prompt_tokens": 120, "completion_tokens": 20, "total_tokens": 140},
        ],
    )

    result = runner.run("task", max_iterations=4)

    assert result == "任务完成"
    assert "page/document content will be cleared in the next turn" in runner._ai_client.calls[3]["context_warning_prompt"]
    assert runner._ai_client.calls[3]["page_context"] is None
    assert runner._ai_client.calls[3]["document_context"] is None
    assert runner._ai_client.calls[3]["page_extraction_notice"] == ""
    assert runner._ai_client.calls[3]["document_extraction_notice"] == ""
    assert runner._automation.clear_page_reader_state_calls == 1
    assert runner._automation.clear_document_reader_state_calls == 1


def test_runner_passes_document_context_after_successful_read_current_document():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "thinking": "先快速读取当前文档。",
            "read_current_document": {},
        },
        {
            "thinking": "现在已经可以结束。",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert runner._automation.executed[0][0] == "read_current_document"
    assert runner._ai_client.calls[1]["document_context"] == {
        "app_name": "Microsoft Word",
        "content": "示例文档正文",
        "chunk_index": 0,
        "total_chunks": 3,
        "source_mode": "extract",
        "has_more": True,
    }
    assert runner._ai_client.calls[1]["document_extraction_notice"] == ""


def test_runner_clears_previous_document_context_and_sets_notice_after_read_current_document_failure():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)], [make_bundle(value=2)]])
    runner._automation = FakeAutomation()
    read_results = iter([
        {
            "ok": True,
            "summary": "已读取当前文档（可能不完整）：Microsoft Word。内容已写入文档解析记录并进入临时文档上下文。 当前块：第 1/2 块。",
            "error": None,
            "document_context": {
                "app_name": "Microsoft Word",
                "content": "示例文档正文",
                "chunk_index": 0,
                "total_chunks": 2,
                "source_mode": "extract",
                "has_more": True,
            },
        },
        {
            "ok": False,
            "summary": "读取当前文档失败",
            "error": "复制结果疑似来自工具栏、字号栏、样式栏或其他非正文区域。",
            "fallback": {
                "type": "read_current_document_focus_retry",
                "app_name": "Microsoft Word",
            },
        },
    ])
    runner._automation.tool_read_current_document = (
        lambda mode="extract", follow_view=False, chunk_index=None, screen_index=None, position=None, screen_info=None: next(read_results)
    )
    runner._ai_client = FakeAIClient([
        {
            "thinking": "先读取当前文档。",
            "read_current_document": {},
        },
        {
            "thinking": "再尝试读取当前文档。",
            "read_current_document": {},
        },
        {
            "thinking": "现在已经可以结束。",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])

    result = runner.run("task", max_iterations=3)

    assert result == "任务完成"
    assert runner._ai_client.calls[1]["document_context"] == {
        "app_name": "Microsoft Word",
        "content": "示例文档正文",
        "chunk_index": 0,
        "total_chunks": 2,
        "source_mode": "extract",
        "has_more": True,
    }
    assert runner._ai_client.calls[1]["document_extraction_notice"] == ""
    assert runner._ai_client.calls[2]["document_context"] is None
    assert "The current document extraction failed; the previous document extraction content has been invalidated and cleared." in runner._ai_client.calls[2]["document_extraction_notice"]
    assert "provide the body area coordinates" in runner._ai_client.calls[2]["document_extraction_notice"]


def test_runner_sets_notice_when_read_current_document_in_ide_requires_position():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._automation.tool_read_current_document = (
        lambda mode="extract", follow_view=False, chunk_index=None, screen_index=None, position=None, screen_info=None: {
            "ok": False,
            "summary": "读取当前文档失败",
            "error": (
                "当前前台应用是编程 IDE。调用 read_current_document 时必须同时提供 "
                "screen_index 和 position，用于先点击代码或文本正文区域；本次未执行任何提取操作。"
            ),
            "fallback": {
                "type": "read_current_document_ide_requires_position",
                "app_name": "Trae CN",
            },
        }
    )
    runner._ai_client = FakeAIClient([
        {
            "thinking": "先尝试读取当前 IDE 正文。",
            "read_current_document": {},
        },
        {
            "thinking": "现在已经可以结束。",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert runner._ai_client.calls[1]["document_context"] is None
    assert "The current frontmost app is a programming IDE / editor." in runner._ai_client.calls[1]["document_extraction_notice"]
    assert "screen_index and position" in runner._ai_client.calls[1]["document_extraction_notice"]
    assert "no extraction operation was performed" in runner._ai_client.calls[1]["document_extraction_notice"]


def test_runner_preserves_document_context_when_read_current_document_reaches_end():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)], [make_bundle(value=2)]])
    runner._automation = FakeAutomation()
    read_results = iter([
        {
            "ok": True,
            "summary": "已读取当前文档（可能不完整）：Microsoft Word。内容已写入文档解析记录并进入临时文档上下文。 当前块：第 2/2 块。 本次未能完成文档视觉跳转，仅更新了当前块文本上下文。",
            "error": None,
            "document_context": {
                "app_name": "Microsoft Word",
                "content": "第二块正文",
                "chunk_index": 1,
                "total_chunks": 2,
                "source_mode": "next",
                "has_more": False,
            },
            "view_follow_attempted": True,
            "view_followed": False,
            "view_follow_message": "本次未能完成文档视觉跳转，仅更新了当前块文本上下文。",
        },
        {
            "ok": False,
            "summary": "读取当前文档失败",
            "error": "当前已经是最后一块，没有更多分块。",
            "fallback": {
                "type": "read_current_document_no_more_chunks",
                "app_name": "Microsoft Word",
            },
        },
    ])
    runner._automation.tool_read_current_document = (
        lambda mode="extract", follow_view=False, chunk_index=None, screen_index=None, position=None, screen_info=None: next(read_results)
    )
    runner._ai_client = FakeAIClient([
        {
            "thinking": "继续读取当前文档的下一块。",
            "read_current_document": {
                "mode": "next",
            },
        },
        {
            "thinking": "再尝试读取下一块。",
            "read_current_document": {
                "mode": "next",
            },
        },
        {
            "thinking": "现在已经可以结束。",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])

    result = runner.run("task", max_iterations=3)

    assert result == "任务完成"
    assert runner._ai_client.calls[1]["document_context"] == {
        "app_name": "Microsoft Word",
        "content": "第二块正文",
        "chunk_index": 1,
        "total_chunks": 2,
        "source_mode": "next",
        "has_more": False,
    }
    assert "本次未能完成文档视觉跳转，仅更新了当前块文本上下文。" in runner._ai_client.calls[1]["action_feedback"]
    assert runner._ai_client.calls[2]["document_context"] == {
        "app_name": "Microsoft Word",
        "content": "第二块正文",
        "chunk_index": 1,
        "total_chunks": 2,
        "source_mode": "next",
        "has_more": False,
    }
    assert "You have reached the end of the document; there are no more chunks." in runner._ai_client.calls[2]["document_extraction_notice"]


def test_runner_sets_notice_when_read_current_document_chunk_requires_extract_first():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._automation.tool_read_current_document = (
        lambda mode="extract", follow_view=False, chunk_index=None, screen_index=None, position=None, screen_info=None: {
            "ok": False,
            "summary": "读取当前文档失败",
            "error": '当前任务还没有成功提取文档全文，请先调用 read_current_document(mode="extract")。',
            "fallback": {
                "type": "read_current_document_need_extract_first",
                "app_name": "未知应用",
            },
        }
    )
    runner._ai_client = FakeAIClient([
        {
            "thinking": "先尝试读取第 1 块。",
            "read_current_document": {
                "mode": "chunk",
                "chunk_index": 0,
            },
        },
        {
            "thinking": "现在已经可以结束。",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert runner._ai_client.calls[1]["document_context"] is None
    assert "There is no full document text available for chunked reading for the current task." in runner._ai_client.calls[1]["document_extraction_notice"]


def test_runner_sets_notice_when_read_current_document_search_has_no_results():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._automation.tool_read_current_document = (
        lambda mode="extract", follow_view=False, chunk_index=None, query=None, top_k=3, screen_index=None, position=None, screen_info=None: {
            "ok": False,
            "summary": "读取当前文档失败",
            "error": '未在当前文档中找到与“退款”相关的内容。',
            "fallback": {
                "type": "read_current_document_search_no_results",
                "app_name": "Microsoft Word",
            },
        }
    )
    runner._ai_client = FakeAIClient([
        {
            "thinking": "先搜索退款相关内容。",
            "read_current_document": {
                "mode": "search",
                "query": "退款",
                "top_k": 3,
            },
        },
        {
            "thinking": "现在已经可以结束。",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    ])

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert runner._ai_client.calls[1]["document_context"] is None
    assert "The current document search found no relevant results" in runner._ai_client.calls[1]["document_extraction_notice"]
    assert "different keywords" in runner._ai_client.calls[1]["document_extraction_notice"]


def test_runner_page_loading_status_waits_and_continues():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "page_loading",
            "report": "我正在等待页面加载完成。",
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])
    iterations = []

    result = runner.run("task", max_iterations=2, on_iteration=lambda idx, info: iterations.append((idx, info)))

    assert result == "任务完成"
    assert runner._automation.executed[0] == ("page_loading", {})
    assert iterations[0][1]["status"] == "page_loading"
    assert iterations[0][1]["report"] == "我正在等待页面加载完成。"
    assert iterations[0][1]["action"] == "page_loading"


def test_runner_page_loading_long_wait_skips_short_wait_tool(monkeypatch):
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "thinking": "安装还在继续，先长等待。",
            "page_loading": {
                "mode": "long_wait",
                "wait_seconds": 4,
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])
    waited = []
    runner._wait_for_long_page_loading = lambda wait_seconds, should_stop: waited.append(wait_seconds) or True
    iterations = []

    result = runner.run("task", max_iterations=2, on_iteration=lambda idx, info: iterations.append((idx, info)))

    assert result == "任务完成"
    assert waited == [4]
    assert runner._automation.executed == []
    assert iterations[0][1]["status"] == "page_loading"
    assert iterations[0][1]["tool_result"]["mode"] == "long_wait"
    assert iterations[0][1]["tool_result"]["wait_seconds"] == 4


def test_runner_page_loading_long_wait_defaults_wait_seconds_to_three():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "thinking": "安装还在继续，先长等待。",
            "page_loading": {
                "mode": "long_wait",
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])
    waited = []
    runner._wait_for_long_page_loading = lambda wait_seconds, should_stop: waited.append(wait_seconds) or True

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert waited == [3]


def test_wait_for_long_page_loading_stops_when_requested(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)

    stopped = ControlLoopRunner._wait_for_long_page_loading(
        wait_seconds=3,
        should_stop=lambda: True,
    )

    assert stopped is False


def test_runner_waits_before_next_capture_after_successful_tool_call(monkeypatch):
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 250)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    events = []

    class OrderedScreenshot(FakeScreenshot):
        def capture_all_screens_bundle(self):
            events.append(f"capture-{self.index}")
            return super().capture_all_screens_bundle()

    class OrderedAutomation(FakeAutomation):
        def tool_click(self, screen_index, position, screen_info=None):
            events.append("tool")
            return super().tool_click(screen_index, position, screen_info=screen_info)

    runner._screenshot = OrderedScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = OrderedAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "先点击",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 200],
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])
    runner._wait_before_next_capture = lambda should_stop: events.append("delay") or True

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert events == ["capture-0", "tool", "delay", "capture-1"]


def test_runner_replan_does_not_wait_before_next_capture(monkeypatch):
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 250)
    config.set("execution_config.stalled_replan_threshold", 1)
    config.set("execution_config.stalled_difficult_threshold", 3)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "重复点击",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 200],
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])

    delay_calls = []
    runner._is_stalled = lambda **kwargs: True
    runner._wait_before_next_capture = lambda should_stop: delay_calls.append("delay") or True

    result = runner.run("task", max_iterations=2)

    assert result == "任务完成"
    assert delay_calls == []
    assert runner._automation.executed == []


def test_runner_stalled_threshold_triggers_replan_without_executing_second_tool():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    config.set("execution_config.stalled_replan_threshold", 2)
    config.set("execution_config.stalled_difficult_threshold", 4)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)], [make_bundle(value=2)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "重复点击",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 200],
                },
            },
        },
        {
            "status": "tool_call",
            "thinking": "继续重复点击",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 200],
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])
    runner._is_stalled = lambda **kwargs: True

    result = runner.run("task", max_iterations=3)

    assert result == "任务完成"
    assert runner._automation.executed == [("click", {"screen_index": 0, "position": [100.0, 200.0]})]
    assert "did not produce a visible interface change" in runner._ai_client.calls[2]["replan_feedback"]


def test_sleep_interruptibly_stops_early(monkeypatch):
    config = Config()
    runner = ControlLoopRunner(config)
    sleep_calls = []
    stop_checks = {"count": 0}

    monkeypatch.setattr("baodou_ai.core.runner.time.sleep", lambda seconds: sleep_calls.append(seconds))

    def should_stop():
        stop_checks["count"] += 1
        return stop_checks["count"] >= 2

    result = runner._sleep_interruptibly(delay_ms=250, should_stop=should_stop, step_ms=20)

    assert result is False
    assert len(sleep_calls) == 1


def test_runner_returns_interrupted_when_stop_requested_after_tool():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=10)]])

    stop_state = {"stop": False}

    class StopAfterClickAutomation(FakeAutomation):
        def tool_click(self, screen_index, position, screen_info=None):
            result = super().tool_click(screen_index, position, screen_info=screen_info)
            stop_state["stop"] = True
            return result

    runner._automation = StopAfterClickAutomation()
    runner._ai_client = FakeAIClient([{
        "status": "tool_call",
        "tool": {
            "name": "click",
            "args": {"screen_index": 0, "position": [100, 200]},
        },
    }])

    result = runner.run("task", max_iterations=2, should_stop=lambda: stop_state["stop"])

    assert result == "Task interrupted by user"
    assert runner._automation.executed == [("click", {"screen_index": 0, "position": [100.0, 200.0]})]


def test_wait_for_tool_pacing_waits_remaining_time(monkeypatch):
    config = Config()
    config.set("execution_config.minimum_tool_interval_ms", 900)
    runner = ControlLoopRunner(config)
    waits = []

    monkeypatch.setattr("baodou_ai.core.runner.time.perf_counter", lambda: 10.2)
    runner._sleep_interruptibly = lambda delay_ms, should_stop: waits.append(delay_ms) or True

    assert runner._wait_for_tool_pacing(10.0, lambda: False) is True
    assert len(waits) == 1
    assert abs(waits[0] - 700.0) < 0.001


def test_runner_injects_current_held_modifier_prompt():
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation()
    runner._automation._held_modifier_keys = ["command"]
    runner._ai_client = FakeAIClient([{
        "status": "respond",
        "outcome": "completed",
        "report": "任务完成",
    }])

    runner.run("task", max_iterations=1)

    assert "Currently held modifier keys: command." in runner._ai_client.calls[0]["held_modifier_prompt"]


def test_runner_hold_modifier_tool_updates_state_for_next_round():
    config = Config()
    config.set("execution_config.post_tool_capture_delay_ms", 0)
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)], [make_bundle(value=2)]])
    runner._automation = FakeAutomation()
    runner._ai_client = FakeAIClient([
        {
            "status": "tool_call",
            "thinking": "需要多选，先保持 command",
            "tool": {
                "name": "hold_modifier_keys",
                "args": {"keys": ["command"]},
            },
        },
        {
            "status": "tool_call",
            "thinking": "当前 command 还在按住，继续点击",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 200],
                },
            },
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])

    result = runner.run("task", max_iterations=3)

    assert result == "任务完成"
    assert "Currently held modifier keys: command." in runner._ai_client.calls[1]["held_modifier_prompt"]
    assert runner._automation.marked_steps == [1]


def test_runner_releases_all_held_modifiers_on_respond():
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation()
    runner._automation._held_modifier_keys = ["command"]
    runner._ai_client = FakeAIClient([{
        "status": "respond",
        "outcome": "completed",
        "report": "任务完成",
    }])

    runner.run("task", max_iterations=1)

    assert runner._automation.release_all_calls >= 1
    assert runner._automation.get_held_modifier_keys() == []


def test_runner_auto_released_modifier_notice_is_injected():
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation()
    runner._automation.auto_release_notice = "先前长按状态已自动解除。"
    runner._ai_client = FakeAIClient([{
        "status": "respond",
        "outcome": "completed",
        "report": "任务完成",
    }])

    runner.run("task", max_iterations=1)

    assert "先前长按状态已自动解除。" in runner._ai_client.calls[0]["held_modifier_prompt"]


def test_runner_restores_external_focus_before_capture_and_injects_frontmost_prompt(capsys):
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation(frontmost_sequence=[
        {"app_name": "BaodouAI", "bundle_id": "com.example.baodou", "pid": 999},
        {"app_name": "Google Chrome", "bundle_id": "com.google.Chrome", "pid": 222},
        {"app_name": "Google Chrome", "bundle_id": "com.google.Chrome", "pid": 222},
    ])
    runner._ai_client = FakeAIClient([{
        "status": "respond",
        "outcome": "completed",
        "report": "任务完成",
    }])

    result = runner.run(
        "task",
        max_iterations=1,
        initial_external_frontmost_app={"app_name": "Google Chrome", "bundle_id": "com.google.Chrome", "pid": 222},
        agent_process_pid=999,
    )

    assert result == "任务完成"
    assert runner._automation.activate_calls == [
        {"app_name": "Google Chrome", "bundle_id": "com.google.Chrome", "identifier": "", "pid": 222}
    ]
    assert runner._ai_client.calls[0]["frontmost_app_prompt"] == "Current frontmost app: Google Chrome."
    assert "[Frontmost App]\nCurrent frontmost app: Google Chrome." in capsys.readouterr().out


def test_runner_injects_focus_fallback_prompt_when_external_focus_unavailable(capsys):
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation(frontmost_sequence=[
        {"app_name": "BaodouAI", "bundle_id": "com.example.baodou", "pid": 999},
        {"app_name": "BaodouAI", "bundle_id": "com.example.baodou", "pid": 999},
        {"app_name": "BaodouAI", "bundle_id": "com.example.baodou", "pid": 999},
    ], activate_result=False)
    runner._ai_client = FakeAIClient([{
        "status": "respond",
        "outcome": "completed",
        "report": "任务完成",
    }])

    runner.run(
        "task",
        max_iterations=1,
        initial_external_frontmost_app={"app_name": "Google Chrome", "bundle_id": "com.google.Chrome", "pid": 222},
        agent_process_pid=999,
    )

    prompt = runner._ai_client.calls[0]["frontmost_app_prompt"]
    assert "The current keyboard focus is not on an operable external application." in prompt
    assert "click the target window or input area first to gain focus" in prompt
    assert "[Frontmost App]\n" in capsys.readouterr().out


def test_runner_clears_stale_external_frontmost_app_after_restore_failure():
    config = Config()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()], [make_bundle(value=1)]])
    runner._automation = FakeAutomation(
        frontmost_sequence=[
            {"app_name": "BaodouAI", "bundle_id": "com.example.baodou", "pid": 999},
            {"app_name": "BaodouAI", "bundle_id": "com.example.baodou", "pid": 999},
            {"app_name": "BaodouAI", "bundle_id": "com.example.baodou", "pid": 999},
            {"app_name": "BaodouAI", "bundle_id": "com.example.baodou", "pid": 999},
        ],
        activate_result=False,
    )
    runner._ai_client = FakeAIClient([
        {
            "status": "page_loading",
        },
        {
            "status": "respond",
            "outcome": "completed",
            "report": "任务完成",
        },
    ])

    runner.run(
        "task",
        max_iterations=2,
        initial_external_frontmost_app={"app_name": "微信", "bundle_id": "com.tencent.xinWeChat", "pid": 321},
        agent_process_pid=999,
    )

    assert runner._automation.activate_calls == [
        {"app_name": "微信", "bundle_id": "com.tencent.xinWeChat", "identifier": "", "pid": 321}
    ]


def test_runner_clear_memory_files_also_clears_extract_dirs(monkeypatch, tmp_path):
    config = Config()
    runner = ControlLoopRunner(config)
    page_extract_dir = tmp_path / "page_extract"
    document_extract_dir = tmp_path / "doc_extract"
    page_extract_dir.mkdir(parents=True, exist_ok=True)
    document_extract_dir.mkdir(parents=True, exist_ok=True)
    memory_file = tmp_path / "memory.txt"
    memory_file.write_text("old", encoding="utf-8")
    (page_extract_dir / "page_001.txt").write_text("old page", encoding="utf-8")
    (document_extract_dir / "document_001.txt").write_text("old document", encoding="utf-8")

    monkeypatch.setattr("baodou_ai.core.runner.MEMORY_FILE", str(memory_file))
    monkeypatch.setattr("baodou_ai.core.runner.PAGE_EXTRACT_DIR", str(page_extract_dir))
    monkeypatch.setattr("baodou_ai.core.runner.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    document_anchor_dir = tmp_path / "doc_anchor"
    monkeypatch.setattr("baodou_ai.core.runner.DOCUMENT_ANCHOR_DIR", str(document_anchor_dir))

    runner._clear_memory_files()

    assert page_extract_dir.exists()
    assert document_extract_dir.exists()
    assert document_anchor_dir.exists()
    assert list(page_extract_dir.iterdir()) == []
    assert list(document_extract_dir.iterdir()) == []
    assert list(document_anchor_dir.iterdir()) == []
    assert memory_file.read_text(encoding="utf-8") == ""
