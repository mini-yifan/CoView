"""Expanded floating panel widget."""

from __future__ import annotations

import html
import re
from typing import Any, Dict, Optional

from PyQt5.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRect, QTimer, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QRegion, QTextDocument
from PyQt5.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from baodou_ai.core.screenshot import CAPTURE_EXCLUDE_PROPERTY
from baodou_ai.gui.floating.input_panel import FloatingInputPanel, StopButton
from baodou_ai.gui.floating.overlay_utils import (
    apply_native_borderless_hints,
    enter_overlay_transparent_mode,
    exit_overlay_transparent_mode,
    setup_overlay_window,
)
from baodou_ai.gui.floating.theme import (
    PALETTE,
    intermediate_report_style,
    result_card_style,
    scroll_area_style,
    status_bubble_style,
    timestamp_style,
    user_bubble_style,
)
from baodou_ai.gui.i18n import t


class PanelWindow(QWidget):
    """展开后的主交互面板。"""

    def __init__(self, controller: "FloatingController"):
        super().__init__()
        self.controller = controller
        self.ball_size = controller.ball_size
        self.expanded_width = controller.expanded_width
        self.expanded_height = controller.expanded_height
        self.shadow_left = 6
        self.shadow_right = 6
        self.shadow_top = 5
        self.shadow_bottom = 10
        self.h_expand_direction = "left"
        self.v_expand_direction = "up"
        self.target_visible = False
        self.pinned_active = False
        self._is_running = False
        self._current_task_text = ""
        self._result_displayed = False
        self._history_render_queue = []
        self._history_render_generation = 0

        setup_overlay_window(self)
        self.setProperty(CAPTURE_EXCLUDE_PROPERTY, True)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet(scroll_area_style())
        self.message_host = QWidget()
        self.message_host.setStyleSheet("background: transparent;")
        self.message_layout = QVBoxLayout(self.message_host)
        self.message_layout.setSpacing(12)
        self.message_layout.setContentsMargins(0, 0, 0, 0)
        self.message_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.message_host)

        self.input_panel = FloatingInputPanel(self)
        self.input_area = self.input_panel
        self.input_panel.submitted.connect(self._on_input_submitted)

        self.stop_button = StopButton(self)
        self.stop_button.hide()
        self.stop_button.clicked.connect(self._on_stop_clicked)

        self.scroll_effect = QGraphicsOpacityEffect()
        self.scroll_area.setGraphicsEffect(self.scroll_effect)
        self.input_effect = QGraphicsOpacityEffect()
        self.input_area.setGraphicsEffect(self.input_effect)
        self.stop_effect = QGraphicsOpacityEffect()
        self.stop_button.setGraphicsEffect(self.stop_effect)

        self.geo_anim = QPropertyAnimation(self, b"geometry")
        self.geo_anim.setDuration(300)
        self.geo_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.geo_anim.valueChanged.connect(self._on_anim_value_changed)
        self.geo_anim.finished.connect(self._on_anim_finished)

        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(300)
        self.opacity_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._focus_input_on_finish = True
        self._animation_light_mode = False

        self.installEventFilter(self)
        self.input_area.installEventFilter(self)
        self.scroll_area.viewport().installEventFilter(self)

        self._status_widget: Optional[QLabel] = None
        self._intermediate_report_widget: Optional[QLabel] = None
        self._intermediate_report_animation: Optional[QPropertyAnimation] = None
        self._voice_indicator_state = "off"
        self._voice_indicator_level = 0.0
        self._voice_indicator_phase = 0
        self._voice_indicator_timer = QTimer(self)
        self._voice_indicator_timer.setInterval(120)
        self._voice_indicator_timer.timeout.connect(self._tick_voice_indicator)
        self.resize(self.expanded_width + self.shadow_left + self.shadow_right, self.expanded_height + self.shadow_top + self.shadow_bottom)
        self.hide()
        self._set_content_opacity(1.0)

    def _surface_rect(self) -> QRect:
        return QRect(
            self.shadow_left,
            self.shadow_top,
            max(1, self.width() - self.shadow_left - self.shadow_right),
            max(1, self.height() - self.shadow_top - self.shadow_bottom),
        )

    def _apply_shape(self) -> None:
        surface = self._surface_rect()
        if surface.width() <= 0 or surface.height() <= 0:
            return

        region = QRegion()
        path = QPainterPath()
        path.addRoundedRect(float(surface.x()), float(surface.y()), float(surface.width()), float(surface.height()), 36.0, 36.0)
        region = region.united(QRegion(path.toFillPolygon().toPolygon()))
        for extra in (2, 4, 5):
            shadow_path = QPainterPath()
            shadow_rect = surface.adjusted(-extra, -extra, extra, extra)
            shadow_path.addRoundedRect(
                float(shadow_rect.x()),
                float(shadow_rect.y()),
                float(shadow_rect.width()),
                float(shadow_rect.height()),
                36.0 + extra,
                36.0 + extra,
            )
            region = region.united(QRegion(shadow_path.toFillPolygon().toPolygon()))
        self.setMask(region)

    def set_direction(self, horizontal: str, vertical: str) -> None:
        self.h_expand_direction = horizontal
        self.v_expand_direction = vertical
        self._layout_children()
        self.update()

    def _set_content_opacity(self, opacity: float) -> None:
        normalized = max(0.0, min(1.0, float(opacity)))
        self.scroll_effect.setOpacity(normalized)
        self.input_effect.setOpacity(normalized)
        self.stop_effect.setOpacity(normalized)

    def _expanded_geometry_for_anchor(self, anchor: QPoint) -> QRect:
        x = anchor.x() - (self.expanded_width - self.ball_size) - self.shadow_left if self.h_expand_direction == "left" else anchor.x() - self.shadow_left
        y = anchor.y() - (self.expanded_height - self.ball_size) - self.shadow_top if self.v_expand_direction == "up" else anchor.y() - self.shadow_top
        return QRect(x, y, self.expanded_width + self.shadow_left + self.shadow_right, self.expanded_height + self.shadow_top + self.shadow_bottom)

    def _collapsed_geometry_for_anchor(self, anchor: QPoint) -> QRect:
        return QRect(
            anchor.x() - self.shadow_left,
            anchor.y() - self.shadow_top,
            self.ball_size + self.shadow_left + self.shadow_right,
            self.ball_size + self.shadow_top + self.shadow_bottom,
        )

    def show_expanding(self, anchor: QPoint, focus_input_on_finish: bool = True, animate: bool = True) -> None:
        self.target_visible = True
        self._focus_input_on_finish = bool(focus_input_on_finish)
        self.geo_anim.stop()
        self.opacity_anim.stop()
        self._animation_light_mode = bool(animate)
        if hasattr(Qt, "WA_ShowWithoutActivating"):
            self.setAttribute(Qt.WA_ShowWithoutActivating, not focus_input_on_finish)

        if animate:
            self.setGeometry(self._collapsed_geometry_for_anchor(anchor))
            self._layout_children()
            self._apply_shape()
            self.setWindowOpacity(0.25)
            self._set_content_opacity(0.0)
            self.show()
            if focus_input_on_finish:
                self.raise_()
            self.geo_anim.setStartValue(self.geometry())
            self.geo_anim.setEndValue(self._expanded_geometry_for_anchor(anchor))
            self.opacity_anim.setStartValue(0.25)
            self.opacity_anim.setEndValue(1.0)
            self.geo_anim.start()
            self.opacity_anim.start()
            return

        self._animation_light_mode = False
        self.setGeometry(self._expanded_geometry_for_anchor(anchor))
        self.setWindowOpacity(1.0)
        self.show()
        if focus_input_on_finish:
            self.raise_()
        self._set_content_opacity(1.0)
        self._apply_shape()
        self._layout_children()
        self.update()
        self.controller.keep_ball_on_top()
        if focus_input_on_finish and not self._is_running:
            QTimer.singleShot(0, self.input_area.setFocus)

    def hide_collapsing(self, anchor: QPoint) -> None:
        if not self.isVisible() and not self.target_visible:
            return
        self.target_visible = False
        self.geo_anim.stop()
        self.opacity_anim.stop()
        self._animation_light_mode = True
        self.input_area.clearFocus()
        self.geo_anim.setStartValue(self.geometry())
        self.geo_anim.setEndValue(self._collapsed_geometry_for_anchor(anchor))
        self.opacity_anim.setStartValue(max(0.0, float(self.windowOpacity())))
        self.opacity_anim.setEndValue(0.25)
        self.geo_anim.start()
        self.opacity_anim.start()

    def hide_immediately(self) -> None:
        self.target_visible = False
        self.geo_anim.stop()
        self.opacity_anim.stop()
        self._animation_light_mode = False
        end = getattr(self.controller, "end_interaction", None)
        if callable(end):
            end("panel")
        self.hide()
        self.setWindowOpacity(1.0)
        self._set_content_opacity(1.0)
        self.input_area.clearFocus()

    def reposition_for_anchor(self, anchor: QPoint) -> None:
        if not self.isVisible():
            return
        target_geometry = self._expanded_geometry_for_anchor(anchor) if self.target_visible else self._collapsed_geometry_for_anchor(anchor)
        self.setGeometry(target_geometry)
        self._apply_shape()

    def is_animating(self) -> bool:
        return self.geo_anim.state() == QAbstractAnimation.Running

    def set_idle_state(self) -> None:
        self._cancel_history_render()
        self._is_running = False
        self._current_task_text = ""
        self._result_displayed = False
        self._reset_messages()
        self._status_widget = None
        self.input_area.clear()
        self.input_area.show()
        self.stop_button.hide()
        self._layout_children()
        self.update()

    def show_running_state(
        self,
        task_text: str,
        anchor: Optional[QPoint] = None,
        focus_input_on_finish: bool = True,
        animate: bool = False,
        status_hint_text: str = "",
    ) -> None:
        if anchor is not None and (not self.isVisible() or not self.target_visible):
            self.show_expanding(anchor, focus_input_on_finish=focus_input_on_finish, animate=animate)
        self._cancel_history_render()
        self._is_running = True
        self._current_task_text = task_text
        self._result_displayed = False
        self._reset_messages()
        self._append_user_bubble(task_text)
        self._status_widget = self._append_status_bubble(
            self._build_status_text(t("executing"), status_hint_text=status_hint_text)
        )
        self._intermediate_report_widget = self._append_intermediate_report("")
        self._start_breathing_animation()
        self.input_area.hide()
        self.stop_button.show()
        self._layout_children()
        self._scroll_to_bottom()
        self.update()

    def show_stopping_state(self) -> None:
        if self._status_widget is not None:
            self._status_widget.setText(self._build_status_text(t("stopping")))
        self._scroll_to_bottom()
        self.update()

    def show_finished_state(self, result_text: str, status_text: str = "", tts_playing: bool = False) -> None:
        status_text = status_text or t("execution_ended")
        self._cancel_history_render()
        self._is_running = False
        self._stop_breathing_animation()
        if self._status_widget is not None:
            self._status_widget.setText(self._build_status_text(status_text))
        if not self._result_displayed:
            self._append_result_card(result_text)
        self._result_displayed = False
        if tts_playing:
            self.input_area.hide()
            self.stop_button.show()
        else:
            self.input_area.show()
            self.stop_button.hide()
        self._layout_children()
        self._scroll_to_bottom()
        self.update()

    def append_background_report(self, text: str) -> None:
        normalized = str(text or "").strip()
        if not normalized:
            return
        self._append_result_card(normalized)
        self._scroll_to_bottom()
        self.update()

    def show_error_state(self, error_text: str, status_text: str = "") -> None:
        status_text = status_text or t("execution_failed")
        self.show_finished_state(error_text, status_text=status_text)

    def _reset_messages(self) -> None:
        while self.message_layout.count():
            item = self.message_layout.takeAt(0)
            layout = item.layout()
            widget = item.widget()
            if layout is not None:
                while layout.count():
                    child = layout.takeAt(0)
                    child_widget = child.widget()
                    if child_widget is not None:
                        child_widget.deleteLater()
                layout.deleteLater()
            elif widget is not None:
                widget.deleteLater()

    def _append_user_bubble(self, text: str) -> None:
        row = QHBoxLayout()
        row.addStretch()
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bubble.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        char_count = len(text)
        min_width_for_text = max(80, char_count * 18 + 36)
        content_width = self.expanded_width - 40
        max_bubble_width = content_width * 4 // 5
        bubble.setMinimumWidth(min(min_width_for_text, max_bubble_width))
        bubble.setMaximumWidth(max_bubble_width)
        bubble.setStyleSheet(user_bubble_style())
        row.addWidget(bubble, 0, Qt.AlignRight)
        self.message_layout.addLayout(row)

    def _append_status_bubble(self, text: str) -> QLabel:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextFormat(Qt.RichText)
        bubble.setMaximumWidth(max(200, self.expanded_width - 100))
        bubble.setStyleSheet(status_bubble_style())
        row.addWidget(bubble, 0, Qt.AlignLeft)
        row.addStretch()
        self.message_layout.addLayout(row)
        return bubble

    def update_status_hint(self, hint_text: str = "") -> None:
        if self._status_widget is None:
            return
        self._status_widget.setText(self._build_status_text(t("executing"), status_hint_text=hint_text))
        self._scroll_to_bottom()
        self.update()

    @staticmethod
    def _build_status_text(text: str, status_hint_text: str = "") -> str:
        main_text = html.escape(str(text or "").strip(), quote=False)
        hint = html.escape(str(status_hint_text or "").strip(), quote=False)
        if not hint:
            return main_text
        return (
            f"{main_text}<br>"
            f'<span style="font-size: 12px; color: {PALETTE["status_muted"]};">{hint}</span>'
        )

    def _append_intermediate_report(self, text: str) -> QLabel:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        label.setMinimumWidth(self.expanded_width - 40)
        label.setMaximumWidth(self.expanded_width - 40)
        label.setStyleSheet(intermediate_report_style())
        row.addWidget(label)
        self.message_layout.addLayout(row)
        return label

    def _start_breathing_animation(self) -> None:
        if self._intermediate_report_widget is None:
            return
        self._intermediate_report_animation = QPropertyAnimation(self._intermediate_report_widget, b"windowOpacity")
        self._intermediate_report_animation.setDuration(2000)
        self._intermediate_report_animation.setStartValue(0.4)
        self._intermediate_report_animation.setEndValue(1.0)
        self._intermediate_report_animation.setEasingCurve(QEasingCurve.InOutSine)
        self._intermediate_report_animation.setLoopCount(-1)
        self._intermediate_report_animation.start()

    def _stop_breathing_animation(self) -> None:
        if self._intermediate_report_animation is not None:
            self._intermediate_report_animation.stop()
            self._intermediate_report_animation = None
        if self._intermediate_report_widget is not None:
            self._intermediate_report_widget.hide()
            self._intermediate_report_widget = None

    def update_intermediate_report(self, payload: Dict[str, Any]) -> None:
        if self._intermediate_report_widget is None:
            return
        status = str(payload.get("status") or "").strip()
        if status == "respond":
            report = str(payload.get("action_result") or "").strip()
            if report:
                self._append_result_card(report)
                self._result_displayed = True
                self._scroll_to_bottom()
                self.update()
            return
        thinking = str(payload.get("thinking") or "").strip()
        if thinking:
            display_text = thinking[:100] + ("..." if len(thinking) > 100 else "")
            self._intermediate_report_widget.setText(display_text)
            self._intermediate_report_widget.show()
            self._scroll_to_bottom()
            self.update()

    def _render_markdown_report(self, text: str) -> tuple[str, str]:
        normalized = str(text or "").strip()
        if not normalized:
            return "", ""

        # Keep title lines readable without rendering heading syntax visually.
        normalized = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", normalized)
        markdown_only = html.escape(normalized, quote=False)

        document = QTextDocument(self)
        font = document.defaultFont()
        font.setPixelSize(14)
        document.setDefaultFont(font)
        
        document.setMarkdown(markdown_only)
        rendered_html = document.toHtml()
        plain_text = document.toPlainText().strip() or normalized
        return rendered_html, plain_text

    def _append_result_card(self, text: str) -> None:
        row = QHBoxLayout()
        row.setContentsMargins(0, -6, 0, 0)
        rendered_html, plain_text = self._render_markdown_report(text)
        bubble = QLabel(rendered_html or plain_text)
        bubble.setWordWrap(True)
        bubble.setOpenExternalLinks(True)
        bubble.setTextFormat(Qt.RichText)
        bubble.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.TextSelectableByMouse)
        bubble.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        bubble.setProperty("report_plain_text", plain_text)
        bubble.setProperty("report_source_markdown", text)
        char_count = len(plain_text)
        min_width_for_text = max(100, char_count * 16 + 32)
        bubble.setMinimumWidth(min(min_width_for_text, self.expanded_width - 40))
        bubble.setMaximumWidth(self.expanded_width - 40)
        bubble.setStyleSheet(result_card_style())
        row.addWidget(bubble, 0, Qt.AlignLeft)
        row.addStretch()
        self.message_layout.addLayout(row)
        bubble.adjustSize()
        self.message_host.updateGeometry()

    def show_history(self, tasks: list) -> None:
        self._is_running = False
        self._history_render_generation += 1
        generation = self._history_render_generation
        self._history_render_queue = list(tasks or [])
        self._reset_messages()
        self._status_widget = None
        self.input_area.show()
        self.stop_button.hide()
        if not tasks:
            self._layout_children()
            self.update()
            return
        self._layout_children()
        self.update()
        QTimer.singleShot(0, lambda: self._render_next_history_item(generation))

    def _cancel_history_render(self) -> None:
        self._history_render_generation += 1
        self._history_render_queue = []

    def _render_next_history_item(self, generation: int) -> None:
        if generation != self._history_render_generation:
            return
        if not self._history_render_queue:
            self._layout_children()
            self._scroll_to_bottom()
            self.update()
            return
        task = self._history_render_queue.pop(0)
        instruction = task.get("instruction", "")
        report = task.get("report", "")
        timestamp = task.get("timestamp", "")
        if instruction:
            self._append_user_bubble(instruction)
            if report:
                self._append_result_card(report)
            if timestamp:
                self._append_history_timestamp(timestamp)
        self._layout_children()
        self._scroll_to_bottom()
        self.update()
        QTimer.singleShot(0, lambda: self._render_next_history_item(generation))

    def set_voice_indicator(self, state: str, level: float = 0.0) -> None:
        self._voice_indicator_state = str(state or "off")
        self._voice_indicator_level = max(0.0, min(1.0, float(level or 0.0)))
        if self._voice_indicator_state == "off":
            self._voice_indicator_timer.stop()
        elif not self._voice_indicator_timer.isActive():
            self._voice_indicator_timer.start()
        self.update()

    def _tick_voice_indicator(self) -> None:
        self._voice_indicator_phase = (self._voice_indicator_phase + 1) % 40
        self.update()

    def _append_history_timestamp(self, text: str) -> None:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        label = QLabel(text)
        label.setStyleSheet(timestamp_style())
        row.addWidget(label, 0, Qt.AlignLeft)
        row.addStretch()
        self.message_layout.addLayout(row)

    def _scroll_to_bottom(self) -> None:
        def _apply() -> None:
            self.message_host.adjustSize()
            scrollbar = self.scroll_area.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        QTimer.singleShot(50, _apply)

    def _on_return_pressed(self) -> None:
        self.input_panel._emit_submit()

    def _on_input_submitted(self, text: str) -> None:
        if self._is_running:
            return
        self.controller.handle_submit(text)

    def _on_stop_clicked(self) -> None:
        self.controller.handle_stop_request()

    def _on_anim_value_changed(self, value) -> None:
        height = self.height()
        if isinstance(value, QRect):
            height = value.height()
        visible_height = max(1, height - self.shadow_top - self.shadow_bottom)
        progress = (
            (visible_height - self.ball_size) / (self.expanded_height - self.ball_size)
            if self.expanded_height != self.ball_size
            else 0.0
        )
        opacity = max(0.0, min(1.0, progress)) ** 1.5
        self._set_content_opacity(opacity)

    def _on_anim_finished(self) -> None:
        self._animation_light_mode = False
        end = getattr(self.controller, "end_interaction", None)
        if callable(end):
            end("panel")
        if self.target_visible:
            self.setWindowOpacity(1.0)
            self._set_content_opacity(1.0)
            self._layout_children()
            self._apply_shape()
            if not self._is_running and self._focus_input_on_finish:
                self.input_area.setFocus()
            self.controller.keep_ball_on_top()
        else:
            self.hide()
            self.setWindowOpacity(1.0)
            self._set_content_opacity(1.0)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        apply_native_borderless_hints(self)
        self._apply_shape()
        self.controller.protect_window(self)

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QEvent.WindowActivate, QEvent.FocusIn, QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.InputMethod):
            self.controller.keep_ball_on_top()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:
        if not self._animation_light_mode:
            self._layout_children()
            self._apply_shape()
        super().resizeEvent(event)

    def _layout_children(self) -> None:
        surface = self._surface_rect()
        width, height = surface.width(), surface.height()
        pill_height = self.ball_size
        if self.v_expand_direction == "up":
            pill_y = surface.bottom() - pill_height
            content_y = surface.y() + 20
        else:
            pill_y = surface.y()
            content_y = surface.y() + pill_height + 10
        content_height = max(1, height - pill_height - 30)
        self.scroll_area.setGeometry(surface.x() + 20, content_y, max(1, width - 40), content_height)

        baseline_y = pill_y + max(0, (pill_height - 40) // 2)
        if self.h_expand_direction == "left":
            input_x = surface.x() + 24
            input_width = max(1, width - self.ball_size - 34)
            stop_x = surface.x() + (self.ball_size - self.stop_button.width()) // 2
        else:
            input_x = surface.x() + self.ball_size + 10
            input_width = max(1, width - self.ball_size - 34)
            stop_x = surface.x() + width - self.ball_size + (self.ball_size - self.stop_button.width()) // 2
            
        self.input_area.setGeometry(input_x, baseline_y, input_width, 40)
        
        stop_y = pill_y + (pill_height - self.stop_button.height()) // 2
        self.stop_button.move(int(stop_x), int(stop_y))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        surface = self._surface_rect()
        if surface.width() <= 0 or surface.height() <= 0:
            return

        background_path = QPainterPath()
        background_path.addRoundedRect(float(surface.x()), float(surface.y()), float(surface.width()), float(surface.height()), 36, 36)
        painter.fillPath(background_path, QColor(PALETTE["panel_bg"]))

        pill_height = self.ball_size
        pill_y = surface.bottom() - pill_height if self.v_expand_direction == "up" else surface.y()
        pill_path = QPainterPath()
        pill_path.addRoundedRect(float(surface.x()), float(pill_y), float(surface.width()), float(pill_height), pill_height / 2, pill_height / 2)
        painter.fillPath(pill_path, QColor(PALETTE["input_bg"]))

        if self.pinned_active:
            painter.setPen(QPen(QColor(PALETTE["border_dark"]), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(surface.adjusted(2, 2, -2, -2), 34, 34)

        self._paint_voice_indicator(painter)

    def _paint_voice_indicator(self, painter: QPainter) -> None:
        state = self._voice_indicator_state
        if state == "off":
            return
        config = getattr(self.controller, "_config", None)
        is_wake_state = state.startswith("wake_")
        if is_wake_state:
            if config is not None and not bool(config.get("wake_word_config.show_indicator", True)):
                return
        elif config is not None and not bool(config.get("voice_interaction_config.show_voice_recording_indicator", True)):
            return

        input_rect = self.input_area.geometry()
        if input_rect.width() <= 0:
            return
        x = input_rect.x()
        y = max(0, input_rect.y() - 7)
        width = input_rect.width()
        height = 4
        level = max(0.0, min(1.0, self._voice_indicator_level))
        phase = self._voice_indicator_phase

        if state == "error":
            base_color = QColor("#E35D5D")
            active_color = QColor("#D83B3B")
            active_ratio = 1.0
        elif state == "wake_error":
            base_color = QColor(227, 93, 93, 110)
            active_color = QColor("#D83B3B")
            active_ratio = 1.0
        elif state == "processing":
            base_color = QColor(180, 180, 180, 130)
            active_color = QColor(PALETTE["black"])
            active_ratio = 0.28
        elif state == "wake_triggered":
            base_color = QColor(52, 211, 153, 72)
            active_color = QColor("#10B981")
            active_ratio = 1.0
        elif state == "wake_cooldown":
            base_color = QColor(245, 158, 11, 88)
            active_color = QColor("#F59E0B")
            active_ratio = 0.45
        elif state == "speaking":
            base_color = QColor(150, 150, 150, 120)
            active_color = QColor(PALETTE["black"])
            active_ratio = max(0.18, level)
        else:
            pulse = 0.25 + (phase % 20) / 80.0
            base_color = QColor(160, 160, 160, int(70 + pulse * 80))
            active_color = QColor(90, 90, 90, 160)
            active_ratio = max(0.08, min(0.22, level))

        painter.setPen(Qt.NoPen)
        painter.setBrush(base_color)
        painter.drawRoundedRect(x, y, width, height, 2, 2)

        active_width = max(8, int(width * active_ratio))
        if state == "processing":
            travel = max(1, width - active_width)
            active_x = x + int((phase % 20) / 19.0 * travel)
        else:
            active_x = x
        painter.setBrush(active_color)
        painter.drawRoundedRect(active_x, y, min(active_width, width), height, 2, 2)

    def enter_transparent_mode(self) -> None:
        platform_adapter = getattr(self.controller, "platform_adapter", getattr(self.controller, "_platform_adapter", None))
        enter_overlay_transparent_mode(self, platform_adapter)

    def exit_transparent_mode(self) -> None:
        platform_adapter = getattr(self.controller, "platform_adapter", getattr(self.controller, "_platform_adapter", None))
        exit_overlay_transparent_mode(self, platform_adapter)
