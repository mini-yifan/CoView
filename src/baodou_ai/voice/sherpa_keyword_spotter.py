"""sherpa-onnx keyword spotting wrapper with injectable backend for tests."""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional, Protocol, Sequence, Tuple

import numpy as np


class WakeWordDependencyError(RuntimeError):
    """Raised when the local wake-word dependency is unavailable."""


class WakeWordConfigurationError(RuntimeError):
    """Raised when wake-word configuration is incomplete or invalid."""


@dataclass(frozen=True)
class WakeWordPhrase:
    text: str
    language: str
    label: str = ""


@dataclass(frozen=True)
class WakeWordHit:
    text: str
    language: str = ""
    score: Optional[float] = None
    detected_at: float = 0.0


@dataclass(frozen=True)
class SherpaKeywordSpotterSettings:
    provider: str = "sherpa_onnx"
    phrases: Tuple[WakeWordPhrase, ...] = ()
    threshold: float = 0.5
    sample_rate: int = 16000
    model_dir: str = ""
    tokens_path: str = ""
    encoder_path: str = ""
    decoder_path: str = ""
    joiner_path: str = ""
    keywords_file: str = ""
    keywords_text: str = ""
    num_threads: int = 2

    @classmethod
    def from_config(cls, config) -> "SherpaKeywordSpotterSettings":
        wake_cfg = config.wake_word_config
        voice_cfg = config.voice_interaction_config
        phrases: List[WakeWordPhrase] = []
        for index, item in enumerate(wake_cfg.get("phrases", [])):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "") or "").strip()
            language = str(item.get("language", "") or "").strip().lower()
            if text:
                phrases.append(
                    WakeWordPhrase(
                        text=text,
                        language=language,
                        label=cls._build_phrase_label(text, language, index),
                    )
                )
        return cls(
            provider=str(wake_cfg.get("provider", "sherpa_onnx") or "sherpa_onnx").strip().lower(),
            phrases=tuple(phrases),
            threshold=float(wake_cfg.get("threshold", 0.5) or 0.5),
            sample_rate=int(voice_cfg.get("sample_rate", 16000) or 16000),
            model_dir=config.resolve_resource_path(wake_cfg.get("model_dir", "")),
            tokens_path=config.resolve_resource_path(wake_cfg.get("tokens_path", "")),
            encoder_path=config.resolve_resource_path(wake_cfg.get("encoder_path", "")),
            decoder_path=config.resolve_resource_path(wake_cfg.get("decoder_path", "")),
            joiner_path=config.resolve_resource_path(wake_cfg.get("joiner_path", "")),
            keywords_file=config.resolve_resource_path(wake_cfg.get("keywords_file", "")),
            keywords_text=str(wake_cfg.get("keywords_text", "") or "").strip(),
            num_threads=max(1, int(wake_cfg.get("num_threads", 2) or 2)),
        )

    @staticmethod
    def _build_phrase_label(text: str, language: str, index: int) -> str:
        normalized_text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", str(text or "").strip())
        normalized_text = normalized_text.strip("_") or "wake"
        normalized_language = str(language or "any").strip().lower() or "any"
        return f"COVIEW_{normalized_language}_{index}_{normalized_text}"


class _SherpaKeywordSpotterBackend(Protocol):
    def create_stream(self):
        ...

    def is_ready(self, stream) -> bool:
        ...

    def decode_stream(self, stream) -> None:
        ...

    def get_result(self, stream):
        ...

    def reset_stream(self, stream) -> None:
        ...

    def close(self) -> None:
        ...


BackendFactory = Callable[[SherpaKeywordSpotterSettings], _SherpaKeywordSpotterBackend]


