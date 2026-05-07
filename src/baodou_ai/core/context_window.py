from typing import Any, Dict, Optional


class ContextWindowManager:
    """管理 page/document 临时上下文窗口及清理策略。"""

    CONTEXT_WARNING_PROMPT = (
        "[Context Warning] Token usage has reached 80% of the context limit. "
        "The previously read page/document content will be cleared in the next turn. "
        "If you still need key information from the page or document, use the remember tool NOW "
        "to save it before it is permanently lost."
    )

    def __init__(self) -> None:
        self.ephemeral_page_context: Optional[Dict[str, Any]] = None
        self.page_extraction_notice: str = ""
        self.ephemeral_document_context: Optional[Dict[str, Any]] = None
        self.document_extraction_notice: str = ""
        self.reader_cleanup_pending: bool = False
        self.context_warning_prompt: str = ""

    def reset(self) -> None:
        self.ephemeral_page_context = None
        self.page_extraction_notice = ""
        self.ephemeral_document_context = None
        self.document_extraction_notice = ""
        self.reader_cleanup_pending = False
        self.context_warning_prompt = ""

    def consume_context_warning_prompt(self) -> str:
        prompt = self.context_warning_prompt
        self.context_warning_prompt = ""
        return prompt

    def apply_pending_cleanup(self, automation: Any) -> bool:
        if not self.reader_cleanup_pending:
            return False

        clear_page_state = getattr(automation, "clear_page_reader_state", None)
        if callable(clear_page_state):
            clear_page_state()

        clear_document_state = getattr(automation, "clear_document_reader_state", None)
        if callable(clear_document_state):
            clear_document_state()

        self.ephemeral_page_context = None
        self.page_extraction_notice = ""
        self.ephemeral_document_context = None
        self.document_extraction_notice = ""
        self.reader_cleanup_pending = False
        return True

    def maybe_schedule_cleanup_on_tokens(
        self,
        round_prompt_tokens: Optional[int],
        context_token_limit: int,
    ) -> bool:
        if (
            self.reader_cleanup_pending
            or (self.ephemeral_document_context is None and self.ephemeral_page_context is None)
            or round_prompt_tokens is None
            or context_token_limit <= 0
            or round_prompt_tokens < context_token_limit * 0.8
        ):
            return False

        self.reader_cleanup_pending = True
        self.context_warning_prompt = self.CONTEXT_WARNING_PROMPT
        return True

    def update_after_page_tool(
        self,
        tool_result: Dict[str, Any],
        build_page_extraction_notice: Any,
    ) -> None:
        if tool_result.get("ok"):
            page_context = tool_result.get("page_context")
            self.ephemeral_page_context = dict(page_context) if isinstance(page_context, dict) else None
            self.page_extraction_notice = ""
            return

        fallback = tool_result.get("fallback")
        preserve_page_context = (
            isinstance(fallback, dict)
            and str(fallback.get("type") or "").strip() == "read_current_page_no_more_chunks"
        )
        if not preserve_page_context:
            self.ephemeral_page_context = None
        self.page_extraction_notice = build_page_extraction_notice(tool_result)

    def update_after_document_tool(
        self,
        tool_result: Dict[str, Any],
        build_document_extraction_notice: Any,
    ) -> None:
        if tool_result.get("ok"):
            document_context = tool_result.get("document_context")
            self.ephemeral_document_context = dict(document_context) if isinstance(document_context, dict) else None
            self.document_extraction_notice = ""
            return

        fallback = tool_result.get("fallback")
        preserve_document_context = (
            isinstance(fallback, dict)
            and str(fallback.get("type") or "").strip() == "read_current_document_no_more_chunks"
        )
        if not preserve_document_context:
            self.ephemeral_document_context = None
        self.document_extraction_notice = build_document_extraction_notice(tool_result)

