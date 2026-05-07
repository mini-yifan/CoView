"""Tool execution feedback builders used by the runner."""

from __future__ import annotations

from typing import Any, Dict, Optional


PAGE_EXTRACTION_FAILURE_NOTICE = (
    "The current webpage extraction failed; the previous webpage extraction content has been invalidated and cleared. "
    "Do not rely on read_current_page results to judge the current webpage content; "
    "you must extract information strictly by analyzing the screenshot."
)
PAGE_EXTRACTION_NEED_EXTRACT_FIRST_NOTICE = (
    "There is no full webpage text available for chunked reading for the current task. "
    "If you need to continue reading the webpage, call read_current_page(mode=\"extract\") first."
)
PAGE_EXTRACTION_SEARCH_NO_RESULTS_NOTICE = (
    "The current webpage search found no relevant results; the previous webpage extraction content has been invalidated and cleared. "
    "Try different keywords, shorter query terms, or use read_current_page(mode=\"chunk\") / "
    "read_current_page(mode=\"next\") to continue reading the full text."
)
PAGE_EXTRACTION_NO_MORE_CHUNKS_NOTICE = (
    "You have reached the end of the webpage; there are no more chunks. "
    "Do not continue calling read_current_page(mode=\"next\"); "
    "if you still need to reference the current chunk, proceed based on the existing webpage context."
)
DOCUMENT_EXTRACTION_FOCUS_RETRY_NOTICE = (
    "The current document extraction failed; the previous document extraction content has been invalidated and cleared. "
    "The result appears to come from a toolbar, font size bar, style bar, or other non-body area. "
    "If you still need to extract the current document, observe the screenshot first and provide the body area coordinates "
    "in the next read_current_document call; "
    "do not call again without coordinates."
)
DOCUMENT_EXTRACTION_IDE_POSITION_NOTICE = (
    "The current document extraction failed; the previous document extraction content has been invalidated and cleared. "
    "The current frontmost app is a programming IDE / editor. When calling read_current_document you must provide "
    "screen_index and position; click the code or text body area first; "
    "no extraction operation was performed this time."
)
DOCUMENT_EXTRACTION_FAILURE_NOTICE = (
    "The current document extraction failed; the previous document extraction content has been invalidated and cleared. "
    "Do not rely on read_current_document results to judge the current document content; "
    "you must extract information strictly by analyzing the screenshot."
)
DOCUMENT_EXTRACTION_UNSUPPORTED_NOTICE = (
    "The current frontmost app or platform does not support read_current_document; the previous document extraction content has been invalidated and cleared. "
    "This tool should only be used when Microsoft Word, Microsoft Excel, TextEdit, Preview, WPS, "
    "as well as Visual Studio Code, Cursor, Windsurf, IntelliJ IDEA, PyCharm, WebStorm, GoLand, CLion, "
    "Android Studio, Sublime Text, Xcode, TRAE, TRAE CN, TRAE SOLO CN is in the foreground on a supported platform."
)
DOCUMENT_EXTRACTION_NEED_EXTRACT_FIRST_NOTICE = (
    "There is no full document text available for chunked reading for the current task. "
    "If you need to continue reading the document, call read_current_document(mode=\"extract\") first."
)
DOCUMENT_EXTRACTION_SEARCH_NO_RESULTS_NOTICE = (
    "The current document search found no relevant results; the previous document extraction content has been invalidated and cleared. "
    "Try different keywords, shorter query terms, or use read_current_document(mode=\"chunk\") / "
    "read_current_document(mode=\"next\") to continue reading the full text."
)
DOCUMENT_EXTRACTION_NO_MORE_CHUNKS_NOTICE = (
    "You have reached the end of the document; there are no more chunks. "
    "Do not continue calling read_current_document(mode=\"next\"); "
    "if you still need to reference the current chunk, proceed based on the existing document context."
)


def is_copy_or_paste_hotkey(tool_name: str, tool_args: Dict[str, Any]) -> bool:
    if tool_name != "hotkey":
        return False

    keys = [str(key).strip().lower() for key in (tool_args.get("keys") or [])]
    return keys in (["command", "c"], ["ctrl", "c"], ["command", "v"], ["ctrl", "v"])


def append_remember_feedback(base_feedback: str, remember_result: Dict[str, Any], remember_content: str) -> str:
    feedback = f"{base_feedback}. Remember result: {remember_result['summary']}"
    if remember_result.get("error"):
        feedback += f". Memory write error: {remember_result['error']}"
    return feedback


