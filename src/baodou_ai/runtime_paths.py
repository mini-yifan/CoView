"""运行时文件路径定义。"""

from __future__ import annotations

from pathlib import Path


MEMORY_FILE = "memory.txt"
CONTEXT_DEBUG_DIR = Path("imgs") / "context_debug"


def resolve_memory_file(memory_file: str | Path | None = None) -> Path:
    target = memory_file if memory_file is not None else MEMORY_FILE
    return Path(target).expanduser().resolve()


def resolve_context_debug_dir(debug_dir: str | Path | None = None) -> Path:
    target = debug_dir if debug_dir is not None else CONTEXT_DEBUG_DIR
    return Path(target).expanduser().resolve()
