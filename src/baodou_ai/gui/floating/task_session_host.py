"""Host boundary for floating task session orchestration."""

from __future__ import annotations

import platform
import threading
from typing import Any, Dict, Optional, Protocol

from baodou_ai.gui.main_window import AIWorker


class TaskSessionHost(Protocol):
    """Explicit services TaskSessionController needs from the floating UI."""

    def stop_tts(self) -> None:
        ...

    def speak(self, text: str) -> Optional[threading.Event]:
        ...

    def start_tts_waiting(self) -> None:
        ...

    def finish_tts_waiting(self) -> None:
        ...

    def set_tts_done_event(self, event: Optional[threading.Event]) -> None:
        ...

    def is_waiting_for_tts(self) -> bool:
        ...

    def hide_companion_suggestions(self) -> None:
        ...

    def close_console_for_task_start(self) -> None:
        ...

    def get_default_max_iterations(self) -> int:
        ...

    def get_config_value(self, key: str, default: Any = None) -> Any:
        ...

    def get_active_respond_language(self) -> str:
        ...

    def localize_tts_text(self, text: str) -> str:
        ...

    def snapshot_last_external_frontmost_app(self) -> Optional[Dict[str, Any]]:
        ...

    def activate_app(self, app_info: Dict[str, Any]) -> None:
        ...

    def show_running_state(self, text: str, *, focus_panel: bool, status_hint_text: str) -> None:
        ...

    def show_idle_state(self) -> None:
        ...

    def show_stopping_state(self) -> None:
        ...

    def show_finished_state(self, text: str, *, status_text: str, tts_playing: bool) -> None:
        ...

    def update_intermediate_report(self, payload: Dict[str, Any]) -> None:
        ...

    def update_status_hint(self, text: str) -> None:
        ...

    def enable_screenshot_protection(self) -> None:
        ...

    def disable_screenshot_protection(self) -> None:
        ...

    def append_log(self, text: str, level: str) -> None:
        ...

    def mark_voice_user_interaction(self) -> None:
        ...

    def show_history_if_idle(self) -> None:
        ...

    def sync_voice_interaction_state(self) -> None:
        ...

    def clear_voice_session_language(self) -> None:
        ...

    def announce_report(self, text: str) -> Optional[threading.Event]:
        ...

    def build_worker(
        self,
        text: str,
        *,
        initial_external_frontmost_app: Optional[Dict[str, Any]],
        history_context: str,
        respond_language_override: str = "",
    ) -> AIWorker:
        ...

    def enter_transparent_mode(self, completed_event=None) -> None:
        ...

    def exit_transparent_mode(self, completed_event=None) -> None:
        ...


