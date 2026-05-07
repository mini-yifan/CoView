"""后台 Code Agent 数据模型。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


def _shorten(text: str, limit: int) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= limit:
        return normalized
    if limit <= 3:
        return normalized[:limit]
    return normalized[: limit - 3] + "..."


class BackgroundJobStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {
            BackgroundJobStatus.COMPLETED,
            BackgroundJobStatus.FAILED,
            BackgroundJobStatus.CANCELLED,
        }


@dataclass
class CodeAgentRequest:
    job_id: str
    provider: str
    title: str
    task: str
    workspace_path: str
    timeout_seconds: int


@dataclass
class BackgroundJobResult:
    ok: bool
    summary: str
    provider: str
    final_output: str = ""
    raw_output: str = ""
    error: Optional[str] = None
    error_envelope: Optional[Dict[str, Any]] = None
    exit_code: Optional[int] = None
    cancelled: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> Dict[str, Any]:
        payload = {
            "ok": self.ok,
            "summary": self.summary,
            "provider": self.provider,
            "final_output": self.final_output,
            "raw_output": self.raw_output,
            "error": self.error,
            "exit_code": self.exit_code,
            "cancelled": self.cancelled,
            "metadata": dict(self.metadata),
        }
        if self.error_envelope:
            payload["error_envelope"] = dict(self.error_envelope)
        return payload


@dataclass
class PendingReportItem:
    job_id: str
    title: str
    provider: str
    status: str
    summary: str
    workspace_path: str
    result_summary: str = ""
    spoken_report: str = ""
    final_output: str = ""
    error: Optional[str] = None
    error_envelope: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)

    def snapshot(self) -> Dict[str, Any]:
        payload = {
            "job_id": self.job_id,
            "title": self.title,
            "provider": self.provider,
            "status": self.status,
            "summary": self.summary,
            "workspace_path": self.workspace_path,
            "result_summary": self.result_summary,
            "spoken_report": self.spoken_report,
            "final_output": self.final_output,
            "error": self.error,
            "created_at": self.created_at,
        }
        if self.error_envelope:
            payload["error_envelope"] = dict(self.error_envelope)
        return payload


@dataclass
class BackgroundJobEvent:
    event_type: str
    job_id: str
    status: str
    message: str
    error_envelope: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)

    def snapshot(self) -> Dict[str, Any]:
        payload = {
            "event_type": self.event_type,
            "job_id": self.job_id,
            "status": self.status,
            "message": self.message,
            "created_at": self.created_at,
        }
        if self.error_envelope:
            payload["error_envelope"] = dict(self.error_envelope)
        return payload


@dataclass
class BackgroundJob:
    job_id: str
    title: str
    goal: str
    task: str
    provider: str
    workspace_path: str
    timeout_seconds: int
    status: BackgroundJobStatus
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    summary: str = ""
    error: Optional[str] = None
    error_envelope: Optional[Dict[str, Any]] = None
    final_output: str = ""
    raw_output: str = ""
    process_pid: Optional[int] = None
    pending_report: bool = False
    dismissed: bool = False
    result_summary: str = ""
    spoken_report: str = ""
    artifacts: List[str] = field(default_factory=list)
    instruction_history: List[str] = field(default_factory=list)
    run_id: Optional[str] = None
    last_run_id: Optional[str] = None
    run_counter: int = 0
    logs: List[str] = field(default_factory=list)
    result: Optional[BackgroundJobResult] = None

    def append_log(self, text: str, max_lines: int = 200) -> None:
        for raw_line in str(text or "").splitlines():
            line = raw_line.rstrip()
            if not line:
                continue
            self.logs.append(line)
        if len(self.logs) > max_lines:
            self.logs = self.logs[-max_lines:]
        self.updated_at = time.time()

    def latest_log_excerpt(self, max_lines: int = 6, max_chars: int = 400) -> str:
        excerpt = "\n".join(self.logs[-max_lines:])
        return _shorten(excerpt, max_chars)

    def context_summary(self) -> str:
        return (
            f"{self.job_id} | provider={self.provider} | status={self.status.value} | "
            f"title={_shorten(self.title, 50)} | workspace={_shorten(self.workspace_path, 80)}"
        )

    def remember_card(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "job_id": self.job_id,
            "provider": self.provider,
            "title": self.title,
            "status": self.status.value,
            "workspace_path": self.workspace_path,
            "goal": self.goal,
        }
        if self.status.is_terminal:
            payload["result_summary"] = self.result_summary
            payload["artifacts"] = list(self.artifacts)
        return payload

    def session_snapshot(self) -> Dict[str, Any]:
        payload = {
            "job_id": self.job_id,
            "provider": self.provider,
            "title": self.title,
            "goal": self.goal,
            "task": self.task,
            "workspace_path": self.workspace_path,
            "timeout_seconds": self.timeout_seconds,
            "status": self.status.value,
            "summary": self.summary,
            "error": self.error,
            "final_output": self.final_output,
            "raw_output": self.raw_output,
            "result_summary": self.result_summary,
            "artifacts": list(self.artifacts),
            "instruction_history": list(self.instruction_history),
            "run_id": self.run_id,
            "last_run_id": self.last_run_id,
            "run_counter": self.run_counter,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "dismissed": self.dismissed,
        }
        if self.error_envelope:
            payload["error_envelope"] = dict(self.error_envelope)
        return payload

    def run_snapshot(self) -> Dict[str, Any]:
        payload = {
            "job_id": self.job_id,
            "run_id": self.run_id or self.last_run_id,
            "provider": self.provider,
            "title": self.title,
            "goal": self.goal,
            "task": self.task,
            "workspace_path": self.workspace_path,
            "timeout_seconds": self.timeout_seconds,
            "status": self.status.value,
            "summary": self.summary,
            "error": self.error,
            "final_output": self.final_output,
            "raw_output": self.raw_output,
            "process_pid": self.process_pid,
            "logs": list(self.logs),
            "result": self.result.snapshot() if self.result is not None else None,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "updated_at": self.updated_at,
        }
        if self.error_envelope:
            payload["error_envelope"] = dict(self.error_envelope)
        return payload

    def snapshot(self, include_logs: bool = False) -> Dict[str, Any]:
        payload = {
            "job_id": self.job_id,
            "run_id": self.run_id,
            "last_run_id": self.last_run_id,
            "title": self.title,
            "goal": self.goal,
            "task": self.task,
            "provider": self.provider,
            "workspace_path": self.workspace_path,
            "timeout_seconds": self.timeout_seconds,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "summary": self.summary,
            "error": self.error,
            "final_output": self.final_output,
            "raw_output": self.raw_output,
            "process_pid": self.process_pid,
            "pending_report": self.pending_report,
            "dismissed": self.dismissed,
            "result_summary": self.result_summary,
            "spoken_report": self.spoken_report,
            "artifacts": list(self.artifacts),
            "instruction_history": list(self.instruction_history),
            "latest_log_excerpt": self.latest_log_excerpt(),
            "log_count": len(self.logs),
            "result": self.result.snapshot() if self.result is not None else None,
        }
        if self.error_envelope:
            payload["error_envelope"] = dict(self.error_envelope)
        if include_logs:
            payload["logs"] = list(self.logs)
        return payload
