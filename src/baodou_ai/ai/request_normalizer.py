"""Request models and message normalization for chat compatibility."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from baodou_ai.ai.provider_profiles import ProviderProfile


@dataclass
class AIRequest:
    model: str
    messages: List[Dict[str, Any]]
    stream: bool = False
    extra_body: Dict[str, Any] = field(default_factory=dict)
    stream_options: Optional[Dict[str, Any]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    temperature: Optional[float] = None
    response_format: Optional[Dict[str, Any]] = None
    parallel_tool_calls: Optional[bool] = None


@dataclass
class NormalizedRequest:
    request: AIRequest
    actions: List[str] = field(default_factory=list)


def normalize_request(
    request: AIRequest,
    profile: ProviderProfile,
    disabled_capabilities: Optional[Set[str]] = None,
) -> NormalizedRequest:
    disabled = set(disabled_capabilities or set())
    cloned = copy.deepcopy(request)
    messages, actions = normalize_messages(cloned.messages, profile, disabled)
    cloned.messages = messages
    return NormalizedRequest(request=cloned, actions=actions)


def normalize_messages(
    messages: List[Dict[str, Any]],
    profile: ProviderProfile,
    disabled_capabilities: Optional[Set[str]] = None,
) -> tuple[List[Dict[str, Any]], List[str]]:
    disabled = set(disabled_capabilities or set())
    capabilities = profile.capabilities
    force_text_string = "text_content_parts" in disabled
    force_drop_images = "multimodal_images" in disabled
    normalized: List[Dict[str, Any]] = []
    actions: List[str] = []

    for index, message in enumerate(copy.deepcopy(messages)):
        if not isinstance(message, dict):
            actions.append(f"drop_non_dict_message:{index}")
            continue

        role = message.get("role")
        if not role:
            actions.append(f"drop_message_without_role:{index}")
            continue

        content = message.get("content", "")
        if isinstance(content, str):
            message["content"] = content
            normalized.append(_public_message(message))
            continue

        if not isinstance(content, list):
            message["content"] = str(content if content is not None else "")
            actions.append(f"coerce_non_list_content:{index}")
            normalized.append(_public_message(message))
            continue

        parts: List[Dict[str, Any]] = []
        for part_index, part in enumerate(content):
            if not isinstance(part, dict):
                actions.append(f"drop_non_dict_part:{index}:{part_index}")
                continue

            part_type = part.get("type")
            if part_type == "text":
                text = part.get("text", "")
                if text is None:
                    text = ""
                    actions.append(f"coerce_none_text:{index}:{part_index}")
                elif not isinstance(text, str):
                    text = str(text)
                    actions.append(f"coerce_text_to_string:{index}:{part_index}")

                if text == "" and not capabilities.supports_empty_text_parts:
                    actions.append(f"drop_empty_text_part:{index}:{part_index}")
                    continue
                parts.append({"type": "text", "text": text})
                continue

            if part_type == "image_url":
                if force_drop_images or not capabilities.supports_multimodal_images:
                    actions.append(f"drop_image_part_unsupported:{index}:{part_index}")
                    continue

                image_url = part.get("image_url")
                if not isinstance(image_url, dict):
                    actions.append(f"drop_invalid_image_part:{index}:{part_index}")
                    continue

                url = image_url.get("url")
                if not isinstance(url, str) or not url:
                    actions.append(f"drop_image_part_without_url:{index}:{part_index}")
                    continue

                if url.startswith("data:") and not capabilities.supports_image_data_url:
                    actions.append(f"drop_image_data_url_unsupported:{index}:{part_index}")
                    continue

                clean_image_url = {"url": url}
                if "detail" in image_url:
                    clean_image_url["detail"] = image_url["detail"]
                parts.append({"type": "image_url", "image_url": clean_image_url})
                continue

            actions.append(f"drop_unknown_part:{index}:{part_index}:{part_type}")

        if not parts:
            message["content"] = ""
            actions.append(f"empty_content_to_string:{index}")
            normalized.append(_public_message(message))
            continue

        text_parts = [str(part.get("text", "")) for part in parts if part.get("type") == "text"]
        has_images = any(part.get("type") == "image_url" for part in parts)
        if (
            not has_images
            and capabilities.supports_text_content_string
            and (force_text_string or not capabilities.supports_text_content_parts)
        ):
            message["content"] = "".join(text_parts)
            actions.append(f"text_parts_to_string:{index}")
        else:
            message["content"] = parts
        normalized.append(_public_message(message))

    return normalized, actions


def _public_message(message: Dict[str, Any]) -> Dict[str, Any]:
    clean = {"role": message.get("role"), "content": message.get("content", "")}
    if "name" in message:
        clean["name"] = message["name"]
    return clean
