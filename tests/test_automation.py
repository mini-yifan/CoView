from types import SimpleNamespace
import time

import pytest

import baodou_ai.core.automation_tools.page_reader as page_reader_module
from baodou_ai.agent.tool_executor import ToolExecutor
from baodou_ai.core.automation import AutomationController
from baodou_ai.core.config import Config
from baodou_ai.core.observation import ObservationService
from baodou_ai.core.automation_tools.runtime import ToolInterrupted


class FakePlatformAdapter:
    def __init__(self):
        self.calls = []

    def move_cursor(self, x, y, duration=0.0):
        self.calls.append(("move_cursor", x, y, duration))

    def click(self, button="left", clicks=1):
        self.calls.append(("click", button, clicks))

    def mouse_down(self, button="left"):
        self.calls.append(("mouse_down", button))

    def mouse_up(self, button="left"):
        self.calls.append(("mouse_up", button))

    def drag_to(self, x, y, duration=0.0, button="left"):
        self.calls.append(("drag_to", x, y, duration, button))

    def scroll(self, amount):
        self.calls.append(("scroll", amount))

    def key_down(self, key):
        self.calls.append(("key_down", key))

    def key_up(self, key):
        self.calls.append(("key_up", key))

    def key_press(self, key):
        self.calls.append(("key_press", key))

    def get_logical_screen_size(self):
        return (1000, 1000)

    def translate_hotkey_keys(self, keys):
        return keys

    def launch_app(self, app_name):
        self.calls.append(("launch_app", app_name))
        return {"matched": True, "app_name": app_name, "suggestions": []}

    def open_app_launcher(self):
        self.calls.append(("open_app_launcher",))
        return {
            "app_names": ["Google Chrome", "Notes", "Terminal"],
        }

    def get_default_browser_info(self):
        return {
            "app_name": "Google Chrome",
            "identifier": "com.google.Chrome",
            "is_chrome_family": True,
        }

    def open_in_browser(self, url=None, query=None):
        self.calls.append(("open_in_browser", url, query))
        return {
            "browser": self.get_default_browser_info(),
            "target_url": url or query,
        }

    def open_in_finder(self, path=None):
        self.calls.append(("open_in_finder", path))
        return {
            "target_path": "/Users/test/Desktop" if path is None else path,
            "revealed_file": None,
        }

    def get_frontmost_app_info(self):
        return {
            "app_name": "Google Chrome",
            "bundle_id": "com.google.Chrome",
            "identifier": "com.google.Chrome",
            "pid": 123,
        }

    def get_hotkey_modifier(self):
        return "command"

    def move_to_trash(self, path):
        self.calls.append(("move_to_trash", path))
        return {"ok": True, "error": None}

    def get_active_document_path(self, app_name):
        if app_name in ("Finder", "访达"):
            return "/Users/test/Desktop"
        return None


def _build_token_heavy_block(
    controller: AutomationController, prefix: str, min_tokens: int, leading_text: str = ""
) -> str:
    parts = [leading_text.strip()] if leading_text.strip() else []
    index = 0
    current_text = " ".join(part for part in parts if part)
    while controller._count_document_tokens(current_text) < min_tokens:
        parts.append(f"{prefix}{index}")
        index += 1
        current_text = " ".join(part for part in parts if part)
    return current_text


def test_move_cursor_smooth_enforces_min_duration():
    controller = AutomationController(Config.create_isolated())
    controller._platform_adapter = FakePlatformAdapter()
    controller._move_cursor_smooth(100, 200, 0.05)

    assert controller._platform_adapter.calls == [("move_cursor", 100, 200, 0.35)]


def test_move_cursor_smooth_uses_configured_min_duration():
    config = Config.create_isolated()
    config.set("mouse_config.min_move_duration", 0.5)
    controller = AutomationController(config)
    controller._platform_adapter = FakePlatformAdapter()
    controller._move_cursor_smooth(100, 200, 0.05)

    assert controller._platform_adapter.calls == [("move_cursor", 100, 200, 0.5)]


def test_execute_tool_runtime_returns_standard_interrupted_result():
    controller = AutomationController(Config.create_isolated())
    context = controller._build_tool_context()

    result = controller._execute_tool_runtime(
        context=context,
        operation=lambda _context: (_ for _ in ()).throw(ToolInterrupted("stop")),
        failure_summary="不应返回这个失败信息",
    )

    assert result == {
        "ok": False,
        "summary": "工具执行已中断",
        "error": "用户已停止当前任务",
    }


def test_tool_executor_wraps_unexpected_exception_with_error_envelope():
    class BrokenAutomation:
        def tool_click(self, **kwargs):
            del kwargs
            raise RuntimeError("boom")

    executor = ToolExecutor(BrokenAutomation())
    result = executor.execute("click", {"screen_index": 0, "position": [100, 200]})

    assert result["ok"] is False
    assert result["summary"] == "工具执行失败"
    assert "boom" in result["error"]
    envelope = result.get("error_envelope")
    assert isinstance(envelope, dict)
    assert envelope["source"] == "tool"
    assert envelope["code"] == "TOOL_EXEC_FAILED"


def test_tool_stop_code_agent_cancels_running_job():
    controller = AutomationController(Config())

    class FakeJobManager:
        def __init__(self):
            self.cancelled = []

        def get_job(self, job_id, include_logs=False):
            del include_logs
            return {
                "job_id": job_id,
                "status": "running",
                "dismissed": False,
            }

        def cancel(self, job_id):
            self.cancelled.append(job_id)
            return {
                "job_id": job_id,
                "status": "cancelled",
                "provider": "codex",
                "title": "计算器页面",
            }

    fake_manager = FakeJobManager()
    controller.set_job_manager(fake_manager)

    result = controller.tool_stop_code_agent("code-job-0001")

    assert fake_manager.cancelled == ["code-job-0001"]
    assert result == {
        "ok": True,
        "summary": "后台代码任务已停止（code-job-0001，provider=codex，status=cancelled）",
        "error": None,
        "job_id": "code-job-0001",
        "job_status": "cancelled",
        "provider": "codex",
        "stop_report": "后台代码任务“计算器页面”已停止。",
    }


def test_tool_stop_code_agent_rejects_non_running_job():
    controller = AutomationController(Config())

    class FakeJobManager:
        def get_job(self, job_id, include_logs=False):
            del job_id, include_logs
            return {
                "job_id": "code-job-0001",
                "status": "completed",
                "dismissed": False,
            }

        def cancel(self, job_id):
            raise AssertionError(f"cancel should not be called: {job_id}")

    controller.set_job_manager(FakeJobManager())

    result = controller.tool_stop_code_agent("code-job-0001")

    assert result["ok"] is False
    assert result["summary"] == "后台代码任务未停止"
    assert result["error"] == "该后台代码任务当前未在运行中"
    assert result["error_envelope"]["source"] == "code_agent"


def test_split_document_into_chunks_prefers_punctuation_and_newlines():
    controller = AutomationController(Config())
    first = _build_token_heavy_block(controller, "alpha", 9)
    second = _build_token_heavy_block(controller, "beta", 9)
    third = _build_token_heavy_block(controller, "gamma", 9)
    content = first + "。\n" + second + "\n" + third

    chunks = controller._split_document_into_chunks(
        content,
        target_tokens=10,
        min_tokens=9,
        max_tokens=12,
    )

    assert chunks == [first + "。", second, third]


def test_build_document_view_anchor_skips_leading_special_chars():
    controller = AutomationController(Config())

    anchor_text, error = controller._build_document_view_anchor(
        full_content="前文内容\n【】（测试锚点内容开始这里）后续正文",
        chunk_content="【】（测试锚点内容开始这里）后续正文",
    )

    assert error == ""
    assert anchor_text.startswith("测试锚点内容开始这里")
    assert not anchor_text.startswith("【")


def test_build_document_view_anchor_prefers_body_phrase_within_first_200_chars():
    controller = AutomationController(Config())
    chunk_content = (
        "第一行标题\n第二行说明\n"
        + "这是正文里稳定可搜索的连续二十字锚点内容甲乙丙丁戊己庚辛"
        + "后续内容"
    )
    full_content = "前文" + chunk_content + "结尾"

    anchor_text, error = controller._build_document_view_anchor(
        full_content=full_content,
        chunk_content=chunk_content,
    )

    assert error == ""
    assert anchor_text == "这是正文里稳定可搜索的连续二十字锚点内容"


def test_build_document_view_anchor_falls_back_to_weak_punctuation_phrase():
    controller = AutomationController(Config())
    chunk_content = (
        "第一行标题\n说明！" + "这是允许，弱标点、“引号”的二十字正文锚点甲乙丙丁戊己" + "结尾"
    )
    full_content = "前文" + chunk_content + "后文"

    anchor_text, error = controller._build_document_view_anchor(
        full_content=full_content,
        chunk_content=chunk_content,
    )

    assert error == ""
    assert anchor_text == "这是允许，弱标点、“引号”的二十字正文锚"


def test_build_document_view_anchor_falls_back_to_first_20_chars_when_no_phrase_found():
    controller = AutomationController(Config())
    chunk_content = "12345\n67890\n12345\n67890"
    full_content = "前文" + chunk_content + "后文"

    anchor_text, error = controller._build_document_view_anchor(
        full_content=full_content,
        chunk_content=chunk_content,
    )

    assert error == ""
    assert anchor_text == "12345 67890 12345 67"


def test_handle_single_point_maps_secondary_screen_coordinates():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform

    mapped, action_str = controller._handle_single_point(
        [500, 500],
        "click",
        0.1,
        target_screen={"width": 300, "height": 200, "x": 1000, "y": -200},
    )

    assert mapped == [1150.0, -100.0]
    assert fake_platform.calls == [
        ("move_cursor", 1150.0, -100.0, 0.35),
        ("click", "left", 1),
    ]
    assert "已点击" in action_str


def test_handle_drag_maps_cross_screen_coordinates():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform

    mapped, action_str = controller._handle_drag(
        [[500, 500], [750, 250]],
        0.1,
        target_screen={"width": 1000, "height": 800, "x": 0, "y": 0},
        end_screen={"width": 1200, "height": 1000, "x": -1400, "y": 100},
    )

    assert mapped == [[500.0, 400.0], [-500.0, 350.0]]
    assert fake_platform.calls == [
        ("move_cursor", 500.0, 400.0, 0.35),
        ("drag_to", -500.0, 350.0, 1.4, "left"),
    ]
    assert "已完成拖拽操作" in action_str


def test_handle_single_point_scroll_uses_platform_scroll_on_macos():
    controller = AutomationController(Config())
    controller._current_os = "Darwin"
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform

    mapped, action_str = controller._handle_single_point(
        [200, 300],
        "scroll_up",
        0.1,
        target_screen={"width": 1000, "height": 1000, "x": 100, "y": 50},
    )

    assert mapped == [300.0, 350.0]
    assert fake_platform.calls == [
        ("move_cursor", 300.0, 350.0, 0.35),
        ("scroll", 10),
    ]
    assert "向上滚动 10" in action_str


