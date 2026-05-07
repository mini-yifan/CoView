from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from baodou_ai.core.screenshot import ScreenCaptureBundle


@dataclass
class RunnerLoopState:
    """单次 run() 生命周期内的循环状态容器。"""

    thinking: str = "Incomplete"
    last_tool_feedback: str = ""
    replan_feedback: str = ""
    last_screen_group_hash: Optional[str] = None
    last_tool_signature: Optional[Dict[str, Any]] = None
    last_bundles: Optional[List[ScreenCaptureBundle]] = None
    stalled_loop_count: int = 0
    step_index: int = 0
    last_process_report_step: int = 0
    pending_required_report: bool = False
    recent_effective_history: List[Dict[str, Any]] = field(default_factory=list)
    held_modifier_notice: str = ""
    last_external_frontmost_app: Dict[str, Any] = field(default_factory=dict)
    ephemeral_page_context: Optional[Dict[str, Any]] = None
    page_extraction_notice: str = ""
    ephemeral_document_context: Optional[Dict[str, Any]] = None
    document_extraction_notice: str = ""
    reader_cleanup_pending: bool = False
    context_warning_prompt: str = ""
    model_request_count: int = 0
    any_token_usage_available: bool = False
    task_token_usage_complete: bool = True
    task_prompt_tokens: int = 0
    task_completion_tokens: int = 0
    task_total_tokens: int = 0
    last_tool_started_at: Optional[float] = None

    def push_effective_history(self, screen_hash: str, signature: Dict[str, Any], keep_last: int = 6) -> None:
        self.recent_effective_history.append({
            "screen_hash": screen_hash,
            "signature": signature,
        })
        if keep_last > 0:
            self.recent_effective_history = self.recent_effective_history[-keep_last:]

    def bump_step(self) -> None:
        self.step_index += 1

    def on_report_consumed(self, has_report: bool, report_requested: bool) -> None:
        if has_report:
            self.last_process_report_step = self.step_index
            self.pending_required_report = False
        elif report_requested:
            self.pending_required_report = True

