"""Runtime prompt context objects."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class RuntimePromptContext:
    """聚合运行时 prompt 构建所需的上下文字段。"""

    screen_info: Optional[List[Dict[str, Any]]] = None
    memory_content: str = ""
    page_context: Optional[Dict[str, Any]] = None
    page_extraction_notice: str = ""
    document_context: Optional[Dict[str, Any]] = None
    document_extraction_notice: str = ""
    context_warning_prompt: str = ""
    replan_feedback: str = ""
    process_report_mode: str = "auto"
    process_report_request_prompt: str = ""
    held_modifier_prompt: str = ""
    frontmost_app_prompt: str = ""
    background_jobs_prompt: str = ""
    pending_reports_prompt: str = ""
