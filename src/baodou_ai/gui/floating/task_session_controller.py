"""Task lifecycle controller for floating GUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from PyQt5.QtCore import QTimer

from baodou_ai.ai.session_history import SessionHistory
from baodou_ai.core.task_memory_store import TaskMemoryStore
from baodou_ai.gui.floating.task_session_host import TaskSessionHost
from baodou_ai.gui.i18n import t
from baodou_ai.gui.main_window import AIWorker

if TYPE_CHECKING:
    from baodou_ai.ai.session_history import SessionHistory as SessionHistoryStore
    from baodou_ai.gui.floating.runtime_state_presenter import RuntimeStatePresenter
    from baodou_ai.gui.floating.task_session_state import UITaskSessionState


class TaskSessionController:
    """集中处理任务启动/停止、worker 回调、历史与 memory 收尾。"""

    def __init__(
        self,
        host: TaskSessionHost,
        state: "UITaskSessionState",
        session_history: "SessionHistoryStore",
        task_memory_store: TaskMemoryStore,
        runtime_state_presenter: "RuntimeStatePresenter",
    ) -> None:
        self._host = host
        self._state = state
        self._session_history = session_history
        self._task_memory_store = task_memory_store
        self._runtime_state_presenter = runtime_state_presenter
        self._ai_thread: Optional[AIWorker] = None
        self._retained_workers: List[AIWorker] = []

    @property
    def ai_thread(self) -> Optional[AIWorker]:
        return self._ai_thread

    @property
    def retained_workers(self) -> List[AIWorker]:
        return self._retained_workers

    def task_active(self) -> bool:
        return self._state.status_key in {"running", "stopping"}

    def start_task(self, text: str, source: str = "keyboard", focus_panel: bool = True) -> None:
        self._host.stop_tts()
        self._host.hide_companion_suggestions()
        self._prune_retained_workers()
        self._state.task_text = text
        self._state.iteration = 0
        self._state.token_total = 0
        self._state.max_iterations = self._host.get_default_max_iterations()
        self._state.active_stream_iteration = None
        self._state.instruction = text
        self._state.source = source
        self._state.iterations = []
        show_startup_wait_hint = self._state.should_show_first_startup_wait_hint
        self._state.should_show_first_startup_wait_hint = False
        self._state.first_startup_wait_hint_active = show_startup_wait_hint
        history_context = self._session_history.build_context_prompt()
        initial_external_frontmost_app = self._host.snapshot_last_external_frontmost_app()
        self._host.show_running_state(
            text,
            focus_panel=focus_panel,
            status_hint_text=t("first_startup_wait_hint") if show_startup_wait_hint else "",
        )
        self._host.enable_screenshot_protection()
        self._runtime_state_presenter.apply_runtime_state("running", t("agent_running"))
        self._host.append_log(
            f"[INFO] 收到{self._source_label(source)}任务: {text}\n",
            "info",
        )
        worker = self._host.build_worker(
            text,
            initial_external_frontmost_app=initial_external_frontmost_app,
            history_context=history_context,
            respond_language_override=self._host.get_active_respond_language(),
        )
        self._retained_workers.append(worker)
        self._ai_thread = worker
        worker.finished.connect(self.handle_worker_result)
        worker.error.connect(self.handle_worker_error)
        worker.stream_chunk.connect(self.handle_stream_chunk)
        worker.enter_transparent_mode.connect(self._host.enter_transparent_mode)
        worker.exit_transparent_mode.connect(self._host.exit_transparent_mode)
        worker.iteration_update.connect(self.handle_iteration_update)
        worker.start()

        # Companion-triggered tasks should preserve user's external focus when possible.
        if not focus_panel and initial_external_frontmost_app:
            try:
                self._host.activate_app(initial_external_frontmost_app)
            except Exception:
                pass

    def request_voice_stop(self) -> None:
        self._host.mark_voice_user_interaction()
        was_waiting_for_tts = self._host.is_waiting_for_tts()
        self._host.stop_tts()
        if self._ai_thread is None and was_waiting_for_tts:
            self._host.show_idle_state()
            self._runtime_state_presenter.apply_runtime_state("ready", t("agent_ready"))
            self._host.show_history_if_idle()
            self._host.append_log("[INFO] 语音请求停止播报\n", "warning")
            return

        stop_text = str(
            self._host.get_config_value(
                "voice_interaction_config.stop_spoken_text",
                t("voice_input_stop_spoken_text_default"),
            )
            or ""
        ).strip()
        stop_text = self._host.localize_tts_text(stop_text)
        announced = self._host.speak(stop_text) if stop_text else None

        if self._ai_thread is None:
            self._host.show_finished_state(
                stop_text or t("task_stopped"),
                status_text=t("broadcasting") if announced is not None else t("task_stopped"),
                tts_playing=announced is not None,
            )
            self._runtime_state_presenter.apply_runtime_state("ready", t("agent_ready"))
            if announced is not None:
                self._host.start_tts_waiting()
            else:
                self._host.show_history_if_idle()
            return

        self._ai_thread.stop()
        self._runtime_state_presenter.apply_runtime_state("stopping", t("agent_stopping"))
        self._host.show_stopping_state()
        self._host.append_log("[INFO] 语音请求停止当前任务\n", "warning")

    def request_voice_new_task(self, text: str) -> None:
        task_text = str(text or "").strip()
        if not task_text:
            return
        self._host.mark_voice_user_interaction()
        self._state.pending_voice_task_text = task_text
        self._host.stop_tts()
        if self._ai_thread is None:
            self.start_pending_voice_task()
            return
        self._ai_thread.stop()
        self._runtime_state_presenter.apply_runtime_state("stopping", t("agent_stopping"))
        self._host.show_stopping_state()
        self._host.append_log(f"[INFO] 语音请求切换新任务: {task_text}\n", "warning")

    def handle_voice_exit_request(self) -> None:
        self._host.mark_voice_user_interaction()
        self._state.pending_voice_task_text = ""
        was_waiting_for_tts = self._host.is_waiting_for_tts()
        self._host.stop_tts()
        if self._ai_thread is None:
            self._host.show_idle_state()
            self._runtime_state_presenter.apply_runtime_state("ready", t("agent_ready"))
            self._host.show_history_if_idle()
            if was_waiting_for_tts:
                self._host.append_log("[INFO] 语音退出程序口令已停止播报\n", "warning")
            return
        self._ai_thread.stop()
        self._runtime_state_presenter.apply_runtime_state("stopping", t("agent_stopping"))
        self._host.append_log("[INFO] 语音退出程序口令已停止当前任务\n", "warning")

    def start_pending_voice_task(self) -> bool:
        pending = str(self._state.pending_voice_task_text or "").strip()
        if not pending:
            return False
        self._state.pending_voice_task_text = ""
        self.start_task(pending, source="voice")
        return True

    def on_tts_wait_timeout(self) -> None:
        if self._host.is_waiting_for_tts():
            return
        self._host.finish_tts_waiting()
        self._host.clear_voice_session_language()
        self._host.show_idle_state()
        self._runtime_state_presenter.apply_runtime_state("ready", t("agent_ready"))
        self._host.show_history_if_idle()
        self._host.sync_voice_interaction_state()

    def handle_stop_request(self) -> None:
        self._host.mark_voice_user_interaction()
        self._host.stop_tts()
        if self._ai_thread is None:
            self._host.show_idle_state()
            self._runtime_state_presenter.apply_runtime_state("ready", t("agent_ready"))
            self._host.show_history_if_idle()
            return
        self._ai_thread.stop()
        self._runtime_state_presenter.apply_runtime_state("stopping", t("agent_stopping"))
        self._host.show_stopping_state()
        self._host.append_log("[INFO] 用户请求停止当前任务\n", "warning")

    def handle_iteration_update(self, iteration_index: int, payload: Dict[str, Any]) -> None:
        self.dismiss_first_startup_wait_hint()
        self._state.iterations.append(payload)
        self._state.iteration = iteration_index + 1
        token_total = payload.get("task_total_tokens")
        if token_total is None:
            token_total = payload.get("total_tokens")
        self._state.token_total = int(token_total or 0)
        self._runtime_state_presenter.apply_runtime_state("running", t("agent_running"))
        self._host.append_log(self._build_iteration_log(iteration_index, payload), "info")
        self._host.update_intermediate_report(payload)

    def handle_stream_chunk(self, iteration: int, chunk: str) -> None:
        self.dismiss_first_startup_wait_hint()
        if self._state.active_stream_iteration != iteration:
            self._host.append_log(f"\n{t('stream_header', n=iteration + 1)}\n", "info")
            self._state.active_stream_iteration = iteration
        if chunk:
            self._host.append_log(chunk, "normal")

    def handle_worker_result(self, result: str) -> None:
        result_text = str(result or "").strip() or t("task_ended")
        if result_text == "Task interrupted by user":
            report = SessionHistory.build_interrupted_report(self._state.instruction, self._state.iterations)
            memory = self._read_memory_content()
            self._session_history.add_task(
                instruction=self._state.instruction,
                status="interrupted",
                report=report,
                memory=memory,
                steps=len(self._state.iterations),
            )
            self._clear_memory_txt()
        elif "difficult" in result_text.lower() or "failed" in result_text.lower():
            report = SessionHistory.build_failed_report(
                self._state.instruction,
                self._state.iterations,
                error=result_text,
            )
            memory = self._read_memory_content()
            self._session_history.add_task(
                instruction=self._state.instruction,
                status="failed",
                report=report,
                memory=memory,
                steps=len(self._state.iterations),
            )
            self._clear_memory_txt()
        else:
            self._session_history.add_task(
                instruction=self._state.instruction,
                status="completed",
                report=result_text,
                memory="",
                steps=len(self._state.iterations),
            )
            self._clear_memory_txt()
        self._state.iterations = []

        final_result = str(result or "").strip() or "Task execution ended"
        if final_result == "Task interrupted by user":
            self._host.append_log(f"[INFO] {t('task_stopped')}\n", "warning")
        else:
            self._host.append_log(f"[READY] {t('task_completed')}: {final_result}\n", "success")
        self._host.disable_screenshot_protection()
        if self._state.pending_voice_task_text:
            self._runtime_state_presenter.apply_runtime_state("ready", t("agent_ready"))
            self._finalize_current_worker()
            QTimer.singleShot(0, self.start_pending_voice_task)
            return
        if self._host.is_waiting_for_tts():
            self._host.show_finished_state(
                final_result,
                status_text=t("broadcasting"),
                tts_playing=True,
            )
            self._runtime_state_presenter.apply_runtime_state("ready", t("agent_ready"))
            self._host.start_tts_waiting()
        else:
            self._host.set_tts_done_event(None)
            self._runtime_state_presenter.apply_runtime_state("ready", t("agent_ready"))
            self._host.show_history_if_idle()
            self._host.clear_voice_session_language()
        self._finalize_current_worker()
        self._host.sync_voice_interaction_state()

    def handle_worker_error(self, error: str) -> None:
        self._state.first_startup_wait_hint_active = False
        normalized = error.strip() or t("unknown_error")
        if self._state.instruction:
            report = SessionHistory.build_failed_report(
                self._state.instruction,
                self._state.iterations,
                error=normalized,
            )
            memory = self._read_memory_content()
            self._session_history.add_task(
                instruction=self._state.instruction,
                status="failed",
                report=report,
                memory=memory,
                steps=len(self._state.iterations),
            )
            self._clear_memory_txt()
            self._state.iterations = []
        self._runtime_state_presenter.apply_runtime_state("error", t("agent_error"))
        self._host.disable_screenshot_protection()
        self._host.append_log(f"{normalized}\n", "error")
        if self._state.pending_voice_task_text:
            self._runtime_state_presenter.apply_runtime_state("ready", t("agent_ready"))
            self._finalize_current_worker()
            QTimer.singleShot(0, self.start_pending_voice_task)
            return
        announced = self._host.announce_report(normalized)
        self._host.show_finished_state(
            normalized,
            status_text=t("execution_failed") + (" 🔊" if announced is not None else ""),
            tts_playing=announced is not None,
        )
        if announced is not None:
            self._host.set_tts_done_event(announced)
            self._host.start_tts_waiting()
        else:
            self._host.set_tts_done_event(None)
            self._host.show_history_if_idle()
            self._host.clear_voice_session_language()
        self._finalize_current_worker()
        self._host.sync_voice_interaction_state()

    def dismiss_first_startup_wait_hint(self) -> None:
        if not self._state.first_startup_wait_hint_active:
            return
        self._state.first_startup_wait_hint_active = False
        self._host.update_status_hint("")

    def shutdown_workers(self) -> None:
        if self._ai_thread is not None and self._ai_thread.isRunning():
            self._ai_thread.stop()
            if not self._ai_thread.wait(1500):
                self._ai_thread.terminate()
                self._ai_thread.wait()

        for worker in list(self._retained_workers):
            if worker.isRunning():
                worker.terminate()
                worker.wait()

    def _build_iteration_log(self, iteration_index: int, payload: Dict[str, Any]) -> str:
        prefix = t("iteration_log_prefix", n=iteration_index + 1)
        status = str(payload.get("status") or "").strip()
        tool_name = str(payload.get("tool_name") or "").strip()
        if tool_name:
            action_result = str(payload.get("action_result") or "").strip()
            return f"{prefix}{tool_name} -> {action_result or t('tool_executed')}\n"
        if status == "page_loading":
            return f"{prefix}{t('page_loading')}\n"
        if status == "respond":
            return f"{prefix}{t('completed_arrow')} {str(payload.get('action_result') or '').strip()}\n"
        return f"{prefix}{str(payload.get('thinking') or '').strip()}\n"

    def _read_memory_content(self) -> str:
        return self._task_memory_store.read()

    def _clear_memory_txt(self) -> None:
        self._task_memory_store.clear()

    def _finalize_current_worker(self) -> None:
        current_worker = self._ai_thread
        if current_worker is not None and current_worker not in self._retained_workers:
            self._retained_workers.append(current_worker)
        self._ai_thread = None
        self._state.active_stream_iteration = None
        self._state.first_startup_wait_hint_active = False
        QTimer.singleShot(1000, self._prune_retained_workers)

    def _prune_retained_workers(self) -> None:
        self._retained_workers = [worker for worker in self._retained_workers if worker.isRunning()]

    @staticmethod
    def _source_label(source: str) -> str:
        if source == "voice":
            return "语音"
        if source == "companion":
            return "伴随推荐"
        return "输入"
