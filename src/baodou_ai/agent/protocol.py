"""
Agent 顶层协议归一化。

扁平化协议：工具名直接作为顶层键，不再使用 tool_call 间接层。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

from baodou_ai.agent.schemas import (
    normalize_page_loading_payload,
    normalize_remember_payload,
    normalize_respond_payload,
)
from baodou_ai.agent.tool_registry import normalize_tool_args, TOOL_DEFINITIONS


NON_BRANCH_KEYS = {"thinking", "report", "remember"}

TOOL_NAMES: Set[str] = set(TOOL_DEFINITIONS.keys())


def _normalize_text(value: Any, field_name: str, allow_empty: bool = False) -> str:
    if value is None:
        raise ValueError(f"{field_name} 不能为空")
    text = str(value).strip()
    if not allow_empty and not text:
        raise ValueError(f"{field_name} 不能为空")
    return text


def _normalize_optional_text(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def get_agent_response_branch(response: Dict[str, Any]) -> str:
    branch_keys = [key for key in response if key not in NON_BRANCH_KEYS]
    if len(branch_keys) != 1:
        raise ValueError("顶层必须且只能出现一个分支键")
    return branch_keys[0]


def is_tool_branch(branch_key: str) -> bool:
    return branch_key in TOOL_NAMES and branch_key not in {"page_loading", "respond"}


def normalize_agent_response(response: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(response, dict):
        raise ValueError("响应必须是 JSON 对象")

    thinking = _normalize_text(response.get("thinking"), "thinking")
    top_report = _normalize_optional_text(response.get("report"), "report")
    remember_payload = response.get("remember")
    branch = get_agent_response_branch(response)

    allowed_top_level = NON_BRANCH_KEYS | {branch}
    extra_keys = sorted(set(response.keys()) - allowed_top_level)
    if extra_keys:
        raise ValueError(f"顶层存在不允许的字段: {', '.join(extra_keys)}")

    normalized: Dict[str, Any] = {
        "thinking": thinking,
    }
    if top_report and branch != "respond":
        normalized["report"] = top_report

    if remember_payload is not None:
        normalized["remember"] = normalize_remember_payload(remember_payload)

    if branch == "respond":
        normalized["respond"] = normalize_respond_payload(response.get("respond"))
        return normalized

    if branch == "page_loading":
        normalized["page_loading"] = normalize_page_loading_payload(response.get("page_loading"))
        return normalized

    if branch in TOOL_NAMES:
        tool_args = response.get(branch)
        if tool_args is None:
            tool_args = {}
        if not isinstance(tool_args, dict):
            raise ValueError(f"{branch} 的参数必须是对象")
        normalized[branch] = normalize_tool_args(branch, tool_args)
        return normalized

    raise ValueError(f"未知的分支键: {branch}")
