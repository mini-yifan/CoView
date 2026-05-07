"""TTS state controller for the floating overlay."""

from __future__ import annotations

import threading
from typing import Optional

from PyQt5.QtCore import QTimer

from baodou_ai.core.config import Config
from baodou_ai.gui.i18n import translate
from baodou_ai.tts.cosyvoice import CosyVoiceTTS


class TTSController:
    def __init__(self, config: Config, on_finished) -> None:
        self.client = CosyVoiceTTS(config)
        self.current_done_event: Optional[threading.Event] = None
        self.current_text = ""
        self.wait_timer = QTimer()
        self.wait_timer.setInterval(200)
        self.wait_timer.timeout.connect(on_finished)

    def speak(self, text: str):
        self.current_text = str(text or "").strip()
        if self.client.available:
            self.current_done_event = self.client.speak(text)
            return self.current_done_event
        self.current_text = ""
        return None

    def is_waiting(self) -> bool:
        return self.current_done_event is not None and not self.current_done_event.is_set()

    def stop(self) -> None:
        self.client.stop()
        self.current_done_event = None
        self.current_text = ""
        self.wait_timer.stop()

    def start_waiting(self) -> None:
        self.wait_timer.start()

    def finish_waiting(self) -> None:
        self.wait_timer.stop()
        self.current_done_event = None
        self.current_text = ""

    def shutdown(self) -> None:
        self.stop()

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
