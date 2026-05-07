"""Delegates extracted from FloatingController."""

from __future__ import annotations

import time
from typing import List, Optional


class FloatingBackgroundJobsDelegate:
    def __init__(self, controller) -> None:
        self._controller = controller

    def is_busy(self) -> bool:
        return bool(self._controller._task_active() or self._controller._is_waiting_for_tts())

    def append_log(self, text: str, level: str) -> None:
        self._controller._log_buffer.append_log(text, level)

    def refresh_console_jobs(self) -> None:
        if self._controller._console_window is not None:
            self._controller._console_window.refresh_jobs()

    def add_history_task(self, **payload) -> None:
        self._controller._session_history.add_task(**payload)

    def display_background_report(self, text: str) -> None:
        normalized = str(text or "").strip()
        if not normalized:
            return
        if self._controller.is_edge_hidden:
            try:
                first_line = normalized.splitlines()[0].strip()
                if first_line:
                    self._controller.toast_window.show_message(self._controller.ball_anchor, first_line)
            except Exception:
                pass
            return
        if not self._controller.panel_window.target_visible:
            self._controller.panel_window.show_expanding(
                self._controller.ball_anchor,
                focus_input_on_finish=False,
                animate=True,
            )
        try:
            self._controller.panel_window.append_background_report(normalized)
        except Exception:
            pass
        self._controller.keep_ball_on_top()

    def announce_report(self, text: str):
        self._controller._tts.stop()
        announced = self._controller._on_report(text)
        if announced is not None:
            self._controller._tts.current_done_event = announced
            self._controller._tts.start_waiting()
        return announced


class FloatingCompanionDelegate:
    def __init__(self, controller) -> None:
        self._controller = controller

    def can_show_companion(self) -> bool:
        return bool(
            not self._controller.is_edge_hidden
            and not self._controller._task_active()
            and not self._controller._is_waiting_for_tts()
        )

    def hide_suggestions(self) -> None:
        try:
            self._controller.suggestion_window.hide_suggestions()
        except Exception:
            pass

    def show_suggestions(self, suggestions: List[str]) -> None:
        try:
            self._controller.suggestion_window.show_suggestions(self._controller.ball_anchor, suggestions)
        except Exception:
            pass

    def show_privacy_notice(self, text: str) -> None:
        try:
            self._controller.suggestion_window.show_privacy_notice(self._controller.ball_anchor, text)
        except Exception:
            pass

    def reposition_suggestions(self) -> None:
        try:
            self._controller.suggestion_window.reposition(self._controller.ball_anchor)
        except Exception:
            pass

    def is_interaction_busy(self) -> bool:
        return self._controller.is_interaction_busy()

    def enter_capture_mode(self) -> None:
        for window in self._controller._managed_windows():
            if hasattr(window, "enter_transparent_mode"):
                window.enter_transparent_mode()

    def exit_capture_mode(self) -> None:
        for window in self._controller._managed_windows():
            if hasattr(window, "exit_transparent_mode"):
                window.exit_transparent_mode()


