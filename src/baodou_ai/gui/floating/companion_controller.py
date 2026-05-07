"""Companion suggestions controller for the floating overlay."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from PyQt5.QtCore import QObject, QTimer

from baodou_ai.ai.companion_privacy import (
    PRIVACY_BLOCKED_POST_CAPTURE,
    PRIVACY_BLOCKED_PRE_CAPTURE,
    CompanionPrivacyGuard,
    CompanionPrivacyResult,
)
from baodou_ai.core.config import Config
from baodou_ai.core.screenshot import ScreenshotCapture
from baodou_ai.gui.floating.companion_capture_worker import CaptureRecommendWorker
from baodou_ai.gui.floating.companion_delegate import LegacyCompanionDelegate


@dataclass(frozen=True)
class _FrontContextSignature:
    pid: int
    identifier: str
    title: str

_CaptureRecommendWorker = CaptureRecommendWorker


class CompanionController(QObject):
    """State machine for companion recommendations (idle observing, suppressed, showing)."""

    def __init__(
        self,
        controller=None,
        *,
        delegate: Optional["CompanionDelegate"] = None,
        config: Optional[Config] = None,
        platform_adapter=None,
    ):
        super().__init__()
        self._delegate = delegate or LegacyCompanionDelegate(controller)
        self._config: Config = config or getattr(controller, "_config", Config())
        self._platform_adapter = platform_adapter if platform_adapter is not None else getattr(controller, "_platform_adapter", None)
        self._own_pid = int(
            getattr(controller, "app", None).applicationPid()
            if hasattr(getattr(controller, "app", None), "applicationPid")
            else 0
        )  # type: ignore
        try:
            import os

            self._own_pid = int(os.getpid())
        except Exception:
            pass

        self._capture = ScreenshotCapture(self._config)
        self._privacy_guard = CompanionPrivacyGuard(self._config)

        self._stable_timer = QTimer()
        self._stable_timer.setSingleShot(True)
        self._stable_timer.timeout.connect(self._on_stable_timeout)

        self._dismiss_timer = QTimer()
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide_suggestions)

        self._suppressed_until = 0.0
        self._switch_events: List[float] = []

        self._last_signature: Optional[_FrontContextSignature] = None
        self._pending_signature: Optional[_FrontContextSignature] = None
        self._pending_window_info: Dict[str, Any] = {}
        self._last_frame_hash: str = ""
        self._request_seq = 0
        self._request_signature: Optional[_FrontContextSignature] = None
        self._privacy_blocked_signature: Optional[_FrontContextSignature] = None
        self._active_worker: Optional[_CaptureRecommendWorker] = None
        self._retained_workers: List[_CaptureRecommendWorker] = []
        self._shutting_down = False
        self._capture_in_flight = False
        self._capture_start_pending = False
        self._capture_overlay_hidden = False
        self._last_capture_started_at = 0.0
        self._min_capture_interval_seconds = 8.0

        self._enabled = True
        self._suggestion_display_seconds = 30
        self._trigger_stable_delay_ms = 1200
        self._rapid_switch_window_seconds = 8
        self._rapid_switch_count_threshold = 4
        self._rapid_switch_cooldown_seconds = 20
        self.refresh_config()

    def refresh_config(self) -> None:
        cfg = getattr(self._config, "companion_config", {}) or {}
        self._enabled = bool(cfg.get("enabled", True))
        self._suggestion_display_seconds = int(cfg.get("suggestion_display_seconds", 30) or 30)
        self._trigger_stable_delay_ms = int(cfg.get("trigger_stable_delay_ms", 1200) or 1200)
        self._rapid_switch_window_seconds = int(cfg.get("rapid_switch_window_seconds", 8) or 8)
        self._rapid_switch_count_threshold = int(cfg.get("rapid_switch_count_threshold", 4) or 4)
        self._rapid_switch_cooldown_seconds = int(cfg.get("rapid_switch_cooldown_seconds", 20) or 20)
        self._privacy_guard.refresh_config()

    def shutdown(self) -> None:
        self._shutting_down = True
        self._stable_timer.stop()
        self._dismiss_timer.stop()
        self._request_seq += 1
        self._request_signature = None
        self._privacy_blocked_signature = None
        self._capture_in_flight = False
        self._capture_start_pending = False
        self._show_overlay_after_capture()
        self.hide_suggestions()
        workers = self._collect_workers()
        self._active_worker = None
        self._retained_workers = []
        for worker in workers:
            self._shutdown_worker(worker)

    def observe_frontmost(self, window_info: Dict[str, Any]) -> None:
        """Called periodically by FloatingController to observe current frontmost window."""
        self._pending_window_info = dict(window_info or {})

        if not self._should_enable_now():
            self._stable_timer.stop()
            self.hide_suggestions()
            return

        signature = self._build_signature(window_info)
        if signature is None:
            return

        if self._last_signature is None:
            self._last_signature = signature
            return

        if signature == self._last_signature:
            return

        # Context changed: apply rapid-switch suppression and schedule stable trigger.
        self._last_signature = signature
        self._record_switch_event()

        if self._is_suppressed():
            self.hide_suggestions()
            return

        self._pending_signature = signature
        self._stable_timer.stop()
        self._stable_timer.start(max(0, int(self._trigger_stable_delay_ms)))

    def hide_suggestions(self) -> None:
        self._dismiss_timer.stop()
        self._delegate.hide_suggestions()

    def reposition(self) -> None:
        self._delegate.reposition_suggestions()

    def pause_for_interaction(self) -> None:
        if self._pending_signature is None or not self._should_enable_now():
            self._stable_timer.stop()
            return
        self._reschedule_capture(1000)

    def _should_enable_now(self) -> bool:
        if not self._enabled:
            return False
        if not self._delegate.can_show_companion():
            return False
        if self._is_suppressed():
            return False
        return True

    def _is_suppressed(self) -> bool:
        return time.monotonic() < float(self._suppressed_until or 0.0)

    def _record_switch_event(self) -> None:
        now = time.monotonic()
        window_seconds = max(1, int(self._rapid_switch_window_seconds))
        threshold = max(1, int(self._rapid_switch_count_threshold))
        cooldown = max(0, int(self._rapid_switch_cooldown_seconds))

        self._switch_events.append(now)
        cutoff = now - float(window_seconds)
        self._switch_events = [t for t in self._switch_events if t >= cutoff]
        if len(self._switch_events) >= threshold:
            self._suppressed_until = now + float(cooldown)
            self._switch_events = []

    @staticmethod
    def _build_signature(window_info: Dict[str, Any]) -> Optional[_FrontContextSignature]:
        if not isinstance(window_info, dict):
            return None
        try:
            pid = int(window_info.get("pid") or 0)
        except Exception:
            pid = 0
        if pid <= 0:
            return None
        identifier = str(window_info.get("identifier") or window_info.get("bundle_id") or "").strip()
        title = str(window_info.get("title") or "").strip()
        return _FrontContextSignature(pid=pid, identifier=identifier, title=title)

    def _on_stable_timeout(self) -> None:
        if not self._should_enable_now():
            return
        if self._pending_signature is None:
            return
        if self._delegate.is_interaction_busy():
            self._reschedule_capture(1000)
            return
        if bool(getattr(self, "_capture_in_flight", False)) or bool(getattr(self, "_capture_start_pending", False)):
            return
        interval_remaining = self._capture_interval_remaining_ms()
        if interval_remaining > 0:
            self._reschedule_capture(interval_remaining)
            return

        current = None
        try:
            if self._platform_adapter is not None:
                getter = getattr(self._platform_adapter, "get_frontmost_window_info", None)
                if callable(getter):
                    current = getter()
        except Exception:
            current = None

        current_sig = self._build_signature(current or self._pending_window_info)
        if current_sig is None or current_sig != self._pending_signature:
            return

        if current_sig.pid == self._own_pid:
            return

        if (
            self._privacy_guard.is_cooling_down()
            and current_sig == self._privacy_blocked_signature
        ):
            self._reschedule_after_privacy_cooldown()
            return

        privacy = self._privacy_guard.review_pre_capture(current or self._pending_window_info)
        if not privacy.allowed:
            self._block_for_privacy(privacy, current_sig)
            return

        context_text = self._build_companion_context(current or self._pending_window_info)
        self._request_seq += 1
        self._request_signature = current_sig
        self._prune_retained_workers()
        self._retain_worker(self._active_worker)
        self._capture_start_pending = True

        self._hide_overlay_for_capture()
        QTimer.singleShot(
            50,
            lambda seq=self._request_seq, info=dict(current or self._pending_window_info), context=context_text: (
                self._start_capture_worker(seq, info, context)
            ),
        )

    def _reschedule_capture(self, delay_ms: int) -> None:
        self._stable_timer.stop()
        self._stable_timer.start(max(1, int(delay_ms)))

    def _capture_interval_remaining_ms(self) -> int:
        elapsed = time.monotonic() - float(getattr(self, "_last_capture_started_at", 0.0) or 0.0)
        remaining = float(getattr(self, "_min_capture_interval_seconds", 8.0) or 0.0) - elapsed
        return max(0, int(remaining * 1000))

    def _start_capture_worker(self, seq: int, window_info: Dict[str, Any], context_text: str) -> None:
        self._capture_start_pending = False
        if self._shutting_down or int(seq) != int(self._request_seq):
            self._show_overlay_after_capture()
            return
        if self._delegate.is_interaction_busy() or bool(getattr(self, "_capture_in_flight", False)):
            self._show_overlay_after_capture()
            self._reschedule_capture(1000)
            return

        self._capture_in_flight = True
        self._last_capture_started_at = time.monotonic()
        worker = _CaptureRecommendWorker(
            seq=seq,
            config=self._config,
            window_info=window_info,
            context_text=context_text,
            privacy_guard=self._privacy_guard,
        )
        worker.result_ready.connect(self._on_worker_finished)
        worker.capture_done.connect(self._on_worker_capture_done)
        worker.finished.connect(lambda worker=worker: self._on_worker_completed(worker))
        self._active_worker = worker
        worker.start()

    def _build_companion_context(self, window_info: Dict[str, Any]) -> str:
        app_name = str(window_info.get("app_name") or "").strip()
        title = str(window_info.get("title") or "").strip()
        identifier = str(window_info.get("identifier") or window_info.get("bundle_id") or "").strip()
        parts = ["请根据用户当前前台窗口内容，输出两条推荐操作。"]
        meta: List[str] = []
        if app_name:
            meta.append(f"app_name={app_name}")
        if identifier:
            meta.append(f"identifier={identifier}")
        if title:
            meta.append(f"title={title}")
        if meta:
            parts.append("[Frontmost Window]")
            parts.append(", ".join(meta))
        return "\n".join(parts).strip()

    def _on_worker_finished(self, seq: int, payload: object) -> None:
        self._capture_in_flight = False
        self._show_overlay_after_capture()
        if self._shutting_down:
            return
        if int(seq) != int(self._request_seq):
            return
        if not isinstance(payload, dict) or not payload.get("ok"):
            privacy = payload.get("privacy") if isinstance(payload, dict) else None
            if isinstance(privacy, CompanionPrivacyResult):
                self._block_for_privacy(privacy, self._request_signature)
            return
        frame_hash = str(payload.get("frame_hash") or "")
        if frame_hash and frame_hash == self._last_frame_hash:
            return
        self._last_frame_hash = frame_hash
        suggestions_obj = payload.get("suggestions")
        suggestions = suggestions_obj if isinstance(suggestions_obj, list) else []
        suggestions = [str(s or "").strip() for s in suggestions if str(s or "").strip()]
        if len(suggestions) < 2:
            return
        if not self._should_enable_now():
            return
        if self._request_signature is None:
            return
        if self._delegate.is_interaction_busy():
            return

        # Ensure context hasn't changed since the request was started.
        latest_info: Dict[str, Any] = {}
        try:
            if self._platform_adapter is not None:
                getter = getattr(self._platform_adapter, "get_frontmost_window_info", None)
                if callable(getter):
                    latest_info = getter() or {}
        except Exception:
            latest_info = {}
        latest_sig = self._build_signature(latest_info)
        if latest_sig is None or latest_sig != self._request_signature:
            return

        self._show_suggestions(suggestions[:2])

    def _on_worker_capture_done(self, seq: int) -> None:
        if int(seq) != int(self._request_seq):
            return
        self._show_overlay_after_capture()

    def _capture_frontmost_window(self, window_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        bounds = window_info.get("bounds")
        if not isinstance(bounds, dict):
            return None
        return self._capture.capture_window_region(
            bounds=bounds,
            optimize=True,
            include_data_url=False,
        )

    def _block_for_privacy(
        self,
        result: CompanionPrivacyResult,
        signature: Optional[_FrontContextSignature],
    ) -> None:
        if result.status not in {PRIVACY_BLOCKED_PRE_CAPTURE, PRIVACY_BLOCKED_POST_CAPTURE}:
            return
        self._request_signature = None
        self._privacy_blocked_signature = signature
        self._request_seq += 1
        self._privacy_guard.mark_blocked()
        self._show_privacy_notice()
        self._reschedule_after_privacy_cooldown()

    def _reschedule_after_privacy_cooldown(self) -> None:
        remaining_ms = self._privacy_guard.cooldown_remaining_ms()
        if remaining_ms <= 0:
            return
        self._stable_timer.stop()
        self._stable_timer.start(max(1, remaining_ms))

    def _show_privacy_notice(self) -> None:
        self._delegate.show_privacy_notice("当前窗口禁用智能推荐")

        self._dismiss_timer.stop()
        seconds = max(1, int(self._suggestion_display_seconds))
        self._dismiss_timer.start(seconds * 1000)

    def _hide_overlay_for_capture(self) -> None:
        self._capture_overlay_hidden = True
        self._delegate.enter_capture_mode()
        self._delegate.hide_suggestions()

    def _show_overlay_after_capture(self) -> None:
        try:
            overlay_hidden = bool(getattr(self, "_capture_overlay_hidden", False))
        except RuntimeError:
            overlay_hidden = False
        if not overlay_hidden:
            return
        self._capture_overlay_hidden = False
        self._delegate.exit_capture_mode()

    def _show_suggestions(self, suggestions: List[str]) -> None:
        self._delegate.show_suggestions(suggestions)

        # Reset dismiss timer.
        self._dismiss_timer.stop()
        seconds = max(1, int(self._suggestion_display_seconds))
        self._dismiss_timer.start(seconds * 1000)

    def _on_worker_completed(self, worker: _CaptureRecommendWorker) -> None:
        if self._active_worker is worker:
            self._active_worker = None
        self._retained_workers = [item for item in self._retained_workers if item is not worker]
        try:
            worker.deleteLater()
        except Exception:
            pass

    def _retain_worker(self, worker: Optional[_CaptureRecommendWorker]) -> None:
        if worker is None or not self._worker_is_running(worker):
            return
        if any(item is worker for item in self._retained_workers):
            return
        self._retained_workers.append(worker)

    def _prune_retained_workers(self) -> None:
        self._retained_workers = [
            worker for worker in self._retained_workers if self._worker_is_running(worker)
        ]

    def _collect_workers(self) -> List[_CaptureRecommendWorker]:
        workers: List[_CaptureRecommendWorker] = []
        for worker in [self._active_worker, *self._retained_workers]:
            if worker is None:
                continue
            if any(existing is worker for existing in workers):
                continue
            workers.append(worker)
        return workers

    @staticmethod
    def _worker_is_running(worker: Optional[_CaptureRecommendWorker]) -> bool:
        if worker is None:
            return False
        checker = getattr(worker, "isRunning", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                return False
        return False

    def _shutdown_worker(self, worker: _CaptureRecommendWorker) -> None:
        try:
            worker.result_ready.disconnect(self._on_worker_finished)
        except Exception:
            pass
        try:
            worker.capture_done.disconnect(self._on_worker_capture_done)
        except Exception:
            pass
        try:
            worker.requestInterruption()
        except Exception:
            pass
        try:
            worker.quit()
        except Exception:
            pass
        if self._worker_is_running(worker):
            try:
                if not worker.wait(3000):
                    worker.terminate()
                    worker.wait(1000)
            except Exception:
                pass
        try:
            worker.deleteLater()
        except Exception:
            pass


class CompanionDelegate(Protocol):
    def can_show_companion(self) -> bool:
        ...

    def hide_suggestions(self) -> None:
        ...

    def show_suggestions(self, suggestions: List[str]) -> None:
        ...

    def show_privacy_notice(self, text: str) -> None:
        ...

    def reposition_suggestions(self) -> None:
        ...

    def is_interaction_busy(self) -> bool:
        ...

    def enter_capture_mode(self) -> None:
        ...

    def exit_capture_mode(self) -> None:
        ...
