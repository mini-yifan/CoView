import queue
import threading
from typing import Optional

try:
    import certifi
    import os
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass

try:
    import dashscope
    from dashscope.audio.tts_v2 import SpeechSynthesizer, ResultCallback
    from dashscope.audio.tts_v2.speech_synthesizer import AudioFormat
    _DASHSCOPE_AVAILABLE = True
except ImportError:
    _DASHSCOPE_AVAILABLE = False
    dashscope = None
    SpeechSynthesizer = None
    ResultCallback = None
    AudioFormat = None

try:
    import sounddevice as sd
    _SOUNDDEVICE_AVAILABLE = True
except ImportError:
    _SOUNDDEVICE_AVAILABLE = False
    sd = None

from baodou_ai.voice.echo_cancellation import get_echo_cancellation_bridge
from baodou_ai.core.error_envelope import (
    CODE_TTS_INIT_FAILED,
    CODE_TTS_PLAYBACK_FAILED,
    KIND_EXECUTION_FAILED,
    SOURCE_TTS,
    from_exception,
)

_SAMPLE_RATE = 24000

if _DASHSCOPE_AVAILABLE:

    class _StreamingCallback(ResultCallback):
        def __init__(self, audio_queue: queue.Queue):
            self._audio_queue = audio_queue

        def on_open(self):
            pass

        def on_complete(self):
            self._audio_queue.put(None)

        def on_error(self, message):
            self._audio_queue.put(None)

        def on_close(self):
            pass

        def on_event(self, message):
            pass

        def on_data(self, data: bytes):
            self._audio_queue.put(data)


class CosyVoiceTTS:
    def __init__(self, config):
        self._config = config
        self._stop_flag = threading.Event()

    def stop(self) -> None:
        self._stop_flag.set()

    def _is_stopped(self) -> bool:
        return self._stop_flag.is_set()

    @property
    def available(self) -> bool:
        if not _DASHSCOPE_AVAILABLE or not _SOUNDDEVICE_AVAILABLE:
            return False
        tts_config = self._config.tts_config
        return bool(tts_config.get("enabled", True)) and bool(tts_config.get("api_key", ""))

    def speak(self, text: str) -> Optional[threading.Event]:
        self._stop_flag.clear()
        done_event = threading.Event()
        stripped = str(text or "").strip()
        if not stripped or not self.available:
            done_event.set()
            return done_event
        t = threading.Thread(target=self._speak_sync, args=(stripped, done_event), daemon=True)
        t.start()
        return done_event

    def _speak_sync(self, text: str, done_event: threading.Event) -> None:
        try:
            self._do_speak(text)
        except Exception as exc:
            print(f"[TTS] 播报失败: {exc}")
            envelope = from_exception(
                exc,
                source=SOURCE_TTS,
                kind=KIND_EXECUTION_FAILED,
                user_message="语音播报失败",
                code=CODE_TTS_INIT_FAILED,
                retryable=True,
            )
            print(f"[ERROR_ENVELOPE] {envelope.to_dict()}")
        finally:
            done_event.set()

    def _do_speak(self, text: str) -> None:
        tts_config = self._config.tts_config
        dashscope.api_key = str(tts_config.get("api_key", ""))
        dashscope.base_websocket_api_url = str(
            tts_config.get("base_url", "wss://dashscope.aliyuncs.com/api-ws/v1/inference")
        )

        audio_queue: queue.Queue = queue.Queue()
        callback = _StreamingCallback(audio_queue)

        speech_rate = float(tts_config.get("speech_rate", 1.2))
        volume = int(tts_config.get("volume", 50))
        pitch_rate = float(tts_config.get("pitch_rate", 1.0))

        synthesizer = SpeechSynthesizer(
            model=str(tts_config.get("model", "cosyvoice-v3-flash")),
            voice=str(tts_config.get("voice", "longanhuan")),
            speech_rate=speech_rate,
            volume=volume,
            pitch_rate=pitch_rate,
            format=AudioFormat.PCM_24000HZ_MONO_16BIT,
            callback=callback,
        )

        player_thread = threading.Thread(
            target=self._play_audio, args=(audio_queue,), daemon=True
        )
        player_thread.start()

        synthesizer.streaming_call(text)
        if self._is_stopped():
            audio_queue.put(None)
            return
        synthesizer.streaming_complete()

        player_thread.join(timeout=30)

    def _play_audio(self, audio_queue: queue.Queue) -> None:
        try:
            with sd.RawOutputStream(samplerate=_SAMPLE_RATE, channels=1, dtype="int16") as stream:
                while not self._is_stopped():
                    try:
                        data = audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if data is None:
                        break
                    get_echo_cancellation_bridge().add_rendered_audio(data, _SAMPLE_RATE)
                    stream.write(data)
        except Exception as exc:
            print(f"[TTS] 音频播放出错: {exc}")
            envelope = from_exception(
                exc,
                source=SOURCE_TTS,
                kind=KIND_EXECUTION_FAILED,
                user_message="语音播放失败",
                code=CODE_TTS_PLAYBACK_FAILED,
                retryable=True,
            )
            print(f"[ERROR_ENVELOPE] {envelope.to_dict()}")
