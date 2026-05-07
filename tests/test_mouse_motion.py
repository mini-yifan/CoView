import pytest

from baodou_ai.api import CoViewAI
from baodou_ai.gui.main_window import AIWorker
from baodou_ai.platform.mouse_motion import (
    MouseMotionCancelled,
    MouseMotionCoordinator,
    get_mouse_motion_coordinator,
)


def test_mouse_motion_coordinator_new_motion_cancels_previous():
    coordinator = MouseMotionCoordinator()
    old_token = coordinator.begin_motion()
    new_token = coordinator.begin_motion()

    with pytest.raises(MouseMotionCancelled):
        coordinator.check_active(old_token)
    coordinator.check_active(new_token)


def test_mouse_motion_coordinator_cancel_current_invalidates_active_token():
    coordinator = MouseMotionCoordinator()
    token = coordinator.begin_motion()

    coordinator.cancel_current()

    with pytest.raises(MouseMotionCancelled):
        coordinator.check_active(token)


def test_global_mouse_motion_coordinator_is_shared():
    assert get_mouse_motion_coordinator() is get_mouse_motion_coordinator()


def test_ai_worker_stop_cancels_mouse_motion(monkeypatch):
    calls = []
    monkeypatch.setattr("baodou_ai.gui.main_window.cancel_current_mouse_motion", lambda: calls.append("cancel"))

    worker = AIWorker("task", config=object())
    worker.stop()

    assert calls == ["cancel"]


def test_api_stop_cancels_mouse_motion(monkeypatch):
    calls = []
    monkeypatch.setattr("baodou_ai.api.cancel_current_mouse_motion", lambda: calls.append("cancel"))

    ai = CoViewAI(config=object())
    ai.stop()

    assert calls == ["cancel"]
