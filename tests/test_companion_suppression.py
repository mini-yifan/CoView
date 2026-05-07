import time
from types import SimpleNamespace

import baodou_ai.gui.floating.companion_controller as companion_module
from baodou_ai.ai.companion_privacy import (
    PRIVACY_ALLOWED,
    PRIVACY_BLOCKED_POST_CAPTURE,
    PRIVACY_BLOCKED_PRE_CAPTURE,
    CompanionPrivacyResult,
)
from baodou_ai.gui.floating.companion_controller import CompanionController, _FrontContextSignature


def test_rapid_switch_suppression_sets_cooldown(monkeypatch):
    # Avoid constructing QObject/QTimer in tests: create a bare instance.
    ctrl = CompanionController.__new__(CompanionController)
    ctrl._rapid_switch_window_seconds = 8
    ctrl._rapid_switch_count_threshold = 4
    ctrl._rapid_switch_cooldown_seconds = 20
    ctrl._switch_events = []
    ctrl._suppressed_until = 0.0

    now = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: now)

    # 4 events within 8 seconds triggers suppression.
    for i in range(4):
        monkeypatch.setattr(time, "monotonic", lambda i=i: now + i)
        ctrl._record_switch_event()

    assert ctrl._suppressed_until >= now + 20


def test_build_signature_handles_missing_fields():
    sig = CompanionController._build_signature({"pid": 123, "identifier": "x", "title": "t"})
    assert sig == _FrontContextSignature(pid=123, identifier="x", title="t")
    assert CompanionController._build_signature({"pid": 0}) is None
    assert CompanionController._build_signature({}) is None


class _FakeTimer:
    def __init__(self):
        self.started = []
        self.stopped = 0

    def stop(self):
        self.stopped += 1

    def start(self, value):
        self.started.append(value)


class _FakeSuggestionWindow:
    def __init__(self):
        self.privacy_notices = []
        self.hidden = 0

    def show_privacy_notice(self, anchor, text):
        self.privacy_notices.append((anchor, text))

    def hide_suggestions(self):
        self.hidden += 1


class _FakeCompanionDelegate:
    def __init__(self, suggestion_window):
        self._window = suggestion_window
        self._anchor = "anchor"
        self.edge_hidden = False
        self.task_active = False
        self.waiting_tts = False
        self.interaction_busy = False
        self.enter_calls = 0
        self.exit_calls = 0

    def can_show_companion(self):
        return not self.edge_hidden and not self.task_active and not self.waiting_tts

    def hide_suggestions(self):
        self._window.hide_suggestions()

    def show_suggestions(self, suggestions):
        self._window.privacy_notices.append(("suggestions", tuple(suggestions)))

    def show_privacy_notice(self, text):
        self._window.show_privacy_notice(self._anchor, text)

    def reposition_suggestions(self):
        return None

    def is_interaction_busy(self):
        return self.interaction_busy

    def enter_capture_mode(self):
        self.enter_calls += 1

    def exit_capture_mode(self):
        self.exit_calls += 1


class _FakePrivacyGuard:
    def __init__(self, pre_status=PRIVACY_ALLOWED, post_status=PRIVACY_ALLOWED):
        self.pre_status = pre_status
        self.post_status = post_status
        self.cooling_down = False
        self.marked = 0
        self.pre_calls = 0
        self.post_calls = 0

    def is_cooling_down(self):
        return self.cooling_down

    def cooldown_remaining_ms(self):
        return 15000

    def mark_blocked(self):
        self.marked += 1

    def review_pre_capture(self, _window_info):
        self.pre_calls += 1
        return CompanionPrivacyResult(self.pre_status, "test_pre")

    def review_post_capture(self, _capture, _window_info):
        self.post_calls += 1
        return CompanionPrivacyResult(self.post_status, "test_post")


class _FakeCapture:
    def __init__(self):
        self.calls = []

    def capture_window_region(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "ok": True,
            "png_bytes": b"png-bytes",
            "data_url": "",
            "frame_hash": "hash-1",
        }


class _FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class _FakeWorker:
    instances = []

    def __init__(self, seq, config, window_info, context_text, privacy_guard, capture=None):
        self.seq = seq
        self.config = config
        self.window_info = dict(window_info)
        self.context_text = context_text
        self.privacy_guard = privacy_guard
        self.capture = capture
        self.capture_done = _FakeSignal()
        self.result_ready = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False
        _FakeWorker.instances.append(self)

    def start(self):
        self.started = True


class _FakeShutdownWorker:
    def __init__(self):
        self.capture_done = SimpleNamespace(disconnect=lambda *_args, **_kwargs: None)
        self.result_ready = SimpleNamespace(disconnect=lambda *_args, **_kwargs: None)
        self.finished = SimpleNamespace(disconnect=lambda *_args, **_kwargs: None)
        self.interruption_requested = 0
        self.quit_calls = 0
        self.wait_calls = []
        self.terminate_calls = 0
        self.delete_later_calls = 0

    def isRunning(self):
        return True

    def requestInterruption(self):
        self.interruption_requested += 1

    def quit(self):
        self.quit_calls += 1

    def wait(self, timeout):
        self.wait_calls.append(timeout)
        return True

    def terminate(self):
        self.terminate_calls += 1

    def deleteLater(self):
        self.delete_later_calls += 1


