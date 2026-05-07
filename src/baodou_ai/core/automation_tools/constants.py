"""Shared constants for automation tools."""

from __future__ import annotations

try:
    import tiktoken
except Exception:  # pragma: no cover - dependency fallback matches legacy behavior
    tiktoken = None

from baodou_ai.runtime_paths import MEMORY_FILE

PAGE_EXTRACT_DIR = "imgs/page_extract"
DOCUMENT_EXTRACT_DIR = "imgs/doc_extract"
DOCUMENT_ANCHOR_DIR = "imgs/doc_anchor"
DOCUMENT_CHUNK_TARGET_TOKENS = 2200
DOCUMENT_CHUNK_MIN_TOKENS = 2000
DOCUMENT_CHUNK_MAX_TOKENS = 2500
DOCUMENT_SEARCH_DEFAULT_TOP_K = 3
DOCUMENT_SEARCH_MAX_TOP_K = 8
DOCUMENT_SEARCH_CODE_CONTEXT_LINES = 8
DOCUMENT_VIEW_FOLLOW_SCAN_WINDOW = 200
DOCUMENT_VIEW_FOLLOW_ANCHOR_LENGTH = 20
DOCUMENT_SUPPORTED_DOCUMENT_APP_NAMES = (
    "Microsoft Word",
    "Microsoft Excel",
    "TextEdit",
    "Preview",
    "WPS",
)
DOCUMENT_SUPPORTED_IDE_APP_NAMES = (
    "Visual Studio Code",
    "Cursor",
    "Windsurf",
    "IntelliJ IDEA",
    "PyCharm",
    "WebStorm",
    "GoLand",
    "CLion",
    "Android Studio",
    "Sublime Text",
    "Xcode",
    "TRAE",
    "TRAE CN",
    "TRAE SOLO CN",
)
DOCUMENT_SUPPORTED_APP_NAMES_TEXT = "、".join(
    DOCUMENT_SUPPORTED_DOCUMENT_APP_NAMES + DOCUMENT_SUPPORTED_IDE_APP_NAMES
)
DOCUMENT_ANCHOR_LEADING_SKIP_CHARS = (
    " \t\r\n"
    "`~!@#$%^&*()-_=+[{]}\\|;:'\",<.>/?"
    "·•，。！？；：、"
    "（）()【】《》「」『』"
    "“”‘’—–-"
)
DOCUMENT_ANCHOR_WEAK_PUNCTUATION_CHARS = "，,、\"'“”‘’"


def automation_exports():
    """Return the public automation module so monkeypatched constants stay compatible."""
    from baodou_ai.core import automation

    return automation
