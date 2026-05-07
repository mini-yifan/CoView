"""Code Agent jobs panel for the control console."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from baodou_ai.code_agent.manager import JobManager
from baodou_ai.gui.i18n import t


PALETTE = {
    "card": "#E8E8ED",
    "text_primary": "#111111",
    "text_secondary": "#707070",
    "text_muted": "#999999",
    "input_bg": "#FFFFFF",
    "divider": "#C9CBD3",
}


class CodeAgentJobsPanel(QFrame):
    """Displays and refreshes background Code Agent jobs."""

    def __init__(
        self,
        job_manager: Optional[JobManager],
        small_button_style_provider: Callable[[], str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._job_manager = job_manager
        self._small_button_style_provider = small_button_style_provider
        self._build_ui()

    def refresh_jobs(self) -> None:
        self._refresh_job_layout(self._jobs_container_layout)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {PALETTE['card']};
                border: 1px solid {PALETTE['divider']};
                border-radius: 18px;
            }}
            """
        )
        self.setMinimumHeight(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)
        title = QLabel(t("jobs_panel_title"))
        title.setStyleSheet(
            f"""
            QLabel {{
                color: {PALETTE['text_primary']};
                font-size: 15px;
                font-weight: 700;
            }}
            """
        )
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QPushButton(t("jobs_panel_refresh"))
        refresh_btn.setStyleSheet(self._small_button_style_provider())
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh_jobs)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        desc = QLabel(t("jobs_panel_desc"))
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"""
            QLabel {{
                color: {PALETTE['text_secondary']};
                font-size: 12px;
                background: transparent;
                border: none;
            }}
            """
        )
        layout.addWidget(desc)

        self._jobs_scroll = QScrollArea()
        self._jobs_scroll.setWidgetResizable(True)
        self._jobs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._jobs_scroll.setMinimumHeight(280)
        self._jobs_scroll.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background: transparent;
            }
            """
        )
        self._jobs_container = QWidget()
        self._jobs_container_layout = QVBoxLayout(self._jobs_container)
        self._jobs_container_layout.setSpacing(12)
        self._jobs_container_layout.setContentsMargins(0, 0, 0, 0)
        self._jobs_scroll.setWidget(self._jobs_container)
        layout.addWidget(self._jobs_scroll)
        self.refresh_jobs()

    def _refresh_job_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        jobs = self._job_manager.list_jobs() if self._job_manager is not None else []
        if not jobs:
            empty = QLabel(t("jobs_panel_empty"))
            empty.setWordWrap(True)
            empty.setStyleSheet(
                f"""
                QLabel {{
                    color: {PALETTE['text_muted']};
                    font-size: 12px;
                    padding: 10px 4px;
                    background: transparent;
                }}
                """
            )
            layout.addWidget(empty)
            layout.addStretch()
            return

        for job in jobs:
            layout.addWidget(self._build_job_card(job))
        layout.addStretch()

    def _build_job_card(self, job: Dict[str, Any]) -> QWidget:
        card = QFrame()
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {PALETTE['input_bg']};
                border: 1px solid {PALETTE['divider']};
                border-radius: 16px;
            }}
            """
        )
        card.setMinimumHeight(150)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(12)
        title = QLabel(str(job.get("title") or job.get("job_id") or t("jobs_panel_job_fallback_title")))
        title.setStyleSheet(
            f"""
            QLabel {{
                color: {PALETTE['text_primary']};
                font-size: 14px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
            """
        )
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._build_status_label(str(job.get("status") or "").strip()))
        layout.addLayout(header)

        meta = QLabel(
            "\n".join(
                [
                    f"{t('jobs_panel_meta_job_id')}: {job.get('job_id') or '-'}",
                    f"{t('jobs_panel_meta_provider')}: {job.get('provider') or '-'}",
                    f"{t('jobs_panel_meta_workspace')}: {job.get('workspace_path') or '-'}",
                ]
            )
        )
        meta.setWordWrap(True)
        meta.setStyleSheet(
            f"""
            QLabel {{
                color: {PALETTE['text_secondary']};
                font-size: 11px;
                line-height: 1.5;
                background: transparent;
                border: none;
            }}
            """
        )
        layout.addWidget(meta)

        summary = str(job.get("summary") or job.get("error") or "").strip()
        if summary:
            summary_label = QLabel(summary)
            summary_label.setWordWrap(True)
            summary_label.setStyleSheet(
                f"""
                QLabel {{
                    color: {PALETTE['text_primary']};
                    font-size: 12px;
                    background: #FFFFFF;
                    padding: 10px 12px;
                    border-radius: 12px;
                    border: 1px solid {PALETTE['divider']};
                }}
                """
            )
            layout.addWidget(summary_label)

        log_excerpt = str(job.get("latest_log_excerpt") or "").strip()
        if log_excerpt:
            log_label = QLabel(log_excerpt)
            log_label.setWordWrap(True)
            log_label.setStyleSheet(
                f"""
                QLabel {{
                    color: {PALETTE['text_muted']};
                    font-size: 11px;
                    background: rgba(255, 255, 255, 0.92);
                    padding: 10px 12px;
                    border-radius: 10px;
                    border: 1px dashed {PALETTE['divider']};
                }}
                """
            )
            layout.addWidget(log_label)

        actions = QHBoxLayout()
        actions.addStretch()
        status_value = str(job.get("status") or "")
        job_id = str(job.get("job_id") or "")
        if status_value == "running":
            action_btn = QPushButton(t("jobs_panel_action_cancel"))
            action_btn.clicked.connect(lambda _checked=False, job_id=job_id: self._cancel_job(job_id))
        else:
            action_btn = QPushButton(t("jobs_panel_action_dismiss"))
            action_btn.clicked.connect(lambda _checked=False, job_id=job_id: self._dismiss_job(job_id))
        action_btn.setCursor(Qt.PointingHandCursor)
        action_btn.setStyleSheet(self._small_button_style_provider())
        actions.addWidget(action_btn)
        layout.addLayout(actions)
        return card

    def _build_status_label(self, status: str) -> QLabel:
        status_bg_map = {
            "running": "#DBEAFE",
            "queued": "#FEF3C7",
            "pending": "#FEF3C7",
            "done": "#DCFCE7",
            "completed": "#DCFCE7",
            "success": "#DCFCE7",
            "failed": "#FEE2E2",
            "error": "#FEE2E2",
            "cancelled": "#F3F4F6",
        }
        status_text_map = {
            "running": "#1D4ED8",
            "queued": "#92400E",
            "pending": "#92400E",
            "done": "#166534",
            "completed": "#166534",
            "success": "#166534",
            "failed": "#B91C1C",
            "error": "#B91C1C",
            "cancelled": "#4B5563",
        }
        status_bg = status_bg_map.get(status.lower(), "#F3F4F6")
        status_text = status_text_map.get(status.lower(), PALETTE["text_secondary"])
        label = QLabel(t(f"jobs_panel_status_{status.lower()}"))
        label.setStyleSheet(
            f"""
            QLabel {{
                color: {status_text};
                font-size: 11px;
                font-weight: 700;
                padding: 5px 10px;
                background-color: {status_bg};
                border-radius: 999px;
                border: none;
            }}
            """
        )
        return label

    def _cancel_job(self, job_id: str) -> None:
        if self._job_manager is None:
            return
        try:
            self._job_manager.cancel(job_id)
        finally:
            self.refresh_jobs()

    def _dismiss_job(self, job_id: str) -> None:
        if self._job_manager is None:
            return
        try:
            self._job_manager.dismiss(job_id)
        finally:
            self.refresh_jobs()
