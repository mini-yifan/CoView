from PyQt5.QtCore import Qt

from baodou_ai.gui.control_console import ControlConsoleWindow
from baodou_ai.gui.floating.windows_native import (
    GWL_EXSTYLE,
    SWP_FRAMECHANGED,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_NOZORDER,
    WS_EX_TOOLWINDOW,
    WS_EX_TRANSPARENT,
    WindowsOverlayHelper,
)
from baodou_ai.platform import windows as windows_platform
from baodou_ai.platform.windows import WindowsAdapter


class _FakePyAutoGui:
    def __init__(self):
        self.calls = []

    def press(self, key):
        self.calls.append(("press", key))


class _FakeWinId:
    def __init__(self, value):
        self._value = value

    def __int__(self):
        return self._value


class _FakeWindow:
    def __init__(self, hwnd=1001, width=180, height=120, opacity=0.9):
        self._hwnd = hwnd
        self._width = width
        self._height = height
        self._opacity = opacity
        self.attributes = {}

    def winId(self):
        return _FakeWinId(self._hwnd)

    def width(self):
        return self._width

    def height(self):
        return self._height

    def windowOpacity(self):
        return self._opacity

    def setWindowOpacity(self, opacity):
        self._opacity = opacity

    def setAttribute(self, attr, value):
        self.attributes[attr] = value


class _FakeUser32:
    def __init__(self):
        self.styles = {}
        self.pos_calls = []

    def GetWindowLongW(self, hwnd, _index):
        return self.styles.get(hwnd, 0)

    def SetWindowLongW(self, hwnd, _index, style):
        self.styles[hwnd] = style
        return style

    def SetWindowPos(self, hwnd, insert_after, x, y, cx, cy, flags):
        self.pos_calls.append((hwnd, insert_after, x, y, cx, cy, flags))
        return True


class _FakeGdi32:
    def __init__(self):
        self.ellipse_calls = []
        self.round_rect_calls = []

    def CreateEllipticRgn(self, left, top, right, bottom):
        self.ellipse_calls.append((left, top, right, bottom))
        return 11

    def CreateRoundRectRgn(self, left, top, right, bottom, width, height):
        self.round_rect_calls.append((left, top, right, bottom, width, height))
        return 22


class _FakeForegroundUser32:
    def __init__(self, hwnd=2001, pid=9527, title="README.md - Visual Studio Code"):
        self._hwnd = hwnd
        self._pid = pid
        self._title = title

    def GetForegroundWindow(self):
        return self._hwnd

    def GetWindowThreadProcessId(self, _hwnd, pid_pointer):
        pid_pointer._obj.value = self._pid
        return 1

    def GetWindowTextW(self, _hwnd, title_buffer, _buffer_size):
        title_buffer.value = self._title
        return len(self._title)


class _FakeActivateUser32:
    def __init__(self):
        self.show_calls = []
        self.attach_calls = []
        self.foreground_hwnd = 300
        self.thread_by_hwnd = {300: 30, 500: 50}

    def GetForegroundWindow(self):
        return self.foreground_hwnd

    def GetWindowThreadProcessId(self, hwnd, pid_pointer):
        if pid_pointer is not None:
            pid_pointer._obj.value = 9527
        return self.thread_by_hwnd.get(int(hwnd), 0)

    def IsWindowVisible(self, _hwnd):
        return True

    def GetWindow(self, _hwnd, _flag):
        return 0

    def IsIconic(self, _hwnd):
        return False

    def ShowWindow(self, hwnd, command):
        self.show_calls.append((int(hwnd), int(command)))
        return True

    def BringWindowToTop(self, _hwnd):
        return True

    def SetForegroundWindow(self, hwnd):
        self.foreground_hwnd = int(hwnd)
        return True

    def AttachThreadInput(self, source_thread, target_thread, attach):
        self.attach_calls.append((int(source_thread), int(target_thread), bool(attach)))
        return True


class _FakeKernel32ForActivate:
    def __init__(self, current_thread_id=10):
        self.current_thread_id = current_thread_id

    def GetCurrentThreadId(self):
        return self.current_thread_id


