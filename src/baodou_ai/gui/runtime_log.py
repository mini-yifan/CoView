"""
运行时日志缓冲与分发。

将 stdout/stderr 从可见窗口中解耦，便于懒加载控制台回放历史日志。
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, pyqtSignal


LogEntry = Tuple[str, str]


class RuntimeLogBuffer(QObject):
    """内存日志缓冲，支持历史回放与实时订阅。"""

    entry_added = pyqtSignal(str, str)
    cleared = pyqtSignal()

    def __init__(self, max_entries: int = 4000) -> None:
        super().__init__()
        self._entries: List[LogEntry] = []
        self._entry_metadata: List[Dict[str, Any]] = []
        self._max_entries = max(1, int(max_entries))
        self._stdout_stream: Optional[_RuntimeLogStream] = None
        self._stderr_stream: Optional[_RuntimeLogStream] = None
        self._original_stdout = None
        self._original_stderr = None
        self._installed = False

    def install(self) -> None:
        """接管 stdout / stderr。重复调用安全。"""
        if self._installed:
            return

        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self._stdout_stream = _RuntimeLogStream(self, default_log_type="normal", original_stream=self._original_stdout)
        self._stderr_stream = _RuntimeLogStream(self, default_log_type="error", original_stream=self._original_stderr)
        sys.stdout = self._stdout_stream
        sys.stderr = self._stderr_stream
        self._installed = True

    def append_log(self, text: str, log_type: str = "normal", metadata: Optional[Dict[str, Any]] = None) -> None:
        """追加日志到缓冲，并向订阅者广播。"""
        if text is None:
            return
        normalized = str(text)
        if not normalized:
            return

        self._entries.append((normalized, log_type))
        self._entry_metadata.append(dict(metadata or {}))
        if len(self._entries) > self._max_entries:
            overflow = len(self._entries) - self._max_entries
            if overflow > 0:
                self._entries = self._entries[overflow:]
                self._entry_metadata = self._entry_metadata[overflow:]

        self.entry_added.emit(normalized, log_type)

    def history(self) -> List[LogEntry]:
        """返回当前历史日志快照。"""
        return list(self._entries)

    def history_with_metadata(self) -> List[Tuple[str, str, Dict[str, Any]]]:
        """返回带 metadata 的历史日志快照。"""
        combined: List[Tuple[str, str, Dict[str, Any]]] = []
        for index, (text, log_type) in enumerate(self._entries):
            metadata = self._entry_metadata[index] if index < len(self._entry_metadata) else {}
            combined.append((text, log_type, dict(metadata)))
        return combined

    def clear(self) -> None:
        """清空历史日志。"""
        self._entries = []
        self._entry_metadata = []
        self.cleared.emit()

    def save_to_file(self, path: str) -> Path:
        """将当前日志保存到文件。"""
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            for text, _log_type in self._entries:
                handle.write(text)
        return output_path

    def append_error_envelope(self, envelope: Dict[str, Any], prefix: str = "") -> None:
        """追加结构化错误日志，同时保持文本日志兼容。"""
        payload = dict(envelope or {})
        source = str(payload.get("source") or "unknown")
        kind = str(payload.get("kind") or "execution_failed")
        code = str(payload.get("code") or "")
        retryable = bool(payload.get("retryable"))
        user_message = str(payload.get("user_message") or "").strip()
        dev_detail = str(payload.get("dev_detail") or "").strip()
        exception_type = str(payload.get("exception_type") or "").strip()

        parts = [part for part in (prefix.strip(), user_message) if part]
        main_text = "：".join(parts) if len(parts) >= 2 else (parts[0] if parts else "执行失败")
        detail_items = [f"source={source}", f"kind={kind}"]
        if code:
            detail_items.append(f"code={code}")
        detail_items.append(f"retryable={'yes' if retryable else 'no'}")
        if exception_type:
            detail_items.append(f"exception={exception_type}")
        if dev_detail:
            detail_items.append(f"detail={dev_detail}")
        detail = ", ".join(detail_items)
        self.append_log(f"{main_text} [{detail}]\n", "error", metadata=payload)


class _RuntimeLogStream(io.StringIO):
    """将标准输出转换为 RuntimeLogBuffer 事件。"""

    ERROR_KEYWORDS = ("错误", "失败", "Traceback", "Exception", "Error")
    WARNING_KEYWORDS = ("警告", "warning", "Warning")

    def __init__(self, log_buffer: RuntimeLogBuffer, default_log_type: str = "normal", original_stream=None) -> None:
        super().__init__()
        self._log_buffer = log_buffer
        self._default_log_type = default_log_type
        self._buffer = ""
        self._original_stream = original_stream

    def _detect_log_type(self, text: str) -> str:
        if self._default_log_type != "normal":
            return self._default_log_type

        normalized = text.strip()
        if any(keyword in normalized for keyword in self.ERROR_KEYWORDS):
            return "error"
        if any(keyword in normalized for keyword in self.WARNING_KEYWORDS):
            return "warning"
        return "normal"

    def write(self, text: str) -> int:
        if self._original_stream is not None:
            try:
                self._original_stream.write(text)
                self._original_stream.flush()
            except Exception:
                pass
        super().write(text)
        self._buffer += text
        if "\n" not in self._buffer:
            return len(text)

        lines = self._buffer.split("\n")
        self._buffer = lines[-1]
        for line in lines[:-1]:
            if line:
                self._log_buffer.append_log(f"{line}\n", self._detect_log_type(line))
        return len(text)

    def flush(self) -> None:
        if self._original_stream is not None:
            try:
                self._original_stream.flush()
            except Exception:
                pass
        if not self._buffer:
            return
        buffered = self._buffer
        self._buffer = ""
        self._log_buffer.append_log(buffered, self._detect_log_type(buffered))


_runtime_log_buffer: Optional[RuntimeLogBuffer] = None


def init_runtime_log_buffer(max_entries: int = 4000) -> RuntimeLogBuffer:
    """获取并初始化全局运行时日志缓冲。"""
    global _runtime_log_buffer
    if _runtime_log_buffer is None:
        _runtime_log_buffer = RuntimeLogBuffer(max_entries=max_entries)
    _runtime_log_buffer.install()
    return _runtime_log_buffer


def get_runtime_log_buffer() -> RuntimeLogBuffer:
    """获取全局运行时日志缓冲。"""
    return init_runtime_log_buffer()
