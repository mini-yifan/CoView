"""Token metrics helpers for the control loop runner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from baodou_ai.core.runner_state import RunnerLoopState


@dataclass(frozen=True)
class ModelMetricsUpdate:
    """Normalized metrics after applying one model request to loop state."""

    metrics: Dict[str, Any]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]


def coerce_optional_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def did_model_request_execute(ai_metrics: Dict[str, Any]) -> bool:
    numeric_keys = (
        "encode_ms",
        "request_prepare_ms",
        "model_latency_ms",
        "first_chunk_ms",
    )
    if any(float(ai_metrics.get(key) or 0.0) > 0.0 for key in numeric_keys):
        return True
    return bool(ai_metrics.get("token_usage_available"))


def apply_model_metrics_to_state(state: RunnerLoopState, ai_metrics: Dict[str, Any]) -> ModelMetricsUpdate:
    """Normalize one response's metrics and update task-level counters."""

    state.model_request_count += 1
    prompt_tokens = coerce_optional_int(ai_metrics.get("prompt_tokens"))
    completion_tokens = coerce_optional_int(ai_metrics.get("completion_tokens"))
    total_tokens = coerce_optional_int(ai_metrics.get("total_tokens"))
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

    normalized_ai_metrics = dict(ai_metrics)
    normalized_ai_metrics["prompt_tokens"] = prompt_tokens
    normalized_ai_metrics["completion_tokens"] = completion_tokens
    normalized_ai_metrics["total_tokens"] = total_tokens

    if normalized_ai_metrics.get("token_usage_available"):
        state.any_token_usage_available = True
        state.task_prompt_tokens += prompt_tokens or 0
        state.task_completion_tokens += completion_tokens or 0
        state.task_total_tokens += total_tokens or 0
    else:
        state.task_token_usage_complete = False

    normalized_ai_metrics.update({
        "task_prompt_tokens": state.task_prompt_tokens if state.any_token_usage_available else None,
        "task_completion_tokens": state.task_completion_tokens if state.any_token_usage_available else None,
        "task_total_tokens": state.task_total_tokens if state.any_token_usage_available else None,
        "task_token_usage_complete": state.task_token_usage_complete and state.any_token_usage_available,
        "model_request_count": state.model_request_count,
    })
    return ModelMetricsUpdate(
        metrics=normalized_ai_metrics,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def build_iteration_token_log(iteration_index: int, ai_metrics: Dict[str, Any]) -> str:
    if not ai_metrics.get("token_usage_available"):
        return f"[第 {iteration_index + 1} 轮 Token] 当前接口未返回 token usage"

    prompt_tokens = coerce_optional_int(ai_metrics.get("prompt_tokens")) or 0
    completion_tokens = coerce_optional_int(ai_metrics.get("completion_tokens")) or 0
    total_tokens = coerce_optional_int(ai_metrics.get("total_tokens"))
    if total_tokens is None:
        total_tokens = prompt_tokens + completion_tokens

    task_total_tokens = coerce_optional_int(ai_metrics.get("task_total_tokens"))
    cumulative_label = (
        f"累计 {task_total_tokens}"
        if bool(ai_metrics.get("task_token_usage_complete")) and task_total_tokens is not None
        else (
            f"累计(部分) {task_total_tokens}"
            if task_total_tokens is not None
            else "累计暂不可用"
        )
    )

    return (
        f"[第 {iteration_index + 1} 轮 Token] "
        f"输入 {prompt_tokens} | 输出 {completion_tokens} | 合计 {total_tokens} | {cumulative_label}"
    )


def build_task_token_summary(
    model_request_count: int,
    any_token_usage_available: bool,
    task_token_usage_complete: bool,
    task_prompt_tokens: int,
    task_completion_tokens: int,
    task_total_tokens: int,
) -> str:
    if model_request_count <= 0:
        return ""
    if not any_token_usage_available:
        return f"[任务 Token 汇总] 共发起 {model_request_count} 轮模型调用，但当前接口未返回 token usage"
    if not task_token_usage_complete:
        return (
            f"[任务 Token 汇总] 共发起 {model_request_count} 轮模型调用，"
            f"token usage 未完整返回；当前已统计 输入 {task_prompt_tokens} | "
            f"输出 {task_completion_tokens} | 合计 {task_total_tokens}"
        )
    return (
        f"[任务 Token 汇总] 轮数 {model_request_count} | "
        f"输入 {task_prompt_tokens} | 输出 {task_completion_tokens} | 合计 {task_total_tokens}"
    )