class _FakeShell32:
    def __init__(self, result=0, aborted=False):
        self.result = result
        self.aborted = aborted
        self.calls = []

    def SHFileOperationW(self, file_op_pointer):
        file_op = file_op_pointer._obj
        self.calls.append(
            {
                "wFunc": int(file_op.wFunc),
                "pFrom": file_op.pFrom,
                "fFlags": int(file_op.fFlags),
            }
        )
        file_op.fAnyOperationsAborted = bool(self.aborted)
        return self.result


def test_windows_overlay_helper_applies_overlay_toolwindow_style():
    user32 = _FakeUser32()
    gdi32 = _FakeGdi32()
    helper = WindowsOverlayHelper(user32, gdi32)
    window = _FakeWindow(width=164, height=164, opacity=0.9)

    helper.ensure_overlay_window(window, opacity=0.75)

    hwnd = int(window.winId())
    assert user32.styles[hwnd] & WS_EX_TOOLWINDOW
    assert helper.restore_opacity(window) == 0.75
    assert user32.pos_calls[-1][-1] == SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
    assert helper.apply_ellipse_region(window) is False
    assert helper.apply_round_rect_region(window, radius=18) is False


def test_windows_adapter_overlay_methods_refresh_and_toggle_transparent_mode():
    user32 = _FakeUser32()
    gdi32 = _FakeGdi32()
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    adapter._user32 = user32
    adapter._gdi32 = gdi32
    adapter._overlay_native = WindowsOverlayHelper(user32, gdi32)
    adapter._is_transparent_mode = False
    adapter._original_opacity = 0.9
    adapter._app_catalog_cache = None

    window = _FakeWindow(opacity=0.85)

    adapter.prepare_overlay_window(window)
    assert adapter.apply_overlay_region(window, "round_rect", 24) is False
    assert adapter.enter_transparent_mode(window) is True
    assert adapter.exit_transparent_mode(window) is True

    hwnd = int(window.winId())
    assert user32.styles[hwnd] & WS_EX_TOOLWINDOW
    assert not (user32.styles[hwnd] & WS_EX_TRANSPARENT)
    assert window.attributes[Qt.WA_TransparentForMouseEvents] is False
    assert window.windowOpacity() == 0.85


def test_windows_adapter_setup_window_does_not_apply_overlay_style():
    user32 = _FakeUser32()
    gdi32 = _FakeGdi32()
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    adapter._user32 = user32
    adapter._gdi32 = gdi32
    adapter._overlay_native = WindowsOverlayHelper(user32, gdi32)
    adapter._is_transparent_mode = False
    adapter._original_opacity = 0.9
    adapter._app_catalog_cache = None

    window = _FakeWindow(opacity=0.85)
    adapter.setup_window(window)

    hwnd = int(window.winId())
    assert hwnd not in user32.styles
    assert adapter._overlay_native.restore_opacity(window) == 0.85


def test_control_console_window_uses_normal_window_behavior_on_windows(monkeypatch):
    monkeypatch.setattr("baodou_ai.gui.control_console.platform.system", lambda: "Windows")

    assert ControlConsoleWindow._use_topmost_window() is False
    assert ControlConsoleWindow._hide_instead_of_close() is False


def test_control_console_window_keeps_previous_window_behavior_on_macos(monkeypatch):
    monkeypatch.setattr("baodou_ai.gui.control_console.platform.system", lambda: "Darwin")

    assert ControlConsoleWindow._use_topmost_window() is True
    assert ControlConsoleWindow._hide_instead_of_close() is True


def test_windows_open_app_launcher_presses_win_and_returns_empty_names(monkeypatch):
    fake_pyautogui = _FakePyAutoGui()
    monkeypatch.setattr("baodou_ai.platform.windows.pyautogui", fake_pyautogui)

    adapter = WindowsAdapter.__new__(WindowsAdapter)

    result = adapter.open_app_launcher()

    assert result == {"app_names": []}
    assert fake_pyautogui.calls == [("press", "win")]


def test_windows_adapter_resolves_known_executable_display_name():
    assert WindowsAdapter._resolve_windows_app_display_name("explorer.exe") == "File Explorer"
    assert WindowsAdapter._resolve_windows_app_display_name("WINWORD.EXE") == "Microsoft Word"
    assert WindowsAdapter._resolve_windows_app_display_name("code.exe") == "Visual Studio Code"
    assert WindowsAdapter._resolve_windows_app_display_name("kwps.exe") == "WPS"
    assert WindowsAdapter._resolve_windows_app_display_name("unknown_tool.exe") == "unknown_tool"