def test_handle_single_point_scroll_accepts_custom_scroll_amount():
    controller = AutomationController(Config())
    controller._current_os = "Darwin"
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform

    mapped, action_str = controller._handle_single_point(
        [200, 300],
        "scroll_down",
        0.1,
        target_screen={"width": 1000, "height": 1000, "x": 100, "y": 50},
        scroll_amount=25,
    )

    assert mapped == [300.0, 350.0]
    assert fake_platform.calls == [
        ("move_cursor", 300.0, 350.0, 0.35),
        ("scroll", -25),
    ]
    assert "向下滚动 25" in action_str


def test_handle_single_point_long_press_uses_configured_duration(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    sleep_calls = []

    def fake_sleep(seconds, should_stop=None):
        sleep_calls.append((seconds, should_stop))
        return True

    monkeypatch.setattr(controller, "_sleep_interruptibly", fake_sleep)

    mapped, action_str = controller._handle_single_point(
        [400, 600],
        "long_press",
        0.1,
        target_screen={"width": 1000, "height": 1000, "x": 0, "y": 0},
        long_press_duration_seconds=2.5,
    )

    assert mapped == [400.0, 600.0]
    assert sleep_calls == [(2.5, None)]
    assert fake_platform.calls == [
        ("move_cursor", 400.0, 600.0, 0.35),
        ("mouse_down", "left"),
        ("mouse_up", "left"),
    ]
    assert "已长按 2.5 秒" in action_str


def test_tool_long_press_defaults_to_three_seconds_and_forwards_stop(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        elapsed_ms=0.0,
        changed_ratio=0.0,
        stable=True,
    )
    stop_checks = []
    sleep_calls = []

    def should_stop():
        stop_checks.append("checked")
        return False

    def fake_sleep(seconds, should_stop=None):
        sleep_calls.append((seconds, should_stop))
        if should_stop is not None:
            should_stop()
        return True

    monkeypatch.setattr(controller, "_sleep_interruptibly", fake_sleep)

    result = controller.tool_long_press(
        screen_index=0,
        position=[500, 500],
        screen_info=[{"width": 1000, "height": 1000, "x": 0, "y": 0}],
        should_stop=should_stop,
    )

    assert result == {"ok": True, "summary": "已长按", "error": None}
    assert sleep_calls == [(3.0, should_stop)]
    assert stop_checks == ["checked", "checked"]
    assert fake_platform.calls == [
        ("move_cursor", 500.0, 500.0, 0.35),
        ("mouse_down", "left"),
        ("mouse_up", "left"),
    ]


def test_handle_single_point_long_press_releases_mouse_when_interrupted(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform

    monkeypatch.setattr(controller, "_sleep_interruptibly", lambda seconds, should_stop=None: False)

    with pytest.raises(RuntimeError, match="长按已中断"):
        controller._handle_single_point(
            [400, 600],
            "long_press",
            0.1,
            target_screen={"width": 1000, "height": 1000, "x": 0, "y": 0},
            long_press_duration_seconds=10,
            should_stop=lambda: True,
        )

    assert fake_platform.calls == [
        ("move_cursor", 400.0, 600.0, 0.35),
        ("mouse_down", "left"),
        ("mouse_up", "left"),
    ]


def test_tool_remember_writes_text_only_without_screenshot(monkeypatch, tmp_path):
    controller = AutomationController(Config())
    memory_file = tmp_path / "memory.txt"

    monkeypatch.setattr("baodou_ai.core.automation.MEMORY_FILE", str(memory_file))
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.screenshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("remember 不应再截图")),
    )

    result = controller.tool_remember("关键信息")

    assert result == {"ok": True, "summary": "已记录重要信息", "error": None}
    assert memory_file.read_text(encoding="utf-8") == "关键信息\n"


def test_tool_scroll_down_scroll_level_scales_default_scroll_range():
    controller = AutomationController(Config())
    controller._current_os = "Windows"
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=0.0,
        probe_count=1,
        last_change_ratio=0.0,
    )

    result = controller.tool_scroll_down(
        screen_index=0,
        position=[200, 300],
        scroll_level=4,
        screen_info=[{"width": 1000, "height": 1000, "x": 100, "y": 50}],
    )

    assert result == {"ok": True, "summary": "已向下滚动", "error": None}
    assert fake_platform.calls == [
        ("move_cursor", 300.0, 350.0, 0.35),
        ("scroll", -400),
    ]


def test_resolve_scroll_amount_rejects_out_of_range_scroll_level():
    controller = AutomationController(Config())

    with pytest.raises(ValueError, match="scroll_level 必须在 1-10 之间"):
        controller._resolve_scroll_amount(11)


def test_resolve_scroll_amount_accepts_upper_bound_scroll_level():
    controller = AutomationController(Config())
    controller._current_os = "Darwin"

    assert controller._resolve_scroll_amount(10) == 100


def test_handle_input_text_replace_and_submit_uses_platform_click_before_keyboard_shortcuts(
    monkeypatch,
):
    controller = AutomationController(Config())
    controller._current_os = "Darwin"
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform

    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.paste", lambda: "original")
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr("baodou_ai.core.automation.time.sleep", lambda _: None)

    result = controller._handle_type_input("hello", [200, 300], replace=True, submit=True)

    assert fake_platform.calls == [
        ("click", "left", 1),
        ("key_down", "command"),
        ("key_press", "a"),
        ("key_up", "command"),
        ("key_down", "command"),
        ("key_press", "v"),
        ("key_up", "command"),
        ("key_press", "enter"),
    ]
    assert "已提交: hello" in result


def test_handle_input_text_with_position_clicks_before_paste_without_enter(monkeypatch):
    controller = AutomationController(Config())
    controller._current_os = "Darwin"
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform

    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.paste", lambda: "original")
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr("baodou_ai.core.automation.time.sleep", lambda _: None)

    result = controller._handle_type_input("hello", [200, 300], replace=False, submit=False)

    assert fake_platform.calls == [
        ("click", "left", 1),
        ("key_down", "command"),
        ("key_press", "v"),
        ("key_up", "command"),
    ]
    assert "已输入: hello" in result


def test_handle_type_input_restores_clipboard_after_success(monkeypatch):
    controller = AutomationController(Config())
    controller._current_os = "Darwin"
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    copy_calls = []

    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.paste", lambda: "original")
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyperclip.copy", lambda text: copy_calls.append(text)
    )
    monkeypatch.setattr("baodou_ai.core.automation.time.sleep", lambda _: None)

    result = controller._handle_type_input("hello", None, replace=False, submit=False)

    assert result.endswith("已输入: hello\n")
    assert copy_calls == ["hello", "original"]
    assert fake_platform.calls == [
        ("key_down", "command"),
        ("key_press", "v"),
        ("key_up", "command"),
    ]


def test_handle_type_input_restores_clipboard_after_failure(monkeypatch):
    controller = AutomationController(Config())
    controller._current_os = "Darwin"
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    copy_calls = []

    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.paste", lambda: "original")
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyperclip.copy", lambda text: copy_calls.append(text)
    )
    monkeypatch.setattr("baodou_ai.core.automation.time.sleep", lambda _: None)

    def _raise_keydown(_key):
        raise RuntimeError("keyboard down failed")

    fake_platform.key_down = _raise_keydown

    with pytest.raises(RuntimeError, match="keyboard down failed"):
        controller._handle_type_input("hello", None, replace=False, submit=False)

    assert copy_calls == ["hello", "original"]


def test_type_text_restores_clipboard(monkeypatch):
    controller = AutomationController(Config())
    controller._current_os = "Darwin"
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    copy_calls = []

    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.paste", lambda: "original")
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyperclip.copy", lambda text: copy_calls.append(text)
    )

    controller.type_text("world")

    assert copy_calls == ["world", "original"]
    assert fake_platform.calls == [
        ("key_down", "command"),
        ("key_press", "v"),
        ("key_up", "command"),
    ]


def test_hotkey_holds_multiple_modifiers_before_pressing_main_key(monkeypatch):
    controller = AutomationController(Config())
    controller._current_os = "Darwin"
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform

    controller.hotkey("command", "shift", "3")

    assert fake_platform.calls == [
        ("key_down", "command"),
        ("key_down", "shift"),
        ("key_press", "3"),
        ("key_up", "shift"),
        ("key_up", "command"),
    ]


def test_tool_click_moves_and_clicks_on_secondary_screen():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=10.0,
        probe_count=2,
        last_change_ratio=0.0,
    )
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    result = controller.tool_click(
        screen_index=1,
        position=[500, 500],
        screen_info=[
            {"x": 0, "y": 0, "width": 800, "height": 600, "is_primary": True},
            {"x": -1600, "y": -200, "width": 1200, "height": 900, "is_primary": False},
        ],
    )

    assert result == {"ok": True, "summary": "已点击", "error": None}
    assert fake_platform.calls == [
        ("move_cursor", -1000.0, 250.0, 0.35),
        ("click", "left", 1),
    ]


def test_tool_drag_moves_across_screens_without_legacy_execute():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=10.0,
        probe_count=2,
        last_change_ratio=0.0,
    )
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    result = controller.tool_drag(
        start_screen_index=0,
        start_position=[500, 500],
        end_screen_index=1,
        end_position=[750, 250],
        screen_info=[
            {"x": 0, "y": 0, "width": 1000, "height": 800, "is_primary": True},
            {"x": -1400, "y": 100, "width": 1200, "height": 1000, "is_primary": False},
        ],
    )

    assert result == {"ok": True, "summary": "已拖拽", "error": None}
    assert fake_platform.calls == [
        ("move_cursor", 500.0, 400.0, 0.35),
        ("drag_to", -500.0, 350.0, 1.4, "left"),
    ]


def test_tool_input_text_without_position_uses_direct_input_path(monkeypatch):
    controller = AutomationController(Config())
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=10.0,
        probe_count=1,
        last_change_ratio=0.0,
    )
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None
    calls = []

    monkeypatch.setattr(
        controller,
        "_handle_type_input",
        lambda text, coordinates, replace=False, submit=False: calls.append(
            (text, coordinates, replace, submit)
        )
        or "已输入",
    )

    result = controller.tool_input_text(text="hello", screen_info=None)

    assert result == {"ok": True, "summary": "已输入文本", "error": None}
    assert calls == [("hello", None, False, False)]


def test_tool_input_text_replace_without_position_is_rejected():
    controller = AutomationController(Config())
    result = controller.tool_input_text(text="hello", replace=True, screen_info=None)

    assert result == {
        "ok": False,
        "summary": "输入文本失败",
        "error": "input_text(replace=true) 必须同时提供 screen_index 和 position",
    }


