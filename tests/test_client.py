import sys
from types import SimpleNamespace

from baodou_ai.ai.client import AIClient
from baodou_ai.ai.companion_recommender import CompanionRecommender
from baodou_ai.ai.prompt_builder import PromptBuilder
from baodou_ai.ai.runtime_prompt_context import RuntimePromptContext
from baodou_ai.core.config import Config


def test_build_extra_body_includes_reasoning_effort_for_volcengine():
    config = Config()
    config.set("api_config.base_url", "https://ark.cn-beijing.volces.com/api/v3")
    config.set("ai_config.thinking_type", "enabled")
    config.set("ai_config.reasoning_effort", "minimal")

    client = AIClient(config)
    extra_body = client._build_extra_body()

    assert extra_body["thinking"]["type"] == "enabled"
    assert extra_body["reasoning_effort"] == "minimal"


def test_build_extra_body_omits_reasoning_effort_for_non_volcengine():
    config = Config()
    config.set("api_config.base_url", "https://api.openai.com/v1")
    config.set("ai_config.thinking_type", "enabled")
    config.set("ai_config.reasoning_effort", "minimal")

    client = AIClient(config)
    extra_body = client._build_extra_body()

    assert extra_body["thinking"]["type"] == "enabled"
    assert "reasoning_effort" not in extra_body


def test_build_full_user_content_includes_process_report_request_without_report_mode_section():
    config = Config()
    client = AIClient(config)
    client._platform_adapter = SimpleNamespace(
        get_default_browser_info=lambda: {
            "app_name": "Google Chrome",
            "identifier": "com.google.Chrome",
            "is_chrome_family": True,
        }
    )

    content = client._build_full_user_content(
        user_content="帮我打开微信",
        screen_info=[{"index": 0, "width": 1920, "height": 1080, "is_primary": True}],
        process_report_mode="auto",
        process_report_request_prompt="A brief process report is required for this turn. report。",
        held_modifier_prompt="Currently held modifier keys: command.",
        frontmost_app_prompt="Current frontmost app: Google Chrome.",
    )

    assert "[Current Task]\n帮我打开微信" in content
    assert "[Report Mode]" not in content
    assert "A brief process report is required for this turn. report。" in content
    assert "Currently held modifier keys: command." in content
    assert "Current frontmost app: Google Chrome." in content
    assert "The current system has 1 screen(s):" in content
    assert "- Screen 0 (Primary)" in content
    assert "Resolution" not in content
    assert "Current default browser: Google Chrome." in content


def test_prompt_builder_full_user_content_matches_client_output():
    config = Config()
    config.set("locale_config.respond_language", "Chinese (Simplified)")
    client = AIClient(config)
    client._platform_adapter = SimpleNamespace(
        get_default_browser_info=lambda: {
            "app_name": "Google Chrome",
            "identifier": "com.google.Chrome",
            "is_chrome_family": True,
        }
    )
    context = RuntimePromptContext(
        screen_info=[{"index": 0, "width": 1920, "height": 1080, "is_primary": True}],
        memory_content="微信账号：test@example.com",
        replan_feedback="上一工具调用未产生可见界面变化，请重新规划。",
        process_report_mode="auto",
        held_modifier_prompt="No modifier keys are currently held。",
        frontmost_app_prompt="Current frontmost app: 访达。",
    )

    builder_content = PromptBuilder().build_full_user_content(
        user_content="帮我打开微信并确认是否登录",
        context=context,
        default_browser_prompt=client._build_default_browser_prompt(),
        respond_language=config.get_respond_language(),
    )
    client_content = client._build_full_user_content(
        user_content="帮我打开微信并确认是否登录",
        runtime_context=context,
    )

    assert client_content == builder_content
    assert "[Language]\nRespond to the user in Chinese (Simplified)." in client_content


