from types import SimpleNamespace
import sys

import numpy as np

from baodou_ai.core.config import Config
from baodou_ai.voice.sherpa_keyword_spotter import (
    SherpaKeywordSpotter,
    SherpaKeywordSpotterSettings,
    WakeWordPhrase,
    WakeWordDependencyError,
    WakeWordHit,
)
from baodou_ai.voice.wake_word_engine import WakeWordEngine


def _pcm(value: int, frames: int = 160) -> bytes:
    return np.full(frames, value, dtype=np.int16).tobytes()


class _FakeClock:
    def __init__(self, now: float = 100.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


class _FakeKeywordStream:
    def __init__(self):
        self.waveforms = []

    def accept_waveform(self, sample_rate, samples) -> None:
        self.waveforms.append((sample_rate, samples.copy()))


class _FakeKeywordBackend:
    def __init__(self, results):
        self.results = list(results)
        self.decode_calls = 0
        self.reset_calls = 0
        self.closed = False
        self.stream = _FakeKeywordStream()

    def create_stream(self):
        return self.stream

    def is_ready(self, stream) -> bool:
        assert stream is self.stream
        return bool(self.results)

    def decode_stream(self, stream) -> None:
        assert stream is self.stream
        self.decode_calls += 1

    def get_result(self, stream):
        assert stream is self.stream
        return self.results.pop(0)

    def reset_stream(self, stream) -> None:
        assert stream is self.stream
        self.reset_calls += 1

    def close(self) -> None:
        self.closed = True


class _ManualAudioSource:
    def __init__(self, on_audio, settings):
        self.on_audio = on_audio
        self.settings = settings
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class _FakeSpotter:
    def __init__(self, settings, *, results=None, process_error=None):
        self.settings = settings
        self.results = list(results or [])
        self.process_error = process_error
        self.started = False
        self.stopped = False
        self.updated_settings = []
        self.process_calls = []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def update_settings(self, settings) -> None:
        self.updated_settings.append(settings)
        self.settings = settings

    def process_audio(self, chunk, sample_rate=None):
        self.process_calls.append((chunk, sample_rate))
        if self.process_error is not None:
            raise self.process_error
        if self.results:
            return self.results.pop(0)
        return None


def test_sherpa_keyword_spotter_returns_hit_and_resets_stream():
    backend = _FakeKeywordBackend(
        [{"keyword": "BAODOU_en_1_hello_Lulu", "score": 0.86, "language": "en"}]
    )
    spotter = SherpaKeywordSpotter(
        SherpaKeywordSpotterSettings(
            phrases=(
                WakeWordPhrase(text="你好彤彤", language="zh", label="BAODOU_zh_0_你好彤彤"),
                WakeWordPhrase(text="hello Lulu", language="en", label="BAODOU_en_1_hello_Lulu"),
            ),
            threshold=0.5,
            sample_rate=16000,
        ),
        backend_factory=lambda settings: backend,
        time_provider=lambda: 12.5,
    )
    spotter.start()

    hit = spotter.process_audio(_pcm(1200))

    assert hit == WakeWordHit(text="hello Lulu", language="en", score=0.86, detected_at=12.5)
    assert backend.reset_calls == 1
    assert backend.stream.waveforms[0][0] == 16000
    assert backend.stream.waveforms[0][1].dtype == np.float32


def test_sherpa_keyword_spotter_generates_keywords_text_with_labels(tmp_path, monkeypatch):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "tokens.txt").write_text("dummy", encoding="utf-8")
    (model_dir / "en.phone").write_text("dummy", encoding="utf-8")

    class _FakeSherpaModule:
        @staticmethod
        def text2token(texts, **kwargs):
            assert texts == ["你好彤彤", "HELLO LULU"]
            assert kwargs["tokens"] == str(model_dir / "tokens.txt")
            assert kwargs["lexicon"] == str(model_dir / "en.phone")
            return [["n", "i3", "hao3"], ["HH", "AH0", "L", "UW1", "L", "UW1"]]

    monkeypatch.setitem(sys.modules, "sherpa_onnx", _FakeSherpaModule())
    settings = SherpaKeywordSpotterSettings(
        phrases=(
            WakeWordPhrase(text="你好彤彤", language="zh", label="BAODOU_zh_0_你好彤彤"),
            WakeWordPhrase(text="hello Lulu", language="en", label="BAODOU_en_1_hello_Lulu"),
        ),
        model_dir=str(model_dir),
    )
    spotter = SherpaKeywordSpotter(settings, backend_factory=lambda _: _FakeKeywordBackend([]))

    keywords_text = spotter._build_keywords_text(settings)

    assert "n i3 hao3 @BAODOU_zh_0_你好彤彤" in keywords_text
    assert "HH AH0 L UW1 L UW1 @BAODOU_en_1_hello_Lulu" in keywords_text


def test_sherpa_keyword_spotter_filters_low_score_hits():
    backend = _FakeKeywordBackend([{"keyword": "你好彤彤", "score": 0.2}])
    spotter = SherpaKeywordSpotter(
        SherpaKeywordSpotterSettings(
            phrases=(SimpleNamespace(text="你好彤彤", language="zh"),),
            threshold=0.5,
        ),
        backend_factory=lambda settings: backend,
    )
    spotter.start()

    hit = spotter.process_audio(_pcm(900))

    assert hit is None
    assert backend.reset_calls == 0


