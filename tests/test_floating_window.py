import json
from pathlib import Path
from types import SimpleNamespace

from PyQt5.QtCore import QByteArray, QEvent, QPoint, QRect, Qt
from PyQt5.QtGui import QColor, QMouseEvent, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QComboBox, QPushButton, QWidget

from baodou_ai.core.config import Config
from baodou_ai.core.screenshot import CAPTURE_EXCLUDE_PROPERTY
from baodou_ai.gui.code_agent_window import CodeAgentJobWindow
from baodou_ai.gui.control_console import ControlConsoleWindow
from baodou_ai.gui.control_console_jobs import CodeAgentJobsPanel
from baodou_ai.gui.floating.ball import BallWindow, EdgeBarWindow
from baodou_ai.gui.floating.background_jobs_controller import BackgroundJobsController
from baodou_ai.gui.floating.controller import FloatingController
from baodou_ai.gui.floating.controller import _normalize_native_event_type
from baodou_ai.gui.floating.menu_controller import FloatingMenuController
from baodou_ai.gui.floating.overlay_window_coordinator import OverlayWindowCoordinator
from baodou_ai.gui.floating.panel import PanelWindow
from baodou_ai.gui.floating.platform_factory import (
    create_ball_window,
    create_edge_bar_window,
    create_panel_window,
    create_taskbar_host_window,
)
from baodou_ai.gui.floating.runtime_state_presenter import RuntimeStatePresenter
from baodou_ai.gui.floating.suggestion_window import SuggestionWindow
from baodou_ai.gui.floating.task_session_controller import TaskSessionController
from baodou_ai.gui.floating.task_session_host import FloatingTaskSessionHost
from baodou_ai.gui.floating.task_session_state import UITaskSessionState
from baodou_ai.gui.floating.windows_taskbar_host import WindowsTaskbarHostWindow
from baodou_ai.gui.frontmost_tracker import FrontmostAppTracker
from baodou_ai.gui.i18n import set_locale
from baodou_ai.gui.runtime_log import RuntimeLogBuffer
from baodou_ai.gui.floating.windows_widgets import (
    WindowsBallWindow,
    WindowsEdgeBarWindow,
    WindowsPanelWindow,
    WindowsSuggestionWindow,
    WindowsToastWindow,
)
from baodou_ai.voice.sherpa_keyword_spotter import WakeWordHit


class _FakePlatformAdapter:
    def __init__(self):
        self.enter_calls = []
        self.exit_calls = []
        self.prepare_calls = []

    def enter_transparent_mode(self, window):
        self.enter_calls.append(window)
        return True

    def exit_transparent_mode(self, window):
        self.exit_calls.append(window)
        return True

    def prepare_overlay_window(self, window):
        self.prepare_calls.append(window)


class _FakeController:
    def __init__(self, config=None):
        self.ball_size = 72
        self.ball_anchor = QPoint(20, 30)
        self.expanded_width = 320
        self.expanded_height = 420
        self.submitted = []
        self.stop_requests = 0
        self.is_pinned = False
        self._platform_adapter = _FakePlatformAdapter()
        self._config = config
        self.task_active = False
        self.interactions = []
        self.drag_started = 0
        self.drag_positions = []

    def handle_submit(self, text):
        self.submitted.append(text)

    def handle_stop_request(self):
        self.stop_requests += 1

    def keep_ball_on_top(self, *args, **kwargs):
        return None

    def protect_window(self, _window):
        return None

    def _task_active(self):
        return self.task_active

    def begin_interaction(self, reason):
        self.interactions.append(("begin", reason))

    def end_interaction(self, reason):
        self.interactions.append(("end", reason))

    def defer_pointer_interaction_end(self, delay_ms=350):
        self.interactions.append(("defer", "pointer", delay_ms))

    def on_ball_long_press(self):
        self.drag_started += 1

    def on_ball_drag(self, pos):
        self.drag_positions.append(QPoint(pos))


class _FakeNativeEventApp:
    def __init__(self):
        self.installed_filters = []
        self.removed_filters = []

    def installNativeEventFilter(self, event_filter):
        self.installed_filters.append(event_filter)

    def removeNativeEventFilter(self, event_filter):
        self.removed_filters.append(event_filter)


class _FakeUser32Hotkey:
    def __init__(self, register_results=None):
        self.register_results = list(register_results or [])
        self.register_calls = []
        self.unregister_calls = []

    def RegisterHotKey(self, hwnd, hotkey_id, modifiers, virtual_key):
        self.register_calls.append((hwnd, hotkey_id, modifiers, virtual_key))
        if self.register_results:
            return self.register_results.pop(0)
        return True

    def UnregisterHotKey(self, hwnd, hotkey_id):
        self.unregister_calls.append((hwnd, hotkey_id))
        return True


class _FakeWinId:
    def __init__(self, value):
        self._value = value

    def __int__(self):
        return self._value


class _FakeHotkeyWindow:
    def __init__(self, hwnd=123456):
        self._hwnd = hwnd

    def winId(self):
        return _FakeWinId(self._hwnd)


class _FakeInputArea:
    def __init__(self):
        self.focus_calls = []
        self.visible = True

    def isVisible(self):
        return self.visible

    def setFocus(self, reason=None):
        self.focus_calls.append(reason)


class _FakeFocusablePanel:
    def __init__(self):
        self.target_visible = True
        self.input_area = _FakeInputArea()
        self.raise_calls = 0
        self.activate_calls = 0

    def raise_(self):
        self.raise_calls += 1

    def activateWindow(self):
        self.activate_calls += 1


class _FakeAudioLifecycleController:
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


class _FakeWakeWordController(_FakeAudioLifecycleController):
    def refresh_config(self):
        return True

    def shutdown(self):
        self.running = False


def _record_wake_word_tts(controller, text, done_event):
    spoken = list(getattr(controller, "_wake_word_tts_spoken", []))
    spoken.append(text)
    controller._wake_word_tts_spoken = spoken
    controller._tts.current_done_event = done_event
    controller._tts.current_text = text
    return done_event


def _patch_fake_movie(monkeypatch, calls):
    class _FakeSignal:
        def connect(self, callback):
            calls.append(("connect", callback))

    class _FakeMovie:
        CacheAll = object()

        def __init__(self, path):
            self.path = path
            self.frameChanged = _FakeSignal()

        def isValid(self):
            return True

        def setCacheMode(self, mode):
            calls.append(("cache", mode))

        def jumpToFrame(self, frame):
            calls.append(("jump", frame))

        def start(self):
            calls.append(("start", None))

        def stop(self):
            calls.append(("stop", None))

        def currentPixmap(self):
            pixmap = QPixmap(8, 8)
            pixmap.fill(QColor("#ffffff"))
            return pixmap

        def deleteLater(self):
            calls.append(("delete", None))

    monkeypatch.setattr("baodou_ai.gui.floating.ball.QMovie", _FakeMovie)


def test_floating_windows_toggle_transparent_mode_through_platform_adapter():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    controller = _FakeController()
    ball = BallWindow(controller)
    panel = PanelWindow(controller)
    edge = EdgeBarWindow(controller)

    ball.show()
    panel.show()
    edge.show()
    app.processEvents()

    ball.enter_transparent_mode()
    panel.enter_transparent_mode()
    edge.enter_transparent_mode()

    assert controller._platform_adapter.enter_calls == [ball, panel, edge]

    ball.exit_transparent_mode()
    panel.exit_transparent_mode()
    edge.exit_transparent_mode()

    assert controller._platform_adapter.exit_calls == [ball, panel, edge]

    ball.close()
    panel.close()
    edge.close()