def _controller_for_timeout(window_info, privacy_guard):
    suggestion_window = _FakeSuggestionWindow()
    delegate = _FakeCompanionDelegate(suggestion_window)
    ctrl = CompanionController.__new__(CompanionController)
    ctrl._delegate = delegate
    ctrl._platform_adapter = SimpleNamespace(get_frontmost_window_info=lambda: dict(window_info))
    ctrl._own_pid = 999
    ctrl._capture = _FakeCapture()
    ctrl._privacy_guard = privacy_guard
    ctrl._stable_timer = _FakeTimer()
    ctrl._dismiss_timer = _FakeTimer()
    ctrl._enabled = True
    ctrl._suppressed_until = 0.0
    ctrl._pending_window_info = dict(window_info)
    ctrl._pending_signature = CompanionController._build_signature(window_info)
    ctrl._last_frame_hash = ""
    ctrl._request_seq = 0
    ctrl._request_signature = None
    ctrl._privacy_blocked_signature = None
    ctrl._active_worker = None
    ctrl._retained_workers = []
    ctrl._shutting_down = False
    ctrl._capture_in_flight = False
    ctrl._capture_start_pending = False
    ctrl._capture_overlay_hidden = False
    ctrl._last_capture_started_at = 0.0
    ctrl._min_capture_interval_seconds = 0.0
    ctrl._suggestion_display_seconds = 30
    ctrl._config = object()
    return ctrl, suggestion_window


