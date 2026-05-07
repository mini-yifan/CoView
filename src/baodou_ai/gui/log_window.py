"""
日志窗口模块

提供后台日志显示功能。
"""

import io
import sys
from typing import List, Optional, Tuple

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from baodou_ai.core.screenshot import CAPTURE_EXCLUDE_PROPERTY
from baodou_ai.gui.styles import Styles
from baodou_ai.platform import get_platform_adapter


class LogSignalHandler(QObject):
    """处理日志信号的类"""
    
    log_signal = pyqtSignal(str, str)
    
    def __init__(self, log_window: "LogWindow"):
        super().__init__()
        self.log_window = log_window
        self.log_signal.connect(self.log_window.append_log)


class LogStream(io.StringIO):
    """自定义输出流"""
    
    ERROR_KEYWORDS = ("错误", "失败", "Traceback", "Exception", "Error")
    WARNING_KEYWORDS = ("警告", "warning", "Warning")

    def __init__(self, signal_handler: LogSignalHandler, default_log_type: str = "normal"):
        super().__init__()
        self.signal_handler = signal_handler
        self.buffer = ""
        self.default_log_type = default_log_type

    def _detect_log_type(self, text: str) -> str:
        """根据流类型和文本内容推断日志级别。"""
        if self.default_log_type != "normal":
            return self.default_log_type

        normalized = text.strip()
        if any(keyword in normalized for keyword in self.ERROR_KEYWORDS):
            return "error"
        if any(keyword in normalized for keyword in self.WARNING_KEYWORDS):
            return "warning"
        return "normal"
    
    def write(self, text: str) -> int:
        super().write(text)
        
        self.buffer += text
        if "\n" in self.buffer:
            lines = self.buffer.split("\n")
            self.buffer = lines[-1]
            
            for line in lines[:-1]:
                if line:
                    try:
                        self.signal_handler.log_signal.emit(
                            line + "\n",
                            self._detect_log_type(line),
                        )
                    except Exception:
                        pass
        
        return len(text)
    
    def flush(self) -> None:
        if self.buffer:
            try:
                self.signal_handler.log_signal.emit(
                    self.buffer,
                    self._detect_log_type(self.buffer),
                )
                self.buffer = ""
            except Exception:
                pass


