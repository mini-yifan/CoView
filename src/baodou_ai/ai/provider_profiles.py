"""Provider capability profiles for OpenAI-compatible chat APIs."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_text_content_string: bool = True
    supports_text_content_parts: bool = False
    supports_empty_text_parts: bool = False
    supports_multimodal_images: bool = True
    supports_image_data_url: bool = True
    supports_stream_options_include_usage: bool = False
    supports_reasoning_effort: bool = False
    supports_thinking: bool = False
    supports_tools: bool = False
    supports_parallel_tool_calls: bool = False
    supports_response_format: bool = False


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    display_name: str
    capabilities: ProviderCapabilities


PROVIDER_PROFILES = {
    "dashscope": ProviderProfile(
        name="dashscope",
        display_name="Alibaba Cloud DashScope",
        capabilities=ProviderCapabilities(
            supports_text_content_string=True,
            supports_text_content_parts=True,
            supports_empty_text_parts=False,
            supports_multimodal_images=True,
            supports_image_data_url=True,
            supports_stream_options_include_usage=True,
            supports_reasoning_effort=False,
            supports_thinking=True,
            supports_tools=True,
            supports_parallel_tool_calls=False,
            supports_response_format=True,
        ),
    ),
    "volcengine": ProviderProfile(
        name="volcengine",
        display_name="Volcengine Ark",
        capabilities=ProviderCapabilities(
            supports_text_content_string=True,
            supports_text_content_parts=True,
            supports_empty_text_parts=False,
            supports_multimodal_images=True,
            supports_image_data_url=True,
            supports_stream_options_include_usage=True,
            supports_reasoning_effort=True,
            supports_thinking=True,
            supports_tools=True,
            supports_parallel_tool_calls=True,
            supports_response_format=True,
        ),
    ),
    "siliconflow": ProviderProfile(
        name="siliconflow",
        display_name="SiliconFlow",
        capabilities=ProviderCapabilities(
            supports_text_content_string=True,
            supports_text_content_parts=False,
            supports_empty_text_parts=False,
            supports_multimodal_images=True,
            supports_image_data_url=True,
            supports_stream_options_include_usage=False,
            supports_reasoning_effort=False,
            supports_thinking=False,
            supports_tools=True,
            supports_parallel_tool_calls=False,
            supports_response_format=True,
        ),
    ),
    "openai": ProviderProfile(
        name="openai",
        display_name="OpenAI",
        capabilities=ProviderCapabilities(
            supports_text_content_string=True,
            supports_text_content_parts=True,
            supports_empty_text_parts=True,
            supports_multimodal_images=True,
            supports_image_data_url=True,
            supports_stream_options_include_usage=True,
            supports_reasoning_effort=True,
            supports_thinking=False,
            supports_tools=True,
            supports_parallel_tool_calls=True,
            supports_response_format=True,
        ),
    ),
    "unknown": ProviderProfile(
        name="unknown",
        display_name="Unknown OpenAI-compatible provider",
        capabilities=ProviderCapabilities(),
    ),
}


def identify_provider(base_url: str) -> str:
    raw_url = str(base_url or "").strip().lower()
    if not raw_url:
        return "unknown"

    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return "unknown"

    if _matches_domain(hostname, "dashscope.aliyuncs.com"):
        return "dashscope"
    if any(
        _matches_domain(hostname, domain)
        for domain in ("volces.com", "volcengine.com", "volcengineapi.com")
    ):
        return "volcengine"
    if _matches_domain(hostname, "siliconflow.cn") or _matches_domain(
        hostname, "siliconflow.com"
    ):
        return "siliconflow"
    if _matches_domain(hostname, "openai.com"):
        return "openai"
    return "unknown"


def get_provider_profile(base_url: str) -> ProviderProfile:
    return PROVIDER_PROFILES.get(identify_provider(base_url), PROVIDER_PROFILES["unknown"])


def _matches_domain(hostname: str, domain: str) -> bool:
    return hostname == domain or hostname.endswith(f".{domain}")
