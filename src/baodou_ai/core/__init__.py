"""
核心功能模块

包含配置管理、截图、坐标处理、自动化控制等核心功能。
"""

from baodou_ai.core.config import Config
from baodou_ai.core.screenshot import ScreenshotCapture
from baodou_ai.core.coordinate import CoordinateMapper
from baodou_ai.core.automation import AutomationController

__all__ = [
    "Config",
    "ScreenshotCapture",
    "CoordinateMapper", 
    "AutomationController",
]
