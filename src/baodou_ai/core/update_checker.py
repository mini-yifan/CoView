"""GitHub Releases based update checking."""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

import certifi

GITHUB_OWNER = "mini-yifan"
GITHUB_REPO = "CoView"
RELEASES_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
LATEST_RELEASE_API_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    release_url: str
    update_available: bool


class UpdateCheckError(RuntimeError):
    """Raised when the latest release cannot be fetched or parsed."""


def check_for_updates(
    current_version: str,
    *,
    timeout: float = 8.0,
    urlopen: Optional[Callable[..., Any]] = None,
) -> UpdateCheckResult:
    """Return update information from the repository's latest GitHub Release."""

    opener = urlopen or urllib.request.urlopen
    request = urllib.request.Request(
        LATEST_RELEASE_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"CoView/{current_version}",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where())

    try:
        with opener(request, timeout=timeout, context=context) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise UpdateCheckError(str(exc)) from exc

    if not isinstance(payload, dict):
        raise UpdateCheckError("GitHub release response is not an object.")

    tag_name = str(payload.get("tag_name") or "").strip()
    latest_version = _normalize_version(tag_name)
    if not latest_version:
        raise UpdateCheckError("GitHub release response does not include a tag_name.")

    release_url = str(payload.get("html_url") or "").strip() or RELEASES_URL
    return UpdateCheckResult(
        current_version=current_version,
        latest_version=latest_version,
        release_url=release_url,
        update_available=_compare_versions(latest_version, current_version) > 0,
    )


def _normalize_version(version: str) -> str:
    version = version.strip()
    if version.lower().startswith("v"):
        version = version[1:]
    return version


def _compare_versions(left: str, right: str) -> int:
    left_key = _version_key(left)
    right_key = _version_key(right)
    max_len = max(len(left_key), len(right_key))
    left_key = left_key + (0,) * (max_len - len(left_key))
    right_key = right_key + (0,) * (max_len - len(right_key))
    if left_key == right_key:
        return 0
    return 1 if left_key > right_key else -1


def _version_key(version: str) -> Tuple[int, ...]:
    public_version = re.split(r"[-+]", _normalize_version(version), maxsplit=1)[0]
    parts = []
    for part in public_version.split("."):
        match = re.match(r"\d+", part)
        if not match:
            break
        parts.append(int(match.group(0)))
    return tuple(parts)