def test_tool_input_text_with_position_moves_then_inputs(monkeypatch):
    controller = AutomationController(Config())
    controller._current_os = "Darwin"
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=10.0,
        probe_count=1,
        last_change_ratio=0.0,
    )
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None
    key_events = []

    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.paste", lambda: "original")
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr("baodou_ai.core.automation.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.keyDown", lambda key: key_events.append(("down", key))
    )
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.keyUp", lambda key: key_events.append(("up", key))
    )
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.press", lambda key: key_events.append(("press", key))
    )

    result = controller.tool_input_text(
        text="world",
        screen_index=0,
        position=[300, 400],
        replace=False,
        submit=False,
        screen_info=[{"x": 0, "y": 0, "width": 1000, "height": 1000, "is_primary": True}],
    )

    assert result == {"ok": True, "summary": "已输入文本", "error": None}
    assert fake_platform.calls == [
        ("move_cursor", 300.0, 400.0, 0.35),
        ("click", "left", 1),
    ]
    assert key_events == [
        ("down", "command"),
        ("press", "v"),
        ("up", "command"),
    ]


def test_tool_input_text_replace_without_submit_moves_then_replaces(monkeypatch):
    controller = AutomationController(Config())
    controller._current_os = "Darwin"
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=10.0,
        probe_count=1,
        last_change_ratio=0.0,
    )
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None
    key_events = []

    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.paste", lambda: "original")
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr("baodou_ai.core.automation.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.keyDown", lambda key: key_events.append(("down", key))
    )
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.keyUp", lambda key: key_events.append(("up", key))
    )
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.press", lambda key: key_events.append(("press", key))
    )

    result = controller.tool_input_text(
        screen_index=0,
        position=[300, 400],
        text="world",
        replace=True,
        submit=False,
        screen_info=[{"x": 0, "y": 0, "width": 1000, "height": 1000, "is_primary": True}],
    )

    assert result == {"ok": True, "summary": "已替换输入内容", "error": None}
    assert fake_platform.calls == [
        ("move_cursor", 300.0, 400.0, 0.35),
        ("click", "left", 1),
    ]
    assert key_events == [
        ("down", "command"),
        ("press", "a"),
        ("up", "command"),
        ("down", "command"),
        ("press", "v"),
        ("up", "command"),
    ]


def test_tool_input_text_replace_and_submit_moves_then_replaces_and_submits(monkeypatch):
    controller = AutomationController(Config())
    controller._current_os = "Darwin"
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=10.0,
        probe_count=1,
        last_change_ratio=0.0,
    )
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None
    key_events = []

    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.paste", lambda: "original")
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr("baodou_ai.core.automation.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.keyDown", lambda key: key_events.append(("down", key))
    )
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.keyUp", lambda key: key_events.append(("up", key))
    )
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.press", lambda key: key_events.append(("press", key))
    )

    result = controller.tool_input_text(
        screen_index=0,
        position=[300, 400],
        text="world",
        replace=True,
        submit=True,
        screen_info=[{"x": 0, "y": 0, "width": 1000, "height": 1000, "is_primary": True}],
    )

    assert result == {"ok": True, "summary": "已替换输入内容并提交", "error": None}
    assert fake_platform.calls == [
        ("move_cursor", 300.0, 400.0, 0.35),
        ("click", "left", 1),
    ]
    assert key_events == [
        ("down", "command"),
        ("press", "a"),
        ("up", "command"),
        ("down", "command"),
        ("press", "v"),
        ("up", "command"),
        ("press", "enter"),
    ]


def test_tool_launch_app_uses_platform_adapter(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=10.0,
        probe_count=1,
        last_change_ratio=0.0,
    )
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    result = controller.tool_launch_app("微信", screen_info=None)

    assert result == {"ok": True, "summary": "已启动应用", "error": None}
    assert fake_platform.calls == [("launch_app", "微信")]


