import subprocess
import sys
import plistlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from baodou_ai.platform.display_names import get_app_display_override
from baodou_ai.platform.macos import MacOSAdapter
from baodou_ai.platform.mouse_motion import MouseMotionCancelled


class NoopMotionCoordinator:
    def __init__(self):
        self.ended = []

    def begin_motion(self):
        return object()

    def check_active(self, token):
        return None

    def wait_active(self, token, timeout):
        return None

    def end_motion(self, token):
        self.ended.append(token)


class CancellingMotionCoordinator(NoopMotionCoordinator):
    def wait_active(self, token, timeout):
        raise MouseMotionCancelled("cancelled")


class FakeQuartz:
    kCGMouseButtonLeft = 0
    kCGMouseButtonRight = 1
    kCGEventMouseMoved = "moved"
    kCGEventLeftMouseDown = "left_down"
    kCGEventLeftMouseUp = "left_up"
    kCGEventLeftMouseDragged = "left_dragged"
    kCGEventRightMouseDown = "right_down"
    kCGEventRightMouseUp = "right_up"
    kCGEventRightMouseDragged = "right_dragged"
    kCGMouseEventClickState = "click_state"
    kCGHIDEventTap = "hid_tap"
    kCGScrollEventUnitLine = "line"

    def __init__(self):
        self.cursor = (10.0, 20.0)
        self.posted = []
        self.warped = []

    def CGEventCreate(self, _source):
        return object()

    def CGEventGetLocation(self, _event):
        return SimpleNamespace(x=self.cursor[0], y=self.cursor[1])

    def CGWarpMouseCursorPosition(self, point):
        normalized = (float(point[0]), float(point[1]))
        self.cursor = normalized
        self.warped.append(normalized)

    def CGEventCreateMouseEvent(self, _source, event_type, point, button):
        return {
            "type": event_type,
            "point": (float(point[0]), float(point[1])),
            "button": button,
            "fields": {},
        }

    def CGEventSetIntegerValueField(self, event, field, value):
        event["fields"][field] = value

    def CGEventCreateScrollWheelEvent(self, _source, _unit, _wheels, amount):
        return {
            "type": "scroll",
            "point": self.cursor,
            "button": None,
            "fields": {"amount": amount},
        }

    def CGEventPost(self, tap, event):
        self.posted.append(
            {
                "tap": tap,
                "type": event["type"],
                "point": event["point"],
                "button": event["button"],
                "fields": dict(event["fields"]),
            }
        )
        self.cursor = event["point"]


class UntrustedQuartz(FakeQuartz):
    kAXTrustedCheckOptionPrompt = "prompt"

    def __init__(self):
        super().__init__()
        self.prompts = []

    def AXIsProcessTrustedWithOptions(self, options):
        self.prompts.append(dict(options))
        return False


def test_macos_click_double_click_sets_click_state(monkeypatch):
    adapter = MacOSAdapter()
    fake_quartz = FakeQuartz()
    monkeypatch.setattr(adapter, "_get_quartz_module", lambda: fake_quartz)
    monkeypatch.setattr("baodou_ai.platform.macos.time.sleep", lambda _: None)

    adapter.click(button="left", clicks=2)

    assert [event["type"] for event in fake_quartz.posted] == [
        "left_down",
        "left_up",
        "left_down",
        "left_up",
    ]
    assert [event["fields"]["click_state"] for event in fake_quartz.posted] == [1, 1, 2, 2]


def test_macos_click_prompts_when_accessibility_is_not_trusted(monkeypatch):
    adapter = MacOSAdapter()
    fake_quartz = UntrustedQuartz()
    monkeypatch.setattr(adapter, "_get_quartz_module", lambda: fake_quartz)

    with pytest.raises(RuntimeError, match="辅助功能权限"):
        adapter.click(button="left")

    assert fake_quartz.prompts == [{"prompt": True}]
    assert fake_quartz.posted == []


