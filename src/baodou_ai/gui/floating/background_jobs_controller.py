"""Background code-agent job window and report controller."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Set

from PyQt5.QtWidgets import QApplication

from baodou_ai.gui.code_agent_window import CodeAgentJobWindow


class BackgroundJobsController:
    def __init__(
        self,
        owner=None,
        *,
        config=None,
        job_manager=None,
        delegate: Optional["BackgroundJobsDelegate"] = None,
    ) -> None:
        if delegate is None:
            delegate = _LegacyBackgroundJobsDelegate(owner)
        self._delegate = delegate
        self._config = config if config is not None else getattr(owner, "_config", None)
        self._job_manager = job_manager if job_manager is not None else getattr(owner, "_job_manager", None)
        self.job_windows: Dict[str, CodeAgentJobWindow] = {}
        self.suppressed_job_window_ids: Set[str] = set()

    def poll(self) -> None:
        try:
            for event in self._job_manager.drain_events():
                self.log_event(event)
            self.sync_memory_job_windows()

            collected_messages: List[str] = []
            for report in self._job_manager.collect_pending_reports():
                message = self.handle_report(report)
                if message:
                    collected_messages.append(message)

            if collected_messages:
                combined = "\n".join(collected_messages)
                self._delegate.display_background_report(combined)
                self._delegate.announce_report(combined)
        except Exception as exc:
            self._delegate.append_log(f"[WARNING] 刷新后台代码任务失败: {exc}\n", "warning")

    def log_event(self, event: Dict[str, Any]) -> None:
        status = str(event.get("status") or "")
        message = str(event.get("message") or "").strip()
        error_envelope = event.get("error_envelope") if isinstance(event.get("error_envelope"), dict) else {}
        if not message:
            message = str(error_envelope.get("user_message") or "").strip()
        job_id = str(event.get("job_id") or "").strip()
        self.sync_job_window(job_id, auto_open=status == "running")
        if not message:
            return
        level = "info"
        if status in {"failed"}:
            level = "error"
        elif status in {"cancelled"}:
            level = "warning"
        elif status in {"running", "completed"}:
            level = "success" if status == "completed" else "info"
        self._delegate.append_log(f"[CODE_AGENT] {message}\n", level)
        self._delegate.refresh_console_jobs()

    def sync_memory_job_windows(self) -> None:
        try:
            memory_jobs = self._job_manager.get_memory_jobs()
        except Exception:
            return

        memory_job_ids = {
            str(job.get("job_id") or "").strip()
            for job in memory_jobs
            if str(job.get("job_id") or "").strip()
        }
        stale_job_ids = [
            job_id for job_id in list(self.job_windows.keys()) if job_id not in memory_job_ids
        ]
        for job_id in stale_job_ids:
            self.close_job_window(job_id)

    def sync_job_window(self, job_id: str, auto_open: bool = False) -> None:
        if not job_id:
            return
        if job_id in self.suppressed_job_window_ids and job_id not in self.job_windows:
            return
        snapshot = self._job_manager.get_job(job_id)
        if snapshot is None:
            self.close_job_window(job_id)
            return
        if bool(snapshot.get("dismissed")):
            self.close_job_window(job_id)
            return

        window, created = self.ensure_job_window(job_id)
        window.refresh_job(force_logs=created)
        if created:
            self.position_job_window(window)
        if created or auto_open:
            window.show()
            window.raise_()
            window.activateWindow()

    def ensure_job_window(self, job_id: str) -> tuple[CodeAgentJobWindow, bool]:
        existing = self.job_windows.get(job_id)
        if existing is not None:
            return existing, False

        window = CodeAgentJobWindow(
            self._config,
            self._job_manager,
            job_id,
            on_closed=self.handle_job_window_closed,
        )
        self.job_windows[job_id] = window
        return window, True

    def position_job_window(self, window: CodeAgentJobWindow) -> None:
        visible_windows = [item for item in self.job_windows.values() if item.isVisible()]
        offset = max(0, len(visible_windows) - 1) * 26
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        width = window.width()
        height = window.height()
        x = geometry.x() + max(24, geometry.width() - width - 40 - offset)
        y = geometry.y() + min(max(24, 56 + offset), max(24, geometry.height() - height - 40))
        window.move(x, y)

    def handle_job_window_closed(self, job_id: str) -> None:
        self.suppressed_job_window_ids.add(job_id)
        self.job_windows.pop(job_id, None)

    def close_job_window(self, job_id: str) -> None:
        window = self.job_windows.pop(job_id, None)
        if window is not None:
            window.close()

    def handle_report(self, report: Dict[str, Any]) -> str:
        message = self.format_report(report)
        context_report = self.format_context_report(report, fallback=message)
        status = str(report.get("status") or "").strip()
        history_status = "completed" if status == "completed" else "failed"
        title = str(report.get("title") or report.get("job_id") or "后台代码任务").strip()

        self._delegate.append_log(
            f"[CODE_AGENT] {message}\n",
            "success" if status == "completed" else "warning",
        )
        self._delegate.add_history_task(
            instruction=f"后台代码任务：{title}",
            status=history_status,
            report=message,
            context_report=context_report,
            memory="",
            steps=0,
            include_in_context=True,
        )
        self._delegate.refresh_console_jobs()
        return message

    @staticmethod
    def format_report(report: Dict[str, Any]) -> str:
        spoken_report = str(report.get("spoken_report") or "").strip()
        if spoken_report:
            return spoken_report

        title = str(report.get("title") or report.get("job_id") or "后台代码任务").strip()
        summary = str(report.get("result_summary") or report.get("summary") or "").strip()
        workspace_path = str(report.get("workspace_path") or "").strip()
        error = str(report.get("error") or "").strip()
        error_envelope = report.get("error_envelope") if isinstance(report.get("error_envelope"), dict) else {}
        status = str(report.get("status") or "").strip()
        if status == "failed":
            detail = (
                str(error_envelope.get("user_message") or "").strip()
                or error
                or summary
                or "任务失败"
            )
            workspace_clause = f"。执行目录：{workspace_path}" if workspace_path else ""
            return f"后台代码任务“{title}”执行失败：{detail}{workspace_clause}。"
        summary_clause = f"结果：{summary}。" if summary else ""
        workspace_clause = f"执行目录：{workspace_path}。" if workspace_path else ""
        return f"后台代码任务“{title}”已执行成功。{summary_clause}{workspace_clause}".strip()

    @classmethod
    def format_context_report(cls, report: Dict[str, Any], fallback: str = "") -> str:
        message = fallback or cls.format_report(report)
        final_output = str(report.get("final_output") or "").strip()
        if not final_output:
            return message
        return f"{message}\n\n最终结果：\n{cls.clip_text(final_output, 6000)}"

    @staticmethod
    def clip_text(text: str, limit: int) -> str:
        normalized = str(text or "").strip()
        if len(normalized) <= limit:
            return normalized
        if limit <= 3:
            return normalized[:limit]
        return normalized[: limit - 3] + "..."

    def shutdown(self) -> None:
        for window in list(self.job_windows.values()):
            window.close()
        self.job_windows = {}


class BackgroundJobsDelegate(Protocol):
    def is_busy(self) -> bool:
        ...

    def append_log(self, text: str, level: str) -> None:
        ...

    def refresh_console_jobs(self) -> None:
        ...

    def add_history_task(self, **payload) -> None:
        ...

    def show_history_if_idle(self) -> None:
        ...

    def display_background_report(self, text: str) -> None:
        ...

    def announce_report(self, text: str) -> None:
        ...


class _LegacyBackgroundJobsDelegate:
    """Compatibility shim for tests/legacy call sites."""

    def __init__(self, owner) -> None:
        self._owner = owner

    def is_busy(self) -> bool:
        owner = self._owner
        checker = getattr(owner, "is_busy", None)
        if callable(checker):
            return bool(checker())
        task_active = getattr(owner, "_task_active", None)
        waiting_tts = getattr(owner, "_is_waiting_for_tts", None)
        return bool(callable(task_active) and task_active()) or bool(callable(waiting_tts) and waiting_tts())

    def display_background_report(self, text: str) -> None:
        owner = self._owner
        handler = getattr(owner, "display_background_report", None)
        if callable(handler):
            handler(text)
            return
        panel = getattr(owner, "panel_window", None)
        if panel is None:
            return
        append = getattr(panel, "append_background_report", None)
        if callable(append):
            append(text)

    def append_log(self, text: str, level: str) -> None:
        logger = getattr(self._owner, "append_log", None)
        if callable(logger):
            logger(text, level)
            return
        log_buffer = getattr(self._owner, "_log_buffer", None)
        if log_buffer is not None:
            log_buffer.append_log(text, level)

    def refresh_console_jobs(self) -> None:
        refresh = getattr(self._owner, "refresh_console_jobs", None)
        if callable(refresh):
            refresh()
            return
        console_window = getattr(self._owner, "_console_window", None)
        if console_window is not None:
            console_window.refresh_jobs()

    def add_history_task(self, **payload) -> None:
        add_task = getattr(self._owner, "add_history_task", None)
        if callable(add_task):
            add_task(**payload)
            return
        session_history = getattr(self._owner, "_session_history", None)
        if session_history is not None:
            session_history.add_task(**payload)

    def show_history_if_idle(self) -> None:
        shower = getattr(self._owner, "show_history_if_idle", None)
        if callable(shower):
            shower()
            return
        legacy = getattr(self._owner, "_show_history_if_idle", None)
        if callable(legacy):
            legacy()

    def announce_report(self, text: str) -> None:
        announcer = getattr(self._owner, "announce_report", None)
        if callable(announcer):
            announcer(text)
            return
        legacy_report = getattr(self._owner, "_on_report", None)
        announced = legacy_report(text) if callable(legacy_report) else None
        if announced is not None:
            tts = getattr(self._owner, "_tts", None)
            if tts is not None:
                tts.current_done_event = announced
                tts.start_waiting()
