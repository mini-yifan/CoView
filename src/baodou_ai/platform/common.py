"""
平台公共工具。
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Sequence
from urllib.parse import quote_plus

try:
    from pypinyin import Style, lazy_pinyin
except ImportError:  # pragma: no cover - 运行时依赖，测试环境缺失时降级
    Style = None
    lazy_pinyin = None


APP_ALIAS_GROUPS: Sequence[Sequence[str]] = (
    ("微信", "WeChat"),
    ("企业微信", "WeCom"),
    ("访达", "Finder"),
    ("系统设置", "System Settings", "Settings"),
    ("Edge", "Microsoft Edge"),
    ("谷歌浏览器", "Google Chrome", "Chrome", "Chromium"),
    ("Excel", "Microsoft Excel"),
    ("Word", "Microsoft Word"),
    ("PowerPoint", "Microsoft PowerPoint", "PPT"),
    ("Outlook", "Microsoft Outlook"),
    ("OneNote", "Microsoft OneNote"),
    ("备忘录", "Notes"),
    ("终端", "Terminal"),
    ("活动监视器", "Activity Monitor"),
    ("照片", "Photos"),
    ("预览", "Preview"),
    ("提醒事项", "Reminders"),
    ("日历", "Calendar"),
    ("音乐", "Music"),
    ("应用商店", "App Store"),
    ("文本编辑", "TextEdit"),
    ("计算器", "Calculator"),
    ("邮件", "Mail"),
    ("信息", "Messages"),
    ("地图", "Maps"),
    ("微信开发者工具", "WeChat DevTools", "wechatwebdevtools"),
    ("豆包", "Doubao"),
    ("豆包浏览器", "Doubao"),
    ("飞书", "Lark", "Feishu"),
)

GOOGLE_SEARCH_TEMPLATE = "https://www.google.com/search?q={query}"
BING_SEARCH_TEMPLATE = "https://www.bing.com/search?q={query}"


def normalize_lookup_text(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return "".join(ch for ch in text if ch.isalnum())


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in value)


def get_pinyin_variants(value: Any) -> List[str]:
    text = str(value or "").strip()
    if not text or lazy_pinyin is None or Style is None or not _contains_cjk(text):
        return []

    try:
        syllables = lazy_pinyin(text, style=Style.NORMAL, errors="default")
    except Exception:
        return []

    cleaned = [str(item).strip().casefold() for item in syllables if str(item).strip()]
    if not cleaned:
        return []

    full = "".join(cleaned)
    initials = "".join(item[0] for item in cleaned if item)
    variants = [variant for variant in (full, initials) if variant]
    return sorted(set(variants))


def get_alias_variants(name: Any) -> List[str]:
    normalized = normalize_lookup_text(name)
    if not normalized:
        return []

    variants = {str(name).strip()}
    for group in APP_ALIAS_GROUPS:
        normalized_group = {normalize_lookup_text(item) for item in group}
        if normalized in normalized_group:
            variants.update(group)
    for base_variant in list(variants):
        variants.update(get_pinyin_variants(base_variant))
    return sorted(variants)


def score_name_match(query: Any, candidate_name: Any, extra_names: Iterable[str] | None = None) -> float:
    query_variants = get_alias_variants(query)
    candidate_variants = get_alias_variants(candidate_name)
    if extra_names:
        for item in extra_names:
            candidate_variants.extend(get_alias_variants(item))

    if not query_variants or not candidate_variants:
        return 0.0

    best = 0.0
    for query_variant in query_variants:
        query_normalized = normalize_lookup_text(query_variant)
        for candidate_variant in candidate_variants:
            candidate_normalized = normalize_lookup_text(candidate_variant)
            if not query_normalized or not candidate_normalized:
                continue
            if query_normalized == candidate_normalized:
                return 1.0
            if (
                query_normalized in candidate_normalized
                or candidate_normalized in query_normalized
            ):
                best = max(best, 0.92)
                continue
            best = max(
                best,
                SequenceMatcher(None, query_normalized, candidate_normalized).ratio(),
            )
    return best


def rank_named_candidates(
    query: str,
    candidates: Iterable[Dict[str, Any]],
    *,
    max_results: int = 3,
    cutoff: float = 0.72,
) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for candidate in candidates:
        name = str(candidate.get("name", "")).strip()
        if not name:
            continue
        score = score_name_match(query, name, candidate.get("aliases"))
        if score < cutoff:
            continue
        ranked.append({**candidate, "score": score})

    ranked.sort(key=lambda item: (-item["score"], normalize_lookup_text(item["name"])))
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for candidate in ranked:
        normalized_name = normalize_lookup_text(candidate["name"])
        if normalized_name in seen:
            continue
        seen.add(normalized_name)
        deduped.append(candidate)
        if len(deduped) >= max_results:
            break
    return deduped


def is_chrome_family_browser(*values: Any) -> bool:
    normalized_values = {normalize_lookup_text(value) for value in values if value}
    normalized_values.discard("")
    if not normalized_values:
        return False

    chrome_markers = {
        "googlechrome",
        "chromebeta",
        "chromecanary",
        "chromium",
        "chromehtml",
        "chrome",
        "chromebeta",
        "chromecanaryexe",
        "chromiumexe",
        "chromeexe",
    }

    if any("edge" in value for value in normalized_values):
        return False

    return any(
        value in chrome_markers
        or "googlechrome" in value
        or value.startswith("googlechrome")
        or value.startswith("chromium")
        or value.startswith("chromehtml")
        for value in normalized_values
    )


def build_browser_target_url(query: str, is_chrome_family: bool) -> str:
    template = GOOGLE_SEARCH_TEMPLATE if is_chrome_family else BING_SEARCH_TEMPLATE
    return template.format(query=quote_plus(str(query or "").strip()))
