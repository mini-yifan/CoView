import sys
from types import SimpleNamespace

import numpy as np
from PyQt5.QtWidgets import QApplication

from baodou_ai.core.config import Config
from baodou_ai.gui.floating.controller import FloatingController
from baodou_ai.gui.floating.voice_controller import VoiceInteractionController
from baodou_ai.gui.i18n import set_locale
from baodou_ai.gui.runtime_log import RuntimeLogBuffer
from baodou_ai.voice.echo_cancellation import EchoCancellationConfig, WebRtcEchoCanceller
from baodou_ai.voice.intent_classifier import VoiceIntentClassifier, VoiceIntentContext
from baodou_ai.voice.local_vad import LocalVadConfig, LocalVadSegmenter
from baodou_ai.voice.qwen_asr import QwenRealtimeAsrClient, QwenRealtimeAsrSettings
from baodou_ai.voice.wake_word_engine import WakeWordEngineStatus


def _pcm(value: int, frames: int = 160) -> bytes:
    return np.full(frames, value, dtype=np.int16).tobytes()


def test_local_vad_detects_start_end_and_preroll():
    vad = LocalVadSegmenter(
        LocalVadConfig(
            sample_rate=16000,
            block_frames=160,
            energy_threshold=500,
            start_ms=20,
            end_ms=30,
            pre_roll_ms=20,
            max_utterance_ms=1000,
        )
    )

    events = []
    events.extend(vad.process(_pcm(0)))
    events.extend(vad.process(_pcm(1000)))
    events.extend(vad.process(_pcm(1000)))
    events.extend(vad.process(_pcm(0)))
    events.extend(vad.process(_pcm(0)))
    events.extend(vad.process(_pcm(0)))

    starts = [event for event in events if event.event_type == "start"]
    ends = [event for event in events if event.event_type == "end"]

    assert len(starts) == 1
    assert starts[0].chunks
    assert len(ends) == 1
    assert ends[0].reason == "silence"


def test_local_vad_forces_max_duration_end():
    vad = LocalVadSegmenter(
        LocalVadConfig(
            sample_rate=16000,
            block_frames=160,
            energy_threshold=500,
            start_ms=10,
            end_ms=1000,
            pre_roll_ms=10,
            max_utterance_ms=30,
        )
    )

    events = []
    for _ in range(6):
        events.extend(vad.process(_pcm(1000)))

    assert any(event.event_type == "end" and event.reason == "max_duration" for event in events)


def test_local_vad_detects_distant_speech_below_fixed_threshold():
    vad = LocalVadSegmenter(
        LocalVadConfig(
            sample_rate=16000,
            block_frames=160,
            energy_threshold=800,
            adaptive_min_energy_threshold=300,
            start_ms=20,
            end_ms=30,
            pre_roll_ms=20,
            max_utterance_ms=1000,
        )
    )

    events = []
    events.extend(vad.process(_pcm(20)))
    events.extend(vad.process(_pcm(30)))
    events.extend(vad.process(_pcm(350)))
    events.extend(vad.process(_pcm(360)))
    events.extend(vad.process(_pcm(20)))
    events.extend(vad.process(_pcm(20)))
    events.extend(vad.process(_pcm(20)))

    starts = [event for event in events if event.event_type == "start"]
    ends = [event for event in events if event.event_type == "end"]

    assert len(starts) == 1
    assert len(ends) == 1


def test_local_vad_raises_adaptive_threshold_above_steady_background_noise():
    vad = LocalVadSegmenter(
        LocalVadConfig(
            sample_rate=16000,
            block_frames=160,
            energy_threshold=800,
            adaptive_min_energy_threshold=300,
            start_ms=20,
            end_ms=30,
            pre_roll_ms=20,
            max_utterance_ms=1000,
        )
    )

    events = []
    for _ in range(12):
        events.extend(vad.process(_pcm(240)))
    events.extend(vad.process(_pcm(320)))
    events.extend(vad.process(_pcm(330)))

    assert not any(event.event_type == "start" for event in events)


class _FakeConversation:
    def __init__(self):
        self.audio = []
        self.commits = 0

    def append_audio(self, payload):
        self.audio.append(payload)

    def commit(self):
        self.commits += 1


