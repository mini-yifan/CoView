"""
macOS平台适配器

提供macOS平台特定的功能实现。
"""

import os
import plistlib
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt

from baodou_ai.platform.base import PlatformAdapter
from baodou_ai.platform.common import (
    build_browser_target_url,
    is_chrome_family_browser,
    rank_named_candidates,
    score_name_match,
)
from baodou_ai.platform.display_names import get_app_display_override
from baodou_ai.platform.mouse_motion import get_mouse_motion_coordinator


class MacOSAdapter(PlatformAdapter):
    """macOS平台适配器"""

    _MOTION_FRAME_INTERVAL_SECONDS = 1.0 / 60.0

    def __init__(self):
        self._is_app_bundle = self._detect_app_bundle()
        self._is_transparent_mode = False
        self._original_opacity = 0.95
        self._qt_app = None
        self._quartz_module = None
        self._app_catalog_cache: Optional[List[Dict[str, Any]]] = None
        self._app_name_catalog_cache: Optional[List[str]] = None

    def _detect_app_bundle(self) -> bool:
        """检测是否在.app包中运行"""
        executable_path = sys.executable
        if ".app/Contents/MacOS" in executable_path:
            return True

        cwd = os.getcwd()
        if ".app/Contents" in cwd:
            return True

        return False

    def get_resource_path(self, relative_path: str) -> Optional[str]:
        """获取资源文件路径"""
        if os.path.isabs(relative_path):
            return relative_path

        if not self._is_app_bundle:
            if os.path.exists(relative_path):
                return os.path.abspath(relative_path)
            return None

        resource_path = self._get_app_resource_path()
        if not resource_path:
            return None

        resources_dir = (
            resource_path if resource_path.endswith("Resources") else os.path.dirname(resource_path)
        )

        direct_path = os.path.join(resources_dir, relative_path)
        if os.path.exists(direct_path):
            return direct_path

        baodou_ai_path = os.path.join(resources_dir, "baodou_AI", relative_path)
        if os.path.exists(baodou_ai_path):
            return baodou_ai_path

        full_path = os.path.join(resource_path, relative_path)
        if os.path.exists(full_path):
            return full_path

        return None

    def _get_app_resource_path(self) -> Optional[str]:
        """获取.app资源包路径"""
        if not self._is_app_bundle:
            return None

        executable_path = sys.executable
        if ".app/Contents/MacOS" in executable_path:
            base_resource_path = executable_path.replace(
                ".app/Contents/MacOS", ".app/Contents/Resources"
            )

            if os.path.exists(os.path.join(base_resource_path, "config.json")):
                return base_resource_path

            possible_paths = [
                base_resource_path,
                os.path.join(base_resource_path, os.path.basename(executable_path)),
                os.path.join(os.path.dirname(base_resource_path), "Resources"),
            ]

            for path in possible_paths:
                if os.path.exists(os.path.join(path, "config.json")):
                    return path

            return base_resource_path

        cwd = os.getcwd()
        if ".app/Contents" in cwd:
            app_match = re.search(r"(.+\.app)/Contents", cwd)
            if app_match:
                app_path = app_match.group(1)
                base_resource_path = os.path.join(app_path, "Contents", "Resources")

                if os.path.exists(os.path.join(base_resource_path, "config.json")):
                    return base_resource_path

                possible_paths = [
                    base_resource_path,
                    os.path.join(base_resource_path, os.path.basename(cwd)),
                    os.path.join(os.path.dirname(base_resource_path), "Resources"),
                ]

                for path in possible_paths:
                    if os.path.exists(os.path.join(path, "config.json")):
                        return path

                return base_resource_path

        return None

    def setup_window(self, window) -> None:
        """设置窗口属性"""
        window.setWindowOpacity(self._original_opacity)
        print("macOS系统：窗口透明度设置已应用")

    def _get_ns_window(self, window):
        """尽量从 Qt 窗口对象解析出对应的 NSWindow。"""
        from AppKit import NSApplication

        try:
            import objc

            native_view = objc.objc_object(c_void_p=window.winId().__int__())
            if native_view is not None and hasattr(native_view, "window"):
                ns_window = native_view.window()
                if ns_window is not None:
                    return ns_window
        except Exception as e:
            print(f"macOS系统：通过原生句柄获取 NSWindow 失败，回退到标题匹配: {e}")

        app = NSApplication.sharedApplication()
        for ns_window in app.windows():
            if ns_window.title() == window.windowTitle():
                return ns_window

        return None

    def prevent_screenshot(self, window) -> bool:
        """防止窗口被截图"""
        try:
            from AppKit import NSWindowSharingNone

            ns_window = self._get_ns_window(window)
            if ns_window is None:
                print("macOS系统：未找到对应的 NSWindow，暂时无法应用防截屏设置")
                return False

            ns_window.setSharingType_(NSWindowSharingNone)
            if hasattr(ns_window, "disableSnapshotRestoration"):
                ns_window.disableSnapshotRestoration()

            print("macOS系统：窗口已设置为不可被截图")
            return True

        except ImportError:
            print("macOS系统：需要安装pyobjc库才能启用防截图功能")
            return False

        except Exception as e:
            print(f"macOS系统：设置窗口不可被截图时出错: {e}")
            return False

    def allow_screenshot(self, window) -> bool:
        """允许窗口被截图"""
        try:
            from AppKit import NSWindowSharingReadOnly

            ns_window = self._get_ns_window(window)
            if ns_window is None:
                print("macOS系统：未找到对应的 NSWindow，暂时无法恢复截屏设置")
                return False

            ns_window.setSharingType_(NSWindowSharingReadOnly)

            print("macOS系统：窗口已恢复可被截图")
            return True

        except ImportError:
            print("macOS系统：需要安装pyobjc库才能恢复截图功能")
            return False

        except Exception as e:
            print(f"macOS系统：恢复窗口截图时出错: {e}")
            return False

    def translate_hotkey_keys(self, keys: List[str]) -> List[str]:
        """翻译快捷键"""
        translated = []
        for key in keys:
            if key in ("win", "meta", "cmd"):
                translated.append("command")
            elif key == "ctrl":
                translated.append("control")
            elif key == "alt":
                translated.append("option")
            else:
                translated.append(key)
        return translated

    def get_hotkey_modifier(self) -> str:
        """获取快捷键修饰符"""
        return "command"

    def is_app_bundle(self) -> bool:
        """检测是否在打包的应用程序中运行"""
        return self._is_app_bundle

    def enter_transparent_mode(self, window) -> bool:
        """
        进入透明穿透模式

        窗口变为完全透明且鼠标可穿透
        """
        try:
            window.setWindowOpacity(0.0)
            window.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            ns_window = self._get_ns_window(window)
            if ns_window is not None:
                ns_window.setIgnoresMouseEvents_(True)
                ns_window.setAlphaValue_(0.0)
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
            window.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            window.setWindowOpacity(self._original_opacity)
            ns_window = self._get_ns_window(window)
            if ns_window is not None:
                ns_window.setIgnoresMouseEvents_(False)
                ns_window.setAlphaValue_(self._original_opacity)
            self._is_transparent_mode = False
            print("窗口已退出透明穿透模式")
            return True
        except Exception as e:
            print(f"退出透明穿透模式时出错: {e}")
            return False

    def _ensure_qt_app(self):
        """确保 Qt 应用实例存在。"""
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication([])
            self._qt_app = app
        return app

    def _get_qt_screen_infos(self) -> List[Dict[str, Any]]:
        """获取按主屏优先排序的 Qt 逻辑屏幕信息。"""
        try:
            from PyQt5.QtWidgets import QApplication

            app = self._ensure_qt_app()
            screens = list(app.screens()) or list(QApplication.screens())
            if not screens:
                return []

            primary_screen = app.primaryScreen() or QApplication.primaryScreen()
            sorted_screens = sorted(
                screens,
                key=lambda screen: (
                    0 if screen == primary_screen else 1,
                    int(screen.geometry().x()),
                    int(screen.geometry().y()),
                ),
            )

            return [
                {
                    "index": index,
                    "x": int(screen.geometry().x()),
                    "y": int(screen.geometry().y()),
                    "width": int(screen.geometry().width()),
                    "height": int(screen.geometry().height()),
                    "is_primary": screen == primary_screen,
                }
                for index, screen in enumerate(sorted_screens)
            ]
        except Exception as e:
            print(f"获取 Qt 屏幕信息时出错: {e}")
            return []

    def _get_sorted_nsscreen_metrics(self) -> List[Dict[str, Any]]:
        """获取按主屏优先排序的 NSScreen 元信息。"""
        try:
            from AppKit import NSScreen

            screens = list(NSScreen.screens())
            main_screen = NSScreen.mainScreen()
            sorted_screens = sorted(
                screens,
                key=lambda screen: (
                    0 if screen == main_screen else 1,
                    int(screen.frame().origin.x),
                    int(screen.frame().origin.y),
                ),
            )

            metrics: List[Dict[str, Any]] = []
            for screen in sorted_screens:
                frame = screen.frame()
                metrics.append(
                    {
                        "x": int(frame.origin.x),
                        "y": int(frame.origin.y),
                        "width": int(frame.size.width),
                        "height": int(frame.size.height),
                        "scale": (
                            float(screen.backingScaleFactor())
                            if hasattr(screen, "backingScaleFactor")
                            else 1.0
                        ),
                        "is_primary": screen == main_screen,
                    }
                )
            return metrics
        except Exception as e:
            print(f"获取 NSScreen 元信息时出错: {e}")
            return []

    def _get_quartz_module(self):
        """延迟加载 Quartz，缺失时抛出清晰错误。"""
        if self._quartz_module is not None:
            return self._quartz_module

        try:
            import Quartz
        except ImportError as exc:
            raise RuntimeError("macOS 多屏控制需要安装 pyobjc/Quartz，当前环境未提供。") from exc

        self._quartz_module = Quartz
        return self._quartz_module

    @staticmethod
    def _build_launch_result(
        matched: bool,
        app_name: str = "",
        app_path: str = "",
        suggestions: Optional[List[str]] = None,
        error: str = "",
        fallback: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "matched": matched,
            "app_name": app_name,
            "app_path": app_path,
            "suggestions": suggestions or [],
            "error": error,
            "fallback": fallback,
        }

    def _iter_macos_application_paths(self) -> List[str]:
        roots = [
            "/Applications",
            os.path.expanduser("~/Applications"),
            "/Applications/Utilities",
            "/System/Applications",
            "/System/Applications/Utilities",
            "/System/Library/CoreServices",
        ]
        result: List[str] = []
        seen = set()
        for root in roots:
            if not os.path.isdir(root):
                continue
            for current_root, dirnames, _files in os.walk(root):
                app_dirs = [name for name in dirnames if name.endswith(".app")]
                for app_dir in app_dirs:
                    app_path = os.path.join(current_root, app_dir)
                    if app_path not in seen:
                        seen.add(app_path)
                        result.append(app_path)
                dirnames[:] = [name for name in dirnames if not name.endswith(".app")]
        return result

    def _get_app_metadata(
        self, app_path: str, apply_display_override: bool = True
    ) -> Dict[str, Any]:
        app_name = os.path.splitext(os.path.basename(app_path))[0]
        display_name = app_name
        bundle_id = ""
        aliases = {app_name}

        try:
            from AppKit import NSBundle, NSFileManager

            display_name_at_path = NSFileManager.defaultManager().displayNameAtPath_(app_path)
            if display_name_at_path:
                display_name = str(display_name_at_path).strip() or display_name
                aliases.add(display_name)

            bundle = NSBundle.bundleWithPath_(app_path)
            info = bundle.infoDictionary() if bundle else {}
            for key in (
                "CFBundleDisplayName",
                "CFBundleName",
                "CFBundleExecutable",
                "CFBundleIdentifier",
            ):
                value = info.get(key) if info else None
                if value:
                    value_text = str(value).strip()
                    aliases.add(value_text)
                    if key == "CFBundleIdentifier":
                        bundle_id = value_text
        except Exception:
            pass

        if apply_display_override:
            override = get_app_display_override(bundle_id)
            if override:
                override_display_name = str(override.get("display_name") or "").strip()
                if override_display_name:
                    display_name = override_display_name
                    aliases.add(override_display_name)
                aliases.update(
                    str(alias).strip()
                    for alias in override.get("aliases", [])
                    if str(alias).strip()
                )

        return {
            "name": app_name,
            "display_name": display_name,
            "bundle_id": bundle_id,
            "path": app_path,
            "aliases": sorted(alias for alias in aliases if alias),
        }

    def _list_available_apps(self) -> List[Dict[str, Any]]:
        if self._app_catalog_cache is not None:
            return self._app_catalog_cache

        catalog: List[Dict[str, Any]] = []
        for app_path in self._iter_macos_application_paths():
            catalog.append(self._get_app_metadata(app_path))

        self._app_catalog_cache = catalog
        return catalog

    def list_installed_app_names(self) -> List[str]:
        if self._app_name_catalog_cache is not None:
            return list(self._app_name_catalog_cache)

        names: List[str] = []
        seen = set()
        for app_path in self._iter_macos_application_paths():
            metadata = self._get_app_metadata(app_path, apply_display_override=False)
            app_name = str(metadata.get("display_name") or metadata.get("name") or "").strip()
            if not app_name:
                continue
            normalized_name = app_name.casefold()
            if normalized_name in seen:
                continue
            seen.add(normalized_name)
            names.append(app_name)

        names.sort(key=str.casefold)
        self._app_name_catalog_cache = list(names)
        return list(names)

    def _find_app_match(self, app_name: str) -> Dict[str, Any]:
        apps = self._list_available_apps()
        if not apps:
            return self._build_launch_result(
                matched=False,
                error=(
                    f"系统级启动未找到名为“{app_name}”的应用。"
                    f"请调用 open_app_launcher 打开启动台，并在其中搜索“{app_name}”尝试启动。"
                ),
                fallback={
                    "type": "app_launcher_search",
                    "app_name": str(app_name).strip(),
                },
            )

        exact_matches = [
            candidate
            for candidate in apps
            if score_name_match(
                app_name,
                candidate.get("display_name") or candidate["name"],
                candidate.get("aliases"),
            )
            >= 1.0
        ]
        if exact_matches:
            best = exact_matches[0]
            return self._build_launch_result(
                matched=True,
                app_name=best.get("display_name") or best["name"],
                app_path=best["path"],
            )

        ranked = rank_named_candidates(app_name, apps, max_results=3, cutoff=0.72)
        if ranked:
            top_candidate = ranked[0]
            top_score = float(top_candidate.get("score", 0.0))
            second_score = float(ranked[1].get("score", 0.0)) if len(ranked) > 1 else 0.0
            # Require a higher confidence before auto-launching, otherwise return suggestions
            # and prompt the agent to use Launchpad search (open_app_launcher).
            if top_score >= 0.96 and (len(ranked) == 1 or (top_score - second_score) >= 0.08):
                return self._build_launch_result(
                    matched=True,
                    app_name=top_candidate.get("display_name") or top_candidate["name"],
                    app_path=top_candidate["path"],
                )
            suggestions = [
                candidate.get("display_name") or candidate["name"] for candidate in ranked
            ]
            return self._build_launch_result(
                matched=False,
                suggestions=suggestions,
                error=(
                    f"系统级启动未找到名为“{app_name}”的应用。"
                    f"如果这些候选都不是目标应用，请调用 open_app_launcher 打开启动台，"
                    f"并在其中搜索“{app_name}”尝试启动。候选名称：{'、'.join(suggestions)}。"
                ),
                fallback={
                    "type": "app_launcher_search",
                    "app_name": str(app_name).strip(),
                },
            )

        return self._build_launch_result(
            matched=False,
            error=(
                f"系统级启动未找到名为“{app_name}”的应用。"
                f"请调用 open_app_launcher 打开启动台，并在其中搜索“{app_name}”尝试启动。"
            ),
            fallback={
                "type": "app_launcher_search",
                "app_name": str(app_name).strip(),
            },
        )

    def launch_app(self, app_name: str) -> Dict[str, Any]:
        match = self._find_app_match(app_name)
        if not match.get("matched"):
            return match

        app_path = str(match.get("app_path") or "").strip()
        if not app_path:
            raise RuntimeError("命中的应用缺少可启动路径。")

        subprocess.run(["open", app_path], check=True)
        return match

    def open_app_launcher(self) -> Dict[str, Any]:
        launchpad_commands = [
            ["open", "-b", "com.apple.apps.launcher"],
            ["open", "-b", "com.apple.launchpad.launcher"],
            ["open", "-a", "Launchpad"],
        ]
        last_error: Optional[subprocess.CalledProcessError] = None
        for command in launchpad_commands:
            try:
                subprocess.run(command, check=True)
                return {
                    "app_names": self.list_installed_app_names(),
                }
            except subprocess.CalledProcessError as exc:
                last_error = exc

        raise RuntimeError(f"打开应用启动器失败: {last_error}") from last_error

    def open_in_finder(self, path: Optional[str] = None) -> Dict[str, Any]:
        if path is None:
            target_path = str(Path.home() / "Desktop")
            script = (
                'tell application "Finder"\n'
                "    activate\n"
                f'    open POSIX file "{target_path}"\n'
                "end tell\n"
            )
            subprocess.run(["osascript", "-e", script], check=True)
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
            script = (
                'tell application "Finder"\n'
                "    activate\n"
                f'    reveal POSIX file "{resolved}"\n'
                "end tell\n"
            )
            subprocess.run(["osascript", "-e", script], check=True)
            return {
                "target_path": str(resolved.parent),
                "revealed_file": str(resolved),
            }

        script = (
            'tell application "Finder"\n'
            "    activate\n"
            f'    open POSIX file "{resolved}"\n'
            "end tell\n"
        )
        subprocess.run(["osascript", "-e", script], check=True)
        return {
            "target_path": str(resolved),
            "revealed_file": None,
        }

    _DOCUMENT_APP_SCRIPTS: Dict[str, str] = {
        "Microsoft Word": (
            'tell application "Microsoft Word"\n'
            "    try\n"
            "        set docPath to full name of active document\n"
            "        return docPath\n"
            "    on error\n"
            '        return ""\n'
            "    end try\n"
            "end tell\n"
        ),
        "Microsoft Excel": (
            'tell application "Microsoft Excel"\n'
            "    try\n"
            "        set docPath to full name of active workbook\n"
            "        return docPath\n"
            "    on error\n"
            '        return ""\n'
            "    end try\n"
            "end tell\n"
        ),
        "Microsoft PowerPoint": (
            'tell application "Microsoft PowerPoint"\n'
            "    try\n"
            "        set docPath to full name of active presentation\n"
            "        return docPath\n"
            "    on error\n"
            '        return ""\n'
            "    end try\n"
            "end tell\n"
        ),
        "WPS": (
            'tell application "wpsoffice"\n'
            "    try\n"
            "        set docPath to full name of active document\n"
            "        return docPath\n"
            "    on error\n"
            '        return ""\n'
            "    end try\n"
            "end tell\n"
        ),
        "Finder": (
            'tell application "Finder"\n'
            "    try\n"
            "        set currentFolder to target of front window as alias\n"
            "        return POSIX path of currentFolder\n"
            "    on error\n"
            '        return ""\n'
            "    end try\n"
            "end tell\n"
        ),
        "访达": (
            'tell application "Finder"\n'
            "    try\n"
            "        set currentFolder to target of front window as alias\n"
            "        return POSIX path of currentFolder\n"
            "    on error\n"
            '        return ""\n'
            "    end try\n"
            "end tell\n"
        ),
    }

    def get_active_document_path(self, app_name: str) -> Optional[str]:
        script = self._DOCUMENT_APP_SCRIPTS.get(app_name)
        if script is None:
            return None

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=2,
            )
            raw = result.stdout.strip()
            if not raw:
                return ""

            if ":" in raw and not raw.startswith("/"):
                script_convert = f'return POSIX path of POSIX file "{raw}"'
                try:
                    convert_result = subprocess.run(
                        ["osascript", "-e", script_convert],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    converted = convert_result.stdout.strip()
                    if converted and converted.startswith("/"):
                        return converted
                except Exception:
                    pass

            if raw.startswith("/"):
                return raw

            return raw
        except Exception:
            return None

    def move_to_trash(self, path: str) -> Dict[str, Any]:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            return {"ok": False, "error": f"路径不存在: {resolved}"}

        script = 'tell application "Finder"\n' f'    delete POSIX file "{resolved}"\n' "end tell\n"
        try:
            subprocess.run(["osascript", "-e", script], check=True, timeout=5)
            return {"ok": True, "error": None}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "操作超时"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_default_browser_info(self) -> Dict[str, Any]:
        bundle_id = self._copy_default_browser_bundle_id()
        if not bundle_id:
            bundle_id = self._read_default_browser_bundle_id_from_preferences()

        app_path = ""
        app_name = ""

        if bundle_id:
            app_path = self._resolve_app_path_for_bundle_id(bundle_id)

        if app_path:
            app_name = os.path.splitext(os.path.basename(app_path))[0]
        elif bundle_id:
            app_name = bundle_id.split(".")[-1]

        return {
            "app_name": app_name,
            "identifier": bundle_id,
            "app_path": app_path,
            "is_chrome_family": is_chrome_family_browser(bundle_id, app_name, app_path),
        }

    @staticmethod
    def _copy_default_browser_bundle_id() -> str:
        try:
            from CoreServices import LSCopyDefaultHandlerForURLScheme

            return str(LSCopyDefaultHandlerForURLScheme("https") or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _read_default_browser_bundle_id_from_preferences() -> str:
        launchservices_path = (
            Path.home()
            / "Library"
            / "Preferences"
            / "com.apple.LaunchServices"
            / "com.apple.launchservices.secure.plist"
        )
        try:
            with launchservices_path.open("rb") as handle:
                data = plistlib.load(handle)
        except Exception:
            return ""

        handlers = data.get("LSHandlers") if isinstance(data, dict) else None
        if not isinstance(handlers, list):
            return ""

        def pick_bundle_id(key: str, value: str) -> str:
            matches = [
                item
                for item in handlers
                if isinstance(item, dict)
                and item.get(key) == value
                and str(item.get("LSHandlerRoleAll") or "").strip()
            ]
            if not matches:
                return ""

            matches.sort(
                key=lambda item: int(item.get("LSHandlerModificationDate") or 0),
                reverse=True,
            )
            return str(matches[0].get("LSHandlerRoleAll") or "").strip()

        for key, value in (
            ("LSHandlerURLScheme", "https"),
            ("LSHandlerURLScheme", "http"),
            ("LSHandlerContentType", "com.apple.default-app.web-browser"),
            ("LSHandlerContentType", "public.html"),
        ):
            bundle_id = pick_bundle_id(key, value)
            if bundle_id:
                return bundle_id
        return ""

    @staticmethod
    def _resolve_app_path_for_bundle_id(bundle_id: str) -> str:
        try:
            from AppKit import NSWorkspace

            workspace = NSWorkspace.sharedWorkspace()
            if hasattr(workspace, "URLForApplicationWithBundleIdentifier_"):
                app_url = workspace.URLForApplicationWithBundleIdentifier_(bundle_id)
                if app_url is not None:
                    if hasattr(app_url, "path"):
                        return str(app_url.path() or "").strip()
                    if hasattr(app_url, "fileSystemRepresentation"):
                        return str(app_url.fileSystemRepresentation() or "").strip()
        except Exception:
            return ""
        return ""

    def open_in_browser(
        self, url: Optional[str] = None, query: Optional[str] = None
    ) -> Dict[str, Any]:
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

        subprocess.run(["open", target_url], check=True)
        return {
            "browser": browser_info,
            "target_url": target_url,
        }

    def get_frontmost_app_info(self) -> Dict[str, Any]:
        try:
            from AppKit import NSWorkspace

            workspace = NSWorkspace.sharedWorkspace()
            app = workspace.frontmostApplication()
            if app is None:
                return {}

            app_name = str(app.localizedName() or "").strip()
            bundle_id = str(app.bundleIdentifier() or "").strip()
            pid = 0
            if hasattr(app, "processIdentifier"):
                try:
                    pid = int(app.processIdentifier())
                except Exception:
                    pid = 0

            return {
                "app_name": app_name,
                "bundle_id": bundle_id,
                "identifier": bundle_id or app_name,
                "pid": pid,
            }
        except Exception as e:
            print(f"获取当前前台应用信息失败: {e}")
            return {}

    def get_frontmost_window_info(self) -> Dict[str, Any]:
        """获取前台窗口标题与矩形区域（用于窗口截图/伴随推荐）。"""
        frontmost = self.get_frontmost_app_info() or {}
        pid = 0
        try:
            pid = int(frontmost.get("pid") or 0)
        except Exception:
            pid = 0

        app_name = str(frontmost.get("app_name") or "").strip()
        bundle_id = str(frontmost.get("bundle_id") or frontmost.get("identifier") or "").strip()

        if pid <= 0:
            return {}

        try:
            Quartz = self._get_quartz_module()

            # On macOS, CGWindowListCopyWindowInfo requires screen recording permission in many environments.
            options = int(getattr(Quartz, "kCGWindowListOptionOnScreenOnly", 1))
            window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
            best_window = None
            best_area = -1
            for window in window_list:
                try:
                    owner_pid = int(window.get("kCGWindowOwnerPID") or 0)
                except Exception:
                    continue
                if owner_pid != pid:
                    continue
                # Filter out non-app layers (menus, overlays). Normal windows typically have layer 0.
                try:
                    layer = int(window.get("kCGWindowLayer") or 0)
                except Exception:
                    layer = 0
                if layer != 0:
                    continue
                bounds = window.get("kCGWindowBounds") or {}
                try:
                    width = float(bounds.get("Width") or 0)
                    height = float(bounds.get("Height") or 0)
                except Exception:
                    width = 0.0
                    height = 0.0
                area = width * height
                if area > best_area:
                    best_area = area
                    best_window = window

            if not best_window:
                return {
                    "pid": pid,
                    "app_name": app_name,
                    "bundle_id": bundle_id,
                    "identifier": bundle_id or app_name,
                    "title": "",
                    "bounds": None,
                }

            title = str(best_window.get("kCGWindowName") or "").strip()
            bounds = best_window.get("kCGWindowBounds") or {}
            x = int(float(bounds.get("X") or 0))
            y = int(float(bounds.get("Y") or 0))
            w = int(float(bounds.get("Width") or 0))
            h = int(float(bounds.get("Height") or 0))

            return {
                "pid": pid,
                "app_name": app_name,
                "bundle_id": bundle_id,
                "identifier": bundle_id or app_name,
                "title": title,
                "bounds": {"x": x, "y": y, "width": w, "height": h},
            }
        except Exception as exc:
            print(f"获取前台窗口信息失败: {exc}")
            return {
                "pid": pid,
                "app_name": app_name,
                "bundle_id": bundle_id,
                "identifier": bundle_id or app_name,
                "title": "",
                "bounds": None,
            }

    def activate_app(self, app_info: Dict[str, Any]) -> bool:
        try:
            from AppKit import NSRunningApplication, NSWorkspace

            pid = 0
            try:
                pid = int(app_info.get("pid") or 0)
            except (TypeError, ValueError):
                pid = 0

            running_app = None
            if pid > 0:
                running_app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)

            if running_app is None:
                bundle_id = str(
                    app_info.get("bundle_id") or app_info.get("identifier") or ""
                ).strip()
                app_name = str(app_info.get("app_name") or "").strip()
                workspace = NSWorkspace.sharedWorkspace()
                running_apps = list(workspace.runningApplications() or [])
                for candidate in running_apps:
                    candidate_bundle_id = str(candidate.bundleIdentifier() or "").strip()
                    candidate_name = str(candidate.localizedName() or "").strip()
                    if bundle_id and candidate_bundle_id == bundle_id:
                        running_app = candidate
                        break
                    if app_name and candidate_name == app_name:
                        running_app = candidate
                        break

            if running_app is None:
                return False

            if hasattr(running_app, "isHidden") and bool(running_app.isHidden()):
                return False

            activated = bool(running_app.activateWithOptions_(0))
            if not activated and hasattr(running_app, "activateWithOptions_"):
                activated = bool(running_app.activateWithOptions_(1))
            return activated
        except Exception as e:
            print(f"激活应用失败: {e}")
            return False

        return False

    @staticmethod
    def _make_point(x: float, y: float) -> Tuple[float, float]:
        """构建 Quartz CGPoint 兼容坐标。"""
        return (float(x), float(y))

    def _get_cursor_position(self) -> Tuple[float, float]:
        """获取当前鼠标位置。"""
        quartz = self._get_quartz_module()
        event = quartz.CGEventCreate(None)
        if event is None:
            return (0.0, 0.0)

        location = quartz.CGEventGetLocation(event)
        if hasattr(location, "x") and hasattr(location, "y"):
            return (float(location.x), float(location.y))
        return (float(location[0]), float(location[1]))

    def _get_button_events(self, button: str):
        """解析鼠标按键和事件类型。"""
        quartz = self._get_quartz_module()
        normalized = (button or "left").lower()
        if normalized == "right":
            return (
                quartz.kCGMouseButtonRight,
                quartz.kCGEventRightMouseDown,
                quartz.kCGEventRightMouseUp,
                quartz.kCGEventRightMouseDragged,
            )
        return (
            quartz.kCGMouseButtonLeft,
            quartz.kCGEventLeftMouseDown,
            quartz.kCGEventLeftMouseUp,
            quartz.kCGEventLeftMouseDragged,
        )

    def is_accessibility_trusted(self, *, prompt: bool = False) -> bool:
        """Return whether macOS trusts this process for accessibility input events."""
        try:
            quartz = self._get_quartz_module()
            checker = getattr(quartz, "AXIsProcessTrustedWithOptions", None)
            if checker is None:
                return True
            prompt_key = getattr(
                quartz, "kAXTrustedCheckOptionPrompt", "AXTrustedCheckOptionPrompt"
            )
            return bool(checker({prompt_key: bool(prompt)}))
        except Exception as exc:
            print(f"检查 macOS 辅助功能权限失败: {exc}")
            return True

    def _ensure_accessibility_trusted(self) -> None:
        """Raise a clear error when HID event posting is not allowed by macOS."""
        if self.is_accessibility_trusted(prompt=True):
            return
        raise RuntimeError(
            "CoView 尚未获得 macOS 辅助功能权限，鼠标点击和键盘输入会被系统拦截。"
            "请打开 系统设置 > 隐私与安全性 > 辅助功能，移除旧的 CoView 条目后重新添加当前 CoView.app，"
            "然后完全退出并重新打开 CoView。"
        )

    def _post_mouse_event(
        self,
        event_type,
        x: float,
        y: float,
        cg_button,
        click_state: Optional[int] = None,
    ) -> None:
        """发送一条 Quartz 鼠标事件。"""
        self._ensure_accessibility_trusted()
        quartz = self._get_quartz_module()
        event = quartz.CGEventCreateMouseEvent(
            None,
            event_type,
            self._make_point(x, y),
            cg_button,
        )
        if event is None:
            raise RuntimeError("无法创建 macOS 鼠标事件，请确认已授予辅助功能权限。")
        if click_state is not None:
            quartz.CGEventSetIntegerValueField(
                event,
                quartz.kCGMouseEventClickState,
                click_state,
            )
        quartz.CGEventPost(quartz.kCGHIDEventTap, event)

    @staticmethod
    def _build_motion_points(
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        duration: float,
    ) -> List[Tuple[float, float]]:
        """按时长构造平滑移动路径。"""
        if duration <= 0:
            return [(end_x, end_y)]

        steps = max(min(int(duration / 0.01), 120), 1)
        return [
            (
                start_x + (end_x - start_x) * (index / steps),
                start_y + (end_y - start_y) * (index / steps),
            )
            for index in range(1, steps + 1)
        ]

    @staticmethod
    def _ease_in_out_quad(progress: float) -> float:
        """Return an ease-in-out progress value in [0, 1]."""
        normalized = min(max(float(progress), 0.0), 1.0)
        if normalized < 0.5:
            return 2.0 * normalized * normalized
        return 1.0 - ((-2.0 * normalized + 2.0) ** 2) / 2.0

    def _perform_motion(
        self, x: float, y: float, duration: float, event_type, button: str = "left"
    ) -> None:
        """执行平滑移动或拖拽。"""
        quartz = self._get_quartz_module()
        cg_button, _, _, _ = self._get_button_events(button)
        coordinator = get_mouse_motion_coordinator()
        token = coordinator.begin_motion()
        start_x, start_y = self._get_cursor_position()
        try:
            coordinator.check_active(token)
            if duration <= 0:
                quartz.CGWarpMouseCursorPosition(self._make_point(x, y))
                self._post_mouse_event(event_type, x, y, cg_button)
                return

            start_time = time.monotonic()
            deadline = start_time + float(duration)
            last_point: Optional[Tuple[float, float]] = None

            while True:
                coordinator.check_active(token)
                now = time.monotonic()
                progress = min(max((now - start_time) / float(duration), 0.0), 1.0)
                eased = self._ease_in_out_quad(progress)
                point_x = start_x + (x - start_x) * eased
                point_y = start_y + (y - start_y) * eased

                if last_point != (point_x, point_y):
                    coordinator.check_active(token)
                    quartz.CGWarpMouseCursorPosition(self._make_point(point_x, point_y))
                    self._post_mouse_event(event_type, point_x, point_y, cg_button)
                    last_point = (point_x, point_y)

                if progress >= 1.0:
                    break

                next_frame = min(
                    now + self._MOTION_FRAME_INTERVAL_SECONDS,
                    deadline,
                )
                coordinator.wait_active(token, max(next_frame - time.monotonic(), 0.0))

            coordinator.check_active(token)
            if last_point != (float(x), float(y)):
                quartz.CGWarpMouseCursorPosition(self._make_point(x, y))
                self._post_mouse_event(event_type, x, y, cg_button)
        finally:
            coordinator.end_motion(token)

    def move_cursor(self, x: float, y: float, duration: float = 0.0) -> None:
        """移动鼠标到指定全局坐标。"""
        quartz = self._get_quartz_module()
        self._perform_motion(x, y, duration, quartz.kCGEventMouseMoved)

    def click(self, button: str = "left", clicks: int = 1) -> None:
        """在当前位置执行点击。"""
        cg_button, down_event, up_event, _ = self._get_button_events(button)
        x, y = self._get_cursor_position()
        for index in range(max(clicks, 1)):
            click_state = index + 1 if clicks > 1 else None
            self._post_mouse_event(down_event, x, y, cg_button, click_state=click_state)
            self._post_mouse_event(up_event, x, y, cg_button, click_state=click_state)
            if index < clicks - 1:
                time.sleep(0.05)

    def mouse_down(self, button: str = "left") -> None:
        """按下鼠标按键。"""
        cg_button, down_event, _, _ = self._get_button_events(button)
        x, y = self._get_cursor_position()
        self._post_mouse_event(down_event, x, y, cg_button)

    def mouse_up(self, button: str = "left") -> None:
        """释放鼠标按键。"""
        cg_button, _, up_event, _ = self._get_button_events(button)
        x, y = self._get_cursor_position()
        self._post_mouse_event(up_event, x, y, cg_button)

    def drag_to(self, x: float, y: float, duration: float = 0.0, button: str = "left") -> None:
        """从当前位置拖拽到指定全局坐标。"""
        quartz = self._get_quartz_module()
        cg_button, down_event, up_event, dragged_event = self._get_button_events(button)
        start_x, start_y = self._get_cursor_position()
        self._post_mouse_event(down_event, start_x, start_y, cg_button)
        try:
            self._perform_motion(x, y, duration, dragged_event, button=button)
        finally:
            release_x, release_y = self._get_cursor_position()
            self._post_mouse_event(up_event, release_x, release_y, cg_button)

    def scroll(self, amount: int) -> None:
        """在当前位置执行滚轮操作。"""
        self._ensure_accessibility_trusted()
        quartz = self._get_quartz_module()
        event = quartz.CGEventCreateScrollWheelEvent(
            None,
            quartz.kCGScrollEventUnitLine,
            1,
            int(amount),
        )
        if event is None:
            raise RuntimeError("无法创建 macOS 滚轮事件，请确认已授予辅助功能权限。")
        quartz.CGEventPost(quartz.kCGHIDEventTap, event)

    def key_down(self, key: str) -> None:
        """按下键盘按键。"""
        self._ensure_accessibility_trusted()
        import pyautogui

        pyautogui.keyDown(key)

    def key_up(self, key: str) -> None:
        """释放键盘按键。"""
        self._ensure_accessibility_trusted()
        import pyautogui

        pyautogui.keyUp(key)

    def key_press(self, key: str) -> None:
        """按下并释放键盘按键。"""
        self._ensure_accessibility_trusted()
        import pyautogui

        pyautogui.press(key)

    def get_scaling_factor(self) -> float:
        """
        获取屏幕缩放因子（Retina缩放）

        在 macOS Retina 屏幕上，物理分辨率是逻辑分辨率的 2 倍。

        Returns:
            缩放因子，例如 Retina 屏幕返回 2.0，普通屏幕返回 1.0
        """
        try:
            from AppKit import NSScreen

            screen = NSScreen.mainScreen()
            if screen:
                return float(screen.backingScaleFactor())
        except Exception as e:
            print(f"获取缩放因子时出错: {e}")

        return 1.0

    def get_logical_screen_size(self) -> tuple:
        """
        获取逻辑屏幕尺寸

        逻辑尺寸是 pyautogui 鼠标操作使用的坐标系统。
        在 macOS 上，这通常小于物理分辨率（Retina 屏幕的情况）。

        Returns:
            (width, height) 逻辑屏幕尺寸
        """
        qt_screens = self._get_qt_screen_infos()
        if qt_screens:
            primary = qt_screens[0]
            return (int(primary["width"]), int(primary["height"]))

        try:
            from AppKit import NSScreen

            screen = NSScreen.mainScreen()
            if screen:
                frame = screen.frame()
                return (int(frame.size.width), int(frame.size.height))
        except Exception as e:
            print(f"获取逻辑屏幕尺寸时出错: {e}")

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
            from AppKit import NSScreen

            return len(NSScreen.screens())
        except Exception as e:
            print(f"获取屏幕数量时出错: {e}")
            return 1

    def get_all_screens_info(self) -> List[Dict[str, Any]]:
        """
        获取所有屏幕信息

        Returns:
            屏幕信息列表
        """
        qt_screens = self._get_qt_screen_infos()
        if qt_screens:
            return qt_screens

        try:
            from AppKit import NSScreen

            screens = NSScreen.screens()
            main_screen = NSScreen.mainScreen()
            result = []

            for i, screen in enumerate(screens):
                frame = screen.frame()
                is_primary = screen == main_screen

                result.append(
                    {
                        "index": i,
                        "x": int(frame.origin.x),
                        "y": int(frame.origin.y),
                        "width": int(frame.size.width),
                        "height": int(frame.size.height),
                        "is_primary": is_primary,
                    }
                )

            return result
        except Exception as e:
            print(f"获取所有屏幕信息时出错: {e}")
            return [{"index": 0, "x": 0, "y": 0, "width": 1920, "height": 1080, "is_primary": True}]

    def get_capture_screens_info(self) -> List[Dict[str, Any]]:
        """获取用于截图的屏幕信息。"""
        qt_screens = self._get_qt_screen_infos()
        nss_metrics = self._get_sorted_nsscreen_metrics()
        if qt_screens:
            capture_screens: List[Dict[str, Any]] = []
            for index, qt_screen in enumerate(qt_screens):
                nss_screen = nss_metrics[index] if index < len(nss_metrics) else {}
                scale = float(nss_screen.get("scale", 1.0))
                capture_screens.append(
                    {
                        "index": index,
                        "is_primary": bool(qt_screen.get("is_primary")),
                        "logical_x": int(qt_screen.get("x", 0)),
                        "logical_y": int(qt_screen.get("y", 0)),
                        "logical_width": int(qt_screen.get("width", 0)),
                        "logical_height": int(qt_screen.get("height", 0)),
                        "capture_x": int(round(qt_screen.get("x", 0) * scale)),
                        "capture_y": int(round(qt_screen.get("y", 0) * scale)),
                        "capture_width": int(round(qt_screen.get("width", 0) * scale)),
                        "capture_height": int(round(qt_screen.get("height", 0) * scale)),
                    }
                )
            return capture_screens

        try:
            from AppKit import NSScreen

            screens = list(NSScreen.screens())
            main_screen = NSScreen.mainScreen()
            sorted_screens = sorted(
                screens,
                key=lambda screen: (
                    0 if screen == main_screen else 1,
                    int(screen.frame().origin.x),
                    int(screen.frame().origin.y),
                ),
            )

            capture_screens: List[Dict[str, Any]] = []
            for index, screen in enumerate(sorted_screens):
                frame = screen.frame()
                scale = (
                    float(screen.backingScaleFactor())
                    if hasattr(screen, "backingScaleFactor")
                    else 1.0
                )
                logical_x = int(frame.origin.x)
                logical_y = int(frame.origin.y)
                logical_width = int(frame.size.width)
                logical_height = int(frame.size.height)
                capture_screens.append(
                    {
                        "index": index,
                        "is_primary": screen == main_screen,
                        "logical_x": logical_x,
                        "logical_y": logical_y,
                        "logical_width": logical_width,
                        "logical_height": logical_height,
                        "capture_x": int(round(logical_x * scale)),
                        "capture_y": int(round(logical_y * scale)),
                        "capture_width": int(round(logical_width * scale)),
                        "capture_height": int(round(logical_height * scale)),
                    }
                )

            return capture_screens
        except Exception as e:
            print(f"获取截图屏幕信息时出错: {e}")
            screens = self.get_all_screens_info()
            return [
                {
                    "index": index,
                    "is_primary": bool(screen.get("is_primary")),
                    "logical_x": int(screen.get("x", 0)),
                    "logical_y": int(screen.get("y", 0)),
                    "logical_width": int(screen.get("width", 0)),
                    "logical_height": int(screen.get("height", 0)),
                    "capture_x": int(screen.get("x", 0)),
                    "capture_y": int(screen.get("y", 0)),
                    "capture_width": int(screen.get("width", 0)),
                    "capture_height": int(screen.get("height", 0)),
                }
                for index, screen in enumerate(screens)
            ]

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
            return (info["x"], info["y"], info["width"], info["height"])
        return (0, 0, 1920, 1080)
