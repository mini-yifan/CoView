"""Small notification sound playback for TTS transitions."""

from __future__ import annotations

import sys
import wave
from pathlib import Path
from typing import Optional

try:
    import sounddevice as sd

    _SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    _SOUNDDEVICE_AVAILABLE = False


_FINAL_RESPONSE_SOUND = Path("sound") / "ios_notify_up_soft.wav"


def play_final_response_cue(config) -> bool:
    """Play the final-response cue when TTS is configured and available."""

    if not _SOUNDDEVICE_AVAILABLE or not _tts_enabled(config):
        return False
    sound_path = _resolve_sound_path(_FINAL_RESPONSE_SOUND)
    if sound_path is None:
        return False
    try:
        _play_wav(sound_path)
        return True
    except Exception as exc:
        print(f"[TTS] 最终播报提示音播放失败: {exc}")
        return False


def _tts_enabled(config) -> bool:
    tts_config = getattr(config, "tts_config", {}) or {}
    return bool(tts_config.get("enabled", True)) and bool(str(tts_config.get("api_key", "") or "").strip())


def _resolve_sound_path(relative_path: Path) -> Optional[Path]:
    candidates = []
    pyinstaller_root = getattr(sys, "_MEIPASS", "")
    if pyinstaller_root:
        candidates.append(Path(pyinstaller_root) / relative_path)
    candidates.append(Path.cwd() / relative_path)
    candidates.append(Path(__file__).resolve().parents[3] / relative_path)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _play_wav(path: Path) -> None:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    dtype_by_width = {
        1: "uint8",
        2: "int16",
        4: "int32",
    }
    dtype = dtype_by_width.get(sample_width)
    if dtype is None:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    with sd.RawOutputStream(samplerate=sample_rate, channels=channels, dtype=dtype) as stream:
        stream.write(frames)