def test_qwen_asr_sends_vad_audio_and_commits_on_end():
    conversation = _FakeConversation()
    states = []
    client = QwenRealtimeAsrClient(
        QwenRealtimeAsrSettings(
            api_key="test",
            sample_rate=16000,
            block_frames=160,
            energy_threshold=500,
            vad_min_speech_ms=10,
            vad_end_silence_ms=20,
            vad_pre_roll_ms=10,
        ),
        on_transcript=lambda text: None,
        on_level=lambda rms, speaking: None,
        on_state=lambda state, message: states.append(state),
        on_error=lambda message: None,
        conversation_factory=lambda settings, callback: conversation,
        input_stream_factory=lambda callback: None,
    )
    client._conversation = conversation

    client._handle_chunk(_pcm(1000))
    client._handle_chunk(_pcm(1000))
    client._handle_chunk(_pcm(0))
    client._handle_chunk(_pcm(0))

    assert conversation.audio
    assert conversation.commits == 1
    assert "speaking" in states
    assert "processing" in states


class _FakeAudioProcessor:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.stream_formats = []
        self.reverse_formats = []
        self.delays = []
        self.capture_frames = []
        self.reverse_frames = []

    def set_stream_format(self, *args):
        self.stream_formats.append(args)

    def set_reverse_stream_format(self, *args):
        self.reverse_formats.append(args)

    def set_stream_delay(self, delay_ms):
        self.delays.append(delay_ms)

    def process_reverse_stream(self, frame):
        self.reverse_frames.append(bytes(frame))

    def process_stream(self, frame):
        self.capture_frames.append(bytes(frame))
        return frame


def test_webrtc_echo_canceller_feeds_reverse_and_capture_streams():
    processor = _FakeAudioProcessor()
    canceller = WebRtcEchoCanceller(
        EchoCancellationConfig(
            enabled=True,
            sample_rate=16000,
            frame_ms=10,
            stream_delay_ms=90,
        ),
        processor_factory=lambda **kwargs: processor,
    )

    canceller.add_rendered_audio(_pcm(1000, frames=240), sample_rate=24000)
    cleaned = canceller.process_capture(_pcm(1000, frames=1600))

    assert cleaned == _pcm(1000, frames=1600)
    assert len(processor.reverse_frames) == 1
    assert len(processor.capture_frames) == 10
    assert processor.delays == [90]


class _FakeEchoBridge:
    def __init__(self):
        self.configure_calls = []
        self.processed_chunks = []

    def configure(self, config):
        self.configure_calls.append(config)
        return SimpleNamespace(available=True)

    def process_capture(self, chunk):
        self.processed_chunks.append(chunk)
        return _pcm(0)


def test_qwen_asr_processes_microphone_audio_through_echo_cancellation_first():
    conversation = _FakeConversation()
    bridge = _FakeEchoBridge()
    client = QwenRealtimeAsrClient(
        QwenRealtimeAsrSettings(
            api_key="test",
            sample_rate=16000,
            block_frames=160,
            energy_threshold=500,
            vad_min_speech_ms=10,
            vad_end_silence_ms=20,
            vad_pre_roll_ms=10,
            echo_cancellation_enabled=True,
        ),
        on_transcript=lambda text: None,
        on_level=lambda rms, speaking: None,
        on_state=lambda state, message: None,
        on_error=lambda message: None,
        conversation_factory=lambda settings, callback: conversation,
        input_stream_factory=lambda callback: None,
        echo_cancellation_bridge=bridge,
    )
    client._conversation = conversation
    client._configure_echo_cancellation()

    client._handle_chunk(_pcm(1000))
    client._handle_chunk(_pcm(1000))

    assert bridge.configure_calls
    assert len(bridge.processed_chunks) == 2
    assert conversation.audio == []


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


class _FakeChat:
    def __init__(self, content):
        self._content = content
        self.completions = self

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _FakeCompletion(self._content)


class _FakeClient:
    def __init__(self, content):
        self.chat = _FakeChat(content)


def test_intent_classifier_accepts_valid_intents_and_defaults_invalid(tmp_path):
    config = Config.create_isolated(str(tmp_path / "config.json"))
    config.set("api_config.api_key", "test")

    assert VoiceIntentClassifier(config, client_factory=lambda: _FakeClient(" stop ")).classify(
        VoiceIntentContext(transcript="停下")
    ) == "stop"
    assert VoiceIntentClassifier(config, client_factory=lambda: _FakeClient("new_task\n")).classify(
        VoiceIntentContext(transcript="换个任务")
    ) == "new_task"
    assert VoiceIntentClassifier(config, client_factory=lambda: _FakeClient("unknown")).classify(
        VoiceIntentContext(transcript="今天天气不错")
    ) == "ignore"