def test_build_full_user_content_uses_runtime_respond_language_override():
    config = Config()
    config.set("locale_config.respond_language", "Chinese (Simplified)")
    client = AIClient(config)
    client._platform_adapter = SimpleNamespace(
        get_default_browser_info=lambda: {
            "app_name": "Google Chrome",
            "identifier": "com.google.Chrome",
            "is_chrome_family": True,
        }
    )

    content = client._build_full_user_content(
        user_content="Open Slack and summarize unread messages",
        respond_language_override="English",
    )

    assert "Respond to the user in English." in content
    assert "Chinese (Simplified)" not in content


def test_build_history_user_content_keeps_only_task_instruction():
    config = Config()
    client = AIClient(config)

    history_content = client._build_history_user_content(
        "Current time: 2026-04-10 16:00\nUser task: 打开微信并确认是否登录"
    )

    assert history_content == "[Current Task]\nUser task: 打开微信并确认是否登录"
    assert "Current time:" not in history_content


def test_build_history_user_content_wraps_plain_task_text():
    config = Config()
    client = AIClient(config)

    history_content = client._build_history_user_content("打开微信并确认是否登录")

    assert history_content == "[Current Task]\n打开微信并确认是否登录"


def test_build_full_user_content_prioritizes_task_and_replan_before_runtime_context():
    config = Config()
    client = AIClient(config)
    client._platform_adapter = SimpleNamespace(
        get_default_browser_info=lambda: {
            "app_name": "Google Chrome",
            "identifier": "com.google.Chrome",
            "is_chrome_family": True,
        }
    )

    content = client._build_full_user_content(
        user_content="帮我打开微信并确认是否登录",
        screen_info=[{"index": 0, "width": 1920, "height": 1080, "is_primary": True}],
        memory_content="微信账号：test@example.com",
        replan_feedback="上一工具调用未产生可见界面变化，请重新规划。",
        process_report_mode="auto",
        held_modifier_prompt="No modifier keys are currently held。",
        frontmost_app_prompt="Current frontmost app: 访达。",
    )

    assert content.startswith("[Current Task]\n帮我打开微信并确认是否登录")
    assert content.index("[Replan Notice]") < content.index("[Frontmost App]")
    assert content.index("[Frontmost App]") < content.index("The current system has 1 screen(s):")
    assert content.index("The current system has 1 screen(s):") < content.index("[Held Modifier Keys]")
    assert content.index("[Held Modifier Keys]") < content.index("[Important Information Memory (no need to remember what is already here)]")


def test_build_screen_prompt_omits_resolution_details_for_multiple_screens():
    content = PromptBuilder.build_screen_prompt(
        [
            {"index": 0, "width": 3024, "height": 1964, "is_primary": True},
            {"index": 1, "width": 1920, "height": 1080, "is_primary": False},
        ]
    )

    assert content == (
        "The current system has 2 screen(s):\n"
        "- Screen 0 (Primary)\n"
        "- Screen 1\n"
    )
    assert "3024" not in content
    assert "1964" not in content
    assert "1920" not in content
    assert "1080" not in content
    assert "Resolution" not in content


def test_build_default_browser_prompt_is_cached_per_client():
    config = Config()
    client = AIClient(config)
    browser_calls = []
    client._platform_adapter = SimpleNamespace(
        get_default_browser_info=lambda: browser_calls.append("called") or {
            "app_name": "Google Chrome",
            "identifier": "com.google.Chrome",
            "is_chrome_family": True,
        }
    )

    first = client._build_full_user_content(user_content="任务一")
    second = client._build_full_user_content(user_content="任务二")

    assert browser_calls == ["called"]
    assert "Current default browser: Google Chrome." in first
    assert "Current default browser: Google Chrome." in second


