"""Wake-word engine state management for local keyword spotting."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

from baodou_ai.gui.runtime_log import RuntimeLogBuffer
from baodou_ai.voice.sherpa_keyword_spotter import (
    SherpaKeywordSpotter,
    SherpaKeywordSpotterSettings,
    WakeWordDependencyError,
    WakeWordHit,
)


class WakeWordSpotter(Protocol):
    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def update_settings(self, settings: SherpaKeywordSpotterSettings) -> None:
        ...

    def process_audio(self, chunk: Any, sample_rate: Optional[int] = None) -> Optional[WakeWordHit]:
        ...


class WakeWordAudioSource(Protocol):
    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...


@dataclass(frozen=True)
class WakeWordEngineSettings:
    enabled: bool = True
    provider: str = "sherpa_onnx"
    cooldown_ms: int = 1500
    post_wake_timeout_seconds: int = 8
    show_indicator: bool = True
    sample_rate: int = 16000
    block_frames: int = 1600
    device: Optional[int] = None
    spotter_settings: SherpaKeywordSpotterSettings = SherpaKeywordSpotterSettings()

    @classmethod
    def from_config(cls, config) -> "WakeWordEngineSettings":
        wake_cfg = config.wake_word_config
        voice_cfg = config.voice_interaction_config
        return cls(
            enabled=bool(wake_cfg.get("enabled", True)),
            provider=str(wake_cfg.get("provider", "sherpa_onnx") or "sherpa_onnx").strip().lower(),
            cooldown_ms=max(0, int(wake_cfg.get("cooldown_ms", 1500) or 0)),
            post_wake_timeout_seconds=max(
                0,
                int(wake_cfg.get("post_wake_timeout_seconds", 8) or 0),
            ),
            show_indicator=bool(wake_cfg.get("show_indicator", True)),
            sample_rate=int(voice_cfg.get("sample_rate", 16000) or 16000),
            block_frames=int(voice_cfg.get("block_frames", 1600) or 1600),
            device=voice_cfg.get("device"),
            spotter_settings=SherpaKeywordSpotterSettings.from_config(config),
        )


@dataclass(frozen=True)
class WakeWordEngineStatus:
    state: str
    message: str = ""
    wake_active: bool = False
    degraded: bool = False
    cooldown_remaining_ms: int = 0
    last_hit_text: str = ""


SpotterFactory = Callable[[SherpaKeywordSpotterSettings], WakeWordSpotter]
AudioSourceFactory = Callable[
    [Callable[[Any], None], WakeWordEngineSettings],
    WakeWordAudioSource,
]
StateCallback = Callable[[WakeWordEngineStatus], None]
HitCallback = Callable[[WakeWordHit], None]


class WakeWordEngine:
    """Tracks wake-word lifecycle, hit windows, cooldown, and graceful degradation."""

    def __init__(
        self,
        config,
        *,
        log_buffer: Optional[RuntimeLogBuffer] = None,
        on_state_change: Optional[StateCallback] = None,
        on_hit: Optional[HitCallback] = None,
        spotter_factory: Optional[SpotterFactory] = None,
        audio_source_factory: Optional[AudioSourceFactory] = None,
        time_provider: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._log_buffer = log_buffer
        self._on_state_change = on_state_change
        self._on_hit = on_hit
        self._spotter_factory = spotter_factory
        self._audio_source_factory = audio_source_factory
        self._time = time_provider

        self._settings = WakeWordEngineSettings.from_config(config)
        self._spotter: Optional[WakeWordSpotter] = None
        self._audio_source: Optional[WakeWordAudioSource] = None
        self._desired_running = False
        self._wake_active_until = 0.0
        self._cooldown_until = 0.0
        self._last_hit: Optional[WakeWordHit] = None
        self._status = WakeWordEngineStatus(state="stopped")

    @property
    def status(self) -> WakeWordEngineStatus:
        self.tick()
        return self._status

    @property
    def state(self) -> str:
        return self.status.state

    @property
    def running(self) -> bool:
        return bool(self._desired_running and self._spotter is not None)

    @property
    def last_hit(self) -> Optional[WakeWordHit]:
        return self._last_hit

    def start(self) -> bool:
        next_settings = WakeWordEngineSettings.from_config(self._config)
        if (
            self._desired_running
            and self._spotter is not None
            and self._settings == next_settings
            and self._status.state not in {"stopped", "disabled", "degraded"}
        ):
            self.tick()
            return True

        self._desired_running = True
        self._settings = next_settings
        if not self._settings.enabled:
            self._transition("disabled", "本地唤醒未启用。")
            return False
        if self._settings.provider != "sherpa_onnx":
            self._enter_degraded(f"不支持的本地唤醒 provider: {self._settings.provider}")
            return False

        self._stop_runtime()
        try:
            self._spotter = self._create_spotter(self._settings.spotter_settings)
            self._spotter.start()
            self._audio_source = self._create_audio_source(self._settings)
            if self._audio_source is not None:
                self._audio_source.start()
        except WakeWordDependencyError as exc:
            self._enter_degraded(str(exc))
            return False
        except Exception as exc:
            self._enter_degraded(f"本地唤醒启动失败: {exc}")
            return False

        self._wake_active_until = 0.0
        self._cooldown_until = 0.0
        self._transition("listening", "等待唤醒词")
        return True

    def stop(self) -> None:
        if not self._desired_running and self._spotter is None and self._audio_source is None:
            if self._status.state != "stopped":
                self._transition("stopped", "")
            return
        self._desired_running = False
        self._wake_active_until = 0.0
        self._cooldown_until = 0.0
        self._stop_runtime()
        self._transition("stopped", "")

    def shutdown(self) -> None:
        self.stop()

    def refresh_config(self) -> bool:
        previous_settings = self._settings
        self._settings = WakeWordEngineSettings.from_config(self._config)
        running_before_refresh = self._desired_running
        spotter_settings_changed = previous_settings.spotter_settings != self._settings.spotter_settings

        if self._spotter is not None and spotter_settings_changed and not running_before_refresh:
            try:
                self._spotter.update_settings(self._settings.spotter_settings)
            except Exception as exc:
                self._enter_degraded(f"本地唤醒配置更新失败: {exc}")
                return False

        if running_before_refresh and spotter_settings_changed:
            self._stop_runtime()

        if not running_before_refresh:
            if not self._settings.enabled:
                self._transition("disabled", "本地唤醒未启用。")
            return True
        return self.start()

    def process_audio(self, chunk: Any, sample_rate: Optional[int] = None) -> Optional[WakeWordHit]:
        self.tick()
        if self._spotter is None:
            return None

        now = self._time()
        if now < self._cooldown_until:
            if now >= self._wake_active_until:
                self._transition("cooldown", "命中冷却中")
            return None

        try:
            hit = self._spotter.process_audio(chunk, sample_rate or self._settings.sample_rate)
        except Exception as exc:
            self._enter_degraded(f"本地唤醒运行失败: {exc}")
            return None

        if hit is None:
            return None

        self._last_hit = hit
        self._cooldown_until = now + (float(self._settings.cooldown_ms) / 1000.0)
        timeout = max(0.0, float(self._settings.post_wake_timeout_seconds))
        self._wake_active_until = now + timeout if timeout > 0 else now
        self._transition("triggered", f"命中唤醒词: {hit.text}")
        self._log(f"[WAKE_WORD] 命中唤醒词: {hit.text}\n", "info")
        if self._on_hit is not None:
            try:
                self._on_hit(hit)
            except Exception:
                pass
        return hit

    def finish_triggered_state(self) -> None:
        self._wake_active_until = 0.0
        self.tick(force=True)

    def cooldown_remaining_ms(self) -> int:
        remaining = self._cooldown_until - self._time()
        return max(0, int(remaining * 1000))

    def tick(self, *, force: bool = False) -> None:
        if self._status.state in {"stopped", "disabled", "degraded"} and not force:
            return

        now = self._time()
        if self._wake_active_until > 0 and now < self._wake_active_until:
            if self._status.state != "triggered":
                self._transition("triggered", self._status.message or "命中唤醒词")
            return

        if self._wake_active_until > 0:
            self._wake_active_until = 0.0

        if now < self._cooldown_until:
            self._transition("cooldown", "命中冷却中")
            return

        if self._cooldown_until > 0:
            self._cooldown_until = 0.0

        if self._desired_running and self._spotter is not None and self._status.state != "listening":
            self._transition("listening", "等待唤醒词")

    def _create_spotter(self, settings: SherpaKeywordSpotterSettings) -> WakeWordSpotter:
        if self._spotter_factory is not None:
            return self._spotter_factory(settings)
        return SherpaKeywordSpotter(settings)

    def _create_audio_source(self, settings: WakeWordEngineSettings) -> Optional[WakeWordAudioSource]:
        if self._audio_source_factory is not None:
            return self._audio_source_factory(
                lambda chunk: self.process_audio(chunk, settings.sample_rate),
                settings,
            )
        return _SoundDeviceWakeWordSource(
            sample_rate=settings.sample_rate,
            block_frames=settings.block_frames,
            device=settings.device,
            on_audio=lambda chunk: self.process_audio(chunk, settings.sample_rate),
        )

    def _stop_runtime(self) -> None:
        audio_source = self._audio_source
        self._audio_source = None
        if audio_source is not None:
            try:
                audio_source.stop()
            except Exception:
                pass

        spotter = self._spotter
        self._spotter = None
        if spotter is not None:
            try:
                spotter.stop()
            except Exception:
                pass

    def _enter_degraded(self, message: str) -> None:
        self._wake_active_until = 0.0
        self._cooldown_until = 0.0
        self._stop_runtime()
        self._transition("degraded", message)
        self._log(f"[WAKE_WORD] {message}\n", "warning")

    def _transition(self, state: str, message: str) -> None:
        status = WakeWordEngineStatus(
            state=state,
            message=str(message or ""),
            wake_active=self._wake_active_until > self._time(),
            degraded=(state == "degraded"),
            cooldown_remaining_ms=self.cooldown_remaining_ms(),
            last_hit_text=self._last_hit.text if self._last_hit is not None else "",
        )
        previous = self._status
        if (
            previous.state == status.state
            and previous.message == status.message
            and previous.wake_active == status.wake_active
            and previous.degraded == status.degraded
            and previous.last_hit_text == status.last_hit_text
        ):
            self._status = status
            return
        self._status = status
        if self._on_state_change is not None:
            try:
                self._on_state_change(status)
            except Exception:
                pass

    def _log(self, text: str, level: str) -> None:
        if self._log_buffer is None:
            return
        try:
            self._log_buffer.append_log(text, level)
        except Exception:
            pass


class _SoundDeviceWakeWordSource:
    """Small sounddevice bridge so the engine can run outside tests."""

    def __init__(
        self,
        *,
        sample_rate: int,
        block_frames: int,
        device: Optional[int],
        on_audio: Callable[[bytes], None],
    ) -> None:
        self._sample_rate = int(sample_rate)
        self._block_frames = int(block_frames)
        self._device = device
        self._on_audio = on_audio
        self._stream = None

    def start(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise WakeWordDependencyError("未安装 sounddevice，无法采集本地唤醒音频。") from exc

        def _callback(indata, frames, _time_info, status) -> None:
            if status:
                return
            if frames <= 0:
                return
            self._on_audio(bytes(indata))

        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self._block_frames,
            callback=_callback,
            device=self._device,
        )
        self._stream.start()

    def stop(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is not None:
            stream.stop()
            stream.close()
