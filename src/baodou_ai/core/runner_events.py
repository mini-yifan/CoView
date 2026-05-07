"""Event and payload builders for the control loop runner."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from baodou_ai.agent.protocol import get_agent_response_branch, is_tool_branch
from baodou_ai.agent.tool_registry import tool_call_to_legacy_fields


def build_invalid_model_output_feedback(parse_error: str = "") -> str:
    feedback = (
        "The previous model output was invalid and was not executed. "
        "Return exactly one valid JSON object that follows the protocol, fix the invalid field or argument, "
        "and do not repeat the same invalid output."
    )
    normalized_error = str(parse_error or "").strip()
    if normalized_error:
        feedback += f" Validation error: {normalized_error}."
        if ("最多删除" in normalized_error or "最多创建" in normalized_error) and "20" in normalized_error:
            feedback += (
                " If the task still needs all items handled, split them into multiple manage_files calls with at most 20 items per call."
            )
    return feedback


def build_iteration_payload(
    agent_response: Dict[str, Any],
    action_result: str,
    capture_ms: float,
    settle_ms: float,
    execute_ms: float,
    loop_total_ms: float,
    changed_pixels_ratio: float,
    screen_count: int,
    ai_metrics: Dict[str, Any],
    report_mode: str,
    report_requested: bool,
    report_request_reason: str,
    loop_report_requested: bool,
    held_modifier_keys: Optional[List[str]] = None,
    held_modifier_notice: str = "",
    tool_result: Optional[Dict[str, Any]] = None,
    remember_content: str = "",
    remember_written: bool = False,
) -> Dict[str, Any]:
    branch = get_agent_response_branch(agent_response)
    respond_payload = agent_response.get("respond", {})

    if is_tool_branch(branch):
        legacy_fields = tool_call_to_legacy_fields(branch, agent_response[branch])
    elif branch == "page_loading":
        legacy_fields = {
            "action": "page_loading",
            "coordinates": [0, 0],
            "type_information": "",
            "screen_index": 0,
            "end_screen_index": 0,
            "element_info": "",
        }
    elif branch == "respond":
        outcome = respond_payload.get("outcome", "")
        legacy_fields = {
            "action": "",
            "coordinates": [0, 0],
            "type_information": respond_payload.get("report", ""),
            "screen_index": 0,
            "end_screen_index": 0,
            "element_info": "",
            "whether_completed": "True" if outcome == "completed" else "difficult",
        }
    else:
        legacy_fields = {
            "action": branch,
            "coordinates": [0, 0],
            "type_information": "",
            "screen_index": 0,
            "end_screen_index": 0,
            "element_info": "",
        }

    return {
        "thinking": agent_response.get("thinking", ""),
        "status": branch,
        "report": "" if branch == "respond" else agent_response.get("report", ""),
        "outcome": respond_payload.get("outcome", ""),
        "report_mode": report_mode,
        "report_requested": report_requested,
        "report_request_reason": report_request_reason,
        "loop_report_requested": loop_report_requested,
        "held_modifier_keys": list(held_modifier_keys or []),
        "held_modifier_notice": held_modifier_notice,
        "tool_name": branch if is_tool_branch(branch) else None,
        "tool_args": agent_response.get(branch) if is_tool_branch(branch) else None,
        "tool_result": tool_result,
        "remember_content": remember_content,
        "remember_written": remember_written,
        "content": remember_content,
        "element_info": legacy_fields.get("element_info", ""),
        "coordinates": legacy_fields.get("coordinates", [0, 0]),
        "action": legacy_fields.get("action", ""),
        "type_information": legacy_fields.get("type_information", ""),
        "screen_index": legacy_fields.get("screen_index", 0),
        "action_result": action_result,
        "capture_ms": capture_ms,
        "settle_ms": settle_ms,
        "execute_ms": execute_ms,
        "loop_total_ms": loop_total_ms,
        "changed_pixels_ratio": changed_pixels_ratio,
        "screen_count": screen_count,
        **ai_metrics,
    }

