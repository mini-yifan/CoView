"""
自动化控制模块

提供鼠标和键盘自动化操作功能。
"""

from __future__ import annotations

import platform
import time
from typing import Any, Callable, Dict, List, Optional

import pyautogui
import pyperclip

from baodou_ai.code_agent.manager import JobManager
from baodou_ai.core.automation_tools.background_tools import BackgroundToolsMixin
from baodou_ai.core.automation_tools.constants import (
    DOCUMENT_ANCHOR_DIR,
    DOCUMENT_ANCHOR_LEADING_SKIP_CHARS,
    DOCUMENT_ANCHOR_WEAK_PUNCTUATION_CHARS,
    DOCUMENT_CHUNK_MAX_TOKENS,
    DOCUMENT_CHUNK_MIN_TOKENS,
    DOCUMENT_CHUNK_TARGET_TOKENS,
    DOCUMENT_EXTRACT_DIR,
    DOCUMENT_SEARCH_CODE_CONTEXT_LINES,
    DOCUMENT_SEARCH_DEFAULT_TOP_K,
    DOCUMENT_SEARCH_MAX_TOP_K,
    DOCUMENT_SUPPORTED_APP_NAMES_TEXT,
    DOCUMENT_SUPPORTED_DOCUMENT_APP_NAMES,
    DOCUMENT_SUPPORTED_IDE_APP_NAMES,
    DOCUMENT_VIEW_FOLLOW_ANCHOR_LENGTH,
    DOCUMENT_VIEW_FOLLOW_SCAN_WINDOW,
    MEMORY_FILE,
    PAGE_EXTRACT_DIR,
)
from baodou_ai.core.automation_tools.desktop_tools import DesktopToolsMixin
from baodou_ai.core.automation_tools.document_reader import DocumentReaderMixin
from baodou_ai.core.automation_tools.file_tools import FileToolsMixin
from baodou_ai.core.automation_tools.page_reader import PageReaderMixin
from baodou_ai.core.automation_tools.runtime import RuntimeMixin, ToolContext, ToolOutcome
from baodou_ai.core.config import Config
from baodou_ai.core.coordinate import CoordinateMapper
from baodou_ai.core.screenshot import ScreenshotCapture
from baodou_ai.core.settler import ScreenSettler, SettleResult
from baodou_ai.platform import get_platform_adapter


class AutomationController(
    RuntimeMixin,
    DesktopToolsMixin,
    FileToolsMixin,
    PageReaderMixin,
    DocumentReaderMixin,
    BackgroundToolsMixin,
):
    """自动化控制类"""

    def __init__(self, config: Optional[Config] = None):
        self._config = config or Config()
        self._coordinate_mapper = CoordinateMapper(self._config)
        self._platform_adapter = get_platform_adapter()
        self._current_os = platform.system()
        self._screenshot = ScreenshotCapture(self._config)
        self._settler = ScreenSettler(self._screenshot, self._config)
        self._last_settle_result: Optional[SettleResult] = None
        self._hide_windows_callback: Optional[Callable] = None
        self._show_windows_callback: Optional[Callable] = None
        self._held_modifier_keys: List[str] = []
        self._held_modifier_since_step: Optional[int] = None
        self._held_modifier_since_time: Optional[float] = None
        self._page_extract_sequence = 0
        self._page_reader_state: Dict[str, Any] = {}
        self._document_extract_sequence = 0
        self._document_anchor_sequence = 0
        self._document_reader_state: Dict[str, Any] = {}
        self._job_manager: Optional[JobManager] = None

        mouse_config = self._config.mouse_config
        pyautogui.FAILSAFE = mouse_config.get("failsafe", False)
