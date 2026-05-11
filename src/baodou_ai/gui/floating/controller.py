"""Main controller for the floating overlay UI."""

from __future__ import annotations

import os
import platform
import sys
import time
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QAbstractNativeEventFilter, QObject, QPoint, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication, QWidget

from baodou_ai.ai.session_history import SessionHistory
from baodou_ai.code_agent.manager import JobManager
from baodou_ai.core.config import Config
from baodou_ai.core.screenshot import CAPTURE_EXCLUDE_PROPERTY
from baodou_ai.core.task_memory_store import TaskMemoryStore
from baodou_ai.gui.code_agent_window import CodeAgentJobWindow
from baodou_ai.gui.control_console import ControlConsoleWindow
from baodou_ai.gui.floating.background_activity_coordinator import FloatingBackgroundActivityCoordinator
from baodou_ai.gui.floating.background_jobs_controller import BackgroundJobsController
from baodou_ai.gui.floating.companion_controller import CompanionController
from baodou_ai.gui.floating.controller_delegates import (
    FloatingBackgroundJobsDelegate,
    FloatingCompanionDelegate,
    FloatingVoiceRuntimeCoordinator,
)
from baodou_ai.gui.floating.menu_controller import FloatingMenuController
from baodou_ai.gui.floating.overlay_window_coordinator import OverlayWindowCoordinator
from baodou_ai.gui.floating.platform_factory import (
    create_ball_window,
    create_edge_bar_window,
    create_panel_window,
    create_suggestion_window,
    create_taskbar_host_window,
    create_toast_window,
)
from baodou_ai.gui.floating.runtime_state_presenter import RuntimeStatePresenter
from baodou_ai.gui.floating.task_session_controller import TaskSessionController
from baodou_ai.gui.floating.task_session_host import FloatingTaskSessionHost
from baodou_ai.gui.floating.task_session_state import UITaskSessionState
from baodou_ai.gui.floating.tts_controller import TTSController
from baodou_ai.gui.floating.voice_controller import VoiceInteractionController
from baodou_ai.gui.frontmost_tracker import FrontmostAppTracker
from baodou_ai.gui.i18n import on_locale_changed, set_locale, t, translate
from baodou_ai.gui.runtime_log import RuntimeLogBuffer
from baodou_ai.gui.shortcut_config import (
    SHORTCUT_ACTION_ACTIVATE,
    SHORTCUT_ACTION_HIDE,
    get_configured_shortcut,
    macos_shortcut_matches_event,
    windows_shortcut_to_native,
)
from baodou_ai.platform import get_platform_adapter
from baodou_ai.platform import cancel_current_mouse_motion
from baodou_ai.voice.sherpa_keyword_spotter import WakeWordHit
from baodou_ai.voice.wake_word_engine import WakeWordEngine, WakeWordEngineStatus


def _get_windows_user32():
    import ctypes

    return ctypes.WinDLL("user32", use_last_error=True)


def _get_windows_last_error() -> int:
    try:
        import ctypes

        return int(ctypes.get_last_error())
    except Exception:
        return 0


def _normalize_native_event_type(event_type) -> str:
    try:
        return bytes(event_type).decode("ascii", "ignore")
    except Exception:
        return str(event_type)


class _WindowsGlobalHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, controller: "FloatingController") -> None:
        super().__init__()
        self._controller = controller

    def nativeEventFilter(self, event_type, message):
        try:
            event_name = _normalize_native_event_type(event_type)
            if event_name not in {"windows_generic_MSG", "windows_dispatcher_MSG"}:
                return False, 0

            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if int(msg.message) != self._controller.windows_hotkey_message_id():
                return False, 0
            handled = self._controller.handle_windows_hotkey_id(int(msg.wParam))
            return bool(handled), 0
        except Exception:
            return False, 0


class _WakeWordEventBridge(QObject):
    hit_received = pyqtSignal(object)
    state_received = pyqtSignal(object)


