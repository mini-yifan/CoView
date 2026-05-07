"""Background activity/timer orchestration for floating UI."""

from __future__ import annotations


class FloatingBackgroundActivityCoordinator:
    def __init__(self, controller) -> None:
        self._controller = controller

    def should_observe_frontmost(self) -> bool:
        return self._controller.is_companion_enabled()

    def background_jobs_active(self) -> bool:
        try:
            jobs = self._controller._job_manager.get_memory_jobs()
        except Exception:
            jobs = []
        if jobs:
            return True
        return bool(getattr(self._controller, "_job_windows", {}))

    def sync_timers(self) -> None:
        frontmost_timer = getattr(self._controller, "_frontmost_timer", None)
        job_poll_timer = getattr(self._controller, "_job_poll_timer", None)
        if frontmost_timer is None or job_poll_timer is None:
            return

        if self.should_observe_frontmost():
            if frontmost_timer.interval() != 700:
                frontmost_timer.setInterval(700)
            if not frontmost_timer.isActive():
                frontmost_timer.start()
        else:
            frontmost_timer.stop()

        target_interval = 500 if self.background_jobs_active() else 1500
        if job_poll_timer.interval() != target_interval:
            job_poll_timer.setInterval(target_interval)
        if not job_poll_timer.isActive():
            job_poll_timer.start()

    def observe_frontmost_app(self) -> None:
        if not self.should_observe_frontmost():
            self._controller._frontmost_timer.stop()
            return
        if self._controller.is_interaction_busy():
            return
        try:
            self._controller._frontmost_tracker.observe_current_frontmost()
            window_info = {}
            getter = getattr(self._controller._platform_adapter, "get_frontmost_window_info", None)
            if callable(getter):
                try:
                    window_info = getter() or {}
                except Exception:
                    window_info = {}
            companion = getattr(self._controller, "_companion", None)
            observe = getattr(companion, "observe_frontmost", None)
            if callable(observe):
                observe(window_info)
        except Exception as exc:
            self._controller._log_buffer.append_log(f"[WARNING] 更新前台应用失败: {exc}\n", "warning")

    def poll_background_jobs(self) -> None:
        self._controller._background_jobs.poll()
        self.sync_timers()