def build_tool_feedback(
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Dict[str, Any],
    *,
    remember_result: Optional[Dict[str, Any]] = None,
    remember_content: str = "",
) -> str:
    if tool_name == "click":
        feedback = str(tool_result.get("summary") or "Clicked.")
    else:
        feedback = f"Executed {tool_name} tool, args: {tool_args}, result: {tool_result['summary']}"
    if tool_result.get("error"):
        feedback += f". Error: {tool_result['error']}"
    if remember_result is not None:
        feedback = append_remember_feedback(
            base_feedback=feedback,
            remember_result=remember_result,
            remember_content=remember_content,
        )

    fallback = tool_result.get("fallback")
    if isinstance(fallback, dict):
        feedback = _append_fallback_feedback(feedback, fallback)

    if tool_result.get("ok") and tool_name == "click":
        feedback += (
            ". If the next step is text input, use input_text directly."
        )
    if tool_result.get("ok") and is_copy_or_paste_hotkey(tool_name, tool_args):
        feedback += (
            ". If the text is already in context, use input_text directly instead of more GUI copy or paste."
        )
    if tool_result.get("ok") and tool_name == "read_current_page":
        feedback += _build_page_content_feedback(tool_result)
    if tool_result.get("ok") and tool_name == "read_current_document":
        feedback += _build_document_content_feedback(tool_result)

    return feedback


def build_page_loading_feedback(
    page_loading_result: Dict[str, Any],
    *,
    remember_result: Optional[Dict[str, Any]] = None,
    remember_content: str = "",
) -> str:
    feedback = str(page_loading_result.get("summary") or "Waited.")
    if page_loading_result.get("error"):
        feedback += f". Error: {page_loading_result['error']}"
    if remember_result is not None:
        feedback = append_remember_feedback(
            base_feedback=feedback,
            remember_result=remember_result,
            remember_content=remember_content,
        )
    return feedback


def build_page_extraction_notice(tool_result: Dict[str, Any]) -> str:
    fallback = tool_result.get("fallback")
    base_notice = PAGE_EXTRACTION_FAILURE_NOTICE
    if isinstance(fallback, dict):
        fallback_type = str(fallback.get("type") or "").strip()
        if fallback_type == "read_current_page_need_extract_first":
            base_notice = PAGE_EXTRACTION_NEED_EXTRACT_FIRST_NOTICE
        elif fallback_type == "read_current_page_search_no_results":
            base_notice = PAGE_EXTRACTION_SEARCH_NO_RESULTS_NOTICE
        elif fallback_type == "read_current_page_no_more_chunks":
            base_notice = PAGE_EXTRACTION_NO_MORE_CHUNKS_NOTICE
    error = str(tool_result.get("error") or "").strip()
    if error:
        return f"{base_notice} Failure reason: {error}"
    return base_notice


def build_document_extraction_notice(tool_result: Dict[str, Any]) -> str:
    fallback = tool_result.get("fallback")
    base_notice = DOCUMENT_EXTRACTION_FAILURE_NOTICE
    if isinstance(fallback, dict):
        fallback_type = str(fallback.get("type") or "").strip()
        if fallback_type == "read_current_document_focus_retry":
            base_notice = DOCUMENT_EXTRACTION_FOCUS_RETRY_NOTICE
        elif fallback_type == "read_current_document_ide_requires_position":
            base_notice = DOCUMENT_EXTRACTION_IDE_POSITION_NOTICE
        elif fallback_type == "read_current_document_need_extract_first":
            base_notice = DOCUMENT_EXTRACTION_NEED_EXTRACT_FIRST_NOTICE
        elif fallback_type == "read_current_document_search_no_results":
            base_notice = DOCUMENT_EXTRACTION_SEARCH_NO_RESULTS_NOTICE
        elif fallback_type == "read_current_document_no_more_chunks":
            base_notice = DOCUMENT_EXTRACTION_NO_MORE_CHUNKS_NOTICE
        elif fallback_type in {
            "read_current_document_not_supported_app",
            "read_current_document_not_supported_platform",
        }:
            base_notice = DOCUMENT_EXTRACTION_UNSUPPORTED_NOTICE
    error = str(tool_result.get("error") or "").strip()
    if error:
        return f"{base_notice} Failure reason: {error}"
    return base_notice


