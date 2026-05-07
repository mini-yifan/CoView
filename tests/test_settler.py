import numpy as np

from baodou_ai.core.settler import ScreenSettler


class DummyConfig:
    def __init__(self, **overrides):
        self.execution_config = {
            "settle_min_wait_ms": 0,
            "settle_probe_interval_ms": 0,
            "settle_required_stable_probes": 2,
            "settle_max_wait_ms": 10,
            "settle_probe_width": 4,
            "settle_probe_height": 4,
            "settle_change_threshold": 0.01,
            **overrides,
        }


class FakeScreenshotCapture:
    def __init__(self, probes):
        self._probes = list(probes)
        self._index = 0

    def capture_screen_probes(self, screen_info=None, probe_width=160, probe_height=90):
        if self._index >= len(self._probes):
            current = self._probes[-1]
        else:
            current = self._probes[self._index]
        self._index += 1
        return True, [{"index": 0, "gray": current}]

    @staticmethod
    def calculate_image_difference(previous_gray, current_gray):
        diff = np.abs(previous_gray.astype(np.float32) - current_gray.astype(np.float32))
        return float(diff.mean() / 255.0)


def test_settler_returns_early_when_screen_stabilizes():
    screenshot = FakeScreenshotCapture([
        np.zeros((4, 4), dtype=np.uint8),
        np.zeros((4, 4), dtype=np.uint8),
        np.zeros((4, 4), dtype=np.uint8),
    ])
    settler = ScreenSettler(screenshot, DummyConfig())

    result = settler.wait_until_stable()

    assert result.stable is True
    assert result.probe_count == 3
    assert result.last_change_ratio == 0.0


def test_settler_waits_through_changes_before_stabilizing():
    screenshot = FakeScreenshotCapture([
        np.zeros((4, 4), dtype=np.uint8),
        np.full((4, 4), 255, dtype=np.uint8),
        np.zeros((4, 4), dtype=np.uint8),
        np.zeros((4, 4), dtype=np.uint8),
        np.zeros((4, 4), dtype=np.uint8),
    ])
    settler = ScreenSettler(screenshot, DummyConfig())

    result = settler.wait_until_stable()

    assert result.stable is True
    assert result.probe_count >= 5


def test_settler_times_out_when_screen_never_stabilizes():
    screenshot = FakeScreenshotCapture([
        np.zeros((4, 4), dtype=np.uint8),
        np.full((4, 4), 255, dtype=np.uint8),
    ])
    settler = ScreenSettler(
        screenshot,
        DummyConfig(settle_max_wait_ms=1, settle_probe_interval_ms=1),
    )

    result = settler.wait_until_stable()

    assert result.stable is False
    assert result.elapsed_ms >= 1


def test_settler_returns_early_when_should_stop():
    screenshot = FakeScreenshotCapture([
        np.zeros((4, 4), dtype=np.uint8),
        np.full((4, 4), 255, dtype=np.uint8),
    ])
    settler = ScreenSettler(
        screenshot,
        DummyConfig(settle_max_wait_ms=1000, settle_probe_interval_ms=100),
    )

    result = settler.wait_until_stable(should_stop=lambda: True)

    assert result.stable is False
    assert result.probe_count == 0
