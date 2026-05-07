"""Runtime artifact directories and context debug log store."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from baodou_ai.runtime_paths import resolve_context_debug_dir

PathLike = Union[str, Path]


def _resolve_runtime_path(path_value: Optional[PathLike]) -> Path:
    target = Path(path_value or ".")
    return target.expanduser().resolve()


class RuntimeArtifactStore:
    """统一运行时产物目录管理入口。"""

    def __init__(
        self,
        page_extract_dir: Optional[PathLike] = None,
        document_extract_dir: Optional[PathLike] = None,
        document_anchor_dir: Optional[PathLike] = None,
        context_debug_dir: Optional[PathLike] = None,
        page_extract_dir_resolver: Optional[Callable[[], Optional[PathLike]]] = None,
        document_extract_dir_resolver: Optional[Callable[[], Optional[PathLike]]] = None,
        document_anchor_dir_resolver: Optional[Callable[[], Optional[PathLike]]] = None,
        context_debug_dir_resolver: Optional[Callable[[], Optional[PathLike]]] = None,
    ) -> None:
        self._page_extract_dir = page_extract_dir
        self._document_extract_dir = document_extract_dir
        self._document_anchor_dir = document_anchor_dir
        self._context_debug_dir = context_debug_dir
        self._page_extract_dir_resolver = page_extract_dir_resolver
        self._document_extract_dir_resolver = document_extract_dir_resolver
        self._document_anchor_dir_resolver = document_anchor_dir_resolver
        self._context_debug_dir_resolver = context_debug_dir_resolver
        self._context_debug_round = 0

    def _resolve_page_extract_dir(self) -> Path:
        target = self._page_extract_dir
        if self._page_extract_dir_resolver is not None:
            target = self._page_extract_dir_resolver()
        return _resolve_runtime_path(target)

    def _resolve_document_extract_dir(self) -> Path:
        target = self._document_extract_dir
        if self._document_extract_dir_resolver is not None:
            target = self._document_extract_dir_resolver()
        return _resolve_runtime_path(target)

    def _resolve_document_anchor_dir(self) -> Path:
        target = self._document_anchor_dir
        if self._document_anchor_dir_resolver is not None:
            target = self._document_anchor_dir_resolver()
        return _resolve_runtime_path(target)

    def _resolve_context_debug_dir(self) -> Path:
        target = self._context_debug_dir
        if self._context_debug_dir_resolver is not None:
            target = self._context_debug_dir_resolver()
        return resolve_context_debug_dir(target)

    @staticmethod
    def _clear_and_prepare_dir(path: Path) -> None:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    def clear_reader_artifacts(self) -> None:
        """清理页面/文档解析缓存目录。"""
        try:
            self._clear_and_prepare_dir(self._resolve_page_extract_dir())
            self._clear_and_prepare_dir(self._resolve_document_extract_dir())
            self._clear_and_prepare_dir(self._resolve_document_anchor_dir())
        except Exception as exc:
            print(f"清空解析缓存失败: {exc}")

    def clear_context_debug(self) -> None:
        """清理 context debug json，并重置轮次计数。"""
        self._context_debug_round = 0
        debug_dir = self._resolve_context_debug_dir()
        if not debug_dir.exists():
            return
        for debug_file in debug_dir.iterdir():
            if debug_file.is_file() and debug_file.suffix == ".json":
                try:
                    debug_file.unlink()
                except OSError:
                    pass

    @staticmethod
    def _serialize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = []
        for msg in messages:
            item: Dict[str, Any] = {"role": str(msg.get("role") or "unknown")}
            content = msg.get("content")
            if isinstance(content, str):
                item["content"] = content
            elif isinstance(content, list):
                parts = []
                for part in content:
                    if not isinstance(part, dict):
                        parts.append(str(part))
                        continue
                    part_type = str(part.get("type") or "unknown")
                    if part_type == "image_url":
                        url = str(part.get("image_url", {}).get("url") or "")
                        if url.startswith("data:"):
                            parts.append({"type": "image_url", "url_length": len(url)})
                        else:
                            parts.append({"type": "image_url", "url": url})
                    else:
                        parts.append(part)
                item["content"] = parts
            else:
                item["content"] = str(content or "")
            serialized.append(item)
        return serialized

    def write_context_debug(self, full_content: str, messages: List[Dict[str, Any]]) -> None:
        """写入单轮 context debug 文件，轮次按实例递增。"""
        debug_dir = self._resolve_context_debug_dir()
        try:
            debug_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return

        self._context_debug_round += 1
        round_num = self._context_debug_round
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        json_path = debug_dir / f"round_{round_num:03d}_{timestamp}.json"

        data = {
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "round": round_num,
            "full_content": full_content or "",
            "messages": self._serialize_messages(messages),
        }
        try:
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