class FloatingTaskSessionHost:
    """Adapter from FloatingController internals to TaskSessionHost."""

    def __init__(self, owner) -> None:
        self._owner = owner

    def _call_owner(self, method_name: str, *args, **kwargs):
        method = getattr(self._owner, method_name, None)
        if callable(method):
            return method(*args, **kwargs)
        raise AttributeError(method_name)

    def stop_tts(self) -> None:
        tts = getattr(self._owner, "_tts", None)
        if hasattr(tts, "stop"):
            tts.stop()

    def speak(self, text: str) -> Optional[threading.Event]:
        try:
            return self._call_owner("speak", text)
        except AttributeError:
            tts = getattr(self._owner, "_tts", None)
            return tts.speak(text) if hasattr(tts, "speak") else None

    def start_tts_waiting(self) -> None:
        try:
            self._call_owner("start_tts_waiting")
        except AttributeError:
            tts = getattr(self._owner, "_tts", None)
            if hasattr(tts, "start_waiting"):
                tts.start_waiting()

    def finish_tts_waiting(self) -> None:
        try:
            self._call_owner("finish_tts_waiting")
        except AttributeError:
            tts = getattr(self._owner, "_tts", None)
            if hasattr(tts, "finish_waiting"):
                tts.finish_waiting()

    def set_tts_done_event(self, event: Optional[threading.Event]) -> None:
        try:
            self._call_owner("set_tts_done_event", event)
        except AttributeError:
            tts = getattr(self._owner, "_tts", None)
            if tts is not None:
                tts.current_done_event = event

    def is_waiting_for_tts(self) -> bool:
        checker = getattr(self._owner, "is_waiting_for_tts", None)
        if callable(checker):
            return bool(checker())
        legacy = getattr(self._owner, "_is_waiting_for_tts", None)
        return bool(legacy()) if callable(legacy) else False

    def hide_companion_suggestions(self) -> None:
        hide = getattr(self._owner, "hide_suggestions", None)
        if callable(hide):
            hide()
            return
        companion = getattr(self._owner, "_companion", None)
        legacy = getattr(companion, "hide_suggestions", None)
        if callable(legacy):
            legacy()

    def close_console_for_task_start(self) -> None:
        closer = getattr(self._owner, "close_console_for_task_start", None)
        if callable(closer):
            closer()
            return
        if platform.system() != "Windows":
            return
        window = getattr(self._owner, "_console_window", None)
        if window is None:
            return
        close = getattr(window, "close", None)
        if callable(close):
            close()

    def get_default_max_iterations(self) -> int:
        getter = getattr(self._owner, "get_default_max_iterations", None)
        if callable(getter):
            return int(getter() or 80)
        config = getattr(self._owner, "_config", None)
        return int(config.execution_config.get("default_max_iterations", 80) or 80)

    def get_config_value(self, key: str, default: Any = None) -> Any:
        getter = getattr(self._owner, "get_config_value", None)
        if callable(getter):
            return getter(key, default)
        config = getattr(self._owner, "_config", None)
        return config.get(key, default) if config is not None else default

    def get_active_respond_language(self) -> str:
        getter = getattr(self._owner, "get_active_respond_language", None)
        if callable(getter):
            return str(getter() or "").strip()
        wake_language = str(getattr(self._owner, "_active_wake_word_language", "") or "").strip().lower()
        if wake_language == "en":
            return "English"
        if wake_language == "zh":
            return "Chinese (Simplified)"
        config = getattr(self._owner, "_config", None)
        if config is None:
            return ""
        return str(config.get_respond_language() or "").strip()

    def localize_tts_text(self, text: str) -> str:
        localizer = getattr(self._owner, "localize_tts_text", None)
        if callable(localizer):
            return str(localizer(text) or "").strip()
        return str(text or "").strip()

    def snapshot_last_external_frontmost_app(self) -> Optional[Dict[str, Any]]:
        getter = getattr(self._owner, "snapshot_last_external_frontmost_app", None)
        if callable(getter):
            return getter()
        tracker = getattr(self._owner, "_frontmost_tracker", None)
        return tracker.snapshot_last_external_frontmost_app() if tracker is not None else None

    def activate_app(self, app_info: Dict[str, Any]) -> None:
        activator = getattr(self._owner, "activate_app", None)
        if callable(activator):
            activator(app_info)
            return
        platform_adapter = getattr(self._owner, "_platform_adapter", None)
        if platform_adapter is not None:
            platform_adapter.activate_app(app_info)

    def show_running_state(self, text: str, *, focus_panel: bool, status_hint_text: str) -> None:
        owner_handler = getattr(self._owner, "show_running_state", None)
        if callable(owner_handler):
            owner_handler(
                text,
                focus_panel=focus_panel,
                status_hint_text=status_hint_text,
            )
            return
        panel_window = getattr(self._owner, "panel_window", None)
        anchor = getattr(self._owner, "ball_anchor", None)
        if panel_window is not None:
            panel_window.show_running_state(
                text,
                anchor=anchor,
                focus_input_on_finish=focus_panel,
                animate=focus_panel,
                status_hint_text=status_hint_text,
            )

    def show_idle_state(self) -> None:
        owner_handler = getattr(self._owner, "show_idle_state", None)
        if callable(owner_handler):
            owner_handler()
            return
        panel_window = getattr(self._owner, "panel_window", None)
        if panel_window is not None:
            panel_window.set_idle_state()

    def show_stopping_state(self) -> None:
        owner_handler = getattr(self._owner, "show_stopping_state", None)
        if callable(owner_handler):
            owner_handler()
            return
        panel_window = getattr(self._owner, "panel_window", None)
        if panel_window is not None:
            panel_window.show_stopping_state()

    def show_finished_state(self, text: str, *, status_text: str, tts_playing: bool) -> None:
        owner_handler = getattr(self._owner, "show_finished_state", None)
        if callable(owner_handler):
            owner_handler(
                text,
                status_text=status_text,
                tts_playing=tts_playing,
            )
            return
        panel_window = getattr(self._owner, "panel_window", None)
        if panel_window is not None:
            panel_window.show_finished_state(
                text,
                status_text=status_text,
                tts_playing=tts_playing,
            )

    def update_intermediate_report(self, payload: Dict[str, Any]) -> None:
        owner_handler = getattr(self._owner, "update_intermediate_report", None)
        if callable(owner_handler):
            owner_handler(payload)
            return
        panel_window = getattr(self._owner, "panel_window", None)
        if panel_window is not None:
            panel_window.update_intermediate_report(payload)

    def update_status_hint(self, text: str) -> None:
        owner_handler = getattr(self._owner, "update_status_hint", None)
        if callable(owner_handler):
            owner_handler(text)
            return
        panel_window = getattr(self._owner, "panel_window", None)
        if panel_window is not None:
            panel_window.update_status_hint(text)

    def enable_screenshot_protection(self) -> None:
        protector = getattr(self._owner, "enable_screenshot_protection", None)
        if callable(protector):
            protector()
            return
        legacy = getattr(self._owner, "_enable_screenshot_protection", None)
        if callable(legacy):
            legacy()

    def disable_screenshot_protection(self) -> None:
        protector = getattr(self._owner, "disable_screenshot_protection", None)
        if callable(protector):
            protector()
            return
        legacy = getattr(self._owner, "_disable_screenshot_protection", None)
        if callable(legacy):
            legacy()

    def append_log(self, text: str, level: str) -> None:
        logger = getattr(self._owner, "append_log", None)
        if callable(logger):
            logger(text, level)
            return
        log_buffer = getattr(self._owner, "_log_buffer", None)
        if log_buffer is not None:
            log_buffer.append_log(text, level)

    def mark_voice_user_interaction(self) -> None:
        marker = getattr(self._owner, "mark_voice_user_interaction", None)
        if callable(marker):
            marker()
            return
        legacy = getattr(self._owner, "_mark_voice_user_interaction", None)
        if callable(legacy):
            legacy()

    def show_history_if_idle(self) -> None:
        shower = getattr(self._owner, "show_history_if_idle", None)
        if callable(shower):
            shower()
            return
        legacy = getattr(self._owner, "_show_history_if_idle", None)
        if callable(legacy):
            legacy()

    def sync_voice_interaction_state(self) -> None:
        syncer = getattr(self._owner, "sync_voice_interaction_state", None)
        if callable(syncer):
            syncer()
            return
        legacy = getattr(self._owner, "_sync_voice_interaction_state", None)
        if callable(legacy):
            legacy()

    def clear_voice_session_language(self) -> None:
        clearer = getattr(self._owner, "clear_voice_session_language", None)
        if callable(clearer):
            clearer()
            return
        legacy = getattr(self._owner, "_clear_active_wake_word_language", None)
        if callable(legacy):
            legacy()
            return
        if hasattr(self._owner, "_active_wake_word_language"):
            self._owner._active_wake_word_language = ""

    def announce_report(self, text: str) -> Optional[threading.Event]:
        announcer = getattr(self._owner, "announce_report", None)
        if callable(announcer):
            return announcer(text)
        legacy = getattr(self._owner, "_on_report", None)
        return legacy(text) if callable(legacy) else None

    def build_worker(
        self,
        text: str,
        *,
        initial_external_frontmost_app: Optional[Dict[str, Any]],
        history_context: str,
        respond_language_override: str = "",
    ) -> AIWorker:
        builder = getattr(self._owner, "build_worker", None)
        if callable(builder):
            return builder(
                text,
                initial_external_frontmost_app=initial_external_frontmost_app,
                history_context=history_context,
                respond_language_override=respond_language_override,
            )
        config = getattr(self._owner, "_config", None)
        on_report = getattr(self._owner, "_on_report", None)
        job_manager = getattr(self._owner, "_job_manager", None)
        return AIWorker(
            text,
            config,
            initial_external_frontmost_app=initial_external_frontmost_app,
            history_context=history_context,
            on_report=on_report,
            job_manager=job_manager,
            respond_language_override=respond_language_override,
        )

    def enter_transparent_mode(self, completed_event=None) -> None:
        handler = getattr(self._owner, "enter_transparent_mode", None)
        if callable(handler):
            handler(completed_event)
            return
        legacy = getattr(self._owner, "_on_enter_transparent_mode", None)
        if callable(legacy):
            legacy(completed_event)

    def exit_transparent_mode(self, completed_event=None) -> None:
        handler = getattr(self._owner, "exit_transparent_mode", None)
        if callable(handler):
            handler(completed_event)
            return
        legacy = getattr(self._owner, "_on_exit_transparent_mode", None)
        if callable(legacy):
            legacy(completed_event)
