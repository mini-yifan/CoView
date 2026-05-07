import hashlib
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from baodou_ai.core.screenshot import ScreenCaptureBundle, ScreenshotCapture


class ObservationService:
    """负责截图观察、前台应用准备与屏幕变化计算。"""

    _FILE_MANAGER_APP_NAMES = ("Finder", "访达", "File Explorer", "Windows Explorer", "Explorer", "资源管理器")

    def __init__(self, screenshot: ScreenshotCapture, automation: Any, focus_fallback_prompt: str) -> None:
        self._screenshot = screenshot
        self._automation = automation
        self._focus_fallback_prompt = focus_fallback_prompt
        self._gray_frame_cache: Dict[str, np.ndarray] = {}

    def clear_frame_cache(self) -> None:
        self._gray_frame_cache = {}

    @staticmethod
    def capture_with_hidden_windows(
        screenshot: ScreenshotCapture,
        on_transparent_enter: Optional[Callable[[], Any]] = None,
        on_transparent_exit: Optional[Callable[[], Any]] = None,
    ) -> Tuple[bool, List[ScreenCaptureBundle]]:
        hidden = False
        try:
            if on_transparent_enter is not None:
                on_transparent_enter()
                hidden = True
                time.sleep(0.05)
            return screenshot.capture_all_screens_bundle()
        finally:
            if hidden and on_transparent_exit is not None:
                on_transparent_exit()

    @staticmethod
    def normalize_frontmost_app_info(app_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(app_info, dict):
            return {}
        normalized = {
            "app_name": str(app_info.get("app_name") or "").strip(),
            "bundle_id": str(app_info.get("bundle_id") or "").strip(),
            "identifier": str(app_info.get("identifier") or "").strip(),
            "pid": 0,
            "hwnd": 0,
        }
        try:
            normalized["pid"] = int(app_info.get("pid") or 0)
        except (TypeError, ValueError):
            normalized["pid"] = 0
        try:
            normalized["hwnd"] = int(app_info.get("hwnd") or 0)
        except (TypeError, ValueError):
            normalized["hwnd"] = 0
        if not (
            normalized["app_name"]
            or normalized["bundle_id"]
            or normalized["identifier"]
            or normalized["pid"] > 0
            or normalized["hwnd"] > 0
        ):
            return {}
        return normalized

    @classmethod
    def is_external_frontmost_app(cls, app_info: Optional[Dict[str, Any]], agent_process_pid: int) -> bool:
        normalized = cls.normalize_frontmost_app_info(app_info)
        if not normalized:
            return False
        pid = int(normalized.get("pid") or 0)
        if pid <= 0 or pid == int(agent_process_pid):
            return False
        return bool(
            normalized.get("app_name")
            or normalized.get("bundle_id")
            or normalized.get("identifier")
        )

    def prepare_external_frontmost_app_before_capture(
        self,
        last_external_frontmost_app: Optional[Dict[str, Any]],
        agent_process_pid: int,
        should_stop: Callable[[], bool],
        sleep_interruptibly: Callable[[float, Callable[[], bool]], bool],
    ) -> Optional[Dict[str, Any]]:
        current_frontmost = self.normalize_frontmost_app_info(self._automation.get_frontmost_app_info())
        if self.is_external_frontmost_app(current_frontmost, agent_process_pid):
            return current_frontmost

        normalized_last = self.normalize_frontmost_app_info(last_external_frontmost_app)
        if not normalized_last:
            return current_frontmost or None

        if self._automation.activate_app(normalized_last):
            sleep_interruptibly(delay_ms=80.0, should_stop=should_stop)
        return self.normalize_frontmost_app_info(self._automation.get_frontmost_app_info()) or None

    def build_frontmost_app_prompt(self, frontmost_app_info: Optional[Dict[str, Any]], agent_process_pid: int) -> str:
        normalized = self.normalize_frontmost_app_info(frontmost_app_info)
        if self.is_external_frontmost_app(normalized, agent_process_pid):
            app_name = (
                str(normalized.get("app_name") or "").strip()
                or str(normalized.get("bundle_id") or "").strip()
                or str(normalized.get("identifier") or "").strip()
            )
            if app_name:
                prompt = f"Current frontmost app: {app_name}."
                doc_path = self._automation._platform_adapter.get_active_document_path(app_name)
                if app_name in self._FILE_MANAGER_APP_NAMES and doc_path is None:
                    time.sleep(0.12)
                    doc_path = self._automation._platform_adapter.get_active_document_path(app_name)
                if doc_path is not None:
                    if app_name in self._FILE_MANAGER_APP_NAMES:
                        if doc_path:
                            prompt += f"\nCurrent folder path: {doc_path}."
                    else:
                        if doc_path:
                            prompt += f"\nCurrent file path: {doc_path}."
                        else:
                            prompt += "\nCurrent document is not saved locally."
                return prompt
        return self._focus_fallback_prompt

    @staticmethod
    def build_screen_info(bundles: List[ScreenCaptureBundle]) -> List[Dict[str, Any]]:
        return [
            {
                "index": bundle.index,
                "x": bundle.x,
                "y": bundle.y,
                "width": bundle.logical_width,
                "height": bundle.logical_height,
                "is_primary": bundle.is_primary,
            }
            for bundle in bundles
        ]

    @staticmethod
    def build_screen_group_hash(bundles: List[ScreenCaptureBundle]) -> str:
        joined_hashes = "|".join(bundle.frame_hash for bundle in bundles)
        return hashlib.sha256(joined_hashes.encode("utf-8")).hexdigest()

    def calculate_changed_pixels_ratio(
        self,
        previous_bundles: Optional[List[ScreenCaptureBundle]],
        current_bundles: List[ScreenCaptureBundle],
    ) -> float:
        if not previous_bundles:
            self._retain_gray_frame_cache([])
            return 1.0

        previous_map = {bundle.index: bundle for bundle in previous_bundles}
        self._retain_gray_frame_cache(previous_bundles + current_bundles)
        ratios: List[float] = []
        for bundle in current_bundles:
            previous = previous_map.get(bundle.index)
            if previous is None:
                ratios.append(1.0)
                continue
            previous_gray = self._get_bundle_gray(previous)
            current_gray = self._get_bundle_gray(bundle)
            if previous_gray is None or current_gray is None:
                ratios.append(1.0)
                continue
            ratios.append(self._screenshot.calculate_image_difference(previous_gray, current_gray))
        return max(ratios) if ratios else 1.0

    def get_gray_frame_cache(self) -> Dict[str, np.ndarray]:
        return dict(self._gray_frame_cache)

    def _get_bundle_gray(self, bundle: ScreenCaptureBundle) -> Optional[np.ndarray]:
        cached = self._gray_frame_cache.get(bundle.frame_hash)
        if cached is not None:
            return cached

        gray = cv2.imdecode(
            np.frombuffer(bundle.png_bytes, dtype=np.uint8),
            cv2.IMREAD_GRAYSCALE,
        )
        if gray is not None:
            self._gray_frame_cache[bundle.frame_hash] = gray
        return gray

    def _retain_gray_frame_cache(self, bundles: List[ScreenCaptureBundle]) -> None:
        keep_hashes = {bundle.frame_hash for bundle in bundles}
        self._gray_frame_cache = {
            frame_hash: gray
            for frame_hash, gray in self._gray_frame_cache.items()
            if frame_hash in keep_hashes
        }