def test_tool_launch_app_returns_suggestions_without_auto_open(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.launch_app = lambda app_name: {
        "matched": False,
        "suggestions": ["微信", "企业微信"],
        "error": "没有找到名为“微信开发版”的应用，可能是这些：微信、企业微信",
    }
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    result = controller.tool_launch_app("微信开发版", screen_info=None)

    assert result == {
        "ok": False,
        "summary": "启动应用失败",
        "error": "没有找到名为“微信开发版”的应用，可能是这些：微信、企业微信",
    }


def test_tool_launch_app_propagates_app_launcher_fallback(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.launch_app = lambda app_name: {
        "matched": False,
        "suggestions": [],
        "error": "系统级启动未找到该应用。请调用 open_app_launcher 打开启动台，并在其中搜索“备忘录”尝试启动。",
        "fallback": {
            "type": "app_launcher_search",
            "app_name": "备忘录",
        },
    }
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    result = controller.tool_launch_app("备忘录", screen_info=None)

    assert result == {
        "ok": False,
        "summary": "启动应用失败",
        "error": "系统级启动未找到该应用。请调用 open_app_launcher 打开启动台，并在其中搜索“备忘录”尝试启动。",
        "fallback": {
            "type": "app_launcher_search",
            "app_name": "备忘录",
        },
    }


def test_tool_open_in_browser_uses_platform_adapter(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=10.0,
        probe_count=1,
        last_change_ratio=0.0,
    )
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    result = controller.tool_open_in_browser(query="罗翔说刑法 bilibili", screen_info=None)

    assert result == {"ok": True, "summary": "已在默认浏览器中打开内容", "error": None}
    assert fake_platform.calls == [("open_in_browser", None, "罗翔说刑法 bilibili")]


def test_tool_open_in_finder_uses_platform_adapter(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=10.0,
        probe_count=1,
        last_change_ratio=0.0,
    )
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    result = controller.tool_open_in_finder(screen_info=None)

    assert result == {"ok": True, "summary": "已打开桌面目录", "error": None}
    assert fake_platform.calls == [("open_in_finder", None)]


def test_tool_open_in_finder_with_path(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=10.0,
        probe_count=1,
        last_change_ratio=0.0,
    )
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    result = controller.tool_open_in_finder(path="/Users/test/Documents", screen_info=None)

    assert result == {"ok": True, "summary": "已在访达中打开: /Users/test/Documents", "error": None}
    assert fake_platform.calls == [("open_in_finder", "/Users/test/Documents")]


def test_tool_open_app_launcher_uses_platform_adapter(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=10.0,
        probe_count=1,
        last_change_ratio=0.0,
    )
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    result = controller.tool_open_app_launcher(screen_info=None)

    assert result == {
        "ok": True,
        "summary": "已打开应用启动器并获取应用列表",
        "error": None,
        "app_names": ["Google Chrome", "Notes", "Terminal"],
    }
    assert fake_platform.calls == [("open_app_launcher",)]


def test_tool_read_current_page_rejects_non_browser_frontmost_app():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Finder",
        "bundle_id": "com.apple.finder",
        "identifier": "com.apple.finder",
        "pid": 456,
    }
    controller._platform_adapter = fake_platform

    result = controller.tool_read_current_page(screen_info=None)

    assert result["ok"] is False
    assert result["summary"] == "读取当前网页失败"
    assert "仅支持在浏览器前台页面使用" in str(result["error"])
    assert result.get("fallback", {}).get("type") == "read_current_page_not_browser"


def test_tool_read_current_page_success_writes_page_record_and_returns_page_context(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    page_extract_dir = tmp_path / "page_extract"
    monkeypatch.setattr("baodou_ai.core.automation.PAGE_EXTRACT_DIR", str(page_extract_dir))
    monkeypatch.setattr(
        controller, "_extract_current_browser_url", lambda max_retries=3: "https://example.com"
    )
    monkeypatch.setattr(
        controller,
        "_fetch_webpage_text",
        lambda url: {
            "title": "Example Domain",
            "text": "这是示例网页正文。\n用于测试 read_current_page 写入网页解析记录。",
        },
    )

    result = controller.tool_read_current_page(screen_info=None)

    assert result["ok"] is True
    assert "已读取当前网页（可能不完整）" in result["summary"]
    assert "进入临时网页上下文" in result["summary"]
    assert result.get("quality") == "best_effort"
    page_context = result.get("page_context", {})
    assert page_context.get("url") == "https://example.com"
    assert page_context.get("title") == "Example Domain"
    assert (
        page_context.get("content")
        == "这是示例网页正文。\n用于测试 read_current_page 写入网页解析记录。"
    )
    assert page_context.get("source_mode") == "extract"
    assert page_context.get("chunk_index") == 0
    assert page_context.get("total_chunks") >= 1
    assert isinstance(page_context.get("has_more"), bool)
    assert page_extract_dir.exists()
    record_files = list(page_extract_dir.glob("page_*.txt"))
    assert len(record_files) == 1
    record_content = record_files[0].read_text(encoding="utf-8")
    assert "链接: https://example.com" in record_content
    assert "标题: Example Domain" in record_content
    assert "质量:" not in record_content
    assert "正文:" in record_content
    assert "用于测试 read_current_page 写入网页解析记录。" in record_content


def test_tool_read_current_page_returns_partial_when_no_text(monkeypatch, tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    page_extract_dir = tmp_path / "page_extract"
    monkeypatch.setattr("baodou_ai.core.automation.PAGE_EXTRACT_DIR", str(page_extract_dir))
    monkeypatch.setattr(
        controller, "_extract_current_browser_url", lambda max_retries=3: "https://example.com"
    )
    monkeypatch.setattr(
        controller,
        "_fetch_webpage_text",
        lambda url: {
            "title": "Example Domain",
            "text": "",
        },
    )

    result = controller.tool_read_current_page(screen_info=None)

    assert result["ok"] is True
    assert result.get("quality") == "partial"
    assert result.get("fallback", {}).get("type") == "read_current_page_partial"
    page_context = result.get("page_context", {})
    assert page_context.get("url") == "https://example.com"
    assert page_context.get("title") == "Example Domain"
    assert page_context.get("quality") == "partial"
    assert page_context.get("content") == ""
    assert page_context.get("source_mode") == "extract"
    record_files = list(page_extract_dir.glob("page_*.txt"))
    assert len(record_files) == 1
    assert "(空)" in record_files[0].read_text(encoding="utf-8")


def test_tool_read_current_page_creates_new_file_for_each_success(monkeypatch, tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    page_extract_dir = tmp_path / "page_extract"
    monkeypatch.setattr("baodou_ai.core.automation.PAGE_EXTRACT_DIR", str(page_extract_dir))
    urls = iter(["https://example.com/1", "https://example.com/2"])
    contents = iter(
        [
            {"title": "Page 1", "text": "第一篇网页正文"},
            {"title": "Page 2", "text": "第二篇网页正文"},
        ]
    )
    monkeypatch.setattr(
        controller, "_extract_current_browser_url", lambda max_retries=3: next(urls)
    )
    monkeypatch.setattr(controller, "_fetch_webpage_text", lambda url: next(contents))

    first = controller.tool_read_current_page(screen_info=None)
    second = controller.tool_read_current_page(screen_info=None)

    assert first["ok"] is True
    assert second["ok"] is True
    record_files = sorted(page_extract_dir.glob("page_*.txt"))
    assert len(record_files) == 2


def test_tool_read_current_page_stops_before_fetch(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    fetch_called = []

    monkeypatch.setattr(
        controller, "_fetch_webpage_text", lambda *args, **kwargs: fetch_called.append(args)
    )

    result = ToolExecutor(controller).execute(
        "read_current_page",
        {"mode": "extract"},
        should_stop=lambda: True,
    )

    assert result == {
        "ok": False,
        "summary": "工具执行已中断",
        "error": "用户已停止当前任务",
    }
    assert fetch_called == []


def test_tool_read_current_page_has_total_timeout(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    monkeypatch.setattr(page_reader_module, "PAGE_READ_TOTAL_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        controller,
        "_extract_current_browser_url",
        lambda max_retries=3: time.sleep(0.02) or "https://example.com",
    )

    result = controller.tool_read_current_page(screen_info=None)

    assert result["ok"] is False
    assert result["summary"] == "读取当前网页失败"
    assert "超时" in str(result["error"])
    assert result.get("fallback", {}).get("type") == "read_current_page_timeout"


def test_tool_read_current_page_times_out_blocking_fetch(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    monkeypatch.setattr(page_reader_module, "PAGE_READ_TOTAL_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(
        controller,
        "_extract_current_browser_url",
        lambda max_retries=3: "https://example.com",
    )
    monkeypatch.setattr(
        controller,
        "_fetch_webpage_text",
        lambda url: time.sleep(0.2) or {"title": "late", "text": "late"},
    )

    started_at = time.perf_counter()
    result = controller.tool_read_current_page(screen_info=None)
    elapsed = time.perf_counter() - started_at

    assert result["ok"] is False
    assert result.get("fallback", {}).get("type") == "read_current_page_timeout"
    assert elapsed < 0.15


def test_fetch_webpage_text_rejects_expired_deadline():
    controller = AutomationController(Config())
    expired_deadline = page_reader_module.automation_exports().time.monotonic() - 0.01

    with pytest.raises(TimeoutError):
        controller._fetch_webpage_text("https://example.com", deadline=expired_deadline)


def test_build_webpage_fetch_url_candidates_adds_http_and_trimmed_slash():
    candidates = AutomationController._build_webpage_fetch_url_candidates(
        "https://www.miniyifan.com.cn/archives/bao-dou-dian-nao/?a=1#top"
    )

    assert candidates == [
        "https://www.miniyifan.com.cn/archives/bao-dou-dian-nao/?a=1#top",
        "http://www.miniyifan.com.cn/archives/bao-dou-dian-nao/?a=1#top",
        "https://www.miniyifan.com.cn/archives/bao-dou-dian-nao?a=1#top",
        "http://www.miniyifan.com.cn/archives/bao-dou-dian-nao?a=1#top",
    ]


def test_fetch_webpage_text_falls_back_to_http_and_trimmed_slash(monkeypatch):
    controller = AutomationController(Config())
    attempted_urls = []

    def fake_download(url, timeout_seconds=15, should_stop=None, deadline=None):
        attempted_urls.append(url)
        if url == "http://www.miniyifan.com.cn/archives/bao-dou-dian-nao":
            return {
                "title": "包豆电脑",
                "text": "正文",
            }
        raise RuntimeError("下载网页失败: simulated")

    monkeypatch.setattr(controller, "_download_and_extract_webpage_text", fake_download)

    result = controller._fetch_webpage_text("https://www.miniyifan.com.cn/archives/bao-dou-dian-nao/")

    assert attempted_urls == [
        "https://www.miniyifan.com.cn/archives/bao-dou-dian-nao/",
        "http://www.miniyifan.com.cn/archives/bao-dou-dian-nao/",
        "https://www.miniyifan.com.cn/archives/bao-dou-dian-nao",
        "http://www.miniyifan.com.cn/archives/bao-dou-dian-nao",
    ]
    assert result["url"] == "http://www.miniyifan.com.cn/archives/bao-dou-dian-nao"
    assert result["title"] == "包豆电脑"
    assert result["text"] == "正文"


def test_tool_read_current_page_uses_final_fallback_url(monkeypatch, tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    page_extract_dir = tmp_path / "page_extract"
    monkeypatch.setattr("baodou_ai.core.automation.PAGE_EXTRACT_DIR", str(page_extract_dir))
    monkeypatch.setattr(
        controller,
        "_extract_current_browser_url",
        lambda max_retries=3, should_stop=None, deadline=None: "https://example.com/post/",
    )
    monkeypatch.setattr(
        controller,
        "_fetch_webpage_text",
        lambda url, should_stop=None, deadline=None: {
            "url": "http://example.com/post",
            "title": "Fallback Page",
            "text": "fallback content",
        },
    )

    result = controller.tool_read_current_page(screen_info=None)

    assert result["ok"] is True
    assert result["url"] == "http://example.com/post"
    assert result["page_context"]["url"] == "http://example.com/post"
    record_files = list(page_extract_dir.glob("page_*.txt"))
    assert len(record_files) == 1
    assert "链接: http://example.com/post" in record_files[0].read_text(encoding="utf-8")


def test_tool_read_current_page_chunk_stop_keeps_current_index():
    controller = AutomationController(Config())
    controller._page_reader_state = {
        "url": "https://example.com",
        "title": "Example",
        "content": "chunk one\n\nchunk two",
        "chunks": ["chunk one", "chunk two"],
        "current_chunk_index": 0,
    }

    result = ToolExecutor(controller).execute(
        "read_current_page",
        {"mode": "chunk", "chunk_index": 1},
        should_stop=lambda: True,
    )

    assert result["summary"] == "工具执行已中断"
    assert controller._page_reader_state["current_chunk_index"] == 0


def test_tool_read_current_document_rejects_unsupported_frontmost_app():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Finder",
        "bundle_id": "com.apple.finder",
        "identifier": "com.apple.finder",
        "pid": 456,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"

    result = controller.tool_read_current_document(screen_info=None)

    assert result["ok"] is False
    assert result["summary"] == "读取当前文档失败"
    assert "仅支持在以下前台应用中使用" in str(result["error"])
    assert result.get("fallback", {}).get("type") == "read_current_document_not_supported_app"


def test_tool_read_current_document_rejects_ide_extract_without_position(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Trae CN",
        "bundle_id": "cn.trae.app",
        "identifier": "cn.trae.app",
        "pid": 456,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"

    operations = []
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: operations.append("backup"))
    monkeypatch.setattr(
        controller, "_press_escape_repeated", lambda count=2: operations.append(("esc", count))
    )
    monkeypatch.setattr(
        controller,
        "_press_hotkey_with_modifier",
        lambda modifier, key: operations.append(("hotkey", modifier, key)),
    )

    result = controller.tool_read_current_document(screen_info=None)

    assert result["ok"] is False
    assert result["summary"] == "读取当前文档失败"
    assert "当前前台应用是编程 IDE" in str(result["error"])
    assert "screen_index 和 position" in str(result["error"])
    assert "未执行任何提取操作" in str(result["error"])
    assert result.get("fallback", {}).get("type") == "read_current_document_ide_requires_position"
    assert operations == []


def test_tool_read_current_document_accepts_supported_ide_with_position(monkeypatch, tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "TRAE CN",
        "bundle_id": "cn.trae.app",
        "identifier": "cn.trae.app",
        "pid": 123,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )

    copies = []
    restore_calls = []
    operations = []
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyperclip.copy", lambda text: copies.append(text)
    )
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller,
        "_restore_clipboard_text",
        lambda has_backup, previous_text: restore_calls.append((has_backup, previous_text)),
    )
    monkeypatch.setattr(
        controller, "_press_escape_repeated", lambda count=2: operations.append(("esc", count))
    )
    monkeypatch.setattr(
        controller,
        "_focus_document_position",
        lambda screen_index, position, screen_info=None: operations.append(
            ("focus", screen_index, position)
        ),
    )
    monkeypatch.setattr(
        controller,
        "_press_hotkey_with_modifier",
        lambda modifier, key: operations.append(("hotkey", modifier, key)),
    )
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: "def hello_world():\n    return 'cursor'\n",
    )

    result = controller.tool_read_current_document(
        screen_index=0,
        position=[320, 420],
        screen_info=[
            {"index": 0, "x": 0, "y": 0, "width": 1440, "height": 900, "is_primary": True}
        ],
    )

    assert result["ok"] is True
    assert result.get("document_context") == {
        "app_name": "TRAE CN",
        "content": "def hello_world():\n    return 'cursor'",
        "chunk_index": 0,
        "total_chunks": 1,
        "source_mode": "extract",
        "has_more": False,
    }
    assert operations == [
        ("esc", 2),
        ("focus", 0, [320, 420]),
        ("hotkey", "command", "a"),
        ("hotkey", "command", "c"),
    ]
    assert len(copies) == 1
    assert copies[0].startswith("__baodou_ai_document_extract_")
    assert restore_calls == [(True, "old clipboard")]
    record_files = list(document_extract_dir.glob("document_*.txt"))
    assert len(record_files) == 1
    record_content = record_files[0].read_text(encoding="utf-8")
    assert "应用: TRAE CN" in record_content
    assert "return 'cursor'" in record_content


def test_get_document_app_family_recognizes_trae_solo_cn():
    family = AutomationController._get_document_app_family(
        {
            "app_name": "TRAE SOLO CN",
            "bundle_id": "cn.trae.solo.app",
            "identifier": "cn.trae.solo.app",
        }
    )

    assert family == "trae"


def test_get_document_app_family_recognizes_trae():
    family = AutomationController._get_document_app_family(
        {
            "app_name": "TRAE",
            "bundle_id": "com.trae.app",
            "identifier": "com.trae.app",
        }
    )

    assert family == "trae"


def test_tool_read_current_document_success_writes_record_and_returns_context(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Microsoft Word",
        "bundle_id": "com.microsoft.Word",
        "identifier": "com.microsoft.Word",
        "pid": 123,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )
    document_anchor_dir = tmp_path / "doc_anchor"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(document_anchor_dir))

    copies = []
    restore_calls = []
    operations = []
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyperclip.copy", lambda text: copies.append(text)
    )
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller,
        "_restore_clipboard_text",
        lambda has_backup, previous_text: restore_calls.append((has_backup, previous_text)),
    )
    monkeypatch.setattr(
        controller, "_press_escape_repeated", lambda count=2: operations.append(("esc", count))
    )
    monkeypatch.setattr(
        controller,
        "_focus_document_position",
        lambda screen_index, position, screen_info=None: operations.append(
            ("focus", screen_index, position)
        ),
    )
    monkeypatch.setattr(
        controller,
        "_press_hotkey_with_modifier",
        lambda modifier, key: operations.append(("hotkey", modifier, key)),
    )
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: "这是示例文档正文。\n用于测试 read_current_document。",
    )

    result = controller.tool_read_current_document(
        screen_index=0,
        position=[500, 500],
        screen_info=[
            {"index": 0, "x": 0, "y": 0, "width": 1440, "height": 900, "is_primary": True}
        ],
    )

    assert result["ok"] is True
    assert "进入临时文档上下文" in result["summary"]
    assert result.get("document_context") == {
        "app_name": "Microsoft Word",
        "content": "这是示例文档正文。\n用于测试 read_current_document。",
        "chunk_index": 0,
        "total_chunks": 1,
        "source_mode": "extract",
        "has_more": False,
    }
    assert operations == [
        ("esc", 2),
        ("focus", 0, [500, 500]),
        ("hotkey", "command", "a"),
        ("hotkey", "command", "c"),
    ]
    assert len(copies) == 1
    assert copies[0].startswith("__baodou_ai_document_extract_")
    assert restore_calls == [(True, "old clipboard")]
    record_files = list(document_extract_dir.glob("document_*.txt"))
    assert len(record_files) == 1
    record_content = record_files[0].read_text(encoding="utf-8")
    assert "应用: Microsoft Word" in record_content
    assert "正文:" in record_content
    assert "用于测试 read_current_document。" in record_content


def test_tool_read_current_document_interrupt_restores_clipboard_and_window(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Microsoft Word",
        "bundle_id": "com.microsoft.Word",
        "identifier": "com.microsoft.Word",
        "pid": 123,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    window_events = []
    restore_calls = []
    controller._hide_windows = lambda: window_events.append("hide")
    controller._show_windows = lambda: window_events.append("show")
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller,
        "_restore_clipboard_text",
        lambda has_backup, previous_text: restore_calls.append((has_backup, previous_text)),
    )
    monkeypatch.setattr(controller, "_press_escape_repeated", lambda count=2: None)
    monkeypatch.setattr(controller, "_press_hotkey_with_modifier", lambda modifier, key: None)
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: (_ for _ in ()).throw(
            ToolInterrupted("stop")
        ),
    )

    result = ToolExecutor(controller).execute(
        "read_current_document",
        {"mode": "extract"},
        should_stop=lambda: False,
    )

    assert result == {
        "ok": False,
        "summary": "工具执行已中断",
        "error": "用户已停止当前任务",
    }
    assert window_events == ["hide", "show"]
    assert restore_calls == [(True, "old clipboard")]


