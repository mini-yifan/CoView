"""Document/editor reader automation tools."""

from __future__ import annotations

import time
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .constants import (
    DOCUMENT_ANCHOR_LEADING_SKIP_CHARS,
    DOCUMENT_ANCHOR_WEAK_PUNCTUATION_CHARS,
    DOCUMENT_CHUNK_MAX_TOKENS,
    DOCUMENT_CHUNK_MIN_TOKENS,
    DOCUMENT_CHUNK_TARGET_TOKENS,
    DOCUMENT_SEARCH_CODE_CONTEXT_LINES,
    DOCUMENT_SEARCH_DEFAULT_TOP_K,
    DOCUMENT_SEARCH_MAX_TOP_K,
    DOCUMENT_SUPPORTED_APP_NAMES_TEXT,
    DOCUMENT_SUPPORTED_DOCUMENT_APP_NAMES,
    DOCUMENT_SUPPORTED_IDE_APP_NAMES,
    DOCUMENT_VIEW_FOLLOW_ANCHOR_LENGTH,
    DOCUMENT_VIEW_FOLLOW_SCAN_WINDOW,
    automation_exports,
    tiktoken,
)
from .runtime import ToolInterrupted


class DocumentReaderMixin:
    def tool_read_current_document(
        self,
        mode: str = "extract",
        follow_view: bool = False,
        chunk_index: Optional[int] = None,
        query: Optional[str] = None,
        top_k: int = DOCUMENT_SEARCH_DEFAULT_TOP_K,
        screen_index: Optional[int] = None,
        position: Optional[List[float]] = None,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        try:
            return self._tool_read_current_document_interruptible(
                mode=mode,
                follow_view=follow_view,
                chunk_index=chunk_index,
                query=query,
                top_k=top_k,
                screen_index=screen_index,
                position=position,
                screen_info=screen_info,
                should_stop=should_stop,
            )
        except ToolInterrupted:
            return self._build_tool_result(False, self._INTERRUPTED_SUMMARY, self._INTERRUPTED_ERROR)

    def _tool_read_current_document_interruptible(
        self,
        mode: str = "extract",
        follow_view: bool = False,
        chunk_index: Optional[int] = None,
        query: Optional[str] = None,
        top_k: int = DOCUMENT_SEARCH_DEFAULT_TOP_K,
        screen_index: Optional[int] = None,
        position: Optional[List[float]] = None,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        self._raise_if_stopped(should_stop)
        normalized_mode = str(mode or "extract").strip().lower()
        if normalized_mode == "chunk":
            return self._read_current_document_chunk(
                chunk_index,
                follow_view=follow_view,
                should_stop=should_stop,
            )
        if normalized_mode == "next":
            return self._read_next_document_chunk(follow_view=follow_view, should_stop=should_stop)
        if normalized_mode == "search":
            return self._search_current_document(
                query=query,
                top_k=top_k,
                follow_view=follow_view,
                should_stop=should_stop,
            )

        has_position = position is not None or screen_index is not None
        if has_position and (position is None or screen_index is None):
            return self._build_tool_result(
                False,
                "读取当前文档失败",
                "read_current_document 传入坐标时必须同时提供 screen_index 和 position。",
                fallback={"type": "read_current_document_copy_failed"},
            )

        if not self._is_supported_document_platform(self._current_os):
            self._document_reader_state = {}
            return self._build_tool_result(
                False,
                "读取当前文档失败",
                "当前平台不支持 read_current_document，当前仅支持 macOS 和 Windows。",
                fallback={
                    "type": "read_current_document_not_supported_platform",
                    "platform": self._current_os,
                },
            )

        frontmost = self.get_frontmost_app_info()
        self._raise_if_stopped(should_stop)
        app_name = self._get_frontmost_app_label(frontmost)
        app_family = self._get_document_app_family(frontmost)
        if not self._is_supported_document_frontmost_app(frontmost):
            self._document_reader_state = {}
            return self._build_document_failure_result(
                fallback_type="read_current_document_not_supported_app",
                app_name=app_name,
                error=(
                    "read_current_document 仅支持在以下前台应用中使用："
                    f"{DOCUMENT_SUPPORTED_APP_NAMES_TEXT}。"
                    f"当前前台应用为：{app_name}。"
                ),
            )
        if self._should_require_position_for_extract(app_family, self._current_os) and not has_position:
            self._document_reader_state = {}
            return self._build_document_failure_result(
                fallback_type="read_current_document_ide_requires_position",
                app_name=app_name,
                error=(
                    "当前前台应用是编程 IDE。调用 read_current_document 时必须同时提供 "
                    "screen_index 和 position，用于先点击代码或文本正文区域；"
                    "本次未执行任何提取操作。"
                ),
            )

        has_backup, original_clipboard = self._backup_clipboard_text()
        try:
            self._hide_windows()
            try:
                self._release_stuck_modifiers()
                self._raise_if_stopped(should_stop)
                self._call_with_optional_should_stop(
                    self._press_escape_repeated,
                    2,
                    should_stop=should_stop,
                )
                if self._should_prefocus_document_body(app_family, self._current_os, has_position):
                    self._raise_if_stopped(should_stop)
                    self._call_with_optional_should_stop(
                        self._prefocus_document_body,
                        app_family=app_family,
                        should_stop=should_stop,
                    )
                if has_position and position is not None and screen_index is not None:
                    self._raise_if_stopped(should_stop)
                    self._call_with_optional_should_stop(
                        self._focus_document_position,
                        screen_index=screen_index,
                        position=position,
                        screen_info=screen_info,
                        should_stop=should_stop,
                    )
                    if not self._sleep_interruptibly(0.08, should_stop=should_stop):
                        raise ToolInterrupted(self._INTERRUPTED_ERROR)

                modifier = self._get_hotkey_modifier()
                sentinel = f"__baodou_ai_document_extract_{automation_exports().time.time_ns()}__"
                self._raise_if_stopped(should_stop)
                automation_exports().pyperclip.copy(sentinel)
                if not self._sleep_interruptibly(0.05, should_stop=should_stop):
                    raise ToolInterrupted(self._INTERRUPTED_ERROR)
                self._call_with_optional_should_stop(
                    self._press_hotkey_with_modifier,
                    modifier,
                    "a",
                    should_stop=should_stop,
                )
                if not self._sleep_interruptibly(0.12, should_stop=should_stop):
                    raise ToolInterrupted(self._INTERRUPTED_ERROR)
                self._call_with_optional_should_stop(
                    self._press_hotkey_with_modifier,
                    modifier,
                    "c",
                    should_stop=should_stop,
                )
                extracted_text = self._call_with_optional_should_stop(
                    self._wait_for_changed_clipboard_text,
                    previous_content=sentinel,
                    timeout_seconds=0.9,
                    should_stop=should_stop,
                )
            finally:
                self._show_windows()
        except ToolInterrupted:
            raise
        except Exception as exc:
            fallback_type = "read_current_document_copy_failed"
            if not has_position:
                fallback_type = "read_current_document_focus_retry"
            self._document_reader_state = {}
            return self._build_document_failure_result(
                fallback_type=fallback_type,
                app_name=app_name,
                error=f"读取当前文档时发生异常：{exc}",
            )
        finally:
            self._restore_clipboard_text(has_backup, original_clipboard)

        normalized_text = str(extracted_text or "").strip()
        self._raise_if_stopped(should_stop)
        if not normalized_text:
            fallback_type = "read_current_document_copy_failed" if has_position else "read_current_document_focus_retry"
            error = "未能从当前文档提取到有效文本。"
            if not has_position:
                error += "请先观察截图并在下次 read_current_document 调用时传入正文区域坐标。"
            else:
                error += "请改用图片或截图分析当前文档内容。"
            self._document_reader_state = {}
            return self._build_document_failure_result(
                fallback_type=fallback_type,
                app_name=app_name,
                error=error,
            )

        if not has_position and self._looks_like_document_toolbar_value(normalized_text):
            self._document_reader_state = {}
            return self._build_document_failure_result(
                fallback_type="read_current_document_focus_retry",
                app_name=app_name,
                error=(
                    "复制结果疑似来自工具栏、字号栏、样式栏或其他非正文区域。"
                    "请先观察截图并在下次 read_current_document 调用时传入正文区域坐标。"
                ),
            )

        self._raise_if_stopped(should_stop)
        record_path = self._write_document_content_record(
            app_name=app_name,
            content=normalized_text,
        )
        self._raise_if_stopped(should_stop)
        self._set_document_reader_state(
            app_name=app_name,
            app_family=app_family,
            content=normalized_text,
            record_path=record_path,
        )
        self._raise_if_stopped(should_stop)
        return self._build_document_chunk_success_result(
            source_mode="extract",
            should_stop=should_stop,
        )

    @staticmethod
    def _get_frontmost_app_label(app_info: Optional[Dict[str, Any]]) -> str:
        if not isinstance(app_info, dict):
            return "未知应用"
        return str(
            app_info.get("app_name")
            or app_info.get("identifier")
            or app_info.get("bundle_id")
            or "未知应用"
        ).strip()

    @staticmethod
    def _is_supported_document_frontmost_app(app_info: Optional[Dict[str, Any]]) -> bool:
        return bool(DocumentReaderMixin._get_document_app_family(app_info))

    @staticmethod
    def _get_document_app_family(
        app_info: Optional[Dict[str, Any]] = None,
        app_name: str = "",
    ) -> str:
        combined_parts = []
        if isinstance(app_info, dict):
            combined_parts.extend(
                str(app_info.get(key) or "").strip().lower()
                for key in ("app_name", "bundle_id", "identifier")
            )
        if app_name:
            combined_parts.append(str(app_name).strip().lower())

        combined = " ".join(part for part in combined_parts if part)
        if not combined:
            return ""

        if "microsoft word" in combined or "com.microsoft.word" in combined:
            return "word"
        if "winword.exe" in combined:
            return "word"
        if "microsoft excel" in combined or "com.microsoft.excel" in combined:
            return "excel"
        if "excel.exe" in combined:
            return "excel"
        if "textedit" in combined or "com.apple.textedit" in combined:
            return "textedit"
        if "notepad.exe" in combined:
            return "textedit"
        if "preview" in combined or "com.apple.preview" in combined:
            return "preview"
        if "wps" in combined or "kingsoft" in combined:
            return "wps"
        if re.search(r"\b(et|wpp)\.exe\b", combined):
            return "wps"
        if (
            "visual studio code" in combined
            or "com.microsoft.vscode" in combined
            or "com.microsoft.vscodeinsiders" in combined
            or "code.exe" in combined
            or re.search(r"\bvscode\b", combined)
        ):
            return "vscode"
        if "cursor" in combined:
            return "cursor"
        if "windsurf" in combined:
            return "windsurf"
        if "intellij idea" in combined or "com.jetbrains.intellij" in combined:
            return "intellij"
        if "idea64.exe" in combined:
            return "intellij"
        if "pycharm" in combined or "com.jetbrains.pycharm" in combined:
            return "pycharm"
        if "pycharm64.exe" in combined:
            return "pycharm"
        if "webstorm" in combined or "com.jetbrains.webstorm" in combined:
            return "webstorm"
        if "webstorm64.exe" in combined:
            return "webstorm"
        if "goland" in combined or "com.jetbrains.goland" in combined:
            return "goland"
        if "goland64.exe" in combined:
            return "goland"
        if "clion" in combined or "com.jetbrains.clion" in combined:
            return "clion"
        if "clion64.exe" in combined:
            return "clion"
        if (
            "android studio" in combined
            or "androidstudio" in combined
            or "com.google.android.studio" in combined
            or "com.jetbrains.androidstudio" in combined
            or "studio64.exe" in combined
        ):
            return "androidstudio"
        if "sublime text" in combined or "com.sublimetext" in combined or "sublime_text.exe" in combined:
            return "sublime"
        if "com.apple.dt.xcode" in combined or re.search(r"\bxcode\b", combined):
            return "xcode"
        if (
            "cn.trae.app" in combined
            or "cn.trae.solo.app" in combined
            or "trae cn" in combined
            or "trae solo cn" in combined
            or re.search(r"\btrae\b", combined)
        ):
            return "trae"
        return ""

    @staticmethod
    def _is_supported_document_platform(current_os: str) -> bool:
        return str(current_os or "").strip() in {"Darwin", "Windows"}

    @staticmethod
    def _supports_document_view_follow(app_family: str) -> bool:
        return str(app_family or "").strip().lower() in {"word", "wps", "textedit"}

    @staticmethod
    def _requires_document_extract_position(app_family: str) -> bool:
        return str(app_family or "").strip().lower() in {
            "vscode",
            "cursor",
            "windsurf",
            "intellij",
            "pycharm",
            "webstorm",
            "goland",
            "clion",
            "androidstudio",
            "sublime",
            "xcode",
            "trae",
        }

    @classmethod
    def _supports_document_view_follow_for_platform(cls, app_family: str, current_os: str) -> bool:
        return str(current_os or "").strip() == "Darwin" and cls._supports_document_view_follow(app_family)

    @classmethod
    def _should_require_position_for_extract(cls, app_family: str, current_os: str) -> bool:
        if str(current_os or "").strip() not in {"Darwin", "Windows"}:
            return False
        return cls._requires_document_extract_position(app_family)

    @staticmethod
    def _build_document_view_follow_disabled_message(context_description: str, current_os: str) -> str:
        if str(current_os or "").strip() == "Windows":
            return f"Windows V1 暂不支持文档视觉跳转，仅更新了{context_description}。"
        return f"当前文档应用暂不支持视觉跳转，仅更新了{context_description}。"

    @staticmethod
    def _should_prefocus_document_body(app_family: str, current_os: str, has_position: bool) -> bool:
        return str(current_os or "").strip() == "Windows" and str(app_family or "").strip().lower() == "wps" and not has_position

    def _focus_document_position(
        self,
        screen_index: int,
        position: List[float],
        screen_info: Optional[List[Dict[str, Any]]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._raise_if_stopped(should_stop)
        target_screen = None
        if screen_info and 0 <= screen_index < len(screen_info):
            target_screen = screen_info[screen_index]
        elif screen_info:
            target_screen = screen_info[0]
        duration = self._config.mouse_config.get("move_duration", 0.1)
        self._handle_single_point(position, "click", duration, target_screen)
        self._raise_if_stopped(should_stop)

    def _prefocus_document_body(
        self,
        app_family: str,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> None:
        if str(app_family or "").strip().lower() != "wps" or self._current_os != "Windows":
            return

        getter = getattr(self._platform_adapter, "get_frontmost_window_info", None)
        if not callable(getter):
            return

        window_info = getter() or {}
        bounds = window_info.get("bounds") or {}
        width = int(bounds.get("width") or 0)
        height = int(bounds.get("height") or 0)
        if width <= 0 or height <= 0:
            return

        x = int(bounds.get("x") or 0) + int(width * 0.5)
        y = int(bounds.get("y") or 0) + int(height * 0.42)
        duration = float(self._config.mouse_config.get("move_duration", 0.1))
        self._platform_adapter.move_cursor(x, y, duration=duration)
        self._raise_if_stopped(should_stop)
        self._platform_adapter.click(button="left")
        if not self._sleep_interruptibly(0.08, should_stop=should_stop):
            raise ToolInterrupted(self._INTERRUPTED_ERROR)

    @staticmethod
    def _looks_like_document_toolbar_value(text: str) -> bool:
        normalized = str(text or "").strip()
        if not normalized:
            return False
        if any(separator in normalized for separator in ("\n", "\t", " ")):
            return False

        lowered = normalized.casefold()
        common_toolbar_tokens = {
            "calibri",
            "arial",
            "aptos",
            "宋体",
            "黑体",
            "仿宋",
            "楷体",
            "微软雅黑",
            "等线",
            "正文",
            "标题",
            "normal",
            "body",
            "heading",
        }
        if lowered in common_toolbar_tokens:
            return True

        if re.fullmatch(r"\d{1,3}(\.\d+)?%?", normalized):
            return True

        return False

    def _build_document_failure_result(
        self,
        fallback_type: str,
        app_name: str,
        error: str,
        **extra_fields: Any,
    ) -> Dict[str, Any]:
        fallback = {"type": fallback_type, "app_name": app_name}
        result = self._build_tool_result(False, "读取当前文档失败", error, fallback=fallback)
        result.update(extra_fields)
        return result

    @staticmethod
    @lru_cache(maxsize=1)
    def _get_document_token_encoder() -> Any:
        if tiktoken is None:
            return None
        return tiktoken.get_encoding("cl100k_base")

    @classmethod
    def _count_document_tokens(cls, text: str) -> int:
        normalized = str(text or "")
        if not normalized:
            return 0
        encoder = cls._get_document_token_encoder()
        if encoder is not None:
            return len(encoder.encode(normalized, disallowed_special=()))

        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", normalized))
        word_count = len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", normalized))
        symbol_count = len(re.findall(r"[^\sA-Za-z0-9\u4e00-\u9fff]", normalized))
        return cjk_count + word_count + ((symbol_count + 3) // 4)

    @classmethod
    def _find_document_index_for_token_budget(
        cls,
        content: str,
        start: int,
        target_tokens: int,
    ) -> int:
        normalized = str(content or "")
        if start >= len(normalized):
            return len(normalized)

        remaining = normalized[start:]
        if cls._count_document_tokens(remaining) <= max(int(target_tokens or 0), 0):
            return len(normalized)

        low = start + 1
        high = len(normalized)
        best = len(normalized)
        while low <= high:
            mid = (low + high) // 2
            token_count = cls._count_document_tokens(normalized[start:mid])
            if token_count >= target_tokens:
                best = mid
                high = mid - 1
            else:
                low = mid + 1
        return best

    @staticmethod
    def _find_document_chunk_boundary(
        content: str,
        start: int,
        min_end: int,
        target_end: int,
        max_end: int,
    ) -> int:
        text_length = len(content)
        if max_end >= text_length:
            return text_length

        search_start = max(start + 1, min(min_end, text_length))
        search_target = min(max(target_end, search_start), text_length)
        search_end = min(max(max_end, search_target), text_length)
        marker_groups = (
            ("\n\n",),
            ("\n",),
            ("。", "！", "？", ".", "!", "?", "；", ";"),
            ("，", ",", "、", "：", ":"),
        )

        for markers in marker_groups:
            best_index = -1
            best_marker = ""
            for marker in markers:
                marker_index = content.rfind(marker, search_start, search_target)
                if marker_index > best_index:
                    best_index = marker_index
                    best_marker = marker
            if best_index >= 0:
                return best_index + len(best_marker)

        for markers in marker_groups:
            earliest_index: Optional[int] = None
            earliest_marker = ""
            for marker in markers:
                marker_index = content.find(marker, search_target, search_end)
                if marker_index >= 0 and (earliest_index is None or marker_index < earliest_index):
                    earliest_index = marker_index
                    earliest_marker = marker
            if earliest_index is not None:
                return earliest_index + len(earliest_marker)

        return search_target

    @classmethod
    def _split_document_into_chunks(
        cls,
        content: str,
        target_tokens: int = DOCUMENT_CHUNK_TARGET_TOKENS,
        min_tokens: int = DOCUMENT_CHUNK_MIN_TOKENS,
        max_tokens: int = DOCUMENT_CHUNK_MAX_TOKENS,
    ) -> List[str]:
        normalized = str(content or "")
        if not normalized:
            return []

        target_budget = max(int(target_tokens or DOCUMENT_CHUNK_TARGET_TOKENS), 1)
        min_budget = max(int(min_tokens or DOCUMENT_CHUNK_MIN_TOKENS), 1)
        max_budget = max(int(max_tokens or DOCUMENT_CHUNK_MAX_TOKENS), min_budget)
        target_budget = min(max(target_budget, min_budget), max_budget)

        chunks: List[str] = []
        start = 0
        text_length = len(normalized)
        while start < text_length:
            while start < text_length and normalized[start].isspace():
                start += 1
            if start >= text_length:
                break

            remaining_text = normalized[start:]
            remaining_tokens = cls._count_document_tokens(remaining_text)
            if remaining_tokens <= max_budget:
                final_chunk = normalized[start:].strip()
                if final_chunk:
                    chunks.append(final_chunk)
                break

            min_end = cls._find_document_index_for_token_budget(
                content=normalized,
                start=start,
                target_tokens=min_budget,
            )
            target_end = cls._find_document_index_for_token_budget(
                content=normalized,
                start=start,
                target_tokens=target_budget,
            )
            max_end = cls._find_document_index_for_token_budget(
                content=normalized,
                start=start,
                target_tokens=max_budget,
            )

            boundary = cls._find_document_chunk_boundary(
                content=normalized,
                start=start,
                min_end=min_end,
                target_end=target_end,
                max_end=max_end,
            )
            if boundary <= start:
                boundary = max(target_end, start + 1)

            chunk = normalized[start:boundary].strip()
            if chunk:
                if cls._count_document_tokens(chunk) < min_budget and boundary < text_length:
                    fallback_boundary = max(max_end, target_end)
                    fallback_chunk = normalized[start:fallback_boundary].strip()
                    if fallback_chunk:
                        chunk = fallback_chunk
                        boundary = fallback_boundary
                chunks.append(chunk)
            start = max(boundary, start + 1)
        return chunks

    def _set_document_reader_state(
        self,
        app_name: str,
        app_family: str,
        content: str,
        record_path: Path,
    ) -> None:
        chunks = self._split_document_into_chunks(content)
        self._document_reader_state = {
            "app_name": app_name,
            "app_family": app_family,
            "content": content,
            "record_path": str(record_path),
            "chunks": chunks,
            "current_chunk_index": 0,
            "total_chunks": len(chunks),
        }

    def _build_document_context_from_state(self, source_mode: str) -> Dict[str, Any]:
        state = self._document_reader_state or {}
        chunks = state.get("chunks") or []
        total_chunks = int(state.get("total_chunks") or len(chunks) or 0)
        current_chunk_index = int(state.get("current_chunk_index") or 0)
        content = ""
        if chunks and 0 <= current_chunk_index < len(chunks):
            content = str(chunks[current_chunk_index] or "")
        has_more = bool(total_chunks > 0 and current_chunk_index < (total_chunks - 1))
        return {
            "app_name": str(state.get("app_name") or "").strip(),
            "content": content,
            "chunk_index": current_chunk_index,
            "total_chunks": total_chunks,
            "source_mode": source_mode,
            "has_more": has_more,
        }

    @staticmethod
    def _is_code_like_document_family(app_family: str) -> bool:
        return DocumentReaderMixin._requires_document_extract_position(app_family)

    @staticmethod
    def _split_document_search_terms(query: str) -> List[str]:
        normalized = DocumentReaderMixin._normalize_document_search_text(query)
        if not normalized:
            return []

        terms: List[str] = []
        seen = set()
        for term in re.split(r"[\s,，、;；]+", normalized):
            cleaned = str(term or "").strip()
            if not cleaned:
                continue
            lowered = cleaned.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            terms.append(cleaned)
        if terms:
            return terms
        return [normalized]

    def _score_document_search_candidate(
        self,
        text: str,
        query: str,
        query_terms: List[str],
    ) -> Tuple[int, List[str]]:
        normalized_text = self._normalize_document_search_text(text)
        normalized_query = self._normalize_document_search_text(query)
        if not normalized_text or not normalized_query:
            return 0, []

        lowered_text = normalized_text.casefold()
        lowered_query = normalized_query.casefold()
        exact_hits = lowered_text.count(lowered_query)
        matched_terms = [term for term in query_terms if term.casefold() in lowered_text]
        if exact_hits <= 0 and not matched_terms:
            return 0, []

        score = exact_hits * 100 + len(matched_terms) * 10
        if lowered_text.startswith(lowered_query):
            score += 5
        return score, matched_terms

    @staticmethod
    def _build_text_document_search_units(content: str) -> List[Dict[str, Any]]:
        normalized = str(content or "")
        if not normalized.strip():
            return []

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", normalized) if part.strip()]
        if len(paragraphs) >= 2:
            return DocumentReaderMixin._build_document_search_units_with_offsets(normalized, paragraphs)

        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        if len(lines) >= 2:
            return DocumentReaderMixin._build_document_search_units_with_offsets(normalized, lines)

        sentences = [
            part.strip()
            for part in re.split(r"(?<=[。！？!?；;])\s+|\n+", normalized)
            if part.strip()
        ]
        if len(sentences) >= 2:
            return DocumentReaderMixin._build_document_search_units_with_offsets(normalized, sentences)

        return DocumentReaderMixin._build_document_search_units_with_offsets(normalized, [normalized.strip()])

    @staticmethod
    def _build_document_search_units_with_offsets(content: str, snippets: List[str]) -> List[Dict[str, Any]]:
        units: List[Dict[str, Any]] = []
        normalized = str(content or "")
        cursor = 0
        for order, snippet in enumerate(snippets):
            cleaned = str(snippet or "").strip()
            if not cleaned:
                continue
            start = normalized.find(cleaned, cursor)
            if start < 0:
                start = normalized.find(cleaned)
            end = start + len(cleaned) if start >= 0 else -1
            if end > cursor:
                cursor = end
            units.append(
                {
                    "snippet": cleaned,
                    "order": order,
                    "start": start,
                    "end": end,
                }
            )
        return units

    def _search_text_document_content(
        self,
        content: str,
        query: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        query_terms = self._split_document_search_terms(query)
        units = self._build_text_document_search_units(content)
        results: List[Dict[str, Any]] = []
        seen_snippets = set()
        for unit in units:
            snippet = str(unit.get("snippet") or "").strip()
            score, matched_terms = self._score_document_search_candidate(snippet, query, query_terms)
            normalized_snippet = self._normalize_document_search_text(snippet)
            if score <= 0 or not normalized_snippet:
                continue
            if normalized_snippet in seen_snippets:
                continue
            seen_snippets.add(normalized_snippet)
            results.append(
                {
                    "snippet": snippet,
                    "matched_terms": matched_terms,
                    "score": score,
                    "order": int(unit.get("order") or 0),
                    "start": int(unit.get("start") or -1),
                    "end": int(unit.get("end") or -1),
                }
            )

        results.sort(key=lambda item: (-int(item.get("score") or 0), int(item.get("order") or 0)))
        return results[:max(int(top_k or DOCUMENT_SEARCH_DEFAULT_TOP_K), 1)]

    def _search_code_document_content(
        self,
        content: str,
        query: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        lines = str(content or "").splitlines()
        if not lines:
            return []

        query_terms = self._split_document_search_terms(query)
        line_offsets: List[int] = []
        current_offset = 0
        for line in lines:
            line_offsets.append(current_offset)
            current_offset += len(line) + 1
        results: List[Dict[str, Any]] = []
        seen_ranges = set()
        seen_snippets = set()
        for line_index, line in enumerate(lines):
            line_score, _ = self._score_document_search_candidate(line, query, query_terms)
            if line_score <= 0:
                continue
            start_line = max(0, line_index - DOCUMENT_SEARCH_CODE_CONTEXT_LINES)
            end_line = min(len(lines), line_index + DOCUMENT_SEARCH_CODE_CONTEXT_LINES + 1)
            range_key = (start_line, end_line)
            if range_key in seen_ranges:
                continue
            seen_ranges.add(range_key)
            snippet = "\n".join(lines[start_line:end_line]).strip()
            snippet_score, matched_terms = self._score_document_search_candidate(snippet, query, query_terms)
            normalized_snippet = self._normalize_document_search_text(snippet)
            if snippet_score <= 0 or not normalized_snippet:
                continue
            if normalized_snippet in seen_snippets:
                continue
            seen_snippets.add(normalized_snippet)
            results.append(
                {
                    "snippet": snippet,
                    "matched_terms": matched_terms,
                    "score": snippet_score,
                    "order": start_line,
                    "start": line_offsets[start_line] if start_line < len(line_offsets) else -1,
                    "end": (
                        line_offsets[end_line - 1] + len(lines[end_line - 1])
                        if end_line - 1 < len(lines)
                        else -1
                    ),
                }
            )

        results.sort(key=lambda item: (-int(item.get("score") or 0), int(item.get("order") or 0)))
        return results[:max(int(top_k or DOCUMENT_SEARCH_DEFAULT_TOP_K), 1)]

    def _search_document_content(
        self,
        content: str,
        chunks: List[str],
        app_family: str,
        query: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        if self._is_code_like_document_family(app_family):
            results = self._search_code_document_content(content=content, query=query, top_k=top_k)
        else:
            results = self._search_text_document_content(content=content, query=query, top_k=top_k)
        return self._attach_document_search_chunk_indices(content=content, chunks=chunks, results=results)

    @staticmethod
    def _build_document_chunk_ranges(content: str, chunks: List[str]) -> List[Tuple[int, int, int]]:
        normalized = str(content or "")
        ranges: List[Tuple[int, int, int]] = []
        cursor = 0
        for chunk_index, chunk in enumerate(chunks):
            chunk_text = str(chunk or "").strip()
            if not chunk_text:
                continue
            start = normalized.find(chunk_text, cursor)
            if start < 0:
                start = normalized.find(chunk_text)
            if start < 0:
                continue
            end = start + len(chunk_text)
            ranges.append((chunk_index, start, end))
            cursor = end
        return ranges

    @classmethod
    def _locate_document_chunk_index(
        cls,
        result: Dict[str, Any],
        chunk_ranges: List[Tuple[int, int, int]],
    ) -> Optional[int]:
        raw_start = result.get("start")
        raw_end = result.get("end")
        start = int(raw_start) if raw_start is not None else -1
        end = int(raw_end) if raw_end is not None else -1
        if start < 0 or end < 0:
            return None
        for chunk_index, chunk_start, chunk_end in chunk_ranges:
            if start < chunk_end and end > chunk_start:
                return chunk_index
        return None

    @classmethod
    def _attach_document_search_chunk_indices(
        cls,
        content: str,
        chunks: List[str],
        results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        chunk_ranges = cls._build_document_chunk_ranges(content=content, chunks=chunks)
        total_chunks = len([chunk for chunk in chunks if str(chunk or "").strip()])
        attached_results: List[Dict[str, Any]] = []
        for result in results:
            enriched = dict(result)
            chunk_index = cls._locate_document_chunk_index(enriched, chunk_ranges)
            if chunk_index is not None:
                enriched["chunk_index"] = chunk_index
            enriched["total_chunks"] = total_chunks
            attached_results.append(enriched)
        return attached_results

    @staticmethod
    def _format_document_search_results(results: List[Dict[str, Any]]) -> str:
        blocks: List[str] = []
        for index, result in enumerate(results, start=1):
            lines = [f"[命中 {index}]"]
            matched_terms = [str(term).strip() for term in result.get("matched_terms") or [] if str(term).strip()]
            snippet = str(result.get("snippet") or "").strip()
            chunk_index = result.get("chunk_index")
            total_chunks = int(result.get("total_chunks") or 0)
            if isinstance(chunk_index, int) and chunk_index >= 0 and total_chunks > 0:
                lines[0] += f" 第 {chunk_index + 1}/{total_chunks} 块"
            if matched_terms:
                lines.append(f"匹配词: {'、'.join(matched_terms)}")
            if snippet:
                lines.append(snippet)
            blocks.append("\n".join(lines))
        return "\n\n".join(block for block in blocks if block)

    def _build_document_search_context(
        self,
        query: str,
        results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        state = self._document_reader_state or {}
        return {
            "app_name": str(state.get("app_name") or "").strip(),
            "content": self._format_document_search_results(results),
            "chunk_index": 0,
            "total_chunks": 0,
            "source_mode": "search",
            "has_more": False,
            "query": query,
            "result_count": len(results),
        }

    @staticmethod
    def _normalize_document_search_text(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    @staticmethod
    def _normalize_document_anchor_text(text: str) -> str:
        normalized = DocumentReaderMixin._normalize_document_search_text(text)
        normalized = normalized.lstrip(DOCUMENT_ANCHOR_LEADING_SKIP_CHARS)
        return normalized.strip()

    @staticmethod
    def _is_document_anchor_candidate_char(char: str, allow_weak_punctuation: bool = False) -> bool:
        if not char:
            return False
        if char == " ":
            return True
        if char in "\n\r\t":
            return False
        if re.fullmatch(r"[A-Za-z0-9\u4e00-\u9fff]", char):
            return True
        if allow_weak_punctuation and char in DOCUMENT_ANCHOR_WEAK_PUNCTUATION_CHARS:
            return True
        return False

    def _find_document_anchor_candidate(
        self,
        chunk_content: str,
        allow_weak_punctuation: bool = False,
    ) -> str:
        raw_chunk = str(chunk_content or "")[:DOCUMENT_VIEW_FOLLOW_SCAN_WINDOW]
        candidate_length = DOCUMENT_VIEW_FOLLOW_ANCHOR_LENGTH
        if len(raw_chunk) < candidate_length:
            return ""

        for start_index in range(0, len(raw_chunk) - candidate_length + 1):
            candidate = raw_chunk[start_index:start_index + candidate_length]
            if candidate[0].isspace() or candidate[-1].isspace():
                continue
            if all(
                self._is_document_anchor_candidate_char(char, allow_weak_punctuation=allow_weak_punctuation)
                for char in candidate
            ):
                normalized_candidate = self._normalize_document_anchor_text(candidate)
                if normalized_candidate:
                    return normalized_candidate
        return ""

    def _build_document_view_anchor(
        self,
        full_content: str,
        chunk_content: str,
        source_description: str = "当前块",
        context_description: str = "当前块文本上下文",
    ) -> Tuple[str, str]:
        normalized_full = self._normalize_document_search_text(full_content)
        raw_chunk = str(chunk_content or "")
        if not normalized_full or not raw_chunk.strip():
            return "", f"{source_description}缺少可用于查找的有效文本，本次未执行文档视觉跳转，仅更新了{context_description}。"

        anchor_text = self._find_document_anchor_candidate(raw_chunk, allow_weak_punctuation=False)
        if not anchor_text:
            anchor_text = self._find_document_anchor_candidate(raw_chunk, allow_weak_punctuation=True)
        if not anchor_text:
            anchor_text = self._normalize_document_anchor_text(raw_chunk[:DOCUMENT_VIEW_FOLLOW_ANCHOR_LENGTH])

        if anchor_text and normalized_full.count(anchor_text) == 1:
            return anchor_text, ""

        if not anchor_text:
            return "", f"{source_description}缺少可用于查找的有效文本，本次未执行文档视觉跳转，仅更新了{context_description}。"
        return "", f"{source_description}可用锚点在全文中不唯一，本次未执行文档视觉跳转，仅更新了{context_description}。"

    def _follow_document_view_to_anchor(
        self,
        anchor_text: str,
        expected_app_family: str,
        target_description: str = "当前块附近",
        context_description: str = "当前块文本上下文",
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Tuple[bool, bool, str]:
        self._raise_if_stopped(should_stop)
        frontmost = self.get_frontmost_app_info()
        current_app_name = self._get_frontmost_app_label(frontmost)
        current_app_family = self._get_document_app_family(frontmost)

        if not self._supports_document_view_follow_for_platform(expected_app_family, self._current_os):
            return False, False, self._build_document_view_follow_disabled_message(
                context_description,
                self._current_os,
            )
        if current_app_family != expected_app_family:
            return (
                False,
                False,
                f"当前前台应用已不是提取文档时的同类应用（当前：{current_app_name}），本次未执行文档视觉跳转，仅更新了{context_description}。",
            )

        modifier = self._get_hotkey_modifier()
        has_backup, original_clipboard = self._backup_clipboard_text()
        try:
            self._write_document_anchor_record(anchor_text)
            self._hide_windows()
            try:
                self._release_stuck_modifiers()
                self._call_with_optional_should_stop(
                    self._press_escape_repeated,
                    2,
                    should_stop=should_stop,
                )
                self._call_with_optional_should_stop(
                    self._press_hotkey_with_modifier,
                    modifier,
                    "f",
                    should_stop=should_stop,
                )
                if not self._sleep_interruptibly(0.12, should_stop=should_stop):
                    raise ToolInterrupted(self._INTERRUPTED_ERROR)
                self._call_with_optional_should_stop(
                    self._press_hotkey_with_modifier,
                    modifier,
                    "a",
                    should_stop=should_stop,
                )
                if not self._sleep_interruptibly(0.05, should_stop=should_stop):
                    raise ToolInterrupted(self._INTERRUPTED_ERROR)
                self._raise_if_stopped(should_stop)
                automation_exports().pyperclip.copy(anchor_text)
                if not self._sleep_interruptibly(0.05, should_stop=should_stop):
                    raise ToolInterrupted(self._INTERRUPTED_ERROR)
                self._call_with_optional_should_stop(
                    self._press_hotkey_with_modifier,
                    modifier,
                    "v",
                    should_stop=should_stop,
                )
                if not self._sleep_interruptibly(0.08, should_stop=should_stop):
                    raise ToolInterrupted(self._INTERRUPTED_ERROR)
                self._raise_if_stopped(should_stop)
                automation_exports().pyautogui.press("enter")
                if not self._sleep_interruptibly(0.12, should_stop=should_stop):
                    raise ToolInterrupted(self._INTERRUPTED_ERROR)
                self._call_with_optional_should_stop(
                    self._press_escape_repeated,
                    2,
                    should_stop=should_stop,
                )
            finally:
                self._show_windows()
        except ToolInterrupted:
            raise
        except Exception as exc:
            return True, False, f"本次未能完成文档视觉跳转，仅更新了{context_description}。原因: {exc}"
        finally:
            self._restore_clipboard_text(has_backup, original_clipboard)

        return True, True, f"已尝试将文档视图跳到{target_description}。"

    def _resolve_document_view_follow_result_from_source(
        self,
        *,
        full_content: str,
        anchor_source_text: str,
        expected_app_family: str,
        follow_view: bool,
        source_description: str,
        target_description: str,
        context_description: str,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Tuple[bool, bool, str]:
        self._raise_if_stopped(should_stop)
        if not follow_view:
            return False, False, f"已关闭文档视觉跳转，仅更新了{context_description}。"
        if not self._supports_document_view_follow_for_platform(expected_app_family, self._current_os):
            return False, False, self._build_document_view_follow_disabled_message(
                context_description,
                self._current_os,
            )

        anchor_text, anchor_error = self._build_document_view_anchor(
            full_content=full_content,
            chunk_content=anchor_source_text,
            source_description=source_description,
            context_description=context_description,
        )
        self._raise_if_stopped(should_stop)
        if not anchor_text:
            return False, False, anchor_error

        return self._follow_document_view_to_anchor(
            anchor_text=anchor_text,
            expected_app_family=expected_app_family,
            target_description=target_description,
            context_description=context_description,
            should_stop=should_stop,
        )

    def _resolve_document_view_follow_result(
        self,
        context: Dict[str, Any],
        follow_view: bool,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Tuple[bool, bool, str]:
        state = self._document_reader_state or {}
        expected_app_family = str(state.get("app_family") or "").strip().lower()
        return self._resolve_document_view_follow_result_from_source(
            full_content=str(state.get("content") or ""),
            anchor_source_text=str(context.get("content") or ""),
            expected_app_family=expected_app_family,
            follow_view=follow_view,
            source_description="当前块",
            target_description="当前块附近",
            context_description="当前块文本上下文",
            should_stop=should_stop,
        )

    def _resolve_document_search_view_follow_result(
        self,
        query: str,
        follow_view: bool,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Tuple[bool, bool, str]:
        self._raise_if_stopped(should_stop)
        state = self._document_reader_state or {}
        expected_app_family = str(state.get("app_family") or "").strip().lower()
        normalized_query = self._normalize_document_search_text(query or "")
        if not follow_view:
            return False, False, "已关闭文档视觉跳转，仅更新了搜索结果文本上下文。"
        if not self._supports_document_view_follow_for_platform(expected_app_family, self._current_os):
            return False, False, self._build_document_view_follow_disabled_message(
                "搜索结果文本上下文",
                self._current_os,
            )
        if not normalized_query:
            return False, False, "当前搜索词为空，本次未执行文档视觉跳转，仅更新了搜索结果文本上下文。"

        return self._follow_document_view_to_anchor(
            anchor_text=normalized_query,
            expected_app_family=expected_app_family,
            target_description="搜索词匹配位置附近",
            context_description="搜索结果文本上下文",
            should_stop=should_stop,
        )

    def _build_document_chunk_success_result(
        self,
        source_mode: str,
        follow_view: bool = False,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        self._raise_if_stopped(should_stop)
        context = self._build_document_context_from_state(source_mode=source_mode)
        total_chunks = int(context.get("total_chunks") or 0)
        chunk_index = int(context.get("chunk_index") or 0)
        app_name = str(context.get("app_name") or "未知应用").strip()
        view_follow_attempted = False
        view_followed = False
        view_follow_message = ""

        if source_mode == "extract":
            summary = (
                f"已读取当前文档（可能不完整）：{app_name}。"
                "内容已写入文档解析记录并进入临时文档上下文。"
            )
        else:
            summary = f"已读取当前文档第 {chunk_index + 1}/{max(total_chunks, 1)} 块：{app_name}。当前块已进入临时文档上下文。"
            view_follow_attempted, view_followed, view_follow_message = self._resolve_document_view_follow_result(
                context=context,
                follow_view=follow_view,
                should_stop=should_stop,
            )

        if total_chunks > 0:
            summary += f" 当前块：第 {chunk_index + 1}/{total_chunks} 块。"
        if source_mode != "extract" and view_follow_message:
            summary += f" {view_follow_message}"

        result = self._build_tool_result(True, summary, None)
        result["document_context"] = context
        record_path = str((self._document_reader_state or {}).get("record_path") or "").strip()
        if record_path:
            result["document_record_path"] = record_path
        if source_mode != "extract":
            result["view_follow_attempted"] = view_follow_attempted
            result["view_followed"] = view_followed
            result["view_follow_message"] = view_follow_message
        return result

    def _search_current_document(
        self,
        query: Optional[str],
        top_k: int = DOCUMENT_SEARCH_DEFAULT_TOP_K,
        follow_view: bool = False,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        self._raise_if_stopped(should_stop)
        state = self._document_reader_state or {}
        app_name = str(state.get("app_name") or "未知应用").strip()
        full_content = str(state.get("content") or "")
        if not full_content.strip():
            return self._build_document_failure_result(
                fallback_type="read_current_document_need_extract_first",
                app_name=app_name,
                error='当前任务还没有成功提取文档全文，请先调用 read_current_document(mode="extract")。',
            )

        normalized_query = self._normalize_document_search_text(query or "")
        if not normalized_query:
            return self._build_document_failure_result(
                fallback_type="read_current_document_search_empty_query",
                app_name=app_name,
                error='read_current_document(mode="search") 必须提供非空 query。',
            )

        normalized_top_k = max(1, min(int(top_k or DOCUMENT_SEARCH_DEFAULT_TOP_K), DOCUMENT_SEARCH_MAX_TOP_K))
        results = self._search_document_content(
            content=full_content,
            chunks=[str(chunk or "") for chunk in state.get("chunks") or []],
            app_family=str(state.get("app_family") or "").strip().lower(),
            query=normalized_query,
            top_k=normalized_top_k,
        )
        self._raise_if_stopped(should_stop)
        if not results:
            return self._build_document_failure_result(
                fallback_type="read_current_document_search_no_results",
                app_name=app_name,
                error=f'未在当前文档中找到与“{normalized_query}”相关的内容。',
            )

        context = self._build_document_search_context(query=normalized_query, results=results)
        preview_text = str(context.get("content") or "")[:160].replace("\n", " ").strip()
        view_follow_attempted, view_followed, view_follow_message = self._resolve_document_search_view_follow_result(
            query=normalized_query,
            follow_view=follow_view,
            should_stop=should_stop,
        )
        summary = (
            f"已在当前文档中搜索“{normalized_query}”：{app_name}。"
            f"找到 {len(results)} 条相关结果，搜索结果已进入临时文档上下文。"
        )
        if preview_text:
            summary += f" 预览：{preview_text}"
        if view_follow_message:
            summary += f" {view_follow_message}"

        result = self._build_tool_result(True, summary, None)
        result["document_context"] = context
        record_path = str(state.get("record_path") or "").strip()
        if record_path:
            result["document_record_path"] = record_path
        result["search_results"] = results
        result["view_follow_attempted"] = view_follow_attempted
        result["view_followed"] = view_followed
        result["view_follow_message"] = view_follow_message
        return result

    def _read_current_document_chunk(
        self,
        chunk_index: Optional[int],
        follow_view: bool = False,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        self._raise_if_stopped(should_stop)
        state = self._document_reader_state or {}
        chunks = state.get("chunks") or []
        if not chunks:
            return self._build_document_failure_result(
                fallback_type="read_current_document_need_extract_first",
                app_name=str(state.get("app_name") or "未知应用").strip(),
                error='当前任务还没有成功提取文档全文，请先调用 read_current_document(mode="extract")。',
            )

        target_index = int(chunk_index if chunk_index is not None else 0)
        if target_index < 0 or target_index >= len(chunks):
            return self._build_document_failure_result(
                fallback_type="read_current_document_no_more_chunks",
                app_name=str(state.get("app_name") or "未知应用").strip(),
                error=f"请求的分块索引超出范围。当前总块数为 {len(chunks)}。",
                requested_chunk_index=target_index,
                total_chunks=len(chunks),
            )

        self._raise_if_stopped(should_stop)
        self._document_reader_state["current_chunk_index"] = target_index
        return self._build_document_chunk_success_result(
            source_mode="chunk",
            follow_view=follow_view,
            should_stop=should_stop,
        )

    def _read_next_document_chunk(
        self,
        follow_view: bool = False,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        self._raise_if_stopped(should_stop)
        state = self._document_reader_state or {}
        chunks = state.get("chunks") or []
        if not chunks:
            return self._build_document_failure_result(
                fallback_type="read_current_document_need_extract_first",
                app_name=str(state.get("app_name") or "未知应用").strip(),
                error='当前任务还没有成功提取文档全文，请先调用 read_current_document(mode="extract")。',
            )

        current_chunk_index = int(state.get("current_chunk_index") or 0)
        next_chunk_index = current_chunk_index + 1
        if next_chunk_index >= len(chunks):
            return self._build_document_failure_result(
                fallback_type="read_current_document_no_more_chunks",
                app_name=str(state.get("app_name") or "未知应用").strip(),
                error="当前已经是最后一块，没有更多分块。",
                requested_chunk_index=next_chunk_index,
                total_chunks=len(chunks),
            )

        self._raise_if_stopped(should_stop)
        self._document_reader_state["current_chunk_index"] = next_chunk_index
        return self._build_document_chunk_success_result(
            source_mode="next",
            follow_view=follow_view,
            should_stop=should_stop,
        )

    def _next_document_extract_path(self) -> Path:
        """生成当前任务内下一份文档解析记录路径。"""
        self._document_extract_sequence += 1
        extract_dir = Path(automation_exports().DOCUMENT_EXTRACT_DIR)
        extract_dir.mkdir(parents=True, exist_ok=True)
        timestamp = automation_exports().time.strftime("%Y%m%d_%H%M%S", automation_exports().time.localtime())
        filename = f"document_{timestamp}_{self._document_extract_sequence:03d}.txt"
        return extract_dir / filename

    def _write_document_content_record(
        self,
        app_name: str,
        content: str,
    ) -> Path:
        record_path = self._next_document_extract_path()
        timestamp = automation_exports().time.strftime("%Y-%m-%d %H:%M:%S", automation_exports().time.localtime())
        lines = [
            f"[文档速读 {timestamp}]",
            f"应用: {app_name or '未知应用'}",
            "说明: read_current_document 为快速提取工具，结果可能不完整。",
            "正文:",
            content or "(空)",
            "",
        ]
        with open(record_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))
        return record_path

    def _next_document_anchor_path(self) -> Path:
        """生成当前任务内下一份文档跳转锚点记录路径。"""
        self._document_anchor_sequence += 1
        anchor_dir = Path(automation_exports().DOCUMENT_ANCHOR_DIR)
        anchor_dir.mkdir(parents=True, exist_ok=True)
        timestamp = automation_exports().time.strftime("%Y%m%d_%H%M%S", automation_exports().time.localtime())
        filename = f"anchor_{timestamp}_{self._document_anchor_sequence:03d}.txt"
        return anchor_dir / filename

    def _write_document_anchor_record(self, anchor_text: str) -> Path:
        record_path = self._next_document_anchor_path()
        timestamp = automation_exports().time.strftime("%Y-%m-%d %H:%M:%S", automation_exports().time.localtime())
        lines = [
            f"[文档跳转锚点 {timestamp}]",
            "跳转锚点内容 (最多20个字符):",
            anchor_text or "(空)",
            "",
        ]
        with open(record_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))
        return record_path
