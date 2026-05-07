"""Prompt builder module."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from baodou_ai.ai.runtime_prompt_context import RuntimePromptContext


class PromptBuilder:
    """封装运行时 prompt 构建细节。"""

    def build_full_user_content(
        self,
        user_content: str,
        context: RuntimePromptContext,
        *,
        default_browser_prompt: str = "",
        respond_language: str = "",
        user_home_directory: Optional[str] = None,
    ) -> str:
        parts: List[str] = []
        task_content = user_content.strip()
        if task_content:
            parts.append(f"[Current Task]\n{task_content}")
        if context.replan_feedback:
            parts.append(f"[Replan Notice]\n{context.replan_feedback.strip()}")
        if context.frontmost_app_prompt:
            parts.append(f"[Frontmost App]\n{context.frontmost_app_prompt.strip()}")

        home_path = user_home_directory or str(Path.home())
        parts.append(f"[User Home Directory]\n{home_path}")

        screen_prompt = self.build_screen_prompt(context.screen_info or [])
        if screen_prompt:
            parts.append(screen_prompt.strip())
        if default_browser_prompt:
            parts.append(default_browser_prompt)
        if context.page_extraction_notice:
            parts.append(f"[Page Extraction Status]\n{context.page_extraction_notice.strip()}")
        if context.document_extraction_notice:
            parts.append(f"[Document Extraction Status]\n{context.document_extraction_notice.strip()}")
        if context.context_warning_prompt:
            parts.append(context.context_warning_prompt.strip())

        page_context_prompt = self.build_page_context_prompt(context.page_context)
        if page_context_prompt:
            parts.append(page_context_prompt)
        document_context_prompt = self.build_document_context_prompt(context.document_context)
        if document_context_prompt:
            parts.append(document_context_prompt)

        if context.process_report_request_prompt:
            parts.append(f"[Report Request]\n{context.process_report_request_prompt.strip()}")
        if context.held_modifier_prompt:
            parts.append(f"[Held Modifier Keys]\n{context.held_modifier_prompt.strip()}")
        if context.background_jobs_prompt:
            parts.append(f"[Background Code Jobs]\n{context.background_jobs_prompt.strip()}")
        if context.pending_reports_prompt:
            parts.append(f"[Pending Background Reports]\n{context.pending_reports_prompt.strip()}")

        if context.memory_content:
            parts.append(
                "[Important Information Memory (no need to remember what is already here)]\n"
                f"{context.memory_content.strip()}"
            )

        if respond_language:
            parts.append(
                "[Language]\n"
                f"Respond to the user in {respond_language}. "
                f"All report and respond.report text must be in {respond_language}."
            )

        return "\n\n".join(part for part in parts if part)

    @staticmethod
    def build_history_user_content(user_content: str) -> str:
        """为历史 user 消息保留最小必要的任务指令。"""
        normalized = str(user_content or "").strip()
        if not normalized:
            return ""

        task_lines: List[str] = []
        for raw_line in normalized.splitlines():
            line = raw_line.strip()
            if not line or line == "[Current Task]" or line.startswith("Current time:"):
                continue
            if line.startswith("User task:"):
                task_lines.append(line)

        if task_lines:
            return "[Current Task]\n" + "\n".join(task_lines)

        if normalized.startswith("[Current Task]"):
            in_task_section = False
            current_task_lines: List[str] = []
            for raw_line in normalized.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line == "[Current Task]":
                    in_task_section = True
                    continue
                if line.startswith("[") and line.endswith("]"):
                    if in_task_section:
                        break
                    continue
                if in_task_section:
                    current_task_lines.append(line)
            if current_task_lines:
                return "[Current Task]\n" + "\n".join(current_task_lines)

        return f"[Current Task]\n{normalized}"

    @staticmethod
    def build_page_context_prompt(page_context: Optional[Dict[str, Any]]) -> str:
        if not isinstance(page_context, dict):
            return ""

        url = str(page_context.get("url") or "").strip()
        title = str(page_context.get("title") or "").strip()
        quality = str(page_context.get("quality") or "").strip()
        source_mode = str(page_context.get("source_mode") or "").strip().lower()
        chunk_index = int(page_context.get("chunk_index") or 0)
        total_chunks = int(page_context.get("total_chunks") or 0)
        has_more = bool(page_context.get("has_more"))
        query = str(page_context.get("query") or "").strip()
        result_count = int(page_context.get("result_count") or 0)
        if not any([url, title, quality, total_chunks, query, result_count]):
            return ""

        lines = ["[Page State]"]
        lines.append(
            "You have previously read a webpage. The full content was returned in the tool result and persists in your conversation history."
        )
        if url:
            lines.append(f"URL: {url}")
        if title:
            lines.append(f"Title: {title}")
        if quality:
            lines.append(f"Quality: {quality}")
        if source_mode == "search":
            if query:
                lines.append(f"Last query: {query}")
            if result_count > 0:
                lines.append(f"Results: {result_count} items")
        elif total_chunks > 0:
            lines.append(f"Chunks: {total_chunks} total, last read: chunk {chunk_index + 1}")
            if has_more:
                lines.append(
                    'More chunks available via read_current_page(mode="next") or read_current_page(mode="chunk", chunk_index=N).'
                )
        lines.append('You can continue reading with read_current_page(mode="chunk"/"next"/"search") at any time.')
        return "\n".join(lines)

    @staticmethod
    def build_document_context_prompt(document_context: Optional[Dict[str, Any]]) -> str:
        if not isinstance(document_context, dict):
            return ""

        app_name = str(document_context.get("app_name") or "").strip()
        source_mode = str(document_context.get("source_mode") or "").strip().lower()
        chunk_index = int(document_context.get("chunk_index") or 0)
        total_chunks = int(document_context.get("total_chunks") or 0)
        has_more = bool(document_context.get("has_more"))
        query = str(document_context.get("query") or "").strip()
        result_count = int(document_context.get("result_count") or 0)
        if not any([app_name, total_chunks, query, result_count]):
            return ""

        lines = ["[Document State]"]
        lines.append(
            "You have previously read a document. The full content was returned in the tool result and persists in your conversation history."
        )
        if app_name:
            lines.append(f"App: {app_name}")
        if source_mode == "search":
            if query:
                lines.append(f"Last query: {query}")
            if result_count > 0:
                lines.append(f"Results: {result_count} items")
        elif total_chunks > 0:
            lines.append(f"Chunks: {total_chunks} total, last read: chunk {chunk_index + 1}")
            if has_more:
                lines.append(
                    'More chunks available via read_current_document(mode="next") or read_current_document(mode="chunk", chunk_index=N).'
                )
        lines.append('You can continue reading with read_current_document(mode="chunk"/"next"/"search") at any time.')
        return "\n".join(lines)

    @staticmethod
    def build_screen_prompt(screen_info: List[Dict[str, Any]]) -> str:
        """构建屏幕信息提示。"""
        if not screen_info:
            return ""

        prompt = f"The current system has {len(screen_info)} screen(s):\n"
        for info in screen_info:
            primary = " (Primary)" if info.get("is_primary") else ""
            prompt += f"- Screen {info['index']}{primary}\n"
        return prompt