def test_macos_drag_to_posts_dragged_events_and_release(monkeypatch):
    adapter = MacOSAdapter()
    fake_quartz = FakeQuartz()
    monkeypatch.setattr(adapter, "_get_quartz_module", lambda: fake_quartz)
    monkeypatch.setattr("baodou_ai.platform.macos.time.sleep", lambda _: None)

    adapter.drag_to(30, 40, duration=0.02, button="left")

    assert fake_quartz.posted[0]["type"] == "left_down"
    assert fake_quartz.posted[-1]["type"] == "left_up"
    assert any(event["type"] == "left_dragged" for event in fake_quartz.posted[1:-1])
    assert fake_quartz.warped[-1] == (30.0, 40.0)


def test_macos_move_cursor_uses_time_based_motion_without_backfilling(monkeypatch):
    adapter = MacOSAdapter()
    fake_quartz = FakeQuartz()
    coordinator = NoopMotionCoordinator()
    times = iter([100.0, 100.0, 100.7, 101.4])
    last_time = {"value": 101.4}

    def fake_monotonic():
        try:
            last_time["value"] = next(times)
        except StopIteration:
            pass
        return last_time["value"]

    monkeypatch.setattr(adapter, "_get_quartz_module", lambda: fake_quartz)
    monkeypatch.setattr(
        "baodou_ai.platform.macos.get_mouse_motion_coordinator", lambda: coordinator
    )
    monkeypatch.setattr("baodou_ai.platform.macos.time.monotonic", fake_monotonic)

    adapter.move_cursor(110, 120, duration=1.0)

    assert fake_quartz.warped[-1] == (110.0, 120.0)
    assert len(fake_quartz.posted) <= 3


def test_macos_move_cursor_raises_when_motion_is_cancelled(monkeypatch):
    adapter = MacOSAdapter()
    fake_quartz = FakeQuartz()
    coordinator = CancellingMotionCoordinator()

    monkeypatch.setattr(adapter, "_get_quartz_module", lambda: fake_quartz)
    monkeypatch.setattr(
        "baodou_ai.platform.macos.get_mouse_motion_coordinator", lambda: coordinator
    )
    monkeypatch.setattr("baodou_ai.platform.macos.time.monotonic", lambda: 100.0)

    try:
        adapter.move_cursor(110, 120, duration=1.0)
    except MouseMotionCancelled:
        pass
    else:
        raise AssertionError("expected MouseMotionCancelled")

    assert fake_quartz.warped[-1] != (110.0, 120.0)
    assert len(coordinator.ended) == 1


def test_macos_drag_to_releases_mouse_when_motion_is_cancelled(monkeypatch):
    adapter = MacOSAdapter()
    fake_quartz = FakeQuartz()
    coordinator = CancellingMotionCoordinator()

    monkeypatch.setattr(adapter, "_get_quartz_module", lambda: fake_quartz)
    monkeypatch.setattr(
        "baodou_ai.platform.macos.get_mouse_motion_coordinator", lambda: coordinator
    )
    monkeypatch.setattr("baodou_ai.platform.macos.time.monotonic", lambda: 100.0)

    with pytest.raises(MouseMotionCancelled):
        adapter.drag_to(110, 120, duration=1.0)

    assert fake_quartz.posted[0]["type"] == "left_down"
    assert fake_quartz.posted[-1]["type"] == "left_up"
    assert fake_quartz.posted[-1]["point"] == fake_quartz.cursor


def test_macos_scroll_posts_scroll_event(monkeypatch):
    adapter = MacOSAdapter()
    fake_quartz = FakeQuartz()
    monkeypatch.setattr(adapter, "_get_quartz_module", lambda: fake_quartz)

    adapter.scroll(12)

    assert fake_quartz.posted == [
        {
            "tap": "hid_tap",
            "type": "scroll",
            "point": (10.0, 20.0),
            "button": None,
            "fields": {"amount": 12},
        }
    ]


