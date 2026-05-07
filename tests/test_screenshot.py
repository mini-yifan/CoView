import cv2
import numpy as np

from baodou_ai.core.config import Config
from baodou_ai.core.screenshot import CaptureTarget
from baodou_ai.core.screenshot import ScreenCaptureBundle, ScreenshotCapture


def make_bundle(index=0):
    return ScreenCaptureBundle(
        index=index,
        x=0,
        y=0,
        width=320,
        height=240,
        logical_width=320,
        logical_height=240,
        is_primary=(index == 0),
        png_bytes=b"png",
        data_url="data:image/png;base64,AAA",
        frame_hash=f"frame-{index}",
        path=None,
    )


def test_capture_all_screens_bundle_prefers_mss_backend(monkeypatch):
    capture = ScreenshotCapture(Config())
    targets = [{
        "index": 0,
        "is_primary": True,
        "logical_x": 0,
        "logical_y": 0,
        "logical_width": 320,
        "logical_height": 240,
        "capture_x": 0,
        "capture_y": 0,
        "capture_width": 320,
        "capture_height": 240,
    }]

    monkeypatch.setattr(capture._platform_adapter, "get_capture_screens_info", lambda: targets)
    monkeypatch.setattr(capture._platform_adapter, "get_scaling_factor", lambda: 1.0)
    monkeypatch.setattr(
        capture,
        "_get_capture_targets",
        lambda: (_ for _ in ()).throw(AssertionError("legacy Qt capture path should not be used")),
    )
    monkeypatch.setattr(
        capture,
        "_capture_targets_with_mss",
        lambda targets, save_dir, optimize, save_debug: [make_bundle(0)],
    )

    success, bundles = capture.capture_all_screens_bundle(save_debug=False)

    assert success is True
    assert len(bundles) == 1
    assert bundles[0].index == 0
    assert bundles[0].width == 320
    assert bundles[0].height == 240


def test_capture_all_screens_bundle_falls_back_when_mss_fails(monkeypatch):
    capture = ScreenshotCapture(Config())
    targets = [{
        "index": 0,
        "is_primary": True,
        "logical_x": 0,
        "logical_y": 0,
        "logical_width": 320,
        "logical_height": 240,
        "capture_x": 0,
        "capture_y": 0,
        "capture_width": 320,
        "capture_height": 240,
    }]

    monkeypatch.setattr(capture._platform_adapter, "get_capture_screens_info", lambda: targets)
    monkeypatch.setattr(capture._platform_adapter, "get_scaling_factor", lambda: 1.0)
    monkeypatch.setattr(
        capture,
        "_capture_targets_with_mss",
        lambda targets, save_dir, optimize, save_debug: (_ for _ in ()).throw(RuntimeError("mss failed")),
    )
    monkeypatch.setattr(
        capture,
        "_capture_targets_with_pyautogui",
        lambda targets, save_dir, optimize, save_debug: [make_bundle(0)],
    )

    success, bundles = capture.capture_all_screens_bundle(save_debug=False)

    assert success is True
    assert [bundle.index for bundle in bundles] == [0]


def test_capture_screen_probes_share_backend_selection(monkeypatch):
    capture = ScreenshotCapture(Config())
    targets = [{
        "index": 0,
        "is_primary": True,
        "logical_x": 0,
        "logical_y": 0,
        "logical_width": 320,
        "logical_height": 240,
        "capture_x": 0,
        "capture_y": 0,
        "capture_width": 320,
        "capture_height": 240,
    }]

    monkeypatch.setattr(capture._platform_adapter, "get_capture_screens_info", lambda: targets)
    monkeypatch.setattr(
        capture,
        "_capture_probes_with_mss",
        lambda targets, probe_width, probe_height: [{
            "index": 0,
            "gray": "probe",
            "width": 320,
            "height": 240,
        }],
    )

    success, probes = capture.capture_screen_probes()

    assert success is True
    assert probes[0]["index"] == 0
    assert probes[0]["gray"] == "probe"