def test_build_full_user_content_includes_page_context_without_truncation():
    config = Config()
    client = AIClient(config)
    client._platform_adapter = SimpleNamespace(
        get_default_browser_info=lambda: {
            "app_name": "Google Chrome",
            "identifier": "com.google.Chrome",
            "is_chrome_family": True,
        }
    )

    content = client._build_full_user_content(
        user_content="帮我总结当前网页",
        page_context={
            "url": "https://example.com",
            "title": "Example Domain",
            "quality": "best_effort",
            "content": "这是正文",
        },
        page_extraction_notice="The current webpage extraction failed; the previous webpage extraction content has been invalidated and cleared. Do not rely on read_current_page results to judge the current webpage content; you must extract information strictly by analyzing the screenshot.",
    )

    assert "[Page Extraction Status]" in content
    assert "The current webpage extraction failed; the previous webpage extraction content has been invalidated and cleared." in content
    assert "[Page State]" in content
    assert "URL: https://example.com" in content
    assert "Title: Example Domain" in content
    assert "Quality: best_effort" in content
    assert "这是正文" not in content
    assert 'You can continue reading with read_current_page(mode="chunk"/"next"/"search") at any time.' in content
    assert "Note: The current content has been truncated due to context limits." not in content


def test_build_full_user_content_truncates_long_page_context():
    config = Config()
    client = AIClient(config)
    client._platform_adapter = SimpleNamespace(
        get_default_browser_info=lambda: {
            "app_name": "Google Chrome",
            "identifier": "com.google.Chrome",
            "is_chrome_family": True,
        }
    )
    long_content = "A" * 4500

    content = client._build_full_user_content(
        user_content="帮我总结当前网页",
        page_context={
            "url": "https://example.com",
            "title": "Long Page",
            "quality": "best_effort",
            "content": long_content,
            "chunk_index": 0,
            "total_chunks": 1,
            "has_more": False,
        },
    )

    assert "URL: https://example.com" in content
    assert "Title: Long Page" in content
    assert "Quality: best_effort" in content
    assert "Chunks: 1 total, last read: chunk 1" in content
    assert "Note: The current content has been truncated due to context limits." not in content
    assert "A" * 4000 not in content


def test_build_full_user_content_includes_document_context_without_truncation():
    config = Config()
    client = AIClient(config)
    client._platform_adapter = SimpleNamespace(
        get_default_browser_info=lambda: {
            "app_name": "Google Chrome",
            "identifier": "com.google.Chrome",
            "is_chrome_family": True,
        }
    )

    content = client._build_full_user_content(
        user_content="帮我总结当前文档",
        document_context={
            "app_name": "Microsoft Word",
            "content": "这是文档正文",
            "chunk_index": 0,
            "total_chunks": 1,
            "has_more": False,
        },
        document_extraction_notice=(
            "The current document extraction failed; the previous document extraction content has been invalidated and cleared. "
            "The result appears to come from a toolbar, font size bar, style bar, or other non-body area. "
            "If you still need to extract the current document, observe the screenshot first and provide the body area coordinates "
            "in the next read_current_document call; "
            "do not call again without coordinates."
        ),
    )

    assert "[Document Extraction Status]" in content
    assert "The current document extraction failed; the previous document extraction content has been invalidated and cleared." in content
    assert "[Document State]" in content
    assert "App: Microsoft Word" in content
    assert "Chunks: 1 total" in content
    assert "这是文档正文" not in content
    assert "Note: The current content has been truncated due to context limits." not in content
    assert "The current document context will not be visible in the next turn" not in content


def test_build_full_user_content_includes_document_search_context():
    config = Config()
    client = AIClient(config)
    client._platform_adapter = SimpleNamespace(
        get_default_browser_info=lambda: {
            "app_name": "Google Chrome",
            "identifier": "com.google.Chrome",
            "is_chrome_family": True,
        }
    )

    content = client._build_full_user_content(
        user_content="帮我找退款条款",
        document_context={
            "app_name": "Microsoft Word",
            "content": "[命中 1] 第 2 段\n匹配词: 退款、违约金\n退款条款如下……",
            "source_mode": "search",
            "query": "退款 违约金",
            "result_count": 1,
            "has_more": False,
        },
    )

    assert "[Document State]" in content
    assert "Last query: 退款 违约金" in content
    assert "Results: 1 items" in content
    assert "App: Microsoft Word" in content
    assert "Chunk:" not in content
    assert "The current document context will not be visible in the next turn" not in content