def test_tool_read_current_document_chunk_stop_does_not_advance_index():
    controller = AutomationController(Config())
    controller._document_reader_state = {
        "app_name": "TextEdit",
        "app_family": "textedit",
        "content": "first\n\nsecond",
        "chunks": ["first", "second"],
        "current_chunk_index": 0,
    }

    result = ToolExecutor(controller).execute(
        "read_current_document",
        {"mode": "chunk", "chunk_index": 1},
        should_stop=lambda: True,
    )

    assert result["summary"] == "工具执行已中断"
    assert controller._document_reader_state["current_chunk_index"] == 0


def test_tool_read_current_document_chunk_reads_requested_block_after_extract(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "TextEdit",
        "bundle_id": "com.apple.TextEdit",
        "identifier": "com.apple.TextEdit",
        "pid": 123,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )
    copies = []
    restore_calls = []
    operations = []
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyperclip.copy", lambda text: copies.append(text)
    )
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller,
        "_restore_clipboard_text",
        lambda has_backup, previous_text: restore_calls.append((has_backup, previous_text)),
    )
    monkeypatch.setattr(
        controller, "_press_escape_repeated", lambda count=2: operations.append(("esc", count))
    )
    monkeypatch.setattr(
        controller,
        "_press_hotkey_with_modifier",
        lambda modifier, key: operations.append(("hotkey", modifier, key)),
    )
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.press", lambda key: operations.append(("press", key))
    )
    first_block = _build_token_heavy_block(controller, "first", 2050)
    second_block = _build_token_heavy_block(
        controller,
        "second",
        2050,
        leading_text="SECOND CHUNK UNIQUE ANCHOR START",
    )
    third_block = _build_token_heavy_block(controller, "third", 2050)
    extracted_content = first_block + "\n\n" + second_block + "\n\n" + third_block
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: extracted_content,
    )

    extract_result = controller.tool_read_current_document(screen_info=None)
    operations.clear()
    copies.clear()
    restore_calls.clear()
    chunk_result = controller.tool_read_current_document(
        mode="chunk", chunk_index=1, follow_view=True, screen_info=None
    )

    assert extract_result["ok"] is True
    assert extract_result["document_context"]["chunk_index"] == 0
    assert extract_result["document_context"]["total_chunks"] == 3
    assert extract_result["document_context"]["has_more"] is True
    assert chunk_result["ok"] is True
    assert chunk_result["document_context"] == {
        "app_name": "TextEdit",
        "content": second_block,
        "chunk_index": 1,
        "total_chunks": 3,
        "source_mode": "chunk",
        "has_more": True,
    }
    assert chunk_result["view_follow_attempted"] is True
    assert chunk_result["view_followed"] is True
    assert chunk_result["view_follow_message"] == "已尝试将文档视图跳到当前块附近。"
    assert operations == [
        ("esc", 2),
        ("hotkey", "command", "f"),
        ("hotkey", "command", "a"),
        ("hotkey", "command", "v"),
        ("press", "enter"),
        ("esc", 2),
    ]
    assert len(copies) == 1
    assert len(copies[0]) == 20
    assert "\n" not in copies[0]
    assert copies[0] in second_block
    assert restore_calls == [(True, "old clipboard")]


def test_tool_read_current_document_next_advances_and_keeps_last_chunk_on_end(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Preview",
        "bundle_id": "com.apple.Preview",
        "identifier": "com.apple.Preview",
        "pid": 123,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller, "_restore_clipboard_text", lambda has_backup, previous_text: None
    )
    monkeypatch.setattr(controller, "_press_escape_repeated", lambda count=2: None)
    monkeypatch.setattr(controller, "_press_hotkey_with_modifier", lambda modifier, key: None)
    first_block = _build_token_heavy_block(controller, "previewfirst", 2050)
    second_block = _build_token_heavy_block(controller, "previewsecond", 2050)
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: first_block + "\n\n" + second_block,
    )

    controller.tool_read_current_document(screen_info=None)
    next_result = controller.tool_read_current_document(
        mode="next", follow_view=True, screen_info=None
    )
    no_more_result = controller.tool_read_current_document(mode="next", screen_info=None)

    assert next_result["ok"] is True
    assert next_result["document_context"] == {
        "app_name": "Preview",
        "content": second_block,
        "chunk_index": 1,
        "total_chunks": 2,
        "source_mode": "next",
        "has_more": False,
    }
    assert next_result["view_follow_attempted"] is False
    assert next_result["view_followed"] is False
    assert "当前文档应用暂不支持视觉跳转" in next_result["view_follow_message"]
    assert no_more_result["ok"] is False
    assert no_more_result.get("fallback", {}).get("type") == "read_current_document_no_more_chunks"
    assert controller._document_reader_state["current_chunk_index"] == 1


def test_tool_read_current_document_chunk_requires_extract_first():
    controller = AutomationController(Config())

    result = controller.tool_read_current_document(mode="chunk", chunk_index=0, screen_info=None)

    assert result["ok"] is False
    assert result.get("fallback", {}).get("type") == "read_current_document_need_extract_first"


def test_tool_read_current_document_search_requires_extract_first():
    controller = AutomationController(Config())

    result = controller.tool_read_current_document(mode="search", query="退款", screen_info=None)

    assert result["ok"] is False
    assert result.get("fallback", {}).get("type") == "read_current_document_need_extract_first"


def test_tool_read_current_document_search_returns_matching_paragraphs(monkeypatch, tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Microsoft Word",
        "bundle_id": "com.microsoft.Word",
        "identifier": "com.microsoft.Word",
        "pid": 123,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None
    copies = []
    restore_calls = []
    operations = []
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )
    controller._backup_clipboard_text = lambda: (True, "old clipboard")
    controller._restore_clipboard_text = lambda has_backup, previous_text: restore_calls.append(
        (has_backup, previous_text)
    )
    controller._press_escape_repeated = lambda count=2: operations.append(("esc", count))
    controller._press_hotkey_with_modifier = lambda modifier, key: operations.append(
        ("hotkey", modifier, key)
    )
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyperclip.copy", lambda text: copies.append(text)
    )
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.press", lambda key: operations.append(("press", key))
    )
    controller._set_document_reader_state(
        app_name="Microsoft Word",
        app_family="word",
        content=(
            "第一段介绍背景。\n\n"
            "第二段包含退款政策和违约金说明，明确写到退款申请后 7 天内处理。\n\n"
            "第三段是其他补充条款。"
        ),
        record_path=tmp_path / "document.txt",
    )

    result = controller.tool_read_current_document(
        mode="search", query="退款 违约金", top_k=2, follow_view=True, screen_info=None
    )

    assert result["ok"] is True
    assert "搜索结果已进入临时文档上下文" in result["summary"]
    assert result["document_context"] == {
        "app_name": "Microsoft Word",
        "content": (
            "[命中 1] 第 1/1 块\n"
            "匹配词: 退款、违约金\n"
            "第二段包含退款政策和违约金说明，明确写到退款申请后 7 天内处理。"
        ),
        "chunk_index": 0,
        "total_chunks": 0,
        "source_mode": "search",
        "has_more": False,
        "query": "退款 违约金",
        "result_count": 1,
    }
    assert len(result["search_results"]) == 1
    assert result["search_results"][0]["chunk_index"] == 0
    assert result["search_results"][0]["total_chunks"] == 1
    assert result["view_follow_attempted"] is True
    assert result["view_followed"] is True
    assert result["view_follow_message"] == "已尝试将文档视图跳到搜索词匹配位置附近。"
    assert operations == [
        ("esc", 2),
        ("hotkey", "command", "f"),
        ("hotkey", "command", "a"),
        ("hotkey", "command", "v"),
        ("press", "enter"),
        ("esc", 2),
    ]
    assert copies == ["退款 违约金"]
    assert restore_calls == [(True, "old clipboard")]


def test_tool_read_current_document_search_returns_line_context_for_code_apps(tmp_path):
    controller = AutomationController(Config())
    controller._current_os = "Darwin"
    controller._set_document_reader_state(
        app_name="TRAE CN",
        app_family="trae",
        content=(
            "def bootstrap():\n"
            "    pass\n"
            "\n"
            "def load_user_profile(user_id):\n"
            "    profile = fetch_profile(user_id)\n"
            "    return profile\n"
            "\n"
            "def render_view():\n"
            "    return 'ok'\n"
        ),
        record_path=tmp_path / "document.txt",
    )

    result = controller.tool_read_current_document(
        mode="search", query="load_user_profile", follow_view=True, screen_info=None
    )

    assert result["ok"] is True
    assert result["document_context"]["source_mode"] == "search"
    assert result["document_context"]["app_name"] == "TRAE CN"
    assert "load_user_profile" in result["document_context"]["content"]
    assert "第 1/1 块" in result["document_context"]["content"]
    assert result["search_results"][0]["chunk_index"] == 0
    assert result["search_results"][0]["total_chunks"] == 1
    assert result["view_follow_attempted"] is False
    assert result["view_followed"] is False
    assert (
        result["view_follow_message"]
        == "当前文档应用暂不支持视觉跳转，仅更新了搜索结果文本上下文。"
    )


