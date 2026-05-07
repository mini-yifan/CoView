from types import SimpleNamespace

from baodou_ai.gui.log_window import LogStream, LogWindow


class _FakeEmitter:
    def __init__(self):
        self.emitted = []

    def emit(self, text, log_type):
        self.emitted.append((text, log_type))


class _FakeSignalHandler:
    def __init__(self):
        self.log_signal = _FakeEmitter()


def test_log_stream_marks_stderr_lines_as_error():
    handler = _FakeSignalHandler()
    stream = LogStream(handler, "error")

    stream.write("traceback line\n")

    assert handler.log_signal.emitted == [("traceback line\n", "error")]


def test_log_stream_detects_error_keywords_in_stdout():
    handler = _FakeSignalHandler()
    stream = LogStream(handler, "normal")

    stream.write("发生错误: boom\n")

    assert handler.log_signal.emitted == [("发生错误: boom\n", "error")]


def test_log_stream_flush_emits_tail_without_newline():
    handler = _FakeSignalHandler()
    stream = LogStream(handler, "normal")

    stream.write("tail")
    stream.flush()

    assert handler.log_signal.emitted == [("tail", "normal")]


def test_log_window_flush_pending_logs_preserves_order():
    flushed = []
    timer = SimpleNamespace(stop=lambda: flushed.append(("timer", "stop")))
    window = SimpleNamespace(
        _pending_log_entries=[("first\n", "info"), ("second\n", "error")],
        _append_log_immediately=lambda text, log_type="normal": flushed.append((text, log_type)),
        _log_flush_timer=timer,
    )

    LogWindow._flush_pending_logs(window, force=True)

    assert flushed == [("timer", "stop"), ("first\n", "info"), ("second\n", "error")]
    assert window._pending_log_entries == []