def test_build_full_user_content_truncates_long_document_context():
    config = Config()
    client = AIClient(config)
    client._platform_adapter = SimpleNamespace(
        get_default_browser_info=lambda: {
            "app_name": "Google Chrome",
            "identifier": "com.google.Chrome",
            "is_chrome_family": True,
        }
    )
    long_content = "B" * 4500

    content = client._build_full_user_content(
        user_content="帮我总结当前文档",
        document_context={
            "app_name": "Preview",
            "content": long_content,
            "chunk_index": 0,
            "total_chunks": 1,
            "has_more": False,
        },
    )

    assert "App: Preview" in content
    assert "Chunks: 1 total" in content
    assert "Note: The current content has been truncated due to context limits." not in content


def test_build_full_user_content_includes_document_chunk_remember_warning():
    config = Config()
    client = AIClient(config)
    client._platform_adapter = SimpleNamespace(
        get_default_browser_info=lambda: {
            "app_name": "Google Chrome",
            "identifier": "com.google.Chrome",
            "is_chrome_family": True,
        }
    )

    content = client._build_full_user_content(
        user_content="继续阅读当前文档",
        document_context={
            "app_name": "TextEdit",
            "content": "这是第二块正文",
            "chunk_index": 1,
            "total_chunks": 3,
            "has_more": True,
        },
    )

    assert "Chunks: 3 total, last read: chunk 2" in content
    assert "The current document context will not be visible in the next turn" not in content


def test_prompt_builder_history_user_content_keeps_task_projection():
    content = PromptBuilder.build_history_user_content(
        "Current time: 2026-04-10 16:00\nUser task: 打开微信并确认是否登录"
    )
    assert content == "[Current Task]\nUser task: 打开微信并确认是否登录"


class FakeStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.closed = False

    def __iter__(self):
        for chunk in self._chunks:
            yield chunk

    def close(self):
        self.closed = True


class FakeCompletions:
    def __init__(self, stream_chunks, non_stream_usage=None, fail_on_stream_options=False):
        self.stream_chunks = list(stream_chunks)
        self.non_stream_usage = non_stream_usage
        self.fail_on_stream_options = fail_on_stream_options
        self.calls = []
        self.last_stream = None

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            if self.fail_on_stream_options and "stream_options" in kwargs:
                raise ValueError("unknown parameter: stream_options")
            self.last_stream = FakeStream(self.stream_chunks)
            return self.last_stream

        full_text = "".join(
            chunk.choices[0].delta.content
            for chunk in self.stream_chunks
            if chunk.choices and chunk.choices[0].delta.content
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=full_text))],
            usage=self.non_stream_usage,
        )


class FakeOpenAIClient:
    def __init__(self, stream_chunks, non_stream_usage=None, fail_on_stream_options=False):
        self.chat = SimpleNamespace(
            completions=FakeCompletions(
                stream_chunks,
                non_stream_usage=non_stream_usage,
                fail_on_stream_options=fail_on_stream_options,
            )
        )


def make_stream_chunk(text, usage=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text))],
        usage=usage,
    )


def test_create_completion_streams_and_aggregates_chunks(monkeypatch):
    config = Config()
    client = AIClient(config)
    client._stream_usage_supported = None
    fake_client = FakeOpenAIClient(
        [
            make_stream_chunk('{"thinking":"测'),
            make_stream_chunk("试"),
            make_stream_chunk(
                '"}',
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3, total_tokens=13),
            ),
        ]
    )
    streamed_chunks = []

    monkeypatch.setattr(client, "_get_client", lambda: fake_client)

    raw_content, metrics = client._create_completion(
        messages=[{"role": "user", "content": "hello"}],
        on_stream_chunk=streamed_chunks.append,
    )

    assert raw_content == '{"thinking":"测试"}'
    assert streamed_chunks == ['{"thinking":"测', "试", '"}']
    assert fake_client.chat.completions.calls[0]["stream"] is True
    assert fake_client.chat.completions.calls[0]["stream_options"] == {"include_usage": True}
    assert metrics["model_latency_ms"] >= 0.0
    assert metrics["first_chunk_ms"] >= 0.0
    assert metrics["prompt_tokens"] == 10
    assert metrics["completion_tokens"] == 3
    assert metrics["total_tokens"] == 13
    assert metrics["token_usage_available"] is True
    assert fake_client.chat.completions.last_stream.closed is True


