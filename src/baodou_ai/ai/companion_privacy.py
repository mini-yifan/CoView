"""Local privacy guard for companion recommendations."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import cv2
import numpy as np

from baodou_ai.core.config import Config


PRIVACY_ALLOWED = "allowed"
PRIVACY_BLOCKED_PRE_CAPTURE = "blocked_pre_capture"
PRIVACY_BLOCKED_POST_CAPTURE = "blocked_post_capture"


DEFAULT_SENSITIVE_KEYWORDS = [
    "登录",
    "密码",
    "验证码",
    "支付",
    "钱包",
    "银行",
    "结算",
    "身份证",
    "password",
    "sign in",
    "signin",
    "login",
    "payment",
    "wallet",
    "bank",
    "verification code",
    "otp",
    "cvv",
    "checkout",
]

DEFAULT_APP_BLACKLIST = [
    "1password",
    "bitwarden",
    "dashlane",
    "lastpass",
    "keeper",
    "keychain access",
    "钥匙串访问",
    "密码",
    "authenticator",
    "google authenticator",
    "microsoft authenticator",
    "支付宝",
    "alipay",
    "微信支付",
    "pay",
    "paypal",
    "wallet",
    "银行",
    "bank",
    "招商银行",
    "工商银行",
    "建设银行",
    "农业银行",
    "中国银行",
    "remote desktop",
    "microsoft remote desktop",
    "anydesk",
    "teamviewer",
    "vnc",
    "vpn",
    "forticlient",
    "globalprotect",
    "bastion",
    "堡垒机",
]


@dataclass(frozen=True)
class CompanionPrivacyResult:
    status: str
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.status == PRIVACY_ALLOWED


class CompanionPrivacyGuard:
    """Two-stage local privacy guard for passive companion screenshots."""

    def __init__(self, config: Optional[Config] = None):
        self._config = config or Config()
        self._privacy_blocked_until = 0.0

    def refresh_config(self) -> None:
        """Kept for symmetry with companion config refresh."""

    @property
    def cooldown_seconds(self) -> int:
        cfg = self._privacy_config()
        return max(0, int(cfg.get("privacy_cooldown_seconds", 15) or 15))

    def is_cooling_down(self) -> bool:
        return time.monotonic() < float(self._privacy_blocked_until or 0.0)

    def cooldown_remaining_ms(self) -> int:
        remaining = float(self._privacy_blocked_until or 0.0) - time.monotonic()
        if remaining <= 0:
            return 0
        return max(1, int(remaining * 1000) + 1)

    def mark_blocked(self) -> None:
        cooldown = self.cooldown_seconds
        self._privacy_blocked_until = time.monotonic() + float(cooldown)

    def review_pre_capture(self, window_info: Dict[str, Any]) -> CompanionPrivacyResult:
        cfg = self._privacy_config()
        if not bool(cfg.get("enabled", True)):
            return CompanionPrivacyResult(PRIVACY_ALLOWED)
        if not bool(cfg.get("enable_pre_capture_guard", True)):
            return CompanionPrivacyResult(PRIVACY_ALLOWED)

        if bool(cfg.get("password_focus_guard_enabled", True)) and self._has_password_focus(window_info):
            return CompanionPrivacyResult(PRIVACY_BLOCKED_PRE_CAPTURE, "password_focus")

        if bool(cfg.get("app_blacklist_enabled", True)):
            app_text = self._join_text_fields(
                window_info,
                ("app_name", "bundle_id", "identifier", "process_name", "executable"),
            )
            matched = self._match_any(app_text, self._list_config("app_blacklist", DEFAULT_APP_BLACKLIST))
            if matched:
                return CompanionPrivacyResult(PRIVACY_BLOCKED_PRE_CAPTURE, f"app_blacklist:{matched}")

        if bool(cfg.get("title_keyword_guard_enabled", True)):
            title_text = self._join_text_fields(window_info, ("title", "browser_title"))
            matched = self._match_any(
                title_text,
                self._list_config("sensitive_keywords", DEFAULT_SENSITIVE_KEYWORDS),
            )
            if matched:
                return CompanionPrivacyResult(PRIVACY_BLOCKED_PRE_CAPTURE, f"title_keyword:{matched}")

        if bool(cfg.get("url_guard_enabled", True)):
            url_text = self._join_text_fields(window_info, ("url", "browser_url"))
            matched = self._match_any(
                url_text,
                self._list_config("sensitive_url_keywords", DEFAULT_SENSITIVE_KEYWORDS),
            )
            if matched:
                return CompanionPrivacyResult(PRIVACY_BLOCKED_PRE_CAPTURE, f"url_keyword:{matched}")

        return CompanionPrivacyResult(PRIVACY_ALLOWED)

    def review_post_capture(
        self,
        capture: Dict[str, Any],
        window_info: Optional[Dict[str, Any]] = None,
    ) -> CompanionPrivacyResult:
        cfg = self._privacy_config()
        if not bool(cfg.get("enabled", True)):
            return CompanionPrivacyResult(PRIVACY_ALLOWED)
        if not bool(cfg.get("enable_post_capture_guard", True)):
            return CompanionPrivacyResult(PRIVACY_ALLOWED)

        try:
            png_bytes = capture.get("png_bytes") if isinstance(capture, dict) else None
            if not isinstance(png_bytes, (bytes, bytearray)) or not png_bytes:
                return CompanionPrivacyResult(PRIVACY_BLOCKED_POST_CAPTURE, "missing_png_bytes")

            image = self._decode_review_image(bytes(png_bytes))
            if image is None:
                return CompanionPrivacyResult(PRIVACY_BLOCKED_POST_CAPTURE, "decode_failed")

            hint_text = self._join_text_fields(
                window_info or {},
                ("title", "browser_title", "url", "browser_url"),
            )
            hint_match = self._match_any(
                hint_text,
                self._list_config("sensitive_keywords", DEFAULT_SENSITIVE_KEYWORDS),
            )

            if self._has_qr_like_region(image):
                return CompanionPrivacyResult(PRIVACY_BLOCKED_POST_CAPTURE, "qr_like_region")
            if self._has_sensitive_form_layout(image, bool(hint_match)):
                reason = "sensitive_form_layout"
                if hint_match:
                    reason = f"{reason}:{hint_match}"
                return CompanionPrivacyResult(PRIVACY_BLOCKED_POST_CAPTURE, reason)
            return CompanionPrivacyResult(PRIVACY_ALLOWED)
        except Exception:
            return CompanionPrivacyResult(PRIVACY_BLOCKED_POST_CAPTURE, "review_exception")

    def _privacy_config(self) -> Dict[str, Any]:
        cfg = getattr(self._config, "companion_privacy_config", None)
        if isinstance(cfg, dict):
            return cfg
        return dict(getattr(self._config, "get", lambda *_: {})("companion_privacy_config", {}) or {})

    def _list_config(self, key: str, default: Iterable[str]) -> List[str]:
        value = self._privacy_config().get(key)
        if isinstance(value, list):
            items = [str(item or "").strip() for item in value]
            return [item for item in items if item]
        return list(default)

    @staticmethod
    def _join_text_fields(data: Dict[str, Any], keys: Iterable[str]) -> str:
        parts = []
        for key in keys:
            value = data.get(key) if isinstance(data, dict) else None
            if value is not None:
                text = str(value or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).lower()

    @staticmethod
    def _match_any(text: str, patterns: Iterable[str]) -> str:
        haystack = str(text or "").lower()
        if not haystack:
            return ""
        for pattern in patterns:
            needle = str(pattern or "").strip().lower()
            if needle and needle in haystack:
                return needle
        return ""

    @staticmethod
    def _has_password_focus(window_info: Dict[str, Any]) -> bool:
        if not isinstance(window_info, dict):
            return False
        bool_keys = (
            "is_password_focus",
            "password_focus",
            "focused_is_password",
            "focused_secure_text_entry",
        )
        if any(bool(window_info.get(key)) for key in bool_keys):
            return True
        focus_text = CompanionPrivacyGuard._join_text_fields(
            window_info,
            ("focused_role", "focused_subrole", "focused_control_type", "focused_description"),
        )
        return any(token in focus_text for token in ("password", "secure text", "securetextfield"))

    @staticmethod
    def _decode_review_image(png_bytes: bytes) -> Optional[np.ndarray]:
        data = np.frombuffer(png_bytes, dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None or image.size <= 0:
            return None
        h, w = image.shape[:2]
        max_side = max(w, h)
        if max_side > 480:
            scale = 480.0 / float(max_side)
            image = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))))
        return image

    @staticmethod
    def _has_qr_like_region(image_bgr: np.ndarray) -> bool:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        detector = getattr(cv2, "QRCodeDetector", None)
        if detector is not None:
            try:
                qr = detector()
                detected, _ = qr.detect(gray)
                if bool(detected):
                    return True
            except Exception:
                pass

        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(255 - binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        img_area = float(gray.shape[0] * gray.shape[1])
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < 56 or h < 56:
                continue
            ratio = w / float(h)
            if ratio < 0.75 or ratio > 1.33:
                continue
            area_ratio = (w * h) / img_area
            if area_ratio < 0.015 or area_ratio > 0.45:
                continue
            roi = binary[y : y + h, x : x + w]
            dark_ratio = float(np.mean(roi < 128))
            if dark_ratio < 0.18 or dark_ratio > 0.82:
                continue
            transitions_x = np.mean(roi[:, 1:] != roi[:, :-1])
            transitions_y = np.mean(roi[1:, :] != roi[:-1, :])
            if float(transitions_x + transitions_y) >= 0.16:
                return True
        return False

    @staticmethod
    def _has_sensitive_form_layout(image_bgr: np.ndarray, has_sensitive_hint: bool) -> bool:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 60, 160)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        img_h, img_w = gray.shape[:2]
        input_rects: List[Dict[str, float]] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < max(90, int(img_w * 0.16)) or h < 18:
                continue
            if w > img_w * 0.85 or h > 62:
                continue
            aspect = w / float(h)
            if 3.0 <= aspect <= 18:
                input_rects.append({
                    "x": float(x),
                    "y": float(y),
                    "w": float(w),
                    "h": float(h),
                    "cx": float(x + w / 2.0),
                })

        button_rects: List[Dict[str, float]] = []
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        colored = ((sat > 55) & (val > 55)).astype(np.uint8) * 255
        button_rects.extend(
            CompanionPrivacyGuard._find_button_like_rects(colored, img_w, img_h)
        )

        dark_blocks = (gray < 80).astype(np.uint8) * 255
        button_rects.extend(
            CompanionPrivacyGuard._find_button_like_rects(dark_blocks, img_w, img_h)
        )

        if len(input_rects) < 2 or not button_rects:
            return False

        input_rects.sort(key=lambda rect: (rect["y"], rect["x"]))
        center_tolerance = max(24.0, img_w * 0.06)
        width_tolerance = 0.35 if has_sensitive_hint else 0.25
        vertical_gap_limit = max(70.0, img_h * 0.22)

        for first_index, first in enumerate(input_rects):
            aligned_inputs = [first]
            for candidate in input_rects[first_index + 1 :]:
                if candidate["y"] <= first["y"]:
                    continue
                if candidate["y"] - first["y"] > vertical_gap_limit:
                    continue
                if abs(candidate["cx"] - first["cx"]) > center_tolerance:
                    continue
                width_delta = abs(candidate["w"] - first["w"]) / max(first["w"], candidate["w"])
                if width_delta > width_tolerance:
                    continue
                aligned_inputs.append(candidate)

            if len(aligned_inputs) < 2:
                continue

            bottom_input = max(aligned_inputs, key=lambda rect: rect["y"] + rect["h"])
            group_center = sum(rect["cx"] for rect in aligned_inputs) / len(aligned_inputs)
            group_width = sum(rect["w"] for rect in aligned_inputs) / len(aligned_inputs)
            group_bottom = bottom_input["y"] + bottom_input["h"]

            for button in button_rects:
                vertical_gap = button["y"] - group_bottom
                if vertical_gap < 8 or vertical_gap > max(95.0, img_h * 0.28):
                    continue
                if abs(button["cx"] - group_center) > max(36.0, img_w * 0.08):
                    continue
                if button["w"] > group_width * 1.15:
                    continue
                if button["w"] < group_width * 0.35:
                    continue
                return True

        return False

    @staticmethod
    def _find_button_like_rects(mask: np.ndarray, img_w: int, img_h: int) -> List[Dict[str, float]]:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rects: List[Dict[str, float]] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < max(80, int(img_w * 0.14)):
                continue
            if h < 22 or h > 70:
                continue
            if w > img_w * 0.75 or h > img_h * 0.22:
                continue
            aspect = w / float(h)
            if 2.0 <= aspect <= 12:
                rects.append({
                    "x": float(x),
                    "y": float(y),
                    "w": float(w),
                    "h": float(h),
                    "cx": float(x + w / 2.0),
                })
        return rects
