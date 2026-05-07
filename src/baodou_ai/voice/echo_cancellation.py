"""Optional WebRTC acoustic echo cancellation bridge.

The AEC processor needs two streams: rendered audio from TTS (reverse stream)
and microphone audio (capture stream). This module keeps that coupling out of
the TTS and ASR implementations.
"""

from __future__ import annotations

import threading
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

    def configure(self, config: EchoCancellationConfig) -> Optional[WebRtcEchoCanceller]:
        if not config.enabled:
            with self._lock:
                self._canceller = None
                self._config = config
            return None
        with self._lock:
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
        canceller = self._canceller
        if canceller is not None:
            canceller.add_rendered_audio(chunk, sample_rate)

    @property
    def available(self) -> bool:
        return self._canceller is not None and self._canceller.available


_BRIDGE = EchoCancellationBridge()


def get_echo_cancellation_bridge() -> EchoCancellationBridge:
    return _BRIDGE
