import sys
import types

import pytest

import baodou_ai.platform as platform_module

from baodou_ai.platform.common import (
    build_browser_target_url,
    is_chrome_family_browser,
    rank_named_candidates,
)


def test_build_browser_target_url_uses_google_for_chrome_family():
    url = build_browser_target_url("罗翔说刑法 bilibili", True)

    assert url == "https://www.google.com/search?q=%E7%BD%97%E7%BF%94%E8%AF%B4%E5%88%91%E6%B3%95+bilibili"


def test_build_browser_target_url_uses_bing_for_non_chrome_family():
    url = build_browser_target_url("罗翔说刑法 bilibili", False)

    assert url == "https://www.bing.com/search?q=%E7%BD%97%E7%BF%94%E8%AF%B4%E5%88%91%E6%B3%95+bilibili"


def test_is_chrome_family_browser_accepts_chrome_variants():
    assert is_chrome_family_browser("com.google.Chrome")
    assert is_chrome_family_browser("ChromeHTML")
    assert is_chrome_family_browser("Chromium")
    assert not is_chrome_family_browser("Microsoft Edge")


def test_rank_named_candidates_returns_high_confidence_alias_suggestions():
    ranked = rank_named_candidates(
        "微信开发版",
        [
            {"name": "微信", "aliases": ["WeChat"]},
            {"name": "企业微信", "aliases": ["WeCom"]},
            {"name": "微信开发者工具", "aliases": []},
            {"name": "记事本", "aliases": []},
        ],
        max_results=3,
        cutoff=0.5,
    )

    ranked_names = [item["name"] for item in ranked]
    assert "微信" in ranked_names
    assert "微信开发者工具" in ranked_names
    assert "记事本" not in ranked_names


def test_score_name_match_supports_excel_alias():
    from baodou_ai.platform.common import score_name_match

    assert score_name_match("Excel", "Microsoft Excel") >= 1.0


def test_score_name_match_supports_common_macos_chinese_aliases():
    from baodou_ai.platform.common import score_name_match

    assert score_name_match("终端", "Terminal") >= 1.0
    assert score_name_match("备忘录", "Notes") >= 1.0
    assert score_name_match("预览", "Preview") >= 1.0
    assert score_name_match("谷歌浏览器", "Google Chrome") >= 1.0


def test_score_name_match_supports_pinyin_and_initials():
    from baodou_ai.platform.common import score_name_match

    assert score_name_match("beiwanglu", "Notes", ["备忘录"]) >= 1.0
    assert score_name_match("bwl", "Notes", ["备忘录"]) >= 1.0
    assert score_name_match("doubaoliulanqi", "Doubao", ["豆包浏览器"]) >= 1.0


def test_get_platform_adapter_returns_windows_adapter_on_windows(monkeypatch):
    class FakeWindowsAdapter:
        pass

    fake_module = types.ModuleType("baodou_ai.platform.windows")
    fake_module.WindowsAdapter = FakeWindowsAdapter

    monkeypatch.setattr(platform_module.platform_module, "system", lambda: "Windows")
    monkeypatch.setitem(sys.modules, "baodou_ai.platform.windows", fake_module)

    adapter = platform_module.get_platform_adapter()

    assert isinstance(adapter, FakeWindowsAdapter)


def test_get_platform_adapter_returns_macos_adapter_on_darwin(monkeypatch):
    class FakeMacOSAdapter:
        pass

    fake_module = types.ModuleType("baodou_ai.platform.macos")
    fake_module.MacOSAdapter = FakeMacOSAdapter

    monkeypatch.setattr(platform_module.platform_module, "system", lambda: "Darwin")
    monkeypatch.setitem(sys.modules, "baodou_ai.platform.macos", fake_module)

    adapter = platform_module.get_platform_adapter()

    assert isinstance(adapter, FakeMacOSAdapter)


def test_get_platform_adapter_raises_for_unsupported_platform(monkeypatch):
    monkeypatch.setattr(platform_module.platform_module, "system", lambda: "Linux")

    with pytest.raises(platform_module.UnsupportedPlatformError, match="Linux"):
        platform_module.get_platform_adapter()