def test_create_completion_retries_stream_without_stream_options_when_unsupported(monkeypatch):
    config = Config()
    client = AIClient(config)
    client._stream_usage_supported = None
    fake_client = FakeOpenAIClient(
        [make_stream_chunk('{"thinking":"fallback"}')],
        fail_on_stream_options=True,
    )

    monkeypatch.setattr(client, "_get_client", lambda: fake_client)

    raw_content, metrics = client._create_completion(
        messages=[{"role": "user", "content": "hello"}],
        on_stream_chunk=lambda _chunk: None,
    )

    assert raw_content == '{"thinking":"fallback"}'
    assert len(fake_client.chat.completions.calls) == 2
    assert "stream_options" in fake_client.chat.completions.calls[0]
    assert "stream_options" not in fake_client.chat.completions.calls[1]
    assert metrics["token_usage_available"] is False


def test_create_completion_extracts_usage_from_non_stream_response(monkeypatch):
    config = Config()
    client = AIClient(config)
    client._stream_usage_supported = None
    fake_client = FakeOpenAIClient(
        [make_stream_chunk('{"thinking":"ok"}')],
        non_stream_usage=SimpleNamespace(
            prompt_tokens=21,
            completion_tokens=8,
            total_tokens=29,
            prompt_tokens_details=SimpleNamespace(cached_tokens=5),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=2),
        ),
    )

    monkeypatch.setattr(client, "_get_client", lambda: fake_client)

    raw_content, metrics = client._create_completion(
        messages=[{"role": "user", "content": "hello"}],
    )

    assert raw_content == '{"thinking":"ok"}'
    assert metrics["prompt_tokens"] == 21
    assert metrics["completion_tokens"] == 8
    assert metrics["total_tokens"] == 29
    assert metrics["cached_tokens"] == 5
    assert metrics["reasoning_tokens"] == 2
    assert metrics["token_usage_available"] is True


def test_get_client_respects_tls_verify_config(monkeypatch):
    config = Config()
    config.set("api_config.api_key", "test-key")
    config.set("api_config.base_url", "https://example.test/v1")
    config.set("api_config.tls_verify", False)
    client = AIClient(config)
    client.close()

    captured = {"verify": [], "clients": []}

    class FakeHttpxClient:
        def __init__(self, *, verify):
            captured["verify"].append(verify)

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, http_client):
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["http_client"] = http_client
            self.closed = False
            captured["clients"].append(self)

        def close(self):
            self.closed = True
            return None

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(Client=FakeHttpxClient))
    monkeypatch.setattr("baodou_ai.ai.client.OpenAI", FakeOpenAI)

    first_client = client._get_client()

    config.set("api_config.tls_verify", True)
    second_client = client._get_client()

    assert captured["api_key"] == "test-key"
    assert captured["base_url"] == "https://example.test/v1"
    assert captured["verify"] == [False, True]
    assert first_client is not second_client
    assert first_client.closed is True
    assert second_client.closed is False


