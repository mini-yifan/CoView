"""Capture/recommend worker for companion suggestions."""

from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from baodou_ai.ai.companion_recommender import CompanionRecommender
from baodou_ai.ai.companion_privacy import CompanionPrivacyGuard
from baodou_ai.core.config import Config
from baodou_ai.core.screenshot import ScreenshotCapture


class CaptureRecommendWorker(QThread):
    capture_done = pyqtSignal(int)
    result_ready = pyqtSignal(int, object)

    def __init__(
        self,
        seq: int,
        config: Config,
        window_info: Dict[str, Any],
        context_text: str,
        privacy_guard: CompanionPrivacyGuard,
        capture: Optional[ScreenshotCapture] = None,
    ):
        super().__init__()
        self._seq = int(seq)
        self._config = config
        self._window_info = dict(window_info or {})
        self._context_text = str(context_text or "")
        self._privacy_guard = privacy_guard
        self._capture = capture

    def run(self) -> None:
        capture_released = False

        def release_capture_overlay() -> None:
            nonlocal capture_released
            if capture_released:
                return
            capture_released = True
            self.capture_done.emit(self._seq)

        try:
            bounds = self._window_info.get("bounds")
            if not isinstance(bounds, dict):
                release_capture_overlay()
                self.result_ready.emit(self._seq, {"ok": False, "error": "missing_bounds"})
                return

            capture = self._capture or ScreenshotCapture(self._config)
            result = capture.capture_window_region(
                bounds=bounds,
                optimize=True,
                include_data_url=False,
            )
            release_capture_overlay()
            if not result or not result.get("ok"):
                self.result_ready.emit(self._seq, {"ok": False, "error": "capture_failed"})
                return

            privacy = self._privacy_guard.review_post_capture(result, self._window_info)
            if not privacy.allowed:
                self.result_ready.emit(self._seq, {"ok": False, "privacy": privacy})
                return

            png_bytes = result.get("png_bytes")
            if not isinstance(png_bytes, (bytes, bytearray)) or not png_bytes:
                self.result_ready.emit(self._seq, {"ok": False, "error": "empty_capture"})
                return
            frame_hash = str(result.get("frame_hash") or "")
            image_data_url = ScreenshotCapture._build_data_url(bytes(png_bytes))
            if not image_data_url:
                self.result_ready.emit(self._seq, {"ok": False, "error": "empty_data_url"})
                return

            rec = CompanionRecommender(self._config)
            suggestions = rec.get_recommendations(
                image_data_url=image_data_url,
                context_text=self._context_text,
            )
            self.result_ready.emit(
                self._seq,
                {
                    "ok": True,
                    "frame_hash": frame_hash,
                    "suggestions": suggestions,
                },
            )
        except Exception as exc:
            release_capture_overlay()
            self.result_ready.emit(self._seq, {"ok": False, "error": str(exc)})