def test_pre_capture_privacy_block_skips_capture_and_shows_notice():
    window_info = {"pid": 123, "identifier": "app", "title": "登录", "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}}
    privacy = _FakePrivacyGuard(pre_status=PRIVACY_BLOCKED_PRE_CAPTURE)
    ctrl, suggestion_window = _controller_for_timeout(window_info, privacy)

    ctrl._on_stable_timeout()

    assert privacy.pre_calls == 1
    assert privacy.post_calls == 0
    assert privacy.marked == 1
    assert ctrl._capture.calls == []
    assert suggestion_window.privacy_notices == [("anchor", "当前窗口禁用智能推荐")]


def test_stable_timeout_defers_capture_while_interaction_busy():
    window_info = {"pid": 123, "identifier": "app", "title": "normal", "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}}
    privacy = _FakePrivacyGuard()
    ctrl, _suggestion_window = _controller_for_timeout(window_info, privacy)
    ctrl._delegate.interaction_busy = True

    ctrl._on_stable_timeout()

    assert privacy.pre_calls == 0
    assert ctrl._capture.calls == []
    assert ctrl._stable_timer.started == [1000]


def test_stable_timeout_does_not_start_duplicate_worker(monkeypatch):
    window_info = {"pid": 123, "identifier": "app", "title": "normal", "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}}
    privacy = _FakePrivacyGuard()
    ctrl, _suggestion_window = _controller_for_timeout(window_info, privacy)
    ctrl._capture_in_flight = True
    _FakeWorker.instances = []
    monkeypatch.setattr(companion_module, "_CaptureRecommendWorker", _FakeWorker)

    ctrl._on_stable_timeout()

    assert privacy.pre_calls == 0
    assert ctrl._capture.calls == []
    assert _FakeWorker.instances == []


def test_post_capture_privacy_block_from_worker_shows_notice():
    window_info = {"pid": 123, "identifier": "app", "title": "normal", "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}}
    privacy = _FakePrivacyGuard(post_status=PRIVACY_BLOCKED_POST_CAPTURE)
    ctrl, suggestion_window = _controller_for_timeout(window_info, privacy)

    ctrl._request_seq = 1
    ctrl._request_signature = CompanionController._build_signature(window_info)
    payload = {"ok": False, "privacy": CompanionPrivacyResult(PRIVACY_BLOCKED_POST_CAPTURE, "test_post")}
    ctrl._on_worker_finished(1, payload)

    assert privacy.marked == 1
    assert ctrl._request_signature is None
    assert suggestion_window.privacy_notices == [("anchor", "当前窗口禁用智能推荐")]


def test_allowed_privacy_flow_starts_worker_without_sync_capture(monkeypatch):
    window_info = {"pid": 123, "identifier": "app", "title": "normal", "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}}
    privacy = _FakePrivacyGuard()
    ctrl, suggestion_window = _controller_for_timeout(window_info, privacy)
    _FakeWorker.instances = []
    monkeypatch.setattr(companion_module, "_CaptureRecommendWorker", _FakeWorker)
    monkeypatch.setattr(companion_module.QTimer, "singleShot", lambda _delay, callback: callback())

    ctrl._on_stable_timeout()

    assert privacy.pre_calls == 1
    assert privacy.post_calls == 0
    assert privacy.marked == 0
    assert ctrl._capture.calls == []
    assert suggestion_window.privacy_notices == []
    assert len(_FakeWorker.instances) == 1
    worker = _FakeWorker.instances[0]
    assert worker.started is True
    assert worker.window_info["title"] == "normal"
    assert "title=normal" in worker.context_text


def test_worker_capture_done_restores_overlay_before_recommendation_result(monkeypatch):
    window_info = {"pid": 123, "identifier": "app", "title": "normal", "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}}
    privacy = _FakePrivacyGuard()
    ctrl, _suggestion_window = _controller_for_timeout(window_info, privacy)
    _FakeWorker.instances = []
    monkeypatch.setattr(companion_module, "_CaptureRecommendWorker", _FakeWorker)
    monkeypatch.setattr(companion_module.QTimer, "singleShot", lambda _delay, callback: callback())

    ctrl._on_stable_timeout()
    worker = _FakeWorker.instances[0]
    assert ctrl._delegate.enter_calls == 1
    assert ctrl._delegate.exit_calls == 0

    for callback in worker.capture_done.callbacks:
        callback(worker.seq)

    assert ctrl._delegate.exit_calls == 1
    assert ctrl._capture_overlay_hidden is False


def test_worker_finished_drops_stale_busy_or_changed_context_results():
    window_info = {"pid": 123, "identifier": "app", "title": "normal", "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}}
    changed_info = {"pid": 456, "identifier": "other", "title": "other", "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}}
    payload = {"ok": True, "frame_hash": "hash-new", "suggestions": ["one", "two"]}

    privacy = _FakePrivacyGuard()
    ctrl, suggestion_window = _controller_for_timeout(window_info, privacy)
    ctrl._request_seq = 2
    ctrl._request_signature = CompanionController._build_signature(window_info)
    ctrl._on_worker_finished(1, payload)
    assert suggestion_window.privacy_notices == []

    ctrl, suggestion_window = _controller_for_timeout(window_info, privacy)
    ctrl._request_seq = 2
    ctrl._request_signature = CompanionController._build_signature(window_info)
    ctrl._delegate.interaction_busy = True
    ctrl._on_worker_finished(2, payload)
    assert suggestion_window.privacy_notices == []

    ctrl, suggestion_window = _controller_for_timeout(window_info, privacy)
    ctrl._platform_adapter = SimpleNamespace(get_frontmost_window_info=lambda: dict(changed_info))
    ctrl._request_seq = 2
    ctrl._request_signature = CompanionController._build_signature(window_info)
    ctrl._on_worker_finished(2, payload)
    assert suggestion_window.privacy_notices == []


def test_shutdown_waits_for_active_and_retained_workers():
    ctrl = CompanionController.__new__(CompanionController)
    ctrl._stable_timer = _FakeTimer()
    ctrl._dismiss_timer = _FakeTimer()
    ctrl._request_seq = 7
    ctrl._request_signature = object()
    ctrl._privacy_blocked_signature = object()
    ctrl._shutting_down = False
    hidden = {"count": 0}
    ctrl.hide_suggestions = lambda: hidden.__setitem__("count", hidden["count"] + 1)
    active = _FakeShutdownWorker()
    retained = _FakeShutdownWorker()
    ctrl._active_worker = active
    ctrl._retained_workers = [retained]

    ctrl.shutdown()

    assert ctrl._shutting_down is True
    assert ctrl._request_seq == 8
    assert ctrl._request_signature is None
    assert ctrl._privacy_blocked_signature is None
    assert hidden["count"] == 1
    assert ctrl._active_worker is None
    assert ctrl._retained_workers == []
    assert active.interruption_requested == 1
    assert retained.interruption_requested == 1
    assert active.quit_calls == 1
    assert retained.quit_calls == 1
    assert active.wait_calls == [3000]
    assert retained.wait_calls == [3000]
    assert active.terminate_calls == 0
    assert retained.terminate_calls == 0
    assert active.delete_later_calls == 1
    assert retained.delete_later_calls == 1


def test_privacy_cooldown_only_suppresses_same_window_signature(monkeypatch):
    first_window = {"pid": 123, "identifier": "app", "title": "登录", "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}}
    second_window = {"pid": 456, "identifier": "safe", "title": "normal", "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}}
    privacy = _FakePrivacyGuard()
    privacy.cooling_down = True
    ctrl, suggestion_window = _controller_for_timeout(first_window, privacy)
    ctrl._privacy_blocked_signature = CompanionController._build_signature(first_window)

    ctrl._on_stable_timeout()

    assert privacy.pre_calls == 0
    assert ctrl._capture.calls == []
    assert ctrl._stable_timer.started == [15000]

    ctrl._platform_adapter = SimpleNamespace(get_frontmost_window_info=lambda: dict(second_window))
    ctrl._pending_window_info = dict(second_window)
    ctrl._pending_signature = CompanionController._build_signature(second_window)
    _FakeWorker.instances = []
    monkeypatch.setattr(companion_module, "_CaptureRecommendWorker", _FakeWorker)
    monkeypatch.setattr(companion_module.QTimer, "singleShot", lambda _delay, callback: callback())

    ctrl._on_stable_timeout()

    assert privacy.pre_calls == 1
    assert privacy.post_calls == 0
    assert ctrl._capture.calls == []
    assert len(_FakeWorker.instances) == 1
    assert suggestion_window.privacy_notices == []
