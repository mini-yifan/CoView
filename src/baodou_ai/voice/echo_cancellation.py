"""Optional WebRTC acoustic echo cancellation bridge.

The AEC processor needs two streams: rendered audio from TTS (reverse stream)
and microphone audio (capture stream). This module keeps that coupling out of
the TTS and ASR implementations.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np


@dataclass(frozen=True)
class EchoCancellationConfig:
    enabled: bool = True
    sample_rate: int = 16000
    frame_ms: int = 10
    stream_delay_ms: int = 80
    enable_ns: bool = True
    enable_agc: bool = False


class WebRtcEchoCanceller:
    """Small adapter around a WebRTC AudioProcessing binding."""

    def __init__(
        self,
        config: EchoCancellationConfig,
        *,
        processor_factory: Optional[Callable[..., object]] = None,
    ) -> None:
        self.config = config
        self.sample_rate = int(config.sample_rate or 16000)
        self.frame_samples = max(1, int(self.sample_rate * int(config.frame_ms or 10) / 1000))
        self.frame_bytes = self.frame_samples * 2
        self._render_buffer = b""
        self._capture_buffer = b""
        self._lock = threading.Lock()
        self._processor = self._create_processor(processor_factory)

    @property
    def available(self) -> bool:
        return self._processor is not None

    def process_capture(self, chunk: bytes) -> bytes:
        if not chunk or self._processor is None:
            return chunk
        output = bytearray()
        with self._lock:
            self._capture_buffer += bytes(chunk)
            while len(self._capture_buffer) >= self.frame_bytes:
                frame = self._capture_buffer[: self.frame_bytes]
                self._capture_buffer = self._capture_buffer[self.frame_bytes :]
                output.extend(self._process_stream_frame(frame))
        if not output:
            return b""
        return bytes(output)

    def add_rendered_audio(self, chunk: bytes, sample_rate: int) -> None:
        if not chunk or self._processor is None:
            return
        converted = self._resample_int16_mono(
            bytes(chunk), int(sample_rate or self.sample_rate), self.sample_rate
        )
        if not converted:
            return
        with self._lock:
            self._render_buffer += converted
            while len(self._render_buffer) >= self.frame_bytes:
                frame = self._render_buffer[: self.frame_bytes]
                self._render_buffer = self._render_buffer[self.frame_bytes :]
                self._process_reverse_frame(frame)

    def _create_processor(
        self, processor_factory: Optional[Callable[..., object]]
    ) -> Optional[object]:
        try:
            if processor_factory is None:
                from aec_audio_processing import AudioProcessor  # type: ignore

                processor_factory = AudioProcessor
            processor = processor_factory(
                enable_aec=True,
                enable_ns=bool(self.config.enable_ns),
                enable_agc=bool(self.config.enable_agc),
            )
            self._set_stream_format(processor)
            self._set_reverse_stream_format(processor)
            if hasattr(processor, "set_stream_delay"):
                processor.set_stream_delay(int(self.config.stream_delay_ms or 0))
            if not any(
                hasattr(processor, method_name)
                for method_name in (
                    "process_reverse_stream",
                    "analyze_reverse_stream",
                    "process_reverse",
                )
            ):
                return None
            return processor
        except Exception:
            return None

    def _set_stream_format(self, processor: object) -> None:
        if not hasattr(processor, "set_stream_format"):
            return
        try:
            processor.set_stream_format(self.sample_rate, 1, self.sample_rate, 1)
        except TypeError:
            processor.set_stream_format(self.sample_rate, 1)

    def _set_reverse_stream_format(self, processor: object) -> None:
        if hasattr(processor, "set_reverse_stream_format"):
            processor.set_reverse_stream_format(self.sample_rate, 1)

    def _process_stream_frame(self, frame: bytes) -> bytes:
        processor = self._processor
        if processor is None or not hasattr(processor, "process_stream"):
            return frame
        result = processor.process_stream(frame)
        return bytes(result or b"")

    def _process_reverse_frame(self, frame: bytes) -> None:
        processor = self._processor
        if processor is None:
            return
        for method_name in ("process_reverse_stream", "analyze_reverse_stream", "process_reverse"):
            method = getattr(processor, method_name, None)
            if callable(method):
                method(frame)
                return

    @staticmethod
    def _resample_int16_mono(chunk: bytes, source_rate: int, target_rate: int) -> bytes:
        if source_rate == target_rate:
            return chunk
        samples = np.frombuffer(chunk, dtype=np.int16)
        if samples.size == 0:
            return b""
        if samples.size == 1:
            repeated = np.repeat(samples, max(1, int(round(target_rate / max(1, source_rate)))))
            return repeated.astype(np.int16).tobytes()
        target_size = max(1, int(round(samples.size * target_rate / max(1, source_rate))))
        source_x = np.linspace(0.0, 1.0, num=samples.size, endpoint=True)
        target_x = np.linspace(0.0, 1.0, num=target_size, endpoint=True)
        resampled = np.interp(target_x, source_x, samples.astype(np.float32))
        resampled = np.clip(np.rint(resampled), -32768, 32767).astype(np.int16)
        return resampled.tobytes()


class EchoCancellationBridge:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._canceller: Optional[WebRtcEchoCanceller] = None
        self._config: Optional[EchoCancellationConfig] = None
        self._render_reference = b""
        self._render_sample_rate = 16000
        self._last_render_at = 0.0
        self._max_reference_seconds = 2.0

    def configure(self, config: EchoCancellationConfig) -> Optional[WebRtcEchoCanceller]:
        if not config.enabled:
            with self._lock:
                self._canceller = None
                self._config = config
                self._set_render_sample_rate_locked(int(config.sample_rate or self._render_sample_rate))
            return None
        with self._lock:
            self._set_render_sample_rate_locked(int(config.sample_rate or self._render_sample_rate))
            if self._config == config and self._canceller is not None:
                return self._canceller
            canceller = WebRtcEchoCanceller(config)
            self._config = config
            self._canceller = canceller if canceller.available else None
            return self._canceller

    def process_capture(self, chunk: bytes) -> bytes:
        canceller = self._canceller
        return canceller.process_capture(chunk) if canceller is not None else chunk

    def add_rendered_audio(self, chunk: bytes, sample_rate: int) -> None:
        self._remember_rendered_audio(chunk, sample_rate)
        canceller = self._canceller
        if canceller is not None:
            canceller.add_rendered_audio(chunk, sample_rate)

    def render_active(self, hangover_ms: int) -> bool:
        hangover_seconds = max(0.0, float(hangover_ms or 0) / 1000.0)
        if hangover_seconds <= 0:
            return False
        return time.monotonic() - float(self._last_render_at or 0.0) <= hangover_seconds

    def looks_like_residual_echo(
        self,
        capture_chunk: bytes,
        sample_rate: int,
        threshold: float,
    ) -> bool:
        if not capture_chunk:
            return False
        with self._lock:
            reference = bytes(self._render_reference)
            target_rate = int(self._render_sample_rate or sample_rate or 16000)
        if not reference:
            return False
        capture = WebRtcEchoCanceller._resample_int16_mono(
            bytes(capture_chunk), int(sample_rate or target_rate), target_rate
        )
        if not capture:
            return False
        capture_samples = np.frombuffer(capture, dtype=np.int16).astype(np.float32)
        reference_samples = np.frombuffer(reference, dtype=np.int16).astype(np.float32)
        if capture_samples.size < 8 or reference_samples.size < capture_samples.size:
            return False
        capture_energy = float(np.sqrt(np.mean(np.square(capture_samples))))
        if capture_energy < 1.0:
            return False
        capture_centered = capture_samples - float(np.mean(capture_samples))
        capture_norm = float(np.linalg.norm(capture_centered))
        if capture_norm <= 1e-6:
            return False
        window_size = int(capture_samples.size)
        step = max(1, min(window_size, window_size // 4 or 1))
        best = 0.0
        for start in range(0, reference_samples.size - window_size + 1, step):
            window = reference_samples[start : start + window_size]
            window_centered = window - float(np.mean(window))
            window_norm = float(np.linalg.norm(window_centered))
            if window_norm <= 1e-6:
                continue
            corr = abs(float(np.dot(capture_centered, window_centered) / (capture_norm * window_norm)))
            if corr > best:
                best = corr
                if best >= float(threshold or 0.0):
                    return True
        return False

    def _remember_rendered_audio(self, chunk: bytes, sample_rate: int) -> None:
        if not chunk:
            return
        with self._lock:
            target_rate = int(self._render_sample_rate or sample_rate or 16000)
        converted = WebRtcEchoCanceller._resample_int16_mono(
            bytes(chunk), int(sample_rate or target_rate), target_rate
        )
        if not converted:
            return
        max_bytes = max(1, int(target_rate * 2 * self._max_reference_seconds))
        with self._lock:
            self._render_sample_rate = target_rate
            self._render_reference = (self._render_reference + converted)[-max_bytes:]
            self._last_render_at = time.monotonic()

    def _set_render_sample_rate_locked(self, sample_rate: int) -> None:
        normalized = int(sample_rate or self._render_sample_rate or 16000)
        if normalized != self._render_sample_rate:
            self._render_reference = b""
            self._last_render_at = 0.0
        self._render_sample_rate = normalized

    @property
    def available(self) -> bool:
        return self._canceller is not None and self._canceller.available


_BRIDGE = EchoCancellationBridge()


def get_echo_cancellation_bridge() -> EchoCancellationBridge:
    return _BRIDGE