def test_tool_read_current_document_search_returns_no_results(tmp_path):
    controller = AutomationController(Config())
    controller._set_document_reader_state(
        app_name="Preview",
        app_family="preview",
        content="这里是示例文档正文，没有你想找的关键词。",
        record_path=tmp_path / "document.txt",
    )

    result = controller.tool_read_current_document(mode="search", query="退款", screen_info=None)

    assert result["ok"] is False
    assert result.get("fallback", {}).get("type") == "read_current_document_search_no_results"
    assert "未在当前文档中找到" in str(result["error"])


def test_tool_read_current_document_search_can_disable_follow_view(tmp_path):
    controller = AutomationController(Config())
    controller._set_document_reader_state(
        app_name="Microsoft Word",
        app_family="word",
        content="第一段。\n\n第二段包含退款和违约金内容。\n\n第三段。",
        record_path=tmp_path / "document.txt",
    )

    result = controller.tool_read_current_document(
        mode="search",
        query="退款 违约金",
        follow_view=False,
        screen_info=None,
    )

    assert result["ok"] is True
    assert result["view_follow_attempted"] is False
    assert result["view_followed"] is False
    assert result["view_follow_message"] == "已关闭文档视觉跳转，仅更新了搜索结果文本上下文。"


def test_tool_read_current_document_search_skips_view_follow_when_frontmost_app_changes(tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "WPS",
        "bundle_id": "com.kingsoft.wpsoffice.mac",
        "identifier": "com.kingsoft.wpsoffice.mac",
        "pid": 123,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    controller._set_document_reader_state(
        app_name="Microsoft Word",
        app_family="word",
        content="第一段。\n\n第二段包含退款和违约金内容。\n\n第三段。",
        record_path=tmp_path / "document.txt",
    )

    result = controller.tool_read_current_document(
        mode="search", query="退款 违约金", follow_view=True, screen_info=None
    )

    assert result["ok"] is True
    assert result["view_follow_attempted"] is False
    assert result["view_followed"] is False
    assert "当前前台应用已不是提取文档时的同类应用" in result["view_follow_message"]


def test_tool_read_current_document_search_still_attempts_view_follow_with_repeated_matches(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "TextEdit",
        "bundle_id": "com.apple.TextEdit",
        "identifier": "com.apple.TextEdit",
        "pid": 123,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None
    operations = []
    copies = []
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller, "_restore_clipboard_text", lambda has_backup, previous_text: None
    )
    monkeypatch.setattr(
        controller, "_press_escape_repeated", lambda count=2: operations.append(("esc", count))
    )
    monkeypatch.setattr(
        controller,
        "_press_hotkey_with_modifier",
        lambda modifier, key: operations.append(("hotkey", modifier, key)),
    )
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyperclip.copy", lambda text: copies.append(text)
    )
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyautogui.press", lambda key: operations.append(("press", key))
    )
    repeated_paragraph = "退款和违约金说明在这里继续展开"
    controller._set_document_reader_state(
        app_name="TextEdit",
        app_family="textedit",
        content=f"{repeated_paragraph}\n\n{repeated_paragraph}\n\n其他补充内容。",
        record_path=tmp_path / "document.txt",
    )

    result = controller.tool_read_current_document(
        mode="search", query="退款 违约金", follow_view=True, screen_info=None
    )

    assert result["ok"] is True
    assert result["view_follow_attempted"] is True
    assert result["view_followed"] is True
    assert result["view_follow_message"] == "已尝试将文档视图跳到搜索词匹配位置附近。"
    assert copies == ["退款 违约金"]
    assert operations == [
        ("esc", 2),
        ("hotkey", "command", "f"),
        ("hotkey", "command", "a"),
        ("hotkey", "command", "v"),
        ("press", "enter"),
        ("esc", 2),
    ]


def test_tool_read_current_document_chunk_can_disable_follow_view(monkeypatch, tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Microsoft Word",
        "bundle_id": "com.microsoft.Word",
        "identifier": "com.microsoft.Word",
        "pid": 123,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller, "_restore_clipboard_text", lambda has_backup, previous_text: None
    )
    monkeypatch.setattr(controller, "_press_escape_repeated", lambda count=2: None)
    monkeypatch.setattr(controller, "_press_hotkey_with_modifier", lambda modifier, key: None)
    first_block = _build_token_heavy_block(controller, "wordfirst", 2050)
    second_block = _build_token_heavy_block(
        controller,
        "wordsecond",
        2050,
        leading_text="SECOND CHUNK UNIQUE ANCHOR START",
    )
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: first_block + "\n\n" + second_block,
    )

    controller.tool_read_current_document(screen_info=None)
    monkeypatch.setattr(
        controller,
        "_press_escape_repeated",
        lambda count=2: (_ for _ in ()).throw(AssertionError("should not follow view")),
    )
    monkeypatch.setattr(
        controller,
        "_press_hotkey_with_modifier",
        lambda modifier, key: (_ for _ in ()).throw(AssertionError("should not follow view")),
    )
    result = controller.tool_read_current_document(
        mode="chunk", chunk_index=1, follow_view=False, screen_info=None
    )

    assert result["ok"] is True
    assert result["view_follow_attempted"] is False
    assert result["view_followed"] is False
    assert result["view_follow_message"] == "已关闭文档视觉跳转，仅更新了当前块文本上下文。"


def test_tool_read_current_document_chunk_skips_view_follow_when_frontmost_app_changes(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    frontmost_apps = iter(
        [
            {
                "app_name": "Microsoft Word",
                "bundle_id": "com.microsoft.Word",
                "identifier": "com.microsoft.Word",
                "pid": 123,
            },
            {
                "app_name": "WPS",
                "bundle_id": "com.kingsoft.wpsoffice.mac",
                "identifier": "com.kingsoft.wpsoffice.mac",
                "pid": 456,
            },
        ]
    )
    fake_platform.get_frontmost_app_info = lambda: next(frontmost_apps)
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller, "_restore_clipboard_text", lambda has_backup, previous_text: None
    )
    monkeypatch.setattr(controller, "_press_escape_repeated", lambda count=2: None)
    monkeypatch.setattr(controller, "_press_hotkey_with_modifier", lambda modifier, key: None)
    first_block = _build_token_heavy_block(controller, "frontfirst", 2050)
    second_block = _build_token_heavy_block(
        controller,
        "frontsecond",
        2050,
        leading_text="SECOND CHUNK UNIQUE ANCHOR START",
    )
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: first_block + "\n\n" + second_block,
    )

    controller.tool_read_current_document(screen_info=None)
    monkeypatch.setattr(
        controller,
        "_press_escape_repeated",
        lambda count=2: (_ for _ in ()).throw(AssertionError("should not follow view")),
    )
    monkeypatch.setattr(
        controller,
        "_press_hotkey_with_modifier",
        lambda modifier, key: (_ for _ in ()).throw(AssertionError("should not follow view")),
    )
    result = controller.tool_read_current_document(
        mode="chunk", chunk_index=1, follow_view=True, screen_info=None
    )

    assert result["ok"] is True
    assert result["view_follow_attempted"] is False
    assert result["view_followed"] is False
    assert "当前前台应用已不是提取文档时的同类应用" in result["view_follow_message"]


def test_tool_read_current_document_chunk_skips_view_follow_when_anchor_is_not_unique(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "TextEdit",
        "bundle_id": "com.apple.TextEdit",
        "identifier": "com.apple.TextEdit",
        "pid": 123,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller, "_restore_clipboard_text", lambda has_backup, previous_text: None
    )
    monkeypatch.setattr(controller, "_press_escape_repeated", lambda count=2: None)
    monkeypatch.setattr(controller, "_press_hotkey_with_modifier", lambda modifier, key: None)
    repeated_block = _build_token_heavy_block(
        controller,
        "repeat",
        2050,
        leading_text="REPEATED ANCHOR PHRASE HERE",
    )
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: repeated_block
        + "\n\n"
        + repeated_block
        + "\n\n"
        + repeated_block,
    )

    controller.tool_read_current_document(screen_info=None)
    monkeypatch.setattr(
        controller,
        "_press_escape_repeated",
        lambda count=2: (_ for _ in ()).throw(AssertionError("should not follow view")),
    )
    monkeypatch.setattr(
        controller,
        "_press_hotkey_with_modifier",
        lambda modifier, key: (_ for _ in ()).throw(AssertionError("should not follow view")),
    )
    result = controller.tool_read_current_document(
        mode="chunk", chunk_index=1, follow_view=True, screen_info=None
    )

    assert result["ok"] is True
    assert result["view_follow_attempted"] is False
    assert result["view_followed"] is False
    assert "锚点在全文中不唯一" in result["view_follow_message"]


def test_tool_read_current_document_returns_focus_retry_when_toolbar_value_is_copied(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Microsoft Word",
        "bundle_id": "com.microsoft.Word",
        "identifier": "com.microsoft.Word",
        "pid": 123,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller, "_restore_clipboard_text", lambda has_backup, previous_text: None
    )
    monkeypatch.setattr(controller, "_press_escape_repeated", lambda count=2: None)
    monkeypatch.setattr(controller, "_press_hotkey_with_modifier", lambda modifier, key: None)
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: "Calibri",
    )

    result = controller.tool_read_current_document(screen_info=None)

    assert result["ok"] is False
    assert result.get("fallback", {}).get("type") == "read_current_document_focus_retry"
    assert "传入正文区域坐标" in str(result["error"])
    assert list(document_extract_dir.glob("document_*.txt")) == []


def test_tool_read_current_document_returns_copy_failed_when_positioned_copy_still_fails(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Preview",
        "bundle_id": "com.apple.Preview",
        "identifier": "com.apple.Preview",
        "pid": 123,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Darwin"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller, "_restore_clipboard_text", lambda has_backup, previous_text: None
    )
    monkeypatch.setattr(controller, "_press_escape_repeated", lambda count=2: None)
    monkeypatch.setattr(
        controller,
        "_focus_document_position",
        lambda screen_index, position, screen_info=None: None,
    )
    monkeypatch.setattr(controller, "_press_hotkey_with_modifier", lambda modifier, key: None)
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: "",
    )

    result = controller.tool_read_current_document(
        screen_index=0,
        position=[420, 360],
        screen_info=[
            {"index": 0, "x": 0, "y": 0, "width": 1440, "height": 900, "is_primary": True}
        ],
    )

    assert result["ok"] is False
    assert result.get("fallback", {}).get("type") == "read_current_document_copy_failed"
    assert "请改用图片或截图分析当前文档内容" in str(result["error"])
    assert list(document_extract_dir.glob("document_*.txt")) == []


