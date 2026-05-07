"""后台 Code Agent 独立任务窗口。"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from baodou_ai.code_agent.adapters.codebuddy import CodeBuddyAdapter
from baodou_ai.code_agent.manager import JobManager
from baodou_ai.core.config import Config
from baodou_ai.platform import get_platform_adapter


WINDOW_PALETTE = {
    "bg": "#F5F5F7",
    "card": "#E8E8ED",
    "card_inner": "#FFFFFF",
    "border": "#C9CBD3",
    "text": "#111111",
    "muted": "#707070",
    "accent": "#111111",
    "success": "#10B981",
    "success_bg": "#D1FAE5",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "log_bg": "#1E293B",
    "log_text": "#E2E8F0",
}


class CodeAgentJobWindow(QMainWindow):
    """每个后台任务对应的独立详情窗口。"""

    _REFRESH_INTERVAL_MS = 500

    def __init__(
        self,
        config: Config,
        job_manager: JobManager,
        job_id: str,
        on_closed: Optional[Callable[[str], None]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._job_manager = job_manager
        self._job_id = job_id
        self._on_closed = on_closed
        self._platform_adapter = get_platform_adapter()
        self._last_log_count = -1
        self._last_final_output: Optional[str] = None
        self._window_title_fallback = f"后台任务 · {job_id}"
        self._last_status = "running"

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(self._REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self.refresh_job)

        self._build_ui()
        self._setup_window()
        self.refresh_job(force_logs=True)
        self._refresh_timer.start()

    def _build_ui(self) -> None:
        self.setMinimumSize(720, 520)
        self.resize(860, 620)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 顶部信息卡片（与设置页 SectionCard 风格统一）
        card = QFrame()
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {WINDOW_PALETTE['card']};
                border: 1px solid {WINDOW_PALETTE['border']};
                border-radius: 18px;
            }}
            """
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        # Header: 标题 | 状态标签 | 终止按钮
        header = QHBoxLayout()
        header.setSpacing(12)

        self.title_label = QLabel(self._window_title_fallback)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            f"color: {WINDOW_PALETTE['text']}; font-size: 17px; font-weight: 700; border: none; background: transparent;"
        )
        header.addWidget(self.title_label, 1)

        self.status_label = QLabel("running")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumWidth(80)
        header.addWidget(self.status_label)

        self.cancel_button = QPushButton("终止运行")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.clicked.connect(self._cancel_job)
        self.cancel_button.setStyleSheet(self._danger_button_style())
        header.addWidget(self.cancel_button)
        card_layout.addLayout(header)

        # Meta 信息（简洁文本，无边框卡片）
        self.meta_label = QLabel("")
        self.meta_label.setWordWrap(True)
        self.meta_label.setStyleSheet(
            f"color: {WINDOW_PALETTE['muted']}; font-size: 12px; border: none; background: transparent;"
        )
        card_layout.addWidget(self.meta_label)

        # 任务内容（白色内嵌卡片）
        self.task_label = QLabel("")
        self.task_label.setWordWrap(True)
        self.task_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.task_label.setStyleSheet(
            f"""
            QLabel {{
                color: {WINDOW_PALETTE['text']};
                font-size: 13px;
                border: none;
                background-color: {WINDOW_PALETTE['card_inner']};
                border-radius: 12px;
                padding: 10px 12px;
            }}
            """
        )
        card_layout.addWidget(self.task_label)

        # 当前状态摘要（白色内嵌卡片）
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary_label.setStyleSheet(
            f"""
            QLabel {{
                color: {WINDOW_PALETTE['text']};
                font-size: 13px;
                border: none;
                background-color: {WINDOW_PALETTE['card_inner']};
                border-radius: 12px;
                padding: 10px 12px;
            }}
            """
        )
        card_layout.addWidget(self.summary_label)

        layout.addWidget(card)

        # Tabs: 最终结果 / 运行日志（极简黑白灰风格）
        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: 1px solid {WINDOW_PALETTE['border']};
                border-radius: 18px;
                background-color: {WINDOW_PALETTE['card']};
                top: 2px;
            }}
            QTabWidget::tab-bar {{
                alignment: left;
                left: 14px;
            }}
            QTabBar::tab {{
                color: {WINDOW_PALETTE['muted']};
                background-color: transparent;
                border: none;
                min-width: 104px;
                min-height: 20px;
                padding: 6px 18px;
                font-size: 13px;
                font-weight: 600;
                border-radius: 10px;
            }}
            QTabBar::tab:selected {{
                color: #FFFFFF;
                background-color: {WINDOW_PALETTE['accent']};
            }}
            """
        )

        result_wrapper = QWidget()
        result_layout = QVBoxLayout(result_wrapper)
        result_layout.setContentsMargins(2, 2, 2, 2)
        self.result_text = QTextBrowser()
        self.result_text.setReadOnly(True)
        self.result_text.setOpenExternalLinks(True)
        self.result_text.setFont(QFont("PingFang SC", 13))
        self.result_text.setStyleSheet(self._text_panel_style())
        self.result_text.document().setDefaultStyleSheet(self._result_document_style())
        result_layout.addWidget(self.result_text)
        tabs.addTab(result_wrapper, "最终结果")

        log_wrapper = QWidget()
        log_layout = QVBoxLayout(log_wrapper)
        log_layout.setContentsMargins(2, 2, 2, 2)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Menlo", 12))
        self.log_text.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {WINDOW_PALETTE['log_bg']};
                color: {WINDOW_PALETTE['log_text']};
                border: none;
                border-radius: 12px;
                padding: 14px;
            }}
            """
        )
        log_layout.addWidget(self.log_text)
        tabs.addTab(log_wrapper, "运行日志")
        layout.addWidget(tabs, 1)

    def _setup_window(self) -> None:
        self.setWindowTitle(self._window_title_fallback)
        self.setStyleSheet(f"QMainWindow {{ background-color: {WINDOW_PALETTE['bg']}; }}")
        self._platform_adapter.setup_window(self)

    def refresh_job(self, force_logs: bool = False) -> None:
        snapshot = self._job_manager.get_job(self._job_id, include_logs=True)
        if snapshot is None:
            self.summary_label.setText("任务记录已不可用。")
            self.cancel_button.setEnabled(False)
            self._refresh_timer.stop()
            return

        title = str(snapshot.get("title") or self._job_id).strip()
        status = str(snapshot.get("status") or "unknown").strip()
        provider = str(snapshot.get("provider") or "").strip()
        workspace = str(snapshot.get("workspace_path") or "").strip()
        pid = snapshot.get("process_pid")
        task = str(snapshot.get("task") or "").strip()
        summary = str(
            snapshot.get("result_summary")
            or snapshot.get("summary")
            or snapshot.get("error")
            or ""
        ).strip()
        final_output = self._normalize_final_output_for_display(
            provider=provider,
            final_output=str(snapshot.get("final_output") or ""),
            raw_output=str(snapshot.get("raw_output") or ""),
        )
        logs = snapshot.get("logs") or []
        log_count = int(snapshot.get("log_count") or len(logs))

        self._last_status = status
        self.setWindowTitle(f"后台任务 · {title}")
        self.title_label.setText(title)
        self.status_label.setText(status)
        self.status_label.setStyleSheet(self._status_style(status))
        self.meta_label.setText(
            f"ID: {self._job_id}   Provider: {provider or '-'}   PID: {pid or '-'}\nWorkspace: {workspace or '-'}"
        )
        self.task_label.setText(f"任务内容：{task or '-'}")
        self.summary_label.setText(f"当前状态：{summary or status}")

        if final_output != self._last_final_output:
            self._last_final_output = final_output
            if final_output:
                self._set_result_markdown(final_output)
            elif status == "running":
                self.result_text.setPlainText("任务完成后将在这里显示最终结果。")
            else:
                self.result_text.setPlainText("没有可显示的最终结果。")

        if force_logs or log_count != self._last_log_count:
            self._last_log_count = log_count
            self.log_text.setPlainText("\n".join(str(line) for line in logs))
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.End)
            self.log_text.setTextCursor(cursor)

        if status == "running":
            self.cancel_button.setVisible(True)
            self.cancel_button.setEnabled(True)
            self.cancel_button.setText("终止运行")
        else:
            self.cancel_button.setVisible(False)
            self._refresh_timer.stop()

    @staticmethod
    def _normalize_final_output_for_display(
        *,
        provider: str,
        final_output: str,
        raw_output: str,
    ) -> str:
        if str(provider or "").strip().lower() == "codebuddy":
            return (
                CodeBuddyAdapter.extract_final_result(raw_output)
                or CodeBuddyAdapter.extract_final_result(final_output)
                or str(final_output or "").strip()
            )
        return str(final_output or "").strip()

    def _set_result_markdown(self, text: str) -> None:
        markdown = str(text or "").strip()
        if not markdown:
            self.result_text.clear()
            return
        self.result_text.setMarkdown(markdown)

    def _cancel_job(self) -> None:
        try:
            self._job_manager.cancel(self._job_id)
        finally:
            self.refresh_job(force_logs=True)

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
        if self._needs_close_confirmation():
            if not self._confirm_close_running_job():
                event.ignore()
                return
            self._job_manager.cancel(self._job_id)

        self._refresh_timer.stop()
        if callable(self._on_closed):
            self._on_closed(self._job_id)
        super().closeEvent(event)

    def _needs_close_confirmation(self) -> bool:
        snapshot = self._job_manager.get_job(self._job_id)
        status = str((snapshot or {}).get("status") or self._last_status or "").strip()
        return status == "running"

    def _confirm_close_running_job(self) -> bool:
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认关闭")
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setText("关闭这个窗口会停止当前 code agent 的执行。")
        msg_box.setInformativeText("点击“确认关闭”后，将终止运行并关闭当前窗口。")
        cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
        confirm_btn = msg_box.addButton("确认关闭", QMessageBox.AcceptRole)
        msg_box.setDefaultButton(cancel_btn)
        msg_box.exec_()
        return msg_box.clickedButton() == confirm_btn

    @staticmethod
    def _status_style(status: str) -> str:
        if status == "completed":
            background = WINDOW_PALETTE["success_bg"]
            color = WINDOW_PALETTE["success"]
        elif status in {"failed", "cancelled"}:
            background = "#FEE2E2"
            color = WINDOW_PALETTE["danger"]
        else:
            background = "#E0E7FF"
            color = "#4F46E5"
        return (
            f"color: {color}; background-color: {background}; padding: 6px 12px; "
            "border-radius: 12px; font-size: 13px; font-weight: bold;"
        )

    @staticmethod
    def _text_panel_style() -> str:
        return (
            f"""
            QTextEdit, QTextBrowser {{
                background-color: transparent;
                color: {WINDOW_PALETTE['text']};
                border: none;
                padding: 14px;
            }}
            """
        )

    @staticmethod
    def _result_document_style() -> str:
        return (
            f"""
            body {{
                color: {WINDOW_PALETTE['text']};
                font-family: "PingFang SC", "Helvetica Neue", Arial, sans-serif;
                font-size: 13px;
                line-height: 1.45;
            }}
            h1, h2, h3, h4, h5, h6 {{
                color: {WINDOW_PALETTE['text']};
                margin-top: 0.7em;
                margin-bottom: 0.35em;
                font-weight: 700;
            }}
            p {{
                margin-top: 0.35em;
                margin-bottom: 0.55em;
            }}
            ul, ol {{
                margin-top: 0.35em;
                margin-bottom: 0.65em;
                padding-left: 1.4em;
            }}
            code {{
                font-family: Menlo, Monaco, Consolas, monospace;
                background-color: #f1f5f9;
                color: #334155;
            }}
            pre {{
                font-family: Menlo, Monaco, Consolas, monospace;
                background-color: #f8fafc;
                border: 1px solid {WINDOW_PALETTE['border']};
                border-radius: 8px;
                padding: 10px;
            }}
            table {{
                border-collapse: collapse;
                margin-top: 0.6em;
                margin-bottom: 0.8em;
            }}
            th, td {{
                border: 1px solid {WINDOW_PALETTE['border']};
                padding: 6px 8px;
            }}
            th {{
                background-color: #f8fafc;
                font-weight: 700;
            }}
            a {{
                color: {WINDOW_PALETTE['accent']};
                text-decoration: none;
            }}
            """
        )

    @staticmethod
    def _danger_button_style() -> str:
        return (
            f"""
            QPushButton {{
                color: white;
                background-color: {WINDOW_PALETTE['danger']};
                border: none;
                border-radius: 8px;
                padding: 6px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:disabled {{
                background-color: #E2E8F0;
                color: #64748B;
            }}
            QPushButton:hover:!disabled {{
                background-color: #DC2626;
            }}
            """
        )