def test_intent_classifier_disables_thinking(tmp_path):
    config = Config.create_isolated(str(tmp_path / "config.json"))
    config.set("api_config.api_key", "test")
    client = _FakeClient("new_task")

    assert VoiceIntentClassifier(config, client_factory=lambda: client).classify(
        VoiceIntentContext(
            transcript="别播了，帮我打开微信",
            agent_status="ready",
            current_task="总结刚才的结果",
            tts_playing=True,
            tts_text="任务已经完成",
            interaction_phase="final_response_tts",
        )
    ) == "new_task"
    assert client.chat.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    system_prompt = client.chat.kwargs["messages"][0]["content"]
    user_prompt = client.chat.kwargs["messages"][1]["content"]
    assert "If interaction_phase is final_response_tts" in system_prompt
    assert "Interaction phase: final_response_tts" in user_prompt
    assert "previous task has already finished" in user_prompt


def test_intent_classifier_build_client_respects_tls_verify(monkeypatch, tmp_path):
    config = Config.create_isolated(str(tmp_path / "config.json"))
    config.set("api_config.api_key", "test-key")
    config.set("api_config.base_url", "https://example.test/v1")
    config.set("api_config.tls_verify", False)
    classifier = VoiceIntentClassifier(config)
    captured = {}

    class FakeHttpxClient:
        def __init__(self, *, verify):
            captured["verify"] = verify

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, http_client):
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["http_client"] = http_client

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(Client=FakeHttpxClient))
    monkeypatch.setattr("baodou_ai.voice.intent_classifier.OpenAI", FakeOpenAI)

    classifier._build_client()

    assert captured["api_key"] == "test-key"
    assert captured["base_url"] == "https://example.test/v1"
    assert captured["verify"] is False


class _FakePanel:
    target_visible = True

    def __init__(self):
        self.voice_states = []

    def set_voice_indicator(self, state, level=0.0):
        self.voice_states.append((state, level))


class _FakeBall:
    def __init__(self):
        self.voice_states = []

    def set_voice_indicator(self, state, level=0.0):
        self.voice_states.append((state, level))


class _FakeTTS:
    current_text = ""


class _FakeFloatingController:
    def __init__(self):
        self.panel_window = _FakePanel()
        self.ball_window = _FakeBall()
        self.is_pinned = True
        self._current_status_key = "ready"
        self._current_task_text = ""
        self._tts = _FakeTTS()
        self.voice_submits = []
        self.voice_stops = 0
        self.voice_new_tasks = []
        self.idle_timeouts = 0
        self.exit_commands = 0
        self.dismiss_commands = 0
        self.waiting_tts = False

    def _task_active(self):
        return self._current_status_key in {"running", "stopping"}

    def _is_waiting_for_tts(self):
        return self.waiting_tts

    # VoiceInteractionDelegate
    def is_task_active(self):
        return self._task_active()

    def is_waiting_for_tts(self):
        return self._is_waiting_for_tts()

    def current_status_key(self):
        return self._current_status_key

    def current_task_text(self):
        return self._current_task_text

    def current_tts_text(self):
        return self._tts.current_text

    def submit_voice_task(self, text):
        self.handle_voice_submit(text)

    def can_handle_idle_dismiss(self):
        return bool(self.is_pinned and self.panel_window.target_visible and not self._task_active() and not self._is_waiting_for_tts())

    def can_handle_priority_exit_command(self):
        return bool(self.is_pinned and self.panel_window.target_visible)

    def apply_voice_indicator(self, state, level):
        self.panel_window.set_voice_indicator(state, level)
        self.ball_window.set_voice_indicator(state, level)

    def handle_voice_submit(self, text):
        self.voice_submits.append(text)

    def request_voice_stop(self):
        self.voice_stops += 1

    def request_voice_new_task(self, text):
        self.voice_new_tasks.append(text)

    def handle_voice_idle_timeout(self):
        self.idle_timeouts += 1

    def handle_voice_exit_command(self):
        self.exit_commands += 1

    def handle_voice_dismiss_command(self):
        self.dismiss_commands += 1


class _FakeWakeWordLifecycle:
    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0
        self.running = False

    def start(self):
        self.start_calls += 1
        self.running = True

    def stop(self):
        self.stop_calls += 1
        self.running = False


class _FakeToastWindow:
    def __init__(self):
        self.messages = []

    def show_message(self, anchor, text):
        self.messages.append((anchor, text))