class FloatingVoiceRuntimeCoordinator:
    def __init__(self, controller) -> None:
        self._controller = controller

    def mark_user_interaction(self) -> None:
        voice = getattr(self._controller, "_voice", None)
        if voice is not None:
            voice.mark_user_interaction()

    def sync_voice_interaction_state(self) -> None:
        voice = getattr(self._controller, "_voice", None)
        wake_word = getattr(self._controller, "_wake_word", None)

        should_run_voice = bool(self._controller.is_pinned and self._controller.panel_window.target_visible)
        if voice is not None and should_run_voice:
            if not bool(getattr(voice, "running", False)):
                voice.start()
        elif voice is not None and bool(getattr(voice, "running", False)):
            voice.stop()

        if wake_word is None:
            return
        if self.should_run_wake_word(should_run_voice):
            wake_state = str(getattr(wake_word, "state", "") or "")
            if not bool(getattr(wake_word, "running", False)) and wake_state != "degraded":
                wake_word.start()
            return
        wake_word.stop()

    def should_run_wake_word(self, should_run_voice: Optional[bool] = None) -> bool:
        if should_run_voice is None:
            should_run_voice = bool(self._controller.is_pinned and self._controller.panel_window.target_visible)
        if should_run_voice:
            return False
        if self._controller.is_pinned or self._controller._task_active() or self._controller._is_waiting_for_tts():
            return False
        if not bool(self._controller._config.get("voice_interaction_config.enabled", True)):
            return False
        return bool(self._controller._config.get("wake_word_config.enabled", True))

    def handle_wake_word_hit(self, hit) -> None:
        if self._controller.is_pinned or self._controller._task_active() or self._controller._is_waiting_for_tts():
            return
        self._controller._set_active_wake_word_language(getattr(hit, "language", ""))
        self._controller.activate_from_hotkey()
        self._announce_wake_word_ack()
        self.sync_voice_interaction_state()

    def handle_wake_word_state_change(self, status) -> None:
        if getattr(self._controller._voice, "running", False):
            return
        if not bool(self._controller._config.get("wake_word_config.show_indicator", True)):
            self.apply_voice_indicator("off", 0.0)
            return
        self.apply_voice_indicator(*self.wake_word_indicator_payload(status))
        self._show_wake_word_feedback(status)

    def apply_voice_indicator(self, state: str, level: float) -> None:
        override = getattr(getattr(self._controller, "__dict__", {}), "get", lambda *_: None)("apply_voice_indicator")
        if callable(override):
            override(state, level)
            return
        normalized_state = str(state or "off")
        normalized_level = max(0.0, min(1.0, float(level or 0.0)))
        previous_state = str(getattr(self._controller, "_last_voice_indicator_state", "") or "")
        previous_level = float(getattr(self._controller, "_last_voice_indicator_level", -1.0) or -1.0)
        previous_at = float(getattr(self._controller, "_last_voice_indicator_at", 0.0) or 0.0)
        now = time.monotonic()
        if (
            normalized_state == previous_state
            and abs(normalized_level - previous_level) < 0.04
            and now - previous_at < 0.12
        ):
            return
        self._controller._last_voice_indicator_state = normalized_state
        self._controller._last_voice_indicator_level = normalized_level
        self._controller._last_voice_indicator_at = now
        panel_window = getattr(self._controller, "panel_window", None)
        if panel_window is not None:
            panel_window.set_voice_indicator(normalized_state, normalized_level)
        ball_window = getattr(self._controller, "ball_window", None)
        if ball_window is not None:
            ball_window.set_voice_indicator(normalized_state, normalized_level)

    def wake_word_indicator_payload(self, status) -> tuple[str, float]:
        state = str(getattr(status, "state", "") or "")
        if state == "degraded":
            return ("wake_error", 0.0)
        if state == "triggered":
            return ("wake_triggered", 1.0)
        if state == "cooldown":
            return ("wake_cooldown", 0.0)
        if state == "listening":
            return ("wake_listening", 0.0)
        return ("off", 0.0)

    def _announce_wake_word_ack(self) -> None:
        tts = getattr(self._controller, "_tts", None)
        if tts is None:
            return
        ack_text = self._controller._current_wake_word_ack_text()
        self._controller._wake_word_ack_text = ack_text
        announced = tts.speak(ack_text)
        if announced is None:
            return
        self._controller._wake_word_ack_done_event = announced
        self._controller._queue_wake_word_ack_finalize(announced)

    def finalize_wake_word_ack(self, announced) -> None:
        if getattr(self._controller, "_wake_word_ack_done_event", None) is not announced:
            return
        if not announced.is_set():
            self._controller._queue_wake_word_ack_finalize(announced)
            return
        tts = getattr(self._controller, "_tts", None)
        if tts is not None and getattr(tts, "current_done_event", None) is announced:
            tts.current_done_event = None
            if str(getattr(tts, "current_text", "") or "").strip() == str(
                getattr(self._controller, "_wake_word_ack_text", "") or ""
            ).strip():
                tts.current_text = ""
        self._controller._wake_word_ack_done_event = None

    def _show_wake_word_feedback(self, status) -> None:
        state = str(getattr(status, "state", "") or "")
        if state in {"stopped", "disabled", ""}:
            self._controller._last_wake_word_feedback_state = state
            return
        if state == getattr(self._controller, "_last_wake_word_feedback_state", None):
            return
        self._controller._last_wake_word_feedback_state = state
        text = self.wake_word_feedback_text(status)
        if not text:
            return
        try:
            self._controller.toast_window.show_message(self._controller.ball_anchor, text)
        except Exception:
            pass

    def wake_word_feedback_text(self, status) -> str:
        state = str(getattr(status, "state", "") or "")
        if state == "listening":
            phrases = self.wake_word_phrase_summary()
            return f"待唤醒: {phrases}" if phrases else "待唤醒"
        if state == "triggered":
            return "已唤醒，请继续说"
        if state == "cooldown":
            return "冷却中，请稍后再试"
        if state == "degraded":
            return "本地唤醒已降级"
        return ""

    def wake_word_phrase_summary(self) -> str:
        phrases: List[str] = []
        getter = getattr(self._controller._config, "get_wake_word_phrase", None)
        if callable(getter):
            for language in ("zh", "en"):
                phrase = str(getter(language) or "").strip()
                if phrase and phrase not in phrases:
                    phrases.append(phrase)
        if not phrases:
            raw_phrases = self._controller._config.get("wake_word_config.phrases", []) or []
            for item in raw_phrases:
                if not isinstance(item, dict):
                    continue
                phrase = str(item.get("text") or "").strip()
                if phrase and phrase not in phrases:
                    phrases.append(phrase)
        return " / ".join(phrases)