def test_platform_factory_uses_windows_specific_widgets(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    monkeypatch.setattr("baodou_ai.gui.floating.platform_factory.platform.system", lambda: "Windows")
    controller = _FakeController()

    ball = create_ball_window(controller)
    panel = create_panel_window(controller)
    edge = create_edge_bar_window(controller)
    host = create_taskbar_host_window(controller)

    assert isinstance(ball, WindowsBallWindow)
    assert isinstance(panel, WindowsPanelWindow)
    assert isinstance(edge, WindowsEdgeBarWindow)
    assert isinstance(host, WindowsTaskbarHostWindow)

    ball.close()
    panel.close()
    edge.close()
    host.allow_shutdown_close()
    host.close()


def test_platform_factory_keeps_existing_widgets_for_macos(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    monkeypatch.setattr("baodou_ai.gui.floating.platform_factory.platform.system", lambda: "Darwin")
    controller = _FakeController()

    ball = create_ball_window(controller)
    panel = create_panel_window(controller)
    edge = create_edge_bar_window(controller)
    host = create_taskbar_host_window(controller)

    assert type(ball) is BallWindow
    assert type(panel) is PanelWindow
    assert type(edge) is EdgeBarWindow
    assert host is None

    ball.close()
    panel.close()
    edge.close()


def test_windows_taskbar_host_window_close_triggers_controller_shutdown():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    shutdown_calls = []
    controller = SimpleNamespace(
        shutdown=lambda: shutdown_calls.append(True),
        open_console_page=lambda _page_id="general": None,
    )
    window = WindowsTaskbarHostWindow(controller)

    try:
        assert window.close() is False
        assert shutdown_calls == [True]
    finally:
        window.allow_shutdown_close()
        window.close()


def test_ball_mouse_move_enters_drag_after_press_delay(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    controller = _FakeController()
    ball = BallWindow(controller)
    local_pos = QPoint(ball.shadow_margin + 12, ball.shadow_margin + 12)
    start_global = QPoint(100, 120)
    move_global = QPoint(101, 121)
    times = iter([1000.0, 1000.21])
    monkeypatch.setattr("baodou_ai.gui.floating.ball.time.monotonic", lambda: next(times))

    press = QMouseEvent(
        QEvent.MouseButtonPress,
        local_pos,
        start_global,
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    move = QMouseEvent(
        QEvent.MouseMove,
        local_pos + QPoint(1, 1),
        move_global,
        Qt.NoButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )

    ball.mousePressEvent(press)
    ball.mouseMoveEvent(move)

    assert controller.drag_started == 1
    assert controller.drag_positions == [move_global - (start_global - controller.ball_anchor)]
    assert ("begin", "pointer") in controller.interactions
    ball.close()


def test_floating_menu_skips_confirmation_on_windows(monkeypatch):
    monkeypatch.setattr("baodou_ai.gui.floating.menu_controller.platform.system", lambda: "Windows")
    controller = FloatingMenuController(lambda: None, lambda: None, lambda: None)

    assert controller._skip_confirmation_dialogs() is True


def test_floating_menu_keeps_confirmation_on_macos(monkeypatch):
    monkeypatch.setattr("baodou_ai.gui.floating.menu_controller.platform.system", lambda: "Darwin")
    controller = FloatingMenuController(lambda: None, lambda: None, lambda: None)

    assert controller._skip_confirmation_dialogs() is False


def test_floating_menu_uses_popup_and_marks_interaction(monkeypatch):
    events = []

    class _FakeSignal:
        def __init__(self):
            self.callbacks = []

        def connect(self, callback):
            self.callbacks.append(callback)

        def emit(self):
            for callback in list(self.callbacks):
                callback()

    class _FakeAction:
        def __init__(self, text=""):
            self.text = text
            self.triggered = _FakeSignal()

        def setText(self, text):
            self.text = text

    class _FakeMenu:
        def __init__(self):
            self.aboutToShow = _FakeSignal()
            self.aboutToHide = _FakeSignal()
            self.popup_calls = []

        def setStyleSheet(self, _style):
            return None

        def addAction(self, text):
            return _FakeAction(text)

        def addSeparator(self):
            return None

        def popup(self, pos):
            self.popup_calls.append(QPoint(pos))
            self.aboutToShow.emit()

    monkeypatch.setattr("baodou_ai.gui.floating.menu_controller.QMenu", _FakeMenu)
    controller = FloatingMenuController(
        lambda *_args: None,
        lambda: None,
        lambda: None,
        begin_interaction=lambda reason: events.append(("begin", reason)),
        end_interaction=lambda reason: events.append(("end", reason)),
    )

    controller.show_ball_context_menu(QPoint(10, 20))
    controller._menu.aboutToHide.emit()

    assert controller._menu.popup_calls == [QPoint(10, 20)]
    assert events == [("begin", "menu"), ("end", "menu")]


def test_floating_menu_localizes_companion_toggle_action(monkeypatch):
    class _FakeSignal:
        def __init__(self):
            self.callbacks = []

        def connect(self, callback):
            self.callbacks.append(callback)

        def emit(self):
            for callback in list(self.callbacks):
                callback()

    class _FakeAction:
        def __init__(self, text=""):
            self.text = text
            self.triggered = _FakeSignal()

        def setText(self, text):
            self.text = text

    class _FakeMenu:
        def __init__(self):
            self.aboutToShow = _FakeSignal()
            self.aboutToHide = _FakeSignal()
            self.actions = []

        def setStyleSheet(self, _style):
            return None

        def addAction(self, text):
            action = _FakeAction(text)
            self.actions.append(action)
            return action

        def addSeparator(self):
            return None

        def popup(self, _pos):
            self.aboutToShow.emit()

    monkeypatch.setattr("baodou_ai.gui.floating.menu_controller.QMenu", _FakeMenu)

    try:
        set_locale("zh_CN")
        controller = FloatingMenuController(
            lambda *_args: None,
            lambda: None,
            lambda: None,
            is_companion_enabled=lambda: True,
        )
        controller.show_ball_context_menu(QPoint(0, 0))
        assert [action.text for action in controller._menu.actions] == [
            "查看执行情况",
            "设置",
            "关闭智能推荐",
            "清除历史",
            "关闭程序",
        ]

        set_locale("en_US")
        controller.show_ball_context_menu(QPoint(0, 0))
        assert [action.text for action in controller._menu.actions] == [
            "View Execution",
            "Settings",
            "Disable Companion Suggestions",
            "Clear History",
            "Quit",
        ]
    finally:
        set_locale("zh_CN")


def test_overlay_expand_defers_history_loading(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    scheduled = []
    operations = []

    class _FakePanel:
        def __init__(self):
            self.target_visible = False
            self.pinned_active = False

        def set_direction(self, *_args):
            return None

        def show_expanding(self, _anchor):
            self.target_visible = True
            operations.append("show")

        def is_animating(self):
            return False

        def isVisible(self):
            return self.target_visible

        def geometry(self):
            return QRect()

    monkeypatch.setattr(
        "baodou_ai.gui.floating.overlay_window_coordinator.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    controller = SimpleNamespace(
        ball_window=QWidget(),
        panel_window=_FakePanel(),
        ball_anchor=QPoint(100, 100),
        ball_size=72,
        expanded_height=420,
        is_pinned=False,
        is_dragging=False,
        is_edge_hidden=False,
        expand_direction="left",
        v_expand_direction="up",
        begin_interaction=lambda reason: operations.append(("begin", reason)),
        _task_active=lambda: False,
        keep_ball_on_top=lambda *args, **kwargs: operations.append("top"),
        _sync_voice_interaction_state=lambda: None,
        _reposition_companion_window=lambda: None,
        _show_history_if_idle=lambda: operations.append("history"),
    )
    coordinator = OverlayWindowCoordinator(controller)

    coordinator.expand()

    assert operations == [("begin", "panel"), "show", "top"]
    assert len(scheduled) == 1
    assert scheduled[0][0] == 50
    scheduled[0][1]()
    assert operations[-1] == "history"


def test_floating_controller_registers_windows_global_hotkeys(monkeypatch):
    fake_app = _FakeNativeEventApp()
    fake_user32 = _FakeUser32Hotkey()
    controller = FloatingController.__new__(FloatingController)
    controller.app = fake_app
    controller._log_buffer = RuntimeLogBuffer()
    controller.ball_window = _FakeHotkeyWindow(hwnd=123456)
    controller._windows_user32 = None
    controller._windows_hotkey_hwnd = None
    controller._windows_registered_hotkey_ids = []
    controller._windows_hotkey_filter = None

    monkeypatch.setattr("baodou_ai.gui.floating.controller.sys.platform", "win32")
    monkeypatch.setattr(
        "baodou_ai.gui.floating.controller._get_windows_user32",
        lambda: fake_user32,
    )

    controller._setup_global_hotkey()

    assert fake_user32.register_calls == [
        (
            123456,
            FloatingController._WINDOWS_HOTKEY_ACTIVATE_ID,
            FloatingController._WINDOWS_MOD_CONTROL
            | FloatingController._WINDOWS_MOD_ALT
            | FloatingController._WINDOWS_MOD_NOREPEAT,
            FloatingController._WINDOWS_VK_SPACE,
        ),
        (
            123456,
            FloatingController._WINDOWS_HOTKEY_HIDE_ID,
            FloatingController._WINDOWS_MOD_CONTROL
            | FloatingController._WINDOWS_MOD_ALT
            | FloatingController._WINDOWS_MOD_NOREPEAT,
            FloatingController._WINDOWS_VK_RETURN,
        ),
    ]
    assert controller._windows_registered_hotkey_ids == [
        FloatingController._WINDOWS_HOTKEY_ACTIVATE_ID,
        FloatingController._WINDOWS_HOTKEY_HIDE_ID,
    ]
    assert controller._windows_hotkey_hwnd == 123456
    assert fake_app.installed_filters == [controller._windows_hotkey_filter]


def test_floating_controller_teardown_unregisters_windows_global_hotkeys(monkeypatch):
    fake_app = _FakeNativeEventApp()
    fake_user32 = _FakeUser32Hotkey()
    controller = FloatingController.__new__(FloatingController)
    controller.app = fake_app
    controller._log_buffer = RuntimeLogBuffer()
    controller.ball_window = _FakeHotkeyWindow(hwnd=654321)
    controller._windows_user32 = None
    controller._windows_hotkey_hwnd = None
    controller._windows_registered_hotkey_ids = []
    controller._windows_hotkey_filter = None

    monkeypatch.setattr("baodou_ai.gui.floating.controller.sys.platform", "win32")
    monkeypatch.setattr(
        "baodou_ai.gui.floating.controller._get_windows_user32",
        lambda: fake_user32,
    )

    controller._setup_global_hotkey()
    installed_filter = controller._windows_hotkey_filter
    controller._teardown_global_hotkey()

    assert fake_app.removed_filters == [installed_filter]
    assert fake_user32.unregister_calls == [
        (654321, FloatingController._WINDOWS_HOTKEY_ACTIVATE_ID),
        (654321, FloatingController._WINDOWS_HOTKEY_HIDE_ID),
    ]
    assert controller._windows_registered_hotkey_ids == []
    assert controller._windows_hotkey_hwnd is None
    assert controller._windows_user32 is None
    assert controller._windows_hotkey_filter is None


def test_floating_controller_dispatches_windows_hotkey_ids(monkeypatch):
    operations = []
    controller = FloatingController.__new__(FloatingController)
    controller.activate_from_hotkey = lambda: operations.append("activate")
    controller.collapse_from_hotkey = lambda: operations.append("collapse")
    monkeypatch.setattr(
        "baodou_ai.gui.floating.controller.QTimer.singleShot",
        lambda _delay, callback: callback(),
    )

    assert controller._handle_windows_hotkey_id(FloatingController._WINDOWS_HOTKEY_ACTIVATE_ID)
    assert controller._handle_windows_hotkey_id(FloatingController._WINDOWS_HOTKEY_HIDE_ID)
    assert not controller._handle_windows_hotkey_id(999999)
    assert operations == ["activate", "collapse"]


def test_windows_native_event_type_normalizes_qbytearray():
    assert _normalize_native_event_type(QByteArray(b"windows_generic_MSG")) == "windows_generic_MSG"


def test_windows_activate_hotkey_focuses_panel_input(monkeypatch):
    operations = []
    delayed_focus_calls = []
    controller = FloatingController.__new__(FloatingController)
    controller.panel_window = _FakeFocusablePanel()
    controller.activate_from_hotkey = lambda: operations.append("activate")
    monkeypatch.setattr(
        "baodou_ai.gui.floating.controller.QTimer.singleShot",
        lambda delay, callback: delayed_focus_calls.append(delay),
    )

    controller._activate_from_windows_hotkey()

    assert operations == ["activate"]
    assert controller.panel_window.raise_calls == 1
    assert controller.panel_window.activate_calls == 1
    assert len(controller.panel_window.input_area.focus_calls) == 1
    assert delayed_focus_calls == [120, 420]


def test_collapse_from_hotkey_only_collapses_panel(monkeypatch):
    operations = []
    controller = FloatingController.__new__(FloatingController)
    controller.is_pinned = True
    controller.is_edge_hidden = False
    controller.collapse_timer = SimpleNamespace(stop=lambda: operations.append("timer_stop"))
    controller.panel_window = SimpleNamespace(
        pinned_active=True,
        update=lambda: operations.append("panel_update"),
    )
    controller.ball_window = SimpleNamespace(update=lambda: operations.append("ball_update"))
    controller._mark_voice_user_interaction = lambda: operations.append("mark")
    controller._task_active = lambda: False
    controller._sync_voice_interaction_state = lambda: operations.append("sync")
    controller.collapse_instantly = lambda: operations.append("collapse")
    controller.snap_to_edge = lambda edge: operations.append(("snap", edge))

    controller.collapse_from_hotkey()

    assert controller.is_pinned is False
    assert controller.panel_window.pinned_active is False
    assert operations == [
        "mark",
        "ball_update",
        "panel_update",
        "sync",
        "timer_stop",
        "collapse",
    ]


def test_handle_voice_exit_command_force_stops_and_collapses_when_busy():
    operations = []
    controller = FloatingController.__new__(FloatingController)
    controller.is_pinned = True
    controller.panel_window = SimpleNamespace(
        target_visible=True,
        pinned_active=True,
        update=lambda: operations.append("panel_update"),
    )
    controller.ball_window = SimpleNamespace(update=lambda: operations.append("ball_update"))
    controller.collapse_timer = SimpleNamespace(stop=lambda: operations.append("timer_stop"))
    controller._task_session_controller = SimpleNamespace(
        handle_voice_exit_request=lambda: operations.append("voice_exit_request")
    )
    controller._log_buffer = SimpleNamespace(
        append_log=lambda text, level: operations.append(("log", text, level))
    )
    controller._hide_companion_suggestions = lambda: operations.append("hide_suggestions")
    controller.collapse_instantly = lambda: operations.append("collapse")

    controller.handle_voice_exit_command()

    assert controller.is_pinned is False
    assert controller.panel_window.pinned_active is False
    assert operations == [
        "voice_exit_request",
        "ball_update",
        "panel_update",
        ("log", "[VOICE] 收到退出程序口令，强制停止并收起显示框\n", "warning"),
        "hide_suggestions",
        "timer_stop",
        "collapse",
    ]


def test_sync_voice_interaction_state_starts_wake_word_when_unpinned():
    controller = FloatingController.__new__(FloatingController)
    controller._config = Config.create_isolated()
    controller._voice = _FakeAudioLifecycleController()
    controller._wake_word = _FakeWakeWordController()
    controller.is_pinned = False
    controller.is_edge_hidden = False
    controller.panel_window = SimpleNamespace(target_visible=False)
    controller._task_active = lambda: False
    controller._is_waiting_for_tts = lambda: False

    controller._sync_voice_interaction_state()

    assert controller._voice.start_calls == 0
    assert controller._voice.stop_calls == 0
    assert controller._wake_word.start_calls == 1
    assert controller._wake_word.stop_calls == 0


def test_sync_voice_interaction_state_does_not_restart_running_wake_word():
    controller = FloatingController.__new__(FloatingController)
    controller._config = Config.create_isolated()
    controller._config.set("voice_interaction_config.enabled", True)
    controller._config.set("wake_word_config.enabled", True)
    controller._voice = _FakeAudioLifecycleController()
    controller._wake_word = _FakeWakeWordController()
    controller._wake_word.running = True
    controller.is_pinned = False
    controller.is_edge_hidden = False
    controller.panel_window = SimpleNamespace(target_visible=False)
    controller._task_active = lambda: False
    controller._is_waiting_for_tts = lambda: False

    controller._sync_voice_interaction_state()

    assert controller._wake_word.start_calls == 0
    assert controller._wake_word.stop_calls == 0


def test_wake_word_hit_activates_voice_chain_and_stops_wake_word():
    try:
        set_locale("en_US")
        controller = FloatingController.__new__(FloatingController)
        controller._config = Config.create_isolated()
        controller._config.set("voice_interaction_config.enabled", True)
        controller._config.set("wake_word_config.enabled", True)
        controller._config.set("locale_config.locale", "en_US")
        controller._voice = _FakeAudioLifecycleController()
        controller._wake_word = _FakeWakeWordController()
        done_event = SimpleNamespace(is_set=lambda: True)
        controller._tts = SimpleNamespace(
            current_done_event=None,
            current_text="",
            speak=lambda text: _record_wake_word_tts(controller, text, done_event),
        )
        controller.is_pinned = False
        controller.is_edge_hidden = False
        controller.panel_window = SimpleNamespace(target_visible=False)
        controller._task_active = lambda: False
        controller._is_waiting_for_tts = lambda: False

        activations = []

        def _activate():
            activations.append(True)
            controller.is_pinned = True
            controller.panel_window.target_visible = True

        controller.activate_from_hotkey = _activate

        from baodou_ai.gui.floating import controller as controller_module

        original_single_shot = controller_module.QTimer.singleShot
        controller_module.QTimer.singleShot = lambda _delay, callback: callback()
        try:
            controller._handle_wake_word_hit(
                WakeWordHit(text="hey Lucy", language="en", score=0.9, detected_at=1.0)
            )
        finally:
            controller_module.QTimer.singleShot = original_single_shot

        assert activations == [True]
        assert controller._wake_word_tts_spoken == ["I'm here"]
        assert controller._voice.start_calls == 1
        assert controller._wake_word.stop_calls == 1
        assert controller._wake_word.start_calls == 0
        assert controller._tts.current_done_event is None
        assert controller._tts.current_text == ""
        assert controller._active_wake_word_language == "en"
    finally:
        set_locale("zh_CN")


def test_wake_word_hit_sets_chinese_voice_session_language():
    controller = FloatingController.__new__(FloatingController)
    controller._config = Config.create_isolated()
    controller._voice = _FakeAudioLifecycleController()
    controller._wake_word = _FakeWakeWordController()
    controller._tts = SimpleNamespace(
        current_done_event=None,
        current_text="",
        speak=lambda _text: None,
    )
    controller.is_pinned = False
    controller.is_edge_hidden = False
    controller.panel_window = SimpleNamespace(target_visible=False)
    controller._task_active = lambda: False
    controller._is_waiting_for_tts = lambda: False

    def _activate():
        controller.is_pinned = True
        controller.panel_window.target_visible = True

    controller.activate_from_hotkey = _activate

    controller._handle_wake_word_hit(
        WakeWordHit(text="你好小彤", language="zh", score=0.9, detected_at=1.0)
    )

    assert controller._active_wake_word_language == "zh"


def test_sync_voice_interaction_state_restores_wake_word_after_voice_chain_ends():
    controller = FloatingController.__new__(FloatingController)
    controller._config = Config.create_isolated()
    controller._config.set("voice_interaction_config.enabled", True)
    controller._config.set("wake_word_config.enabled", True)
    controller._voice = _FakeAudioLifecycleController()
    controller._wake_word = _FakeWakeWordController()
    controller.is_pinned = True
    controller.is_edge_hidden = False
    controller.panel_window = SimpleNamespace(target_visible=True)
    controller._task_active = lambda: False
    controller._is_waiting_for_tts = lambda: False

    controller._sync_voice_interaction_state()

    controller.is_pinned = False
    controller.panel_window.target_visible = False
    controller._sync_voice_interaction_state()

    assert controller._voice.start_calls == 1
    assert controller._voice.stop_calls == 1
    assert controller._wake_word.stop_calls == 1
    assert controller._wake_word.start_calls == 1


def test_sync_voice_interaction_state_keeps_pinned_voice_available_after_wake_word_degrades():
    controller = FloatingController.__new__(FloatingController)
    controller._config = Config.create_isolated()
    controller._voice = _FakeAudioLifecycleController()
    controller._wake_word = _FakeWakeWordController()
    controller._wake_word.running = False
    controller._wake_word.state = "degraded"
    controller.is_pinned = True
    controller.is_edge_hidden = False
    controller.panel_window = SimpleNamespace(target_visible=True)
    controller._task_active = lambda: False
    controller._is_waiting_for_tts = lambda: False

    controller._sync_voice_interaction_state()

    assert controller._voice.start_calls == 1
    assert controller._voice.stop_calls == 0
    assert controller._wake_word.stop_calls == 1
    assert controller._wake_word.start_calls == 0


def test_floating_controller_protect_window_sets_capture_exclusion_property():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    protected = []
    controller = FloatingController.__new__(FloatingController)
    controller._platform_adapter = SimpleNamespace(setup_window=lambda window: protected.append(window))
    window = QLabel("floating")

    controller.protect_window(window)

    assert window.property(CAPTURE_EXCLUDE_PROPERTY) is True
    assert protected == [window]


def test_ball_window_apply_mode_preserves_no_activate_flags():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    controller = _FakeController()
    ball = BallWindow(controller)

    assert bool(ball.windowFlags() & Qt.WindowDoesNotAcceptFocus)
    assert ball.testAttribute(Qt.WA_ShowWithoutActivating)

    ball._apply_window_mode()

    assert bool(ball.windowFlags() & Qt.WindowDoesNotAcceptFocus)
    assert ball.testAttribute(Qt.WA_ShowWithoutActivating)
    ball.close()


def test_keep_ball_on_top_does_not_raise_collapsing_panel():
    class _FakeBall:
        def __init__(self):
            self.apply_calls = 0
            self.show_calls = 0
            self.raise_calls = 0
            self.update_calls = 0

        def _apply_window_mode(self):
            self.apply_calls += 1

        def isVisible(self):
            return True

        def show(self):
            self.show_calls += 1

        def raise_(self):
            self.raise_calls += 1

        def update(self):
            self.update_calls += 1

    class _FakePanel:
        target_visible = False

        def __init__(self):
            self.raise_calls = 0

        def isVisible(self):
            return True

        def raise_(self):
            self.raise_calls += 1

    controller = FloatingController.__new__(FloatingController)
    controller.is_edge_hidden = False
    controller.ball_window = _FakeBall()
    controller.panel_window = _FakePanel()
    controller.edge_bar = SimpleNamespace(isVisible=lambda: False, raise_=lambda: None)
    controller._companion = None
    controller.toast_window = SimpleNamespace(reposition=lambda _anchor: None)
    controller.ball_anchor = QPoint(100, 100)

    controller.keep_ball_on_top()

    assert controller.panel_window.raise_calls == 0
    assert controller.ball_window.raise_calls == 1


def test_collapse_instantly_does_not_raise_overlay_windows():
    class _FakePanel:
        def __init__(self):
            self.hide_calls = 0
            self.raise_calls = 0
            self.target_visible = False

        def hide_immediately(self):
            self.hide_calls += 1

        def isVisible(self):
            return True

        def raise_(self):
            self.raise_calls += 1

    class _FakeBall:
        def __init__(self):
            self.apply_calls = 0
            self.raise_calls = 0
            self.update_calls = 0

        def _apply_window_mode(self):
            self.apply_calls += 1

        def isVisible(self):
            return True

        def show(self):
            raise AssertionError("visible ball should not be shown again")

        def raise_(self):
            self.raise_calls += 1

        def update(self):
            self.update_calls += 1

    controller = FloatingController.__new__(FloatingController)
    controller.is_edge_hidden = False
    controller.collapse_timer = SimpleNamespace(stop=lambda: None)
    controller.panel_window = _FakePanel()
    controller.ball_window = _FakeBall()
    controller.edge_bar = SimpleNamespace(isVisible=lambda: True, raise_=lambda: (_ for _ in ()).throw(AssertionError("edge bar should not raise")))
    controller._sync_voice_interaction_state = lambda: None
    controller._companion = None
    controller.toast_window = SimpleNamespace(reposition=lambda _anchor: None)
    controller.ball_anchor = QPoint(100, 100)

    controller.collapse_instantly()

    assert controller.panel_window.hide_calls == 1
    assert controller.panel_window.raise_calls == 0
    assert controller.ball_window.raise_calls == 0
    assert controller.ball_window.update_calls == 1


def test_overlay_coordinator_drag_moves_ball_immediately_and_defers_follow_updates():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    operations = []

    class _FakeBallWidget(QWidget):
        shadow_margin = 5

        def __init__(self):
            super().__init__()
            self.move_calls = []
            self.resize(82, 82)

        def move_to_anchor(self, anchor):
            point = QPoint(anchor)
            self.move_calls.append(point)
            self.move(point.x(), point.y())

        def global_ball_rect(self):
            return self.geometry()

        def _apply_window_mode(self):
            return None

    class _FakePanelWidget(QWidget):
        target_visible = True
        pinned_active = False

        def __init__(self):
            super().__init__()
            self.reposition_calls = []

        def reposition_for_anchor(self, anchor):
            self.reposition_calls.append(QPoint(anchor))

        def is_animating(self):
            return False

        def hide_immediately(self):
            return None

    controller = SimpleNamespace(
        ball_window=_FakeBallWidget(),
        panel_window=_FakePanelWidget(),
        ball_size=72,
        expanded_width=320,
        expanded_height=420,
        ball_anchor=QPoint(0, 0),
        is_edge_hidden=False,
        is_dragging=True,
        is_pinned=False,
        edge_bar=SimpleNamespace(isVisible=lambda: False, raise_=lambda: None),
        _mark_voice_user_interaction=lambda: operations.append("mark"),
        keep_ball_on_top=lambda *args, **kwargs: operations.append(("keep", kwargs)),
        _reposition_companion_window=lambda: operations.append("companion"),
        _reposition_toast_window=lambda: operations.append("toast"),
        _task_active=lambda: False,
        _is_waiting_for_tts=lambda: False,
        _sync_voice_interaction_state=lambda: None,
        _hide_toast_window=lambda: None,
        _hide_companion_suggestions=lambda: None,
    )
    coordinator = OverlayWindowCoordinator(controller)

    coordinator.on_ball_drag(QPoint(120, 160))

    assert controller.ball_anchor == QPoint(120, 160)
    assert controller.ball_window.move_calls == [QPoint(120, 160)]
    assert controller.panel_window.reposition_calls == []
    assert ("keep", {"raise_windows": False, "sync_helpers": False}) not in operations
    assert "companion" not in operations
    assert "toast" not in operations
    assert coordinator._pending_drag_anchor == QPoint(120, 160)
    assert coordinator.drag_follow_timer.isActive() is True


def test_overlay_coordinator_flush_drag_follow_updates_batches_helper_work():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    operations = []

    class _FakeBallWidget(QWidget):
        shadow_margin = 5

        def __init__(self):
            super().__init__()
            self.resize(82, 82)

        def move_to_anchor(self, anchor):
            self.move(anchor.x(), anchor.y())

        def global_ball_rect(self):
            return self.geometry()

        def _apply_window_mode(self):
            return None

    class _FakePanelWidget(QWidget):
        target_visible = True
        pinned_active = False

        def __init__(self):
            super().__init__()
            self.reposition_calls = []

        def reposition_for_anchor(self, anchor):
            self.reposition_calls.append(QPoint(anchor))

        def is_animating(self):
            return False

        def hide_immediately(self):
            return None

    controller = SimpleNamespace(
        ball_window=_FakeBallWidget(),
        panel_window=_FakePanelWidget(),
        ball_size=72,
        expanded_width=320,
        expanded_height=420,
        ball_anchor=QPoint(140, 180),
        is_edge_hidden=False,
        is_dragging=True,
        is_pinned=False,
        edge_bar=SimpleNamespace(isVisible=lambda: False, raise_=lambda: None),
        _mark_voice_user_interaction=lambda: None,
        keep_ball_on_top=lambda *args, **kwargs: operations.append(("keep", kwargs)),
        _reposition_companion_window=lambda: operations.append("companion"),
        _reposition_toast_window=lambda: operations.append("toast"),
        _task_active=lambda: False,
        _is_waiting_for_tts=lambda: False,
        _sync_voice_interaction_state=lambda: None,
        _hide_toast_window=lambda: None,
        _hide_companion_suggestions=lambda: None,
    )
    coordinator = OverlayWindowCoordinator(controller)
    coordinator._pending_drag_anchor = QPoint(controller.ball_anchor)

    coordinator._flush_drag_follow_updates()

    assert controller.panel_window.reposition_calls == [QPoint(140, 180)]
    assert operations == [("keep", {"raise_windows": False, "sync_helpers": False}), "companion", "toast"]
    assert coordinator._pending_drag_anchor is None


def test_overlay_coordinator_drag_finished_forces_final_sync(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    operations = []

    class _FakeBallWidget(QWidget):
        shadow_margin = 5

        def __init__(self):
            super().__init__()
            self.resize(82, 82)

        def move_to_anchor(self, anchor):
            self.move(anchor.x(), anchor.y())

        def global_ball_rect(self):
            return self.geometry()

        def _apply_window_mode(self):
            return None

    class _FakePanelWidget(QWidget):
        target_visible = True
        pinned_active = False

        def __init__(self):
            super().__init__()
            self.reposition_calls = []

        def reposition_for_anchor(self, anchor):
            self.reposition_calls.append(QPoint(anchor))

        def is_animating(self):
            return False

        def hide_immediately(self):
            return None

    controller = SimpleNamespace(
        ball_window=_FakeBallWidget(),
        panel_window=_FakePanelWidget(),
        ball_size=72,
        expanded_width=320,
        expanded_height=420,
        ball_anchor=QPoint(210, 260),
        is_edge_hidden=False,
        is_dragging=True,
        is_pinned=False,
        edge_bar=SimpleNamespace(isVisible=lambda: False, raise_=lambda: None),
        _mark_voice_user_interaction=lambda: operations.append("mark"),
        keep_ball_on_top=lambda *args, **kwargs: operations.append(("keep", kwargs)),
        _reposition_companion_window=lambda: operations.append("companion"),
        _reposition_toast_window=lambda: operations.append("toast"),
        _task_active=lambda: False,
        _is_waiting_for_tts=lambda: False,
        _sync_voice_interaction_state=lambda: None,
        _hide_toast_window=lambda: None,
        _hide_companion_suggestions=lambda: None,
    )
    coordinator = OverlayWindowCoordinator(controller)
    coordinator._pending_drag_anchor = QPoint(controller.ball_anchor)

    monkeypatch.setattr(coordinator, "check_edge_snap", lambda: None)
    monkeypatch.setattr("baodou_ai.gui.floating.overlay_window_coordinator.QCursor.pos", lambda: QPoint(-999, -999))

    coordinator.on_ball_drag_finished()

    assert controller.is_dragging is False
    assert controller.panel_window.reposition_calls == [QPoint(210, 260)]
    assert operations == [
        "mark",
        ("keep", {"raise_windows": False, "sync_helpers": False}),
        "companion",
        "toast",
        ("keep", {}),
    ]
    assert coordinator._pending_drag_anchor is None


def test_edge_bar_hover_unsnaps_after_showing_at_edge(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    controller = _FakeController()
    controller.unsnapped_positions = []
    controller.unsnap_from_edge = lambda pos: controller.unsnapped_positions.append(pos)
    edge = EdgeBarWindow(controller)

    screen = app.primaryScreen()
    geometry = screen.geometry()
    edge.show_at_edge("right", QPoint(geometry.right() - controller.ball_size, geometry.center().y()))
    app.processEvents()

    hover_pos = edge.geometry().center()
    monkeypatch.setattr("baodou_ai.gui.floating.ball.QCursor.pos", lambda: hover_pos)
    edge._check_hover()

    assert controller.unsnapped_positions == [hover_pos]
    edge.close()


def test_ball_window_loads_static_custom_asset(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    asset_path = tmp_path / "ball.png"
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor("#ffffff"))
    assert pixmap.save(str(asset_path))

    config = Config.create_isolated(str(tmp_path / "config.json"))
    config.set("floating_ball_config.asset_path", str(asset_path))
    controller = _FakeController(config=config)

    ball = BallWindow(controller)

    assert ball._static_pixmap is not None
    assert not ball._static_pixmap.isNull()
    assert ball._movie is None
    ball.close()


def test_ball_window_plays_gif_on_hover_and_resets_on_leave(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    gif_path = tmp_path / "ball.gif"
    gif_path.write_bytes(b"GIF89a")
    calls = []
    _patch_fake_movie(monkeypatch, calls)

    config = Config.create_isolated(str(tmp_path / "config.json"))
    config.set("floating_ball_config.asset_path", str(gif_path))
    controller = _FakeController(config=config)
    ball = BallWindow(controller)
    ball.show()
    app.processEvents()

    ball.enterEvent(QEvent(QEvent.Enter))
    ball.leaveEvent(QEvent(QEvent.Leave))

    assert ("start", None) in calls
    assert ("stop", None) in calls
    assert calls.count(("jump", 0)) >= 2
    ball._clear_asset()
    ball.close()


def test_ball_window_always_play_setting_keeps_gif_running(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    gif_path = tmp_path / "ball.gif"
    gif_path.write_bytes(b"GIF89a")
    calls = []
    _patch_fake_movie(monkeypatch, calls)

    config = Config.create_isolated(str(tmp_path / "config.json"))
    config.set("floating_ball_config.asset_path", str(gif_path))
    config.set("floating_ball_config.animation_always_play", True)
    controller = _FakeController(config=config)
    ball = BallWindow(controller)
    ball.show()
    app.processEvents()

    stop_count = calls.count(("stop", None))
    ball.leaveEvent(QEvent(QEvent.Leave))

    assert ("start", None) in calls
    assert calls.count(("stop", None)) == stop_count
    ball._clear_asset()
    ball.close()


def test_ball_window_plays_gif_while_task_is_active(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    gif_path = tmp_path / "ball.gif"
    gif_path.write_bytes(b"GIF89a")
    calls = []
    _patch_fake_movie(monkeypatch, calls)

    config = Config.create_isolated(str(tmp_path / "config.json"))
    config.set("floating_ball_config.asset_path", str(gif_path))
    controller = _FakeController(config=config)
    controller.task_active = True
    ball = BallWindow(controller)
    ball.show()
    app.processEvents()

    controller.task_active = False
    ball.sync_animation_state()

    assert ("start", None) in calls
    assert ("stop", None) in calls
    assert calls.count(("jump", 0)) >= 2
    ball._clear_asset()
    ball.close()


def test_ball_window_hidden_stops_gif_even_when_always_play_enabled(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    gif_path = tmp_path / "ball.gif"
    gif_path.write_bytes(b"GIF89a")
    calls = []
    _patch_fake_movie(monkeypatch, calls)

    config = Config.create_isolated(str(tmp_path / "config.json"))
    config.set("floating_ball_config.asset_path", str(gif_path))
    config.set("floating_ball_config.animation_always_play", True)
    controller = _FakeController(config=config)
    ball = BallWindow(controller)
    ball.show()
    app.processEvents()

    stop_count = calls.count(("stop", None))
    ball.hide()
    app.processEvents()

    assert calls.count(("stop", None)) > stop_count
    assert calls.count(("jump", 0)) >= 2
    ball._clear_asset()
    ball.close()


def test_edge_bar_delayed_hover_tracking_is_cancelled_after_hide(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    scheduled_callbacks = []
    controller = _FakeController()
    edge = EdgeBarWindow(controller)

    monkeypatch.setattr(
        "baodou_ai.gui.floating.ball.QTimer.singleShot",
        lambda _delay, callback: scheduled_callbacks.append(callback),
    )

    edge.show_at_edge("right", QPoint(200, 200))
    edge.hide_bar()
    scheduled_callbacks[0]()

    assert edge._hover_tracking_enabled is False
    assert edge._hover_timer.isActive() is False
    edge.close()


def test_overlay_coordinator_sync_hover_timer_tracks_visibility_and_edge_state():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    class _FakeBallWidget(QWidget):
        shadow_margin = 5

        def __init__(self):
            super().__init__()
            self.resize(82, 82)

        def global_ball_rect(self):
            return self.geometry()

    class _FakePanelWidget(QWidget):
        target_visible = False
        pinned_active = False

        def __init__(self):
            super().__init__()

        def is_animating(self):
            return False

    controller = SimpleNamespace(
        ball_window=_FakeBallWidget(),
        panel_window=_FakePanelWidget(),
        ball_size=72,
        expanded_width=320,
        expanded_height=420,
        ball_anchor=QPoint(0, 0),
        is_edge_hidden=False,
        is_dragging=False,
        is_pinned=False,
        edge_bar=SimpleNamespace(isVisible=lambda: False, raise_=lambda: None),
        _mark_voice_user_interaction=lambda: None,
        keep_ball_on_top=lambda *args, **kwargs: None,
        _reposition_companion_window=lambda: None,
        _reposition_toast_window=lambda: None,
        _task_active=lambda: False,
        _is_waiting_for_tts=lambda: False,
        _sync_voice_interaction_state=lambda: None,
        _hide_toast_window=lambda: None,
        _hide_companion_suggestions=lambda: None,
        _show_history_if_idle=lambda: None,
    )
    controller.ball_window.show()
    coordinator = OverlayWindowCoordinator(controller)

    coordinator._sync_hover_timer()
    assert coordinator.hover_timer.isActive() is True

    controller.is_edge_hidden = True
    coordinator._sync_hover_timer()
    assert coordinator.hover_timer.isActive() is False

    controller.is_edge_hidden = False
    controller.ball_window.hide()
    coordinator._sync_hover_timer()
    assert coordinator.hover_timer.isActive() is False

    controller.ball_window.show()
    coordinator._sync_hover_timer()
    assert coordinator.hover_timer.isActive() is True
    coordinator.hover_timer.stop()
    controller.ball_window.close()
    controller.panel_window.close()


def test_sync_background_activity_timers_only_runs_frontmost_when_companion_enabled():
    controller = FloatingController.__new__(FloatingController)
    controller._config = Config.create_isolated()
    controller._config.set("companion_config.enabled", False)
    controller._job_manager = SimpleNamespace(get_memory_jobs=lambda: [])
    controller._job_windows = {}
    controller._frontmost_timer = SimpleNamespace(
        active=False,
        interval_value=300,
        start_calls=0,
        stop_calls=0,
        start=lambda self=None: None,
    )
    controller._job_poll_timer = SimpleNamespace(
        active=False,
        interval_value=500,
        start_calls=0,
    )

    def _frontmost_is_active():
        return controller._frontmost_timer.active

    def _frontmost_start():
        controller._frontmost_timer.start_calls += 1
        controller._frontmost_timer.active = True

    def _frontmost_stop():
        controller._frontmost_timer.stop_calls += 1
        controller._frontmost_timer.active = False

    def _frontmost_interval():
        return controller._frontmost_timer.interval_value

    def _frontmost_set_interval(value):
        controller._frontmost_timer.interval_value = value

    controller._frontmost_timer.isActive = _frontmost_is_active
    controller._frontmost_timer.start = _frontmost_start
    controller._frontmost_timer.stop = _frontmost_stop
    controller._frontmost_timer.interval = _frontmost_interval
    controller._frontmost_timer.setInterval = _frontmost_set_interval

    def _job_is_active():
        return controller._job_poll_timer.active

    def _job_start():
        controller._job_poll_timer.start_calls += 1
        controller._job_poll_timer.active = True

    def _job_interval():
        return controller._job_poll_timer.interval_value

    def _job_set_interval(value):
        controller._job_poll_timer.interval_value = value

    controller._job_poll_timer.isActive = _job_is_active
    controller._job_poll_timer.start = _job_start
    controller._job_poll_timer.interval = _job_interval
    controller._job_poll_timer.setInterval = _job_set_interval

    controller._sync_background_activity_timers()

    assert controller._frontmost_timer.stop_calls == 1
    assert controller._frontmost_timer.start_calls == 0
    assert controller._job_poll_timer.interval_value == 1500
    assert controller._job_poll_timer.start_calls == 1

    controller._config.set("companion_config.enabled", True)
    controller._job_manager = SimpleNamespace(get_memory_jobs=lambda: [{"job_id": "job-1"}])

    controller._sync_background_activity_timers()

    assert controller._frontmost_timer.interval_value == 700
    assert controller._frontmost_timer.start_calls == 1
    assert controller._job_poll_timer.interval_value == 500


def test_console_copies_floating_ball_asset_and_notifies_config_change(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    fake_platform = SimpleNamespace(
        setup_window=lambda _window: None,
        prevent_screenshot=lambda _window: True,
        enter_transparent_mode=lambda _window: True,
        exit_transparent_mode=lambda _window: True,
    )
    monkeypatch.setattr("baodou_ai.gui.control_console.get_platform_adapter", lambda: fake_platform)
    monkeypatch.setattr("baodou_ai.gui.control_console.Path.home", lambda: tmp_path)

    source_path = tmp_path / "source.png"
    pixmap = QPixmap(10, 10)
    pixmap.fill(QColor("#111111"))
    assert pixmap.save(str(source_path))
    monkeypatch.setattr(
        "baodou_ai.gui.control_console.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(source_path), "Images (*.png)"),
    )

    changes = []
    config = Config.create_isolated(str(tmp_path / "config.json"))
    window = ControlConsoleWindow(config, RuntimeLogBuffer(), on_config_changed=lambda key, value: changes.append((key, value)))

    assert "floating_ball_config.animation_always_play" in window._config_widgets
    assert "floating_ball_config.play_on_hover" not in window._config_widgets

    window._choose_floating_ball_asset()

    copied_path = tmp_path / ".coview" / "floating_assets" / "ball_asset.png"
    assert copied_path.exists()
    assert config.get("floating_ball_config.asset_path") == str(copied_path)
    assert changes[-1] == ("floating_ball_config.asset_path", str(copied_path))


def test_control_console_wake_word_phrase_widgets_save_and_restore(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    fake_platform = SimpleNamespace(
        setup_window=lambda _window: None,
        prevent_screenshot=lambda _window: True,
        enter_transparent_mode=lambda _window: True,
        exit_transparent_mode=lambda _window: True,
    )
    monkeypatch.setattr("baodou_ai.gui.control_console.get_platform_adapter", lambda: fake_platform)

    config_path = tmp_path / "config.json"
    config = Config.create_isolated(str(config_path))
    window = ControlConsoleWindow(config, RuntimeLogBuffer())

    assert window._wake_word_phrase_widgets["zh"].text() == "你好小彤"
    assert window._wake_word_phrase_widgets["en"].text() == "hey Lucy"

    window._set_wake_word_phrase("zh", "你好同窗")
    window._set_wake_word_phrase("en", "Hey CoView")

    assert config.get_wake_word_phrase("zh") == "你好同窗"
    assert config.get_wake_word_phrase("en") == "Hey CoView"

    restored_config = Config.create_isolated(str(config_path))
    restored_window = ControlConsoleWindow(restored_config, RuntimeLogBuffer())

    assert restored_window._wake_word_phrase_widgets["zh"].text() == "你好同窗"
    assert restored_window._wake_word_phrase_widgets["en"].text() == "Hey CoView"


def test_control_console_fills_tts_api_key_from_model_for_aliyun(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    fake_platform = SimpleNamespace(
        setup_window=lambda _window: None,
        prevent_screenshot=lambda _window: True,
        enter_transparent_mode=lambda _window: True,
        exit_transparent_mode=lambda _window: True,
    )
    monkeypatch.setattr("baodou_ai.gui.control_console.get_platform_adapter", lambda: fake_platform)

    changes = []
    config = Config.create_isolated(str(tmp_path / "config.json"))
    config.set("api_config.base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    config.set("tts_config.base_url", "wss://dashscope.aliyuncs.com/api-ws/v1/inference")
    config.set("tts_config.api_key", "")
    window = ControlConsoleWindow(
        config,
        RuntimeLogBuffer(),
        on_config_changed=lambda key, value: changes.append((key, value)),
    )

    window._set_text_config("api_config.api_key", "shared-key")

    assert config.get("api_config.api_key") == "shared-key"
    assert config.get("tts_config.api_key") == "shared-key"
    assert window._config_widgets["tts_config.api_key"].text() == "shared-key"
    assert changes == [
        ("api_config.api_key", "shared-key"),
        ("tts_config.api_key", "shared-key"),
    ]


def test_control_console_does_not_override_existing_tts_api_key(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    fake_platform = SimpleNamespace(
        setup_window=lambda _window: None,
        prevent_screenshot=lambda _window: True,
        enter_transparent_mode=lambda _window: True,
        exit_transparent_mode=lambda _window: True,
    )
    monkeypatch.setattr("baodou_ai.gui.control_console.get_platform_adapter", lambda: fake_platform)

    changes = []
    config = Config.create_isolated(str(tmp_path / "config.json"))
    config.set("api_config.base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    config.set("tts_config.base_url", "wss://dashscope.aliyuncs.com/api-ws/v1/inference")
    config.set("tts_config.api_key", "custom-tts-key")
    window = ControlConsoleWindow(
        config,
        RuntimeLogBuffer(),
        on_config_changed=lambda key, value: changes.append((key, value)),
    )

    window._set_text_config("api_config.api_key", "shared-key")

    assert config.get("api_config.api_key") == "shared-key"
    assert config.get("tts_config.api_key") == "custom-tts-key"
    assert window._config_widgets["tts_config.api_key"].text() == "custom-tts-key"
    assert changes == [("api_config.api_key", "shared-key")]


def test_control_console_shows_footer_entries_and_switches_locale(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    fake_platform = SimpleNamespace(
        setup_window=lambda _window: None,
        prevent_screenshot=lambda _window: True,
        enter_transparent_mode=lambda _window: True,
        exit_transparent_mode=lambda _window: True,
    )
    monkeypatch.setattr("baodou_ai.gui.control_console.get_platform_adapter", lambda: fake_platform)
    set_locale("zh_CN")

    try:
        config = Config.create_isolated(str(tmp_path / "config.json"))
        config.set("voice_interaction_config.stop_spoken_text", "好的，已停止当前任务。")
        window = ControlConsoleWindow(config, RuntimeLogBuffer())

        assert window.windowTitle() == "同窗设置"
        assert [window._footer_sidebar.item(index).text() for index in range(window._footer_sidebar.count())] == [
            "关于",
            "语言 / Language",
        ]
        assert window._sidebar.item(5).text() == "后台代码代理"
        assert window._config_widgets["voice_interaction_config.block_frames"].suffix() == " 帧"
        assert window._config_widgets["api_config.api_key"].placeholderText() == "请输入接口密钥..."
        assert window._config_widgets["voice_interaction_config.asr_provider"].itemText(0) == "通义千问"
        assert window._config_widgets["wake_word_config.provider"].itemText(0) == "本地唤醒引擎"

        window.switch_to_page(7)
        assert window._current_page_id == "about"
        assert any(label.text() == "2.0.0" for label in window.findChildren(QLabel))

        window.switch_to_page(8)
        english_button = next(
            button for button in window.findChildren(QPushButton) if button.text() == "English"
        )
        english_button.click()
        app.processEvents()

        assert config.get("locale_config.locale") == "en_US"
        assert (
            config.get("voice_interaction_config.stop_spoken_text")
            == "Okay, I stopped the current task."
        )
        assert window.windowTitle() == "CoView Settings"
        assert window._current_page_id == "language"
        assert window._sidebar.item(0).text() == "General"
        assert window._sidebar.item(5).text() == "Background Agent"
        assert window._footer_sidebar.item(0).text() == "About"
        assert window._footer_sidebar.item(1).text() == "语言 / Language"
        assert window._config_widgets["voice_interaction_config.block_frames"].suffix() == " frames"
        assert window._config_widgets["api_config.api_key"].placeholderText() == "Enter API Key..."
        assert window._config_widgets["voice_interaction_config.asr_provider"].itemText(0) == "Qwen"
        assert window._config_widgets["wake_word_config.provider"].itemText(0) == "Sherpa-ONNX"
        assert window._config_widgets["code_agent_config.provider"].itemText(0) == "codex"
        assert (
            window._config_widgets["voice_interaction_config.stop_spoken_text"].text()
            == "Okay, I stopped the current task."
        )
    finally:
        set_locale("zh_CN")


def test_floating_controller_reloads_ball_asset_when_console_config_changes():
    reloads = []
    controller = FloatingController.__new__(FloatingController)
    controller.ball_window = SimpleNamespace(reload_asset=lambda: reloads.append(True))

    controller._handle_console_config_changed("floating_ball_config.asset_path", "/tmp/ball.png")
    controller._handle_console_config_changed("tts_config.enabled", True)

    assert reloads == [True]


def test_panel_window_switches_between_idle_running_and_finished_states():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    controller = _FakeController()
    panel = PanelWindow(controller)
    panel.resize(
        controller.expanded_width + panel.shadow_left + panel.shadow_right,
        controller.expanded_height + panel.shadow_top + panel.shadow_bottom,
    )
    panel.set_direction("left", "up")
    panel.set_idle_state()

    panel.input_area.setText("打开抖音网页")
    panel._on_return_pressed()
    assert controller.submitted == ["打开抖音网页"]

    panel.show_running_state("打开抖音网页")
    assert not panel.input_area.isVisible()
    assert not panel.stop_button.isHidden()
    assert panel._status_widget is not None
    assert panel._status_widget.text() == "正在执行 ⏳"

    panel.show_stopping_state()
    assert panel._status_widget.text() == "正在停止"

    panel.show_finished_state("已经为你打开抖音网页")
    message_text = "\n".join(label.text() for label in panel.message_host.findChildren(type(panel._status_widget)))
    assert "打开抖音网页" in message_text
    assert "已经为你打开抖音网页" in message_text
    user_label = next(
        label
        for label in panel.message_host.findChildren(QLabel)
        if label.text() == "打开抖音网页"
    )
    report_label = next(
        label
        for label in panel.message_host.findChildren(QLabel)
        if label.property("report_plain_text") == "已经为你打开抖音网页"
    )
    assert "#111111" in user_label.styleSheet()
    assert "#FFFFFF" in user_label.styleSheet()
    assert "#FFFFFF" in report_label.styleSheet()
    assert "#111111" in report_label.styleSheet()
    assert not panel.input_area.isHidden()
    assert panel.stop_button.isHidden()

    panel.stop_button.click()
    assert controller.stop_requests == 1


def test_panel_window_renders_report_markdown_as_rich_text():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    controller = _FakeController()
    panel = PanelWindow(controller)

    panel.show_finished_state("## 总结\n- 第一项\n- 第二项\n[打开链接](https://example.com)")

    report_label = next(
        label
        for label in panel.message_host.findChildren(QLabel)
        if label.property("report_plain_text")
    )
    plain_text = str(report_label.property("report_plain_text"))

    assert report_label.openExternalLinks() is True
    assert "总结" in plain_text
    assert "第一项" in plain_text
    assert "第二项" in plain_text
    assert "打开链接" in plain_text
    assert "## 总结" not in report_label.text()
    assert "<a href=\"https://example.com\"" in report_label.text()


def test_panel_window_animation_progress_skips_expensive_shape_and_layout(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    controller = _FakeController()
    panel = PanelWindow(controller)
    expensive_calls = []
    opacities = []

    monkeypatch.setattr(panel, "_apply_shape", lambda: expensive_calls.append("shape"))
    monkeypatch.setattr(panel, "_layout_children", lambda: expensive_calls.append("layout"))
    monkeypatch.setattr(panel, "_set_content_opacity", lambda opacity: opacities.append(opacity))

    panel._on_anim_value_changed(QRect(0, 0, panel.width(), panel.ball_size + panel.shadow_top + panel.shadow_bottom + 120))

    assert expensive_calls == []
    assert len(opacities) == 1
    assert 0.0 < opacities[0] < 1.0


def test_panel_window_resize_event_skips_expensive_updates_in_animation_light_mode(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    controller = _FakeController()
    panel = PanelWindow(controller)
    panel.show()
    app.processEvents()

    expensive_calls = []
    monkeypatch.setattr(panel, "_apply_shape", lambda: expensive_calls.append("shape"))
    monkeypatch.setattr(panel, "_layout_children", lambda: expensive_calls.append("layout"))

    panel._animation_light_mode = True
    panel.resize(panel.width() + 10, panel.height() + 10)
    app.processEvents()

    assert expensive_calls == []

    panel._animation_light_mode = False
    panel.resize(panel.width() + 10, panel.height() + 10)
    app.processEvents()

    assert expensive_calls == ["layout", "shape"]


def test_panel_window_animation_finish_reapplies_expensive_updates(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    controller = _FakeController()
    keep_on_top_calls = []
    controller.keep_ball_on_top = lambda: keep_on_top_calls.append(True)
    panel = PanelWindow(controller)
    panel.target_visible = True
    panel._focus_input_on_finish = False
    panel._animation_light_mode = True

    expensive_calls = []
    opacities = []
    monkeypatch.setattr(panel, "_apply_shape", lambda: expensive_calls.append("shape"))
    monkeypatch.setattr(panel, "_layout_children", lambda: expensive_calls.append("layout"))
    monkeypatch.setattr(panel, "_set_content_opacity", lambda opacity: opacities.append(opacity))

    panel._on_anim_finished()

    assert panel._animation_light_mode is False
    assert expensive_calls == ["layout", "shape"]
    assert opacities[-1] == 1.0
    assert keep_on_top_calls == [True]


def test_windows_overlay_refresh_is_coalesced_within_event_loop(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    scheduled_callbacks = []
    controller = _FakeController()
    ball = WindowsBallWindow(controller)

    monkeypatch.setattr(ball, "isVisible", lambda: True)
    monkeypatch.setattr(
        "baodou_ai.gui.floating.windows_widgets.QTimer.singleShot",
        lambda _delay, callback: scheduled_callbacks.append(callback),
    )

    ball._schedule_native_overlay_refresh()
    ball._schedule_native_overlay_refresh()

    assert len(scheduled_callbacks) == 1
    assert controller._platform_adapter.prepare_calls == []

    scheduled_callbacks[0]()

    assert controller._platform_adapter.prepare_calls == [ball]
    assert ball._overlay_refresh_pending is False


def test_windows_panel_reposition_does_not_refresh_native_overlay():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    controller = _FakeController()
    panel = WindowsPanelWindow(controller)
    panel._schedule_native_overlay_refresh = lambda: controller._platform_adapter.prepare_calls.append("scheduled")
    panel.isVisible = lambda: True
    controller._platform_adapter.prepare_calls.clear()

    panel.reposition_for_anchor(QPoint(160, 220))

    assert controller._platform_adapter.prepare_calls == []


def test_windows_suggestion_and_toast_reposition_do_not_refresh_native_overlay():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    controller = _FakeController()
    suggestion = WindowsSuggestionWindow(controller)
    toast = WindowsToastWindow(controller)
    suggestion._schedule_native_overlay_refresh = lambda: controller._platform_adapter.prepare_calls.append("suggestion")
    toast._schedule_native_overlay_refresh = lambda: controller._platform_adapter.prepare_calls.append("toast")
    suggestion.isVisible = lambda: True
    toast.isVisible = lambda: True
    controller._platform_adapter.prepare_calls.clear()

    suggestion.reposition(QPoint(220, 240))
    toast.reposition(QPoint(220, 240))

    assert controller._platform_adapter.prepare_calls == []


def test_floating_monochrome_theme_does_not_keep_legacy_purple_tokens():
    floating_dir = Path(__file__).resolve().parents[1] / "src" / "baodou_ai" / "gui" / "floating"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in floating_dir.glob("*.py"))

    for token in ("#6366F1", "#818CF8", "#C7D2FE", "#F5F3FF", "#E8E0F0"):
        assert token not in combined


def test_control_console_replays_history_and_updates_runtime_state(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    fake_platform = SimpleNamespace(
        setup_window=lambda _window: None,
        prevent_screenshot=lambda _window: True,
        enter_transparent_mode=lambda _window: True,
        exit_transparent_mode=lambda _window: True,
    )
    monkeypatch.setattr("baodou_ai.gui.control_console.get_platform_adapter", lambda: fake_platform)
    set_locale("zh_CN")

    try:
        config = Config.create_isolated()
        config.set("locale_config.locale", "zh_CN")
        log_buffer = RuntimeLogBuffer()
        log_buffer.append_log("[INFO] hello\n", "info")
        log_buffer.append_log("[READY] world\n", "success")

        window = ControlConsoleWindow(config, log_buffer)
        window._flush_pending_logs(force=True)

        assert "[INFO] hello" in window.log_text.toPlainText()
        assert "[READY] world" in window.log_text.toPlainText()

        window.update_runtime_state(
            status_key="running",
            status_text="助手执行中",
            iteration=3,
            max_iterations=80,
            token_total=123,
        )

        assert window.status_label.text() == "助手执行中"
        assert window.iter_label.text() == "迭代: 3 / 80"
        assert window.token_label.text() == "令牌: 123"
    finally:
        set_locale("zh_CN")


def test_control_console_code_agent_provider_includes_supported_cli_agents(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    fake_platform = SimpleNamespace(
        setup_window=lambda _window: None,
        prevent_screenshot=lambda _window: True,
        enter_transparent_mode=lambda _window: True,
        exit_transparent_mode=lambda _window: True,
    )
    monkeypatch.setattr("baodou_ai.gui.control_console.get_platform_adapter", lambda: fake_platform)
    set_locale("zh_CN")

    try:
        config = Config.create_isolated()
        config.set("locale_config.locale", "zh_CN")
        window = ControlConsoleWindow(config, RuntimeLogBuffer())
        combo = window._config_widgets["code_agent_config.provider"]

        assert isinstance(combo, QComboBox)
        values = [combo.itemText(index) for index in range(combo.count())]
        assert values == [
            "codex",
            "claude",
            "kimi",
            "qwen",
            "codebuddy",
        ]

        combo.setCurrentText("qwen")

        assert combo.currentText() == "qwen"
        assert config.get("code_agent_config.provider") == "qwen"
    finally:
        set_locale("zh_CN")


def test_code_agent_jobs_panel_refreshes_empty_running_and_terminal_jobs():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    set_locale("zh_CN")
    calls = []

    class _FakeJobManager:
        def __init__(self):
            self.jobs = []

        def list_jobs(self):
            return list(self.jobs)

        def cancel(self, job_id):
            calls.append(("cancel", job_id))
            self.jobs = []

        def dismiss(self, job_id):
            calls.append(("dismiss", job_id))
            self.jobs = []

    manager = _FakeJobManager()
    panel = CodeAgentJobsPanel(manager, lambda: "")
    try:
        assert any("当前没有后台代码代理任务。" in label.text() for label in panel.findChildren(QLabel))

        manager.jobs = [
            {
                "job_id": "job-1",
                "title": "运行任务",
                "status": "running",
                "provider": "codex",
                "workspace_path": "/tmp/project",
                "summary": "执行中",
            }
        ]
        panel.refresh_jobs()
        cancel_button = next(button for button in panel.findChildren(QPushButton) if button.text() == "取消")
        cancel_button.click()
        assert calls == [("cancel", "job-1")]

        manager.jobs = [
            {
                "job_id": "job-2",
                "title": "完成任务",
                "status": "completed",
                "provider": "codex",
                "workspace_path": "/tmp/project",
                "summary": "完成",
            }
        ]
        panel.refresh_jobs()
        dismiss_button = next(button for button in panel.findChildren(QPushButton) if button.text() == "关闭")
        dismiss_button.click()
        assert calls == [("cancel", "job-1"), ("dismiss", "job-2")]
    finally:
        panel.close()
        set_locale("zh_CN")


def test_floating_controller_persists_completed_background_job_reports():
    spoken_messages = []
    history_entries = []
    displayed_reports = []

    class _FakeJobManager:
        def drain_events(self):
            return []

        def collect_pending_reports(self):
            return [{
                "job_id": "code-job-0001",
                "title": "修复测试",
                "provider": "codex",
                "status": "completed",
                "summary": "所有测试已修复",
                "result_summary": "已修复所有测试",
                "spoken_report": "后台代码任务“修复测试”已执行成功。结果：已修复所有测试。执行目录：/tmp/project。",
                "final_output": "最终测试结果表格",
                "workspace_path": "/tmp/project",
                "error": "",
            }]

    class _FakeSessionHistory:
        def add_task(self, **kwargs):
            history_entries.append(kwargs)

    controller = FloatingController.__new__(FloatingController)
    controller._job_manager = _FakeJobManager()
    controller._log_buffer = RuntimeLogBuffer()
    controller._console_window = None
    controller._session_history = _FakeSessionHistory()
    controller._task_active = lambda: False
    controller._is_waiting_for_tts = lambda: False
    controller.is_edge_hidden = False
    controller.ball_anchor = QPoint(0, 0)
    controller.keep_ball_on_top = lambda *args, **kwargs: None
    controller.toast_window = SimpleNamespace(show_message=lambda *args, **kwargs: None)
    controller.panel_window = SimpleNamespace(
        target_visible=True,
        show_expanding=lambda *args, **kwargs: None,
        append_background_report=lambda text: displayed_reports.append(text),
    )
    controller._on_report = lambda text: spoken_messages.append(text) or None
    controller._tts = SimpleNamespace(
        current_done_event=None,
        stop=lambda: None,
        start_waiting=lambda: None,
    )
    controller._background_jobs = BackgroundJobsController(controller)

    controller._poll_background_jobs()

    assert history_entries == [{
        "instruction": "后台代码任务：修复测试",
        "status": "completed",
        "report": "后台代码任务“修复测试”已执行成功。结果：已修复所有测试。执行目录：/tmp/project。",
        "context_report": "后台代码任务“修复测试”已执行成功。结果：已修复所有测试。执行目录：/tmp/project。\n\n最终结果：\n最终测试结果表格",
        "memory": "",
        "steps": 0,
        "include_in_context": True,
    }]
    assert spoken_messages == [
        "后台代码任务“修复测试”已执行成功。结果：已修复所有测试。执行目录：/tmp/project。",
    ]
    assert displayed_reports == [
        "后台代码任务“修复测试”已执行成功。结果：已修复所有测试。执行目录：/tmp/project。",
    ]


def test_background_jobs_controller_collects_reports_even_while_busy():
    announced_messages = []
    displayed_messages = []
    history_tasks = []

    class _FakeJobManager:
        def drain_events(self):
            return []

        def collect_pending_reports(self):
            return [{"job_id": "job-1", "title": "修复", "status": "completed"}]

    class _FakeDelegate:
        def is_busy(self):
            return True

        def append_log(self, _text, _level):
            return None

        def refresh_console_jobs(self):
            return None

        def add_history_task(self, **payload):
            history_tasks.append(payload)

        def show_history_if_idle(self):
            return None

        def display_background_report(self, text):
            displayed_messages.append(text)

        def announce_report(self, text):
            announced_messages.append(text)

    controller = BackgroundJobsController(
        config=Config.create_isolated(),
        job_manager=_FakeJobManager(),
        delegate=_FakeDelegate(),
    )

    controller.poll()

    assert len(history_tasks) == 1
    assert announced_messages == ["后台代码任务“修复”已执行成功。"]
    assert displayed_messages == ["后台代码任务“修复”已执行成功。"]


def test_voice_stop_during_tts_only_does_not_speak_confirmation():
    operations = []

    class _FakeTTS:
        def __init__(self):
            self.speak_calls = []
            self.stop_calls = 0

        def stop(self):
            self.stop_calls += 1

        def is_waiting(self):
            return True

        def speak(self, text):
            self.speak_calls.append(text)
            return object()

        def start_waiting(self):
            operations.append("start_waiting")

    controller = FloatingController.__new__(FloatingController)
    controller._config = SimpleNamespace(get=lambda key, default=None: default)
    controller._log_buffer = SimpleNamespace(
        append_log=lambda text, level: operations.append(("log", text, level))
    )
    controller._tts = _FakeTTS()
    controller._mark_voice_user_interaction = lambda: operations.append("mark")
    controller._is_waiting_for_tts = lambda: True
    controller._set_runtime_state = lambda key, text: operations.append(("state", key, text))
    controller._show_history_if_idle = lambda: operations.append("history")
    controller.panel_window = SimpleNamespace(
        set_idle_state=lambda: operations.append("idle"),
        show_finished_state=lambda *args, **kwargs: operations.append(("finished", args, kwargs)),
    )
    controller._console_window = None
    controller._ui_task_state = UITaskSessionState(status_key="running", status_text="运行中")
    controller._runtime_state_presenter = RuntimeStatePresenter(controller, controller._ui_task_state)
    controller._task_session_controller = TaskSessionController(
        host=FloatingTaskSessionHost(controller),
        state=controller._ui_task_state,
        session_history=SimpleNamespace(),
        task_memory_store=SimpleNamespace(read=lambda: "", clear=lambda: None),
        runtime_state_presenter=controller._runtime_state_presenter,
    )

    controller.request_voice_stop()

    assert controller._tts.stop_calls == 1
    assert controller._tts.speak_calls == []
    assert "start_waiting" not in operations
    assert not any(item[0] == "finished" for item in operations if isinstance(item, tuple))
    assert "idle" in operations
    assert "history" in operations


def test_voice_new_task_during_tts_only_starts_new_voice_task(monkeypatch):
    operations = []
    created_workers = []

    class _FakeSignal:
        def connect(self, callback):
            operations.append(("connect", callback))

    class _FakeWorker:
        def __init__(
            self,
            text,
            config,
            *,
            initial_external_frontmost_app=None,
            history_context="",
            on_report=None,
            job_manager=None,
            respond_language_override="",
        ):
            del config, on_report, job_manager
            self.text = text
            self.initial_external_frontmost_app = initial_external_frontmost_app
            self.history_context = history_context
            self.respond_language_override = respond_language_override
            self.finished = _FakeSignal()
            self.error = _FakeSignal()
            self.stream_chunk = _FakeSignal()
            self.enter_transparent_mode = _FakeSignal()
            self.exit_transparent_mode = _FakeSignal()
            self.iteration_update = _FakeSignal()
            created_workers.append(self)

        def start(self):
            operations.append(("worker_start", self.text))

        def isRunning(self):
            return False

    class _FakeTTS:
        def __init__(self):
            self.stop_calls = 0
            self.current_text = "这是上一条任务的最终播报"

        def stop(self):
            self.stop_calls += 1

    monkeypatch.setattr("baodou_ai.gui.floating.task_session_host.AIWorker", _FakeWorker)

    owner = SimpleNamespace()
    owner._config = Config.create_isolated()
    owner._active_wake_word_language = "en"
    owner._tts = _FakeTTS()
    owner._mark_voice_user_interaction = lambda: operations.append("mark")
    owner._is_waiting_for_tts = lambda: True
    owner._show_history_if_idle = lambda: operations.append("history")
    owner._enable_screenshot_protection = lambda: operations.append("protect")
    owner._frontmost_tracker = SimpleNamespace(snapshot_last_external_frontmost_app=lambda: None)
    owner._platform_adapter = SimpleNamespace(activate_app=lambda app_info: operations.append(("activate", app_info)))
    owner._log_buffer = SimpleNamespace(append_log=lambda text, level: operations.append(("log", text, level)))
    owner._on_report = lambda _text: None
    owner._job_manager = None
    owner._console_window = None
    owner.ball_anchor = QPoint(0, 0)
    owner.panel_window = SimpleNamespace(
        show_running_state=lambda *args, **kwargs: operations.append(("show_running_state", args, kwargs))
    )
    state = UITaskSessionState(status_key="ready", status_text="就绪")
    owner._ui_task_state = state
    presenter = RuntimeStatePresenter(owner, state)
    session = TaskSessionController(
        host=FloatingTaskSessionHost(owner),
        state=state,
        session_history=SimpleNamespace(build_context_prompt=lambda: ""),
        task_memory_store=SimpleNamespace(read=lambda: "", clear=lambda: None),
        runtime_state_presenter=presenter,
    )

    session.request_voice_new_task("打开浏览器")

    assert owner._tts.stop_calls >= 1
    assert state.pending_voice_task_text == ""
    assert state.task_text == "打开浏览器"
    assert state.source == "voice"
    assert created_workers
    assert created_workers[0].text == "打开浏览器"
    assert created_workers[0].history_context == ""
    assert created_workers[0].respond_language_override == "English"
    assert ("worker_start", "打开浏览器") in operations
    assert any(item[0] == "show_running_state" for item in operations if isinstance(item, tuple))


def test_task_session_host_closes_console_for_task_start_on_windows(monkeypatch):
    close_calls = []
    owner = SimpleNamespace(_console_window=SimpleNamespace(close=lambda: close_calls.append(True)))
    monkeypatch.setattr("baodou_ai.gui.floating.task_session_host.platform.system", lambda: "Windows")

    FloatingTaskSessionHost(owner).close_console_for_task_start()

    assert close_calls == [True]


def test_task_session_host_does_not_close_console_for_task_start_on_macos(monkeypatch):
    close_calls = []
    owner = SimpleNamespace(_console_window=SimpleNamespace(close=lambda: close_calls.append(True)))
    monkeypatch.setattr("baodou_ai.gui.floating.task_session_host.platform.system", lambda: "Darwin")

    FloatingTaskSessionHost(owner).close_console_for_task_start()

    assert close_calls == []


def test_start_task_closes_console_window_before_worker_start(monkeypatch):
    operations = []
    created_workers = []

    class _FakeSignal:
        def connect(self, callback):
            operations.append(("connect", callback))

    class _FakeWorker:
        def __init__(
            self,
            text,
            config,
            *,
            initial_external_frontmost_app=None,
            history_context="",
            on_report=None,
            job_manager=None,
            respond_language_override="",
        ):
            del config, on_report, job_manager
            self.text = text
            self.initial_external_frontmost_app = initial_external_frontmost_app
            self.history_context = history_context
            self.respond_language_override = respond_language_override
            self.finished = _FakeSignal()
            self.error = _FakeSignal()
            self.stream_chunk = _FakeSignal()
            self.enter_transparent_mode = _FakeSignal()
            self.exit_transparent_mode = _FakeSignal()
            self.iteration_update = _FakeSignal()
            created_workers.append(self)

        def start(self):
            operations.append(("worker_start", self.text))

        def isRunning(self):
            return False

    monkeypatch.setattr("baodou_ai.gui.floating.task_session_host.AIWorker", _FakeWorker)

    owner = SimpleNamespace()
    owner._config = Config.create_isolated()
    owner._tts = SimpleNamespace(stop=lambda: operations.append("tts_stop"))
    owner.hide_suggestions = lambda: operations.append("hide_suggestions")
    owner.close_console_for_task_start = lambda: operations.append("close_console")
    owner._show_history_if_idle = lambda: operations.append("history")
    owner._enable_screenshot_protection = lambda: operations.append("protect")
    owner._frontmost_tracker = SimpleNamespace(snapshot_last_external_frontmost_app=lambda: None)
    owner._platform_adapter = SimpleNamespace(activate_app=lambda app_info: operations.append(("activate", app_info)))
    owner._log_buffer = SimpleNamespace(append_log=lambda text, level: operations.append(("log", text, level)))
    owner._on_report = lambda _text: None
    owner._job_manager = None
    owner._console_window = None
    owner.ball_anchor = QPoint(0, 0)
    owner.panel_window = SimpleNamespace(
        show_running_state=lambda *args, **kwargs: operations.append(("show_running_state", args, kwargs))
    )
    state = UITaskSessionState(status_key="ready", status_text="就绪")
    owner._ui_task_state = state
    presenter = RuntimeStatePresenter(owner, state)
    session = TaskSessionController(
        host=FloatingTaskSessionHost(owner),
        state=state,
        session_history=SimpleNamespace(build_context_prompt=lambda: ""),
        task_memory_store=SimpleNamespace(read=lambda: "", clear=lambda: None),
        runtime_state_presenter=presenter,
    )

    session.start_task("打开浏览器")

    assert created_workers
    assert operations.index("hide_suggestions") < operations.index("close_console") < operations.index(("worker_start", "打开浏览器"))


def test_code_agent_job_window_refreshes_logs_and_cancels_running_job(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    fake_platform = SimpleNamespace(
        setup_window=lambda _window: None,
        prevent_screenshot=lambda _window: True,
        enter_transparent_mode=lambda _window: True,
        exit_transparent_mode=lambda _window: True,
    )
    monkeypatch.setattr(
        "baodou_ai.gui.code_agent_window.get_platform_adapter",
        lambda: fake_platform,
    )

    class _FakeJobManager:
        def __init__(self):
            self.cancelled = []
            self.status = "running"

        def get_job(self, job_id, include_logs=False):
            assert job_id == "code-job-0001"
            return {
                "job_id": job_id,
                "title": "生成页面",
                "task": "Create a playable HTML page",
                "provider": "codex",
                "workspace_path": "/tmp",
                "status": self.status,
                "summary": "后台代码任务运行中",
                "final_output": "",
                "error": None,
                "process_pid": 12345,
                "logs": ["line 1", "line 2"] if include_logs else [],
                "log_count": 2,
            }

        def cancel(self, job_id):
            self.cancelled.append(job_id)
            self.status = "cancelled"

    manager = _FakeJobManager()
    window = CodeAgentJobWindow(Config.create_isolated(), manager, "code-job-0001")
    app.processEvents()

    assert window.title_label.text() == "生成页面"
    assert "任务完成后" in window.result_text.toPlainText()
    assert "line 1" in window.log_text.toPlainText()
    assert window.property(CAPTURE_EXCLUDE_PROPERTY) is None

    window.cancel_button.click()

    assert manager.cancelled == ["code-job-0001"]
    window.close()


def test_code_agent_job_window_extracts_codebuddy_result_from_raw_output(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    fake_platform = SimpleNamespace(
        setup_window=lambda _window: None,
        prevent_screenshot=lambda _window: True,
        enter_transparent_mode=lambda _window: True,
        exit_transparent_mode=lambda _window: True,
    )
    monkeypatch.setattr(
        "baodou_ai.gui.code_agent_window.get_platform_adapter",
        lambda: fake_platform,
    )

    raw_output = json.dumps(
        [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "large prompt"}],
            },
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "这是 CodeBuddy 的最终结果。",
            },
        ],
        ensure_ascii=False,
        indent=2,
    )

    class _FakeJobManager:
        def get_job(self, job_id, include_logs=False):
            return {
                "job_id": job_id,
                "title": "CodeBuddy 任务",
                "task": "Ask CodeBuddy",
                "provider": "codebuddy",
                "workspace_path": "/tmp",
                "status": "completed",
                "summary": "任务完成",
                "final_output": "legacy full event log that should not be shown",
                "raw_output": raw_output,
                "error": None,
                "process_pid": None,
                "logs": ["line 1"] if include_logs else [],
                "log_count": 1,
            }

    window = CodeAgentJobWindow(
        Config.create_isolated(), _FakeJobManager(), "code-job-0001"
    )
    app.processEvents()

    assert window.result_text.toPlainText() == "这是 CodeBuddy 的最终结果。"
    window.close()


def test_code_agent_job_window_renders_final_output_markdown(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    fake_platform = SimpleNamespace(
        setup_window=lambda _window: None,
        prevent_screenshot=lambda _window: True,
        enter_transparent_mode=lambda _window: True,
        exit_transparent_mode=lambda _window: True,
    )
    monkeypatch.setattr(
        "baodou_ai.gui.code_agent_window.get_platform_adapter",
        lambda: fake_platform,
    )

    class _FakeJobManager:
        def get_job(self, job_id, include_logs=False):
            return {
                "job_id": job_id,
                "title": "Markdown 任务",
                "task": "Render markdown",
                "provider": "codex",
                "workspace_path": "/tmp",
                "status": "completed",
                "summary": "任务完成",
                "final_output": (
                    "## 修复结果\n\n- **测试通过**\n- 已更新 `code_agent_window.py`"
                ),
                "raw_output": "",
                "error": None,
                "process_pid": None,
                "logs": [] if include_logs else [],
                "log_count": 0,
            }

    window = CodeAgentJobWindow(
        Config.create_isolated(), _FakeJobManager(), "code-job-0001"
    )
    app.processEvents()

    plain_text = window.result_text.toPlainText()
    html = window.result_text.toHtml()
    assert "修复结果" in plain_text
    assert "测试通过" in plain_text
    assert "**测试通过**" not in plain_text
    assert "<li" in html
    assert "font-weight" in html
    window.close()


def test_code_agent_job_window_requires_confirmation_before_closing(monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    fake_platform = SimpleNamespace(
        setup_window=lambda _window: None,
        prevent_screenshot=lambda _window: True,
        enter_transparent_mode=lambda _window: True,
        exit_transparent_mode=lambda _window: True,
    )
    monkeypatch.setattr("baodou_ai.gui.code_agent_window.get_platform_adapter", lambda: fake_platform)

    class _FakeJobManager:
        def __init__(self):
            self.cancelled = []

        def get_job(self, job_id, include_logs=False):
            return {
                "job_id": job_id,
                "title": "生成页面",
                "task": "Create a playable HTML page",
                "provider": "codex",
                "workspace_path": "/tmp",
                "status": "running",
                "summary": "后台代码任务运行中",
                "final_output": "",
                "error": None,
                "process_pid": 12345,
                "logs": [] if include_logs else [],
                "log_count": 0,
            }

        def cancel(self, job_id):
            self.cancelled.append(job_id)

    manager = _FakeJobManager()
    window = CodeAgentJobWindow(Config.create_isolated(), manager, "code-job-0001")

    monkeypatch.setattr(window, "_confirm_close_running_job", lambda: False)
    assert window.close() is False
    assert manager.cancelled == []
    assert window.isVisible() is False

    monkeypatch.setattr(window, "_confirm_close_running_job", lambda: True)
    assert window.close() is True
    assert manager.cancelled == ["code-job-0001"]


def test_floating_controller_creates_job_window_for_background_job():
    class _FakeWindow:
        def __init__(self):
            self.refreshed = []
            self.show_calls = 0
            self.raise_calls = 0
            self.activate_calls = 0

        def refresh_job(self, force_logs=False):
            self.refreshed.append(force_logs)

        def show(self):
            self.show_calls += 1

        def raise_(self):
            self.raise_calls += 1

        def activateWindow(self):
            self.activate_calls += 1

    controller = FloatingController.__new__(FloatingController)
    controller._job_manager = SimpleNamespace(get_job=lambda job_id: {"job_id": job_id, "dismissed": False})
    controller._background_jobs = BackgroundJobsController(controller)
    controller._job_windows = controller._background_jobs.job_windows
    fake_window = _FakeWindow()
    controller._background_jobs.ensure_job_window = lambda job_id: (fake_window, True)
    controller._background_jobs.position_job_window = lambda window: None
    controller._background_jobs.close_job_window = lambda job_id: None

    controller._sync_job_window("code-job-0001")

    assert fake_window.refreshed == [True]
    assert fake_window.show_calls == 1
    assert fake_window.raise_calls == 1
    assert fake_window.activate_calls == 1


def test_floating_controller_opens_settings_for_local_slash_commands():
    class _FakeConsoleWindow:
        def __init__(self):
            self.page_ids = []
            self.show_calls = 0
            self.raise_calls = 0
            self.activate_calls = 0

        def switch_to_page_id(self, page_id):
            self.page_ids.append(page_id)

        def show(self):
            self.show_calls += 1

        def raise_(self):
            self.raise_calls += 1

        def activateWindow(self):
            self.activate_calls += 1

    for command in ("/设置", "/setting", "/Setting"):
        controller = FloatingController.__new__(FloatingController)
        controller._console_window = None
        controller._task_active = lambda: False
        controller._mark_voice_user_interaction = lambda: None
        start_calls = []
        hide_calls = []
        fake_window = _FakeConsoleWindow()
        controller._ensure_console_window = lambda window=fake_window: window
        controller._start_task = (
            lambda text, source="keyboard", focus_panel=True: start_calls.append(
                (text, source, focus_panel)
            )
        )
        controller._companion = SimpleNamespace(hide_suggestions=lambda: hide_calls.append(True))

        controller.handle_submit(command)

        assert fake_window.page_ids == ["general"]
        assert fake_window.show_calls == 1
        assert fake_window.raise_calls == 1
        assert fake_window.activate_calls == 1
        assert hide_calls == [True]
        assert start_calls == []


def test_floating_controller_managed_windows_excludes_console_and_background_job_windows():
    controller = FloatingController.__new__(FloatingController)
    controller.ball_window = object()
    controller.panel_window = object()
    controller.edge_bar = object()
    controller._console_window = object()
    controller._job_windows = {"code-job-0001": object()}

    managed = controller._managed_windows()

    assert managed == [
        controller.ball_window,
        controller.panel_window,
        controller.edge_bar,
    ]


def test_floating_controller_does_not_reopen_suppressed_job_window():
    controller = FloatingController.__new__(FloatingController)
    controller._job_manager = SimpleNamespace(get_job=lambda job_id: {"job_id": job_id, "dismissed": False})
    controller._background_jobs = BackgroundJobsController(controller)
    controller._job_windows = controller._background_jobs.job_windows
    controller._suppressed_job_window_ids = controller._background_jobs.suppressed_job_window_ids
    controller._suppressed_job_window_ids.add("code-job-0001")
    controller._background_jobs.close_job_window = lambda job_id: None
    controller._background_jobs.ensure_job_window = lambda job_id: (_ for _ in ()).throw(AssertionError("should not create window"))

    controller._sync_job_window("code-job-0001", auto_open=True)


def test_floating_controller_closes_job_windows_evicted_from_memory_window():
    closed_job_ids = []

    controller = FloatingController.__new__(FloatingController)
    controller._job_manager = SimpleNamespace(
        get_memory_jobs=lambda: [
            {"job_id": "code-job-0002"},
            {"job_id": "code-job-0003"},
        ]
    )
    controller._background_jobs = BackgroundJobsController(controller)
    controller._background_jobs.job_windows = {
        "code-job-0001": object(),
        "code-job-0002": object(),
    }
    controller._job_windows = controller._background_jobs.job_windows
    controller._background_jobs.close_job_window = lambda job_id: closed_job_ids.append(job_id)

    controller._sync_memory_job_windows()

    assert closed_job_ids == ["code-job-0001"]


def test_suggestion_window_privacy_notice_is_not_clickable():
    app = QApplication.instance() or QApplication([])
    controller = _FakeController()
    window = SuggestionWindow(controller)
    clicked = []
    window.clicked.connect(clicked.append)

    try:
        window.show_privacy_notice(QPoint(100, 100), "当前窗口禁用智能推荐")
        app.processEvents()

        assert window.isVisible()
        assert window._buttons[0].text() == "当前窗口禁用智能推荐"
        assert not window._buttons[0].isEnabled()
        assert window._buttons[1].isHidden()

        window._buttons[0].click()
        app.processEvents()
        assert clicked == []

        window.show_suggestions(QPoint(100, 100), ["总结内容", "提取信息"])
        app.processEvents()
        assert window._buttons[0].isEnabled()
        assert not window._buttons[1].isHidden()
        assert window._buttons[0].text() == "总结内容"
        assert window._buttons[1].text() == "提取信息"
    finally:
        window.close()


def _make_worker_result_test_session(history_entries, clear_calls):
    owner = SimpleNamespace()
    owner._disable_screenshot_protection = lambda: None
    owner._log_buffer = SimpleNamespace(append_log=lambda text, level: None)
    owner._is_waiting_for_tts = lambda: False
    owner._tts = SimpleNamespace(current_done_event="pending", start_waiting=lambda: None)
    owner.panel_window = SimpleNamespace(show_finished_state=lambda *args, **kwargs: None)
    owner._show_history_if_idle = lambda: None
    owner._on_report = lambda _text: None
    owner._console_window = None
    state = UITaskSessionState(
        instruction="测试任务",
        task_text="测试任务",
        iterations=[{"status": "click"}],
        status_key="running",
        status_text="运行中",
    )
    owner._ui_task_state = state
    presenter = RuntimeStatePresenter(owner, state)
    session = TaskSessionController(
        host=FloatingTaskSessionHost(owner),
        state=state,
        session_history=SimpleNamespace(add_task=lambda **kwargs: history_entries.append(kwargs)),
        task_memory_store=SimpleNamespace(
            read=lambda: "remember 内容",
            clear=lambda: clear_calls.append("clear"),
        ),
        runtime_state_presenter=presenter,
    )
    return session, state


def test_floating_controller_clears_memory_after_interrupted_result():
    history_entries = []
    clear_calls = []
    session, state = _make_worker_result_test_session(history_entries, clear_calls)

    session.handle_worker_result("Task interrupted by user")

    assert clear_calls == ["clear"]
    assert history_entries[0]["status"] == "interrupted"
    assert history_entries[0]["memory"] == "remember 内容"
    assert state.iterations == []


def test_floating_controller_clears_memory_after_failed_result():
    history_entries = []
    clear_calls = []
    session, state = _make_worker_result_test_session(history_entries, clear_calls)

    session.handle_worker_result("Task failed: timeout")

    assert clear_calls == ["clear"]
    assert history_entries[0]["status"] == "failed"
    assert history_entries[0]["memory"] == "remember 内容"
    assert state.iterations == []


def test_floating_controller_clears_memory_after_completed_result():
    history_entries = []
    clear_calls = []
    session, state = _make_worker_result_test_session(history_entries, clear_calls)

    session.handle_worker_result("任务完成")

    assert clear_calls == ["clear"]
    assert history_entries[0]["status"] == "completed"
    assert history_entries[0]["memory"] == ""
    assert state.iterations == []


def test_interrupted_worker_result_restarts_wake_word_after_voice_exit():
    history_entries = []
    controller = FloatingController.__new__(FloatingController)
    controller._config = Config.create_isolated()
    controller._config.set("voice_interaction_config.enabled", True)
    controller._config.set("wake_word_config.enabled", True)
    controller._voice = _FakeAudioLifecycleController()
    controller._wake_word = _FakeWakeWordController()
    controller.is_pinned = False
    controller.is_edge_hidden = False
    controller.panel_window = SimpleNamespace(target_visible=False)
    controller.ball_window = SimpleNamespace(update=lambda: None)
    controller._console_window = None
    controller._disable_screenshot_protection = lambda: None
    controller._log_buffer = SimpleNamespace(append_log=lambda text, level: None)
    controller._is_waiting_for_tts = lambda: False
    controller._tts = SimpleNamespace(current_done_event=None, start_waiting=lambda: None)
    controller._show_history_if_idle = lambda: None

    state = UITaskSessionState(
        instruction="长任务",
        task_text="长任务",
        iterations=[{"status": "click"}],
        status_key="stopping",
        status_text="停止中",
    )
    controller._ui_task_state = state
    session = TaskSessionController(
        host=FloatingTaskSessionHost(controller),
        state=state,
        session_history=SimpleNamespace(add_task=lambda **kwargs: history_entries.append(kwargs)),
        task_memory_store=SimpleNamespace(read=lambda: "", clear=lambda: None),
        runtime_state_presenter=RuntimeStatePresenter(controller, state),
    )

    session.handle_worker_result("Task interrupted by user")

    assert state.status_key == "ready"
    assert history_entries[0]["status"] == "interrupted"
    assert controller._wake_word.start_calls == 1


def test_tts_wait_timeout_clears_voice_session_language():
    owner = SimpleNamespace()
    owner._config = Config.create_isolated()
    owner._active_wake_word_language = "en"
    owner._tts = SimpleNamespace(
        current_done_event=None,
        finish_waiting=lambda: None,
    )
    owner._is_waiting_for_tts = lambda: False
    owner._show_history_if_idle = lambda: None
    owner._sync_voice_interaction_state = lambda: None
    owner.panel_window = SimpleNamespace(set_idle_state=lambda: None)
    owner._console_window = None
    state = UITaskSessionState(status_key="ready", status_text="就绪")
    owner._ui_task_state = state
    presenter = RuntimeStatePresenter(owner, state)
    session = TaskSessionController(
        host=FloatingTaskSessionHost(owner),
        state=state,
        session_history=SimpleNamespace(),
        task_memory_store=SimpleNamespace(read=lambda: "", clear=lambda: None),
        runtime_state_presenter=presenter,
    )

    session.on_tts_wait_timeout()

    assert owner._active_wake_word_language == ""


def test_runtime_log_buffer_trims_history_and_emits_clear():
    buffer = RuntimeLogBuffer(max_entries=2)
    cleared = []
    buffer.cleared.connect(lambda: cleared.append(True))

    buffer.append_log("first\n", "info")
    buffer.append_log("second\n", "normal")
    buffer.append_log("third\n", "warning")

    assert buffer.history() == [
        ("second\n", "normal"),
        ("third\n", "warning"),
    ]

    buffer.clear()

    assert buffer.history() == []
    assert cleared == [True]


def test_tracker_records_last_external_frontmost_app():
    class _TrackerPlatformAdapter:
        def __init__(self, infos):
            self._infos = list(infos)
            self._index = 0

        def get_frontmost_app_info(self):
            if not self._infos:
                return {}
            current_index = min(self._index, len(self._infos) - 1)
            self._index += 1
            return dict(self._infos[current_index])

        def get_frontmost_window_info(self):
            return {"hwnd": 7788}

    tracker = FrontmostAppTracker(
        _TrackerPlatformAdapter([
            {"app_name": "Google Chrome", "bundle_id": "com.google.Chrome", "pid": 222},
        ]),
        own_pid=999,
    )

    tracker.observe_current_frontmost()

    assert tracker.snapshot_last_external_frontmost_app() == {
        "app_name": "Google Chrome",
        "bundle_id": "com.google.Chrome",
        "identifier": "",
        "pid": 222,
        "hwnd": 7788,
    }


def test_tracker_does_not_record_current_process_as_external_app():
    class _TrackerPlatformAdapter:
        def __init__(self, infos):
            self._infos = list(infos)
            self._index = 0

        def get_frontmost_app_info(self):
            if not self._infos:
                return {}
            current_index = min(self._index, len(self._infos) - 1)
            self._index += 1
            return dict(self._infos[current_index])

    tracker = FrontmostAppTracker(
        _TrackerPlatformAdapter([
            {"app_name": "CoViewAI", "bundle_id": "com.example.coview", "pid": 999},
        ]),
        own_pid=999,
    )

    tracker.observe_current_frontmost()

    assert tracker.snapshot_last_external_frontmost_app() is None