def test_voice_controller_routes_idle_transcript_to_submit(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())
    voice._running = True

    voice._handle_transcript("打开浏览器")

    assert controller.voice_submits == ["打开浏览器"]


def test_voice_controller_ignores_idle_punctuation_noise(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())
    voice._running = True

    voice._handle_transcript("。")
    voice._handle_transcript("，，，")

    assert controller.voice_submits == []


def test_voice_controller_ignores_idle_filler_transcript(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())
    voice._running = True

    voice._handle_transcript("嗯")
    voice._handle_transcript("好的")

    assert controller.voice_submits == []


def test_voice_controller_ignores_idle_short_fragment_without_command_semantics(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())
    voice._running = True

    voice._handle_transcript("微信")

    assert controller.voice_submits == []


def test_voice_controller_allows_idle_short_command(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())
    voice._running = True

    voice._handle_transcript("关闭")

    assert controller.voice_submits == ["关闭"]


def test_voice_controller_throttles_redundant_level_indicator_updates(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())
    voice._running = True
    now = {"value": 100.0}
    monkeypatch.setattr("baodou_ai.gui.floating.voice_controller.time.monotonic", lambda: now["value"])

    voice._handle_level(350.0, False)
    now["value"] += 0.02
    voice._handle_level(360.0, False)
    now["value"] += 0.02
    voice._handle_level(370.0, True)

    assert controller.ball_window.voice_states == [
        ("listening", 0.1),
        ("speaking", 370.0 / 3500.0),
    ]


def test_voice_controller_strips_error_envelope_for_user_state(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())
    captured = []
    voice.state_received.connect(lambda state, message: captured.append((state, message)))

    voice._handle_error("语音识别启动失败\n[ERROR_ENVELOPE] {'source': 'voice'}")

    assert captured
    assert captured[-1] == ("error", "语音识别启动失败")


def test_voice_controller_handles_idle_dismiss_commands_locally(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())
    voice._running = True

    voice._handle_transcript("你给我退下吧")

    assert controller.dismiss_commands == 1
    assert controller.exit_commands == 0
    assert controller.voice_submits == []


def test_voice_controller_matches_priority_exit_phrase_with_blocklist(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())

    assert voice._matches_priority_exit_command("请退出程序")
    assert voice._matches_priority_exit_command("请你现在立刻退出程序谢谢")
    assert not voice._matches_priority_exit_command("先不要退出程序")
    assert not voice._matches_priority_exit_command("怎么退出程序")
    assert voice._matches_priority_exit_command("please close the program right now")
    assert voice._matches_priority_exit_command("could you quit the app for me")
    assert not voice._matches_priority_exit_command("please do not close the program")
    assert not voice._matches_priority_exit_command("how do i quit the app")


def test_voice_controller_handles_priority_exit_while_busy(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    controller._current_status_key = "running"
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())
    voice._running = True
    classified = []
    voice._classify_async = lambda text: classified.append(text)

    voice._handle_transcript("请退出程序")

    assert controller.exit_commands == 1
    assert controller.dismiss_commands == 0
    assert controller.voice_submits == []
    assert classified == []


def test_voice_controller_treats_long_exit_phrase_as_priority_command(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    controller._current_status_key = "running"
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())
    voice._running = True
    classified = []
    voice._classify_async = lambda text: classified.append(text)

    voice._handle_transcript("请你现在立刻退出程序")

    assert controller.exit_commands == 1
    assert classified == []


def test_voice_controller_does_not_treat_blocked_exit_phrase_as_priority_command(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    controller._current_status_key = "running"
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())
    voice._running = True
    classified = []
    voice._classify_async = lambda text: classified.append(text)

    voice._handle_transcript("先不要退出程序")

    assert controller.exit_commands == 0
    assert classified == ["先不要退出程序"]


def test_voice_controller_routes_intents(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    controller._current_status_key = "running"
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())
    voice._running = True

    voice._handle_intent("ignore", "闲聊")
    voice._handle_intent("stop", "停下")
    voice._handle_intent("new_task", "换成打开浏览器")

    assert controller.voice_stops == 1
    assert controller.voice_new_tasks == ["换成打开浏览器"]
    assert controller.voice_submits == []