def test_get_next_action_from_capture_builds_runtime_prompt_context(monkeypatch):
    config = Config()
    config.set("api_config.api_key", "test-key")
    client = AIClient(config)
    captured_runtime_context = {}

    def fake_build_full_user_content(*, user_content, runtime_context, **_kwargs):
        captured_runtime_context["user_content"] = user_content
        captured_runtime_context["context"] = runtime_context
        return "[Current Task]\n测试任务"

    monkeypatch.setattr(client, "_build_full_user_content", fake_build_full_user_content)
    monkeypatch.setattr(client, "_load_prompt", lambda: "SYSTEM")
    monkeypatch.setattr(client, "_create_completion", lambda *args, **kwargs: ('{"thinking":"ok"}', {}))
    monkeypatch.setattr(client, "_parse_and_store_response", lambda *args, **kwargs: {"thinking": "ok"})

    parsed, _metrics = client.get_next_action_from_capture(
        captures=[],
        user_content="测试任务",
        page_context={"url": "https://example.com", "title": "Example"},
        document_context={"app_name": "Preview", "total_chunks": 1},
        process_report_mode="auto",
        process_report_request_prompt="A brief process report is required.",
        held_modifier_prompt="command",
        frontmost_app_prompt="Current frontmost app: Finder.",
        background_jobs_prompt="No background jobs.",
        pending_reports_prompt="No pending reports.",
    )

    assert parsed == {"thinking": "ok"}
    assert captured_runtime_context["user_content"] == "测试任务"
    assert isinstance(captured_runtime_context["context"], RuntimePromptContext)
    assert captured_runtime_context["context"].page_context == {
        "url": "https://example.com",
        "title": "Example",
    }
    assert captured_runtime_context["context"].document_context == {
        "app_name": "Preview",
        "total_chunks": 1,
    }
    assert captured_runtime_context["context"].process_report_mode == "auto"


def test_get_next_action_from_capture_passes_runtime_respond_language_override(monkeypatch):
    config = Config()
    config.set("api_config.api_key", "test-key")
    client = AIClient(config)
    captured = {}

    def fake_build_full_user_content(*, user_content, runtime_context, respond_language_override="", **_kwargs):
        captured["user_content"] = user_content
        captured["runtime_context"] = runtime_context
        captured["respond_language_override"] = respond_language_override
        return "[Current Task]\nTest task"

    monkeypatch.setattr(client, "_build_full_user_content", fake_build_full_user_content)
    monkeypatch.setattr(client, "_load_prompt", lambda: "SYSTEM")
    monkeypatch.setattr(client, "_create_completion", lambda *args, **kwargs: ('{"thinking":"ok"}', {}))
    monkeypatch.setattr(client, "_parse_and_store_response", lambda *args, **kwargs: {"thinking": "ok"})

    parsed, _metrics = client.get_next_action_from_capture(
        captures=[],
        user_content="Test task",
        respond_language_override="English",
    )

    assert parsed == {"thinking": "ok"}
    assert captured["user_content"] == "Test task"
    assert captured["respond_language_override"] == "English"


def test_companion_recommender_get_client_respects_tls_verify_config(monkeypatch):
    config = Config.create_isolated()
    config.set("api_config.api_key", "test-key")
    config.set("api_config.base_url", "https://example.test/v1")
    config.set("api_config.tls_verify", False)
    config.set("companion_config.request_timeout_seconds", 12)
    recommender = CompanionRecommender(config)

    captured = {"verify": [], "timeout": [], "clients": []}

    class FakeHttpxClient:
        def __init__(self, *, verify, timeout):
            captured["verify"].append(verify)
            captured["timeout"].append(timeout)

    class FakeTimeout:
        def __init__(self, value):
            self.value = value

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, http_client):
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["http_client"] = http_client
            self.closed = False
            captured["clients"].append(self)

        def close(self):
            self.closed = True
            return None

    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(Client=FakeHttpxClient, Timeout=FakeTimeout),
    )
    monkeypatch.setattr("baodou_ai.ai.companion_recommender.OpenAI", FakeOpenAI)

    first_client = recommender._get_client()

    config.set("api_config.tls_verify", True)
    second_client = recommender._get_client()

    assert captured["api_key"] == "test-key"
    assert captured["base_url"] == "https://example.test/v1"
    assert captured["verify"] == [False, True]
    assert [item.value for item in captured["timeout"]] == [12, 12]
    assert first_client is not second_client
    assert first_client.closed is True
    assert second_client.closed is False
