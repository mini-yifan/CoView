"""后台 Code Agent 会话文件目录工具。"""

from __future__ import annotations

import shutil
from pathlib import Path


def resolve_session_root(session_root: str | Path | None = None) -> Path:
    """返回后台 Code Agent 会话目录。"""
    root = Path(session_root).expanduser() if session_root is not None else (Path.home() / ".baodou" / "code_agent_sessions")
    return root.resolve()


def clear_session_root(session_root: str | Path | None = None) -> Path:
    """清空后台 Code Agent 会话目录内容，并保留目录本身。"""
    root = resolve_session_root(session_root)
    try:
        if root.exists():
            for child in list(root.iterdir()):
                try:
                    if child.is_dir() and not child.is_symlink():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink(missing_ok=True)
                except Exception:
                    continue
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return root
