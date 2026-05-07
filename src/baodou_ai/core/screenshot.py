"""
截图功能模块

提供屏幕截图、图片优化和保存功能。
"""

import base64
import hashlib
import os
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pyautogui
from PyQt5.QtCore import QRect
from PyQt5.QtGui import QScreen
from PyQt5.QtWidgets import QApplication

from baodou_ai.core.config import Config
from baodou_ai.core.error_envelope import (
    CODE_CAPTURE_FAILED,
    KIND_BACKEND_FALLBACK,
    KIND_EXECUTION_FAILED,
    SOURCE_CAPTURE,
    from_exception,
    from_message,
)
from baodou_ai.platform import get_platform_adapter

CAPTURE_EXCLUDE_PROPERTY = "baodou_exclude_from_ai_capture"


@dataclass
class ScreenCaptureBundle:
    """正式截图在内存中的打包结果。"""

    index: int
    x: int
    y: int
    width: int
    height: int
    logical_width: int
    logical_height: int
    is_primary: bool
    png_bytes: bytes
    data_url: str
    frame_hash: str
    path: Optional[str] = None


@dataclass(frozen=True)
class CaptureTarget:
    """多屏截图的统一真相模型。"""

    index: int
    is_primary: bool
    logical_x: int
    logical_y: int
    logical_width: int
    logical_height: int
    capture_x: int
    capture_y: int
    capture_width: int
    capture_height: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CaptureTarget":
        """将平台层屏幕信息转换为标准 CaptureTarget。"""
        return cls(
            index=int(data["index"]),
            is_primary=bool(data["is_primary"]),
            logical_x=int(data["logical_x"]),
            logical_y=int(data["logical_y"]),
            logical_width=int(data["logical_width"]),
            logical_height=int(data["logical_height"]),
            capture_x=int(data["capture_x"]),
            capture_y=int(data["capture_y"]),
            capture_width=int(data["capture_width"]),
            capture_height=int(data["capture_height"]),
        )