def test_voice_controller_marks_tts_only_stage_as_final_response_phase(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = _FakeFloatingController()
    controller._current_status_key = "ready"
    controller._current_task_text = "总结上一个任务"
    controller.waiting_tts = True
    controller._tts.current_text = "我已经帮你完成了"
    voice = VoiceInteractionController(controller, config, RuntimeLogBuffer())

    context = voice._build_intent_context("别播了，帮我打开浏览器")

    assert context.transcript == "别播了，帮我打开浏览器"
    assert context.agent_status == "ready"
    assert context.current_task == "总结上一个任务"
    assert context.tts_playing is True
    assert context.tts_text == "我已经帮你完成了"
    assert context.interaction_phase == "final_response_tts"


def test_wake_word_listening_prompt_uses_default_phrases(tmp_path):
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = FloatingController.__new__(FloatingController)
    controller._config = config
    controller._voice = SimpleNamespace(running=False)
    controller.ball_anchor = object()
    controller.toast_window = _FakeToastWindow()
    controller.apply_voice_indicator = lambda state, level: controller.__dict__.setdefault(
        "_applied_indicators", []
    ).append((state, level))

    controller._handle_wake_word_state_change(
        WakeWordEngineStatus(state="listening", message="等待唤醒词")
    )

    assert controller._applied_indicators == [("wake_listening", 0.0)]
    assert controller.toast_window.messages == [(controller.ball_anchor, "待唤醒: 你好小彤 / hey Lucy")]


def test_wake_word_listening_prompt_uses_custom_phrases(tmp_path):
    config = Config.create_isolated(str(tmp_path / "config.json"))
    config.set_wake_word_phrase("zh", "你好同窗")
    config.set_wake_word_phrase("en", "hey CoView")
    controller = FloatingController.__new__(FloatingController)
    controller._config = config
    controller._voice = SimpleNamespace(running=False)
    controller.ball_anchor = object()
    controller.toast_window = _FakeToastWindow()
    controller.apply_voice_indicator = lambda state, level: controller.__dict__.setdefault(
        "_applied_indicators", []
    ).append((state, level))

    controller._handle_wake_word_state_change(
        WakeWordEngineStatus(state="listening", message="等待唤醒词")
    )

    assert controller._applied_indicators == [("wake_listening", 0.0)]
    assert controller.toast_window.messages == [(controller.ball_anchor, "待唤醒: 你好同窗 / hey CoView")]


def test_wake_word_hit_enters_existing_voice_chain(tmp_path):
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = FloatingController.__new__(FloatingController)
    controller._config = config
    controller._voice = _FakeWakeWordLifecycle()
    controller._wake_word = _FakeWakeWordLifecycle()
    controller.is_pinned = False
    controller.panel_window = SimpleNamespace(target_visible=False)
    controller._task_active = lambda: False
    controller._is_waiting_for_tts = lambda: False

    activations = []

    def _activate():
        activations.append(True)
        controller.is_pinned = True
        controller.panel_window.target_visible = True

    controller.activate_from_hotkey = _activate

    controller._handle_wake_word_hit(object())

    assert activations == [True]
    assert controller._voice.start_calls == 1
    assert controller._wake_word.stop_calls == 1


def test_wake_word_cooldown_state_shows_dedicated_feedback(tmp_path):
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = FloatingController.__new__(FloatingController)
    controller._config = config
    controller._voice = SimpleNamespace(running=False)
    controller.ball_anchor = object()
    controller.toast_window = _FakeToastWindow()
    controller.apply_voice_indicator = lambda state, level: controller.__dict__.setdefault(
        "_applied_indicators", []
    ).append((state, level))

    controller._handle_wake_word_state_change(
        WakeWordEngineStatus(state="cooldown", message="命中冷却中", cooldown_remaining_ms=1200)
    )

    assert controller._applied_indicators == [("wake_cooldown", 0.0)]
    assert controller.toast_window.messages == [(controller.ball_anchor, "冷却中，请稍后再试")]


def test_wake_word_degraded_state_shows_error_feedback(tmp_path):
    config = Config.create_isolated(str(tmp_path / "config.json"))
    controller = FloatingController.__new__(FloatingController)
    controller._config = config
    controller._voice = SimpleNamespace(running=False)
    controller.ball_anchor = object()
    controller.toast_window = _FakeToastWindow()
    controller.apply_voice_indicator = lambda state, level: controller.__dict__.setdefault(
        "_applied_indicators", []
    ).append((state, level))

    controller._handle_wake_word_state_change(
        WakeWordEngineStatus(state="degraded", message="本地唤醒启动失败", degraded=True)
    )

    assert controller._applied_indicators == [("wake_error", 0.0)]
    assert controller.toast_window.messages == [(controller.ball_anchor, "本地唤醒已降级")]
