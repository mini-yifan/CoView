"""Browser page reader automation tools."""

from __future__ import annotations

import re
import ssl
import time
import urllib.error
import urllib.request
from html import unescape
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pyautogui
import pyperclip

from .constants import (
    DOCUMENT_SEARCH_DEFAULT_TOP_K,
    DOCUMENT_SEARCH_MAX_TOP_K,
    automation_exports,
)
from .runtime import ToolInterrupted


class PageReaderMixin:
    def tool_read_current_page(
        self,
        mode: str = "extract",
        chunk_index: Optional[int] = None,
        query: Optional[str] = None,
        top_k: int = DOCUMENT_SEARCH_DEFAULT_TOP_K,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        try:
            self._raise_if_stopped(should_stop)
            normalized_mode = str(mode or "extract").strip().lower()
            if normalized_mode == "chunk":
                return self._read_current_page_chunk(chunk_index, should_stop=should_stop)
            if normalized_mode == "next":
                return self._read_next_page_chunk(should_stop=should_stop)
            if normalized_mode == "search":
                return self._search_current_page(query=query, top_k=top_k, should_stop=should_stop)

            frontmost = self.get_frontmost_app_info()
            self._raise_if_stopped(should_stop)
            if not self._is_browser_frontmost_app(frontmost):
                app_name = str(frontmost.get("app_name") or frontmost.get("identifier") or "未知应用").strip()
                fallback = {
                    "type": "read_current_page_not_browser",
                    "app_name": app_name,
                }
                return self._build_tool_result(
                    False,
                    "读取当前网页失败",
                    f"read_current_page 仅支持在浏览器前台页面使用，当前前台应用为：{app_name}。",
                    fallback=fallback,
                )

            self._hide_windows()
            try:
                url = self._call_with_optional_should_stop(
                    self._extract_current_browser_url,
                    max_retries=3,
                    should_stop=should_stop,
                )
            finally:
                self._show_windows()

            self._raise_if_stopped(should_stop)
            page = self._call_with_optional_should_stop(
                self._fetch_webpage_text,
                url,
                should_stop=should_stop,
            )
            self._raise_if_stopped(should_stop)
            full_text = str(page.get("text", "") or "").strip()
            title = str(page.get("title") or "").strip()
            record_path = self._write_page_content_record(
                url=url,
                title=title,
                content=full_text,
            )

            if not full_text:
                self._page_reader_state = {}
                page_context = {
                    "url": url,
                    "title": title,
                    "quality": "partial",
                    "content": "",
                    "chunk_index": 0,
                    "total_chunks": 0,
                    "source_mode": "extract",
                    "has_more": False,
                }
                result = self._build_tool_result(
                    True,
                    "已获取当前网页链接，网页解析记录已保存，但正文提取不完整",
                    "网页结构较复杂或内容依赖脚本动态渲染，未提取到足够正文内容。",
                    fallback={"type": "read_current_page_partial", "url": url},
                )
                result["quality"] = "partial"
                result["url"] = url
                result["page_context"] = page_context
                result["page_record_path"] = str(record_path)
                return result

            self._set_page_reader_state(
                url=url,
                title=title,
                content=full_text,
                record_path=record_path,
            )
            result = self._build_page_chunk_success_result(source_mode="extract")
            result["quality"] = "best_effort"
            result["url"] = url
            return result
        except ToolInterrupted:
            return self._build_tool_result(False, self._INTERRUPTED_SUMMARY, self._INTERRUPTED_ERROR)
        except Exception as exc:
            return self._build_tool_result(False, "读取当前网页失败", str(exc))

    @staticmethod
    def _is_browser_frontmost_app(app_info: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(app_info, dict):
            return False

        combined = " ".join(
            str(app_info.get(key) or "").strip().lower()
            for key in ("app_name", "bundle_id", "identifier")
        )
        if not combined:
            return False

        markers = (
            "chrome",
            "chromium",
            "safari",
            "firefox",
            "edge",
            "brave",
            "vivaldi",
            "opera",
            "arc",
            "browser",
            "duckduckgo",
        )
        return any(marker in combined for marker in markers)


    def _get_hotkey_modifier(self) -> str:
        hotkey_modifier = str(self._platform_adapter.get_hotkey_modifier() or "command").strip().lower()
        if hotkey_modifier not in {"command", "ctrl"}:
            hotkey_modifier = "command" if self._current_os == "Darwin" else "ctrl"
        return hotkey_modifier

    def _extract_current_browser_url(
        self,
        max_retries: int = 3,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> str:
        hotkey_modifier = self._get_hotkey_modifier()

        has_backup, original_clipboard = self._backup_clipboard_text()
        try:
            for attempt in range(max(max_retries, 1)):
                self._raise_if_stopped(should_stop)
                before_copy = str(automation_exports().pyperclip.paste() or "").strip()

                self._release_stuck_modifiers()
                self._press_hotkey_with_modifier(hotkey_modifier, "l", should_stop=should_stop)
                if not self._sleep_interruptibly(0.15 + attempt * 0.08, should_stop=should_stop):
                    raise ToolInterrupted(self._INTERRUPTED_ERROR)
                self._press_hotkey_with_modifier(hotkey_modifier, "c", should_stop=should_stop)

                url = self._wait_for_url_in_clipboard(
                    previous_content=before_copy,
                    timeout_seconds=0.7,
                    should_stop=should_stop,
                )
                self._restore_browser_focus_after_copy()
                if url:
                    return url

                print(f"第 {attempt + 1} 次提取当前网页 URL 失败，准备重试。")

            raise RuntimeError("未能从当前浏览器页面提取到有效 URL。")
        finally:
            self._restore_clipboard_text(has_backup, original_clipboard)

    def _release_stuck_modifiers(self) -> None:
        for key in ("command", "ctrl", "control", "option", "alt", "win"):
            try:
                automation_exports().pyautogui.keyUp(key)
            except Exception:
                pass

    def _press_escape_repeated(
        self,
        count: int = 2,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> None:
        for _ in range(max(count, 0)):
            self._raise_if_stopped(should_stop)
            automation_exports().pyautogui.press("esc")
            if not self._sleep_interruptibly(0.04, should_stop=should_stop):
                raise ToolInterrupted(self._INTERRUPTED_ERROR)

    def _press_hotkey_with_modifier(
        self,
        modifier: str,
        key: str,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> None:
        translated = self._platform_adapter.translate_hotkey_keys([modifier, key])
        if len(translated) < 2:
            return
        modifier_key = translated[0]
        target_key = translated[1]
        self._raise_if_stopped(should_stop)
        automation_exports().pyautogui.keyDown(modifier_key)
        try:
            if not self._sleep_interruptibly(0.03, should_stop=should_stop):
                raise ToolInterrupted(self._INTERRUPTED_ERROR)
            automation_exports().pyautogui.press(target_key)
            if not self._sleep_interruptibly(0.03, should_stop=should_stop):
                raise ToolInterrupted(self._INTERRUPTED_ERROR)
        finally:
            automation_exports().pyautogui.keyUp(modifier_key)

    def _wait_for_url_in_clipboard(
        self,
        previous_content: str,
        timeout_seconds: float = 0.7,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> str:
        deadline = automation_exports().time.monotonic() + max(timeout_seconds, 0.1)
        previous = str(previous_content or "").strip()
        while automation_exports().time.monotonic() < deadline:
            self._raise_if_stopped(should_stop)
            current = str(automation_exports().pyperclip.paste() or "").strip()
            if current and re.match(r"^https?://", current):
                if current != previous:
                    return current
                # 内容没有变化时再多等一轮，兼容“原剪贴板本来就是 URL”的情况。
                if (deadline - automation_exports().time.monotonic()) < 0.2:
                    return current
            if not self._sleep_interruptibly(0.05, should_stop=should_stop):
                raise ToolInterrupted(self._INTERRUPTED_ERROR)
        return ""

    def _wait_for_changed_clipboard_text(
        self,
        previous_content: str,
        timeout_seconds: float = 0.9,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> str:
        deadline = automation_exports().time.monotonic() + max(timeout_seconds, 0.1)
        previous = str(previous_content or "").strip()
        while automation_exports().time.monotonic() < deadline:
            self._raise_if_stopped(should_stop)
            current = str(automation_exports().pyperclip.paste() or "").strip()
            if current and current != previous:
                return current
            if not self._sleep_interruptibly(0.05, should_stop=should_stop):
                raise ToolInterrupted(self._INTERRUPTED_ERROR)
        return ""

    def _restore_browser_focus_after_copy(self) -> None:
        automation_exports().time.sleep(0.06)
        self._release_stuck_modifiers()
        self._press_escape_repeated(3)


    def _set_page_reader_state(
        self,
        url: str,
        title: str,
        content: str,
        record_path: Path,
    ) -> None:
        chunks = self._split_document_into_chunks(content)
        self._page_reader_state = {
            "url": url,
            "title": title,
            "content": content,
            "record_path": str(record_path),
            "chunks": chunks,
            "current_chunk_index": 0,
            "total_chunks": len(chunks),
        }

    def _build_page_context_from_state(self, source_mode: str) -> Dict[str, Any]:
        state = self._page_reader_state or {}
        chunks = state.get("chunks") or []
        total_chunks = int(state.get("total_chunks") or len(chunks) or 0)
        current_chunk_index = int(state.get("current_chunk_index") or 0)
        content = ""
        if chunks and 0 <= current_chunk_index < len(chunks):
            content = str(chunks[current_chunk_index] or "")
        has_more = bool(total_chunks > 0 and current_chunk_index < (total_chunks - 1))
        return {
            "url": str(state.get("url") or "").strip(),
            "title": str(state.get("title") or "").strip(),
            "content": content,
            "chunk_index": current_chunk_index,
            "total_chunks": total_chunks,
            "source_mode": source_mode,
            "has_more": has_more,
        }

    def _build_page_chunk_success_result(self, source_mode: str) -> Dict[str, Any]:
        context = self._build_page_context_from_state(source_mode=source_mode)
        total_chunks = int(context.get("total_chunks") or 0)
        chunk_index = int(context.get("chunk_index") or 0)
        url = str(context.get("url") or "").strip()
        title = str(context.get("title") or "").strip()

        if source_mode == "extract":
            summary = (
                f"已读取当前网页（可能不完整）：{title or '无标题'}。"
                f"链接：{url}。内容已写入网页解析记录并进入临时网页上下文。"
            )
        else:
            summary = f"已读取当前网页第 {chunk_index + 1}/{max(total_chunks, 1)} 块：{title or '无标题'}。链接：{url}。当前块已进入临时网页上下文。"

        if total_chunks > 0:
            summary += f" 当前块：第 {chunk_index + 1}/{total_chunks} 块。"

        result = self._build_tool_result(True, summary, None)
        result["page_context"] = context
        record_path = str((self._page_reader_state or {}).get("record_path") or "").strip()
        if record_path:
            result["page_record_path"] = record_path
        return result

    def _build_page_failure_result(
        self,
        fallback_type: str,
        error: str,
        **extra_fields: Any,
    ) -> Dict[str, Any]:
        self._page_reader_state = {}
        fallback = {"type": fallback_type}
        result = self._build_tool_result(False, "读取当前网页失败", error, fallback=fallback)
        result.update(extra_fields)
        return result

    def _read_current_page_chunk(
        self,
        chunk_index: Optional[int],
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        self._raise_if_stopped(should_stop)
        state = self._page_reader_state or {}
        chunks = state.get("chunks") or []
        url = str(state.get("url") or "").strip()
        if not chunks:
            return self._build_page_failure_result(
                fallback_type="read_current_page_need_extract_first",
                error='当前任务还没有成功提取网页全文，请先调用 read_current_page(mode="extract")。',
            )

        target_index = int(chunk_index if chunk_index is not None else 0)
        if target_index < 0 or target_index >= len(chunks):
            return self._build_page_failure_result(
                fallback_type="read_current_page_no_more_chunks",
                error=f"请求的分块索引超出范围。当前总块数为 {len(chunks)}。",
                requested_chunk_index=target_index,
                total_chunks=len(chunks),
            )

        self._raise_if_stopped(should_stop)
        self._page_reader_state["current_chunk_index"] = target_index
        return self._build_page_chunk_success_result(source_mode="chunk")

    def _read_next_page_chunk(
        self,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        self._raise_if_stopped(should_stop)
        state = self._page_reader_state or {}
        chunks = state.get("chunks") or []
        if not chunks:
            return self._build_page_failure_result(
                fallback_type="read_current_page_need_extract_first",
                error='当前任务还没有成功提取网页全文，请先调用 read_current_page(mode="extract")。',
            )

        current_chunk_index = int(state.get("current_chunk_index") or 0)
        next_chunk_index = current_chunk_index + 1
        if next_chunk_index >= len(chunks):
            return self._build_page_failure_result(
                fallback_type="read_current_page_no_more_chunks",
                error="当前已经是最后一块，没有更多分块。",
                requested_chunk_index=next_chunk_index,
                total_chunks=len(chunks),
            )

        self._raise_if_stopped(should_stop)
        self._page_reader_state["current_chunk_index"] = next_chunk_index
        return self._build_page_chunk_success_result(source_mode="next")

    def _search_current_page(
        self,
        query: Optional[str],
        top_k: int = DOCUMENT_SEARCH_DEFAULT_TOP_K,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        self._raise_if_stopped(should_stop)
        state = self._page_reader_state or {}
        url = str(state.get("url") or "").strip()
        title = str(state.get("title") or "").strip()
        full_content = str(state.get("content") or "")
        if not full_content.strip():
            return self._build_page_failure_result(
                fallback_type="read_current_page_need_extract_first",
                error='当前任务还没有成功提取网页全文，请先调用 read_current_page(mode="extract")。',
            )

        normalized_query = self._normalize_document_search_text(query or "")
        if not normalized_query:
            return self._build_page_failure_result(
                fallback_type="read_current_page_search_empty_query",
                error='read_current_page(mode="search") 必须提供非空 query。',
            )

        normalized_top_k = max(1, min(int(top_k or DOCUMENT_SEARCH_DEFAULT_TOP_K), DOCUMENT_SEARCH_MAX_TOP_K))
        results = self._search_text_document_content(
            content=full_content,
            query=normalized_query,
            top_k=normalized_top_k,
        )
        self._raise_if_stopped(should_stop)
        if not results:
            return self._build_page_failure_result(
                fallback_type="read_current_page_search_no_results",
                error=f'未在当前网页中找到与"{normalized_query}"相关的内容。',
            )

        formatted = self._format_document_search_results(results)
        page_context = {
            "url": url,
            "title": title,
            "content": formatted,
            "chunk_index": 0,
            "total_chunks": 0,
            "source_mode": "search",
            "has_more": False,
            "query": normalized_query,
            "result_count": len(results),
        }
        preview_text = formatted[:160].replace("\n", " ").strip()
        summary = (
            f'已在当前网页中搜索"{normalized_query}"：{title or "无标题"}。'
            f"链接：{url}。找到 {len(results)} 条相关结果，搜索结果已进入临时网页上下文。"
        )
        if preview_text:
            summary += f" 预览：{preview_text}"

        result = self._build_tool_result(True, summary, None)
        result["page_context"] = page_context
        record_path = str(state.get("record_path") or "").strip()
        if record_path:
            result["page_record_path"] = record_path
        result["search_results"] = results
        return result

    def _fetch_webpage_text(
        self,
        url: str,
        timeout_seconds: int = 15,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, str]:
        self._raise_if_stopped(should_stop)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        request = urllib.request.Request(url, headers=headers)
        context = ssl._create_unverified_context()
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context),
        )

        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                html_bytes = response.read()
                content_type = str(response.headers.get("Content-Type", "") or "")
            self._raise_if_stopped(should_stop)
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise RuntimeError(f"下载网页失败: {reason}") from exc
        except Exception as exc:
            raise RuntimeError(f"下载网页失败: {exc}") from exc

        html_text = self._decode_webpage_bytes(html_bytes, content_type)
        self._raise_if_stopped(should_stop)
        result = self._extract_title_and_text_from_html(html_text)
        self._raise_if_stopped(should_stop)
        return result

    @staticmethod
    def _decode_webpage_bytes(html_bytes: bytes, content_type: str) -> str:
        charset_match = re.search(r"charset=([a-zA-Z0-9_-]+)", str(content_type or ""), re.IGNORECASE)
        candidates = []
        if charset_match:
            candidates.append(charset_match.group(1).strip())
        candidates.extend(["utf-8", "gb18030", "big5", "latin-1"])

        for charset in candidates:
            if not charset:
                continue
            try:
                return html_bytes.decode(charset, errors="replace")
            except Exception:
                continue
        return html_bytes.decode("utf-8", errors="replace")

    @staticmethod
    def _extract_title_and_text_from_html(html_text: str) -> Dict[str, str]:
        title = ""
        title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html_text or "")
        if title_match:
            raw_title = re.sub(r"(?is)<[^>]+>", " ", title_match.group(1))
            title = unescape(re.sub(r"\s+", " ", raw_title)).strip()

        body = re.sub(r"(?is)<script[^>]*>.*?</script>", "\n", html_text or "")
        body = re.sub(r"(?is)<style[^>]*>.*?</style>", "\n", body)
        body = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", "\n", body)
        body = re.sub(r"(?is)<svg[^>]*>.*?</svg>", "\n", body)
        body = re.sub(r"(?is)<[^>]+>", "\n", body)
        body = unescape(body)
        body = re.sub(r"[ \t\r\f\v]+", " ", body)
        body = re.sub(r"\s*\n\s*", "\n", body)

        return {
            "title": title,
            "text": body.strip(),
        }

    def _next_page_extract_path(self) -> Path:
        """生成当前任务内下一份网页解析记录路径。"""
        self._page_extract_sequence += 1
        extract_dir = Path(automation_exports().PAGE_EXTRACT_DIR)
        extract_dir.mkdir(parents=True, exist_ok=True)
        timestamp = automation_exports().time.strftime("%Y%m%d_%H%M%S", automation_exports().time.localtime())
        filename = f"page_{timestamp}_{self._page_extract_sequence:03d}.txt"
        return extract_dir / filename

    def _write_page_content_record(
        self,
        url: str,
        title: str,
        content: str,
    ) -> Path:
        record_path = self._next_page_extract_path()
        timestamp = automation_exports().time.strftime("%Y-%m-%d %H:%M:%S", automation_exports().time.localtime())
        lines = [
            f"[网页速读 {timestamp}]",
            f"链接: {url}",
            f"标题: {title or '无标题'}",
            "说明: read_current_page 为快速提取工具，结果可能不完整。",
            "正文:",
            content or "(空)",
            "",
        ]
        with open(record_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))
        return record_path