def test_tool_read_current_document_windows_rejects_unsupported_frontmost_app():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "File Explorer",
        "bundle_id": "",
        "identifier": "explorer.exe",
        "pid": 456,
    }
    controller._platform_adapter = fake_platform
    controller._current_os = "Windows"

    result = controller.tool_read_current_document(screen_info=None)

    assert result["ok"] is False
    assert result["summary"] == "读取当前文档失败"
    assert "仅支持在以下前台应用中使用" in str(result["error"])
    assert result.get("fallback", {}).get("type") == "read_current_document_not_supported_app"


def test_tool_read_current_document_windows_rejects_ide_extract_without_position(monkeypatch):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Visual Studio Code",
        "bundle_id": "",
        "identifier": "code.exe",
        "pid": 456,
    }
    fake_platform.get_hotkey_modifier = lambda: "ctrl"
    controller._platform_adapter = fake_platform
    controller._current_os = "Windows"

    operations = []
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: operations.append("backup"))
    monkeypatch.setattr(
        controller, "_press_escape_repeated", lambda count=2: operations.append(("esc", count))
    )
    monkeypatch.setattr(
        controller,
        "_press_hotkey_with_modifier",
        lambda modifier, key: operations.append(("hotkey", modifier, key)),
    )

    result = controller.tool_read_current_document(screen_info=None)

    assert result["ok"] is False
    assert "当前前台应用是编程 IDE" in str(result["error"])
    assert result.get("fallback", {}).get("type") == "read_current_document_ide_requires_position"
    assert operations == []


def test_tool_read_current_document_windows_accepts_supported_ide_with_position(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Visual Studio Code",
        "bundle_id": "",
        "identifier": "code.exe",
        "pid": 123,
    }
    fake_platform.get_hotkey_modifier = lambda: "ctrl"
    controller._platform_adapter = fake_platform
    controller._current_os = "Windows"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )

    copies = []
    restore_calls = []
    operations = []
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyperclip.copy", lambda text: copies.append(text)
    )
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller,
        "_restore_clipboard_text",
        lambda has_backup, previous_text: restore_calls.append((has_backup, previous_text)),
    )
    monkeypatch.setattr(
        controller, "_press_escape_repeated", lambda count=2: operations.append(("esc", count))
    )
    monkeypatch.setattr(
        controller,
        "_focus_document_position",
        lambda screen_index, position, screen_info=None: operations.append(
            ("focus", screen_index, position)
        ),
    )
    monkeypatch.setattr(
        controller,
        "_press_hotkey_with_modifier",
        lambda modifier, key: operations.append(("hotkey", modifier, key)),
    )
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: "def hello_windows():\n    return 'code'\n",
    )

    result = controller.tool_read_current_document(
        screen_index=0,
        position=[320, 420],
        screen_info=[
            {"index": 0, "x": 0, "y": 0, "width": 1440, "height": 900, "is_primary": True}
        ],
    )

    assert result["ok"] is True
    assert result.get("document_context") == {
        "app_name": "Visual Studio Code",
        "content": "def hello_windows():\n    return 'code'",
        "chunk_index": 0,
        "total_chunks": 1,
        "source_mode": "extract",
        "has_more": False,
    }
    assert operations == [
        ("esc", 2),
        ("focus", 0, [320, 420]),
        ("hotkey", "ctrl", "a"),
        ("hotkey", "ctrl", "c"),
    ]
    assert len(copies) == 1
    assert copies[0].startswith("__baodou_ai_document_extract_")
    assert restore_calls == [(True, "old clipboard")]
    record_files = list(document_extract_dir.glob("document_*.txt"))
    assert len(record_files) == 1
    record_content = record_files[0].read_text(encoding="utf-8")
    assert "应用: Visual Studio Code" in record_content
    assert "return 'code'" in record_content


def test_tool_read_current_document_windows_success_writes_record_and_returns_context(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Microsoft Word",
        "bundle_id": "",
        "identifier": "winword.exe",
        "pid": 123,
    }
    fake_platform.get_hotkey_modifier = lambda: "ctrl"
    controller._platform_adapter = fake_platform
    controller._current_os = "Windows"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )

    copies = []
    restore_calls = []
    operations = []
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyperclip.copy", lambda text: copies.append(text)
    )
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller,
        "_restore_clipboard_text",
        lambda has_backup, previous_text: restore_calls.append((has_backup, previous_text)),
    )
    monkeypatch.setattr(
        controller, "_press_escape_repeated", lambda count=2: operations.append(("esc", count))
    )
    monkeypatch.setattr(
        controller,
        "_press_hotkey_with_modifier",
        lambda modifier, key: operations.append(("hotkey", modifier, key)),
    )
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: "这是 Windows Word 正文。\n用于测试 read_current_document。",
    )

    result = controller.tool_read_current_document(screen_info=None)

    assert result["ok"] is True
    assert result.get("document_context") == {
        "app_name": "Microsoft Word",
        "content": "这是 Windows Word 正文。\n用于测试 read_current_document。",
        "chunk_index": 0,
        "total_chunks": 1,
        "source_mode": "extract",
        "has_more": False,
    }
    assert operations == [
        ("esc", 2),
        ("hotkey", "ctrl", "a"),
        ("hotkey", "ctrl", "c"),
    ]
    assert len(copies) == 1
    assert copies[0].startswith("__baodou_ai_document_extract_")
    assert restore_calls == [(True, "old clipboard")]
    record_files = list(document_extract_dir.glob("document_*.txt"))
    assert len(record_files) == 1
    assert "Windows Word 正文" in record_files[0].read_text(encoding="utf-8")


def test_tool_read_current_document_windows_wps_prefocuses_body_before_copy(monkeypatch, tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "WPS",
        "bundle_id": "",
        "identifier": "kwps.exe",
        "pid": 123,
    }
    fake_platform.get_frontmost_window_info = lambda: {
        "pid": 123,
        "identifier": "kwps.exe",
        "app_name": "WPS",
        "title": "示例文档 - WPS",
        "bounds": {"x": 100, "y": 80, "width": 1200, "height": 900},
    }
    fake_platform.get_hotkey_modifier = lambda: "ctrl"
    controller._platform_adapter = fake_platform
    controller._current_os = "Windows"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )

    copies = []
    restore_calls = []
    operations = []
    monkeypatch.setattr(
        "baodou_ai.core.automation.pyperclip.copy", lambda text: copies.append(text)
    )
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller,
        "_restore_clipboard_text",
        lambda has_backup, previous_text: restore_calls.append((has_backup, previous_text)),
    )
    monkeypatch.setattr(
        controller, "_press_escape_repeated", lambda count=2: operations.append(("esc", count))
    )
    monkeypatch.setattr(
        controller,
        "_press_hotkey_with_modifier",
        lambda modifier, key: operations.append(("hotkey", modifier, key)),
    )
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: "这是 WPS 正文。\n用于测试自动聚焦。",
    )

    result = controller.tool_read_current_document(screen_info=None)

    assert result["ok"] is True
    assert fake_platform.calls[:2] == [
        ("move_cursor", 700, 458, controller._config.mouse_config.get("move_duration", 0.1)),
        ("click", "left", 1),
    ]
    assert operations == [
        ("esc", 2),
        ("hotkey", "ctrl", "a"),
        ("hotkey", "ctrl", "c"),
    ]
    assert result["document_context"]["app_name"] == "WPS"
    assert "WPS 正文" in result["document_context"]["content"]
    assert copies[0].startswith("__baodou_ai_document_extract_")
    assert restore_calls == [(True, "old clipboard")]


def test_tool_read_current_document_windows_chunk_returns_context_without_follow_view(tmp_path):
    controller = AutomationController(Config())
    controller._current_os = "Windows"
    first_block = _build_token_heavy_block(controller, "winfirst", 2050)
    second_block = _build_token_heavy_block(
        controller, "winsecond", 2050, leading_text="WINDOWS SECOND CHUNK UNIQUE"
    )
    controller._set_document_reader_state(
        app_name="Microsoft Word",
        app_family="word",
        content=first_block + "\n\n" + second_block,
        record_path=tmp_path / "document.txt",
    )

    result = controller.tool_read_current_document(
        mode="chunk", chunk_index=1, follow_view=True, screen_info=None
    )

    assert result["ok"] is True
    assert result["document_context"] == {
        "app_name": "Microsoft Word",
        "content": second_block,
        "chunk_index": 1,
        "total_chunks": 2,
        "source_mode": "chunk",
        "has_more": False,
    }
    assert result["view_follow_attempted"] is False
    assert result["view_followed"] is False
    assert (
        result["view_follow_message"]
        == "Windows V1 暂不支持文档视觉跳转，仅更新了当前块文本上下文。"
    )


def test_tool_read_current_document_windows_search_returns_results_without_follow_view(tmp_path):
    controller = AutomationController(Config())
    controller._current_os = "Windows"
    controller._set_document_reader_state(
        app_name="Microsoft Word",
        app_family="word",
        content="第一段。\n\n第二段包含退款和违约金内容。\n\n第三段。",
        record_path=tmp_path / "document.txt",
    )

    result = controller.tool_read_current_document(
        mode="search",
        query="退款 违约金",
        follow_view=True,
        screen_info=None,
    )

    assert result["ok"] is True
    assert result["view_follow_attempted"] is False
    assert result["view_followed"] is False
    assert (
        result["view_follow_message"]
        == "Windows V1 暂不支持文档视觉跳转，仅更新了搜索结果文本上下文。"
    )
    assert result["document_context"]["result_count"] == 1


def test_tool_read_current_document_windows_returns_focus_retry_when_unpositioned_copy_fails(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Microsoft Word",
        "bundle_id": "",
        "identifier": "winword.exe",
        "pid": 123,
    }
    fake_platform.get_hotkey_modifier = lambda: "ctrl"
    controller._platform_adapter = fake_platform
    controller._current_os = "Windows"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller, "_restore_clipboard_text", lambda has_backup, previous_text: None
    )
    monkeypatch.setattr(controller, "_press_escape_repeated", lambda count=2: None)
    monkeypatch.setattr(controller, "_press_hotkey_with_modifier", lambda modifier, key: None)
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: "",
    )

    result = controller.tool_read_current_document(screen_info=None)

    assert result["ok"] is False
    assert result.get("fallback", {}).get("type") == "read_current_document_focus_retry"
    assert "传入正文区域坐标" in str(result["error"])
    assert list(document_extract_dir.glob("document_*.txt")) == []


