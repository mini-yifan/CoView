"""Ordered fallback policy for provider compatibility failures."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Set


class RetryAction(str, Enum):
    DROP_STREAM_OPTIONS = "drop_stream_options"
    DROP_REASONING_EFFORT = "drop_reasoning_effort"
    DROP_THINKING = "drop_thinking"
    DOWNGRADE_TEXT_PARTS = "downgrade_text_parts"
    CLEAN_INVALID_PARTS = "clean_invalid_parts"
    DROP_MULTIMODAL = "drop_multimodal"


@dataclass(frozen=True)
class RetryDecision:
    action: RetryAction
    capability: str
    reason: str


class CompatibilityRetryPolicy:
    _ORDER = (
        RetryDecision(
            RetryAction.DROP_STREAM_OPTIONS,
            "stream_options",
            "stream usage options appear unsupported",
        ),
        RetryDecision(
            RetryAction.DROP_REASONING_EFFORT,
            "reasoning_effort",
            "reasoning_effort appears unsupported",
        ),
        RetryDecision(
            RetryAction.DROP_THINKING,
            "thinking",
            "thinking appears unsupported",
        ),
        RetryDecision(
            RetryAction.DOWNGRADE_TEXT_PARTS,
            "text_content_parts",
            "text content parts appear unsupported",
        ),
        RetryDecision(
            RetryAction.CLEAN_INVALID_PARTS,
            "strict_message_parts",
            "message content validation failed",
        ),
        RetryDecision(
            RetryAction.DROP_MULTIMODAL,
            "multimodal_images",
            "multimodal image content appears unsupported",
        ),
    )

    def decide(self, exc: Exception, disabled_capabilities: Set[str]) -> Optional[RetryDecision]:
        message = str(exc).lower()

        preferred_capability = self._classify(message)
        if preferred_capability:
            for decision in self._ORDER:
                if (
                    decision.capability == preferred_capability
                    and decision.capability not in disabled_capabilities
                ):
                    return decision

        for decision in self._ORDER:
            if decision.capability not in disabled_capabilities and self._message_matches(
                message, decision.capability
            ):
                return decision

        return None

    @staticmethod
    def _classify(message: str) -> Optional[str]:
        if "stream_options" in message or "include_usage" in message:
            return "stream_options"
        if "reasoning_effort" in message:
            return "reasoning_effort"
        if "thinking" in message:
            return "thinking"
        if (
            "content part" in message
            or "content_part" in message
            or "expected a string" in message
            or "messages" in message
            and "content" in message
            and "string" in message
        ):
            return "text_content_parts"
        if "image_url" in message or "data url" in message or "data_url" in message:
            return "multimodal_images"
        if (
            "validation" in message
            or "schema" in message
            or "missing" in message
            or "invalid" in message
            or "extra inputs are not permitted" in message
        ):
            return "strict_message_parts"
        if "unknown parameter" in message or "unrecognized request argument" in message:
            return None
        return None

    @staticmethod
    def _message_matches(message: str, capability: str) -> bool:
        generic_parameter_error = any(
            marker in message
            for marker in (
                "unknown parameter",
                "unexpected keyword argument",
                "extra inputs are not permitted",
                "unrecognized request argument",
                "unsupported parameter",
            )
        )
        if capability in {"stream_options", "reasoning_effort", "thinking"}:
            return generic_parameter_error
        return any(marker in message for marker in ("validation", "schema", "invalid", "messages"))
