import json

import pytest

from baodou_ai.core.update_checker import (
    LATEST_RELEASE_API_URL,
    RELEASES_URL,
    UpdateCheckError,
    _compare_versions,
    check_for_updates,
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_check_for_updates_detects_newer_github_release():
    calls = []

    def fake_urlopen(request, timeout, context):
        calls.append((request, timeout, context))
        return FakeResponse(
            {
                "tag_name": "v2.1.0",
                "html_url": "https://github.com/mini-yifan/CoView/releases/tag/v2.1.0",
            }
        )

    result = check_for_updates("2.0.0", urlopen=fake_urlopen)

    assert result.update_available is True
    assert result.latest_version == "2.1.0"
    assert result.release_url.endswith("/v2.1.0")
    assert calls[0][0].full_url == LATEST_RELEASE_API_URL


def test_check_for_updates_uses_releases_page_when_html_url_missing():
    def fake_urlopen(request, timeout, context):
        return FakeResponse({"tag_name": "v2.0.0"})

    result = check_for_updates("2.0.0", urlopen=fake_urlopen)

    assert result.update_available is False
    assert result.release_url == RELEASES_URL


def test_check_for_updates_rejects_missing_tag_name():
    def fake_urlopen(request, timeout, context):
        return FakeResponse({"html_url": "https://example.test/release"})

    with pytest.raises(UpdateCheckError):
        check_for_updates("2.0.0", urlopen=fake_urlopen)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("2.0.1", "2.0.0", 1),
        ("v2.0.0", "2.0", 0),
        ("2.0.0", "2.1.0", -1),
        ("2.10.0", "2.9.9", 1),
    ],
)
def test_compare_versions(left, right, expected):
    assert _compare_versions(left, right) == expected
