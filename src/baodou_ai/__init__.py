"""
CoView 同窗 - AI 智能控制系统

一个基于AI视觉模型的智能电脑控制系统，能够通过分析屏幕内容自动执行鼠标和键盘操作。
"""

__version__ = "2.0.0"
__author__ = "CoView Team"

from baodou_ai.core.config import Config
from baodou_ai.core.screenshot import ScreenshotCapture
from baodou_ai.core.coordinate import CoordinateMapper
from baodou_ai.core.automation import AutomationController
from baodou_ai.ai.client import AIClient
from baodou_ai.ai.parser import ResponseParser
from baodou_ai.api import BaodouAI, CoViewAI, execute_task

__all__ = [
    "Config",
    "ScreenshotCapture", 
    "CoordinateMapper",
    "AutomationController",
    "AIClient",
    "ResponseParser",
    "CoViewAI",
    "BaodouAI",
    "execute_task",
]