class ScreenshotCapture:
    """屏幕截图类"""
    
    TARGET_WIDTH = 1000
    TARGET_HEIGHT = 1000

    @staticmethod
    def _capture_error_payload(
        *,
        user_message: str,
        dev_detail: str = "",
        retryable: bool = True,
        kind: str = KIND_EXECUTION_FAILED,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        envelope = from_message(
            source=SOURCE_CAPTURE,
            kind=kind,
            user_message=user_message,
            dev_detail=dev_detail,
            code=CODE_CAPTURE_FAILED,
            retryable=retryable,
            extra=extra,
        )
        return envelope.to_dict()
    
    def __init__(self, config: Optional[Config] = None):
        self._config = config or Config()
        self._platform_adapter = get_platform_adapter()
        self._original_width = 0
        self._original_height = 0
        self._logical_width = 0
        self._logical_height = 0
        self._scaling_factor = 1.0
        self._last_capture_error_envelope: Optional[Dict[str, Any]] = None

    def get_last_capture_error_envelope(self) -> Optional[Dict[str, Any]]:
        return dict(self._last_capture_error_envelope or {}) if self._last_capture_error_envelope else None
    
    def capture(
        self,
        save_path: Optional[str] = None,
        optimize: Optional[bool] = None
    ) -> Tuple[bool, float, Tuple[int, int]]:
        """
        截取屏幕并保存，缩放到1000x1000像素
        
        Args:
            save_path: 保存路径，默认使用配置中的路径
            optimize: 是否优化速度，默认使用配置中的设置
        
        Returns:
            Tuple[bool, float, Tuple[int, int]]: (是否成功, 缩放比例, (逻辑宽度, 逻辑高度))
                注意：返回的是逻辑屏幕尺寸，用于 pyautogui 鼠标操作
        """
        screenshot_config = self._config.screenshot_config
        
        if save_path is None:
            save_path = self._config.get_resolved_path("input_path") or "imgs/screen.png"
        if optimize is None:
            optimize = screenshot_config.get("optimize_for_speed", True)
        
        save_path = self._resolve_path(save_path)
        self._ensure_directory(save_path)
        
        try:
            if not optimize:
                print("正在执行截屏...")
                start_time = time.time()
            
            self._scaling_factor = self._platform_adapter.get_scaling_factor()
            logical_size = self._platform_adapter.get_logical_screen_size()
            self._logical_width, self._logical_height = logical_size
            
            screenshot = pyautogui.screenshot()
            screenshot_np = np.array(screenshot)
            screenshot_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
            
            height, width, _ = screenshot_bgr.shape
            self._original_width = width
            self._original_height = height
            
            screenshot_bgr = cv2.resize(
                screenshot_bgr, 
                (self.TARGET_WIDTH, self.TARGET_HEIGHT)
            )

            try:
                mx, my = pyautogui.position()
                self._draw_cursor_on_image(
                    screenshot_bgr, mx, my,
                    0, 0, self._logical_width, self._logical_height,
                )
            except Exception:
                pass

            scale = min(self.TARGET_WIDTH / width, self.TARGET_HEIGHT / height)
            
            save_params = [int(cv2.IMWRITE_PNG_COMPRESSION), 1] if optimize else []
            success = cv2.imwrite(save_path, screenshot_bgr, save_params)
            
            if success and not optimize:
                file_size = os.path.getsize(save_path) / 1024
                img_height, img_width, _ = screenshot_bgr.shape
                print(f"截屏成功！")
                print(f"物理尺寸: {width} x {height} 像素")
                print(f"逻辑尺寸: {self._logical_width} x {self._logical_height} 像素")
                print(f"缩放因子: {self._scaling_factor}")
                print(f"缩放后尺寸: {img_width} x {img_height} 像素")
                print(f"保存路径: {os.path.abspath(save_path)}")
                print(f"文件大小: {file_size:.2f} KB")
                print(f"处理耗时: {(time.time() - start_time):.2f} 秒")
            elif not success:
                print("保存图像失败")
            
            return success, scale, (self._logical_width, self._logical_height)
        
        except Exception as e:
            print(f"截屏过程中发生错误: {e}")
            return False, 1.0, (0, 0)
    
    def _resolve_path(self, path: str) -> str:
        """解析路径"""
        if os.path.isabs(path):
            return path
        
        resolved = self._platform_adapter.get_resource_path(path)
        return resolved if resolved else path
    
    def _ensure_directory(self, file_path: str) -> None:
        """确保目录存在"""
        output_dir = os.path.dirname(file_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"创建文件夹: {output_dir}")

    @staticmethod
    def _draw_cursor_on_image(
        image: np.ndarray,
        mouse_x: int,
        mouse_y: int,
        screen_x: int,
        screen_y: int,
        screen_width: int,
        screen_height: int,
    ) -> None:
        rel_x = mouse_x - screen_x
        rel_y = mouse_y - screen_y
        if rel_x < 0 or rel_x >= screen_width or rel_y < 0 or rel_y >= screen_height:
            return

        h, w = image.shape[:2]
        cx = int(rel_x * w / screen_width)
        cy = int(rel_y * h / screen_height)

        cursor_height = max(18, int(h * 0.022))
        scale = cursor_height / 20.0

        base_pts = np.array([
            [0, 0], [0, 18], [5, 14], [8, 20], [11, 17], [7, 11], [12, 11]
        ], dtype=np.float64)
        pts = (base_pts * scale + [cx, cy]).astype(np.int32)

        cv2.fillPoly(image, [pts], (255, 255, 255))
        cv2.drawContours(image, [pts], -1, (0, 0, 0), 1, cv2.LINE_AA)
    
    def get_image_dimensions(self, image_path: Optional[str] = None) -> Tuple[Optional[int], Optional[int]]:
        """
        获取图片尺寸
        
        Args:
            image_path: 图片路径，默认使用配置中的截图路径
        
        Returns:
            Tuple[Optional[int], Optional[int]]: (宽度, 高度)
        """
        if image_path is None:
            image_path = self._config.get_resolved_path("input_path") or "imgs/screen.png"
        
        image_path = self._resolve_path(image_path)
        
        if not os.path.exists(image_path):
            return None, None
        
        img = cv2.imread(image_path)
        if img is None:
            return None, None
        
        height, width = img.shape[:2]
        return width, height
    
    def _ensure_qt_app(self) -> QApplication:
        """确保 QApplication 实例存在"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    @staticmethod
    def _encode_png_bytes(image_bgr: np.ndarray, optimize: bool = True) -> bytes:
        """将 BGR 图像编码为 PNG 字节"""
        encode_params = [int(cv2.IMWRITE_PNG_COMPRESSION), 1] if optimize else []
        success, buffer = cv2.imencode(".png", image_bgr, encode_params)
        if not success:
            raise RuntimeError("无法将截图编码为 PNG")
        return buffer.tobytes()

    @staticmethod
    def _build_data_url(png_bytes: bytes) -> str:
        """构建 data URL"""
        img_base64 = base64.b64encode(png_bytes).decode("utf-8")
        return f"data:image/png;base64,{img_base64}"

    @staticmethod
    def _calculate_frame_hash(png_bytes: bytes) -> str:
        """计算截图哈希，用于缓存和停滞检测"""
        return hashlib.sha256(png_bytes).hexdigest()

    @staticmethod
    def calculate_image_difference(previous_gray: np.ndarray, current_gray: np.ndarray) -> float:
        """计算两张灰度图的平均差异比例"""
        if previous_gray.shape != current_gray.shape:
            current_gray = cv2.resize(
                current_gray,
                (previous_gray.shape[1], previous_gray.shape[0])
            )

        diff = cv2.absdiff(previous_gray, current_gray)
        return float(np.mean(diff) / 255.0)

    @staticmethod
    def _capture_region_bgr(x: int, y: int, width: int, height: int) -> np.ndarray:
        """使用现有 backend 截取指定区域并返回 BGR 图像"""
        screenshot = pyautogui.screenshot(region=(x, y, width, height))
        screenshot_np = np.array(screenshot)
        return cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)

    def capture_window_region(
        self,
        bounds: Dict[str, Any],
        optimize: Optional[bool] = None,
        include_data_url: bool = True,
    ) -> Dict[str, Any]:
        """
        截取指定窗口区域并返回轻量结果（用于伴随推荐）。

        Args:
            bounds: {x, y, width, height}（默认按 pyautogui/mss 的全局坐标系）
            optimize: 是否优化编码速度，默认使用 screenshot_config.optimize_for_speed

        Returns:
            dict: {
              ok: bool,
              error: Optional[str],
              width: int,
              height: int,
              png_bytes: bytes,
              data_url: str,  # include_data_url=false 时为空
              frame_hash: str
            }
        """
        if not isinstance(bounds, dict):
            return {
                "ok": False,
                "error": "bounds 非法",
                "width": 0,
                "height": 0,
                "error_envelope": self._capture_error_payload(user_message="窗口截图失败", dev_detail="bounds 非法"),
            }

        try:
            x = int(bounds.get("x", 0))
            y = int(bounds.get("y", 0))
            width = int(bounds.get("width", 0))
            height = int(bounds.get("height", 0))
        except Exception:
            return {
                "ok": False,
                "error": "bounds 字段无法解析为整数",
                "width": 0,
                "height": 0,
                "error_envelope": self._capture_error_payload(
                    user_message="窗口截图失败",
                    dev_detail="bounds 字段无法解析为整数",
                ),
            }

        if width <= 0 or height <= 0:
            return {
                "ok": False,
                "error": "bounds 尺寸非法",
                "width": 0,
                "height": 0,
                "error_envelope": self._capture_error_payload(user_message="窗口截图失败", dev_detail="bounds 尺寸非法"),
            }

        screenshot_config = self._config.screenshot_config
        if optimize is None:
            optimize = bool(screenshot_config.get("optimize_for_speed", True))

        backend = self._get_backend_name(screenshot_config.get("capture_backend", "auto"))
        fallback_backend = self._get_backend_name(
            screenshot_config.get("capture_fallback_backend", "pyautogui")
        )
        fallback_envelope: Optional[Dict[str, Any]] = None

        screenshot_bgr: Optional[np.ndarray] = None
        if backend in {"auto", "mss"}:
            try:
                mss_module = self._load_mss_module()
                if mss_module is None:
                    raise RuntimeError("mss 未安装")
                with mss_module.mss() as sct:
                    raw = sct.grab({"left": x, "top": y, "width": width, "height": height})
                    rgba = np.array(raw)  # BGRA
                    screenshot_bgr = cv2.cvtColor(rgba, cv2.COLOR_BGRA2BGR)
            except Exception as exc:
                print(f"mss 窗口截图失败，切换到 {fallback_backend}: {exc}")
                fallback_envelope = from_exception(
                    exc,
                    source=SOURCE_CAPTURE,
                    kind=KIND_BACKEND_FALLBACK,
                    user_message="截图后端已回退到备用方案",
                    code=CODE_CAPTURE_FAILED,
                    retryable=True,
                    extra={"backend": backend, "fallback_backend": fallback_backend},
                ).to_dict()
                screenshot_bgr = None
                if backend == "mss" and fallback_backend != "pyautogui":
                    return {
                        "ok": False,
                        "error": str(exc),
                        "width": 0,
                        "height": 0,
                        "error_envelope": from_exception(
                            exc,
                            source=SOURCE_CAPTURE,
                            kind=KIND_EXECUTION_FAILED,
                            user_message="窗口截图失败",
                            code=CODE_CAPTURE_FAILED,
                            retryable=False,
                            extra={"backend": backend, "fallback_backend": fallback_backend},
                        ).to_dict(),
                    }

        if screenshot_bgr is None and (fallback_backend == "pyautogui" or backend == "pyautogui"):
            try:
                screenshot_bgr = self._capture_region_bgr(x, y, width, height)
            except Exception as exc:
                return {
                    "ok": False,
                    "error": str(exc),
                    "width": 0,
                    "height": 0,
                    "error_envelope": from_exception(
                        exc,
                        source=SOURCE_CAPTURE,
                        kind=KIND_EXECUTION_FAILED,
                        user_message="窗口截图失败",
                        code=CODE_CAPTURE_FAILED,
                        retryable=True,
                        extra={"backend": "pyautogui"},
                    ).to_dict(),
                }

        if screenshot_bgr is None:
            return {
                "ok": False,
                "error": "未能截取窗口区域",
                "width": 0,
                "height": 0,
                "error_envelope": self._capture_error_payload(user_message="窗口截图失败", dev_detail="未能截取窗口区域"),
            }

        # Keep companion payload bounded; this is not the main agent's multi-screen capture path.
        try:
            h0, w0 = screenshot_bgr.shape[:2]
            max_side = max(w0, h0)
            if max_side > self.TARGET_WIDTH:
                scale = float(self.TARGET_WIDTH) / float(max_side)
                new_w = max(1, int(w0 * scale))
                new_h = max(1, int(h0 * scale))
                screenshot_bgr = cv2.resize(screenshot_bgr, (new_w, new_h))
        except Exception:
            pass

        try:
            png_bytes = self._encode_png_bytes(screenshot_bgr, optimize=bool(optimize))
            return {
                "ok": True,
                "error": None,
                "width": int(screenshot_bgr.shape[1]),
                "height": int(screenshot_bgr.shape[0]),
                "png_bytes": png_bytes,
                "data_url": self._build_data_url(png_bytes) if include_data_url else "",
                "frame_hash": self._calculate_frame_hash(png_bytes),
                "fallback_error_envelope": fallback_envelope,
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "width": 0,
                "height": 0,
                "error_envelope": from_exception(
                    exc,
                    source=SOURCE_CAPTURE,
                    kind=KIND_EXECUTION_FAILED,
                    user_message="窗口截图失败",
                    code=CODE_CAPTURE_FAILED,
                    retryable=True,
                ).to_dict(),
            }

    def _get_sorted_qt_screens(self) -> Tuple[Optional[QScreen], List[QScreen]]:
        """获取按主屏优先排序后的 Qt 屏幕对象"""
        app = self._ensure_qt_app()
        screens = list(app.screens())
        if not screens:
            screens = list(QApplication.screens())
        if not screens:
            return None, []

        primary_screen = QApplication.primaryScreen()
        sorted_screens = sorted(screens, key=lambda screen: 0 if screen == primary_screen else 1)
        return primary_screen, sorted_screens

    def _get_capture_targets(self) -> List[Dict[str, Any]]:
        """获取截图目标，优先使用 Qt，失败时回退到平台层屏幕信息"""
        primary_screen, sorted_screens = self._get_sorted_qt_screens()
        if sorted_screens:
            targets: List[Dict[str, Any]] = []
            for idx, screen in enumerate(sorted_screens):
                geometry = screen.geometry()
                targets.append({
                    "index": idx,
                    "x": geometry.x(),
                    "y": geometry.y(),
                    "width": geometry.width(),
                    "height": geometry.height(),
                    "logical_width": geometry.width(),
                    "logical_height": geometry.height(),
                    "is_primary": screen == primary_screen,
                })
            return targets

        platform_screens = self.get_screens_info()
        if not platform_screens:
            return []

        print("Qt 未返回屏幕列表，回退到平台屏幕信息")
        sorted_platform_screens = sorted(
            platform_screens,
            key=lambda screen: (0 if screen.get("is_primary") else 1, screen.get("index", 0))
        )

        targets: List[Dict[str, Any]] = []
        for idx, screen in enumerate(sorted_platform_screens):
            width = int(screen.get("width", 0))
            height = int(screen.get("height", 0))
            targets.append({
                "index": idx,
                "x": int(screen.get("x", 0)),
                "y": int(screen.get("y", 0)),
                "width": width,
                "height": height,
                "logical_width": int(screen.get("logical_width", width)),
                "logical_height": int(screen.get("logical_height", height)),
                "is_primary": bool(screen.get("is_primary")),
            })
        return targets

    def _build_screen_bundle(
        self,
        index: int,
        geometry: QRect,
        logical_width: int,
        logical_height: int,
        is_primary: bool,
        save_path: Optional[str],
        optimize: bool
    ) -> ScreenCaptureBundle:
        """基于现有截图 backend 构建单屏幕内存 bundle"""
        return self._build_screen_bundle_from_target(
            target={
                "index": index,
                "x": geometry.x(),
                "y": geometry.y(),
                "width": geometry.width(),
                "height": geometry.height(),
                "logical_width": logical_width,
                "logical_height": logical_height,
                "is_primary": is_primary,
            },
            save_path=save_path,
            optimize=optimize,
        )

    def _build_screen_bundle_from_target(
        self,
        target: Dict[str, Any],
        save_path: Optional[str],
        optimize: bool
    ) -> ScreenCaptureBundle:
        screen_x = int(target["x"])
        screen_y = int(target["y"])
        screen_width = int(target["width"])
        screen_height = int(target["height"])

        screenshot_bgr = self._capture_region_bgr(screen_x, screen_y, screen_width, screen_height)
        screenshot_resized = cv2.resize(
            screenshot_bgr,
            (self.TARGET_WIDTH, self.TARGET_HEIGHT)
        )

        try:
            mx, my = pyautogui.position()
            logical_w = int(target.get("logical_width", screen_width))
            logical_h = int(target.get("logical_height", screen_height))
            self._draw_cursor_on_image(
                screenshot_resized, mx, my,
                screen_x, screen_y, logical_w, logical_h,
            )
        except Exception:
            pass

        png_bytes = self._encode_png_bytes(screenshot_resized, optimize=optimize)

        if save_path:
            self._ensure_directory(save_path)
            with open(save_path, "wb") as image_file:
                image_file.write(png_bytes)

        return ScreenCaptureBundle(
            index=int(target["index"]),
            x=screen_x,
            y=screen_y,
            width=screen_width,
            height=screen_height,
            logical_width=int(target["logical_width"]),
            logical_height=int(target["logical_height"]),
            is_primary=bool(target["is_primary"]),
            png_bytes=png_bytes,
            data_url=self._build_data_url(png_bytes),
            frame_hash=self._calculate_frame_hash(png_bytes),
            path=save_path
        )

    @staticmethod
    def _get_backend_name(config_value: str) -> str:
        """规范化截图 backend 名称。"""
        backend = (config_value or "auto").strip().lower()
        return backend if backend in {"auto", "mss", "pyautogui"} else "auto"

    @staticmethod
    def _load_mss_module():
        """延迟加载 mss，避免环境未安装时模块导入失败。"""
        try:
            import mss  # type: ignore

            return mss
        except ImportError:
            return None

    def _resolve_capture_targets(
        self,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> List[CaptureTarget]:
        """获取统一的截图目标列表。"""
        raw_targets = self._platform_adapter.get_capture_screens_info()
        targets = [CaptureTarget.from_dict(item) for item in raw_targets]
        if not targets and screen_info:
            return [
                CaptureTarget(
                    index=int(screen.get("index", position)),
                    is_primary=bool(screen.get("is_primary")),
                    logical_x=int(screen.get("x", 0)),
                    logical_y=int(screen.get("y", 0)),
                    logical_width=int(screen.get("logical_width", screen.get("width", 0))),
                    logical_height=int(screen.get("logical_height", screen.get("height", 0))),
                    capture_x=int(screen.get("capture_x", screen.get("x", 0))),
                    capture_y=int(screen.get("capture_y", screen.get("y", 0))),
                    capture_width=int(screen.get("capture_width", screen.get("width", 0))),
                    capture_height=int(screen.get("capture_height", screen.get("height", 0))),
                )
                for position, screen in enumerate(screen_info)
            ]

        if not screen_info or not targets:
            return targets

        target_by_index = {target.index: target for target in targets}
        resolved_targets: List[CaptureTarget] = []
        for position, screen in enumerate(screen_info):
            screen_index = int(screen.get("index", position))
            target = target_by_index.get(screen_index)
            if target is None and position < len(targets):
                target = targets[position]
            if target is not None:
                resolved_targets.append(target)

        return resolved_targets or targets

    @staticmethod
    def _monitor_rect_to_dict(monitor: Dict[str, Any]) -> Dict[str, int]:
        """将 mss monitor 元信息标准化。"""
        return {
            "left": int(monitor["left"]),
            "top": int(monitor["top"]),
            "width": int(monitor["width"]),
            "height": int(monitor["height"]),
        }

    def _capture_virtual_desktop_bgr(self, mss_module) -> Tuple[np.ndarray, Dict[str, int], int]:
        """使用 mss 抓取整张虚拟桌面。"""
        with mss_module.mss() as sct:
            monitors = getattr(sct, "monitors", None) or []
            if len(monitors) <= 1:
                raise RuntimeError("mss 未返回可用的物理屏幕信息")

            virtual_monitor = self._monitor_rect_to_dict(monitors[0])
            screenshot = sct.grab(virtual_monitor)
            screenshot_np = np.array(screenshot)
            screenshot_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_BGRA2BGR)
            return screenshot_bgr, virtual_monitor, len(monitors) - 1

    def _get_mss_physical_monitors(self, mss_module) -> List[Dict[str, int]]:
        """获取 mss 的物理屏幕矩形，并按主屏优先排序。"""
        with mss_module.mss() as sct:
            monitors = getattr(sct, "monitors", None) or []
            if len(monitors) <= 1:
                raise RuntimeError("mss 未返回可用的物理屏幕信息")

            physical_monitors = [
                self._monitor_rect_to_dict(monitor)
                for monitor in monitors[1:]
            ]

        return sorted(
            physical_monitors,
            key=lambda monitor: (
                0 if monitor["left"] == 0 and monitor["top"] == 0 else 1,
                monitor["left"],
                monitor["top"],
            ),
        )

    @staticmethod
    def _capture_monitor_bgr(mss_module, monitor: Dict[str, int]) -> np.ndarray:
        """使用 mss 直接抓取单个物理屏幕。"""
        region = {
            "left": int(monitor["left"]),
            "top": int(monitor["top"]),
            "width": int(monitor["width"]),
            "height": int(monitor["height"]),
        }
        with mss_module.mss() as sct:
            screenshot = sct.grab(region)
        screenshot_np = np.array(screenshot)
        return cv2.cvtColor(screenshot_np, cv2.COLOR_BGRA2BGR)

    def _get_mss_monitors_for_targets(
        self,
        mss_module,
        targets: List[CaptureTarget],
    ) -> List[Dict[str, int]]:
        """按平台选择 mss 抓取矩形。"""
        if platform.system() == "Darwin":
            return self._get_mss_physical_monitors(mss_module)

        return [
            {
                "left": target.capture_x,
                "top": target.capture_y,
                "width": target.capture_width,
                "height": target.capture_height,
            }
            for target in targets
        ]

    @staticmethod
    def _get_crop_params(targets: List[CaptureTarget], desktop_bgr_shape: Tuple[int, ...]) -> Tuple[int, int, float, float]:
        capture_left = min(t.capture_x for t in targets)
        capture_top = min(t.capture_y for t in targets)
        capture_right = max(t.capture_x + t.capture_width for t in targets)
        capture_bottom = max(t.capture_y + t.capture_height for t in targets)
        capture_width = capture_right - capture_left
        capture_height = capture_bottom - capture_top

        scale_x = desktop_bgr_shape[1] / capture_width if capture_width > 0 else 1.0
        scale_y = desktop_bgr_shape[0] / capture_height if capture_height > 0 else 1.0

        return capture_left, capture_top, scale_x, scale_y

    @staticmethod
    def _crop_virtual_desktop_bgr(
        desktop_bgr: np.ndarray,
        target: CaptureTarget,
        capture_left: int,
        capture_top: int,
        scale_x: float,
        scale_y: float,
    ) -> np.ndarray:
        """从虚拟桌面截图中裁切出指定屏幕区域。"""
        relative_x = int(round((target.capture_x - capture_left) * scale_x))
        relative_y = int(round((target.capture_y - capture_top) * scale_y))
        crop_width = int(round(target.capture_width * scale_x))
        crop_height = int(round(target.capture_height * scale_y))

        end_x = min(relative_x + crop_width, desktop_bgr.shape[1])
        end_y = min(relative_y + crop_height, desktop_bgr.shape[0])
        relative_x = max(0, relative_x)
        relative_y = max(0, relative_y)

        if relative_x >= end_x or relative_y >= end_y:
            raise RuntimeError(
                f"目标屏幕 {target.index} 的裁切区域越界/无效: "
                f"({relative_x}, {relative_y}, {end_x}, {end_y})"
            )

        return desktop_bgr[relative_y:end_y, relative_x:end_x].copy()

    def _build_bundle_from_image(
        self,
        target: CaptureTarget,
        screenshot_bgr: np.ndarray,
        save_path: Optional[str],
        optimize: bool,
    ) -> ScreenCaptureBundle:
        screenshot_resized = cv2.resize(
            screenshot_bgr,
            (self.TARGET_WIDTH, self.TARGET_HEIGHT),
        )

        try:
            mx, my = pyautogui.position()
            self._draw_cursor_on_image(
                screenshot_resized, mx, my,
                target.logical_x, target.logical_y,
                target.logical_width, target.logical_height,
            )
        except Exception:
            pass

        png_bytes = self._encode_png_bytes(screenshot_resized, optimize=optimize)

        if save_path:
            self._ensure_directory(save_path)
            with open(save_path, "wb") as image_file:
                image_file.write(png_bytes)

        return ScreenCaptureBundle(
            index=target.index,
            x=target.logical_x,
            y=target.logical_y,
            width=target.capture_width,
            height=target.capture_height,
            logical_width=target.logical_width,
            logical_height=target.logical_height,
            is_primary=target.is_primary,
            png_bytes=png_bytes,
            data_url=self._build_data_url(png_bytes),
            frame_hash=self._calculate_frame_hash(png_bytes),
            path=save_path,
        )

    def _capture_targets_with_mss(
        self,
        targets: List[CaptureTarget],
        save_dir: str,
        optimize: bool,
        save_debug: bool,
    ) -> List[ScreenCaptureBundle]:
        """使用 mss 逐屏抓取物理 monitor，避免混合缩放虚拟桌面裁切偏移。"""
        mss_module = self._load_mss_module()
        if mss_module is None:
            raise RuntimeError("mss 未安装")

        monitors = self._get_mss_monitors_for_targets(mss_module, targets)
        if len(monitors) != len(targets):
            raise RuntimeError(
                f"mss monitor 数量 {len(monitors)} 与平台屏幕数量 {len(targets)} 不一致"
            )

        bundles: List[ScreenCaptureBundle] = []
        for target, monitor in zip(targets, monitors):
            save_path = os.path.join(save_dir, f"screen_{target.index}.png") if save_debug else None
            screen_bgr = self._capture_monitor_bgr(mss_module, monitor)
            bundles.append(
                self._build_bundle_from_image(
                    target=target,
                    screenshot_bgr=screen_bgr,
                    save_path=save_path,
                    optimize=optimize,
                )
            )

        return bundles

    def _capture_targets_with_pyautogui(
        self,
        targets: List[CaptureTarget],
        save_dir: str,
        optimize: bool,
        save_debug: bool,
    ) -> List[ScreenCaptureBundle]:
        """使用 pyautogui fallback 逐屏截图。"""
        bundles: List[ScreenCaptureBundle] = []
        for target in targets:
            save_path = os.path.join(save_dir, f"screen_{target.index}.png") if save_debug else None
            screen_bgr = self._capture_region_bgr(
                target.capture_x,
                target.capture_y,
                target.capture_width,
                target.capture_height,
            )
            bundles.append(
                self._build_bundle_from_image(
                    target=target,
                    screenshot_bgr=screen_bgr,
                    save_path=save_path,
                    optimize=optimize,
                )
            )

        return bundles

    def _capture_targets(
        self,
        targets: List[CaptureTarget],
        save_dir: str,
        optimize: bool,
        save_debug: bool,
    ) -> List[ScreenCaptureBundle]:
        """按照配置选择截图 backend，并在失败时回退。"""
        screenshot_config = self._config.screenshot_config
        backend = self._get_backend_name(screenshot_config.get("capture_backend", "auto"))
        fallback_backend = self._get_backend_name(
            screenshot_config.get("capture_fallback_backend", "pyautogui")
        )

        if backend in {"auto", "mss"}:
            try:
                return self._capture_targets_with_mss(
                    targets=targets,
                    save_dir=save_dir,
                    optimize=optimize,
                    save_debug=save_debug,
                )
            except Exception as exc:
                print(f"mss 截图失败，切换到 {fallback_backend}: {exc}")
                if backend == "mss" and fallback_backend != "pyautogui":
                    raise

        if fallback_backend == "pyautogui" or backend == "pyautogui":
            return self._capture_targets_with_pyautogui(
                targets=targets,
                save_dir=save_dir,
                optimize=optimize,
                save_debug=save_debug,
            )

        raise RuntimeError(f"不支持的截图 backend 配置: {backend}/{fallback_backend}")

    def _capture_probes_with_mss(
        self,
        targets: List[CaptureTarget],
        probe_width: int,
        probe_height: int,
    ) -> List[Dict[str, Any]]:
        """使用 mss 抓取低清 probe。"""
        mss_module = self._load_mss_module()
        if mss_module is None:
            raise RuntimeError("mss 未安装")

        monitors = self._get_mss_monitors_for_targets(mss_module, targets)
        if len(monitors) != len(targets):
            raise RuntimeError(
                f"mss monitor 数量 {len(monitors)} 与平台屏幕数量 {len(targets)} 不一致"
            )

        probes: List[Dict[str, Any]] = []
        for target, monitor in zip(targets, monitors):
            screen_bgr = self._capture_monitor_bgr(mss_module, monitor)
            resized = cv2.resize(screen_bgr, (probe_width, probe_height))
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            probes.append({
                "index": target.index,
                "gray": gray,
                "width": target.logical_width,
                "height": target.logical_height,
            })

        return probes

    def _capture_probes_with_pyautogui(
        self,
        targets: List[CaptureTarget],
        probe_width: int,
        probe_height: int,
    ) -> List[Dict[str, Any]]:
        """使用 pyautogui fallback 抓取低清 probe。"""
        probes: List[Dict[str, Any]] = []
        for target in targets:
            screenshot_bgr = self._capture_region_bgr(
                target.capture_x,
                target.capture_y,
                target.capture_width,
                target.capture_height,
            )
            resized = cv2.resize(screenshot_bgr, (probe_width, probe_height))
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            probes.append({
                "index": target.index,
                "gray": gray,
                "width": target.logical_width,
                "height": target.logical_height,
            })

        return probes

    def capture_all_screens_bundle(
        self,
        save_dir: Optional[str] = None,
        optimize: Optional[bool] = None,
        save_debug: Optional[bool] = None
    ) -> Tuple[bool, List[ScreenCaptureBundle]]:
        """截取所有屏幕并返回内存 bundle，调试模式下可选落盘"""
        screenshot_config = self._config.screenshot_config

        if save_dir is None:
            save_dir = os.path.dirname(
                self._config.get_resolved_path("input_path") or "imgs/screen.png"
            )
        if optimize is None:
            optimize = screenshot_config.get("optimize_for_speed", True)
        if save_debug is None:
            save_debug = screenshot_config.get("save_debug_captures", False)

        save_dir = self._resolve_path(save_dir)
        self._last_capture_error_envelope = None

        try:
            if not optimize:
                print("正在执行多屏幕截图（内存 bundle）...")
                start_time = time.time()

            capture_targets = self._resolve_capture_targets()
            if not capture_targets:
                print("未检测到屏幕")
                return False, []

            self._scaling_factor = self._platform_adapter.get_scaling_factor()
            bundles = self._capture_targets(
                targets=capture_targets,
                save_dir=save_dir,
                optimize=optimize,
                save_debug=save_debug,
            )

            if not optimize:
                print(f"多屏幕截图完成，共 {len(bundles)} 个屏幕")
                print(f"处理耗时: {(time.time() - start_time):.2f} 秒")

            return len(bundles) > 0, bundles

        except Exception as e:
            print(f"多屏幕截图（内存 bundle）过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            self._last_capture_error_envelope = from_exception(
                e,
                source=SOURCE_CAPTURE,
                kind=KIND_EXECUTION_FAILED,
                user_message="屏幕截图失败",
                code=CODE_CAPTURE_FAILED,
                retryable=True,
            ).to_dict()
            return False, []

    def capture_screen_probes(
        self,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        probe_width: int = 160,
        probe_height: int = 90
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """截取所有屏幕的低清 probe，用于页面稳定检测"""
        self._last_capture_error_envelope = None
        try:
            targets = self._resolve_capture_targets(screen_info)
            if not targets:
                return False, []

            screenshot_config = self._config.screenshot_config
            backend = self._get_backend_name(screenshot_config.get("capture_backend", "auto"))
            fallback_backend = self._get_backend_name(
                screenshot_config.get("capture_fallback_backend", "pyautogui")
            )
            probes: List[Dict[str, Any]] = []

            if backend in {"auto", "mss"}:
                try:
                    probes = self._capture_probes_with_mss(
                        targets=targets,
                        probe_width=probe_width,
                        probe_height=probe_height,
                    )
                except Exception as exc:
                    print(f"mss probe 鎴浘澶辫触锛屽垏鎹㈠埌 {fallback_backend}: {exc}")
                    if backend == "mss" and fallback_backend != "pyautogui":
                        raise

            if not probes and (fallback_backend == "pyautogui" or backend == "pyautogui"):
                probes = self._capture_probes_with_pyautogui(
                    targets=targets,
                    probe_width=probe_width,
                    probe_height=probe_height,
                )

            return len(probes) > 0, probes

        except Exception as e:
            print(f"截取低清 probe 失败: {e}")
            self._last_capture_error_envelope = from_exception(
                e,
                source=SOURCE_CAPTURE,
                kind=KIND_EXECUTION_FAILED,
                user_message="屏幕截图失败",
                code=CODE_CAPTURE_FAILED,
                retryable=True,
            ).to_dict()
            return False, []

    def capture_all_screens(
        self,
        save_dir: Optional[str] = None,
        optimize: Optional[bool] = None
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        截取所有屏幕并保存
        
        Args:
            save_dir: 保存目录，默认使用配置中的路径
            optimize: 是否优化速度，默认使用配置中的设置
        
        Returns:
            Tuple[bool, List[Dict]]: (是否成功, 屏幕信息列表)
            每个屏幕信息包含:
            - index: 屏幕索引
            - path: 截图保存路径
            - width: 原始宽度
            - height: 原始高度
            - logical_width: 逻辑宽度
            - logical_height: 逻辑高度
            - x: 屏幕在虚拟桌面中的X坐标
            - y: 屏幕在虚拟桌面中的Y坐标
            - is_primary: 是否为主屏幕
        """
        success, bundles = self.capture_all_screens_bundle(
            save_dir=save_dir,
            optimize=optimize,
            save_debug=True,
        )
        if not success:
            return False, []

        return True, [
            {
                "index": bundle.index,
                "path": bundle.path,
                "width": bundle.width,
                "height": bundle.height,
                "logical_width": bundle.logical_width,
                "logical_height": bundle.logical_height,
                "x": bundle.x,
                "y": bundle.y,
                "is_primary": bundle.is_primary,
            }
            for bundle in bundles
        ]

        screenshot_config = self._config.screenshot_config
        
        if save_dir is None:
            save_dir = os.path.dirname(
                self._config.get_resolved_path("input_path") or "imgs/screen.png"
            )
        if optimize is None:
            optimize = screenshot_config.get("optimize_for_speed", True)
        
        save_dir = self._resolve_path(save_dir)
        self._ensure_directory(os.path.join(save_dir, "screen_0.png"))
        
        try:
            if not optimize:
                print("正在执行多屏幕截屏...")
                start_time = time.time()
            
            app = self._ensure_qt_app()
            screens = QApplication.screens()
            
            if not screens:
                print("未检测到屏幕")
                return False, []
            
            primary_screen = QApplication.primaryScreen()
            sorted_screens = sorted(
                screens,
                key=lambda s: 0 if s == primary_screen else 1
            )
            
            results = []
            self._scaling_factor = self._platform_adapter.get_scaling_factor()
            
            for idx, screen in enumerate(sorted_screens):
                geometry = screen.geometry()
                screen_x = geometry.x()
                screen_y = geometry.y()
                screen_width = geometry.width()
                screen_height = geometry.height()
                is_primary = (screen == primary_screen)
                
                screenshot = pyautogui.screenshot(
                    region=(screen_x, screen_y, screen_width, screen_height)
                )
                screenshot_np = np.array(screenshot)
                screenshot_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
                
                original_height, original_width = screenshot_bgr.shape[:2]
                
                screenshot_resized = cv2.resize(
                    screenshot_bgr,
                    (self.TARGET_WIDTH, self.TARGET_HEIGHT)
                )
                
                save_path = os.path.join(save_dir, f"screen_{idx}.png")
                save_params = [int(cv2.IMWRITE_PNG_COMPRESSION), 1] if optimize else []
                success = cv2.imwrite(save_path, screenshot_resized, save_params)
                
                if success:
                    result = {
                        'index': idx,
                        'path': save_path,
                        'width': original_width,
                        'height': original_height,
                        'logical_width': screen_width,
                        'logical_height': screen_height,
                        'x': screen_x,
                        'y': screen_y,
                        'is_primary': is_primary
                    }
                    results.append(result)
                    
                    if not optimize:
                        file_size = os.path.getsize(save_path) / 1024
                        primary_str = "（主屏幕）" if is_primary else ""
                        print(f"屏幕{idx}{primary_str}截屏成功！")
                        print(f"  物理尺寸: {original_width} x {original_height} 像素")
                        print(f"  逻辑尺寸: {screen_width} x {screen_height} 像素")
                        print(f"  位置: ({screen_x}, {screen_y})")
                        print(f"  保存路径: {save_path}")
                        print(f"  文件大小: {file_size:.2f} KB")
                else:
                    print(f"屏幕{idx}保存图像失败")
            
            if not optimize:
                print(f"多屏幕截屏完成，共 {len(results)} 个屏幕")
                print(f"处理耗时: {(time.time() - start_time):.2f} 秒")
            
            return len(results) > 0, results
        
        except Exception as e:
            print(f"多屏幕截屏过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            return False, []
    
    def get_screen_count(self) -> int:
        """
        获取屏幕数量
        
        Returns:
            屏幕数量
        """
        return self._platform_adapter.get_screen_count()
    
    def get_screens_info(self) -> List[Dict[str, Any]]:
        """
        获取所有屏幕信息
        
        Returns:
            屏幕信息列表
        """
        return self._platform_adapter.get_all_screens_info()
