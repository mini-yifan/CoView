"""TTS state controller for the floating overlay."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Optional

from PyQt5.QtCore import QTimer

from baodou_ai.core.config import Config
from baodou_ai.gui.i18n import translate
from baodou_ai.tts.cosyvoice import CosyVoiceTTS


class TTSController:
    def __init__(self, config: Config, on_finished) -> None:
        self._config = config
        self.client = CosyVoiceTTS(config)
        self.current_done_event: Optional[threading.Event] = None
        self.current_text = ""
        self._history: Deque[tuple[str, float, Optional[float]]] = deque()
        self._current_history_index: Optional[int] = None
        self._last_finished_at = 0.0
        self.wait_timer = QTimer()
        self.wait_timer.setInterval(200)
        self.wait_timer.timeout.connect(on_finished)

    def speak(self, text: str):
        self.current_text = str(text or "").strip()
        if self.client.available:
            self._record_history_start(self.current_text)
            self.current_done_event = self.client.speak(text)
            return self.current_done_event
        self.current_text = ""
        return None

    def is_waiting(self) -> bool:
        return self.current_done_event is not None and not self.current_done_event.is_set()

    def stop(self) -> None:
        self.client.stop()
        self._record_history_end()
        self.current_done_event = None
        self.current_text = ""
        self.wait_timer.stop()

    def start_waiting(self) -> None:
        self.wait_timer.start()

    def finish_waiting(self) -> None:
        self.wait_timer.stop()
        self._record_history_end()
        self.current_done_event = None
        self.current_text = ""

    def shutdown(self) -> None:
        self.stop()

    def recent_texts(self, window_seconds: float) -> tuple[str, ...]:
        self._prune_history()
        now = time.monotonic()
        window = max(0.0, float(window_seconds or 0.0))
        texts: list[str] = []
        for text, started_at, finished_at in self._history:
            if not text:
                continue
            reference_at = finished_at if finished_at is not None else started_at
            if window <= 0 or now - float(reference_at or 0.0) <= window:
                texts.append(text)
        return tuple(texts)

    def is_in_echo_guard(self, guard_seconds: float) -> bool:
        guard = max(0.0, float(guard_seconds or 0.0))
        if guard <= 0 or self._last_finished_at <= 0:
            return False
        return time.monotonic() - self._last_finished_at <= guard

    def _record_history_start(self, text: str) -> None:
        normalized = str(text or "").strip()
        if not normalized:
            self._current_history_index = None
            return
        if self._current_history_index is not None:
            self._record_history_end()
        self._prune_history()
        self._history.append((normalized, time.monotonic(), None))
        self._current_history_index = len(self._history) - 1

    def _record_history_end(self) -> None:
        if self._current_history_index is None:
            return
        now = time.monotonic()
        try:
            text, started_at, finished_at = self._history[self._current_history_index]
            if finished_at is None:
                self._history[self._current_history_index] = (text, started_at, now)
                self._last_finished_at = now
        except IndexError:
            pass
        self._current_history_index = None
        self._prune_history()

    def _prune_history(self) -> None:
        window = float(
            self._config.get("voice_interaction_config.tts_echo_history_seconds", 20) or 20
        )
        cutoff = time.monotonic() - max(1.0, window)
        while self._history:
            _, started_at, finished_at = self._history[0]
            if finished_at is None:
                break
            reference_at = finished_at if finished_at is not None else started_at
            if reference_at >= cutoff:
                break
            self._history.popleft()
            if self._current_history_index is not None:
                self._current_history_index = max(0, self._current_history_index - 1)

    @staticmethod
    def localize_text(text: str, locale: str) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""
        localized_stop_texts = {
            translate("zh_CN", "voice_input_stop_spoken_text_default"): {
                "zh_CN": translate("zh_CN", "voice_input_stop_spoken_text_default"),
                "en_US": translate("en_US", "voice_input_stop_spoken_text_default"),
            },
            translate("en_US", "voice_input_stop_spoken_text_default"): {
                "zh_CN": translate("zh_CN", "voice_input_stop_spoken_text_default"),
                "en_US": translate("en_US", "voice_input_stop_spoken_text_default"),
            },
        }
        variants = localized_stop_texts.get(normalized)
        if variants:
            return variants.get(str(locale or "").strip(), normalized)
        return normalized
