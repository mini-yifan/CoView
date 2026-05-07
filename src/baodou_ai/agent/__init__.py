"""
Agent 协议与工具注册模块。
"""

from baodou_ai.agent.protocol import (
    normalize_agent_response,
    is_tool_branch,
    get_agent_response_branch,
)
from baodou_ai.agent.tool_registry import (
    TOOL_DEFINITIONS,
    get_tool_json_schema,
    get_tool_definition,
    normalize_tool_args,
    render_tool_prompt,
    tool_call_to_legacy_fields,
)

__all__ = [
    "TOOL_DEFINITIONS",
    "get_agent_response_branch",
    "get_tool_json_schema",
    "get_tool_definition",
    "is_tool_branch",
    "normalize_agent_response",
    "normalize_tool_args",
    "render_tool_prompt",
    "tool_call_to_legacy_fields",
]
