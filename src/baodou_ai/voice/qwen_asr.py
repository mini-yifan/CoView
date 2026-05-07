"""DashScope Qwen realtime ASR with local VAD boundaries."""

from __future__ import annotations

import base64
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

try:
    import certifi
    import os

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass

try:
    from dashscope.audio.qwen_omni import (
        MultiModality,
        OmniRealtimeCallback,
        OmniRealtimeConversation,
    )
    from dashscope.audio.qwen_omni.omni_realtime import TranscriptionParams

    _DASHSCOPE_AVAILABLE = True
except ImportError:
    MultiModality = None
    OmniRealtimeConversation = None
    TranscriptionParams = None

    class OmniRealtimeCallback:  # type: ignore[no-redef]
        pass

    _DASHSCOPE_AVAILABLE = False

try:
    import sounddevice as sd

    _SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    _SOUNDDEVICE_AVAILABLE = False

from baodou_ai.voice.local_vad import LocalVadConfig, LocalVadSegmenter
from baodou_ai.voice.echo_cancellation import (
    EchoCancellationConfig,
    EchoCancellationBridge,
    get_echo_cancellation_bridge,
)
from baodou_ai.core.error_envelope import (
    CODE_VOICE_INIT_FAILED,
    CODE_VOICE_RUNTIME_FAILED,
    KIND_DEPENDENCY_MISSING,
    KIND_EXECUTION_FAILED,
    SOURCE_VOICE,
    from_exception,
    from_message,
)


BEIJING_REALTIME_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"


@dataclass(frozen=True)
class QwenRealtimeAsrSettings:
    api_key: str = ""
    url: str = BEIJING_REALTIME_URL
    model: str = "qwen3-asr-flash-realtime"
    language: str = "zh"
    sample_rate: int = 16000
    block_frames: int = 1600
    device: Optional[int] = None
    energy_threshold: float = 900.0
    vad_min_speech_ms: int = 200
    vad_end_silence_ms: int = 1200
    vad_pre_roll_ms: int = 500
    vad_max_utterance_ms: int = 20000
    echo_cancellation_enabled: bool = True
    echo_cancellation_frame_ms: int = 10
    echo_cancellation_stream_delay_ms: int = 80
    echo_cancellation_ns: bool = True
    echo_cancellation_agc: bool = False
    adaptive_threshold_enabled: bool = True
    adaptive_min_energy_threshold: float = 300.0
    adaptive_noise_multiplier: float = 1.8
    adaptive_noise_offset: float = 80.0
    adaptive_noise_alpha: float = 0.08

    @classmethod
    def from_config(cls, config) -> "QwenRealtimeAsrSettings":
        voice_config = config.voice_interaction_config
        return cls(
            api_key=str(voice_config.get("asr_api_key", "") or ""),
            url=str(voice_config.get("asr_url", BEIJING_REALTIME_URL) or BEIJING_REALTIME_URL),
            model=str(voice_config.get("asr_model", "qwen3-asr-flash-realtime") or "qwen3-asr-flash-realtime"),
            language=str(voice_config.get("asr_language", "zh") or "zh"),
            sample_rate=int(voice_config.get("sample_rate", 16000) or 16000),
            block_frames=int(voice_config.get("block_frames", 1600) or 1600),
            energy_threshold=float(voice_config.get("energy_threshold", 900.0) or 900.0),
            adaptive_threshold_enabled=bool(voice_config.get("adaptive_threshold_enabled", True)),
            adaptive_min_energy_threshold=float(
                voice_config.get("adaptive_min_energy_threshold", 300.0) or 300.0
            ),
            adaptive_noise_multiplier=float(
                voice_config.get("adaptive_noise_multiplier", 1.8) or 1.8
            ),
            adaptive_noise_offset=float(voice_config.get("adaptive_noise_offset", 80.0) or 80.0),
            adaptive_noise_alpha=float(voice_config.get("adaptive_noise_alpha", 0.08) or 0.08),
            vad_min_speech_ms=int(voice_config.get("vad_min_speech_ms", 200) or 200),
            vad_end_silence_ms=int(voice_config.get("vad_end_silence_ms", 1200) or 1200),
            vad_pre_roll_ms=int(voice_config.get("vad_pre_roll_ms", 500) or 500),
            vad_max_utterance_ms=int(voice_config.get("vad_max_utterance_ms", 20000) or 20000),
            echo_cancellation_enabled=bool(voice_config.get("echo_cancellation_enabled", True)),
            echo_cancellation_frame_ms=int(voice_config.get("echo_cancellation_frame_ms", 10) or 10),
            echo_cancellation_stream_delay_ms=int(
                voice_config.get("echo_cancellation_stream_delay_ms", 80) or 80
            ),
            echo_cancellation_ns=bool(voice_config.get("echo_cancellation_ns", True)),
            echo_cancellation_agc=bool(voice_config.get("echo_cancellation_agc", False)),
        )

    def to_vad_config(self) -> LocalVadConfig:
        return LocalVadConfig(
            sample_rate=self.sample_rate,
            block_frames=self.block_frames,
            energy_threshold=self.energy_threshold,
            adaptive_threshold_enabled=self.adaptive_threshold_enabled,
            adaptive_min_energy_threshold=self.adaptive_min_energy_threshold,
            adaptive_noise_multiplier=self.adaptive_noise_multiplier,
            adaptive_noise_offset=self.adaptive_noise_offset,
            adaptive_noise_alpha=self.adaptive_noise_alpha,
            start_ms=self.vad_min_speech_ms,
            end_ms=self.vad_end_silence_ms,
            pre_roll_ms=self.vad_pre_roll_ms,
            max_utterance_ms=self.vad_max_utterance_ms,
        )

    def to_echo_cancellation_config(self) -> EchoCancellationConfig:
        return EchoCancellationConfig(
            enabled=self.echo_cancellation_enabled,
            sample_rate=self.sample_rate,
            frame_ms=self.echo_cancellation_frame_ms,
            stream_delay_ms=self.echo_cancellation_stream_delay_ms,
            enable_ns=self.echo_cancellation_ns,
            enable_agc=self.echo_cancellation_agc,
        )


