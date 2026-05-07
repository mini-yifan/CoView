"""Small local energy-based VAD used before realtime ASR."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional

import numpy as np


@dataclass(frozen=True)
class LocalVadConfig:
    sample_rate: int = 16000
    block_frames: int = 1600
    energy_threshold: float = 900.0
    start_ms: int = 200
    end_ms: int = 1200
    pre_roll_ms: int = 500
    max_utterance_ms: int = 20000
    adaptive_threshold_enabled: bool = True
    adaptive_min_energy_threshold: float = 300.0
    adaptive_noise_multiplier: float = 1.8
    adaptive_noise_offset: float = 80.0
    adaptive_noise_alpha: float = 0.08


@dataclass(frozen=True)
class LocalVadEvent:
    event_type: str
    rms: float = 0.0
    voiced: bool = False
    utterance_index: int = 0
    chunks: tuple[bytes, ...] = ()
    reason: str = ""


class LocalVadSegmenter:
    """Detect utterance boundaries using int16 PCM RMS energy."""

    def __init__(self, config: LocalVadConfig) -> None:
        self.config = config
        self.chunk_ms = max(1, int(config.block_frames * 1000 / max(1, config.sample_rate)))
        self.start_chunks = max(1, math.ceil(config.start_ms / self.chunk_ms))
        self.end_chunks = max(1, math.ceil(config.end_ms / self.chunk_ms))
        self.pre_roll_chunks = max(1, math.ceil(config.pre_roll_ms / self.chunk_ms))
        self.max_utterance_chunks = max(1, math.ceil(config.max_utterance_ms / self.chunk_ms))
        self.pre_roll: Deque[bytes] = deque(maxlen=self.pre_roll_chunks)
        self.in_speech = False
        self.voiced_run = 0
        self.silence_run = 0
        self.utterance_chunks = 0
        self.utterance_index = 0
        self._noise_floor = 0.0

    def reset(self) -> None:
        self.pre_roll.clear()
        self.in_speech = False
        self.voiced_run = 0
        self.silence_run = 0
        self.utterance_chunks = 0
        self._noise_floor = 0.0

    def detect(self, chunk: bytes) -> tuple[bool, float]:
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            return False, 0.0
        rms = float(np.sqrt(np.mean(np.square(samples))))
        return rms >= self._effective_energy_threshold(), rms

    def _effective_energy_threshold(self) -> float:
        fixed_threshold = max(0.0, float(self.config.energy_threshold or 0.0))
        if not self.config.adaptive_threshold_enabled:
            return fixed_threshold
        adaptive_min = max(0.0, float(self.config.adaptive_min_energy_threshold or 0.0))
        dynamic_threshold = (
            self._noise_floor * max(1.0, float(self.config.adaptive_noise_multiplier or 1.0))
            + max(0.0, float(self.config.adaptive_noise_offset or 0.0))
        )
        adaptive_threshold = max(adaptive_min, dynamic_threshold)
        if fixed_threshold <= 0:
            return adaptive_threshold
        return min(fixed_threshold, adaptive_threshold)

    def _update_noise_floor(self, rms: float) -> None:
        if not self.config.adaptive_threshold_enabled:
            return
        normalized_rms = max(0.0, float(rms or 0.0))
        if self._noise_floor <= 0.0:
            self._noise_floor = normalized_rms
            return
        alpha = max(0.0, min(1.0, float(self.config.adaptive_noise_alpha or 0.0)))
        self._noise_floor = (self._noise_floor * (1.0 - alpha)) + (normalized_rms * alpha)

    def process(self, chunk: bytes) -> List[LocalVadEvent]:
        voiced, rms = self.detect(chunk)
        events: List[LocalVadEvent] = [
            LocalVadEvent(
                event_type="level",
                rms=rms,
                voiced=voiced,
                utterance_index=self.utterance_index,
            )
        ]

        if not self.in_speech:
            self.pre_roll.append(chunk)
            if not voiced:
                self._update_noise_floor(rms)
            self.voiced_run = self.voiced_run + 1 if voiced else 0
            if self.voiced_run >= self.start_chunks:
                self.in_speech = True
                self.silence_run = 0
                self.utterance_chunks = 0
                self.utterance_index += 1
                buffered_chunks = tuple(self.pre_roll)
                self.pre_roll.clear()
                self.utterance_chunks += len(buffered_chunks)
                events.append(
                    LocalVadEvent(
                        event_type="start",
                        rms=rms,
                        voiced=True,
                        utterance_index=self.utterance_index,
                        chunks=buffered_chunks,
                    )
                )
            return events

        self.utterance_chunks += 1
        events.append(
            LocalVadEvent(
                event_type="chunk",
                rms=rms,
                voiced=voiced,
                utterance_index=self.utterance_index,
                chunks=(chunk,),
            )
        )

        if voiced:
            self.silence_run = 0
        else:
            self.silence_run += 1

        end_reason: Optional[str] = None
        if self.silence_run >= self.end_chunks:
            end_reason = "silence"
        elif self.utterance_chunks >= self.max_utterance_chunks:
            end_reason = "max_duration"

        if end_reason:
            events.append(
                LocalVadEvent(
                    event_type="end",
                    rms=rms,
                    voiced=voiced,
                    utterance_index=self.utterance_index,
                    reason=end_reason,
                )
            )
            self.in_speech = False
            self.voiced_run = 0
            self.silence_run = 0
            self.utterance_chunks = 0
            self.pre_roll.clear()

        return events