def test_tool_read_current_document_windows_returns_copy_failed_when_positioned_copy_fails(
    monkeypatch, tmp_path
):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Microsoft Word",
        "bundle_id": "",
        "identifier": "winword.exe",
        "pid": 123,
    }
    fake_platform.get_hotkey_modifier = lambda: "ctrl"
    controller._platform_adapter = fake_platform
    controller._current_os = "Windows"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    document_extract_dir = tmp_path / "doc_extract"
    monkeypatch.setattr("baodou_ai.core.automation.DOCUMENT_EXTRACT_DIR", str(document_extract_dir))
    monkeypatch.setattr(
        "baodou_ai.core.automation.DOCUMENT_ANCHOR_DIR", str(tmp_path / "doc_anchor")
    )
    monkeypatch.setattr("baodou_ai.core.automation.pyperclip.copy", lambda text: None)
    monkeypatch.setattr(controller, "_backup_clipboard_text", lambda: (True, "old clipboard"))
    monkeypatch.setattr(
        controller, "_restore_clipboard_text", lambda has_backup, previous_text: None
    )
    monkeypatch.setattr(controller, "_press_escape_repeated", lambda count=2: None)
    monkeypatch.setattr(
        controller,
        "_focus_document_position",
        lambda screen_index, position, screen_info=None: None,
    )
    monkeypatch.setattr(controller, "_press_hotkey_with_modifier", lambda modifier, key: None)
    monkeypatch.setattr(
        controller,
        "_wait_for_changed_clipboard_text",
        lambda previous_content, timeout_seconds=0.9: "",
    )

    result = controller.tool_read_current_document(
        screen_index=0,
        position=[420, 360],
        screen_info=[
            {"index": 0, "x": 0, "y": 0, "width": 1440, "height": 900, "is_primary": True}
        ],
    )

    assert result["ok"] is False
    assert result.get("fallback", {}).get("type") == "read_current_document_copy_failed"
    assert "请改用图片或截图分析当前文档内容" in str(result["error"])
    assert list(document_extract_dir.glob("document_*.txt")) == []


def test_tool_hold_modifier_keys_presses_and_records_state():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    result = controller.tool_hold_modifier_keys(keys=["command"], screen_info=None)

    assert result == {"ok": True, "summary": "已进入修饰键长按状态", "error": None}
    assert controller.get_held_modifier_keys() == ["command"]
    assert fake_platform.calls == [("key_down", "command")]


def test_tool_release_modifier_keys_releases_all():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    controller.tool_hold_modifier_keys(keys=["command", "shift"], screen_info=None)
    fake_platform.calls.clear()

    result = controller.tool_release_modifier_keys(screen_info=None)

    assert result == {"ok": True, "summary": "已释放修饰键长按状态", "error": None}
    assert controller.get_held_modifier_keys() == []
    assert fake_platform.calls == [("key_up", "shift"), ("key_up", "command")]


def test_tool_release_modifier_keys_releases_subset():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    controller.tool_hold_modifier_keys(keys=["command", "shift"], screen_info=None)
    fake_platform.calls.clear()

    result = controller.tool_release_modifier_keys(keys=["command"], screen_info=None)

    assert result == {"ok": True, "summary": "已释放修饰键长按状态", "error": None}
    assert controller.get_held_modifier_keys() == ["shift"]
    assert fake_platform.calls == [("key_up", "command")]


def test_auto_release_stale_modifier_keys_by_steps():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    controller._platform_adapter = fake_platform

    controller._held_modifier_keys = ["command"]
    controller._held_modifier_since_step = 1
    controller._held_modifier_since_time = 0.0

    notice = controller.auto_release_stale_modifier_keys(
        current_step=6, max_steps=5, max_seconds=9999
    )

    assert notice == "先前长按状态已自动解除。"
    assert controller.get_held_modifier_keys() == []
    assert fake_platform.calls == [("key_up", "command")]


def test_manage_files_search_finds_matching_files(tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Finder",
        "bundle_id": "com.apple.finder",
        "identifier": "com.apple.finder",
        "pid": 100,
    }
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=0.0,
        probe_count=1,
        last_change_ratio=0.0,
    )

    (tmp_path / "report_2024.txt").write_text("data")
    (tmp_path / "report_2025.txt").write_text("data")
    (tmp_path / "notes.txt").write_text("data")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "report_draft.txt").write_text("data")

    result = controller.tool_manage_files(
        mode="search", path=str(tmp_path), query="report", screen_info=None
    )

    assert result["ok"] is True
    assert "report_2024.txt" in result["summary"]
    assert "report_2025.txt" in result["summary"]
    assert "report_draft.txt" in result["summary"]
    assert "notes.txt" not in result["summary"]
    assert "共找到 3 个结果" in result["summary"]


def test_manage_files_search_returns_no_results(tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Finder",
        "bundle_id": "com.apple.finder",
        "identifier": "com.apple.finder",
        "pid": 100,
    }
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=0.0,
        probe_count=1,
        last_change_ratio=0.0,
    )

    (tmp_path / "notes.txt").write_text("data")

    result = controller.tool_manage_files(
        mode="search", path=str(tmp_path), query="report", screen_info=None
    )

    assert result["ok"] is True
    assert "未找到" in result["summary"]


def test_manage_files_search_can_be_interrupted(tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Finder",
        "bundle_id": "com.apple.finder",
        "identifier": "com.apple.finder",
        "pid": 100,
    }
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None

    (tmp_path / "report_2024.txt").write_text("data")
    (tmp_path / "report_2025.txt").write_text("data")
    stop_checks = {"count": 0}

    def should_stop():
        stop_checks["count"] += 1
        return stop_checks["count"] >= 3

    result = controller.tool_manage_files(
        mode="search",
        path=str(tmp_path),
        query="report",
        screen_info=None,
        should_stop=should_stop,
    )

    assert result["ok"] is False
    assert result["error"] == "用户已停止当前任务"
    assert "工具执行已中断" in result["summary"]
    assert "已扫描" in result["summary"]


def test_manage_files_create_interrupt_preserves_completed_items(tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Finder",
        "bundle_id": "com.apple.finder",
        "identifier": "com.apple.finder",
        "pid": 100,
    }
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None
    stop_values = iter([False, False, False, True])

    def should_stop():
        return next(stop_values, True)

    result = controller.tool_manage_files(
        mode="create",
        parent=str(tmp_path),
        items=[
            {"name": "created.txt", "type": "file"},
            {"name": "not-created.txt", "type": "file"},
        ],
        screen_info=None,
        should_stop=should_stop,
    )

    assert result["ok"] is False
    assert result["processed_count"] == 1
    assert result["remaining_count"] == 1
    assert (tmp_path / "created.txt").exists()
    assert not (tmp_path / "not-created.txt").exists()


def test_manage_files_search_requires_query():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Finder",
        "bundle_id": "com.apple.finder",
        "identifier": "com.apple.finder",
        "pid": 100,
    }
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=0.0,
        probe_count=1,
        last_change_ratio=0.0,
    )

    result = controller.tool_manage_files(mode="search", path="/tmp", query="", screen_info=None)

    assert result["ok"] is False
    assert "query" in result["summary"]


def test_manage_files_search_uses_finder_current_path_when_path_omitted(tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Finder",
        "bundle_id": "com.apple.finder",
        "identifier": "com.apple.finder",
        "pid": 100,
    }
    fake_platform.get_active_document_path = lambda app_name: str(tmp_path)
    controller._platform_adapter = fake_platform
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=0.0,
        probe_count=1,
        last_change_ratio=0.0,
    )

    (tmp_path / "target_file.txt").write_text("data")

    result = controller.tool_manage_files(mode="search", query="target", screen_info=None)

    assert result["ok"] is True
    assert "target_file.txt" in result["summary"]


def test_manage_files_search_uses_file_explorer_current_path_when_path_omitted_on_windows(tmp_path):
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "File Explorer",
        "bundle_id": "",
        "identifier": "explorer.exe",
        "pid": 100,
    }
    fake_platform.get_active_document_path = lambda app_name: (
        str(tmp_path) if app_name == "File Explorer" else None
    )
    controller._platform_adapter = fake_platform
    controller._current_os = "Windows"
    controller._hide_windows = lambda: None
    controller._show_windows = lambda: None
    controller.wait_for_stability = lambda screen_info=None: SimpleNamespace(
        stable=True,
        elapsed_ms=0.0,
        probe_count=1,
        last_change_ratio=0.0,
    )

    (tmp_path / "target_file.txt").write_text("data")

    result = controller.tool_manage_files(mode="search", query="target", screen_info=None)

    assert result["ok"] is True
    assert "target_file.txt" in result["summary"]


def test_manage_files_rejects_non_file_manager_frontmost_app_with_cross_platform_message():
    controller = AutomationController(Config())
    fake_platform = FakePlatformAdapter()
    fake_platform.get_frontmost_app_info = lambda: {
        "app_name": "Google Chrome",
        "bundle_id": "",
        "identifier": "chrome.exe",
        "pid": 100,
    }
    controller._platform_adapter = fake_platform

    result = controller.tool_manage_files(
        mode="search", path="/tmp", query="target", screen_info=None
    )

    assert result["ok"] is False
    assert "访达或文件资源管理器" in result["summary"]


def test_observation_service_builds_windows_file_manager_folder_prompt():
    automation = SimpleNamespace(
        _platform_adapter=SimpleNamespace(
            get_active_document_path=lambda app_name: r"C:\Users\tester\Documents"
        )
    )
    service = ObservationService(
        screenshot=SimpleNamespace(), automation=automation, focus_fallback_prompt="fallback"
    )

    prompt = service.build_frontmost_app_prompt(
        {"app_name": "File Explorer", "bundle_id": "", "identifier": "explorer.exe", "pid": 9527},
        agent_process_pid=1,
    )

    assert (
        prompt
        == "Current frontmost app: File Explorer.\nCurrent folder path: C:\\Users\\tester\\Documents."
    )


def test_observation_service_builds_windows_document_file_prompt():
    automation = SimpleNamespace(
        _platform_adapter=SimpleNamespace(
            get_active_document_path=lambda app_name: r"C:\docs\report.docx"
        )
    )
    service = ObservationService(
        screenshot=SimpleNamespace(), automation=automation, focus_fallback_prompt="fallback"
    )

    prompt = service.build_frontmost_app_prompt(
        {"app_name": "Microsoft Word", "bundle_id": "", "identifier": "winword.exe", "pid": 9527},
        agent_process_pid=1,
    )

    assert (
        prompt
        == "Current frontmost app: Microsoft Word.\nCurrent file path: C:\\docs\\report.docx."
    )


def test_observation_service_retries_windows_file_manager_path_once_when_initial_lookup_is_none(
    monkeypatch,
):
    calls = []

    def get_active_document_path(app_name):
        calls.append(app_name)
        if len(calls) == 1:
            return None
        return r"C:\Users\tester\Documents"

    automation = SimpleNamespace(
        _platform_adapter=SimpleNamespace(get_active_document_path=get_active_document_path)
    )
    service = ObservationService(
        screenshot=SimpleNamespace(), automation=automation, focus_fallback_prompt="fallback"
    )
    monkeypatch.setattr("baodou_ai.core.observation.time.sleep", lambda _seconds: None)

    prompt = service.build_frontmost_app_prompt(
        {"app_name": "File Explorer", "bundle_id": "", "identifier": "explorer.exe", "pid": 9527},
        agent_process_pid=1,
    )

    assert (
        prompt
        == "Current frontmost app: File Explorer.\nCurrent folder path: C:\\Users\\tester\\Documents."
    )
    assert calls == ["File Explorer", "File Explorer"]
