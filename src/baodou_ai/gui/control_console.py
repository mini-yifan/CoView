"""
设置窗口（macOS 系统设置风格）。

左侧侧边栏导航 + 右侧 QStackedWidget 内容区。
视觉风格与悬浮球显示框统一为黑白灰极简风格。
"""

from __future__ import annotations

import platform
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    Qt,
    QThread,
    QTimer,
    QUrl,
    pyqtProperty,
    pyqtSignal,
)
from PyQt5.QtGui import QBrush, QColor, QDesktopServices, QFont, QPainter, QPainterPath
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from baodou_ai import __version__
from baodou_ai.code_agent.manager import JobManager
from baodou_ai.core.config import Config
from baodou_ai.core.screenshot import CAPTURE_EXCLUDE_PROPERTY
from baodou_ai.core.update_checker import (
    RELEASES_URL,
    UpdateCheckError,
    UpdateCheckResult,
    check_for_updates,
)
from baodou_ai.gui.control_console_jobs import CodeAgentJobsPanel
from baodou_ai.gui.i18n import set_locale, t, translate
from baodou_ai.gui.runtime_log import RuntimeLogBuffer
from baodou_ai.platform import get_platform_adapter

# 黑白灰极简风格（与悬浮球显示框统一）
PALETTE = {
    "bg": "#F5F5F7",
    "card": "#E8E8ED",
    "text_primary": "#111111",
    "text_secondary": "#707070",
    "text_muted": "#999999",
    "input_bg": "#FFFFFF",
    "input_border": "#BABCC5",
    "input_focus": "#111111",
    "divider": "#C9CBD3",
    "sidebar_selected_bg": "#111111",
    "sidebar_selected_text": "#FFFFFF",
    "sidebar_hover_bg": "#F0F0F0",
    "log_bg": "#1E293B",
    "log_text": "#E2E8F0",
    "log_info": "#818CF8",
    "log_warning": "#FBBF24",
    "log_error": "#F87171",
    "log_success": "#34D399",
    "status_ready": "#10B981",
    "status_running": "#3B82F6",
    "status_stopping": "#F59E0B",
    "status_error": "#EF4444",
}


CODE_AGENT_PROVIDER_OPTIONS = [
    "codex",
    "claude",
    "kimi",
    "qwen",
    "codebuddy",
]


MAIN_SIDEBAR_ITEMS = [
    ("general", "sidebar_general"),
    ("floating", "sidebar_floating"),
    ("voice", "sidebar_voice"),
    ("companion", "sidebar_companion"),
    ("advanced", "sidebar_advanced"),
    ("code_agent", "sidebar_code_agent"),
    ("runtime", "sidebar_runtime"),
]

FOOTER_SIDEBAR_ITEMS = [
    ("about", "sidebar_about"),
    ("language", "sidebar_language"),
]


class _NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event) -> None:
        event.ignore()


class _NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event) -> None:
        event.ignore()


class _NoWheelComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._original_texts: List[str] = []
        self._display_texts: List[str] = []

    def wheelEvent(self, event) -> None:
        event.ignore()

    def set_items(self, values: List[str], display_texts: Optional[List[str]] = None) -> None:
        self._original_texts = list(values)
        self._display_texts = list(display_texts or values)
        super().clear()
        super().addItems(self._display_texts)

    def addItems(self, texts: List[str]) -> None:
        self.set_items(texts)

    def clear(self) -> None:
        self._original_texts = []
        self._display_texts = []
        super().clear()

    def currentText(self) -> str:
        idx = self.currentIndex()
        if 0 <= idx < len(self._original_texts):
            return self._original_texts[idx]
        return super().currentText()

    def raw_items(self) -> List[str]:
        return list(self._original_texts)

    def setCurrentText(self, text: str) -> None:
        for i, raw in enumerate(self._original_texts):
            if raw == text:
                self.setCurrentIndex(i)
                return
        super().setCurrentText(text)

    def showPopup(self) -> None:
        current = self.currentIndex()
        for i in range(self.count()):
            text = self._display_texts[i]
            prefix = "✓  " if i == current else "    "
            self.setItemText(i, prefix + text)
        super().showPopup()

    def hidePopup(self) -> None:
        super().hidePopup()
        for i in range(self.count()):
            self.setItemText(i, self._display_texts[i])


class ToggleSwitch(QCheckBox):
    """自定义系统风格胶囊滑动开关"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setFixedSize(48, 28)
        self.setCursor(Qt.PointingHandCursor)
        self._thumb_position = 0.0

        self._animation = QPropertyAnimation(self, b"thumb_position", self)
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)
        self._animation.setDuration(150)

        self.toggled.connect(self._on_toggled)

    def _track_rect(self) -> QRectF:
        # 留出更宽松的安全边距，避免右端圆角在抗锯齿下显得被切掉。
        return QRectF(1.5, 1.5, self.width() - 3.0, self.height() - 3.0)

    def _thumb_diameter(self) -> float:
        return self._track_rect().height() - 4.0

    def _thumb_range(self) -> Tuple[float, float]:
        track = self._track_rect()
        thumb_diameter = self._thumb_diameter()
        start = track.left() + 2.0
        end = track.right() - 2.0 - thumb_diameter
        return start, end

    @pyqtProperty(float)
    def thumb_position(self) -> float:
        return self._thumb_position

    @thumb_position.setter
    def thumb_position(self, pos: float) -> None:
        self._thumb_position = pos
        self.update()

    def _on_toggled(self, checked: bool) -> None:
        start, end = self._thumb_range()
        self._animation.stop()
        self._animation.setStartValue(self._thumb_position)
        self._animation.setEndValue(end if checked else start)
        self._animation.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        start, end = self._thumb_range()
        self._thumb_position = end if self.isChecked() else start
        self.update()

    def hitButton(self, pos: QPoint) -> bool:
        return self.contentsRect().contains(pos)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self._track_rect()
        checked = self.isChecked()

        # Background
        bg_color = QColor("#111111") if checked else QColor("#D1D1D6")
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.fillPath(path, QBrush(bg_color))

        # Thumb
        thumb_diameter = self._thumb_diameter()
        thumb_rect = QRectF(
            self._thumb_position,
            rect.top() + 2.0,
            thumb_diameter,
            thumb_diameter,
        )

        # Shadow
        painter.setBrush(QColor(0, 0, 0, 30))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(thumb_rect.translated(0, 1))

        # White circle
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(thumb_rect)

        painter.end()


class SectionCard(QFrame):
    """系统设置风格的分组卡片。"""

    def __init__(self, title: str, description: str = "", parent=None) -> None:
        super().__init__(parent)
        self._row_count = 0
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {PALETTE['card']};
                border: 1px solid {PALETTE['divider']};
                border-radius: 18px;
            }}
            """)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setSpacing(4)
        header_layout.setContentsMargins(20, 18, 20, 12)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {PALETTE['text_primary']};
                font-size: 15px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
            """)
        header_layout.addWidget(title_label)

        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet(f"""
                QLabel {{
                    color: {PALETTE['text_secondary']};
                    font-size: 12px;
                    line-height: 1.5;
                    background: transparent;
                    border: none;
                }}
                """)
            header_layout.addWidget(desc_label)

        layout.addWidget(header)

        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(0)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.content_layout)

    def add_row(
        self,
        title_text: str,
        widget: QWidget,
        description: str = "",
        *,
        control_width: int = 220,
    ) -> None:
        if isinstance(widget, QCheckBox) and widget.text():
            if not description:
                description = widget.text()
            widget.setText("")

        if self._row_count > 0:
            separator = QFrame()
            separator.setFixedHeight(1)
            separator.setStyleSheet(
                f"background-color: {PALETTE['divider']}; border: none; margin: 0 20px;"
            )
            self.content_layout.addWidget(separator)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setSpacing(16)
        row_layout.setContentsMargins(20, 16, 20, 16)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        title_label = QLabel(title_text)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {PALETTE['text_primary']};
                font-size: 14px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
            """)
        text_layout.addWidget(title_label)

        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet(f"""
                QLabel {{
                    color: {PALETTE['text_secondary']};
                    font-size: 12px;
                    line-height: 1.5;
                    background: transparent;
                    border: none;
                }}
                """)
            text_layout.addWidget(desc_label)

        row_layout.addLayout(text_layout, 1)

        control_container = QWidget()
        control_layout = QHBoxLayout(control_container)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(0)
        control_layout.addStretch()
        control_layout.addWidget(widget)
        row_layout.addWidget(control_container, 0, Qt.AlignVCenter)

        if not isinstance(widget, QCheckBox) and control_width > 0:
            widget.setMinimumWidth(control_width)
            widget.setMinimumHeight(max(widget.minimumHeight(), 38))

        self.content_layout.addWidget(row)
        self._row_count += 1