def test_mss_capture_grabs_each_physical_monitor_without_virtual_desktop_crop(monkeypatch):
    class FakeMSSContext:
        monitors = [
            {"left": -100, "top": 0, "width": 300, "height": 100},
            {"left": -100, "top": 0, "width": 100, "height": 50},
            {"left": 0, "top": 0, "width": 200, "height": 100},
        ]

        def __init__(self, owner):
            self.owner = owner

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def grab(self, region):
            self.owner.grabs.append(dict(region))
            value = 80 if region["left"] == 0 else 160
            return np.full((region["height"], region["width"], 4), value, dtype=np.uint8)

    class FakeMSSModule:
        def __init__(self):
            self.grabs = []

        def mss(self):
            return FakeMSSContext(self)

    capture = ScreenshotCapture(Config())
    fake_mss = FakeMSSModule()
    monkeypatch.setattr("baodou_ai.core.screenshot.platform.system", lambda: "Darwin")
    monkeypatch.setattr(capture, "_load_mss_module", lambda: fake_mss)
    monkeypatch.setattr("baodou_ai.core.screenshot.pyautogui.position", lambda: (0, 0))
    targets = [
        CaptureTarget(
            index=0,
            is_primary=True,
            logical_x=0,
            logical_y=0,
            logical_width=100,
            logical_height=50,
            capture_x=0,
            capture_y=0,
            capture_width=200,
            capture_height=100,
        ),
        CaptureTarget(
            index=1,
            is_primary=False,
            logical_x=-100,
            logical_y=0,
            logical_width=100,
            logical_height=50,
            capture_x=-200,
            capture_y=0,
            capture_width=200,
            capture_height=100,
        ),
    ]

    bundles = capture._capture_targets_with_mss(
        targets=targets,
        save_dir=".",
        optimize=True,
        save_debug=False,
    )

    assert fake_mss.grabs == [
        {"left": 0, "top": 0, "width": 200, "height": 100},
        {"left": -100, "top": 0, "width": 100, "height": 50},
    ]
    assert [bundle.index for bundle in bundles] == [0, 1]
    decoded = [
        cv2.imdecode(np.frombuffer(bundle.png_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        for bundle in bundles
    ]
    assert int(decoded[0].mean()) == 80
    assert int(decoded[1].mean()) == 160


def test_mss_capture_uses_target_capture_rects_on_non_macos(monkeypatch):
    capture = ScreenshotCapture(Config())
    targets = [
        CaptureTarget(
            index=0,
            is_primary=True,
            logical_x=0,
            logical_y=0,
            logical_width=100,
            logical_height=50,
            capture_x=10,
            capture_y=20,
            capture_width=200,
            capture_height=100,
        ),
        CaptureTarget(
            index=1,
            is_primary=False,
            logical_x=100,
            logical_y=-50,
            logical_width=100,
            logical_height=50,
            capture_x=300,
            capture_y=-100,
            capture_width=150,
            capture_height=75,
        ),
    ]

    monkeypatch.setattr("baodou_ai.core.screenshot.platform.system", lambda: "Windows")
    monitors = capture._get_mss_monitors_for_targets(object(), targets)

    assert monitors == [
        {"left": 10, "top": 20, "width": 200, "height": 100},
        {"left": 300, "top": -100, "width": 150, "height": 75},
    ]


def test_capture_window_region_returns_error_envelope_when_capture_fails(monkeypatch):
    capture = ScreenshotCapture(Config())
    monkeypatch.setattr(capture, "_load_mss_module", lambda: None)
    monkeypatch.setattr(capture, "_capture_region_bgr", lambda x, y, w, h: (_ for _ in ()).throw(RuntimeError("snap failed")))

    result = capture.capture_window_region(
        bounds={"x": 0, "y": 0, "width": 300, "height": 200},
        include_data_url=False,
    )

    assert result["ok"] is False
    assert "snap failed" in str(result["error"])
    envelope = result.get("error_envelope")
    assert isinstance(envelope, dict)
    assert envelope["source"] == "capture"
    assert envelope["code"] == "CAPTURE_FAILED"
