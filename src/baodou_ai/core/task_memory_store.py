"""Task-level remember memory file access."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Union

from baodou_ai.runtime_paths import resolve_memory_file

MemoryPathLike = Union[str, Path]


class TaskMemoryStore:
    """统一 task memory.txt 的读写入口。"""

    def __init__(
        self,
        memory_file: Optional[MemoryPathLike] = None,
        memory_file_resolver: Optional[Callable[[], Optional[MemoryPathLike]]] = None,
    ) -> None:
        self._memory_file = memory_file
        self._memory_file_resolver = memory_file_resolver

    def _resolve_path(self) -> Path:
        target = self._memory_file
        if self._memory_file_resolver is not None:
            target = self._memory_file_resolver()
        return resolve_memory_file(target)

    def read(self) -> str:
        """读取 memory 内容（去除首尾空白）。"""
        try:
            memory_file = self._resolve_path()
            if memory_file.exists():
                return memory_file.read_text(encoding="utf-8").strip()
        except Exception as exc:
            print(f"读取记忆文件失败: {exc}")
        return ""

    def append(self, content: str) -> bool:
        """追加 remember 内容。返回是否成功写入。"""
        normalized = str(content or "")
        try:
            memory_file = self._resolve_path()
            memory_file.parent.mkdir(parents=True, exist_ok=True)
            with open(memory_file, "a", encoding="utf-8") as handle:
                handle.write(f"{normalized}\n")
            return True
        except Exception as exc:
            print(f"写入记忆文件失败: {exc}")
            return False

    def clear(self) -> None:
        """清空 memory 内容。"""
        try:
            memory_file = self._resolve_path()
            if memory_file.exists():
                memory_file.write_text("", encoding="utf-8")
        except Exception as exc:
            print(f"清空记忆文件失败: {exc}")