class UpdateCheckWorker(QThread):
    result_ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            self.result_ready.emit(check_for_updates(__version__))
        except UpdateCheckError as exc:
            self.failed.emit(str(exc))


class ControlConsoleWindow(QMainWindow):
    """设置与运行时控制台"""

    _LOG_FLUSH_INTERVAL_MS = 33

    @staticmethod
    def _use_topmost_window() -> bool:
        return platform.system() != "Windows"

    @staticmethod
    def _hide_instead_of_close() -> bool:
        return platform.system() != "Windows"

    def __init__(
        self,
        config: Config,
        log_buffer: RuntimeLogBuffer,
        job_manager: Optional[JobManager] = None,
        on_config_changed: Optional[Callable[[str, Any], None]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._log_buffer = log_buffer
        self._job_manager = job_manager
        self._on_config_changed = on_config_changed
        self._platform_adapter = get_platform_adapter()
        self._pending_log_entries: List[Tuple[str, str]] = []
        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setInterval(self._LOG_FLUSH_INTERVAL_MS)
        self._log_flush_timer.timeout.connect(self._flush_pending_logs)
        self._job_refresh_timer = QTimer(self)
        self._job_refresh_timer.setInterval(700)
        self._job_refresh_timer.timeout.connect(self.refresh_jobs)
        self._config_widgets: Dict[str, QWidget] = {}
        self._wake_word_phrase_widgets: Dict[str, QLineEdit] = {}
        self._jobs_panel: Optional[CodeAgentJobsPanel] = None
        self._current_status_key = "ready"
        self._current_status_text = t("agent_ready")
        self._current_iteration: Optional[int] = 0
        self._current_max_iterations: Optional[int] = 0
        self._current_token_total: Optional[int] = 0
        self._stack: Optional[QStackedWidget] = None
        self._sidebar: Optional[QListWidget] = None
        self._footer_sidebar: Optional[QListWidget] = None
        self._current_page_id = "general"
        self._update_check_worker: Optional[UpdateCheckWorker] = None
        self._update_status_label: Optional[QLabel] = None
        self._update_check_button: Optional[QPushButton] = None
        self._latest_release_url = RELEASES_URL

        set_locale(str(self._config.get("locale_config.locale", "zh_CN") or "zh_CN"))

        self._build_ui()
        self._setup_window()
        self._connect_config_signals()
        self._load_config_values()
        self._bind_log_buffer()
        if self._job_manager is not None:
            self._job_refresh_timer.start()
            self.refresh_jobs()
        self.update_runtime_state(status_key="ready", status_text=t("agent_ready"))

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle(t("settings_window_title"))
        self.setMinimumSize(720, 560)
        self.resize(800, 620)
        self.setStyleSheet(f"QMainWindow {{ background-color: {PALETTE['bg']}; }}")
        self._rebuild_content_ui()

    def _rebuild_content_ui(self) -> None:
        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setSpacing(0)
        central_layout.setContentsMargins(0, 0, 0, 0)

        sidebar_container = self._build_sidebar_container()
        central_layout.addWidget(sidebar_container)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background-color: {PALETTE['bg']};")
        central_layout.addWidget(self._stack, 1)

        for _page_id, builder in self._page_builders():
            self._stack.addWidget(builder())

        self.setCentralWidget(central)
        self._select_page(self._current_page_id)

    def _page_builders(self) -> List[Tuple[str, Callable[[], QWidget]]]:
        return [
            ("general", self._build_general_page),
            ("floating", self._build_floating_page),
            ("voice", self._build_voice_page),
            ("companion", self._build_companion_page),
            ("advanced", self._build_advanced_page),
            ("code_agent", self._build_code_agent_page),
            ("runtime", self._build_runtime_page),
            ("about", self._build_about_page),
            ("language", self._build_language_page),
        ]

    def _build_sidebar_container(self) -> QWidget:
        container = QWidget()
        container.setFixedWidth(182)
        layout = QVBoxLayout(container)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self._sidebar = self._build_sidebar_list(
            MAIN_SIDEBAR_ITEMS, top_padding=20, bottom_padding=12
        )
        self._footer_sidebar = self._build_sidebar_list(
            FOOTER_SIDEBAR_ITEMS, top_padding=8, bottom_padding=0
        )
        layout.addWidget(self._sidebar, 0, Qt.AlignTop)
        layout.addStretch(1)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(
            f"background-color: {PALETTE['divider']}; border: none; margin: 0 16px 8px 16px;"
        )
        layout.addWidget(divider)
        layout.addWidget(self._footer_sidebar, 0, Qt.AlignBottom)
        return container

    def _build_sidebar_list(
        self,
        items: List[Tuple[str, str]],
        *,
        top_padding: int,
        bottom_padding: int,
    ) -> QListWidget:
        sidebar = QListWidget()
        sidebar.setFocusPolicy(Qt.NoFocus)
        sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar.setStyleSheet(f"""
            QListWidget {{
                background-color: {PALETTE['bg']};
                border: none;
                outline: none;
                padding: {top_padding}px 8px {bottom_padding}px 8px;
            }}
            QListWidget::item {{
                color: {PALETTE['text_primary']};
                font-size: 14px;
                font-weight: 700;
                padding: 12px 16px;
                border-radius: 8px;
                margin-bottom: 6px;
            }}
            QListWidget::item:selected {{
                background-color: {PALETTE['sidebar_selected_bg']};
                color: {PALETTE['sidebar_selected_text']};
            }}
            QListWidget::item:hover {{
                background-color: {PALETTE['sidebar_hover_bg']};
            }}
            QListWidget::item:selected:hover {{
                background-color: {PALETTE['sidebar_selected_bg']};
                color: {PALETTE['sidebar_selected_text']};
            }}
            """)

        for key, label_key in items:
            item = QListWidgetItem(t(label_key))
            item.setData(Qt.UserRole, key)
            font = QFont()
            font.setPointSize(14)
            font.setWeight(QFont.Bold)
            item.setFont(font)
            sidebar.addItem(item)

        sidebar.setFixedHeight(self._sidebar_list_height(len(items), top_padding, bottom_padding))
        sidebar.currentItemChanged.connect(self._on_sidebar_item_changed)
        return sidebar

    def _sidebar_list_height(self, item_count: int, top_padding: int, bottom_padding: int) -> int:
        # Keep all sidebar items visible without scrolling and let the footer block
        # sit flush near the window bottom.
        row_height = 54
        return top_padding + bottom_padding + (row_height * item_count)

    def _on_sidebar_item_changed(
        self,
        current: Optional[QListWidgetItem],
        _previous: Optional[QListWidgetItem],
    ) -> None:
        if current is None:
            return
        page_id = str(current.data(Qt.UserRole) or "")
        if page_id:
            self._select_page(page_id)

    def _select_page(self, page_id: str) -> None:
        page_ids = [item[0] for item in self._page_builders()]
        if page_id not in page_ids:
            page_id = "general"
        self._current_page_id = page_id
        if self._stack is not None:
            self._stack.setCurrentIndex(page_ids.index(page_id))
        self._sync_sidebar_selection(self._sidebar, page_id)
        self._sync_sidebar_selection(self._footer_sidebar, page_id)

    def _sync_sidebar_selection(self, sidebar: Optional[QListWidget], active_page_id: str) -> None:
        if sidebar is None:
            return
        sidebar.blockSignals(True)
        selected_row = -1
        for index in range(sidebar.count()):
            item = sidebar.item(index)
            if str(item.data(Qt.UserRole) or "") == active_page_id:
                selected_row = index
                break
        sidebar.setCurrentRow(selected_row)
        sidebar.blockSignals(False)

    def switch_to_page(self, index: int) -> None:
        page_ids = [item[0] for item in self._page_builders()]
        if 0 <= index < len(page_ids):
            self._select_page(page_ids[index])

    def _wrap_scroll(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #C0C0C0;
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            """)
        scroll.setWidget(widget)
        return scroll

    def _page_widget(self) -> QWidget:
        """创建统一的内容页容器"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 24, 24, 24)
        layout.setAlignment(Qt.AlignTop)
        return page

    # ------------------------------------------------------------------
    # 通用页
    # ------------------------------------------------------------------

    def _build_general_page(self) -> QWidget:
        page = self._page_widget()

        card_api = SectionCard(t("section_api"), t("general_api_desc"))
        card_api.add_row(
            t("label_api_key"),
            self._register_widget(
                "api_config.api_key",
                self._styled_line_edit(t("api_key_placeholder"), password=True),
            ),
            t("general_api_key_desc"),
        )
        card_api.add_row(
            t("label_base_url"),
            self._register_widget(
                "api_config.base_url",
                self._styled_line_edit("https://dashscope.aliyuncs.com/compatible-mode/v1"),
            ),
            t("general_base_url_desc"),
        )
        card_api.add_row(
            t("label_model_name"),
            self._register_widget(
                "api_config.model_name", self._styled_line_edit("qwen3.6-35b-a3b")
            ),
            t("general_model_desc"),
        )
        page.layout().addWidget(card_api)

        card_ai = SectionCard(t("section_ai"), t("general_ai_desc"))
        card_ai.add_row(
            t("label_thinking_type"),
            self._register_widget(
                "ai_config.thinking_type",
                self._styled_combo_box(["disabled", "enabled", "auto"]),
            ),
            t("general_thinking_type_desc"),
        )
        card_ai.add_row(
            t("label_reasoning_effort"),
            self._register_widget(
                "ai_config.reasoning_effort",
                self._styled_combo_box(["minimal", "low", "medium", "high"]),
            ),
            t("general_reasoning_effort_desc"),
        )
        page.layout().addWidget(card_ai)

        card_memory = SectionCard(t("section_memory"), t("general_memory_desc"))
        card_memory.add_row(
            t("label_max_text_memory"),
            self._register_widget(
                "memory_config.max_text_memory",
                self._styled_spin_box(1, 200, t("suffix_text_memory")),
            ),
            t("general_text_memory_desc"),
        )
        card_memory.add_row(
            t("label_max_image_memory"),
            self._register_widget(
                "memory_config.max_image_memory",
                self._styled_spin_box(1, 20, t("suffix_image_memory")),
            ),
            t("general_image_memory_desc"),
        )
        card_memory.add_row(
            t("label_history_count"),
            self._register_widget(
                "memory_config.history_count",
                self._styled_spin_box(1, 10, t("suffix_history_count")),
            ),
            t("general_history_count_desc"),
        )
        page.layout().addWidget(card_memory)

        card_exec = SectionCard(t("section_execution_behavior"), t("general_execution_desc"))
        card_exec.add_row(
            t("label_max_iterations"),
            self._register_widget(
                "execution_config.default_max_iterations",
                self._styled_spin_box(1, 500, t("suffix_iterations")),
            ),
            t("general_max_iterations_desc"),
        )
        page.layout().addWidget(card_exec)

        page.layout().addStretch()
        return self._wrap_scroll(page)

    # ------------------------------------------------------------------
    # 悬浮球页
    # ------------------------------------------------------------------

    def _build_floating_page(self) -> QWidget:
        page = self._page_widget()

        card = SectionCard(t("section_floating_appearance"), t("floating_desc"))
        card.add_row(
            t("floating_asset_label"),
            self._build_floating_asset_selector(),
            t("floating_asset_desc"),
            control_width=360,
        )
        card.add_row(
            t("floating_animation_always_play_label"),
            self._register_widget(
                "floating_ball_config.animation_always_play",
                self._styled_check_box(t("floating_animation_always_play_cb")),
            ),
            t("floating_animation_always_play_desc"),
        )
        card.add_row(
            t("floating_reset_on_leave_label"),
            self._register_widget(
                "floating_ball_config.reset_animation_on_leave",
                self._styled_check_box(t("floating_reset_on_leave_cb")),
            ),
            t("floating_reset_on_leave_desc"),
        )
        page.layout().addWidget(card)
        page.layout().addStretch()
        return self._wrap_scroll(page)

    # ------------------------------------------------------------------
    # 语音交互页
    # ------------------------------------------------------------------

    def _build_voice_page(self) -> QWidget:
        page = self._page_widget()

        card_tts = SectionCard(t("section_tts"), t("voice_tts_desc"))
        card_tts.add_row(
            t("label_tts_enabled"),
            self._register_widget(
                "tts_config.enabled", self._styled_check_box(t("label_tts_enabled_cb"))
            ),
            t("voice_tts_enabled_desc"),
        )
        card_tts.add_row(
            t("label_tts_api_key"),
            self._register_widget(
                "tts_config.api_key",
                self._styled_line_edit(t("api_key_placeholder"), password=True),
            ),
            t("voice_tts_api_key_desc"),
        )
        card_tts.add_row(
            t("label_tts_base_url"),
            self._register_widget(
                "tts_config.base_url",
                self._styled_line_edit("wss://dashscope.aliyuncs.com/api-ws/v1/inference"),
            ),
            t("voice_tts_base_url_desc"),
        )
        card_tts.add_row(
            t("label_tts_model"),
            self._register_widget("tts_config.model", self._styled_line_edit("cosyvoice-v3-flash")),
            t("voice_tts_model_desc"),
        )
        card_tts.add_row(
            t("label_tts_voice"),
            self._register_widget("tts_config.voice", self._styled_line_edit("longanhuan")),
            t("voice_tts_voice_desc"),
        )
        card_tts.add_row(
            t("label_tts_speech_rate"),
            self._register_widget(
                "tts_config.speech_rate", self._styled_double_spin_box(0.5, 3.0, suffix="x")
            ),
            t("voice_tts_speech_rate_desc"),
        )
        card_tts.add_row(
            t("label_tts_volume"),
            self._register_widget("tts_config.volume", self._styled_spin_box(0, 100)),
            t("voice_tts_volume_desc"),
        )
        card_tts.add_row(
            t("label_tts_pitch_rate"),
            self._register_widget(
                "tts_config.pitch_rate", self._styled_double_spin_box(0.5, 2.0, suffix="x")
            ),
            t("voice_tts_pitch_rate_desc"),
        )
        page.layout().addWidget(card_tts)

        card_input = SectionCard(t("section_voice_input"), t("voice_input_desc"))
        card_input.add_row(
            t("voice_input_enabled_label"),
            self._register_widget(
                "voice_interaction_config.enabled",
                self._styled_check_box(t("voice_input_enabled_cb")),
            ),
            t("voice_input_enabled_desc"),
        )

        card_input.add_row(
            t("voice_input_asr_provider_label"),
            self._register_widget(
                "voice_interaction_config.asr_provider", self._styled_combo_box(["qwen"])
            ),
            t("voice_input_asr_provider_desc"),
        )
        card_input.add_row(
            t("voice_input_asr_api_key_label"),
            self._register_widget(
                "voice_interaction_config.asr_api_key",
                self._styled_line_edit(t("api_key_placeholder"), password=True),
            ),
            t("voice_input_asr_api_key_desc"),
        )
        card_input.add_row(
            t("voice_input_asr_url_label"),
            self._register_widget(
                "voice_interaction_config.asr_url",
                self._styled_line_edit("wss://dashscope.aliyuncs.com/api-ws/v1/realtime"),
            ),
            t("voice_input_asr_url_desc"),
        )
        card_input.add_row(
            t("voice_input_asr_model_label"),
            self._register_widget(
                "voice_interaction_config.asr_model",
                self._styled_line_edit("qwen3-asr-flash-realtime"),
            ),
            t("voice_input_asr_model_desc"),
        )
        card_input.add_row(
            t("voice_input_asr_language_label"),
            self._register_widget(
                "voice_interaction_config.asr_language", self._styled_line_edit("zh")
            ),
            t("voice_input_asr_language_desc"),
        )
        card_input.add_row(
            t("voice_input_stop_spoken_text_label"),
            self._register_widget(
                "voice_interaction_config.stop_spoken_text",
                self._styled_line_edit(t("voice_input_stop_spoken_text_default")),
            ),
            t("voice_input_stop_spoken_text_desc"),
        )
        card_input.add_row(
            t("voice_input_ignore_tts_echo_label"),
            self._register_widget(
                "voice_interaction_config.ignore_tts_echo",
                self._styled_check_box(t("voice_input_ignore_tts_echo_cb")),
            ),
            t("voice_input_ignore_tts_echo_desc"),
        )
        card_input.add_row(
            t("voice_input_idle_auto_unpin_label"),
            self._register_widget(
                "voice_interaction_config.idle_auto_unpin_seconds",
                self._styled_spin_box(0, 3600, t("suffix_seconds")),
            ),
            t("voice_input_idle_auto_unpin_desc"),
        )
        card_input.add_row(
            t("voice_input_recording_indicator_label"),
            self._register_widget(
                "voice_interaction_config.show_voice_recording_indicator",
                self._styled_check_box(t("voice_input_recording_indicator_cb")),
            ),
            t("voice_input_recording_indicator_desc"),
        )
        page.layout().addWidget(card_input)

        card_wake_word = SectionCard(t("section_wake_word"), t("wake_word_desc"))
        card_wake_word.add_row(
            t("wake_word_enabled_label"),
            self._register_widget(
                "wake_word_config.enabled", self._styled_check_box(t("wake_word_enabled_cb"))
            ),
            t("wake_word_enabled_desc"),
        )
        card_wake_word.add_row(
            t("wake_word_provider_label"),
            self._register_widget(
                "wake_word_config.provider", self._styled_combo_box(["sherpa_onnx"])
            ),
            t("wake_word_provider_desc"),
        )
        card_wake_word.add_row(
            t("wake_word_phrase_zh_label"),
            self._register_wake_word_phrase_widget("zh", self._styled_line_edit("你好小彤")),
            t("wake_word_phrase_zh_desc"),
        )
        card_wake_word.add_row(
            t("wake_word_phrase_en_label"),
            self._register_wake_word_phrase_widget("en", self._styled_line_edit("hey Lucy")),
            t("wake_word_phrase_en_desc"),
        )
        card_wake_word.add_row(
            t("wake_word_threshold_label"),
            self._register_widget(
                "wake_word_config.threshold", self._styled_double_spin_box(0.0, 1.0, decimals=2)
            ),
            t("wake_word_threshold_desc"),
        )
        card_wake_word.add_row(
            t("wake_word_cooldown_label"),
            self._register_widget(
                "wake_word_config.cooldown_ms", self._styled_spin_box(0, 60000, t("suffix_ms"))
            ),
            t("wake_word_cooldown_desc"),
        )
        card_wake_word.add_row(
            t("wake_word_timeout_label"),
            self._register_widget(
                "wake_word_config.post_wake_timeout_seconds",
                self._styled_spin_box(0, 120, t("suffix_seconds")),
            ),
            t("wake_word_timeout_desc"),
        )
        card_wake_word.add_row(
            t("wake_word_indicator_label"),
            self._register_widget(
                "wake_word_config.show_indicator",
                self._styled_check_box(t("wake_word_indicator_cb")),
            ),
            t("wake_word_indicator_desc"),
        )
        page.layout().addWidget(card_wake_word)

        page.layout().addStretch()
        return self._wrap_scroll(page)

    # ------------------------------------------------------------------
    # 伴随推荐页
    # ------------------------------------------------------------------

    def _build_companion_page(self) -> QWidget:
        page = self._page_widget()

        card = SectionCard(t("section_companion"), t("companion_desc"))
        card.add_row(
            t("companion_enabled_label"),
            self._register_widget(
                "companion_config.enabled",
                self._styled_check_box(t("companion_enabled_cb")),
            ),
            t("companion_enabled_desc"),
        )
        enable_thinking_switch = self._styled_check_box(t("companion_thinking_cb"))
        enable_thinking_switch.setChecked(
            not self._config.get("companion_config.disable_thinking", True)
        )
        enable_thinking_switch.toggled.connect(self._on_companion_thinking_toggled)
        card.add_row(
            t("companion_thinking_label"),
            enable_thinking_switch,
            t("companion_thinking_desc"),
        )
        card.add_row(
            t("companion_display_seconds_label"),
            self._register_widget(
                "companion_config.suggestion_display_seconds",
                self._styled_spin_box(5, 120, t("suffix_seconds")),
            ),
            t("companion_display_seconds_desc"),
        )
        card.add_row(
            t("companion_stable_delay_label"),
            self._register_widget(
                "companion_config.trigger_stable_delay_ms",
                self._styled_spin_box(0, 5000, t("suffix_ms")),
            ),
            t("companion_stable_delay_desc"),
        )
        card.add_row(
            t("companion_switch_window_label"),
            self._register_widget(
                "companion_config.rapid_switch_window_seconds",
                self._styled_spin_box(1, 60, t("suffix_seconds")),
            ),
            t("companion_switch_window_desc"),
        )
        card.add_row(
            t("companion_switch_threshold_label"),
            self._register_widget(
                "companion_config.rapid_switch_count_threshold",
                self._styled_spin_box(1, 10, t("suffix_iterations")),
            ),
            t("companion_switch_threshold_desc"),
        )
        card.add_row(
            t("companion_cooldown_label"),
            self._register_widget(
                "companion_config.rapid_switch_cooldown_seconds",
                self._styled_spin_box(0, 120, t("suffix_seconds")),
            ),
            t("companion_cooldown_desc"),
        )
        page.layout().addWidget(card)
        page.layout().addStretch()
        return self._wrap_scroll(page)

    # ------------------------------------------------------------------
    # 后台 Agent 页
    # ------------------------------------------------------------------

    def _build_code_agent_page(self) -> QWidget:
        page = self._page_widget()

        card = SectionCard(t("section_code_agent"), t("code_agent_desc"))
        card.add_row(
            t("code_agent_provider_label"),
            self._register_widget(
                "code_agent_config.provider",
                self._styled_combo_box(CODE_AGENT_PROVIDER_OPTIONS),
            ),
            t("code_agent_provider_desc"),
        )
        card.add_row(
            t("code_agent_workspace_label"),
            self._register_widget(
                "code_agent_config.workspace_root",
                self._styled_line_edit("/Users/xxx/project"),
            ),
            t("code_agent_workspace_desc"),
        )
        card.add_row(
            t("code_agent_concurrency_label"),
            self._register_widget(
                "code_agent_config.max_concurrent_jobs",
                self._styled_spin_box(1, 8),
            ),
            t("code_agent_concurrency_desc"),
        )
        card.add_row(
            t("code_agent_timeout_label"),
            self._register_widget(
                "code_agent_config.default_timeout_seconds",
                self._styled_spin_box(60, 24 * 3600, t("suffix_seconds")),
            ),
            t("code_agent_timeout_desc"),
        )
        page.layout().addWidget(card)

        self._jobs_panel = CodeAgentJobsPanel(
            self._job_manager,
            self._small_button_style,
            parent=page,
        )
        page.layout().addWidget(self._jobs_panel)

        page.layout().addStretch()
        return self._wrap_scroll(page)

    # ------------------------------------------------------------------
    # 高级页
    # ------------------------------------------------------------------

    def _build_advanced_page(self) -> QWidget:
        page = self._page_widget()

        card_exec = SectionCard(t("section_exec"), t("advanced_exec_desc"))
        card_exec.add_row(
            t("label_report_mode"),
            self._register_widget(
                "execution_config.process_report_mode",
                self._styled_combo_box(["auto", "every_step", "off"]),
            ),
            t("advanced_report_mode_desc"),
        )
        card_exec.add_row(
            t("label_report_interval"),
            self._register_widget(
                "execution_config.process_report_interval_steps",
                self._styled_spin_box(1, 20, t("suffix_steps")),
            ),
            t("advanced_report_interval_desc"),
        )
        card_exec.add_row(
            t("label_post_tool_delay"),
            self._register_widget(
                "execution_config.post_tool_capture_delay_ms",
                self._styled_spin_box(0, 5000, t("suffix_ms")),
            ),
            t("advanced_post_tool_delay_desc"),
        )
        page.layout().addWidget(card_exec)

        card_mouse = SectionCard(t("section_mouse"), t("advanced_mouse_desc"))
        card_mouse.add_row(
            t("label_move_duration"),
            self._register_widget(
                "mouse_config.move_duration",
                self._styled_double_spin_box(0.0, 5.0, suffix=t("suffix_seconds")),
            ),
            t("advanced_move_duration_desc"),
        )
        card_mouse.add_row(
            t("label_failsafe"),
            self._register_widget(
                "mouse_config.failsafe", self._styled_check_box(t("label_failsafe_cb"))
            ),
            t("advanced_failsafe_desc"),
        )
        page.layout().addWidget(card_mouse)

        card_vad = SectionCard(t("section_vad"), t("vad_desc"))
        card_vad.add_row(
            t("vad_sample_rate_label"),
            self._register_widget(
                "voice_interaction_config.sample_rate", self._styled_spin_box(8000, 48000, " Hz")
            ),
            t("vad_sample_rate_desc"),
        )
        card_vad.add_row(
            t("vad_block_frames_label"),
            self._register_widget(
                "voice_interaction_config.block_frames",
                self._styled_spin_box(160, 4800, t("suffix_frames")),
            ),
            t("vad_block_frames_desc"),
        )
        card_vad.add_row(
            t("vad_energy_threshold_label"),
            self._register_widget(
                "voice_interaction_config.energy_threshold", self._styled_spin_box(0, 20000)
            ),
            t("vad_energy_threshold_desc"),
        )
        card_vad.add_row(
            t("vad_min_speech_label"),
            self._register_widget(
                "voice_interaction_config.vad_min_speech_ms",
                self._styled_spin_box(50, 3000, t("suffix_ms")),
            ),
            t("vad_min_speech_desc"),
        )
        card_vad.add_row(
            t("vad_end_silence_label"),
            self._register_widget(
                "voice_interaction_config.vad_end_silence_ms",
                self._styled_spin_box(100, 5000, t("suffix_ms")),
            ),
            t("vad_end_silence_desc"),
        )
        card_vad.add_row(
            t("vad_pre_roll_label"),
            self._register_widget(
                "voice_interaction_config.vad_pre_roll_ms",
                self._styled_spin_box(0, 3000, t("suffix_ms")),
            ),
            t("vad_pre_roll_desc"),
        )
        card_vad.add_row(
            t("vad_max_utterance_label"),
            self._register_widget(
                "voice_interaction_config.vad_max_utterance_ms",
                self._styled_spin_box(1000, 120000, t("suffix_ms")),
            ),
            t("vad_max_utterance_desc"),
        )
        page.layout().addWidget(card_vad)

        card_aec = SectionCard(t("section_aec"), t("aec_desc"))
        card_aec.add_row(
            t("aec_enabled_label"),
            self._register_widget(
                "voice_interaction_config.echo_cancellation_enabled",
                self._styled_check_box(t("aec_enabled_cb")),
            ),
            t("aec_enabled_desc"),
        )
        card_aec.add_row(
            t("aec_frame_label"),
            self._register_widget(
                "voice_interaction_config.echo_cancellation_frame_ms",
                self._styled_spin_box(10, 30, t("suffix_ms")),
            ),
            t("aec_frame_desc"),
        )
        card_aec.add_row(
            t("aec_delay_label"),
            self._register_widget(
                "voice_interaction_config.echo_cancellation_stream_delay_ms",
                self._styled_spin_box(0, 500, t("suffix_ms")),
            ),
            t("aec_delay_desc"),
        )
        card_aec.add_row(
            t("aec_ns_label"),
            self._register_widget(
                "voice_interaction_config.echo_cancellation_ns",
                self._styled_check_box(t("aec_ns_cb")),
            ),
            t("aec_ns_desc"),
        )
        card_aec.add_row(
            t("aec_agc_label"),
            self._register_widget(
                "voice_interaction_config.echo_cancellation_agc",
                self._styled_check_box(t("aec_agc_cb")),
            ),
            t("aec_agc_desc"),
        )
        page.layout().addWidget(card_aec)

        card_intent = SectionCard(t("section_intent"), t("intent_desc"))
        card_intent.add_row(
            t("intent_model_label"),
            self._register_widget(
                "voice_interaction_config.intent_model_name",
                self._styled_line_edit(t("intent_model_placeholder")),
            ),
            t("intent_model_desc"),
        )
        page.layout().addWidget(card_intent)

        page.layout().addStretch()
        return self._wrap_scroll(page)

    # ------------------------------------------------------------------
    # 关于 / 语言页
    # ------------------------------------------------------------------

    def _build_about_page(self) -> QWidget:
        page = self._page_widget()

        card = SectionCard(t("section_about"), t("about_desc"))
        card.add_row(
            t("about_product_name_label"),
            self._read_only_value_label(t("app_name")),
            t("about_product_name_desc"),
        )
        card.add_row(
            t("about_version_label"),
            self._read_only_value_label(__version__),
            t("about_version_desc"),
        )
        self._update_status_label = self._read_only_value_label(t("about_update_idle"))
        self._update_check_button = QPushButton(t("about_update_check_button"))
        self._update_check_button.setCursor(Qt.PointingHandCursor)
        self._update_check_button.setStyleSheet(self._small_button_style())
        self._update_check_button.clicked.connect(self._start_update_check)
        update_controls = QWidget()
        update_layout = QHBoxLayout(update_controls)
        update_layout.setContentsMargins(0, 0, 0, 0)
        update_layout.setSpacing(8)
        update_layout.addWidget(self._update_status_label, 1)
        update_layout.addWidget(self._update_check_button)
        card.add_row(
            t("about_update_label"),
            update_controls,
            t("about_update_desc"),
            control_width=360,
        )
        page.layout().addWidget(card)
        page.layout().addStretch()
        return self._wrap_scroll(page)

    def _start_update_check(self) -> None:
        if self._update_check_worker is not None and self._update_check_worker.isRunning():
            return
        if self._update_status_label is not None:
            self._update_status_label.setText(t("about_update_checking"))
        if self._update_check_button is not None:
            self._update_check_button.setEnabled(False)

        worker = UpdateCheckWorker(self)
        worker.result_ready.connect(self._on_update_check_finished)
        worker.failed.connect(self._on_update_check_failed)
        worker.result_ready.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        self._update_check_worker = worker
        worker.start()

    def _on_update_check_finished(self, result: UpdateCheckResult) -> None:
        self._latest_release_url = result.release_url
        if self._update_status_label is not None:
            if result.update_available:
                self._update_status_label.setText(
                    t("about_update_available").format(version=result.latest_version)
                )
            else:
                self._update_status_label.setText(t("about_update_current"))
        if self._update_check_button is not None:
            self._update_check_button.setEnabled(True)
            self._update_check_button.setText(
                t("about_update_open_button")
                if result.update_available
                else t("about_update_check_button")
            )
            try:
                self._update_check_button.clicked.disconnect()
            except TypeError:
                pass
            if result.update_available:
                self._update_check_button.clicked.connect(self._open_latest_release)
            else:
                self._update_check_button.clicked.connect(self._start_update_check)
        self._update_check_worker = None

    def _on_update_check_failed(self, message: str) -> None:
        if self._update_status_label is not None:
            self._update_status_label.setText(t("about_update_failed").format(error=message))
        if self._update_check_button is not None:
            self._update_check_button.setEnabled(True)
        self._update_check_worker = None

    def _open_latest_release(self) -> None:
        QDesktopServices.openUrl(QUrl(self._latest_release_url or RELEASES_URL))

    def _build_language_page(self) -> QWidget:
        page = self._page_widget()

        card = SectionCard(t("language_page_title"), t("language_page_desc"))
        card.add_row(
            t("language_option_zh"),
            self._build_language_button("zh_CN", t("language_option_zh")),
            t("language_option_zh_desc"),
        )
        card.add_row(
            t("language_option_en"),
            self._build_language_button("en_US", t("language_option_en")),
            t("language_option_en_desc"),
        )
        page.layout().addWidget(card)
        page.layout().addStretch()
        return self._wrap_scroll(page)

    # ------------------------------------------------------------------
    # 运行时页
    # ------------------------------------------------------------------

    def _build_runtime_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 24, 24, 24)

        # 状态栏
        status_card = QFrame()
        status_card.setStyleSheet(f"""
            QFrame {{
                background-color: {PALETTE['card']};
                border: 1px solid {PALETTE['divider']};
                border-radius: 16px;
            }}
            """)
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(20, 12, 20, 12)
        status_layout.setSpacing(14)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {PALETTE['status_ready']}; font-size: 18px;")
        status_layout.addWidget(self.status_dot)

        self.status_label = QLabel(t("agent_ready"))
        self.status_label.setStyleSheet(self._status_label_style(PALETTE["status_ready"]))
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        self.iter_label = QLabel(t("iteration_label", current=0, total=0))
        self.iter_label.setStyleSheet(self._metric_label_style())
        status_layout.addWidget(self.iter_label)

        self.token_label = QLabel(t("token_label", count=0))
        self.token_label.setStyleSheet(self._metric_label_style())
        status_layout.addWidget(self.token_label)
        layout.addWidget(status_card)

        # 日志
        log_card = QFrame()
        log_card.setStyleSheet(f"""
            QFrame {{
                background-color: {PALETTE['card']};
                border: 1px solid {PALETTE['divider']};
                border-radius: 16px;
            }}
            """)
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(20, 14, 20, 14)
        log_layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel(t("log_title"))
        title.setStyleSheet(f"""
            QLabel {{
                color: {PALETTE['text_primary']};
                font-size: 13px;
                font-weight: bold;
            }}
            """)
        header.addWidget(title)
        header.addStretch()

        clear_btn = QPushButton(t("log_clear"))
        clear_btn.setStyleSheet(self._small_button_style())
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._log_buffer.clear)
        header.addWidget(clear_btn)

        save_btn = QPushButton(t("log_save"))
        save_btn.setStyleSheet(self._small_button_style())
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save_log)
        header.addWidget(save_btn)
        log_layout.addLayout(header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {PALETTE['log_bg']};
                color: {PALETTE['log_text']};
                border: none;
                border-radius: 14px;
                padding: 14px;
                font-family: 'Menlo', monospace;
                font-size: 12px;
                line-height: 1.6;
            }}
            """)
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_card, 1)
        return page

    # ------------------------------------------------------------------
    # 样式化控件
    # ------------------------------------------------------------------

    def _styled_line_edit(self, placeholder: str = "", *, password: bool = False) -> QLineEdit:
        widget = QLineEdit()
        widget.setPlaceholderText(placeholder)
        if password:
            widget.setEchoMode(QLineEdit.Password)
        widget.setStyleSheet(f"""
            QLineEdit {{
                background-color: {PALETTE['input_bg']};
                border: 1px solid {PALETTE['input_border']};
                border-radius: 11px;
                padding: 0 12px;
                color: {PALETTE['text_primary']};
                font-size: 13px;
                min-height: 38px;
            }}
            QLineEdit:focus {{
                border-color: {PALETTE['input_focus']};
                background-color: {PALETTE['input_bg']};
            }}
            """)
        return widget

    def _styled_combo_box(self, values: List[str]) -> QComboBox:
        widget = _NoWheelComboBox()
        widget.addItems(values)
        # 使用 Qt 原生 QListView 替代平台原生菜单，确保 stylesheet 完全生效
        widget.setView(QListView())
        widget.setStyleSheet(f"""
            QComboBox {{
                background-color: {PALETTE['input_bg']};
                border: 1.5px solid {PALETTE['input_border']};
                border-radius: 11px;
                padding: 0 40px 0 14px;
                color: {PALETTE['text_primary']};
                font-size: 13px;
                min-height: 38px;
            }}
            QComboBox:hover {{
                border-color: #8E8E93;
                background-color: #FAFAFA;
            }}
            QComboBox:focus {{
                border-color: {PALETTE['input_focus']};
                background-color: {PALETTE['input_bg']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 36px;
                background-color: transparent;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 1px;
                height: 1px;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {PALETTE['text_secondary']};
            }}
            QComboBox QAbstractItemView {{
                background-color: {PALETTE['input_bg']};
                color: {PALETTE['text_primary']};
                border: 1.5px solid {PALETTE['input_border']};
                border-radius: 10px;
                selection-background-color: {PALETTE['sidebar_selected_bg']};
                selection-color: {PALETTE['sidebar_selected_text']};
                outline: none;
                padding: 6px;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 32px;
                padding: 6px 12px;
                border-radius: 8px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {PALETTE['sidebar_hover_bg']};
                color: {PALETTE['text_primary']};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {PALETTE['sidebar_selected_bg']};
                color: {PALETTE['sidebar_selected_text']};
            }}
            """)
        return widget

    def _combo_option_label(self, key: str, value: str) -> str:
        translation_map = {
            "ai_config.thinking_type": "option_thinking_type_",
            "ai_config.reasoning_effort": "option_reasoning_effort_",
            "execution_config.process_report_mode": "option_report_mode_",
            "voice_interaction_config.asr_provider": "option_asr_provider_",
            "wake_word_config.provider": "option_wake_word_provider_",
        }
        prefix = translation_map.get(key)
        if not prefix:
            return value
        return t(f"{prefix}{value}")

    def _styled_spin_box(self, minimum: int, maximum: int, suffix: str = "") -> QSpinBox:
        widget = _NoWheelSpinBox()
        widget.setRange(minimum, maximum)
        widget.setSuffix(suffix)
        widget.setButtonSymbols(QSpinBox.NoButtons)
        widget.setStyleSheet(f"""
            QSpinBox {{
                background-color: {PALETTE['input_bg']};
                border: 1px solid {PALETTE['input_border']};
                border-radius: 11px;
                padding: 0 12px;
                color: {PALETTE['text_primary']};
                font-size: 13px;
                min-height: 38px;
            }}
            QSpinBox:focus {{
                border-color: {PALETTE['input_focus']};
                background-color: {PALETTE['input_bg']};
            }}
            """)
        return widget

    def _styled_double_spin_box(
        self,
        minimum: float,
        maximum: float,
        decimals: int = 2,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        widget = _NoWheelDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(decimals)
        widget.setSuffix(suffix)
        widget.setButtonSymbols(QDoubleSpinBox.NoButtons)
        widget.setStyleSheet(f"""
            QDoubleSpinBox {{
                background-color: {PALETTE['input_bg']};
                border: 1px solid {PALETTE['input_border']};
                border-radius: 11px;
                padding: 0 12px;
                color: {PALETTE['text_primary']};
                font-size: 13px;
                min-height: 38px;
            }}
            QDoubleSpinBox:focus {{
                border-color: {PALETTE['input_focus']};
                background-color: {PALETTE['input_bg']};
            }}
            """)
        return widget

    def _styled_check_box(self, text: str) -> QCheckBox:
        return ToggleSwitch(text)

    def _read_only_value_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setStyleSheet(f"""
            QLabel {{
                color: {PALETTE['text_primary']};
                font-size: 13px;
                font-weight: 700;
                padding: 0 12px;
                min-height: 38px;
                background: {PALETTE['input_bg']};
                border: 1px solid {PALETTE['input_border']};
                border-radius: 11px;
            }}
            """)
        return label

    def _build_language_button(self, locale_value: str, label: str) -> QPushButton:
        button = QPushButton(label)
        button.setCursor(Qt.PointingHandCursor)
        button.setProperty("active", locale_value == self._config.get("locale_config.locale"))
        button.setStyleSheet(self._language_button_style(bool(button.property("active"))))
        button.clicked.connect(
            lambda _checked=False, locale_value=locale_value: self._on_locale_changed(locale_value)
        )
        return button

    def _language_button_style(self, active: bool) -> str:
        border_color = PALETTE["text_primary"] if active else PALETTE["input_border"]
        background = PALETTE["text_primary"] if active else PALETTE["input_bg"]
        text_color = PALETTE["sidebar_selected_text"] if active else PALETTE["text_primary"]
        return f"""
            QPushButton {{
                background-color: {background};
                border: 1px solid {border_color};
                border-radius: 11px;
                color: {text_color};
                padding: 0 16px;
                font-size: 13px;
                font-weight: 700;
                min-height: 38px;
            }}
            QPushButton:hover {{
                border-color: {PALETTE['text_primary']};
            }}
        """

    def _register_widget(self, key: str, widget: QWidget) -> QWidget:
        self._config_widgets[key] = widget
        if isinstance(widget, _NoWheelComboBox):
            raw_values = widget.raw_items()
            widget.set_items(
                raw_values, [self._combo_option_label(key, value) for value in raw_values]
            )
        return widget

    def _register_wake_word_phrase_widget(self, language: str, widget: QLineEdit) -> QLineEdit:
        normalized_language = str(language or "").strip().lower()
        self._wake_word_phrase_widgets[normalized_language] = widget
        widget.editingFinished.connect(
            lambda language=normalized_language, widget=widget: self._set_wake_word_phrase(
                language,
                widget.text(),
            )
        )
        return widget

    def _build_floating_asset_selector(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        path_edit = self._styled_line_edit(t("floating_asset_placeholder"))
        path_edit.setReadOnly(True)
        self._register_widget("floating_ball_config.asset_path", path_edit)
        layout.addWidget(path_edit, 1)

        choose_button = QPushButton(t("button_choose"))
        choose_button.setCursor(Qt.PointingHandCursor)
        choose_button.setStyleSheet(self._compact_button_style())
        choose_button.clicked.connect(self._choose_floating_ball_asset)
        layout.addWidget(choose_button)

        clear_button = QPushButton(t("button_clear"))
        clear_button.setCursor(Qt.PointingHandCursor)
        clear_button.setStyleSheet(self._compact_button_style())
        clear_button.clicked.connect(self._clear_floating_ball_asset)
        layout.addWidget(clear_button)
        return container

    def _compact_button_style(self) -> str:
        return f"""
            QPushButton {{
                background-color: {PALETTE['input_bg']};
                border: 1px solid {PALETTE['input_border']};
                border-radius: 11px;
                color: {PALETTE['text_primary']};
                padding: 0 14px;
                font-size: 13px;
                min-height: 38px;
            }}
            QPushButton:hover {{
                border-color: {PALETTE['text_primary']};
                background-color: #FAFAFB;
            }}
            """

    def _small_button_style(self) -> str:
        return f"""
            QPushButton {{
                background-color: {PALETTE['input_bg']};
                color: {PALETTE['text_primary']};
                border: 1px solid {PALETTE['divider']};
                border-radius: 10px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: 600;
                min-height: 34px;
            }}
            QPushButton:hover {{
                background-color: #FAFAFB;
                border-color: {PALETTE['text_primary']};
            }}
            """

    def _metric_label_style(self) -> str:
        return f"""
            QLabel {{
                color: {PALETTE['text_secondary']};
                font-size: 11px;
                padding: 5px 12px;
                background-color: {PALETTE['input_bg']};
                border-radius: 8px;
                border: 1px solid {PALETTE['divider']};
            }}
            """

    def _status_label_style(self, color: str) -> str:
        return f"""
            QLabel {{
                color: {color};
                background-color: rgba(0,0,0,0.08);
                padding: 8px 18px;
                border-radius: 10px;
                font-weight: bold;
                font-size: 12px;
            }}
            """

    # ------------------------------------------------------------------
    # 配置加载 / 保存 / 信号
    # ------------------------------------------------------------------

    def _connect_config_signals(self) -> None:
        for key, widget in self._config_widgets.items():
            if isinstance(widget, QLineEdit):
                widget.editingFinished.connect(
                    lambda key=key, widget=widget: self._set_text_config(key, widget.text())
                )
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(
                    lambda value, key=key: self._set_config_value(key, bool(value))
                )
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(
                    lambda _idx, key=key, widget=widget: self._set_config_value(
                        key, widget.currentText()
                    )
                )
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(
                    lambda value, key=key: self._set_config_value(key, int(value))
                )
            elif isinstance(widget, QDoubleSpinBox):
                widget.valueChanged.connect(
                    lambda value, key=key: self._set_config_value(key, float(value))
                )

    def _on_locale_changed(self, locale_value: str) -> None:
        locale_value = str(locale_value or "zh_CN")
        self._sync_locale_sensitive_defaults(locale_value)
        set_locale(locale_value)
        self._config.set("locale_config.locale", locale_value)
        self._config.save()
        self._refresh_all_ui_text()

    def _sync_locale_sensitive_defaults(self, locale_value: str) -> None:
        stop_text_key = "voice_interaction_config.stop_spoken_text"
        current_stop_text = str(self._config.get(stop_text_key, "") or "").strip()
        legacy_stop_texts = {
            translate("zh_CN", "voice_input_stop_spoken_text_default"),
            translate("en_US", "voice_input_stop_spoken_text_default"),
        }
        if current_stop_text in legacy_stop_texts:
            self._config.set(
                stop_text_key,
                translate(locale_value, "voice_input_stop_spoken_text_default"),
            )

    def _refresh_all_ui_text(self) -> None:
        existing_log_html = self.log_text.toHtml() if hasattr(self, "log_text") else ""
        self._config_widgets = {}
        self._wake_word_phrase_widgets = {}
        self._jobs_panel = None
        self.setWindowTitle(t("settings_window_title"))
        self._rebuild_content_ui()
        self._connect_config_signals()
        self._load_config_values()
        if existing_log_html and hasattr(self, "log_text"):
            self.log_text.setHtml(existing_log_html)
        self._restore_runtime_state_text()

    def _restore_runtime_state_text(self) -> None:
        status_text = t(f"agent_{self._current_status_key}")
        self.update_runtime_state(
            status_key=self._current_status_key,
            status_text=status_text,
            iteration=self._current_iteration,
            max_iterations=self._current_max_iterations,
            token_total=self._current_token_total,
        )

    def _load_config_values(self) -> None:
        for key, widget in self._config_widgets.items():
            value = self._config.get(key)
            if isinstance(widget, QLineEdit):
                widget.blockSignals(True)
                widget.setText("" if value is None else str(value))
                widget.blockSignals(False)
            elif isinstance(widget, QCheckBox):
                widget.blockSignals(True)
                widget.setChecked(bool(value))
                widget.blockSignals(False)
            elif isinstance(widget, QComboBox):
                widget.blockSignals(True)
                if value is not None:
                    widget.setCurrentText(str(value))
                widget.blockSignals(False)
            elif isinstance(widget, QSpinBox):
                widget.blockSignals(True)
                widget.setValue(int(value or 0))
                widget.blockSignals(False)
            elif isinstance(widget, QDoubleSpinBox):
                widget.blockSignals(True)
                widget.setValue(float(value or 0.0))
                widget.blockSignals(False)
        self._load_wake_word_phrase_values()

    def _load_wake_word_phrase_values(self) -> None:
        for language, widget in self._wake_word_phrase_widgets.items():
            widget.blockSignals(True)
            widget.setText(self._config.get_wake_word_phrase(language))
            widget.blockSignals(False)

    def _set_text_config(self, key: str, value: str) -> None:
        normalized = str(value or "").strip()
        if key == "api_config.api_key":
            self._config.api_key = normalized
            return
        self._set_config_value(key, normalized)

    def _set_wake_word_phrase(self, language: str, value: str) -> None:
        self._config.set_wake_word_phrase(language, value)
        self._config.save()
        self._load_wake_word_phrase_values()
        self._notify_config_changed(
            "wake_word_config.phrases",
            self._config.get("wake_word_config.phrases"),
        )

    def _set_config_value(self, key: str, value) -> None:
        self._config.set(key, value)
        self._config.save()
        self._notify_config_changed(key, value)

    def _notify_config_changed(self, key: str, value) -> None:
        if self._on_config_changed is not None:
            self._on_config_changed(key, value)

    def _on_companion_thinking_toggled(self, checked: bool) -> None:
        self._config.set("companion_config.disable_thinking", not checked)
        self._config.save()
        self._notify_config_changed("companion_config.disable_thinking", not checked)

    # ------------------------------------------------------------------
    # 悬浮球素材选择
    # ------------------------------------------------------------------

    def _choose_floating_ball_asset(self) -> None:
        source_path, _ = QFileDialog.getOpenFileName(
            self,
            t("dialog_select_floating_asset_title"),
            str(Path.home()),
            t("dialog_images_filter"),
        )
        if not source_path:
            return
        source = Path(source_path).expanduser()
        suffix = source.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            self.append_log(t("log_unsupported_floating_asset") + "\n", "warning")
            return

        target_dir = Path.home() / ".coview" / "floating_assets"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"ball_asset{suffix}"
        try:
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
        except Exception as exc:
            self.append_log(t("log_copy_floating_asset_failed", error=exc) + "\n", "error")
            return

        self._update_registered_line_edit("floating_ball_config.asset_path", str(target))
        self._set_config_value("floating_ball_config.asset_path", str(target))

    def _clear_floating_ball_asset(self) -> None:
        self._update_registered_line_edit("floating_ball_config.asset_path", "")
        self._set_config_value("floating_ball_config.asset_path", "")

    def _update_registered_line_edit(self, key: str, value: str) -> None:
        widget = self._config_widgets.get(key)
        if isinstance(widget, QLineEdit):
            widget.blockSignals(True)
            widget.setText(value)
            widget.blockSignals(False)

    # ------------------------------------------------------------------
    # 后台任务
    # ------------------------------------------------------------------

    def refresh_jobs(self) -> None:
        if self._jobs_panel is not None:
            self._jobs_panel.refresh_jobs()

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------

    def _bind_log_buffer(self) -> None:
        self._log_buffer.entry_added.connect(self.append_log)
        self._log_buffer.cleared.connect(self._clear_log_view)
        for text, log_type in self._log_buffer.history():
            self.append_log(text, log_type)
        self._flush_pending_logs(force=True)

    def _save_log(self) -> None:
        default_name = f"coview-agent-log-{time.strftime('%Y%m%d-%H%M%S')}.log"
        target_path, _ = QFileDialog.getSaveFileName(
            self, t("log_save_title"), default_name, t("dialog_log_filter")
        )
        if not target_path:
            return
        saved_path = self._log_buffer.save_to_file(target_path)
        self.append_log(t("log_saved", path=saved_path) + "\n", "info")

    def append_log(self, text: str, log_type: str = "normal") -> None:
        self._pending_log_entries.append((text, log_type))
        if not self._log_flush_timer.isActive():
            self._log_flush_timer.start()

    def _clear_log_view(self) -> None:
        self._pending_log_entries = []
        self._log_flush_timer.stop()
        self.log_text.clear()

    def _flush_pending_logs(self, force: bool = False) -> None:
        if not self._pending_log_entries:
            if force:
                self._log_flush_timer.stop()
            return

        pending_entries = self._pending_log_entries
        self._pending_log_entries = []
        self._log_flush_timer.stop()

        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.End)
        for text, log_type in pending_entries:
            if log_type == "error":
                color = PALETTE["log_error"]
            elif log_type == "warning":
                color = PALETTE["log_warning"]
            elif log_type == "info":
                color = PALETTE["log_info"]
            elif log_type == "success":
                color = PALETTE["log_success"]
            else:
                color = PALETTE["log_text"]
            cursor.insertHtml(
                f'<span style="color:{color}">{text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(chr(10), "<br>")}</span>'
            )
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()

    # ------------------------------------------------------------------
    # 运行时状态
    # ------------------------------------------------------------------

    def update_runtime_state(
        self,
        *,
        status_key: str,
        status_text: str,
        iteration: Optional[int] = None,
        max_iterations: Optional[int] = None,
        token_total: Optional[int] = None,
    ) -> None:
        color_map = {
            "ready": PALETTE["status_ready"],
            "running": PALETTE["status_running"],
            "stopping": PALETTE["status_stopping"],
            "error": PALETTE["status_error"],
        }
        color = color_map.get(status_key, PALETTE["status_ready"])
        self._current_status_key = status_key
        self._current_status_text = status_text
        self._current_iteration = iteration if iteration is not None else self._current_iteration
        self._current_max_iterations = (
            max_iterations if max_iterations is not None else self._current_max_iterations
        )
        self._current_token_total = (
            token_total if token_total is not None else self._current_token_total
        )
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet(self._status_label_style(color))

        if iteration is not None:
            total_iterations = int(max_iterations or 0)
            current_iteration = max(0, int(iteration))
            self.iter_label.setText(
                t("iteration_label", current=current_iteration, total=total_iterations)
            )
        if token_total is not None:
            self.token_label.setText(t("token_label", count=int(token_total)))

    # ------------------------------------------------------------------
    # 窗口生命周期
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        flags = self.windowFlags()
        if self._use_topmost_window():
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.setProperty(CAPTURE_EXCLUDE_PROPERTY, True)
        self._platform_adapter.setup_window(self)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._job_manager is not None and not self._job_refresh_timer.isActive():
            self._job_refresh_timer.start()
            self.refresh_jobs()

    def enter_transparent_mode(self) -> None:
        was_visible = self.isVisible()
        setattr(self, "_transparent_mode_restore_needed", was_visible)
        if not was_visible:
            return
        self.clearFocus()
        self._platform_adapter.enter_transparent_mode(self)

    def exit_transparent_mode(self) -> None:
        restore_needed = bool(getattr(self, "_transparent_mode_restore_needed", False))
        setattr(self, "_transparent_mode_restore_needed", False)
        if not restore_needed:
            return
        self._platform_adapter.exit_transparent_mode(self)

    def closeEvent(self, event) -> None:
        self._job_refresh_timer.stop()
        if self._hide_instead_of_close():
            event.ignore()
            self.hide()
            return
        event.accept()
        super().closeEvent(event)