def test_wake_word_engine_transitions_triggered_to_cooldown_to_listening():
    clock = _FakeClock()
    captured_hits = []
    statuses = []
    fake_spotter = _FakeSpotter(
        settings=None,
        results=[WakeWordHit(text="你好彤彤", language="zh", detected_at=clock())],
    )
    config = Config.create_isolated()
    config.set("wake_word_config.enabled", True)
    config.set("wake_word_config.cooldown_ms", 3000)
    config.set("wake_word_config.post_wake_timeout_seconds", 2)

    engine = WakeWordEngine(
        config,
        on_hit=captured_hits.append,
        on_state_change=statuses.append,
        spotter_factory=lambda settings: fake_spotter,
        audio_source_factory=lambda on_audio, settings: _ManualAudioSource(on_audio, settings),
        time_provider=clock,
    )

    assert engine.start() is True
    hit = engine.process_audio(_pcm(1200))

    assert hit is not None
    assert captured_hits == [hit]
    assert engine.state == "triggered"
    assert engine.status.wake_active is True
    assert engine.cooldown_remaining_ms() == 3000

    clock.advance(2.1)
    engine.tick()
    assert engine.state == "cooldown"

    clock.advance(1.0)
    engine.tick()
    assert engine.state == "listening"
    assert statuses[-1].state == "listening"


def test_wake_word_engine_start_is_idempotent_when_already_running():
    created_spotters = []
    created_sources = []
    config = Config.create_isolated()
    config.set("wake_word_config.enabled", True)

    def _spotter_factory(settings):
        spotter = _FakeSpotter(settings=settings)
        created_spotters.append(spotter)
        return spotter

    def _source_factory(on_audio, settings):
        source = _ManualAudioSource(on_audio, settings)
        created_sources.append(source)
        return source

    engine = WakeWordEngine(
        config,
        spotter_factory=_spotter_factory,
        audio_source_factory=_source_factory,
    )

    assert engine.start() is True
    assert engine.start() is True

    assert engine.running is True
    assert len(created_spotters) == 1
    assert len(created_sources) == 1
    assert created_spotters[0].stopped is False
    assert created_sources[0].stopped is False


def test_wake_word_engine_does_not_emit_duplicate_listening_statuses():
    statuses = []
    config = Config.create_isolated()
    config.set("wake_word_config.enabled", True)
    fake_spotter = _FakeSpotter(settings=None)
    engine = WakeWordEngine(
        config,
        on_state_change=statuses.append,
        spotter_factory=lambda settings: fake_spotter,
        audio_source_factory=lambda on_audio, settings: _ManualAudioSource(on_audio, settings),
    )

    assert engine.start() is True
    engine.process_audio(_pcm(100))
    engine.process_audio(_pcm(120))

    assert [status.state for status in statuses] == ["listening"]


def test_wake_word_engine_refresh_config_restarts_with_new_settings():
    created_settings = []
    config = Config.create_isolated()
    config.set("wake_word_config.enabled", True)
    config.set("wake_word_config.cooldown_ms", 1500)
    config.set(
        "wake_word_config.phrases",
        [
            {"text": "你好彤彤", "language": "zh"},
            {"text": "hello Lulu", "language": "en"},
        ],
    )

    def _spotter_factory(settings):
        created_settings.append(settings)
        return _FakeSpotter(settings=settings)

    engine = WakeWordEngine(
        config,
        spotter_factory=_spotter_factory,
        audio_source_factory=lambda on_audio, settings: _ManualAudioSource(on_audio, settings),
    )

    assert engine.start() is True
    config.set("wake_word_config.cooldown_ms", 3000)
    config.set(
        "wake_word_config.phrases",
        [
            {"text": "你好包豆", "language": "zh"},
            {"text": "Hey Baodou", "language": "en"},
        ],
    )

    assert engine.refresh_config() is True

    assert len(created_settings) == 2
    assert created_settings[-1].threshold == 0.5
    assert created_settings[-1].phrases[0].text == "你好包豆"
    assert created_settings[-1].phrases[1].text == "Hey Baodou"
    assert engine.state == "listening"


def test_wake_word_engine_enters_degraded_on_runtime_failure():
    config = Config.create_isolated()
    config.set("wake_word_config.enabled", True)
    engine = WakeWordEngine(
        config,
        spotter_factory=lambda settings: _FakeSpotter(
            settings=settings,
            process_error=RuntimeError("boom"),
        ),
        audio_source_factory=lambda on_audio, settings: _ManualAudioSource(on_audio, settings),
    )

    assert engine.start() is True

    hit = engine.process_audio(_pcm(500))

    assert hit is None
    assert engine.state == "degraded"
    assert engine.status.degraded is True
    assert "本地唤醒运行失败" in engine.status.message


def test_wake_word_engine_degrades_when_dependency_is_missing():
    config = Config.create_isolated()
    config.set("wake_word_config.enabled", True)
    engine = WakeWordEngine(
        config,
        spotter_factory=lambda settings: (_ for _ in ()).throw(
            WakeWordDependencyError("未安装 sherpa-onnx")
        ),
        audio_source_factory=lambda on_audio, settings: _ManualAudioSource(on_audio, settings),
    )

    assert engine.start() is False
    assert engine.state == "degraded"
    assert "未安装 sherpa-onnx" in engine.status.message