class SherpaKeywordSpotter:
    """Wraps sherpa-onnx keyword spotting behind a testable interface."""

    def __init__(
        self,
        settings: SherpaKeywordSpotterSettings,
        *,
        backend_factory: Optional[BackendFactory] = None,
        time_provider: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._backend_factory = backend_factory or self._build_backend
        self._time = time_provider
        self._backend: Optional[_SherpaKeywordSpotterBackend] = None
        self._stream = None
        self._keywords_tempdir: Optional[tempfile.TemporaryDirectory] = None

    @property
    def settings(self) -> SherpaKeywordSpotterSettings:
        return self._settings

    @property
    def running(self) -> bool:
        return self._backend is not None and self._stream is not None

    def start(self) -> None:
        if self.running:
            return
        self._backend = self._backend_factory(self._settings)
        self._stream = self._backend.create_stream()

    def stop(self) -> None:
        self._stream = None
        backend = self._backend
        self._backend = None
        if backend is not None:
            try:
                backend.close()
            except Exception:
                pass
        if self._keywords_tempdir is not None:
            self._keywords_tempdir.cleanup()
            self._keywords_tempdir = None

    def update_settings(self, settings: SherpaKeywordSpotterSettings) -> None:
        should_restart = self.running
        self.stop()
        self._settings = settings
        if should_restart:
            self.start()

    def process_audio(self, chunk: Any, sample_rate: Optional[int] = None) -> Optional[WakeWordHit]:
        if not self.running:
            return None
        assert self._backend is not None
        assert self._stream is not None

        effective_sample_rate = int(sample_rate or self._settings.sample_rate or 16000)
        samples = self._to_float32_samples(chunk)
        if samples.size == 0:
            return None
        self._stream.accept_waveform(effective_sample_rate, samples)
        while self._backend.is_ready(self._stream):
            self._backend.decode_stream(self._stream)
            result = self._backend.get_result(self._stream)
            hit = self._extract_hit(result, detected_at=self._time())
            if hit is not None:
                self._backend.reset_stream(self._stream)
                return hit
        return None

    @staticmethod
    def _to_float32_samples(chunk: Any) -> np.ndarray:
        if chunk is None:
            return np.zeros(0, dtype=np.float32)
        if isinstance(chunk, bytes):
            if not chunk:
                return np.zeros(0, dtype=np.float32)
            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
            return samples / 32768.0

        array = np.asarray(chunk)
        if array.size == 0:
            return np.zeros(0, dtype=np.float32)
        if array.dtype == np.int16:
            return array.astype(np.float32) / 32768.0
        return array.astype(np.float32).reshape(-1)

    def _extract_hit(self, result: Any, *, detected_at: float) -> Optional[WakeWordHit]:
        if result is None:
            return None

        text = ""
        language = ""
        score: Optional[float] = None
        if isinstance(result, str):
            text = result.strip()
        elif isinstance(result, dict):
            text = str(result.get("keyword") or result.get("text") or "").strip()
            language = str(result.get("language") or "").strip().lower()
            score = self._coerce_score(result.get("score"))
        else:
            text = str(
                getattr(result, "keyword", None)
                or getattr(result, "text", None)
                or getattr(result, "result", None)
                or ""
            ).strip()
            language = str(getattr(result, "language", "") or "").strip().lower()
            score = self._coerce_score(getattr(result, "score", None))

        if not text:
            return None
        if score is not None and score < float(self._settings.threshold):
            return None
        phrase = self._find_phrase(text)
        if phrase is not None:
            text = phrase.text
            if not language:
                language = phrase.language
        elif not language:
            language = self._find_language(text)
        return WakeWordHit(text=text, language=language, score=score, detected_at=detected_at)

    @staticmethod
    def _coerce_score(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _find_language(self, text: str) -> str:
        phrase = self._find_phrase(text)
        return phrase.language if phrase is not None else ""

    def _find_phrase(self, text: str) -> Optional[WakeWordPhrase]:
        normalized = str(text or "").strip().lower()
        for phrase in self._settings.phrases:
            if phrase.text.strip().lower() == normalized:
                return phrase
            if phrase.label and phrase.label.strip().lower() == normalized:
                return phrase
        return None

    def _build_backend(self, settings: SherpaKeywordSpotterSettings) -> _SherpaKeywordSpotterBackend:
        if settings.provider != "sherpa_onnx":
            raise WakeWordConfigurationError(f"不支持的本地唤醒 provider: {settings.provider}")
        try:
            import sherpa_onnx  # type: ignore
        except ImportError as exc:
            raise WakeWordDependencyError("未安装 sherpa-onnx，无法启用本地唤醒。") from exc

        tokens_path = self._resolve_asset_path(settings.tokens_path, settings.model_dir, "tokens.txt")
        encoder_path = self._resolve_asset_path(settings.encoder_path, settings.model_dir, "encoder*.onnx")
        decoder_path = self._resolve_asset_path(settings.decoder_path, settings.model_dir, "decoder*.onnx")
        joiner_path = self._resolve_asset_path(settings.joiner_path, settings.model_dir, "joiner*.onnx")
        keywords_path = self._resolve_keywords_file(settings)

        missing = [
            name
            for name, value in (
                ("tokens_path", tokens_path),
                ("encoder_path", encoder_path),
                ("decoder_path", decoder_path),
                ("joiner_path", joiner_path),
                ("keywords_file", keywords_path),
            )
            if not value
        ]
        if missing:
            joined = ", ".join(missing)
            raise WakeWordConfigurationError(
                f"本地唤醒配置不完整，缺少: {joined}。"
            )

        try:
            return sherpa_onnx.KeywordSpotter(
                tokens=tokens_path,
                encoder=encoder_path,
                decoder=decoder_path,
                joiner=joiner_path,
                keywords_file=keywords_path,
                provider="cpu",
                num_threads=max(1, int(settings.num_threads)),
            )
        except Exception as exc:
            raise WakeWordConfigurationError(f"sherpa-onnx 唤醒器初始化失败: {exc}") from exc

    def _resolve_keywords_file(self, settings: SherpaKeywordSpotterSettings) -> str:
        explicit_path = str(settings.keywords_file or "").strip()
        if explicit_path:
            return explicit_path

        keywords_text = str(settings.keywords_text or "").strip()
        if not keywords_text:
            keywords_text = self._build_keywords_text(settings)
        if not keywords_text:
            return ""

        self._keywords_tempdir = tempfile.TemporaryDirectory(prefix="coview-kws-")
        keywords_path = Path(self._keywords_tempdir.name) / "keywords.txt"
        keywords_path.write_text(keywords_text, encoding="utf-8")
        return str(keywords_path)

    def _build_keywords_text(self, settings: SherpaKeywordSpotterSettings) -> str:
        if not settings.phrases:
            return ""

        tokens_path = self._resolve_asset_path(settings.tokens_path, settings.model_dir, "tokens.txt")
        lexicon_path = self._resolve_asset_path("", settings.model_dir, "en.phone")
        if not tokens_path:
            raise WakeWordConfigurationError("本地唤醒配置不完整，缺少: tokens_path。")
        if not lexicon_path:
            raise WakeWordConfigurationError("本地唤醒配置不完整，缺少: en.phone。")

        try:
            import sherpa_onnx  # type: ignore
        except ImportError as exc:
            raise WakeWordDependencyError("未安装 sherpa-onnx，无法生成唤醒词关键词文件。") from exc

        texts = [self._prepare_phrase_for_tokenization(phrase) for phrase in settings.phrases]
        try:
            encoded_texts = sherpa_onnx.text2token(
                texts,
                tokens=tokens_path,
                tokens_type="phone+ppinyin",
                lexicon=lexicon_path,
            )
        except ModuleNotFoundError as exc:
            if exc.name == "sentencepiece":
                raise WakeWordDependencyError(
                    "未安装 sentencepiece，无法生成自定义唤醒词关键词文件。"
                ) from exc
            raise WakeWordConfigurationError(f"生成关键词文件失败: {exc}") from exc
        except Exception as exc:
            raise WakeWordConfigurationError(f"生成关键词文件失败: {exc}") from exc

        lines = []
        for phrase, encoded in zip(settings.phrases, encoded_texts):
            tokens = [str(token) for token in encoded]
            if not tokens:
                raise WakeWordConfigurationError(f"唤醒词无法转换为关键词: {phrase.text}")
            lines.append(" ".join(tokens + [f"@{phrase.label}"]))
        return "\n".join(lines)

    @staticmethod
    def _prepare_phrase_for_tokenization(phrase: WakeWordPhrase) -> str:
        text = str(phrase.text or "").strip()
        if phrase.language == "en":
            return text.upper()
        return text

    @staticmethod
    def _resolve_asset_path(explicit_path: str, model_dir: str, pattern: str) -> str:
        normalized_explicit = str(explicit_path or "").strip()
        if normalized_explicit:
            return normalized_explicit
        normalized_model_dir = str(model_dir or "").strip()
        if not normalized_model_dir:
            return ""

        candidates = sorted(Path(normalized_model_dir).glob(pattern))
        if not candidates:
            return ""

        preferred = [
            candidate
            for candidate in candidates
            if ".int8." not in candidate.name.lower()
        ]
        selected = preferred[0] if preferred else candidates[0]
        return str(selected)
