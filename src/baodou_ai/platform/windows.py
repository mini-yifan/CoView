"""
Windows平台适配器

提供Windows平台特定的功能实现。
"""

import ctypes
import os
import re
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pyautogui
from PyQt5.QtCore import Qt

from baodou_ai.gui.floating.windows_native import WindowsOverlayHelper
from baodou_ai.platform.base import PlatformAdapter
from baodou_ai.platform.common import (
    build_browser_target_url,
    is_chrome_family_browser,
    rank_named_candidates,
    score_name_match,
)


GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x00000080
WDA_EXCLUDEFROMCAPTURE = 0x00000011
LWA_ALPHA = 0x00000002
SM_CMONITORS = 80
SM_CXSCREEN = 0
SM_CYSCREEN = 1
MONITORINFOF_PRIMARY = 1
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GW_OWNER = 4
SW_RESTORE = 9
FO_DELETE = 0x0003
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400
_POWERSHELL_NONE_SENTINEL = "__COVIEW_AI_NONE__"
_POWERSHELL_EMPTY_SENTINEL = "__COVIEW_AI_EMPTY__"


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


class WindowsAdapter(PlatformAdapter):
    """Windows平台适配器"""
    
    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._shell32 = ctypes.windll.shell32
        self._gdi32 = ctypes.windll.gdi32
        self._overlay_native = WindowsOverlayHelper(self._user32, self._gdi32)
        self._is_transparent_mode = False
        self._original_opacity = 0.95
        self._app_catalog_cache: Optional[List[Dict[str, Any]]] = None
    
    def get_resource_path(self, relative_path: str) -> Optional[str]:
        """获取资源文件路径"""
        if os.path.isabs(relative_path):
            return relative_path
        
        if os.path.exists(relative_path):
            return os.path.abspath(relative_path)
        
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        full_path = os.path.join(base_dir, relative_path)
        if os.path.exists(full_path):
            return full_path
        
        return None
    
    def setup_window(self, window) -> None:
        """设置普通窗口属性。

        悬浮主 UI 会通过 prepare_overlay_window() 走单独的 overlay 初始化，
        普通窗口不要复用那条链路，避免在 Windows 上被误处理成 tool window。
        """
        try:
            opacity = getattr(window, "windowOpacity", lambda: self._original_opacity)()
            if opacity > 0:
                self._overlay_native.remember_opacity(window, opacity)
        except Exception as e:
            print(f"设置窗口属性时出错: {e}")

    def prepare_overlay_window(self, window) -> None:
        opacity = getattr(window, "windowOpacity", lambda: self._original_opacity)()
        if opacity > 0:
            self._overlay_native.remember_opacity(window, opacity)
        self._overlay_native.ensure_overlay_window(window)

    def refresh_overlay_window(self, window) -> None:
        self.prepare_overlay_window(window)

    def apply_overlay_region(self, window, kind: str, radius_or_bounds=None) -> bool:
        if kind == "ellipse":
            inset = int(radius_or_bounds or 0)
            return self._overlay_native.apply_ellipse_region(window, inset=inset)
        if kind == "round_rect":
            radius = int(radius_or_bounds or 0)
            return self._overlay_native.apply_round_rect_region(window, radius=radius)
        return False

    def clear_overlay_region(self, window) -> bool:
        return self._overlay_native.clear_region(window)
    
    def prevent_screenshot(self, window) -> bool:
        """防止窗口被截图"""
        try:
            hwnd = window.winId().__int__()
            self._user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            print("窗口已设置为不可被截图")
            return True
        except Exception as e:
            print(f"设置窗口不可被截图时出错: {e}")
            return False

    def allow_screenshot(self, window) -> bool:
        """允许窗口被截图"""
        try:
            hwnd = window.winId().__int__()
            self._user32.SetWindowDisplayAffinity(hwnd, 0)
            print("窗口已恢复可被截图")
            return True
        except Exception as e:
            print(f"恢复窗口截图时出错: {e}")
            return False
    
    def translate_hotkey_keys(self, keys: List[str]) -> List[str]:
        """翻译快捷键"""
        translated: List[str] = []
        for key in keys:
            if key == "meta":
                translated.append("win")
            elif key == "control":
                translated.append("ctrl")
            elif key == "option":
                translated.append("alt")
            else:
                translated.append(key)
        return translated
    
    def get_hotkey_modifier(self) -> str:
        """获取快捷键修饰符"""
        return "ctrl"
    
    def is_app_bundle(self) -> bool:
        """检测是否在打包的应用程序中运行"""
        return False
    
    def enter_transparent_mode(self, window) -> bool:
        """
        进入透明穿透模式
        
        窗口变为完全透明且鼠标可穿透
        """
        try:
            restore_opacity = getattr(window, "windowOpacity", lambda: self._original_opacity)()
            if restore_opacity > 0:
                self._overlay_native.remember_opacity(window, restore_opacity)
            window.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            window.setWindowOpacity(0.0)
            self._overlay_native.set_click_through(window, True)
            self._is_transparent_mode = True
            print("窗口已进入透明穿透模式")
            return True
        except Exception as e:
            print(f"进入透明穿透模式时出错: {e}")
            return False
    
    def exit_transparent_mode(self, window) -> bool:
        """
        退出透明穿透模式
        
        窗口恢复不透明且鼠标不可穿透，不抢占焦点
        """
        try:
            restore_opacity = self._overlay_native.restore_opacity(window, default=self._original_opacity)
            window.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            window.setWindowOpacity(restore_opacity)
            self._overlay_native.set_click_through(window, False)
            self._is_transparent_mode = False
            print("窗口已退出透明穿透模式")
            return True
        except Exception as e:
            print(f"退出透明穿透模式时出错: {e}")
            return False
    
    def get_scaling_factor(self) -> float:
        """
        获取屏幕缩放因子（DPI缩放）

        在 Windows 高 DPI 屏幕上，可能有不同的缩放比例。

        Returns:
            缩放因子，例如 150% 缩放返回 1.5，普通屏幕返回 1.0
        """
        try:
            try:
                return float(self._user32.GetDpiForSystem()) / 96.0
            except AttributeError:
                pass

            self._user32.SetProcessDPIAware()
            hdc = self._user32.GetDC(0)
            if not hdc:
                return 1.0

            try:
                LOGPIXELSX = 88
                dpi = self._gdi32.GetDeviceCaps(hdc, LOGPIXELSX)
            finally:
                self._user32.ReleaseDC(0, hdc)

            return float(dpi) / 96.0 if dpi else 1.0
        except Exception as e:
            print(f"获取缩放因子时出错: {e}")
        
        return 1.0
    
    def get_logical_screen_size(self) -> tuple:
        """
        获取逻辑屏幕尺寸

        逻辑尺寸是 pyautogui 鼠标操作使用的坐标系统。

        Returns:
            (width, height) 逻辑屏幕尺寸
        """
        import pyautogui
        size = pyautogui.size()
        return (size.width, size.height)
    
    def get_screen_count(self) -> int:
        """
        获取屏幕数量
        
        Returns:
            屏幕数量
        """
        try:
            return self._user32.GetSystemMetrics(SM_CMONITORS)
        except Exception as e:
            print(f"获取屏幕数量时出错: {e}")
            return 1
    
    def get_all_screens_info(self) -> List[Dict[str, Any]]:
        """
        获取所有屏幕信息
        
        Returns:
            屏幕信息列表
        """
        try:
            monitors = []
            
            class RECT(ctypes.Structure):
                _fields_ = [
                    ('left', ctypes.c_long),
                    ('top', ctypes.c_long),
                    ('right', ctypes.c_long),
                    ('bottom', ctypes.c_long)
                ]
            
            class MONITORINFOEX(ctypes.Structure):
                _fields_ = [
                    ('cbSize', ctypes.c_ulong),
                    ('rcMonitor', RECT),
                    ('rcWork', RECT),
                    ('dwFlags', ctypes.c_ulong),
                    ('szDevice', ctypes.c_wchar * 32)
                ]
            
            def callback(hmonitor, hdc, rect, data):
                monitor_info = MONITORINFOEX()
                monitor_info.cbSize = ctypes.sizeof(MONITORINFOEX)
                self._user32.GetMonitorInfoW(hmonitor, ctypes.byref(monitor_info))
                monitors.append({
                    'handle': hmonitor,
                    'rect': monitor_info.rcMonitor,
                    'device_name': monitor_info.szDevice,
                    'is_primary': (monitor_info.dwFlags & MONITORINFOF_PRIMARY) != 0
                })
                return 1
            
            MonitorEnumProc = ctypes.WINFUNCTYPE(
                ctypes.c_int,
                ctypes.c_ulong,
                ctypes.c_ulong,
                ctypes.POINTER(RECT),
                ctypes.c_double
            )
            
            self._user32.EnumDisplayMonitors(
                None, None, MonitorEnumProc(callback), 0
            )
            
            result = []
            for i, mon in enumerate(monitors):
                rect = mon['rect']
                result.append({
                    'index': i,
                    'device_name': mon.get('device_name', ''),
                    'x': rect.left,
                    'y': rect.top,
                    'width': rect.right - rect.left,
                    'height': rect.bottom - rect.top,
                    'is_primary': mon['is_primary']
                })
            
            return result
        except Exception as e:
            print(f"获取所有屏幕信息时出错: {e}")
            return [{'index': 0, 'x': 0, 'y': 0, 'width': 1920, 'height': 1080, 'is_primary': True}]

    def _get_current_display_settings(self) -> Dict[str, Dict[str, int]]:
        """Return current display mode rectangles keyed by Win32 device name."""
        try:
            CCHDEVICENAME = 32
            CCHFORMNAME = 32
            DISPLAY_DEVICE_ACTIVE = 0x00000001
            ENUM_CURRENT_SETTINGS = -1

            class DISPLAY_DEVICEW(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("DeviceName", ctypes.c_wchar * CCHDEVICENAME),
                    ("DeviceString", ctypes.c_wchar * 128),
                    ("StateFlags", wintypes.DWORD),
                    ("DeviceID", ctypes.c_wchar * 128),
                    ("DeviceKey", ctypes.c_wchar * 128),
                ]

            class POINTL(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            class DEVMODEW(ctypes.Structure):
                _fields_ = [
                    ("dmDeviceName", ctypes.c_wchar * CCHDEVICENAME),
                    ("dmSpecVersion", wintypes.WORD),
                    ("dmDriverVersion", wintypes.WORD),
                    ("dmSize", wintypes.WORD),
                    ("dmDriverExtra", wintypes.WORD),
                    ("dmFields", wintypes.DWORD),
                    ("dmPosition", POINTL),
                    ("dmDisplayOrientation", wintypes.DWORD),
                    ("dmDisplayFixedOutput", wintypes.DWORD),
                    ("dmColor", wintypes.WORD),
                    ("dmDuplex", wintypes.WORD),
                    ("dmYResolution", wintypes.WORD),
                    ("dmTTOption", wintypes.WORD),
                    ("dmCollate", wintypes.WORD),
                    ("dmFormName", ctypes.c_wchar * CCHFORMNAME),
                    ("dmLogPixels", wintypes.WORD),
                    ("dmBitsPerPel", wintypes.DWORD),
                    ("dmPelsWidth", wintypes.DWORD),
                    ("dmPelsHeight", wintypes.DWORD),
                    ("dmDisplayFlags", wintypes.DWORD),
                    ("dmDisplayFrequency", wintypes.DWORD),
                    ("dmICMMethod", wintypes.DWORD),
                    ("dmICMIntent", wintypes.DWORD),
                    ("dmMediaType", wintypes.DWORD),
                    ("dmDitherType", wintypes.DWORD),
                    ("dmReserved1", wintypes.DWORD),
                    ("dmReserved2", wintypes.DWORD),
                    ("dmPanningWidth", wintypes.DWORD),
                    ("dmPanningHeight", wintypes.DWORD),
                ]

            settings: Dict[str, Dict[str, int]] = {}
            device_index = 0
            while True:
                display_device = DISPLAY_DEVICEW()
                display_device.cb = ctypes.sizeof(display_device)
                if not self._user32.EnumDisplayDevicesW(None, device_index, ctypes.byref(display_device), 0):
                    break
                device_index += 1
                if not (int(display_device.StateFlags) & DISPLAY_DEVICE_ACTIVE):
                    continue

                devmode = DEVMODEW()
                devmode.dmSize = ctypes.sizeof(devmode)
                if not self._user32.EnumDisplaySettingsW(
                    display_device.DeviceName,
                    ENUM_CURRENT_SETTINGS,
                    ctypes.byref(devmode),
                ):
                    continue
                settings[display_device.DeviceName] = {
                    "x": int(devmode.dmPosition.x),
                    "y": int(devmode.dmPosition.y),
                    "width": int(devmode.dmPelsWidth),
                    "height": int(devmode.dmPelsHeight),
                }

            return settings
        except Exception as e:
            print(f"Failed to get Windows current display settings: {e}")
            return {}

    def get_capture_screens_info(self) -> List[Dict[str, Any]]:
        """获取用于截图的屏幕信息。"""
        screens = self.get_all_screens_info()
        display_settings = self._get_current_display_settings()
        sorted_screens = sorted(
            screens,
            key=lambda screen: (
                0 if screen.get("is_primary") else 1,
                screen.get("x", 0),
                screen.get("y", 0),
            ),
        )

        capture_screens: List[Dict[str, Any]] = []
        for index, screen in enumerate(sorted_screens):
            logical_x = int(screen.get("x", 0))
            logical_y = int(screen.get("y", 0))
            logical_width = int(screen.get("width", 0))
            logical_height = int(screen.get("height", 0))
            device_name = str(screen.get("device_name") or "")
            capture_rect = display_settings.get(device_name, {})
            capture_x = int(capture_rect.get("x", logical_x))
            capture_y = int(capture_rect.get("y", logical_y))
            capture_width = int(capture_rect.get("width", logical_width))
            capture_height = int(capture_rect.get("height", logical_height))
            capture_screens.append({
                "index": index,
                "is_primary": bool(screen.get("is_primary")),
                "logical_x": logical_x,
                "logical_y": logical_y,
                "logical_width": logical_width,
                "logical_height": logical_height,
                "capture_x": capture_x,
                "capture_y": capture_y,
                "capture_width": capture_width,
                "capture_height": capture_height,
            })

        return capture_screens

    def get_screen_rect(self, screen_index: int) -> Tuple[int, int, int, int]:
        """
        获取指定屏幕的矩形区域
        
        Args:
            screen_index: 屏幕索引
        
        Returns:
            (x, y, width, height) 屏幕在虚拟桌面中的位置和尺寸
        """
        screens_info = self.get_all_screens_info()
        if 0 <= screen_index < len(screens_info):
            info = screens_info[screen_index]
            return (info['x'], info['y'], info['width'], info['height'])
        return (0, 0, 1920, 1080)

    def move_cursor(self, x: float, y: float, duration: float = 0.0) -> None:
        """移动鼠标到指定坐标。"""
        tween = getattr(pyautogui, "easeInOutQuad", None)
        if tween is not None:
            pyautogui.moveTo(x, y, duration=duration, tween=tween)
        else:
            pyautogui.moveTo(x, y, duration=duration)

    def click(self, button: str = "left", clicks: int = 1) -> None:
        """在当前位置执行点击。"""
        if clicks <= 1:
            if button == "right":
                pyautogui.rightClick()
            else:
                pyautogui.click(button=button)
            return
        pyautogui.click(button=button, clicks=clicks, interval=0.05)

    def mouse_down(self, button: str = "left") -> None:
        """按下鼠标按键。"""
        pyautogui.mouseDown(button=button)

    def mouse_up(self, button: str = "left") -> None:
        """释放鼠标按键。"""
        pyautogui.mouseUp(button=button)

    def drag_to(self, x: float, y: float, duration: float = 0.0, button: str = "left") -> None:
        """拖拽到指定坐标。"""
        tween = getattr(pyautogui, "easeInOutQuad", None)
        if tween is not None:
            pyautogui.dragTo(x, y, duration=duration, button=button, tween=tween)
        else:
            pyautogui.dragTo(x, y, duration=duration, button=button)

    def scroll(self, amount: int) -> None:
        """滚动滚轮。"""
        pyautogui.scroll(amount)

    def key_down(self, key: str) -> None:
        """按下键盘按键。"""
        pyautogui.keyDown(key)

    def key_up(self, key: str) -> None:
        """释放键盘按键。"""
        pyautogui.keyUp(key)

    @staticmethod
    def _build_launch_result(
        matched: bool,
        app_name: str = "",
        app_path: str = "",
        suggestions: Optional[List[str]] = None,
        error: str = "",
    ) -> Dict[str, Any]:
        return {
            "matched": matched,
            "app_name": app_name,
            "app_path": app_path,
            "suggestions": suggestions or [],
            "error": error,
        }

    def _discover_registry_app_paths(self) -> List[Dict[str, Any]]:
        try:
            import winreg
        except ImportError:
            return []

        results: List[Dict[str, Any]] = []
        roots = [
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        ]

        for root, subkey_path in roots:
            try:
                with winreg.OpenKey(root, subkey_path) as parent_key:
                    subkey_count = winreg.QueryInfoKey(parent_key)[0]
                    for index in range(subkey_count):
                        try:
                            subkey_name = winreg.EnumKey(parent_key, index)
                            with winreg.OpenKey(parent_key, subkey_name) as subkey:
                                app_path, _ = winreg.QueryValueEx(subkey, "")
                        except OSError:
                            continue

                        if not app_path or not os.path.exists(app_path):
                            continue

                        app_name = os.path.splitext(os.path.basename(app_path))[0]
                        results.append({
                            "name": app_name,
                            "path": app_path,
                            "aliases": [subkey_name],
                        })
            except OSError:
                continue

        return results

    def _discover_start_menu_apps(self) -> List[Dict[str, Any]]:
        roots = [
            os.path.join(os.environ.get("ProgramData", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        ]

        results: List[Dict[str, Any]] = []
        for root in roots:
            if not os.path.isdir(root):
                continue
            for current_root, _dirs, files in os.walk(root):
                for filename in files:
                    if not filename.lower().endswith((".lnk", ".exe")):
                        continue
                    path = os.path.join(current_root, filename)
                    name = os.path.splitext(filename)[0]
                    results.append({
                        "name": name,
                        "path": path,
                        "aliases": [],
                    })
        return results

    def _discover_install_dir_apps(self) -> List[Dict[str, Any]]:
        roots = [
            os.environ.get("ProgramFiles", ""),
            os.environ.get("ProgramFiles(x86)", ""),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        ]

        results: List[Dict[str, Any]] = []
        for root in roots:
            if not os.path.isdir(root):
                continue
            try:
                for entry in os.scandir(root):
                    if not entry.is_dir():
                        continue
                    try:
                        for child in os.scandir(entry.path):
                            if child.is_file() and child.name.lower().endswith(".exe"):
                                results.append({
                                    "name": os.path.splitext(child.name)[0],
                                    "path": child.path,
                                    "aliases": [entry.name],
                                })
                    except OSError:
                        continue
            except OSError:
                continue
        return results

    def _list_available_apps(self) -> List[Dict[str, Any]]:
        if self._app_catalog_cache is not None:
            return self._app_catalog_cache

        catalog = (
            self._discover_registry_app_paths()
            + self._discover_start_menu_apps()
            + self._discover_install_dir_apps()
        )

        deduped: List[Dict[str, Any]] = []
        seen_paths = set()
        for item in catalog:
            path = str(item.get("path", "")).strip().lower()
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            deduped.append(item)

        self._app_catalog_cache = deduped
        return deduped

    def _find_app_match(self, app_name: str) -> Dict[str, Any]:
        apps = self._list_available_apps()
        if not apps:
            return self._build_launch_result(
                matched=False,
                error=f"当前电脑上没有找到名为“{app_name}”的应用，也没有足够接近的候选名称，建议询问用户更准确的应用名称。",
            )

        exact_matches = [
            candidate
            for candidate in apps
            if score_name_match(app_name, candidate["name"], candidate.get("aliases")) >= 1.0
        ]
        if exact_matches:
            best = exact_matches[0]
            return self._build_launch_result(
                matched=True,
                app_name=best["name"],
                app_path=best["path"],
            )

        ranked = rank_named_candidates(app_name, apps, max_results=3, cutoff=0.72)
        if ranked:
            top_candidate = ranked[0]
            top_score = float(top_candidate.get("score", 0.0))
            second_score = float(ranked[1].get("score", 0.0)) if len(ranked) > 1 else 0.0
            if top_score >= 0.9 and (len(ranked) == 1 or (top_score - second_score) >= 0.08):
                return self._build_launch_result(
                    matched=True,
                    app_name=top_candidate["name"],
                    app_path=top_candidate["path"],
                )
            suggestions = [candidate["name"] for candidate in ranked]
            return self._build_launch_result(
                matched=False,
                suggestions=suggestions,
                error=f"没有找到名为“{app_name}”的应用，可能是这些：{'、'.join(suggestions)}",
            )

        return self._build_launch_result(
            matched=False,
            error=f"当前电脑上没有找到名为“{app_name}”的应用，也没有足够接近的候选名称，建议询问用户更准确的应用名称。",
        )

    def launch_app(self, app_name: str) -> Dict[str, Any]:
        match = self._find_app_match(app_name)
        if not match.get("matched"):
            return match

        running_app = self._find_running_app_info(
            str(match.get("app_name") or "").strip() or str(app_name or "").strip(),
            str(match.get("app_path") or "").strip(),
        )
        if running_app and self.activate_app(running_app):
            return match

        app_path = str(match.get("app_path") or "").strip()
        if not app_path:
            raise RuntimeError("命中的应用缺少可启动路径。")

        if hasattr(os, "startfile"):
            os.startfile(app_path)
        else:
            subprocess.Popen([app_path])
        return match

    def open_app_launcher(self) -> Dict[str, Any]:
        pyautogui.press("win")
        return {
            "app_names": [],
        }

    def open_in_finder(self, path: Optional[str] = None) -> Dict[str, Any]:
        if path is None:
            target_path = str(Path.home() / "Desktop")
            if hasattr(os, "startfile"):
                os.startfile(target_path)
            else:
                subprocess.Popen(["explorer.exe", target_path])
            return {
                "target_path": target_path,
                "revealed_file": None,
            }

        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            return {
                "target_path": None,
                "revealed_file": None,
                "error": f"路径不存在: {resolved}",
            }

        if resolved.is_file():
            subprocess.Popen(["explorer.exe", "/select,", str(resolved)])
            return {
                "target_path": str(resolved.parent),
                "revealed_file": str(resolved),
            }

        target_path = str(resolved)
        if hasattr(os, "startfile"):
            os.startfile(target_path)
        else:
            subprocess.Popen(["explorer.exe", target_path])
        return {
            "target_path": target_path,
            "revealed_file": None,
        }

    def _extract_executable_from_command(self, command: str) -> str:
        text = str(command or "").strip()
        if not text:
            return ""

        quoted_match = re.match(r'"([^"]+)"', text)
        if quoted_match:
            return quoted_match.group(1)

        parts = text.split()
        return parts[0] if parts else ""

    @staticmethod
    def _resolve_windows_app_display_name(executable_name: str, title: str = "") -> str:
        normalized_executable = str(executable_name or "").strip().lower()
        known_names = {
            "explorer.exe": "File Explorer",
            "winword.exe": "Microsoft Word",
            "excel.exe": "Microsoft Excel",
            "powerpnt.exe": "Microsoft PowerPoint",
            "notepad.exe": "Notepad",
            "code.exe": "Visual Studio Code",
            "code - insiders.exe": "Visual Studio Code",
            "cursor.exe": "Cursor",
            "windsurf.exe": "Windsurf",
            "pycharm64.exe": "PyCharm",
            "idea64.exe": "IntelliJ IDEA",
            "webstorm64.exe": "WebStorm",
            "goland64.exe": "GoLand",
            "clion64.exe": "CLion",
            "studio64.exe": "Android Studio",
            "sublime_text.exe": "Sublime Text",
            "wps.exe": "WPS",
            "kwps.exe": "WPS",
            "et.exe": "WPS",
            "ket.exe": "WPS",
            "wpp.exe": "WPS",
            "kwpp.exe": "WPS",
            "trae.exe": "TRAE",
        }
        if normalized_executable in known_names:
            return known_names[normalized_executable]

        if normalized_executable:
            return os.path.splitext(os.path.basename(normalized_executable))[0]

        return str(title or "").strip()

    def _get_process_image_path(self, pid: int) -> str:
        process_handle = None
        try:
            process_handle = self._kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not process_handle:
                return ""

            buffer_length = ctypes.c_ulong(32767)
            image_buffer = ctypes.create_unicode_buffer(buffer_length.value)
            ok = bool(
                self._kernel32.QueryFullProcessImageNameW(
                    process_handle,
                    0,
                    image_buffer,
                    ctypes.byref(buffer_length),
                )
            )
            if not ok:
                return ""
            return image_buffer.value[: buffer_length.value].strip()
        except Exception:
            return ""
        finally:
            if process_handle:
                try:
                    self._kernel32.CloseHandle(process_handle)
                except Exception:
                    pass

    def _run_powershell(self, script: str, timeout: float = 2.0) -> Optional[str]:
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except Exception:
            return None

        if result.returncode != 0:
            return None

        output = (result.stdout or "").strip()
        if not output:
            return None
        if output == _POWERSHELL_NONE_SENTINEL:
            return None
        if output == _POWERSHELL_EMPTY_SENTINEL:
            return ""
        return output.strip().strip('"')

    @staticmethod
    def _normalize_document_app_family(app_name: str) -> str:
        normalized = str(app_name or "").strip().lower()
        if normalized in {"microsoft word"}:
            return "word"
        if normalized in {"microsoft excel"}:
            return "excel"
        if normalized in {"microsoft powerpoint"}:
            return "powerpoint"
        if normalized in {"wps"}:
            return "wps"
        if normalized in {"file explorer", "windows explorer", "explorer", "资源管理器"}:
            return "explorer"
        return ""

    def _get_foreground_window_handle(self) -> int:
        try:
            return int(self._user32.GetForegroundWindow() or 0)
        except Exception:
            return 0

    def _enumerate_top_level_windows(self) -> List[int]:
        windows: List[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            windows.append(int(hwnd))
            return True

        try:
            self._user32.EnumWindows(callback, 0)
        except Exception:
            return []
        return windows

    def _get_window_pid(self, hwnd: int) -> int:
        try:
            pid = ctypes.c_ulong(0)
            self._user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
            return int(pid.value)
        except Exception:
            return 0

    def _is_candidate_main_window(self, hwnd: int) -> bool:
        try:
            if not bool(self._user32.IsWindowVisible(int(hwnd))):
                return False
            if int(self._user32.GetWindow(int(hwnd), GW_OWNER) or 0) != 0:
                return False
            return True
        except Exception:
            return False

    def _find_top_level_window_by_pid(self, pid: int) -> int:
        for hwnd in self._enumerate_top_level_windows():
            if self._get_window_pid(hwnd) != int(pid):
                continue
            if self._is_candidate_main_window(hwnd):
                return int(hwnd)
        return 0

    def _find_running_app_info(self, app_name: str, app_path: str = "") -> Optional[Dict[str, Any]]:
        normalized_name = str(app_name or "").strip()
        normalized_app_path = str(app_path or "").strip().lower()
        normalized_executable = os.path.basename(normalized_app_path) if normalized_app_path else ""

        for hwnd in self._enumerate_top_level_windows():
            if not self._is_candidate_main_window(hwnd):
                continue
            pid = self._get_window_pid(hwnd)
            if pid <= 0:
                continue
            process_path = self._get_process_image_path(pid)
            process_path_normalized = str(process_path or "").strip().lower()
            executable_name = os.path.basename(process_path_normalized)
            display_name = self._resolve_windows_app_display_name(executable_name)

            if normalized_app_path and process_path_normalized and process_path_normalized == normalized_app_path:
                pass
            elif normalized_executable and executable_name and executable_name == normalized_executable:
                pass
            elif normalized_name and score_name_match(normalized_name, display_name) >= 1.0:
                pass
            else:
                continue

            return {
                "app_name": display_name or normalized_name,
                "bundle_id": "",
                "identifier": process_path or executable_name or str(pid),
                "pid": pid,
                "hwnd": int(hwnd),
                "app_path": process_path,
                "executable_name": os.path.basename(process_path) if process_path else executable_name,
            }
        return None

    def _find_window_by_handle(self, hwnd: int, pid: int = 0) -> int:
        candidate = int(hwnd or 0)
        if candidate <= 0:
            return 0
        if not self._is_candidate_main_window(candidate):
            return 0
        if pid > 0 and self._get_window_pid(candidate) != int(pid):
            return 0
        return candidate

    def _is_window_minimized(self, hwnd: int) -> bool:
        try:
            return bool(self._user32.IsIconic(int(hwnd)))
        except Exception:
            return False

    def _bring_window_to_foreground(self, hwnd: int) -> bool:
        try:
            self._user32.BringWindowToTop(int(hwnd))
        except Exception:
            pass
        try:
            return bool(self._user32.SetForegroundWindow(int(hwnd)))
        except Exception:
            return False

    def _bring_window_to_foreground_with_attach(self, hwnd: int) -> bool:
        attached_pairs: List[Tuple[int, int]] = []
        try:
            current_thread_id = int(self._kernel32.GetCurrentThreadId())
            foreground_hwnd = self._get_foreground_window_handle()
            foreground_thread_id = int(self._user32.GetWindowThreadProcessId(int(foreground_hwnd), None) or 0)
            target_thread_id = int(self._user32.GetWindowThreadProcessId(int(hwnd), None) or 0)

            for source_thread_id in (foreground_thread_id, target_thread_id):
                if source_thread_id <= 0 or source_thread_id == current_thread_id:
                    continue
                if bool(self._user32.AttachThreadInput(source_thread_id, current_thread_id, True)):
                    attached_pairs.append((source_thread_id, current_thread_id))

            try:
                self._user32.BringWindowToTop(int(hwnd))
            except Exception:
                pass
            return bool(self._user32.SetForegroundWindow(int(hwnd)))
        except Exception:
            return False
        finally:
            for source_thread_id, target_thread_id in reversed(attached_pairs):
                try:
                    self._user32.AttachThreadInput(source_thread_id, target_thread_id, False)
                except Exception:
                    pass

    def _is_foreground_match(self, hwnd: int, pid: int) -> bool:
        current_hwnd = self._get_foreground_window_handle()
        if current_hwnd > 0 and int(current_hwnd) == int(hwnd):
            return True
        if pid > 0 and self._get_window_pid(current_hwnd) == int(pid):
            return True
        return False

    def _get_active_explorer_path(self) -> Optional[str]:
        hwnd = self._get_foreground_window_handle()
        if hwnd <= 0:
            return None

        script = f"""
$targetHwnd = [int64]{hwnd}
try {{
    $shell = New-Object -ComObject Shell.Application
}} catch {{
    Write-Output '{_POWERSHELL_NONE_SENTINEL}'
    exit 0
}}

foreach ($window in $shell.Windows()) {{
    try {{
        if ([int64]$window.HWND -ne $targetHwnd) {{
            continue
        }}
        $folder = $window.Document.Folder
        if ($null -eq $folder -or $null -eq $folder.Self) {{
            Write-Output '{_POWERSHELL_EMPTY_SENTINEL}'
            exit 0
        }}
        $path = [string]$folder.Self.Path
        if ([string]::IsNullOrWhiteSpace($path)) {{
            Write-Output '{_POWERSHELL_EMPTY_SENTINEL}'
            exit 0
        }}
        Write-Output $path.Trim()
        exit 0
    }} catch {{
        continue
    }}
}}

Write-Output '{_POWERSHELL_NONE_SENTINEL}'
"""
        return self._run_powershell(script, timeout=2.5)

    def _get_office_active_document_path(
        self,
        prog_id: str,
        active_member: str,
        path_member: str = "FullName",
    ) -> Optional[str]:
        script = f"""
try {{
    $app = [System.Runtime.InteropServices.Marshal]::GetActiveObject('{prog_id}')
}} catch {{
    Write-Output '{_POWERSHELL_NONE_SENTINEL}'
    exit 0
}}

try {{
    $doc = $app.{active_member}
    if ($null -eq $doc) {{
        Write-Output '{_POWERSHELL_NONE_SENTINEL}'
        exit 0
    }}
    $path = [string]$doc.{path_member}
    if ([string]::IsNullOrWhiteSpace($path)) {{
        Write-Output '{_POWERSHELL_EMPTY_SENTINEL}'
        exit 0
    }}
    Write-Output $path.Trim()
}} catch {{
    Write-Output '{_POWERSHELL_NONE_SENTINEL}'
}}
"""
        return self._run_powershell(script, timeout=2.5)

    def _get_word_active_document_path(self) -> Optional[str]:
        return self._get_office_active_document_path("Word.Application", "ActiveDocument")

    def _get_excel_active_document_path(self) -> Optional[str]:
        return self._get_office_active_document_path("Excel.Application", "ActiveWorkbook")

    def _get_powerpoint_active_document_path(self) -> Optional[str]:
        return self._get_office_active_document_path("PowerPoint.Application", "ActivePresentation")

    def _get_wps_active_document_path(self) -> Optional[str]:
        script = f"""
$candidates = @(
    @{{ ProgId = 'KWPS.Application'; ActiveMember = 'ActiveDocument'; PathMember = 'FullName' }},
    @{{ ProgId = 'wps.Application'; ActiveMember = 'ActiveDocument'; PathMember = 'FullName' }},
    @{{ ProgId = 'KET.Application'; ActiveMember = 'ActiveWorkbook'; PathMember = 'FullName' }},
    @{{ ProgId = 'et.Application'; ActiveMember = 'ActiveWorkbook'; PathMember = 'FullName' }},
    @{{ ProgId = 'KWPP.Application'; ActiveMember = 'ActivePresentation'; PathMember = 'FullName' }},
    @{{ ProgId = 'wpp.Application'; ActiveMember = 'ActivePresentation'; PathMember = 'FullName' }}
)

foreach ($candidate in $candidates) {{
    try {{
        $app = [System.Runtime.InteropServices.Marshal]::GetActiveObject($candidate.ProgId)
    }} catch {{
        continue
    }}
    try {{
        $doc = $app.($candidate.ActiveMember)
        if ($null -eq $doc) {{
            continue
        }}
        $path = [string]$doc.($candidate.PathMember)
        if ([string]::IsNullOrWhiteSpace($path)) {{
            Write-Output '{_POWERSHELL_EMPTY_SENTINEL}'
            exit 0
        }}
        Write-Output $path.Trim()
        exit 0
    }} catch {{
        continue
    }}
}}

Write-Output '{_POWERSHELL_NONE_SENTINEL}'
"""
        return self._run_powershell(script, timeout=2.5)

    def get_active_document_path(self, app_name: str) -> Optional[str]:
        app_family = self._normalize_document_app_family(app_name)
        if app_family == "explorer":
            return self._get_active_explorer_path()
        if app_family == "word":
            return self._get_word_active_document_path()
        if app_family == "excel":
            return self._get_excel_active_document_path()
        if app_family == "powerpoint":
            return self._get_powerpoint_active_document_path()
        if app_family == "wps":
            return self._get_wps_active_document_path()
        return None

    @staticmethod
    def _build_shell_operation_path(path: Path) -> str:
        return f"{path}\0\0"

    def move_to_trash(self, path: str) -> Dict[str, Any]:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            return {"ok": False, "error": f"路径不存在: {resolved}"}

        file_op = _SHFILEOPSTRUCTW()
        file_op.hwnd = 0
        file_op.wFunc = FO_DELETE
        file_op.pFrom = self._build_shell_operation_path(resolved)
        file_op.pTo = None
        file_op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT
        file_op.fAnyOperationsAborted = False
        file_op.hNameMappings = None
        file_op.lpszProgressTitle = None

        try:
            result = int(self._shell32.SHFileOperationW(ctypes.byref(file_op)))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        if int(file_op.fAnyOperationsAborted):
            return {"ok": False, "error": "操作已取消"}
        if result != 0:
            return {"ok": False, "error": ctypes.FormatError(result).strip() or f"移到回收站失败 (Win32={result})"}
        return {"ok": True, "error": None}

    def get_default_browser_info(self) -> Dict[str, Any]:
        identifier = ""
        app_path = ""

        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
            ) as key:
                identifier, _ = winreg.QueryValueEx(key, "ProgId")
        except Exception:
            identifier = ""

        if identifier:
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_CLASSES_ROOT,
                    rf"{identifier}\shell\open\command",
                ) as key:
                    command, _ = winreg.QueryValueEx(key, "")
                    app_path = self._extract_executable_from_command(command)
            except Exception:
                app_path = ""

        executable_name = os.path.basename(app_path) if app_path else ""
        known_names = {
            "chrome.exe": "Google Chrome",
            "msedge.exe": "Microsoft Edge",
            "firefox.exe": "Mozilla Firefox",
            "brave.exe": "Brave",
            "chromium.exe": "Chromium",
        }
        app_name = known_names.get(executable_name.lower(), os.path.splitext(executable_name)[0] or identifier)

        return {
            "app_name": app_name,
            "identifier": identifier or executable_name,
            "app_path": app_path,
            "is_chrome_family": is_chrome_family_browser(identifier, app_name, executable_name),
        }

    def open_in_browser(self, url: Optional[str] = None, query: Optional[str] = None) -> Dict[str, Any]:
        if bool(url) == bool(query):
            raise ValueError("open_in_browser 必须且只能提供 url 或 query 其中一个")

        browser_info = self.get_default_browser_info()
        target_url = str(url or "").strip()
        if query:
            target_url = build_browser_target_url(
                str(query).strip(),
                bool(browser_info.get("is_chrome_family")),
            )
        if not target_url:
            raise ValueError("目标 URL 不能为空")

        if hasattr(os, "startfile"):
            os.startfile(target_url)
        else:
            subprocess.Popen(["cmd", "/c", "start", "", target_url])

        return {
            "browser": browser_info,
            "target_url": target_url,
        }

    def get_frontmost_app_info(self) -> Dict[str, Any]:
        try:
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd:
                return {}

            pid = ctypes.c_ulong(0)
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            title_buffer = ctypes.create_unicode_buffer(512)
            self._user32.GetWindowTextW(hwnd, title_buffer, 512)
            title = title_buffer.value.strip()
            pid_value = int(pid.value)
            app_path = self._get_process_image_path(pid_value)
            executable_name = os.path.basename(app_path).strip()
            app_name = self._resolve_windows_app_display_name(executable_name, title=title)
            identifier = app_path or executable_name or title or str(pid_value)

            return {
                "app_name": app_name,
                "bundle_id": "",
                "identifier": identifier,
                "pid": pid_value,
                "title": title,
                "app_path": app_path,
                "executable_name": executable_name,
            }
        except Exception as e:
            print(f"获取当前前台应用信息失败: {e}")
            return {}

    def get_frontmost_window_info(self) -> Dict[str, Any]:
        """获取前台窗口标题与矩形区域（用于窗口截图/伴随推荐）。"""
        try:
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd:
                return {}

            pid = ctypes.c_ulong(0)
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            title_buffer = ctypes.create_unicode_buffer(512)
            self._user32.GetWindowTextW(hwnd, title_buffer, 512)
            title = title_buffer.value.strip()

            rect = wintypes.RECT()
            ok = bool(self._user32.GetWindowRect(hwnd, ctypes.byref(rect)))
            if not ok:
                return {
                    "hwnd": int(hwnd),
                    "pid": int(pid.value),
                    "identifier": str(int(pid.value)),
                    "app_name": "",
                    "title": title,
                    "bounds": None,
                }

            x1, y1, x2, y2 = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
            width = max(0, x2 - x1)
            height = max(0, y2 - y1)
            return {
                "hwnd": int(hwnd),
                "pid": int(pid.value),
                "identifier": str(int(pid.value)),
                "app_name": "",
                "title": title,
                "bounds": {
                    "x": x1,
                    "y": y1,
                    "width": width,
                    "height": height,
                },
            }
        except Exception as exc:
            print(f"获取前台窗口信息失败: {exc}")
            return {}

    def activate_app(self, app_info: Dict[str, Any]) -> bool:
        try:
            pid = int(app_info.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        try:
            hwnd_hint = int(app_info.get("hwnd") or 0)
        except (TypeError, ValueError):
            hwnd_hint = 0
        if pid <= 0 and hwnd_hint <= 0:
            return False

        hwnd = self._find_window_by_handle(hwnd_hint, pid=pid)
        if hwnd <= 0 and pid > 0:
            hwnd = self._find_top_level_window_by_pid(pid)
        if hwnd <= 0:
            return False
        if self._is_foreground_match(hwnd, pid):
            return True

        try:
            if self._is_window_minimized(hwnd):
                self._user32.ShowWindow(int(hwnd), SW_RESTORE)
        except Exception:
            pass

        self._bring_window_to_foreground(hwnd)
        if self._is_foreground_match(hwnd, pid):
            return True

        self._bring_window_to_foreground_with_attach(hwnd)
        return self._is_foreground_match(hwnd, pid)
