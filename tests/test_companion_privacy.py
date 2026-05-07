import time

import cv2
import numpy as np

from baodou_ai.ai.companion_privacy import (
    PRIVACY_ALLOWED,
    PRIVACY_BLOCKED_POST_CAPTURE,
    PRIVACY_BLOCKED_PRE_CAPTURE,
    CompanionPrivacyGuard,
)
from baodou_ai.core.config import Config


def _png_bytes(image_bgr):
    ok, buffer = cv2.imencode(".png", image_bgr)
    assert ok
    return buffer.tobytes()


def _guard(**privacy_overrides):
    config = Config.create_isolated()
    for key, value in privacy_overrides.items():
        config.set(f"companion_privacy_config.{key}", value)
    return CompanionPrivacyGuard(config)


def test_pre_capture_blocks_blacklisted_app():
    guard = _guard()

    result = guard.review_pre_capture({
        "app_name": "1Password",
        "bundle_id": "com.1password.1password",
        "pid": 100,
        "title": "Home",
    })

    assert result.status == PRIVACY_BLOCKED_PRE_CAPTURE
    assert "app_blacklist" in result.reason


def test_pre_capture_blocks_title_and_url_keywords():
    guard = _guard()

    title_result = guard.review_pre_capture({"pid": 100, "title": "验证码登录"})
    url_result = guard.review_pre_capture({"pid": 100, "url": "https://example.com/checkout"})

    assert title_result.status == PRIVACY_BLOCKED_PRE_CAPTURE
    assert "title_keyword" in title_result.reason
    assert url_result.status == PRIVACY_BLOCKED_PRE_CAPTURE
    assert "url_keyword" in url_result.reason


def test_pre_capture_allows_non_sensitive_metadata():
    guard = _guard()

    result = guard.review_pre_capture({
        "app_name": "Pages",
        "bundle_id": "com.apple.iWork.Pages",
        "pid": 100,
        "title": "项目计划",
    })

    assert result.status == PRIVACY_ALLOWED


def test_post_capture_allows_password_dots_without_form_layout():
    guard = _guard()
    image = np.full((220, 420, 3), 255, dtype=np.uint8)
    for x in range(95, 180, 18):
        cv2.circle(image, (x, 102), 5, (0, 0, 0), -1)

    result = guard.review_post_capture({"png_bytes": _png_bytes(image)}, {})

    assert result.status == PRIVACY_ALLOWED


def test_post_capture_blocks_sensitive_form_layout():
    guard = _guard()
    image = np.full((260, 460, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (70, 70), (390, 108), (130, 130, 130), 2)
    cv2.rectangle(image, (70, 130), (390, 168), (130, 130, 130), 2)
    cv2.rectangle(image, (120, 190), (340, 230), (30, 90, 210), -1)

    result = guard.review_post_capture({"png_bytes": _png_bytes(image)}, {})

    assert result.status == PRIVACY_BLOCKED_POST_CAPTURE
    assert result.reason.startswith("sensitive_form_layout")


def test_post_capture_allows_unaligned_content_cards():
    guard = _guard()
    image = np.full((320, 520, 3), 248, dtype=np.uint8)
    cv2.rectangle(image, (40, 50), (210, 130), (210, 230, 250), -1)
    cv2.rectangle(image, (250, 60), (470, 170), (240, 210, 220), -1)
    cv2.rectangle(image, (55, 155), (190, 190), (30, 90, 210), -1)
    cv2.rectangle(image, (265, 210), (430, 250), (40, 40, 40), -1)

    result = guard.review_post_capture({"png_bytes": _png_bytes(image)}, {})

    assert result.status == PRIVACY_ALLOWED


def test_post_capture_decode_failure_blocks():
    guard = _guard()

    result = guard.review_post_capture({"png_bytes": b"not a png"}, {})

    assert result.status == PRIVACY_BLOCKED_POST_CAPTURE
    assert result.reason == "decode_failed"


def test_privacy_cooldown(monkeypatch):
    guard = _guard(privacy_cooldown_seconds=15)
    now = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: now)

    guard.mark_blocked()

    assert guard.is_cooling_down()
    assert guard.cooldown_remaining_ms() > 14000

    monkeypatch.setattr(time, "monotonic", lambda: now + 16)
    assert not guard.is_cooling_down()