def test_windows_capture_screens_info_uses_display_settings_for_capture_rects(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    monkeypatch.setattr(
        adapter,
        "get_all_screens_info",
        lambda: [
            {
                "index": 0,
                "device_name": r"\\.\DISPLAY1",
                "x": 0,
                "y": 0,
                "width": 2880,
                "height": 1800,
                "is_primary": True,
            },
            {
                "index": 1,
                "device_name": r"\\.\DISPLAY2",
                "x": 1890,
                "y": -2160,
                "width": 3840,
                "height": 2160,
                "is_primary": False,
            },
        ],
    )
    monkeypatch.setattr(
        adapter,
        "_get_current_display_settings",
        lambda: {
            r"\\.\DISPLAY1": {"x": 0, "y": 0, "width": 2880, "height": 1800},
            r"\\.\DISPLAY2": {"x": 945, "y": -1080, "width": 1920, "height": 1080},
        },
    )

    screens = adapter.get_capture_screens_info()

    assert screens[1]["logical_x"] == 1890
    assert screens[1]["logical_y"] == -2160
    assert screens[1]["logical_width"] == 3840
    assert screens[1]["logical_height"] == 2160
    assert screens[1]["capture_x"] == 945
    assert screens[1]["capture_y"] == -1080
    assert screens[1]["capture_width"] == 1920
    assert screens[1]["capture_height"] == 1080


def test_windows_get_frontmost_app_info_prefers_process_executable(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    adapter._user32 = _FakeForegroundUser32(pid=4242, title="main.py - Visual Studio Code")
    monkeypatch.setattr(
        adapter,
        "_get_process_image_path",
        lambda pid: r"C:\Users\tester\AppData\Local\Programs\Microsoft VS Code\Code.exe" if pid == 4242 else "",
    )

    result = adapter.get_frontmost_app_info()

    assert result == {
        "app_name": "Visual Studio Code",
        "bundle_id": "",
        "identifier": r"C:\Users\tester\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        "pid": 4242,
        "title": "main.py - Visual Studio Code",
        "app_path": r"C:\Users\tester\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        "executable_name": "Code.exe",
    }


def test_windows_get_active_document_path_returns_none_for_unsupported_app():
    adapter = WindowsAdapter.__new__(WindowsAdapter)

    assert adapter.get_active_document_path("Notepad") is None


def test_windows_run_powershell_hides_subprocess_window(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    calls = []

    class Completed:
        returncode = 0
        stdout = "ok\n"

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(windows_platform.subprocess, "run", fake_run)

    result = adapter._run_powershell("Write-Output ok")

    assert result == "ok"
    assert calls[0][0][0] == "powershell"
    assert calls[0][1]["creationflags"] == windows_platform.subprocess.CREATE_NO_WINDOW
    assert calls[0][1]["startupinfo"].dwFlags & windows_platform.subprocess.STARTF_USESHOWWINDOW
    assert calls[0][1]["startupinfo"].wShowWindow == windows_platform.subprocess.SW_HIDE


def test_windows_get_active_document_path_resolves_explorer_folder_via_powershell(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    scripts = []
    monkeypatch.setattr(adapter, "_get_foreground_window_handle", lambda: 4096)
    monkeypatch.setattr(adapter, "_run_powershell", lambda script, timeout=2.5: scripts.append((script, timeout)) or r"C:\Users\tester\Documents")

    result = adapter.get_active_document_path("File Explorer")

    assert result == r"C:\Users\tester\Documents"
    assert "Shell.Application" in scripts[0][0]
    assert "4096" in scripts[0][0]


def test_windows_get_active_document_path_returns_empty_string_for_unsaved_explorer_location(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    monkeypatch.setattr(adapter, "_get_foreground_window_handle", lambda: 2048)
    monkeypatch.setattr(adapter, "_run_powershell", lambda script, timeout=2.5: "")

    assert adapter.get_active_document_path("Explorer") == ""


def test_windows_get_active_document_path_resolves_word_document_via_powershell(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    scripts = []
    monkeypatch.setattr(adapter, "_run_powershell", lambda script, timeout=2.5: scripts.append(script) or r"C:\docs\report.docx")

    result = adapter.get_active_document_path("Microsoft Word")

    assert result == r"C:\docs\report.docx"
    assert "Word.Application" in scripts[0]
    assert "ActiveDocument" in scripts[0]


def test_windows_get_active_document_path_resolves_excel_workbook_via_powershell(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    scripts = []
    monkeypatch.setattr(adapter, "_run_powershell", lambda script, timeout=2.5: scripts.append(script) or r"C:\docs\budget.xlsx")

    result = adapter.get_active_document_path("Microsoft Excel")

    assert result == r"C:\docs\budget.xlsx"
    assert "Excel.Application" in scripts[0]
    assert "ActiveWorkbook" in scripts[0]


def test_windows_get_active_document_path_resolves_powerpoint_presentation_via_powershell(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    scripts = []
    monkeypatch.setattr(adapter, "_run_powershell", lambda script, timeout=2.5: scripts.append(script) or r"C:\docs\deck.pptx")

    result = adapter.get_active_document_path("Microsoft PowerPoint")

    assert result == r"C:\docs\deck.pptx"
    assert "PowerPoint.Application" in scripts[0]
    assert "ActivePresentation" in scripts[0]


def test_windows_get_active_document_path_resolves_wps_document_via_powershell(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    scripts = []
    monkeypatch.setattr(adapter, "_run_powershell", lambda script, timeout=2.5: scripts.append(script) or r"C:\docs\wps.docx")

    result = adapter.get_active_document_path("WPS")

    assert result == r"C:\docs\wps.docx"
    assert "KWPS.Application" in scripts[0]
    assert "KET.Application" in scripts[0]
    assert "KWPP.Application" in scripts[0]


def test_windows_get_active_document_path_returns_empty_string_when_office_document_unsaved(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    monkeypatch.setattr(adapter, "_run_powershell", lambda script, timeout=2.5: "")

    assert adapter.get_active_document_path("Microsoft Word") == ""


def test_windows_find_running_app_info_matches_process_by_exact_path(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    monkeypatch.setattr(adapter, "_enumerate_top_level_windows", lambda: [500])
    monkeypatch.setattr(adapter, "_is_candidate_main_window", lambda hwnd: True)
    monkeypatch.setattr(adapter, "_get_window_pid", lambda hwnd: 9527)
    monkeypatch.setattr(
        adapter,
        "_get_process_image_path",
        lambda pid: r"C:\Program Files\Tencent\QQ\QQ.exe" if pid == 9527 else "",
    )

    result = adapter._find_running_app_info("QQ", r"C:\Program Files\Tencent\QQ\QQ.exe")

    assert result == {
        "app_name": "qq",
        "bundle_id": "",
        "identifier": r"C:\Program Files\Tencent\QQ\QQ.exe",
        "pid": 9527,
        "hwnd": 500,
        "app_path": r"C:\Program Files\Tencent\QQ\QQ.exe",
        "executable_name": "QQ.exe",
    }


def test_windows_launch_app_prefers_activate_existing_instance(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    monkeypatch.setattr(
        adapter,
        "_find_app_match",
        lambda app_name: {"matched": True, "app_name": "QQ", "app_path": r"C:\Program Files\Tencent\QQ\QQ.exe", "suggestions": [], "error": ""},
    )
    monkeypatch.setattr(
        adapter,
        "_find_running_app_info",
        lambda app_name, app_path="": {"app_name": "qq", "bundle_id": "", "identifier": app_path, "pid": 9527, "hwnd": 500},
    )
    activate_calls = []
    monkeypatch.setattr(adapter, "activate_app", lambda app_info: activate_calls.append(dict(app_info)) or True)
    startfile_calls = []
    monkeypatch.setattr("baodou_ai.platform.windows.os.startfile", lambda path: startfile_calls.append(path))

    result = adapter.launch_app("QQ")

    assert result["matched"] is True
    assert activate_calls == [{"app_name": "qq", "bundle_id": "", "identifier": r"C:\Program Files\Tencent\QQ\QQ.exe", "pid": 9527, "hwnd": 500}]
    assert startfile_calls == []


def test_windows_launch_app_falls_back_to_startfile_when_activation_fails(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    monkeypatch.setattr(
        adapter,
        "_find_app_match",
        lambda app_name: {"matched": True, "app_name": "QQ", "app_path": r"C:\Program Files\Tencent\QQ\QQ.exe", "suggestions": [], "error": ""},
    )
    monkeypatch.setattr(
        adapter,
        "_find_running_app_info",
        lambda app_name, app_path="": {"app_name": "qq", "bundle_id": "", "identifier": app_path, "pid": 9527, "hwnd": 500},
    )
    monkeypatch.setattr(adapter, "activate_app", lambda app_info: False)
    startfile_calls = []
    monkeypatch.setattr("baodou_ai.platform.windows.os.startfile", lambda path: startfile_calls.append(path))

    result = adapter.launch_app("QQ")

    assert result["matched"] is True
    assert startfile_calls == [r"C:\Program Files\Tencent\QQ\QQ.exe"]


def test_windows_open_in_finder_hides_explorer_fallback_for_file(tmp_path, monkeypatch):
    target = tmp_path / "sample.txt"
    target.write_text("data", encoding="utf-8")
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    calls = []

    monkeypatch.setattr(
        windows_platform.subprocess,
        "Popen",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    result = adapter.open_in_finder(str(target))

    assert result["revealed_file"] == str(target.resolve())
    assert calls[0][0] == ["explorer.exe", "/select,", str(target.resolve())]
    assert calls[0][1]["creationflags"] == windows_platform.subprocess.CREATE_NO_WINDOW


def test_windows_open_in_browser_hides_cmd_start_fallback(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    calls = []

    monkeypatch.setattr(adapter, "get_default_browser_info", lambda: {"is_chrome_family": True})
    monkeypatch.delattr(windows_platform.os, "startfile", raising=False)
    monkeypatch.setattr(
        windows_platform.subprocess,
        "Popen",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    result = adapter.open_in_browser(url="https://example.com")

    assert result["target_url"] == "https://example.com"
    assert calls[0][0] == ["cmd", "/c", "start", "", "https://example.com"]
    assert calls[0][1]["creationflags"] == windows_platform.subprocess.CREATE_NO_WINDOW


def test_windows_build_shell_operation_path_uses_double_null_suffix(tmp_path):
    path = tmp_path / "sample.txt"

    built = WindowsAdapter._build_shell_operation_path(path)

    assert built == f"{path}\0\0"


def test_windows_move_to_trash_uses_shell_delete_flags(tmp_path):
    target = tmp_path / "sample.txt"
    target.write_text("data", encoding="utf-8")

    adapter = WindowsAdapter.__new__(WindowsAdapter)
    adapter._shell32 = _FakeShell32(result=0, aborted=False)

    result = adapter.move_to_trash(str(target))

    assert result == {"ok": True, "error": None}
    assert adapter._shell32.calls == [
        {
            "wFunc": 3,
            "pFrom": str(target),
            "fFlags": 1108,
        }
    ]


def test_windows_move_to_trash_returns_missing_path_error(tmp_path):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    adapter._shell32 = _FakeShell32(result=0, aborted=False)
    missing = tmp_path / "missing.txt"

    result = adapter.move_to_trash(str(missing))

    assert result == {"ok": False, "error": f"路径不存在: {missing.resolve()}"}
    assert adapter._shell32.calls == []


def test_windows_move_to_trash_returns_cancelled_when_operation_aborted(tmp_path):
    target = tmp_path / "sample.txt"
    target.write_text("data", encoding="utf-8")

    adapter = WindowsAdapter.__new__(WindowsAdapter)
    adapter._shell32 = _FakeShell32(result=0, aborted=True)

    result = adapter.move_to_trash(str(target))

    assert result == {"ok": False, "error": "操作已取消"}


def test_windows_move_to_trash_returns_win32_error(monkeypatch, tmp_path):
    target = tmp_path / "sample.txt"
    target.write_text("data", encoding="utf-8")

    adapter = WindowsAdapter.__new__(WindowsAdapter)
    adapter._shell32 = _FakeShell32(result=5, aborted=False)
    monkeypatch.setattr("baodou_ai.platform.windows.ctypes.FormatError", lambda code: f"Windows error {code}")

    result = adapter.move_to_trash(str(target))

    assert result == {"ok": False, "error": "Windows error 5"}


def test_windows_activate_app_returns_false_without_valid_pid():
    adapter = WindowsAdapter.__new__(WindowsAdapter)

    assert adapter.activate_app({"app_name": "Microsoft Word"}) is False


def test_windows_activate_app_prefers_recorded_hwnd_before_pid_lookup(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    adapter._user32 = _FakeActivateUser32()

    states = iter([False, True])
    calls = []
    monkeypatch.setattr(adapter, "_find_window_by_handle", lambda hwnd, pid=0: calls.append(("hwnd", hwnd, pid)) or 600)
    monkeypatch.setattr(adapter, "_find_top_level_window_by_pid", lambda pid: calls.append(("pid", pid)) or 500)
    monkeypatch.setattr(adapter, "_is_foreground_match", lambda hwnd, pid: next(states))
    monkeypatch.setattr(adapter, "_is_window_minimized", lambda hwnd: False)
    monkeypatch.setattr(adapter, "_bring_window_to_foreground", lambda hwnd: calls.append(("simple", hwnd)) or True)
    monkeypatch.setattr(adapter, "_bring_window_to_foreground_with_attach", lambda hwnd: calls.append(("attach", hwnd)) or False)

    assert adapter.activate_app({"app_name": "File Explorer", "pid": 9527, "hwnd": 600}) is True
    assert calls == [
        ("hwnd", 600, 9527),
        ("simple", 600),
    ]


def test_windows_activate_app_restores_minimized_window_before_foreground(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    adapter._user32 = _FakeActivateUser32()

    states = iter([False, True])
    calls = []
    monkeypatch.setattr(adapter, "_find_top_level_window_by_pid", lambda pid: 500 if pid == 9527 else 0)
    monkeypatch.setattr(adapter, "_is_foreground_match", lambda hwnd, pid: next(states))
    monkeypatch.setattr(adapter, "_is_window_minimized", lambda hwnd: True)
    monkeypatch.setattr(adapter, "_bring_window_to_foreground", lambda hwnd: calls.append(("simple", hwnd)) or True)
    monkeypatch.setattr(adapter, "_bring_window_to_foreground_with_attach", lambda hwnd: calls.append(("attach", hwnd)) or False)

    assert adapter.activate_app({"app_name": "Microsoft Word", "pid": 9527}) is True
    assert adapter._user32.show_calls == [(500, 9)]
    assert calls == [("simple", 500)]


def test_windows_bring_window_to_foreground_with_attach_attaches_threads():
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    adapter._user32 = _FakeActivateUser32()
    adapter._kernel32 = _FakeKernel32ForActivate(current_thread_id=10)

    assert adapter._bring_window_to_foreground_with_attach(500) is True
    assert adapter._user32.attach_calls == [
        (30, 10, True),
        (50, 10, True),
        (50, 10, False),
        (30, 10, False),
    ]


def test_windows_activate_app_uses_attach_fallback_when_simple_foreground_does_not_take_effect(monkeypatch):
    adapter = WindowsAdapter.__new__(WindowsAdapter)
    adapter._user32 = _FakeActivateUser32()

    states = iter([False, False, True])
    calls = []
    monkeypatch.setattr(adapter, "_find_top_level_window_by_pid", lambda pid: 500 if pid == 9527 else 0)
    monkeypatch.setattr(adapter, "_is_foreground_match", lambda hwnd, pid: next(states))
    monkeypatch.setattr(adapter, "_is_window_minimized", lambda hwnd: False)
    monkeypatch.setattr(adapter, "_bring_window_to_foreground", lambda hwnd: calls.append(("simple", hwnd)) or False)
    monkeypatch.setattr(adapter, "_bring_window_to_foreground_with_attach", lambda hwnd: calls.append(("attach", hwnd)) or True)

    assert adapter.activate_app({"app_name": "Microsoft Word", "pid": 9527}) is True
    assert calls == [("simple", 500), ("attach", 500)]
