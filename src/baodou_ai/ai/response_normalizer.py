"""Normalize OpenAI-compatible chat responses and stream chunks."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def coerce_optional_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_usage_metrics(usage: Any) -> Dict[str, Any]:
    if usage is None:
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "cached_tokens": None,
            "reasoning_tokens": None,
            "token_usage_available": False,
        }

    getter = usage.get if isinstance(usage, dict) else lambda key, default=None: getattr(usage, key, default)
    prompt_tokens = coerce_optional_int(getter("prompt_tokens"))
    completion_tokens = coerce_optional_int(getter("completion_tokens"))
    total_tokens = coerce_optional_int(getter("total_tokens"))
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens

    prompt_details = getter("prompt_tokens_details")
    completion_details = getter("completion_tokens_details")
    prompt_getter = (
        prompt_details.get
        if isinstance(prompt_details, dict)
        else lambda key, default=None: getattr(prompt_details, key, default)
    )
    completion_getter = (
        completion_details.get
        if isinstance(completion_details, dict)
        else lambda key, default=None: getattr(completion_details, key, default)
    )

    cached_tokens = coerce_optional_int(prompt_getter("cached_tokens"))
    reasoning_tokens = coerce_optional_int(completion_getter("reasoning_tokens"))
    token_usage_available = any(
        value is not None
        for value in (prompt_tokens, completion_tokens, total_tokens, cached_tokens, reasoning_tokens)
    )
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "reasoning_tokens": reasoning_tokens,
        "token_usage_available": token_usage_available,
    }


def extract_text_from_completion(completion: Any) -> str:
    choices = getattr(completion, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    return coerce_content_to_text(getattr(message, "content", None))


def extract_text_from_stream_chunk(chunk: Any) -> str:
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return ""

    delta = getattr(choices[0], "delta", None)
    if delta is None:
        return ""

    return coerce_content_to_text(getattr(delta, "content", None))


def coerce_content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                continue
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return str(content)
