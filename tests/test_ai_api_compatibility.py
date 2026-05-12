from types import SimpleNamespace

from baodou_ai.ai.client import AIClient
from baodou_ai.ai.provider_adapter import ProviderRequestAdapter
from baodou_ai.ai.provider_profiles import get_provider_profile
from baodou_ai.ai.request_normalizer import AIRequest, normalize_request
from baodou_ai.core.config import Config


def test_provider_profile_identification():
    assert get_provider_profile("https://dashscope.aliyuncs.com/compatible-mode/v1").name == "dashscope"
    assert get_provider_profile("https://ark.cn-beijing.volces.com/api/v3").name == "volcengine"
    assert get_provider_profile("https://api.siliconflow.cn/v1").name == "siliconflow"
    assert get_provider_profile("https://api.openai.com/v1").name == "openai"
    assert get_provider_profile("https://example.test/v1").name == "unknown"


def test_normalize_text_string_message_keeps_string_content():
    profile = get_provider_profile("https://api.siliconflow.cn/v1")
    request = AIRequest(model="m", messages=[{"role": "user", "content": "hello"}])

    normalized = normalize_request(request, profile)

    assert normalized.request.messages == [{"role": "user", "content": "hello"}]


def test_normalize_text_parts_can_downgrade_to_string_without_mutating_original():
    profile = get_provider_profile("https://api.siliconflow.cn/v1")
    messages = [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
    request = AIRequest(model="m", messages=messages)

    normalized = normalize_request(request, profile)

    assert normalized.request.messages == [{"role": "user", "content": "hello"}]
    assert messages == [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
    assert "text_parts_to_string:0" in normalized.actions


def test_normalize_drops_empty_and_invalid_parts_and_keeps_valid_image():
    profile = get_provider_profile("https://dashscope.aliyuncs.com/compatible-mode/v1")
    request = AIRequest(
        model="m",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": ""},
                    {"type": "text", "text": None},
                    {"type": "image_url", "image_url": {"url": ""}},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                    {"type": "bogus", "text": "drop"},
                    "drop",
                ],
            }
        ],
    )

    normalized = normalize_request(request, profile)

    assert normalized.request.messages == [
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}],
        }
    ]
    assert "drop_empty_text_part:0:0" in normalized.actions
    assert "coerce_none_text:0:1" in normalized.actions
    assert "drop_image_part_without_url:0:2" in normalized.actions
    assert "drop_unknown_part:0:4:bogus" in normalized.actions
    assert "drop_non_dict_part:0:5" in normalized.actions


def test_adapter_removes_unsupported_stream_options_and_extra_fields():
    profile = get_provider_profile("https://api.siliconflow.cn/v1")
    request = AIRequest(
        model="m",
        messages=[{"role": "user", "content": "hello"}],
        stream=True,
        stream_options={"include_usage": True},
        extra_body={"thinking": {"type": "enabled"}, "reasoning_effort": "minimal"},
        tools=[{"type": "function", "function": {"name": "x"}}],
        parallel_tool_calls=True,
        response_format={"type": "json_object"},
    )

    adapted = ProviderRequestAdapter(profile).adapt(request)

    assert "stream_options" not in adapted.kwargs
    assert "extra_body" not in adapted.kwargs
    assert "tools" in adapted.kwargs
    assert "parallel_tool_calls" not in adapted.kwargs
    assert adapted.kwargs["response_format"] == {"type": "json_object"}
    assert "stream_options" in adapted.removed_fields
    assert "extra_body.thinking" in adapted.removed_fields
    assert "extra_body.reasoning_effort" in adapted.removed_fields


class FakeCompletions:
    def __init__(self, failures):
        self.failures = list(failures)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.failures:
            raise ValueError(self.failures.pop(0))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"thinking":"ok"}'))],
            usage=None,
        )


class FakeOpenAIClient:
    def __init__(self, failures):
        self.chat = SimpleNamespace(completions=FakeCompletions(failures))


def test_completion_retries_without_reasoning_effort_when_unsupported(monkeypatch):
    config = Config()
    config.set("api_config.base_url", "https://ark.cn-beijing.volces.com/api/v3")
    config.set("ai_config.reasoning_effort", "minimal")
    client = AIClient(config)
    fake_client = FakeOpenAIClient(["unknown parameter: reasoning_effort"])
    monkeypatch.setattr(client, "_get_client", lambda: fake_client)

    raw_content, metrics = client._create_completion(
        messages=[{"role": "user", "content": "hello"}],
    )

    assert raw_content == '{"thinking":"ok"}'
    assert len(fake_client.chat.completions.calls) == 2
    assert "reasoning_effort" in fake_client.chat.completions.calls[0]["extra_body"]
    assert "reasoning_effort" not in fake_client.chat.completions.calls[1]["extra_body"]
    assert metrics["token_usage_available"] is False


def test_completion_retries_with_text_parts_downgraded_to_string(monkeypatch):
    config = Config()
    config.set("api_config.base_url", "https://api.openai.com/v1")
    client = AIClient(config)
    fake_client = FakeOpenAIClient(["messages.content expected a string"])
    monkeypatch.setattr(client, "_get_client", lambda: fake_client)

    raw_content, _metrics = client._create_completion(
        messages=[{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
    )

    assert raw_content == '{"thinking":"ok"}'
    assert fake_client.chat.completions.calls[0]["messages"][0]["content"] == [
        {"type": "text", "text": "hello"}
    ]
    assert fake_client.chat.completions.calls[1]["messages"][0]["content"] == "hello"


def test_retry_caches_failed_capability_for_same_provider(monkeypatch):
    config = Config()
    config.set("api_config.base_url", "https://ark.cn-beijing.volces.com/api/v3")
    client = AIClient(config)
    first_fake = FakeOpenAIClient(["unknown parameter: reasoning_effort"])
    monkeypatch.setattr(client, "_get_client", lambda: first_fake)

    client._create_completion(messages=[{"role": "user", "content": "hello"}])

    second_fake = FakeOpenAIClient([])
    monkeypatch.setattr(client, "_get_client", lambda: second_fake)
    client._create_completion(messages=[{"role": "user", "content": "hello"}])

    assert "reasoning_effort" not in second_fake.chat.completions.calls[0]["extra_body"]
