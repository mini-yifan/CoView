"""GUI task session state shared by controller and presenters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UITaskSessionState:
    """Qt 主线程上的任务会话状态。"""

    instruction: str = ""
    source: str = ""
    status_key: str = "ready"
    status_text: str = ""
    task_text: str = ""
    iteration: int = 0
    max_iterations: int = 80
    token_total: int = 0
    iterations: List[Dict[str, Any]] = field(default_factory=list)
    pending_voice_task_text: str = ""
    active_stream_iteration: Optional[int] = None
    should_show_first_startup_wait_hint: bool = True
    first_startup_wait_hint_active: bool = False