class FloatingController:
    """悬浮球应用主控制器。"""

    _LOCAL_INPUT_COMMAND_PAGES = {
        "/setting": "general",
        "/settings": "general",
        "/设置": "general",
    }

    _WINDOWS_WM_HOTKEY = 0x0312
    _WINDOWS_MOD_ALT = 0x0001
    _WINDOWS_MOD_CONTROL = 0x0002
    _WINDOWS_MOD_NOREPEAT = 0x4000
    _WINDOWS_VK_I = 0x49
    _WINDOWS_VK_O = 0x4F
    _WINDOWS_HOTKEY_ACTIVATE_ID = 0xBA01
    _WINDOWS_HOTKEY_HIDE_ID = 0xBA02

    def __init__(self, app: QApplication, config: Optional[Config] = None, log_buffer: Optional[RuntimeLogBuffer] = None):
        self.app = app
        self._config = config or Config()
        self._task_memory_store = TaskMemoryStore()
        self._log_buffer = log_buffer
        if self._log_buffer is None:
            raise ValueError("FloatingController 需要传入已初始化的 RuntimeLogBuffer")
        self._platform_adapter = get_platform_adapter()
        self._job_manager = JobManager(self._config)
        self._frontmost_tracker = FrontmostAppTracker(self._platform_adapter, own_pid=os.getpid())
        self._frontmost_timer = QTimer()
        self._frontmost_timer.setInterval(700)
        self._frontmost_timer.timeout.connect(self._observe_frontmost_app)
        self._job_poll_timer = QTimer()
        self._job_poll_timer.setInterval(500)
        self._job_poll_timer.timeout.connect(self._poll_background_jobs)

        self.ball_size = 72
        self.expanded_width = 320
        self.expanded_height = 420
        self.ball_anchor = QPoint(0, 0)
        self.expand_direction = "left"
        self.v_expand_direction = "up"
        self.is_pinned = False
        self.is_dragging = False
        self.is_edge_hidden = False
        self.edge_side = "right"
        self._interaction_reasons: set[str] = set()
        self._interaction_idle_timer = QTimer()
        self._interaction_idle_timer.setSingleShot(True)
        self._interaction_idle_timer.timeout.connect(lambda: self.end_interaction("pointer"))
        self._ui_perf_timer: Optional[QTimer] = None
        self._ui_perf_last_tick = 0.0
        self._last_voice_indicator_state = ""
        self._last_voice_indicator_level = -1.0
        self._last_voice_indicator_at = 0.0
        self._active_wake_word_language = ""

        locale = self._config.locale_config.get("locale", "zh_CN")
        set_locale(locale)

        self.ball_window = create_ball_window(self)
        self.panel_window = create_panel_window(self)
        self.edge_bar = create_edge_bar_window(self)
        self.suggestion_window = create_suggestion_window(self)
        self.toast_window = create_toast_window(self)
        self._taskbar_host_window = create_taskbar_host_window(self)
        self._overlay = OverlayWindowCoordinator(self)
        self._snap_anim = self._overlay.snap_anim
        self._unsnap_anim = self._overlay.unsnap_anim
        self.collapse_timer = self._overlay.collapse_timer
        self.hover_timer = self._overlay.hover_timer

        self._console_window: Optional[ControlConsoleWindow] = None
        self._background_activity = FloatingBackgroundActivityCoordinator(self)
        self._background_jobs_delegate = FloatingBackgroundJobsDelegate(self)
        self._background_jobs = BackgroundJobsController(
            config=self._config,
            job_manager=self._job_manager,
            delegate=self._background_jobs_delegate,
        )
        self._job_windows = self._background_jobs.job_windows
        self._suppressed_job_window_ids = self._background_jobs.suppressed_job_window_ids
        self._session_history = SessionHistory(max_tasks=int(self._config.get("memory_config.history_count", 5)))
        self._ui_task_state = UITaskSessionState(
            status_key="ready",
            status_text=t("agent_ready"),
            max_iterations=int(self._config.execution_config.get("default_max_iterations", 80) or 80),
        )
        self._runtime_state_presenter = RuntimeStatePresenter(self, self._ui_task_state)
        self._task_session_controller = TaskSessionController(
            host=FloatingTaskSessionHost(self),
            state=self._ui_task_state,
            session_history=self._session_history,
            task_memory_store=self._task_memory_store,
            runtime_state_presenter=self._runtime_state_presenter,
        )
        on_locale_changed(self._on_locale_changed)

        self._global_hotkey_monitor = None
        self._local_hotkey_monitor = None
        self._windows_user32 = None
        self._windows_hotkey_hwnd: Optional[int] = None
        self._windows_registered_hotkey_ids: List[int] = []
        self._windows_hotkey_filter = None
        self._tts = TTSController(self._config, self._on_tts_wait_timeout)
        self._voice_runtime = FloatingVoiceRuntimeCoordinator(self)
        self._voice = VoiceInteractionController(self, self._config, self._log_buffer)
        self._wake_word_bridge = _WakeWordEventBridge()
        self._wake_word_bridge.hit_received.connect(self._handle_wake_word_hit)
        self._wake_word_bridge.state_received.connect(self._handle_wake_word_state_change)
        self._wake_word = WakeWordEngine(
            self._config,
            log_buffer=self._log_buffer,
            on_hit=lambda hit: self._wake_word_bridge.hit_received.emit(hit),
            on_state_change=lambda status: self._wake_word_bridge.state_received.emit(status),
        )
        self._menu_controller = FloatingMenuController(
            self.open_console,
            self.clear_history,
            self.shutdown,
            self.is_companion_enabled,
            self.toggle_companion_enabled,
            self.begin_interaction,
            self.end_interaction,
        )
        self._companion_delegate = FloatingCompanionDelegate(self)
        self._companion = CompanionController(
            controller=self,
            delegate=self._companion_delegate,
            config=self._config,
            platform_adapter=self._platform_adapter,
        )
        try:
            self.suggestion_window.clicked.connect(self._on_suggestion_clicked)
        except Exception:
            pass

    @property
    def platform_adapter(self):
        return self._platform_adapter

    def _ensure_background_activity(self) -> FloatingBackgroundActivityCoordinator:
        coordinator = getattr(self, "_background_activity", None)
        if coordinator is None:
            coordinator = FloatingBackgroundActivityCoordinator(self)
            self._background_activity = coordinator
        return coordinator

    def _ensure_background_jobs_delegate(self) -> FloatingBackgroundJobsDelegate:
        delegate = getattr(self, "_background_jobs_delegate", None)
        if delegate is None:
            delegate = FloatingBackgroundJobsDelegate(self)
            self._background_jobs_delegate = delegate
        return delegate

    def _ensure_companion_delegate(self) -> FloatingCompanionDelegate:
        delegate = getattr(self, "_companion_delegate", None)
        if delegate is None:
            delegate = FloatingCompanionDelegate(self)
            self._companion_delegate = delegate
        return delegate

    def _ensure_voice_runtime(self) -> FloatingVoiceRuntimeCoordinator:
        runtime = getattr(self, "_voice_runtime", None)
        if runtime is None:
            runtime = FloatingVoiceRuntimeCoordinator(self)
            self._voice_runtime = runtime
        return runtime

    @classmethod
    def windows_hotkey_message_id(cls) -> int:
        return cls._WINDOWS_WM_HOTKEY

    def handle_windows_hotkey_id(self, hotkey_id: int) -> bool:
        return self._handle_windows_hotkey_id(hotkey_id)

    def _setup_global_hotkey(self) -> None:
        if sys.platform == "darwin":
            self._setup_macos_global_hotkey()
        elif sys.platform == "win32":
            self._setup_windows_global_hotkey()

    def _setup_macos_global_hotkey(self) -> None:
        try:
            from AppKit import NSEvent
        except ImportError:
            return

        try:
            NSKeyDownMask = 1 << 10

            self._global_hotkey_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSKeyDownMask, self._global_hotkey_handler
            )
            self._local_hotkey_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                NSKeyDownMask, self._local_hotkey_handler
            )
        except Exception:
            self._global_hotkey_monitor = None
            self._local_hotkey_monitor = None

    def _configured_windows_hotkeys(self) -> List[tuple[int, int, int, str]]:
        hotkeys: List[tuple[int, int, int, str]] = []
        for hotkey_id, action in (
            (self._WINDOWS_HOTKEY_ACTIVATE_ID, SHORTCUT_ACTION_ACTIVATE),
            (self._WINDOWS_HOTKEY_HIDE_ID, SHORTCUT_ACTION_HIDE),
        ):
            keys = get_configured_shortcut(
                getattr(self, "_config", None),
                action,
                "windows",
            )
            native = windows_shortcut_to_native(keys)
            if native is None:
                continue
            modifiers, virtual_key = native
            label = "+".join(keys)
            hotkeys.append(
                (hotkey_id, modifiers | self._WINDOWS_MOD_NOREPEAT, virtual_key, label)
            )
        return hotkeys

    def _setup_windows_global_hotkey(self) -> None:
        if getattr(self, "_windows_registered_hotkey_ids", []):
            return

        try:
            import ctypes
            from ctypes import wintypes

            user32 = _get_windows_user32()
            try:
                user32.RegisterHotKey.argtypes = [
                    wintypes.HWND,
                    ctypes.c_int,
                    ctypes.c_uint,
                    ctypes.c_uint,
                ]
                user32.RegisterHotKey.restype = wintypes.BOOL
                user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
                user32.UnregisterHotKey.restype = wintypes.BOOL
            except Exception:
                pass

            hotkey_hwnd = int(self.ball_window.winId())
            if not hotkey_hwnd:
                self._log_buffer.append_log(
                    "[WARNING] Windows global hotkey setup failed: missing window handle\n",
                    "warning",
                )
                self._windows_user32 = None
                return

            self._windows_user32 = user32
            self._windows_hotkey_hwnd = hotkey_hwnd
            self._windows_registered_hotkey_ids = []
            for hotkey_id, modifiers, virtual_key, label in self._configured_windows_hotkeys():
                registered = bool(
                    user32.RegisterHotKey(hotkey_hwnd, hotkey_id, modifiers, virtual_key)
                )
                if registered:
                    self._windows_registered_hotkey_ids.append(hotkey_id)
                    continue

                error_code = _get_windows_last_error()
                self._log_buffer.append_log(
                    f"[WARNING] Windows global hotkey registration failed: "
                    f"{label} (code: {error_code})\n",
                    "warning",
                )

            if not self._windows_registered_hotkey_ids:
                self._windows_user32 = None
                return

            self._windows_hotkey_filter = _WindowsGlobalHotkeyFilter(self)
            self.app.installNativeEventFilter(self._windows_hotkey_filter)
        except Exception as exc:
            try:
                self._teardown_windows_global_hotkey()
            except Exception:
                pass
            self._windows_user32 = None
            self._windows_registered_hotkey_ids = []
            self._windows_hotkey_filter = None
            self._log_buffer.append_log(
                f"[WARNING] Windows global hotkey setup failed: {exc}\n",
                "warning",
            )

    def _teardown_global_hotkey(self) -> None:
        if sys.platform == "win32":
            self._teardown_windows_global_hotkey()
            return
        self._teardown_macos_global_hotkey()

    def _refresh_global_hotkey(self) -> None:
        self._teardown_global_hotkey()
        self._setup_global_hotkey()

    def _teardown_macos_global_hotkey(self) -> None:
        try:
            from AppKit import NSEvent
        except ImportError:
            return

        if self._global_hotkey_monitor is not None:
            NSEvent.removeMonitor_(self._global_hotkey_monitor)
            self._global_hotkey_monitor = None
        if self._local_hotkey_monitor is not None:
            NSEvent.removeMonitor_(self._local_hotkey_monitor)
            self._local_hotkey_monitor = None

    def _teardown_windows_global_hotkey(self) -> None:
        hotkey_filter = getattr(self, "_windows_hotkey_filter", None)
        if hotkey_filter is not None:
            try:
                self.app.removeNativeEventFilter(hotkey_filter)
            except Exception:
                pass
            self._windows_hotkey_filter = None

        user32 = getattr(self, "_windows_user32", None)
        hotkey_hwnd = int(getattr(self, "_windows_hotkey_hwnd", 0) or 0)
        registered_ids = list(getattr(self, "_windows_registered_hotkey_ids", []))
        if user32 is not None:
            for hotkey_id in registered_ids:
                try:
                    user32.UnregisterHotKey(hotkey_hwnd, hotkey_id)
                except Exception:
                    pass

        self._windows_registered_hotkey_ids = []
        self._windows_hotkey_hwnd = None
        self._windows_user32 = None

    def _is_hotkey_event(self, event) -> bool:
        keys = get_configured_shortcut(
            getattr(self, "_config", None),
            SHORTCUT_ACTION_ACTIVATE,
            "macos",
        )
        return macos_shortcut_matches_event(keys, event)

    def _is_hide_hotkey_event(self, event) -> bool:
        keys = get_configured_shortcut(
            getattr(self, "_config", None),
            SHORTCUT_ACTION_HIDE,
            "macos",
        )
        return macos_shortcut_matches_event(keys, event)

    def _global_hotkey_handler(self, event) -> None:
        try:
            if self._is_hotkey_event(event):
                QTimer.singleShot(0, self.activate_from_hotkey)
            elif self._is_hide_hotkey_event(event):
                QTimer.singleShot(0, self.collapse_from_hotkey)
        except Exception:
            pass

    def _local_hotkey_handler(self, event):
        try:
            if self._is_hotkey_event(event):
                QTimer.singleShot(0, self.activate_from_hotkey)
                return None
            if self._is_hide_hotkey_event(event):
                QTimer.singleShot(0, self.collapse_from_hotkey)
                return None
            return event
        except Exception:
            return event

    def _handle_windows_hotkey_id(self, hotkey_id: int) -> bool:
        if hotkey_id == self._WINDOWS_HOTKEY_ACTIVATE_ID:
            QTimer.singleShot(0, self._activate_from_windows_hotkey)
            return True
        if hotkey_id == self._WINDOWS_HOTKEY_HIDE_ID:
            QTimer.singleShot(0, self.collapse_from_hotkey)
            return True
        return False

    def _activate_from_windows_hotkey(self) -> None:
        self.activate_from_hotkey()
        self._focus_panel_input_from_hotkey()
        QTimer.singleShot(120, self._focus_panel_input_from_hotkey)
        QTimer.singleShot(420, self._focus_panel_input_from_hotkey)

    def _focus_panel_input_from_hotkey(self) -> None:
        try:
            if not self.panel_window.target_visible:
                return
            input_area = self.panel_window.input_area
            if hasattr(input_area, "isVisible") and not input_area.isVisible():
                return
            if hasattr(self.panel_window, "raise_"):
                self.panel_window.raise_()
            if hasattr(self.panel_window, "activateWindow"):
                self.panel_window.activateWindow()
            input_area.setFocus(Qt.OtherFocusReason)
        except Exception:
            pass

    def activate_from_hotkey(self) -> None:
        self._overlay.activate_from_hotkey()

    def hide_to_edge(self) -> None:
        self._overlay.hide_to_edge()

    def collapse_from_hotkey(self) -> None:
        overlay = getattr(self, "_overlay", None)
        if overlay is not None:
            overlay.collapse_from_hotkey()
            return
        # Legacy fallback for tests building controller via __new__.
        self._mark_voice_user_interaction()
        if self._task_active() or self.is_edge_hidden:
            return
        self.is_pinned = False
        self.panel_window.pinned_active = False
        self.ball_window.update()
        self.panel_window.update()
        self._sync_voice_interaction_state()
        self.collapse_timer.stop()
        self.collapse_instantly()

    def _nearest_edge(self) -> Optional[str]:
        return self._overlay.nearest_edge()

    def start(self) -> None:
        primary_screen = self.app.primaryScreen()
        screen_geometry = primary_screen.geometry()
        if self._taskbar_host_window is not None:
            self._taskbar_host_window.show_for_taskbar()
        self.ball_anchor = QPoint(
            screen_geometry.x() + screen_geometry.width() - 100,
            screen_geometry.y() + screen_geometry.height() // 2 - self.ball_size // 2,
        )
        self.ball_window.move_to_anchor(self.ball_anchor)
        self.ball_window.show()
        self.panel_window.set_idle_state()
        self._show_history_if_idle()
        self.keep_ball_on_top()
        self._overlay._sync_hover_timer()
        self._sync_background_activity_timers()
        if self._frontmost_timer.isActive():
            self._observe_frontmost_app()
        self._start_ui_perf_probe()
        self._setup_global_hotkey()
        self._sync_voice_interaction_state()
        self._log_buffer.append_log("[READY] 悬浮球主界面已启动\n", "success")

    def protect_window(self, window: QWidget) -> None:
        window.setProperty(CAPTURE_EXCLUDE_PROPERTY, True)
        self._platform_adapter.setup_window(window)

    def _enable_screenshot_protection(self) -> None:
        for w in self._managed_windows():
            self._platform_adapter.prevent_screenshot(w)

    def _disable_screenshot_protection(self) -> None:
        for w in self._managed_windows():
            self._platform_adapter.allow_screenshot(w)

    def _show_history_if_idle(self) -> None:
        if self._task_active():
            return
        current_max = int(self._config.get("memory_config.history_count", 5))
        self._session_history.set_max_tasks(current_max)
        tasks = self._session_history.get_recent_tasks()
        self.panel_window.show_history(tasks)


    def clear_history(self) -> None:
        self._session_history.clear()
        if not self._task_active():
            self.panel_window.show_history([])

    def _managed_windows(self) -> List[QWidget]:
        windows: List[QWidget] = []
        for attr_name in ("ball_window", "panel_window", "edge_bar", "suggestion_window", "toast_window"):
            window = getattr(self, attr_name, None)
            if window is not None:
                windows.append(window)
        if platform.system() == "Darwin":
            console_window = getattr(self, "_console_window", None)
            if console_window is not None:
                windows.append(console_window)
        return windows

    def close_console_for_task_start(self) -> None:
        if platform.system() != "Windows":
            return
        window = self._console_window
        if window is None:
            return
        try:
            window.close()
        except Exception:
            pass

    def _ensure_console_window(self) -> ControlConsoleWindow:
        if self._console_window is None:
            self._console_window = ControlConsoleWindow(
                self._config,
                self._log_buffer,
                job_manager=self._job_manager,
                on_config_changed=self._handle_console_config_changed,
            )
            self._runtime_state_presenter.sync_console_window(self._console_window)
        return self._console_window

    def _handle_console_config_changed(self, key: str, value) -> None:
        if key.startswith("shortcut_config."):
            self._refresh_global_hotkey()
        if key.startswith("floating_ball_config."):
            self.ball_window.reload_asset()
        if key.startswith("voice_interaction_config."):
            wake_word = getattr(self, "_wake_word", None)
            if wake_word is not None:
                wake_word.refresh_config()
            self._sync_voice_interaction_state()
        if key.startswith("wake_word_config."):
            wake_word = getattr(self, "_wake_word", None)
            if wake_word is not None:
                wake_word.refresh_config()
            self._sync_voice_interaction_state()
        if key.startswith("companion_config.") or key.startswith("companion_privacy_config."):
            companion = getattr(self, "_companion", None)
            refresh = getattr(companion, "refresh_config", None)
            if callable(refresh):
                refresh()
            self._sync_background_activity_timers()

    def open_console(self, page_index: int = 0) -> None:
        self._mark_voice_user_interaction()
        window = self._ensure_console_window()
        window.switch_to_page(page_index)
        window.show()
        window.raise_()
        window.activateWindow()

    def open_console_page(self, page_id: str = "general") -> None:
        self._mark_voice_user_interaction()
        window = self._ensure_console_window()
        window.switch_to_page_id(page_id)
        window.show()
        window.raise_()
        window.activateWindow()

    def show_ball_context_menu(self, global_pos: QPoint) -> None:
        self._mark_voice_user_interaction()
        self._menu_controller.show_ball_context_menu(global_pos)

    def on_ball_hover_enter(self) -> None:
        self._overlay.on_ball_hover_enter()

    def is_companion_enabled(self) -> bool:
        config = getattr(self, "_config", None)
        if config is None:
            return True
        return bool(config.get("companion_config.enabled", True))

    def toggle_companion_enabled(self) -> None:
        enabled = not self.is_companion_enabled()
        self._config.set("companion_config.enabled", enabled)
        self._config.save()
        companion = getattr(self, "_companion", None)
        refresh = getattr(companion, "refresh_config", None)
        if callable(refresh):
            refresh()
        if not enabled:
            hide = getattr(companion, "hide_suggestions", None)
            if callable(hide):
                hide()
        if self._console_window is not None:
            try:
                self._console_window._load_config_values()
            except Exception:
                pass
        self.show_companion_toast(
            t("companion_toast_enabled") if enabled else t("companion_toast_disabled")
        )

    def show_companion_toast(self, text: str) -> None:
        try:
            self.toast_window.show_message(self.ball_anchor, text)
        except Exception:
            pass

    def keep_ball_on_top(self, raise_windows: bool = True, sync_helpers: bool = True) -> None:
        if not self.is_edge_hidden:
            self.ball_window._apply_window_mode()
            if not self.ball_window.isVisible():
                self.ball_window.show()
            if raise_windows:
                if self.panel_window.isVisible() and self.panel_window.target_visible:
                    self.panel_window.raise_()
                self.ball_window.raise_()
            self.ball_window.update()
            if sync_helpers:
                companion = getattr(self, "_companion", None)
                reposition = getattr(companion, "reposition", None)
                if callable(reposition):
                    reposition()
                try:
                    self.toast_window.reposition(self.ball_anchor)
                except Exception:
                    pass
        if raise_windows and self.edge_bar.isVisible():
            self.edge_bar.raise_()

    def _should_observe_frontmost(self) -> bool:
        return self._ensure_background_activity().should_observe_frontmost()

    def _background_jobs_active(self) -> bool:
        return self._ensure_background_activity().background_jobs_active()

    def _sync_background_activity_timers(self) -> None:
        self._ensure_background_activity().sync_timers()

    def _observe_frontmost_app(self) -> None:
        self._ensure_background_activity().observe_frontmost_app()

    def _poll_background_jobs(self) -> None:
        self._ensure_background_activity().poll_background_jobs()

    def _start_ui_perf_probe(self) -> None:
        if str(os.environ.get("COVIEW_FLOATING_PERF", "")).strip() != "1":
            return
        if self._ui_perf_timer is not None:
            return
        self._ui_perf_last_tick = time.monotonic()
        self._ui_perf_timer = QTimer()
        self._ui_perf_timer.setInterval(100)
        self._ui_perf_timer.timeout.connect(self._check_ui_event_loop_gap)
        self._ui_perf_timer.start()

    def _check_ui_event_loop_gap(self) -> None:
        now = time.monotonic()
        gap_ms = int((now - float(self._ui_perf_last_tick or now)) * 1000)
        self._ui_perf_last_tick = now
        if gap_ms <= 300:
            return
        active = ",".join(sorted(self._interaction_reasons)) or "idle"
        self._log_buffer.append_log(
            f"[FLOATING_UI_STALL] event_loop_gap_ms={gap_ms} active={active}\n",
            "warning",
        )

    def _log_background_job_event(self, event: Dict[str, Any]) -> None:
        self._background_jobs.log_event(event)

    def _sync_memory_job_windows(self) -> None:
        self._background_jobs.sync_memory_job_windows()

    def _sync_job_window(self, job_id: str, auto_open: bool = False) -> None:
        self._background_jobs.sync_job_window(job_id, auto_open=auto_open)

    def _ensure_job_window(self, job_id: str) -> tuple[CodeAgentJobWindow, bool]:
        return self._background_jobs.ensure_job_window(job_id)

    def _position_job_window(self, window: CodeAgentJobWindow) -> None:
        self._background_jobs.position_job_window(window)

    def _handle_job_window_closed(self, job_id: str) -> None:
        self._background_jobs.handle_job_window_closed(job_id)

    def _close_job_window(self, job_id: str) -> None:
        self._background_jobs.close_job_window(job_id)

    def _handle_background_job_report(self, report: Dict[str, Any]) -> str:
        return self._background_jobs.handle_report(report)

    @staticmethod
    def _format_background_job_report(report: Dict[str, Any]) -> str:
        return BackgroundJobsController.format_report(report)

    @classmethod
    def _format_background_job_context_report(cls, report: Dict[str, Any], fallback: str = "") -> str:
        return BackgroundJobsController.format_context_report(report, fallback=fallback)

    @staticmethod
    def _clip_text(text: str, limit: int) -> str:
        return BackgroundJobsController.clip_text(text, limit)

    def _determine_expand_direction(self) -> None:
        self._overlay.determine_expand_direction()

    def _is_hovering_any(self) -> bool:
        return self._overlay.is_hovering_any()

    def _mark_voice_user_interaction(self) -> None:
        self._ensure_voice_runtime().mark_user_interaction()

    def begin_interaction(self, reason: str) -> None:
        normalized = str(reason or "interaction").strip() or "interaction"
        self._interaction_reasons.add(normalized)
        if normalized == "pointer":
            self._interaction_idle_timer.stop()
        companion = getattr(self, "_companion", None)
        pause = getattr(companion, "pause_for_interaction", None)
        if callable(pause):
            pause()

    def end_interaction(self, reason: str) -> None:
        normalized = str(reason or "interaction").strip() or "interaction"
        self._interaction_reasons.discard(normalized)

    def defer_pointer_interaction_end(self, delay_ms: int = 350) -> None:
        if "pointer" in self._interaction_reasons:
            self._interaction_idle_timer.start(max(0, int(delay_ms)))

    def is_interaction_busy(self) -> bool:
        return bool(getattr(self, "_interaction_reasons", set()))

    @staticmethod
    def _t(key: str) -> str:
        return t(key)

    def _reposition_companion_window(self) -> None:
        companion = getattr(self, "_companion", None)
        reposition = getattr(companion, "reposition", None)
        if callable(reposition):
            reposition()

    def _hide_companion_suggestions(self) -> None:
        companion = getattr(self, "_companion", None)
        hide = getattr(companion, "hide_suggestions", None)
        if callable(hide):
            hide()

    def _hide_toast_window(self) -> None:
        try:
            self.toast_window.hide_message()
        except Exception:
            pass

    def _reposition_toast_window(self) -> None:
        try:
            self.toast_window.reposition(self.ball_anchor)
        except Exception:
            pass

    def _sync_voice_interaction_state(self) -> None:
        self._ensure_voice_runtime().sync_voice_interaction_state()

    def _should_run_wake_word(self, should_run_voice: Optional[bool] = None) -> bool:
        return self._ensure_voice_runtime().should_run_wake_word(should_run_voice)

    def _handle_wake_word_hit(self, hit: WakeWordHit) -> None:
        self._ensure_voice_runtime().handle_wake_word_hit(hit)

    def _announce_wake_word_ack(self) -> None:
        self._ensure_voice_runtime()._announce_wake_word_ack()

    def _queue_wake_word_ack_finalize(self, announced) -> None:
        QTimer.singleShot(200, lambda: self._finalize_wake_word_ack(announced))

    def _finalize_wake_word_ack(self, announced) -> None:
        self._ensure_voice_runtime().finalize_wake_word_ack(announced)

    def _handle_wake_word_state_change(self, status: WakeWordEngineStatus) -> None:
        self._ensure_voice_runtime().handle_wake_word_state_change(status)

    def _wake_word_indicator_payload(self, status: WakeWordEngineStatus) -> tuple[str, float]:
        return self._ensure_voice_runtime().wake_word_indicator_payload(status)

    def _show_wake_word_feedback(self, status: WakeWordEngineStatus) -> None:
        self._ensure_voice_runtime()._show_wake_word_feedback(status)

    def _wake_word_feedback_text(self, status: WakeWordEngineStatus) -> str:
        return self._ensure_voice_runtime().wake_word_feedback_text(status)

    def _wake_word_phrase_summary(self) -> str:
        return self._ensure_voice_runtime().wake_word_phrase_summary()

    # VoiceInteractionDelegate
    def is_task_active(self) -> bool:
        return self._task_active()

    def is_waiting_for_tts(self) -> bool:
        return self._is_waiting_for_tts()

    def current_status_key(self) -> str:
        return str(self._current_status_key)

    def current_task_text(self) -> str:
        return str(self._current_task_text)

    def current_tts_text(self) -> str:
        return str(getattr(self._tts, "current_text", "") or "")

    def get_active_respond_language(self) -> str:
        override_locale = self._voice_locale_override()
        if override_locale == "en_US":
            return "English"
        if override_locale == "zh_CN":
            return "Chinese (Simplified)"
        return self._config.get_respond_language()

    def localize_tts_text(self, text: str) -> str:
        return TTSController.localize_text(text, self._voice_locale_override())

    def clear_voice_session_language(self) -> None:
        self._clear_active_wake_word_language()

    def submit_voice_task(self, text: str) -> None:
        self.handle_voice_submit(text)

    def can_handle_idle_dismiss(self) -> bool:
        return bool(self.is_pinned and self.panel_window.target_visible and not self._task_active() and not self._is_waiting_for_tts())

    def can_handle_priority_exit_command(self) -> bool:
        return bool(self.is_pinned and self.panel_window.target_visible)

    def apply_voice_indicator(self, state: str, level: float) -> None:
        self._ensure_voice_runtime().apply_voice_indicator(state, level)

    def is_busy(self) -> bool:
        return self._ensure_background_jobs_delegate().is_busy()

    def append_log(self, text: str, level: str) -> None:
        self._ensure_background_jobs_delegate().append_log(text, level)

    def refresh_console_jobs(self) -> None:
        self._ensure_background_jobs_delegate().refresh_console_jobs()

    def add_history_task(self, **payload) -> None:
        self._ensure_background_jobs_delegate().add_history_task(**payload)

    def display_background_report(self, text: str) -> None:
        self._ensure_background_jobs_delegate().display_background_report(text)

    def announce_report(self, text: str) -> Optional[threading.Event]:
        return self._ensure_background_jobs_delegate().announce_report(text)

    def can_show_companion(self) -> bool:
        return self._ensure_companion_delegate().can_show_companion()

    def hide_suggestions(self) -> None:
        self._ensure_companion_delegate().hide_suggestions()

    def show_suggestions(self, suggestions: List[str]) -> None:
        self._ensure_companion_delegate().show_suggestions(suggestions)

    def show_privacy_notice(self, text: str) -> None:
        self._ensure_companion_delegate().show_privacy_notice(text)

    def reposition_suggestions(self) -> None:
        self._ensure_companion_delegate().reposition_suggestions()

    def enter_capture_mode(self) -> None:
        self._ensure_companion_delegate().enter_capture_mode()

    def exit_capture_mode(self) -> None:
        self._ensure_companion_delegate().exit_capture_mode()

    def _task_active(self) -> bool:
        task_controller = getattr(self, "_task_session_controller", None)
        if task_controller is None:
            return self.__dict__.get("__legacy_current_status_key", "ready") in {"running", "stopping"}
        return task_controller.task_active()

    @property
    def _current_status_key(self) -> str:
        state = getattr(self, "_ui_task_state", None)
        if state is None:
            return self.__dict__.get("__legacy_current_status_key", "ready")
        return state.status_key

    @_current_status_key.setter
    def _current_status_key(self, value: str) -> None:
        normalized = str(value or "ready")
        state = getattr(self, "_ui_task_state", None)
        if state is None:
            self.__dict__["__legacy_current_status_key"] = normalized
            return
        state.status_key = normalized

    @property
    def _current_task_text(self) -> str:
        state = getattr(self, "_ui_task_state", None)
        if state is None:
            return self.__dict__.get("__legacy_current_task_text", "")
        return state.task_text

    @_current_task_text.setter
    def _current_task_text(self, value: str) -> None:
        normalized = str(value or "")
        state = getattr(self, "_ui_task_state", None)
        if state is None:
            self.__dict__["__legacy_current_task_text"] = normalized
            return
        state.task_text = normalized

    def _check_global_hover(self) -> None:
        self._overlay.check_global_hover()

    def expand(self) -> None:
        self._overlay.expand()

    def collapse(self) -> None:
        self._overlay.collapse()

    def collapse_instantly(self) -> None:
        overlay = getattr(self, "_overlay", None)
        if overlay is not None:
            overlay.collapse_instantly()
            return
        # Legacy fallback for tests building controller via __new__.
        self.collapse_timer.stop()
        self.panel_window.hide_immediately()
        self.keep_ball_on_top(raise_windows=False)
        self._sync_voice_interaction_state()
        self._reposition_companion_window()

    def on_ball_click(self) -> None:
        self._overlay.on_ball_click()

    def on_ball_long_press(self) -> None:
        self._overlay.on_ball_long_press()

    def on_ball_drag(self, new_anchor: QPoint) -> None:
        self._overlay.on_ball_drag(new_anchor)

    def on_ball_drag_finished(self) -> None:
        self._overlay.on_ball_drag_finished()

    def _check_edge_snap(self) -> Optional[str]:
        return self._overlay.check_edge_snap()

    def snap_to_edge(self, edge_side: str) -> None:
        self._overlay.snap_to_edge(edge_side)

    def _on_snap_finished(self) -> None:
        self._overlay._on_snap_finished()

    def unsnap_from_edge(self, global_pos: QPoint) -> None:
        self._overlay.unsnap_from_edge(global_pos)

    def _on_unsnap_finished(self) -> None:
        self._overlay._on_unsnap_finished()

    def handle_submit(self, text: str) -> None:
        if self._task_active():
            return
        self._mark_voice_user_interaction()
        companion = getattr(self, "_companion", None)
        hide = getattr(companion, "hide_suggestions", None)
        if callable(hide):
            hide()
        if self._handle_local_input_command(text):
            return
        self._start_task(text, source="keyboard")

    def _handle_suggestion_submit(self, text: str) -> None:
        if self._task_active():
            return
        task = str(text or "").strip()
        if not task:
            return
        self._mark_voice_user_interaction()
        companion = getattr(self, "_companion", None)
        hide = getattr(companion, "hide_suggestions", None)
        if callable(hide):
            hide()
        self._start_task(task, source="companion", focus_panel=False)

    def handle_voice_submit(self, text: str) -> None:
        if self._task_active():
            return
        self._start_task(text, source="voice")

    def _start_task(self, text: str, source: str = "keyboard", focus_panel: bool = True) -> None:
        self._task_session_controller.start_task(text, source=source, focus_panel=focus_panel)

    def _handle_local_input_command(self, text: str) -> bool:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return False
        page_id = self._LOCAL_INPUT_COMMAND_PAGES.get(normalized_text.lower())
        if page_id is None:
            return False
        self.open_console_page(page_id)
        return True

    def request_voice_stop(self) -> None:
        self._task_session_controller.request_voice_stop()

    def request_voice_new_task(self, text: str) -> None:
        self._task_session_controller.request_voice_new_task(text)

    def _start_pending_voice_task(self) -> bool:
        return self._task_session_controller.start_pending_voice_task()

    def handle_voice_idle_timeout(self) -> None:
        self._dismiss_pinned_panel_from_voice("[VOICE] 空闲超时，自动取消固定并收起显示框\n")

    def handle_voice_exit_command(self) -> None:
        self._force_stop_and_collapse_from_voice("[VOICE] 收到退出程序口令，强制停止并收起显示框\n")

    def handle_voice_dismiss_command(self) -> None:
        self._dismiss_pinned_panel_from_voice("[VOICE] 收到退下指令，取消固定并收起显示框\n")

    def _force_stop_and_collapse_from_voice(self, log_message: str) -> None:
        if not self.can_handle_priority_exit_command():
            return
        self._task_session_controller.handle_voice_exit_request()
        self.is_pinned = False
        self.panel_window.pinned_active = False
        self.ball_window.update()
        self.panel_window.update()
        self._log_buffer.append_log(log_message, "warning")
        self._hide_companion_suggestions()
        self.collapse_timer.stop()
        self.collapse_instantly()

    def _dismiss_pinned_panel_from_voice(self, log_message: str) -> None:
        if self._task_active() or self._is_waiting_for_tts():
            return
        if not self.is_pinned:
            return
        self.is_pinned = False
        self.panel_window.pinned_active = False
        self.ball_window.update()
        self.panel_window.update()
        self._log_buffer.append_log(log_message, "info")
        self.collapse()

    def _on_report(self, text: str):
        spoken_text = TTSController.localize_text(text, self._voice_locale_override())
        return self._tts.speak(spoken_text)

    def _is_waiting_for_tts(self) -> bool:
        return self._tts.is_waiting()

    def _on_tts_wait_timeout(self) -> None:
        self._task_session_controller.on_tts_wait_timeout()

    def handle_stop_request(self) -> None:
        self._task_session_controller.handle_stop_request()

    def _handle_iteration_update(self, iteration_index: int, payload: Dict[str, Any]) -> None:
        self._task_session_controller.handle_iteration_update(iteration_index, payload)

    def _handle_stream_chunk(self, iteration: int, chunk: str) -> None:
        self._task_session_controller.handle_stream_chunk(iteration, chunk)

    def _handle_worker_result(self, result: str) -> None:
        self._task_session_controller.handle_worker_result(result)

    def _read_memory_content(self) -> str:
        return self._task_memory_store.read()

    def _clear_memory_txt(self) -> None:
        self._task_memory_store.clear()

    def _handle_worker_error(self, error: str) -> None:
        self._task_session_controller.handle_worker_error(error)

    def _set_runtime_state(self, status_key: str, status_text: str) -> None:
        self._runtime_state_presenter.apply_runtime_state(status_key, status_text)

    def _on_locale_changed(self) -> None:
        if self.panel_window is not None:
            self.panel_window.input_area.setPlaceholderText(t("input_placeholder"))
            if self._ui_task_state.first_startup_wait_hint_active:
                self.panel_window.update_status_hint(t("first_startup_wait_hint"))
        if self._ui_task_state.status_key == "ready":
            self._set_runtime_state("ready", t("agent_ready"))
        if self._console_window is not None:
            self._console_window._refresh_all_ui_text()

    def _current_wake_word_ack_text(self) -> str:
        locale = self._voice_locale_override()
        return translate(locale, "wake_word_ack_text")

    def _voice_locale_override(self) -> str:
        language = str(getattr(self, "_active_wake_word_language", "") or "").strip().lower()
        if language == "en":
            return "en_US"
        if language == "zh":
            return "zh_CN"
        return str(self._config.get("locale_config.locale", "zh_CN") or "zh_CN").strip()

    def _set_active_wake_word_language(self, language: str) -> None:
        normalized = str(language or "").strip().lower()
        self._active_wake_word_language = normalized if normalized in {"zh", "en"} else ""

    def _clear_active_wake_word_language(self) -> None:
        self._active_wake_word_language = ""

    def _dismiss_first_startup_wait_hint(self) -> None:
        self._task_session_controller.dismiss_first_startup_wait_hint()

    def _on_enter_transparent_mode(self, completed_event=None) -> None:
        try:
            for window in self._managed_windows():
                if hasattr(window, "enter_transparent_mode"):
                    window.enter_transparent_mode()
        finally:
            if completed_event is not None:
                completed_event.set()

    def _on_exit_transparent_mode(self, completed_event=None) -> None:
        try:
            for window in self._managed_windows():
                if hasattr(window, "exit_transparent_mode"):
                    window.exit_transparent_mode()
        finally:
            if completed_event is not None:
                completed_event.set()

    def shutdown(self) -> None:
        cancel_current_mouse_motion()
        taskbar_host = getattr(self, "_taskbar_host_window", None)
        if taskbar_host is not None:
            try:
                taskbar_host.allow_shutdown_close()
            except Exception:
                pass
        self._teardown_global_hotkey()
        self.hover_timer.stop()
        self.collapse_timer.stop()
        self._frontmost_timer.stop()
        self._job_poll_timer.stop()
        self._interaction_idle_timer.stop()
        if self._ui_perf_timer is not None:
            self._ui_perf_timer.stop()
        wake_word = getattr(self, "_wake_word", None)
        if wake_word is not None:
            wake_word.shutdown()
        self._voice.shutdown()
        self._tts.shutdown()
        try:
            self._companion.shutdown()
        except Exception:
            pass
        self._job_manager.shutdown()

        self._task_session_controller.shutdown_workers()

        if self._console_window is not None:
            self._console_window.close()
        if taskbar_host is not None:
            taskbar_host.close()
        self._background_jobs.shutdown()
        self._job_windows = self._background_jobs.job_windows
        self.panel_window.hide()
        self.edge_bar.hide()
        try:
            self.suggestion_window.hide()
        except Exception:
            pass
        try:
            self.toast_window.hide()
        except Exception:
            pass
        self.ball_window.hide()
        self.app.quit()

    def _on_suggestion_clicked(self, text: str) -> None:
        # Clicking a suggestion is equivalent to auto-submitting a normal task.
        task = str(text or "").strip()
        if not task:
            return
        if self._task_active() or self._is_waiting_for_tts():
            return
        self.is_pinned = True
        self.panel_window.pinned_active = True
        self.ball_window.update()
        self._handle_suggestion_submit(task)
