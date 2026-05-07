"""Voice interaction coordinator for the floating overlay."""

from __future__ import annotations

import difflib
import re
import threading
import time
from typing import Optional, Protocol

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from baodou_ai.core.config import Config
from baodou_ai.gui.runtime_log import RuntimeLogBuffer
from baodou_ai.voice.intent_classifier import VoiceIntentClassifier, VoiceIntentContext
from baodou_ai.voice.qwen_asr import QwenRealtimeAsrClient, QwenRealtimeAsrSettings


class VoiceInteractionController(QObject):
    """Owns microphone/ASR lifecycle and routes voice events to FloatingController."""

    _IDLE_DISMISS_COMMANDS = ("退下吧",)
    _IDLE_DISMISS_COMMANDS_EN: tuple[str, ...] = ()
    _PRIORITY_EXIT_COMMAND_CN = "退出程序"
    _PRIORITY_EXIT_BLOCKED_COMMANDS_CN = (
        "不要退出程序",
        "别退出程序",
        "不退出程序",
        "先不要退出程序",
        "暂时不要退出程序",
        "怎么退出程序",
    )
    _PRIORITY_EXIT_COMMANDS_EN = (
        "close program",
        "close the program",
        "exit program",
        "exit the program",
        "quit program",
        "quit the program",
        "close app",
        "close the app",
        "exit app",
        "exit the app",
        "quit app",
        "quit the app",
    )
    _PRIORITY_EXIT_BLOCKED_COMMANDS_EN = (
        "do not close program",
        "do not close the program",
        "don't close program",
        "don't close the program",
        "not close program",
        "not close the program",
        "do not exit program",
        "do not exit the program",
        "don't exit program",
        "don't exit the program",
        "not exit program",
        "not exit the program",
        "do not quit program",
        "do not quit the program",
        "don't quit program",
        "don't quit the program",
        "not quit program",
        "not quit the program",
        "do not close app",
        "do not close the app",
        "don't close app",
        "don't close the app",
        "do not exit app",
        "do not exit the app",
        "don't exit app",
        "don't exit the app",
        "do not quit app",
        "do not quit the app",
        "don't quit app",
        "don't quit the app",
        "how to close program",
        "how to close the program",
        "how do i close program",
        "how do i close the program",
        "how to exit program",
        "how to exit the program",
        "how do i exit program",
        "how do i exit the program",
        "how to quit program",
        "how to quit the program",
        "how do i quit program",
        "how do i quit the program",
        "how to close app",
        "how to close the app",
        "how do i close app",
        "how do i close the app",
        "how to exit app",
        "how to exit the app",
        "how do i exit app",
        "how do i exit the app",
        "how to quit app",
        "how to quit the app",
        "how do i quit app",
        "how do i quit the app",
    )
    _DISMISS_NORMALIZE_TRANSLATION = str.maketrans("", "", " \t\r\n，。！？!?、,.；;：:")
    _TRANSCRIPT_SCREENING_TRANSLATION = str.maketrans(
        "",
        "",
        " \t\r\n，。！？!?、,.；;：:\"'“”‘’()（）[]【】<>《》-—_~…·`/\\|",
    )
    _GARBAGE_TRANSCRIPTS = {
        "嗯",
        "啊",
        "额",
        "呃",
        "哦",
        "唉",
        "诶",
        "欸",
        "哎",
        "哼",
        "哈",
        "嗯嗯",
        "啊啊",
        "额额",
        "哦哦",
        "呃呃",
        "哼哼",
        "哈哈",
        "嘿",
        "嘿嘿",
        "好的",
        "好吧",
        "行吧",
        "可以",
        "收到",
        "明白",
        "知道了",
        "谢谢",
        "谢了",
    }
    _IDLE_SHORT_COMMANDS = {
        "打开",
        "关闭",
        "退出",
        "停止",
        "继续",
        "返回",
        "刷新",
        "搜索",
        "发送",
        "复制",
        "粘贴",
        "截图",
        "开始",
        "暂停",
        "继续",
    }

    transcript_received = pyqtSignal(str)
    level_received = pyqtSignal(float, bool)
    state_received = pyqtSignal(str, str)
    intent_received = pyqtSignal(str, str)

    def __init__(self, delegate: "VoiceInteractionDelegate", config: Config, log_buffer: RuntimeLogBuffer) -> None:
        super().__init__()
        self._delegate = delegate
        self._config = config
        self._log_buffer = log_buffer
        self._asr: Optional[QwenRealtimeAsrClient] = None
        self._classifier = VoiceIntentClassifier(config)
        self._running = False
        self._processing_count = 0
        self._last_interaction_at = time.monotonic()
        self._latest_state = "off"
        self._latest_level = 0.0
        self._latest_speaking = False
        self._last_level_indicator_at = 0.0
        self._min_level_indicator_interval = 0.12

        self.transcript_received.connect(self._handle_transcript)
        self.level_received.connect(self._handle_level)
        self.state_received.connect(self._handle_state)
        self.intent_received.connect(self._handle_intent)

        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(1000)
        self._idle_timer.timeout.connect(self._check_idle_timeout)

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        voice_config = self._config.voice_interaction_config
        if not bool(voice_config.get("enabled", True)):
            self._apply_voice_state("off", 0.0, "")
            return
        if self._running:
            return

        provider = str(voice_config.get("asr_provider", "qwen") or "qwen").strip().lower()
        if provider != "qwen":
            self._handle_error(f"不支持的语音识别 provider: {provider}")
            return

        self._last_interaction_at = time.monotonic()
        settings = QwenRealtimeAsrSettings.from_config(self._config)
        self._asr = QwenRealtimeAsrClient(
            settings,
            on_transcript=lambda text: self.transcript_received.emit(text),
            on_level=lambda rms, speaking: self.level_received.emit(float(rms), bool(speaking)),
            on_state=lambda state, message="": self.state_received.emit(str(state), str(message or "")),
            on_error=self._handle_error,
        )
        if self._asr.start():
            self._running = True
            self._idle_timer.start()
            self._apply_voice_state("listening", 0.0, "语音交互已开启")
            self._log("[VOICE] 语音交互已开启\n", "info")

    def stop(self) -> None:
        if not self._running and self._asr is None:
            if self._latest_state != "off" or self._latest_level != 0.0:
                self._apply_voice_state("off", 0.0, "")
            return
        self._idle_timer.stop()
        asr = self._asr
        self._asr = None
        if asr is not None:
            asr.stop()
        was_running = self._running
        self._running = False
        self._processing_count = 0
        self._apply_voice_state("off", 0.0, "")
        if was_running:
            self._log("[VOICE] 语音交互已关闭\n", "info")

    def shutdown(self) -> None:
        self.stop()

    def mark_user_interaction(self) -> None:
        self._last_interaction_at = time.monotonic()

    def _handle_transcript(self, text: str) -> None:
        if not self._running:
            return
        transcript = str(text or "").strip()
        min_len = int(self._config.get("voice_interaction_config.asr_min_text_length", 1) or 1)
        if len(transcript) < min_len:
            self._apply_voice_state("listening", self._latest_level, "")
            return
        if self._is_garbage_transcript(transcript):
            self._log(f"[VOICE] ignore garbage transcript: {transcript}\n", "info")
            self._apply_voice_state("listening", self._latest_level, "")
            return

        self.mark_user_interaction()
        self._log(f"[VOICE] ASR: {transcript}\n", "info")
        if self._can_handle_priority_exit_command() and self._matches_priority_exit_command(transcript):
            self._delegate.handle_voice_exit_command()
            return
        if self._can_handle_idle_dismiss_command() and self._is_idle_dismiss_command(transcript):
            self._delegate.handle_voice_dismiss_command()
            return
        if not self._delegate.is_task_active() and not self._delegate.is_waiting_for_tts():
            if not self._passes_idle_submit_gate(transcript):
                self._log(f"[VOICE] ignore idle transcript: {transcript}\n", "info")
                self._apply_voice_state("listening", self._latest_level, "")
                return
            self._delegate.submit_voice_task(transcript)
            self._apply_voice_state("listening", self._latest_level, "")
            return

        self._classify_async(transcript)

    def _can_handle_idle_dismiss_command(self) -> bool:
        try:
            return bool(self._delegate.can_handle_idle_dismiss())
        except Exception:
            return False

    def _can_handle_priority_exit_command(self) -> bool:
        try:
            return bool(self._delegate.can_handle_priority_exit_command())
        except Exception:
            return False

    @classmethod
    def _matches_priority_exit_command(cls, transcript: str) -> bool:
        normalized = str(transcript or "").translate(cls._DISMISS_NORMALIZE_TRANSLATION).strip().lower()
        if any(blocked in normalized for blocked in cls._PRIORITY_EXIT_BLOCKED_COMMANDS_CN):
            return False
        if cls._PRIORITY_EXIT_COMMAND_CN in normalized:
            return True

        english_phrase = " ".join(re.findall(r"[a-zA-Z]+", str(transcript or "").lower()))
        if any(blocked in english_phrase for blocked in cls._PRIORITY_EXIT_BLOCKED_COMMANDS_EN):
            return False
        return any(command in english_phrase for command in cls._PRIORITY_EXIT_COMMANDS_EN)

    def _is_idle_dismiss_command(self, transcript: str) -> bool:
        normalized = str(transcript or "").translate(self._DISMISS_NORMALIZE_TRANSLATION).strip().lower()
        commands = set(self._IDLE_DISMISS_COMMANDS)
        locale = str(self._config.get("locale_config.locale", "zh_CN") or "zh_CN").strip().lower()
        if locale.startswith("en"):
            commands.update(self._IDLE_DISMISS_COMMANDS_EN)
        normalized_commands = {
            str(command or "").translate(self._DISMISS_NORMALIZE_TRANSLATION).strip().lower()
            for command in commands
        }
        return any(command and command in normalized for command in normalized_commands)

    @classmethod
    def _normalize_transcript_for_screening(cls, transcript: str) -> str:
        return str(transcript or "").translate(cls._TRANSCRIPT_SCREENING_TRANSLATION).strip().lower()

    @classmethod
    def _is_garbage_transcript(cls, transcript: str) -> bool:
        normalized = cls._normalize_transcript_for_screening(transcript)
        if not normalized:
            return True
        if normalized in cls._GARBAGE_TRANSCRIPTS:
            return True
        if len(normalized) <= 3 and len(set(normalized)) == 1 and normalized in {"嗯", "啊", "额", "呃", "哦", "哼", "哈"}:
            return True
        return False

    def _passes_idle_submit_gate(self, transcript: str) -> bool:
        normalized = self._normalize_transcript_for_screening(transcript)
        if not normalized:
            return False
        if normalized in self._IDLE_SHORT_COMMANDS:
            return True
        min_len = int(self._config.get("voice_interaction_config.idle_submit_min_text_length", 3) or 3)
        return len(normalized) >= max(1, min_len)

    def _classify_async(self, transcript: str) -> None:
        if self._should_ignore_tts_echo(transcript):
            self.intent_received.emit("ignore", transcript)
            return

        self._processing_count += 1
        self._apply_voice_state("processing", self._latest_level, "正在判断语音意图")
        context = self._build_intent_context(transcript)

        def _run() -> None:
            intent = self._classifier.classify(context)
            self.intent_received.emit(intent, transcript)

        threading.Thread(target=_run, name="baodou-voice-intent", daemon=True).start()

    def _build_intent_context(self, transcript: str) -> VoiceIntentContext:
        task_active = bool(self._delegate.is_task_active())
        tts_playing = bool(self._delegate.is_waiting_for_tts())
        return VoiceIntentContext(
            transcript=transcript,
            agent_status=str(self._delegate.current_status_key()),
            current_task=str(self._delegate.current_task_text()),
            tts_playing=tts_playing,
            tts_text=self._delegate.current_tts_text(),
            interaction_phase=self._describe_interaction_phase(task_active, tts_playing),
        )

    @staticmethod
    def _describe_interaction_phase(task_active: bool, tts_playing: bool) -> str:
        if task_active:
            return "task_running"
        if tts_playing:
            # Final TTS playback is still interruptible and should preserve stop/new_task/ignore semantics.
            return "final_response_tts"
        return "idle"

    def _handle_intent(self, intent: str, transcript: str) -> None:
        if self._processing_count > 0:
            self._processing_count -= 1
        normalized = intent if intent in {"stop", "new_task", "ignore"} else "ignore"
        self._log(f"[VOICE] intent={normalized}: {transcript}\n", "info")
        if normalized == "stop":
            self._delegate.request_voice_stop()
        elif normalized == "new_task":
            self._delegate.request_voice_new_task(transcript)
        self._apply_voice_state("processing" if self._processing_count else "listening", self._latest_level, "")

    def _handle_level(self, rms: float, speaking: bool) -> None:
        previous_level = self._latest_level
        previous_speaking = self._latest_speaking
        self._latest_level = self._normalize_level(rms)
        self._latest_speaking = bool(speaking)
        now = time.monotonic()
        if (
            bool(speaking) == previous_speaking
            and
            now - float(self._last_level_indicator_at or 0.0) < self._min_level_indicator_interval
            and abs(self._latest_level - previous_level) < 0.08
        ):
            return
        self._last_level_indicator_at = now
        if self._processing_count > 0:
            self._apply_voice_state("processing", self._latest_level, "")
            return
        self._apply_voice_state("speaking" if speaking else "listening", self._latest_level, "")

    def _handle_state(self, state: str, message: str) -> None:
        if state in {"listening", "speaking"} and self._processing_count > 0:
            return
        self._apply_voice_state(state, self._latest_level, message)

    def _handle_error(self, message: str) -> None:
        normalized = str(message or "").strip()
        marker = "\n[ERROR_ENVELOPE] "
        user_message = normalized.split(marker, 1)[0] if marker in normalized else normalized
        self.state_received.emit("error", user_message)
        self._log(f"[VOICE] {normalized}\n", "warning")

    def _apply_voice_state(self, state: str, level: float, message: str) -> None:
        self._latest_state = state
        level = max(0.0, min(1.0, float(level or 0.0)))
        try:
            self._delegate.apply_voice_indicator(state, level)
        except Exception:
            pass
        if state == "error" and message:
            self._log(f"[VOICE] {message}\n", "warning")

    def _check_idle_timeout(self) -> None:
        if not self._running:
            return
        timeout = int(self._config.get("voice_interaction_config.idle_auto_unpin_seconds", 30) or 0)
        if timeout <= 0:
            return
        if self._delegate.is_task_active() or self._delegate.is_waiting_for_tts():
            self._last_interaction_at = time.monotonic()
            return
        if not self._delegate.can_handle_idle_dismiss():
            return
        if time.monotonic() - self._last_interaction_at >= timeout:
            self._delegate.handle_voice_idle_timeout()

    def _should_ignore_tts_echo(self, transcript: str) -> bool:
        if not bool(self._config.get("voice_interaction_config.ignore_tts_echo", True)):
            return False
        tts_text = str(self._delegate.current_tts_text() or "").strip()
        if not tts_text:
            return False
        ratio = difflib.SequenceMatcher(None, transcript.strip(), tts_text).ratio()
        return ratio >= 0.72

    @staticmethod
    def _normalize_level(rms: float) -> float:
        if rms <= 0:
            return 0.0
        return max(0.0, min(1.0, rms / 3500.0))

    def _log(self, text: str, level: str) -> None:
        try:
            self._log_buffer.append_log(text, level)
        except Exception:
            pass


class VoiceInteractionDelegate(Protocol):
    def is_task_active(self) -> bool:
        ...

    def is_waiting_for_tts(self) -> bool:
        ...

    def current_status_key(self) -> str:
        ...

    def current_task_text(self) -> str:
        ...

    def current_tts_text(self) -> str:
        ...

    def submit_voice_task(self, text: str) -> None:
        ...

    def request_voice_stop(self) -> None:
        ...

    def request_voice_new_task(self, text: str) -> None:
        ...

    def handle_voice_idle_timeout(self) -> None:
        ...

    def handle_voice_exit_command(self) -> None:
        ...

    def handle_voice_dismiss_command(self) -> None:
        ...

    def can_handle_idle_dismiss(self) -> bool:
        ...

    def can_handle_priority_exit_command(self) -> bool:
        ...

    def apply_voice_indicator(self, state: str, level: float) -> None:
        ...