def _append_fallback_feedback(feedback: str, fallback: Dict[str, Any]) -> str:
    fallback_type = fallback.get("type")
    if fallback_type == "app_launcher_search":
        fallback_app_name = str(fallback.get("app_name") or "").strip()
        if fallback_app_name:
            return (
                feedback
                + ". launch_app did not find the app. "
                f'Use open_app_launcher and search for "{fallback_app_name}".'
            )
    if fallback_type == "read_current_page_not_browser":
        fallback_app_name = str(fallback.get("app_name") or "").strip() or "unknown app"
        return (
            feedback
            + ". read_current_page only supports browser foreground pages. "
            f'The current frontmost app is "{fallback_app_name}"; switch to a browser page first before trying again.'
        )
    if fallback_type == "read_current_page_partial":
        return (
            feedback
            + ". The webpage extraction result may be incomplete. "
            "Do not repeatedly call read_current_page; verify the page by scrolling and screenshots instead."
        )
    if fallback_type == "read_current_document_not_supported_platform":
        return (
            feedback
            + ". read_current_document only supports macOS and Windows. "
            "Stop retrying this tool and use screenshots instead."
        )
    if fallback_type == "read_current_document_not_supported_app":
        fallback_app_name = str(fallback.get("app_name") or "").strip() or "unknown app"
        return (
            feedback
            + f'. The current frontmost app "{fallback_app_name}" does not support read_current_document. '
            "Switch to a supported document app first."
        )
    if fallback_type == "read_current_document_ide_requires_position":
        return (
            feedback
            + ". The current frontmost app is a programming IDE / editor. "
            "Next time, call read_current_document(mode=\"extract\") with screen_index and position on the code or text body."
        )
    if fallback_type == "read_current_document_focus_retry":
        return (
            feedback
            + ". Current focus is not on the document body. "
            "If you retry, provide the body area coordinates in the next call."
        )
    if fallback_type == "read_current_document_copy_failed":
        return (
            feedback
            + ". The document could not be extracted reliably by copy. "
            "Stop retrying this tool and use screenshots instead."
        )
    if fallback_type == "read_current_document_need_extract_first":
        return (
            feedback
            + ". The current task has not yet successfully extracted the full document text. "
            'If you need to continue chunked reading, call read_current_document(mode="extract") first.'
        )
    if fallback_type == "read_current_document_search_no_results":
        return (
            feedback
            + ". No results related to the query term were found in the current document. "
            "Try different keywords, shorter query terms, or use chunked reading to continue reading the full text."
        )
    if fallback_type == "read_current_document_no_more_chunks":
        return (
            feedback
            + ". You are already at the end of the document. "
            "Do not call read_current_document(mode=\"next\") again."
        )
    return feedback


def _build_page_content_feedback(tool_result: Dict[str, Any]) -> str:
    page_ctx = tool_result.get("page_context") or {}
    page_content = str(page_ctx.get("content") or "").strip()
    page_url = str(page_ctx.get("url") or tool_result.get("url") or "").strip()
    page_title = str(page_ctx.get("title") or "").strip()
    page_chunk_index = int(page_ctx.get("chunk_index") or 0)
    page_total_chunks = int(page_ctx.get("total_chunks") or 0)
    page_source_mode = str(page_ctx.get("source_mode") or "").strip()
    page_has_more = bool(page_ctx.get("has_more"))
    page_summary = str(tool_result.get("summary") or "").strip()
    feedback = ""
    if page_content:
        feedback += (
            "\n\n--- Page Content ---\n"
            f"{page_content}\n"
            "--- End of Page Content ---\n"
        )
    total_chunks = max(page_total_chunks, 1)
    current_chunk = min(page_chunk_index + 1, total_chunks)
    return feedback + (
        "\n(Page Info: "
        f"Chunk {current_chunk}/{total_chunks}. "
        + (
            'Not the last chunk; call read_current_page(mode="next") to continue. '
            'Or call read_current_page(mode="search", query="...") to search for key information. '
            if page_has_more
            else ""
        )
        + f"URL={page_url}. Title={page_title or 'Untitled'}. Mode={page_source_mode}."
        + (f" Summary={page_summary}" if page_summary else "")
        + ")"
    )


def _build_document_content_feedback(tool_result: Dict[str, Any]) -> str:
    doc_ctx = tool_result.get("document_context") or {}
    doc_content = str(doc_ctx.get("content") or "").strip()
    doc_app = str(doc_ctx.get("app_name") or "").strip()
    doc_chunk_index = int(doc_ctx.get("chunk_index") or 0)
    doc_total_chunks = int(doc_ctx.get("total_chunks") or 0)
    doc_source_mode = str(doc_ctx.get("source_mode") or "").strip()
    feedback = ""
    if doc_content:
        feedback += (
            f"\n\n--- Document Content (App: {doc_app}, "
            f"Chunk: {doc_chunk_index + 1}/{max(doc_total_chunks, 1)}, "
            f"Mode: {doc_source_mode}) ---\n"
            f"{doc_content}\n"
            f"--- End of Document Content ---\n"
            f"This document content will persist in your context across turns. "
            f"If token usage approaches the limit, you will be warned to save key information via remember."
        )
    return feedback + (
        " The content from read_current_document is a copy extraction result and may be incomplete; "
        "if the task requires high-accuracy details, continue verifying the document through visual operations."
    )