def test_get_capture_screens_info_prefers_qt_logical_geometry(monkeypatch):
    adapter = MacOSAdapter()
    monkeypatch.setattr(
        adapter,
        "_get_qt_screen_infos",
        lambda: [
            {"index": 0, "x": 0, "y": 0, "width": 1512, "height": 982, "is_primary": True},
            {"index": 1, "x": -1600, "y": -200, "width": 1200, "height": 900, "is_primary": False},
        ],
    )
    monkeypatch.setattr(
        adapter,
        "_get_sorted_nsscreen_metrics",
        lambda: [
            {"x": 999, "y": 888, "width": 1512, "height": 982, "scale": 2.0, "is_primary": True},
            {"x": 777, "y": 666, "width": 1200, "height": 900, "scale": 1.0, "is_primary": False},
        ],
    )

    screens = adapter.get_capture_screens_info()

    assert screens == [
        {
            "index": 0,
            "is_primary": True,
            "logical_x": 0,
            "logical_y": 0,
            "logical_width": 1512,
            "logical_height": 982,
            "capture_x": 0,
            "capture_y": 0,
            "capture_width": 3024,
            "capture_height": 1964,
        },
        {
            "index": 1,
            "is_primary": False,
            "logical_x": -1600,
            "logical_y": -200,
            "logical_width": 1200,
            "logical_height": 900,
            "capture_x": -1600,
            "capture_y": -200,
            "capture_width": 1200,
            "capture_height": 900,
        },
    ]


def test_get_all_screens_info_prefers_qt_logical_geometry(monkeypatch):
    adapter = MacOSAdapter()
    monkeypatch.setattr(
        adapter,
        "_get_qt_screen_infos",
        lambda: [
            {"index": 0, "x": 0, "y": 0, "width": 1512, "height": 982, "is_primary": True},
            {"index": 1, "x": -1600, "y": -200, "width": 1200, "height": 900, "is_primary": False},
        ],
    )

    screens = adapter.get_all_screens_info()

    assert screens[1]["x"] == -1600
    assert screens[1]["y"] == -200
    assert screens[1]["width"] == 1200
    assert screens[1]["height"] == 900