class _QwenCallback(OmniRealtimeCallback):
    def __init__(self, client: "QwenRealtimeAsrClient") -> None:
        self.client = client

    def on_open(self) -> None:
        self.client._emit_state("listening", "ASR connection opened")

    def on_close(self, code, msg) -> None:
        self.client._emit_error(f"ASR connection closed: code={code}, msg={msg}")
        self.client._stop_event.set()

    def on_event(self, response) -> None:
        self.client.handle_event(response)


class QwenRealtimeAsrClient:
    """Non-blocking realtime ASR client. UI callers receive callbacks from worker threads."""

    def __init__(
        self,
        settings: QwenRealtimeAsrSettings,
        *,
        on_transcript: Callable[[str], None],
        on_level: Callable[[float, bool], None],
        on_state: Callable[[str, str], None],
        on_error: Callable[[str], None],
        conversation_factory=None,
        input_stream_factory=None,
        echo_cancellation_bridge: Optional[EchoCancellationBridge] = None,
    ) -> None:
        self.settings = settings
        self.on_transcript = on_transcript
        self.on_level = on_level
        self.on_state = on_state
        self.on_error = on_error
        self._conversation_factory = conversation_factory
        self._input_stream_factory = input_stream_factory
        self._stop_event = threading.Event()
        self._audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=64)
        self._thread: Optional[threading.Thread] = None
        self._processing_thread: Optional[threading.Thread] = None
        self._conversation = None
        self._vad = LocalVadSegmenter(settings.to_vad_config())
        self._echo_bridge = echo_cancellation_bridge or get_echo_cancellation_bridge()
        self._echo_cancellation_available = False

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.running:
            return True
        if not self._dependencies_available():
            envelope = from_message(
                source=SOURCE_VOICE,
                kind=KIND_DEPENDENCY_MISSING,
                user_message="语音识别依赖不可用，请安装 voice 依赖",
                dev_detail="dashscope 或 sounddevice 不可用",
                code=CODE_VOICE_INIT_FAILED,
                retryable=False,
            )
            self._emit_error("语音识别依赖不可用，请安装 voice 依赖", envelope=envelope.to_dict())
            return False
        if not self.settings.api_key and self._conversation_factory is None:
            envelope = from_message(
                source=SOURCE_VOICE,
                kind=KIND_EXECUTION_FAILED,
                user_message="语音识别 API Key 未配置",
                dev_detail="缺少 asr_api_key 配置",
                code=CODE_VOICE_INIT_FAILED,
                retryable=False,
            )
            self._emit_error("语音识别 API Key 未配置", envelope=envelope.to_dict())
            return False

        self._stop_event.clear()
        self._vad.reset()
        self._configure_echo_cancellation()
        self._thread = threading.Thread(target=self._run, name="baodou-qwen-asr", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._processing_thread = None
        self._conversation = None

    def _dependencies_available(self) -> bool:
        if self._conversation_factory is not None and self._input_stream_factory is not None:
            return True
        return _DASHSCOPE_AVAILABLE and _SOUNDDEVICE_AVAILABLE

    def _run(self) -> None:
        try:
            callback = _QwenCallback(self)
            self._conversation = self._create_conversation(callback)
            self._conversation.connect()
            self._update_session()
            self._processing_thread = threading.Thread(
                target=self._processing_loop,
                name="baodou-qwen-asr-processing",
                daemon=True,
            )
            self._processing_thread.start()
            self._emit_state("listening", "语音识别已启动")
            with self._create_input_stream():
                while not self._stop_event.is_set():
                    time.sleep(0.1)
        except Exception as exc:
            envelope = from_exception(
                exc,
                source=SOURCE_VOICE,
                kind=KIND_EXECUTION_FAILED,
                user_message="语音识别启动失败",
                code=CODE_VOICE_INIT_FAILED,
                retryable=True,
            )
            self._emit_error(f"语音识别启动失败: {exc}", envelope=envelope.to_dict())
        finally:
            self._stop_event.set()
            if self._processing_thread is not None and self._processing_thread.is_alive():
                self._processing_thread.join(timeout=1.0)
            self._close_conversation()

    def _create_conversation(self, callback):
        if self._conversation_factory is not None:
            return self._conversation_factory(self.settings, callback)
        return OmniRealtimeConversation(
            model=self.settings.model,
            callback=callback,
            api_key=self.settings.api_key,
            url=self.settings.url,
        )

    def _update_session(self) -> None:
        if self._conversation is None or not hasattr(self._conversation, "update_session"):
            return
        self._conversation.update_session(
            output_modalities=[MultiModality.TEXT],
            enable_input_audio_transcription=True,
            transcription_params=TranscriptionParams(
                language=self.settings.language,
                sample_rate=self.settings.sample_rate,
                input_audio_format="pcm",
            ),
            enable_turn_detection=False,
        )

    def _create_input_stream(self):
        if self._input_stream_factory is not None:
            return self._input_stream_factory(self._audio_callback)
        return sd.RawInputStream(
            samplerate=self.settings.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self.settings.block_frames,
            device=self.settings.device,
            callback=self._audio_callback,
        )

    def _audio_callback(self, indata, frames=None, time_info=None, status=None) -> None:
        del frames, time_info
        if status:
            envelope = from_message(
                source=SOURCE_VOICE,
                kind=KIND_EXECUTION_FAILED,
                user_message="音频输入状态异常",
                dev_detail=str(status),
                code=CODE_VOICE_RUNTIME_FAILED,
                retryable=True,
            )
            self._emit_error(f"音频输入状态异常: {status}", envelope=envelope.to_dict())
        if self._stop_event.is_set():
            return
        try:
            self._audio_queue.put_nowait(bytes(indata))
        except queue.Full:
            pass

    def _processing_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            self._handle_chunk(chunk)

    def _handle_chunk(self, chunk: bytes) -> None:
        if self._conversation is None:
            return
        chunk = self._echo_bridge.process_capture(chunk)
        if not chunk:
            return
        for event in self._vad.process(chunk):
            if event.event_type == "level":
                self.on_level(event.rms, self._vad.in_speech or event.voiced)
            elif event.event_type == "start":
                self._emit_state("speaking", "检测到用户说话")
                self._send_chunks(event.chunks)
            elif event.event_type == "chunk":
                self._send_chunks(event.chunks)
            elif event.event_type == "end":
                self._emit_state("processing", f"语音段结束: {event.reason}")
                self._conversation.commit()

    def _send_chunks(self, chunks: tuple[bytes, ...]) -> None:
        for chunk in chunks:
            audio_b64 = base64.b64encode(chunk).decode("ascii")
            self._conversation.append_audio(audio_b64)

    def _close_conversation(self) -> None:
        conversation = self._conversation
        if conversation is None:
            return
        try:
            if hasattr(conversation, "end_session"):
                conversation.end_session(timeout=5)
        except Exception:
            pass
        try:
            if hasattr(conversation, "close"):
                conversation.close()
        except Exception:
            pass

    def handle_event(self, response) -> None:
        event_type = response.get("type") if isinstance(response, dict) else ""
        if event_type == "conversation.item.input_audio_transcription.completed":
            transcript = str(response.get("transcript") or "").strip()
            if transcript:
                self.on_transcript(transcript)
            self._emit_state("listening", "语音识别完成")
        elif event_type == "error":
            envelope = from_message(
                source=SOURCE_VOICE,
                kind=KIND_EXECUTION_FAILED,
                user_message="语音识别服务端错误",
                dev_detail=str(response),
                code=CODE_VOICE_RUNTIME_FAILED,
                retryable=True,
            )
            self._emit_error(f"语音识别服务端错误: {response}", envelope=envelope.to_dict())
            self._stop_event.set()
        elif event_type == "session.finished":
            self._stop_event.set()

    def _emit_state(self, state: str, message: str = "") -> None:
        try:
            self.on_state(state, message)
        except Exception:
            pass

    def _emit_error(self, message: str, envelope: Optional[dict] = None) -> None:
        try:
            message_text = str(message)
            if envelope:
                message_text = f"{message_text}\n[ERROR_ENVELOPE] {dict(envelope)}"
            self.on_error(message_text)
            self.on_state("error", message_text)
        except Exception:
            pass

    def _configure_echo_cancellation(self) -> None:
        self._echo_cancellation_available = False
        if not self.settings.echo_cancellation_enabled:
            self._echo_bridge.configure(self.settings.to_echo_cancellation_config())
            return
        canceller = self._echo_bridge.configure(self.settings.to_echo_cancellation_config())
        self._echo_cancellation_available = canceller is not None and canceller.available
        if not self._echo_cancellation_available:
            self._emit_state("listening", "WebRTC 回声消除不可用，已使用原始麦克风输入")
