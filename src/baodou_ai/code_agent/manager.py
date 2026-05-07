"""后台 Code Agent 任务管理器。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from baodou_ai.core.config import Config
from baodou_ai.core.error_envelope import (
    CODE_CODE_AGENT_FAILED,
    KIND_EXECUTION_FAILED,
    SOURCE_CODE_AGENT,
    from_exception,
)
from baodou_ai.runtime_paths import resolve_context_debug_dir, resolve_memory_file

from .dispatcher import CodeAgentDispatcher
from .models import (
    BackgroundJob,
    BackgroundJobEvent,
    BackgroundJobResult,
    BackgroundJobStatus,
    CodeAgentRequest,
    PendingReportItem,
)
from .reporter import CodeAgentReportGenerator
from .runtime import BackgroundJobWorker
from .session_files import resolve_session_root
from .store import InMemoryJobStore


class JobManager:
    """统一管理后台 code agent 任务。"""

    _LOG_LIMIT = 200
    _RUN_JOIN_TIMEOUT = 5.0
    _PENDING_FINAL_OUTPUT_LIMIT = 12000

    def __init__(
        self,
        config: Optional[Config] = None,
        dispatcher: Optional[CodeAgentDispatcher] = None,
        reporter: Optional[CodeAgentReportGenerator] = None,
        session_root: Optional[str | Path] = None,
    ) -> None:
        self._config = config or Config()
        self._dispatcher = dispatcher or CodeAgentDispatcher(self._config)
        self._reporter = reporter or CodeAgentReportGenerator(self._config)
        self._store = InMemoryJobStore()
        self._lock = threading.RLock()
        self._workers: Dict[str, BackgroundJobWorker] = {}
        self._events: List[BackgroundJobEvent] = []
        self._pending_reports: List[PendingReportItem] = []
        self._job_counter = 0
        self._restarting_jobs: Set[str] = set()
        self._session_root = resolve_session_root(session_root)
        self._session_root.mkdir(parents=True, exist_ok=True)

    def submit(
        self,
        *,
        task: str,
        title: Optional[str] = None,
        goal: Optional[str] = None,
        job_id: Optional[str] = None,
        workspace_path: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        code_config = self._config.code_agent_config
        if not bool(code_config.get("enabled", True)):
            raise ValueError("code_agent 功能当前未启用")

        normalized_task = str(task or "").strip()
        if not normalized_task:
            raise ValueError("task 不能为空")

        restarting_worker: Optional[BackgroundJobWorker] = None
        restarting_job_id = ""
        new_snapshot: Dict[str, Any]

        with self._lock:
            max_concurrent = self._get_max_concurrent_locked()
            if job_id:
                job = self._require_job(job_id)
                if job.dismissed:
                    raise ValueError("该后台任务已从当前会话移除，无法继续修改")
                if not self._is_job_in_memory_window_locked(job_id):
                    raise ValueError("该后台任务已不在当前记忆窗口中，无法继续修改")
                if job.status != BackgroundJobStatus.RUNNING and self._running_count_locked() >= max_concurrent:
                    raise ValueError("当前后台代码任务已满，请等待已有任务结束后再试")
                if job.status == BackgroundJobStatus.RUNNING:
                    restarting_job_id = job.job_id
                    restarting_worker = self._workers.get(job.job_id)
                    self._restarting_jobs.add(job.job_id)
            else:
                if self._running_count_locked() >= max_concurrent:
                    raise ValueError("当前后台代码任务已满，请等待已有任务结束后再试")

        if restarting_worker is not None:
            restarting_worker.cancel()
            restarting_worker.join(timeout=self._RUN_JOIN_TIMEOUT)
            if restarting_worker.is_alive():
                with self._lock:
                    self._restarting_jobs.discard(restarting_job_id)
                raise ValueError("后台代码任务正在忙，暂时无法切换新的任务要求")

        with self._lock:
            max_concurrent = self._get_max_concurrent_locked()
            if job_id:
                job = self._require_job(job_id)
                resolved_timeout = job.timeout_seconds
                resolved_provider = job.provider
                normalized_title = self._normalize_title(title, job.title, normalized_task)
                resolved_goal = self._normalize_goal(goal, job.goal, normalized_task)

                if restarting_job_id:
                    self._restarting_jobs.discard(restarting_job_id)
                    self._workers.pop(job.job_id, None)
                    self._persist_job_locked(job)
                elif self._running_count_locked() >= max_concurrent and job.status != BackgroundJobStatus.RUNNING:
                    raise ValueError("当前后台代码任务已满，请等待已有任务结束后再试")

                job.provider = resolved_provider
                job.title = normalized_title
                job.goal = resolved_goal
                job.task = normalized_task
                job.timeout_seconds = resolved_timeout
                job.pending_report = False
                job.result_summary = ""
                job.spoken_report = ""
                job.artifacts = []
                self._pending_reports = [item for item in self._pending_reports if item.job_id != job.job_id]
                if normalized_task:
                    job.instruction_history.append(normalized_task)
                self._start_job_locked(job)
                new_snapshot = job.snapshot()
            else:
                provider = self._dispatcher.resolve_provider()
                resolved_workspace = self._resolve_workspace_path(workspace_path, code_config)
                resolved_timeout = int(timeout_seconds or code_config.get("default_timeout_seconds", 1800) or 1800)
                normalized_title = self._normalize_title(title, "", normalized_task)
                resolved_goal = self._normalize_goal(goal, "", normalized_task)

                self._job_counter += 1
                created_job_id = f"code-job-{int(time.time() * 1000)}-{self._job_counter:04d}"
                job = BackgroundJob(
                    job_id=created_job_id,
                    title=normalized_title,
                    goal=resolved_goal,
                    task=normalized_task,
                    provider=provider,
                    workspace_path=resolved_workspace,
                    timeout_seconds=max(resolved_timeout, 1),
                    status=BackgroundJobStatus.RUNNING,
                    summary="后台代码任务运行中",
                    instruction_history=[normalized_task],
                )
                self._store.put(job)
                self._start_job_locked(job)
                new_snapshot = job.snapshot()

            return new_snapshot

    def list_jobs(self, include_dismissed: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = []
            for job in self._store.values():
                if not include_dismissed and job.dismissed:
                    continue
                jobs.append(job.snapshot())
            jobs.sort(key=lambda item: (item["created_at"], item["job_id"]), reverse=True)
            return jobs

    def get_job(self, job_id: str, include_logs: bool = False) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._store.get(job_id)
            if job is None:
                return None
            return job.snapshot(include_logs=include_logs)

    def get_memory_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [job.remember_card() for job in self._memory_jobs_locked()]

    def cancel(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._require_job(job_id)
            if job.status.is_terminal:
                return job.snapshot()
            worker = self._workers.get(job_id)

        if worker is not None:
            worker.cancel()
            worker.join(timeout=self._RUN_JOIN_TIMEOUT)

        with self._lock:
            job = self._require_job(job_id)
            self._workers.pop(job_id, None)
            if not job.status.is_terminal:
                job.status = BackgroundJobStatus.CANCELLED
                job.summary = "任务已取消"
                job.error = None
                job.result = None
                job.process_pid = None
                job.ended_at = time.time()
                job.updated_at = job.ended_at
                job.pending_report = False
                self._persist_job_locked(job)
                self._push_event(job, "cancelled", f"{job.title} 已取消")
            return job.snapshot()

    def dismiss(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._require_job(job_id)
            if not job.status.is_terminal:
                raise ValueError("运行中的任务不能关闭，请先取消")
            job.dismissed = True
            job.pending_report = False
            self._pending_reports = [item for item in self._pending_reports if item.job_id != job_id]
            self._persist_job_locked(job)
            self._push_event(job, "dismissed", f"{job.title} 已从任务中心移除")
            return job.snapshot()

    def drain_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            events = [event.snapshot() for event in self._events]
            self._events = []
            return events

    def collect_pending_reports(self) -> List[Dict[str, Any]]:
        with self._lock:
            reports = [item.snapshot() for item in self._pending_reports]
            self._pending_reports = []
            for job in self._store.values():
                if job.job_id in {item["job_id"] for item in reports}:
                    job.pending_report = False
                    self._persist_job_locked(job)
            return reports

    def build_running_jobs_prompt(self) -> str:
        with self._lock:
            cards = [job.remember_card() for job in self._memory_jobs_locked()]
            if not cards:
                return ""

            lines = [
                "These are the remembered background code-agent task cards in the current session.",
                "Use job_id only internally when continuing one of these exact tasks; the user will refer to them in natural language.",
                "If the user adds or changes requirements for one of these tasks, rewrite a complete fresh task yourself, then call code_agent again with the same job_id; the tool layer will stop the old run and restart that job_id with your new task.",
            ]
            for card in cards:
                line = (
                    f"- job_id={card['job_id']} | provider={card['provider']} | status={card['status']} | "
                    f"title={card['title']} | goal={card['goal']} | workspace={card['workspace_path']}"
                )
                result_summary = str(card.get("result_summary") or "").strip()
                artifacts = card.get("artifacts") or []
                if result_summary:
                    line += f" | result_summary={result_summary}"
                if artifacts:
                    line += f" | artifacts={', '.join(str(item) for item in artifacts)}"
                lines.append(line)
            return "\n".join(lines)

    def build_pending_reports_prompt(self) -> str:
        with self._lock:
            if not self._pending_reports:
                return ""
            lines = [
                "One or more background code-agent jobs finished while the foreground assistant was busy.",
                "Surface the result to the user before taking any new GUI action, and do not automatically take over the computer based on these results.",
            ]
            for item in self._pending_reports:
                summary = item.spoken_report or item.result_summary or item.summary or item.error or ""
                lines.append(
                    f"- {item.job_id} | provider={item.provider} | status={item.status} | "
                    f"title={item.title} | summary={summary}"
                )
                final_output = self._clip_text(item.final_output, self._PENDING_FINAL_OUTPUT_LIMIT)
                if final_output:
                    lines.append(f"  Final output:\n{final_output}")
            return "\n".join(lines)

    def shutdown(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
        for worker in workers:
            worker.cancel()
        for worker in workers:
            worker.join(timeout=self._RUN_JOIN_TIMEOUT)

    def _resolve_workspace_path(self, workspace_path: Optional[str], code_config: Dict[str, Any]) -> str:
        raw_path = str(workspace_path or code_config.get("workspace_root") or self._default_workspace_root()).strip()
        resolved = Path(raw_path).expanduser().resolve()
        if not resolved.exists():
            raise ValueError(f"workspace_path 不存在: {resolved}")
        if resolved.is_file():
            resolved = resolved.parent
        return str(resolved)

    @staticmethod
    def _default_workspace_root() -> Path:
        desktop = Path.home() / "Desktop"
        if desktop.exists():
            return desktop
        return Path.cwd()

    def _start_job_locked(self, job: BackgroundJob) -> None:
        now = time.time()
        job.status = BackgroundJobStatus.RUNNING
        job.started_at = now
        job.ended_at = None
        job.updated_at = now
        job.summary = "后台代码任务运行中"
        job.error = None
        job.error_envelope = None
        job.final_output = ""
        job.raw_output = ""
        job.process_pid = None
        job.pending_report = False
        job.result_summary = ""
        job.spoken_report = ""
        job.artifacts = []
        job.result = None
        job.logs = []
        job.run_counter += 1
        run_id = f"{job.job_id}-run-{job.run_counter:04d}"
        job.run_id = run_id
        job.last_run_id = run_id

        request = CodeAgentRequest(
            job_id=job.job_id,
            provider=job.provider,
            title=job.title,
            task=job.task,
            workspace_path=job.workspace_path,
            timeout_seconds=job.timeout_seconds,
        )
        worker = BackgroundJobWorker(
            request=request,
            dispatcher=self._dispatcher,
            on_complete=lambda result, job_id=job.job_id, run_id=run_id: self._handle_worker_complete(job_id, run_id, result),
            on_log=lambda text, job_id=job.job_id, run_id=run_id: self._append_log(job_id, run_id, text),
            on_pid=lambda pid, job_id=job.job_id, run_id=run_id: self._set_process_pid(job_id, run_id, pid),
        )
        self._workers[job.job_id] = worker
        self._persist_job_locked(job)
        self._push_event(job, "running", f"{job.title} 已开始运行")
        worker.start()

    def _append_log(self, job_id: str, run_id: str, text: str) -> None:
        with self._lock:
            job = self._store.get(job_id)
            if job is None or job.run_id != run_id:
                return
            job.append_log(text, max_lines=self._LOG_LIMIT)

    def _set_process_pid(self, job_id: str, run_id: str, pid: int) -> None:
        with self._lock:
            job = self._store.get(job_id)
            if job is None or job.run_id != run_id:
                return
            job.process_pid = int(pid)
            job.updated_at = time.time()

    def _handle_worker_complete(self, job_id: str, run_id: str, result: BackgroundJobResult) -> None:
        report_input: Optional[Dict[str, Any]] = None
        report_status = ""
        report_event_type = ""
        report_event_message = ""

        with self._lock:
            job = self._require_job(job_id)
            if job_id in self._restarting_jobs and job.run_id == run_id:
                self._workers.pop(job_id, None)
                return
            if job.run_id != run_id:
                return

            job.result = result
            job.final_output = result.final_output
            job.raw_output = result.raw_output
            job.error = result.error
            job.error_envelope = dict(result.error_envelope or {}) if result.error_envelope else None
            job.process_pid = None
            job.ended_at = time.time()
            job.updated_at = job.ended_at
            job.summary = result.summary
            self._workers.pop(job_id, None)

            if result.cancelled:
                job.status = BackgroundJobStatus.CANCELLED
                job.pending_report = False
                self._persist_job_locked(job)
                self._push_event(job, "cancelled", f"{job.title} 已取消")
                return

            if result.ok:
                job.status = BackgroundJobStatus.COMPLETED
                report_status = job.status.value
                report_event_type = "completed"
                report_event_message = f"{job.title} 已完成"
                report_input = {
                    "title": job.title,
                    "task": job.task,
                    "status": job.status.value,
                    "workspace_path": job.workspace_path,
                    "summary": result.summary,
                    "final_output": result.final_output,
                    "error": result.error,
                    "error_envelope": dict(result.error_envelope or {}) if result.error_envelope else None,
                    "logs": list(job.logs),
                }
            else:
                job.status = BackgroundJobStatus.FAILED
                report_status = job.status.value
                report_event_type = "failed"
                report_event_message = f"{job.title} 执行失败"
                report_input = {
                    "title": job.title,
                    "task": job.task,
                    "status": job.status.value,
                    "workspace_path": job.workspace_path,
                    "summary": result.summary,
                    "final_output": result.final_output,
                    "error": result.error,
                    "error_envelope": dict(result.error_envelope or {}) if result.error_envelope else None,
                    "logs": list(job.logs),
                }
            self._persist_job_locked(job)

        if report_input is None:
            return

        artifacts = self._collect_workspace_artifacts(report_input["workspace_path"])
        report_payload = self._reporter.build_report(report_input)

        with self._lock:
            job = self._require_job(job_id)
            if job.run_id != run_id:
                return
            job.result_summary = str(report_payload.get("result_summary") or report_payload.get("report_summary") or "").strip()
            job.spoken_report = str(report_payload.get("spoken_report") or "").strip()
            job.artifacts = artifacts
            if job.dismissed:
                self._persist_job_locked(job)
                return
            job.pending_report = True
            self._pending_reports.append(
                PendingReportItem(
                    job_id=job.job_id,
                    title=job.title,
                    provider=job.provider,
                    status=report_status,
                    summary=result.summary,
                    workspace_path=job.workspace_path,
                    result_summary=job.result_summary,
                    spoken_report=job.spoken_report,
                    final_output=result.final_output,
                    error=result.error,
                    error_envelope=dict(result.error_envelope or {}) if result.error_envelope else None,
                )
            )
            self._persist_job_locked(job)
            self._push_event(
                job,
                report_event_type,
                report_event_message,
                error_envelope=dict(result.error_envelope or {}) if result.error_envelope else None,
            )

    def _push_event(
        self,
        job: BackgroundJob,
        event_type: str,
        message: str,
        error_envelope: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._events.append(
            BackgroundJobEvent(
                event_type=event_type,
                job_id=job.job_id,
                status=job.status.value,
                message=message,
                error_envelope=dict(error_envelope or {}),
            )
        )

    def _require_job(self, job_id: str) -> BackgroundJob:
        job = self._store.get(job_id)
        if job is None:
            raise ValueError(f"未找到后台任务: {job_id}")
        return job

    def _get_max_concurrent_locked(self) -> int:
        max_concurrent = int(self._config.code_agent_config.get("max_concurrent_jobs", 2) or 2)
        return max(1, max_concurrent)

    def _running_count_locked(self) -> int:
        return sum(
            1
            for job in self._store.values()
            if not job.dismissed and job.status == BackgroundJobStatus.RUNNING
        )

    def _memory_jobs_locked(self) -> List[BackgroundJob]:
        max_total = self._get_max_concurrent_locked() + 1
        jobs = [job for job in self._store.values() if not job.dismissed]
        running_jobs = [job for job in jobs if job.status == BackgroundJobStatus.RUNNING]
        running_jobs.sort(key=lambda item: (item.updated_at, item.job_id), reverse=True)

        remaining_slots = max(0, max_total - len(running_jobs))
        non_running_jobs = [job for job in jobs if job.status != BackgroundJobStatus.RUNNING]
        non_running_jobs.sort(key=lambda item: (item.updated_at, item.job_id), reverse=True)

        return running_jobs + non_running_jobs[:remaining_slots]

    def _is_job_in_memory_window_locked(self, job_id: str) -> bool:
        return job_id in {job.job_id for job in self._memory_jobs_locked()}

    @staticmethod
    def _normalize_title(title: Optional[str], fallback_title: str, task: str) -> str:
        candidate = str(title or "").strip() or str(fallback_title or "").strip() or str(task or "").strip()
        return candidate[:80]

    @staticmethod
    def _normalize_goal(goal: Optional[str], fallback_goal: str, task: str) -> str:
        candidate = str(goal or "").strip() or str(fallback_goal or "").strip() or str(task or "").strip()
        if not candidate:
            raise ValueError("goal 不能为空")
        return candidate

    def _session_dir(self, job_id: str) -> Path:
        return self._session_root / job_id

    def _persist_job_locked(self, job: BackgroundJob) -> None:
        session_dir = self._session_dir(job.job_id)
        runs_dir = session_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)

        self._write_json(session_dir / "session.json", job.session_snapshot())
        self._write_json(session_dir / "card.json", job.remember_card())

        run_id = job.run_id or job.last_run_id
        if run_id:
            self._write_json(runs_dir / f"{run_id}.json", job.run_snapshot())
            try:
                (runs_dir / f"{run_id}.log").write_text("\n".join(job.logs), encoding="utf-8")
            except Exception:
                pass

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            envelope = from_exception(
                exc,
                source=SOURCE_CODE_AGENT,
                kind=KIND_EXECUTION_FAILED,
                user_message="后台任务状态文件写入失败",
                code=CODE_CODE_AGENT_FAILED,
                retryable=True,
                extra={"path": str(path)},
            )
            print(f"[ERROR_ENVELOPE] {envelope.to_dict()}")

    @staticmethod
    def _collect_workspace_artifacts(workspace_path: str, limit: int = 5) -> List[str]:
        if not workspace_path:
            return []
        root = Path(workspace_path).expanduser()
        if not root.exists():
            return []

        ignored_parts = {".git", "node_modules", ".venv", "venv", "__pycache__"}
        candidates: List[Path] = []
        try:
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if any(part in ignored_parts for part in path.parts):
                    continue
                if JobManager._is_runtime_owned_artifact(path):
                    continue
                candidates.append(path)
        except Exception:
            return []

        candidates.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0.0, reverse=True)
        artifacts: List[str] = []
        for path in candidates:
            try:
                relative = str(path.relative_to(root)).replace("\\", "/")
            except Exception:
                relative = path.name
            if relative in artifacts:
                continue
            artifacts.append(relative)
            if len(artifacts) >= limit:
                break
        return artifacts

    @staticmethod
    def _is_runtime_owned_artifact(path: Path) -> bool:
        try:
            candidate = path.expanduser().resolve()
        except Exception:
            return False

        try:
            if candidate == resolve_memory_file():
                return True
        except Exception:
            pass

        try:
            context_debug_dir = resolve_context_debug_dir()
            if context_debug_dir in candidate.parents:
                return True
        except Exception:
            pass

        return False

    @staticmethod
    def _clip_text(text: str, limit: int) -> str:
        normalized = str(text or "").strip()
        if len(normalized) <= limit:
            return normalized
        if limit <= 3:
            return normalized[:limit]
        return normalized[: limit - 3] + "..."
