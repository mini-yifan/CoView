"""Adapt normalized internal requests to OpenAI SDK kwargs."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from baodou_ai.ai.provider_profiles import ProviderProfile
from baodou_ai.ai.request_normalizer import AIRequest, normalize_request


@dataclass
class AdaptedRequest:
    kwargs: Dict[str, Any]
    profile: ProviderProfile
    normalization_actions: List[str] = field(default_factory=list)
    removed_fields: List[str] = field(default_factory=list)
    disabled_capabilities: Set[str] = field(default_factory=set)

    def log_summary(self) -> str:
        parts = [
            f"provider={self.profile.name}",
            f"profile={self.profile.display_name}",
        ]
        if self.normalization_actions:
            parts.append(f"normalization={self.normalization_actions}")
        if self.removed_fields:
            parts.append(f"removed={self.removed_fields}")
        if self.disabled_capabilities:
            parts.append(f"disabled={sorted(self.disabled_capabilities)}")
        return "; ".join(parts)


class ProviderRequestAdapter:
    def __init__(self, profile: ProviderProfile):
        self.profile = profile

    def adapt(
        self,
        request: AIRequest,
        disabled_capabilities: Optional[Set[str]] = None,
    ) -> AdaptedRequest:
        disabled = set(disabled_capabilities or set())
        normalized = normalize_request(request, self.profile, disabled)
        req = normalized.request
        caps = self.profile.capabilities
        removed: List[str] = []

        kwargs: Dict[str, Any] = {
            "model": req.model,
            "messages": req.messages,
        }
        if req.stream:
            kwargs["stream"] = True

        extra_body = copy.deepcopy(req.extra_body or {})
        if ("thinking" in extra_body) and (
            not caps.supports_thinking or "thinking" in disabled
        ):
            extra_body.pop("thinking", None)
            removed.append("extra_body.thinking")
        if ("reasoning_effort" in extra_body) and (
            not caps.supports_reasoning_effort or "reasoning_effort" in disabled
        ):
            extra_body.pop("reasoning_effort", None)
            removed.append("extra_body.reasoning_effort")
        if extra_body:
            kwargs["extra_body"] = extra_body
        elif req.extra_body:
            removed.append("extra_body")

        stream_options = copy.deepcopy(req.stream_options)
        if stream_options is not None:
            include_usage_requested = bool(stream_options.get("include_usage"))
            include_usage_supported = (
                caps.supports_stream_options_include_usage
                and "stream_options" not in disabled
                and "stream_options.include_usage" not in disabled
            )
            if include_usage_requested and include_usage_supported:
                kwargs["stream_options"] = stream_options
            else:
                removed.append("stream_options")

        if req.tools is not None:
            if caps.supports_tools and "tools" not in disabled:
                kwargs["tools"] = copy.deepcopy(req.tools)
            else:
                removed.append("tools")

        if req.tool_choice is not None:
            if caps.supports_tools and "tools" not in disabled:
                kwargs["tool_choice"] = copy.deepcopy(req.tool_choice)
            else:
                removed.append("tool_choice")

        if req.parallel_tool_calls is not None:
            if caps.supports_parallel_tool_calls and "parallel_tool_calls" not in disabled:
                kwargs["parallel_tool_calls"] = req.parallel_tool_calls
            else:
                removed.append("parallel_tool_calls")

        if req.temperature is not None:
            kwargs["temperature"] = req.temperature

        if req.response_format is not None:
            if caps.supports_response_format and "response_format" not in disabled:
                kwargs["response_format"] = copy.deepcopy(req.response_format)
            else:
                removed.append("response_format")

        return AdaptedRequest(
            kwargs=kwargs,
            profile=self.profile,
            normalization_actions=normalized.actions,
            removed_fields=removed,
            disabled_capabilities=disabled,
        )
