"""
GUI 工具执行器。
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, Optional

from baodou_ai.agent.tool_registry import normalize_tool_args
from baodou_ai.core.error_envelope import (
    CODE_TOOL_EXEC_FAILED,
    KIND_EXECUTION_FAILED,
    SOURCE_TOOL,
    from_exception,
)
from baodou_ai.core.automation_tools.runtime import RuntimeMixin, ToolInterrupted


class ToolExecutor:
    """将工具调用分发到 AutomationController。"""

    def __init__(self, automation) -> None:
        self._automation = automation

    def execute(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        screen_info: Optional[list[Dict[str, Any]]] = None,
        should_stop=None,
    ) -> Dict[str, Any]:
        normalized_args = normalize_tool_args(tool_name, tool_args)
        handler_name = f"tool_{tool_name}"
        handler = getattr(self._automation, handler_name, None)
        if handler is None:
            raise ValueError(f"未找到工具处理器: {tool_name}")
        call_kwargs: Dict[str, Any] = {
            "screen_info": screen_info,
            **normalized_args,
        }
        signature = inspect.signature(handler)
        if "should_stop" in signature.parameters:
            call_kwargs["should_stop"] = should_stop
        try:
            return handler(**call_kwargs)
        except ToolInterrupted:
            return RuntimeMixin._build_tool_result(
                False,
                RuntimeMixin._INTERRUPTED_SUMMARY,
                RuntimeMixin._INTERRUPTED_ERROR,
            )
        except Exception as exc:
            envelope = from_exception(
                exc,
                source=SOURCE_TOOL,
                kind=KIND_EXECUTION_FAILED,
                user_message="工具执行失败",
                code=CODE_TOOL_EXEC_FAILED,
                retryable=True,
                extra={
                    "tool_name": tool_name,
                    "tool_args": dict(normalized_args),
                },
            )
            return envelope.to_tool_result(
                "工具执行失败",
                ok=False,
                error=str(exc),
            )