def test_macos_launch_app_accepts_excel_alias_and_uses_open_path(monkeypatch):
    adapter = MacOSAdapter()
    monkeypatch.setattr(
        adapter,
        "_list_available_apps",
        lambda: [
            {
                "name": "Microsoft Excel",
                "display_name": "Microsoft Excel",
                "bundle_id": "com.microsoft.Excel",
                "path": "/Applications/Microsoft Excel.app",
                "aliases": [],
            }
        ],
    )

    recorded = {}

    def fake_run(cmd, check):
        recorded["cmd"] = cmd
        recorded["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("baodou_ai.platform.macos.subprocess.run", fake_run)

    result = adapter.launch_app("Excel")

    assert result["matched"] is True
    assert result["app_name"] == "Microsoft Excel"
    assert recorded == {
        "cmd": ["open", "/Applications/Microsoft Excel.app"],
        "check": True,
    }


def test_macos_launch_app_bridges_localized_system_name(monkeypatch):
    adapter = MacOSAdapter()
    monkeypatch.setattr(
        adapter,
        "_list_available_apps",
        lambda: [
            {
                "name": "Notes",
                "display_name": "备忘录",
                "bundle_id": "com.apple.Notes",
                "path": "/System/Applications/Notes.app",
                "aliases": ["Notes", "备忘录"],
            }
        ],
    )

    recorded = {}

    def fake_run(cmd, check):
        recorded["cmd"] = cmd
        recorded["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("baodou_ai.platform.macos.subprocess.run", fake_run)

    result = adapter.launch_app("备忘录")

    assert result["matched"] is True
    assert result["app_name"] == "备忘录"
    assert recorded["cmd"] == ["open", "/System/Applications/Notes.app"]


def test_macos_launch_app_bridges_finder_name(monkeypatch):
    adapter = MacOSAdapter()
    monkeypatch.setattr(
        adapter,
        "_list_available_apps",
        lambda: [
            {
                "name": "Finder",
                "display_name": "访达",
                "bundle_id": "com.apple.finder",
                "path": "/System/Library/CoreServices/Finder.app",
                "aliases": ["Finder", "访达"],
            }
        ],
    )

    recorded = {}

    def fake_run(cmd, check):
        recorded["cmd"] = cmd
        recorded["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("baodou_ai.platform.macos.subprocess.run", fake_run)

    result = adapter.launch_app("访达")

    assert result["matched"] is True
    assert result["app_name"] == "访达"
    assert recorded["cmd"] == ["open", "/System/Library/CoreServices/Finder.app"]


def test_macos_launch_app_returns_app_launcher_fallback_when_unmatched(monkeypatch):
    adapter = MacOSAdapter()
    monkeypatch.setattr(adapter, "_list_available_apps", lambda: [])

    result = adapter.launch_app("陌生软件")

    assert result["matched"] is False
    assert result["fallback"] == {
        "type": "app_launcher_search",
        "app_name": "陌生软件",
    }
    assert "open_app_launcher" in result["error"]


def test_macos_open_in_browser_uses_launchservices_preferences_when_coreservices_returns_none(
    monkeypatch, tmp_path
):
    adapter = MacOSAdapter()
    launchservices_dir = tmp_path / "Library" / "Preferences" / "com.apple.LaunchServices"
    launchservices_dir.mkdir(parents=True)
    with (launchservices_dir / "com.apple.launchservices.secure.plist").open("wb") as handle:
        plistlib.dump(
            {
                "LSHandlers": [
                    {
                        "LSHandlerURLScheme": "https",
                        "LSHandlerRoleAll": "com.google.chrome",
                        "LSHandlerModificationDate": 123,
                    }
                ]
            },
            handle,
        )

    class FakeCoreServices:
        @staticmethod
        def LSCopyDefaultHandlerForURLScheme(_scheme):
            return None

    class FakeAppURL:
        @staticmethod
        def path():
            return "/Applications/Google Chrome.app"

    class FakeWorkspace:
        @staticmethod
        def sharedWorkspace():
            return FakeWorkspace()

        def URLForApplicationWithBundleIdentifier_(self, bundle_id):
            assert bundle_id == "com.google.chrome"
            return FakeAppURL()

    monkeypatch.setitem(sys.modules, "CoreServices", FakeCoreServices)
    monkeypatch.setitem(sys.modules, "AppKit", SimpleNamespace(NSWorkspace=FakeWorkspace))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    recorded = {}

    def fake_run(cmd, check):
        recorded["cmd"] = cmd
        recorded["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("baodou_ai.platform.macos.subprocess.run", fake_run)

    result = adapter.open_in_browser(query="今天天气")

    assert result["browser"]["identifier"] == "com.google.chrome"
    assert result["browser"]["app_name"] == "Google Chrome"
    assert result["browser"]["is_chrome_family"] is True
    assert (
        result["target_url"]
        == "https://www.google.com/search?q=%E4%BB%8A%E5%A4%A9%E5%A4%A9%E6%B0%94"
    )
    assert recorded["cmd"] == ["open", result["target_url"]]


def test_macos_open_in_browser_without_target_launches_default_browser(monkeypatch):
    adapter = MacOSAdapter.__new__(MacOSAdapter)
    recorded = {}

    monkeypatch.setattr(
        adapter,
        "get_default_browser_info",
        lambda: {"identifier": "com.google.chrome", "app_path": "/Applications/Google Chrome.app"},
    )

    def fake_run(cmd, check):
        recorded["cmd"] = cmd
        recorded["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("baodou_ai.platform.macos.subprocess.run", fake_run)

    result = adapter.open_in_browser()

    assert result["target_url"] == ""
    assert recorded == {"cmd": ["open", "-b", "com.google.chrome"], "check": True}


def test_macos_list_installed_app_names_uses_raw_scanned_names(monkeypatch):
    adapter = MacOSAdapter()
    monkeypatch.setattr(
        adapter,
        "_iter_macos_application_paths",
        lambda: [
            "/System/Applications/Notes.app",
            "/Applications/Lark.app",
            "/Applications/notes.app",
        ],
    )

    seen_flags = []

    def fake_get_app_metadata(app_path, apply_display_override=True):
        seen_flags.append(apply_display_override)
        if app_path.endswith("Notes.app"):
            return {
                "name": "Notes",
                "display_name": "Notes",
                "bundle_id": "com.apple.Notes",
                "path": app_path,
                "aliases": ["Notes"],
            }
        return {
            "name": "Lark",
            "display_name": "Lark",
            "bundle_id": "com.electron.lark",
            "path": app_path,
            "aliases": ["Lark"],
        }

    monkeypatch.setattr(adapter, "_get_app_metadata", fake_get_app_metadata)

    app_names = adapter.list_installed_app_names()

    assert app_names == ["Lark", "Notes"]
    assert seen_flags == [False, False, False]


def test_macos_open_app_launcher_falls_back_between_launchpad_commands(monkeypatch):
    adapter = MacOSAdapter()
    monkeypatch.setattr(adapter, "list_installed_app_names", lambda: ["Google Chrome", "Notes"])
    recorded = []

    def fake_run(cmd, check):
        recorded.append({"cmd": cmd, "check": check})
        if cmd == ["open", "-b", "com.apple.apps.launcher"]:
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("baodou_ai.platform.macos.subprocess.run", fake_run)

    result = adapter.open_app_launcher()

    assert result == {
        "app_names": ["Google Chrome", "Notes"],
    }
    assert recorded == [
        {
            "cmd": ["open", "-b", "com.apple.apps.launcher"],
            "check": True,
        },
        {
            "cmd": ["open", "-b", "com.apple.launchpad.launcher"],
            "check": True,
        },
    ]


def test_macos_open_in_finder_uses_osascript(monkeypatch):
    adapter = MacOSAdapter()
    recorded = {}

    def fake_run(cmd, check):
        recorded["cmd"] = cmd
        recorded["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("baodou_ai.platform.macos.subprocess.run", fake_run)
    monkeypatch.setattr("baodou_ai.platform.macos.Path.home", lambda: Path("/Users/test"))

    result = adapter.open_in_finder()

    assert result == {
        "target_path": "/Users/test/Desktop",
        "revealed_file": None,
    }
    assert recorded["cmd"][0:2] == ["osascript", "-e"]
    assert 'tell application "Finder"' in recorded["cmd"][2]
    assert 'open POSIX file "/Users/test/Desktop"' in recorded["cmd"][2]
    assert recorded["check"] is True


def test_macos_open_in_finder_with_directory_path(monkeypatch, tmp_path):
    adapter = MacOSAdapter()
    recorded = {}

    def fake_run(cmd, check):
        recorded["cmd"] = cmd
        recorded["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("baodou_ai.platform.macos.subprocess.run", fake_run)
    test_dir = tmp_path / "my_folder"
    test_dir.mkdir()

    result = adapter.open_in_finder(path=str(test_dir))

    assert result["target_path"] == str(test_dir)
    assert result["revealed_file"] is None
    assert "open POSIX file" in recorded["cmd"][2]
    assert str(test_dir) in recorded["cmd"][2]


def test_macos_open_in_finder_with_file_path_uses_reveal(monkeypatch, tmp_path):
    adapter = MacOSAdapter()
    recorded = {}

    def fake_run(cmd, check):
        recorded["cmd"] = cmd
        recorded["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("baodou_ai.platform.macos.subprocess.run", fake_run)
    test_file = tmp_path / "report.pdf"
    test_file.write_text("test")

    result = adapter.open_in_finder(path=str(test_file))

    assert result["target_path"] == str(tmp_path)
    assert result["revealed_file"] == str(test_file)
    assert "reveal POSIX file" in recorded["cmd"][2]
    assert str(test_file) in recorded["cmd"][2]


def test_macos_open_in_finder_returns_error_for_nonexistent_path(monkeypatch):
    adapter = MacOSAdapter()

    result = adapter.open_in_finder(path="/nonexistent/path/that/does/not/exist")

    assert result["target_path"] is None
    assert result["revealed_file"] is None
    assert "error" in result


def test_display_name_overrides_include_common_chinese_app_names():
    assert get_app_display_override("com.bot.pc.doubao")["display_name"] == "豆包"
    assert get_app_display_override("com.electron.lark")["display_name"] == "飞书"
    assert get_app_display_override("com.volcengine.corplink")["display_name"] == "飞连"
    assert get_app_display_override("com.apple.stocks")["display_name"] == "股市"
    assert get_app_display_override("com.apple.clock")["display_name"] == "时钟"
    assert get_app_display_override("com.apple.finder")["display_name"] == "访达"


def test_iter_macos_application_paths_recurses_into_system_apps(monkeypatch):
    adapter = MacOSAdapter()

    monkeypatch.setattr("baodou_ai.platform.macos.os.path.isdir", lambda path: True)

    walk_map = {
        "/Applications": [
            ("/Applications", ["Google Chrome.app", "Python 3.11"], []),
            ("/Applications/Python 3.11", ["IDLE.app"], []),
        ],
        "/Users/test/Applications": [],
        "/Applications/Utilities": [
            ("/Applications/Utilities", ["Terminal.app"], []),
        ],
        "/System/Applications": [
            ("/System/Applications", ["Notes.app", "Utilities"], []),
            ("/System/Applications/Utilities", ["Activity Monitor.app"], []),
        ],
        "/System/Applications/Utilities": [
            ("/System/Applications/Utilities", ["Activity Monitor.app"], []),
        ],
        "/System/Library/CoreServices": [
            ("/System/Library/CoreServices", ["Finder.app"], []),
        ],
    }

    monkeypatch.setattr(
        "baodou_ai.platform.macos.os.path.expanduser", lambda path: "/Users/test/Applications"
    )
    monkeypatch.setattr(
        "baodou_ai.platform.macos.os.walk", lambda root: iter(walk_map.get(root, []))
    )

    app_paths = adapter._iter_macos_application_paths()

    assert "/Applications/Google Chrome.app" in app_paths
    assert "/Applications/Python 3.11/IDLE.app" in app_paths
    assert "/Applications/Utilities/Terminal.app" in app_paths
    assert "/System/Applications/Notes.app" in app_paths
    assert "/System/Applications/Utilities/Activity Monitor.app" in app_paths
    assert "/System/Library/CoreServices/Finder.app" in app_paths


def test_macos_activate_app_only_activates_running_process(monkeypatch):
    adapter = MacOSAdapter()
    calls = {"pid": None, "activated": 0}

    class FakeRunningApp:
        def activateWithOptions_(self, option):
            calls["activated"] += 1
            return True

    class FakeNSRunningApplication:
        @staticmethod
        def runningApplicationWithProcessIdentifier_(pid):
            calls["pid"] = pid
            return FakeRunningApp()

    class FakeWorkspace:
        @staticmethod
        def sharedWorkspace():
            return SimpleNamespace(runningApplications=lambda: [])

    fake_appkit = SimpleNamespace(
        NSRunningApplication=FakeNSRunningApplication,
        NSWorkspace=FakeWorkspace,
    )
    monkeypatch.setitem(sys.modules, "AppKit", fake_appkit)

    assert (
        adapter.activate_app({"app_name": "微信", "bundle_id": "com.tencent.xinWeChat", "pid": 321})
        is True
    )
    assert calls["pid"] == 321
    assert calls["activated"] >= 1


def test_macos_activate_app_does_not_relaunch_closed_app(monkeypatch):
    adapter = MacOSAdapter()

    class FakeNSRunningApplication:
        @staticmethod
        def runningApplicationWithProcessIdentifier_(_pid):
            return None

    class FakeWorkspace:
        @staticmethod
        def sharedWorkspace():
            return SimpleNamespace(runningApplications=lambda: [])

    fake_appkit = SimpleNamespace(
        NSRunningApplication=FakeNSRunningApplication,
        NSWorkspace=FakeWorkspace,
    )
    monkeypatch.setitem(sys.modules, "AppKit", fake_appkit)

    assert (
        adapter.activate_app({"app_name": "微信", "bundle_id": "com.tencent.xinWeChat", "pid": 321})
        is False
    )


def test_macos_activate_app_does_not_unhide_hidden_app(monkeypatch):
    adapter = MacOSAdapter()
    calls = {"activated": 0}

    class FakeRunningApp:
        def isHidden(self):
            return True

        def activateWithOptions_(self, option):
            calls["activated"] += 1
            return True

    class FakeNSRunningApplication:
        @staticmethod
        def runningApplicationWithProcessIdentifier_(_pid):
            return FakeRunningApp()

    class FakeWorkspace:
        @staticmethod
        def sharedWorkspace():
            return SimpleNamespace(runningApplications=lambda: [])

    fake_appkit = SimpleNamespace(
        NSRunningApplication=FakeNSRunningApplication,
        NSWorkspace=FakeWorkspace,
    )
    monkeypatch.setitem(sys.modules, "AppKit", fake_appkit)

    assert (
        adapter.activate_app({"app_name": "微信", "bundle_id": "com.tencent.xinWeChat", "pid": 321})
        is False
    )
    assert calls["activated"] == 0