class LogWindow(QWidget):
    """日志窗口类"""

    _LOG_FLUSH_INTERVAL_MS = 33
    
    _instance: Optional["LogWindow"] = None
    
    def __new__(cls) -> "LogWindow":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        super().__init__()
        self._initialized = True
        self._platform_adapter = get_platform_adapter()
        
        self.signal_handler = LogSignalHandler(self)
        
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
        self.stdout_stream = LogStream(self.signal_handler, "normal")
        self.stderr_stream = LogStream(self.signal_handler, "error")
        
        sys.stdout = self.stdout_stream
        sys.stderr = self.stderr_stream
        
        self.log_count = 0
        self.max_log_lines = 1000
        self._pending_log_entries: List[Tuple[str, str]] = []
        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setInterval(self._LOG_FLUSH_INTERVAL_MS)
        self._log_flush_timer.timeout.connect(self._flush_pending_logs)
        
        self._init_ui()
        self._setup_window()
    
    def _init_ui(self) -> None:
        self.setWindowTitle("后台日志")
        self.setGeometry(800, 100, 640, 440)
        
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Window)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 14, 16, 14)
        
        title_label = QLabel("📋 后台执行日志")
        title_font = QFont("Microsoft YaHei", 15, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(Styles.TITLE_LABEL_STYLE)
        main_layout.addWidget(title_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_font = QFont("Consolas", 10)
        self.log_text.setFont(log_font)
        self.log_text.setStyleSheet(Styles.LOG_TEXT_STYLE)
        main_layout.addWidget(self.log_text)
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.clear_btn = QPushButton("🗑️ 清空日志")
        self.clear_btn.clicked.connect(self.clear_log)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setStyleSheet(Styles.CLEAR_BUTTON_STYLE)
        button_layout.addWidget(self.clear_btn)
        
        self.save_btn = QPushButton("💾 保存日志")
        self.save_btn.clicked.connect(self.save_log)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(Styles.SAVE_BUTTON_STYLE)
        button_layout.addWidget(self.save_btn)
        
        button_layout.addStretch()
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
        self.setStyleSheet(Styles.LOG_WINDOW_STYLE)
        
        self.append_log("=== 后台日志窗口已启动 ===\n", "info")
        self._flush_pending_logs(force=True)
    
    def _setup_window(self) -> None:
        """设置窗口属性"""
        self.setProperty(CAPTURE_EXCLUDE_PROPERTY, True)
        self._platform_adapter.setup_window(self)
        self._platform_adapter.prevent_screenshot(self)

    def showEvent(self, event) -> None:
        """窗口展示后再次补应用防截屏设置。"""
        super().showEvent(event)
        self._platform_adapter.prevent_screenshot(self)
    
    def is_minimized(self) -> bool:
        """检查窗口是否最小化"""
        return self.isMinimized()
    
    def enter_transparent_mode(self) -> None:
        """进入透明穿透模式"""
        if not self.is_minimized():
            self._platform_adapter.enter_transparent_mode(self)
    
    def exit_transparent_mode(self) -> None:
        """退出透明穿透模式"""
        if not self.is_minimized():
            self._platform_adapter.exit_transparent_mode(self)
    
    def append_log(self, text: str, log_type: str = "normal") -> None:
        """添加日志，使用短周期缓冲减少高频 UI 刷新。"""
        self._pending_log_entries.append((text, log_type))
        if not self._log_flush_timer.isActive():
            self._log_flush_timer.start()

    def _append_log_immediately(self, text: str, log_type: str = "normal") -> None:
        """立即追加日志到 UI。"""
        color_map = {
            "error": "#f87171",
            "warning": "#fbbf24",
            "info": "#818cf8",
            "normal": "#e2e8f0",
        }
        
        color = color_map.get(log_type, "#eeffff")
        plain_text = text

        if log_type != "normal":
            text = f'<span style="color:{color}">{text}</span>'
        
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        if log_type != "normal":
            self.log_text.insertHtml(text)
        else:
            self.log_text.insertPlainText(text)
        
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()
        
        self.log_count += plain_text.count("\n")
        if self.log_count > self.max_log_lines:
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 
                              self.max_log_lines // 4)
            cursor.removeSelectedText()
            self.log_count -= self.max_log_lines // 4

    def _flush_pending_logs(self, force: bool = False) -> None:
        """批量刷出缓冲日志。"""
        if not self._pending_log_entries:
            if force:
                self._log_flush_timer.stop()
            return

        pending_entries = self._pending_log_entries
        self._pending_log_entries = []
        self._log_flush_timer.stop()

        for text, log_type in pending_entries:
            self._append_log_immediately(text, log_type)
    
    def clear_log(self) -> None:
        """清空日志"""
        self._pending_log_entries = []
        self._log_flush_timer.stop()
        self.log_text.clear()
        self.log_count = 0
        self.append_log("=== 日志已清空 ===\n", "info")
        self._flush_pending_logs(force=True)
    
    def save_log(self) -> None:
        """保存日志"""
        try:
            self.stdout_stream.flush()
            self.stderr_stream.flush()
            self._flush_pending_logs(force=True)
            with open("coview_log.txt", "w", encoding="utf-8") as f:
                f.write(self.log_text.toPlainText())
            self.append_log("日志已保存到 coview_log.txt\n", "info")
            self._flush_pending_logs(force=True)
        except Exception as e:
            self.append_log(f"保存日志失败: {str(e)}\n", "error")
            self._flush_pending_logs(force=True)
    
    def closeEvent(self, event) -> None:
        """关闭窗口时恢复原始输出流"""
        self.stdout_stream.flush()
        self.stderr_stream.flush()
        self._flush_pending_logs(force=True)
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        event.accept()
    
    @classmethod
    def get_instance(cls) -> Optional["LogWindow"]:
        """获取日志窗口单例"""
        app = QApplication.instance()
        if app is None:
            return None
        return cls()


def init_log_window() -> Optional[LogWindow]:
    """初始化日志窗口"""
    app = QApplication.instance()
    if app is None:
        return None
    
    log_window = LogWindow.get_instance()
    if log_window:
        log_window.show()
    return log_window


def get_log_window() -> Optional[LogWindow]:
    """获取日志窗口实例"""
    return LogWindow.get_instance()
