"""Window geometry/orchestration coordinator for floating overlay widgets."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QTimer,
)
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication

from baodou_ai.gui.floating.overlay_utils import edge_anchor, edge_anchor_in, screen_at


class OverlayWindowCoordinator:
    """Centralizes floating overlay geometry and expand/collapse orchestration."""

    def __init__(self, controller: "FloatingController") -> None:
        self._controller = controller
        self._pending_expand_after_unsnap = False
        self._snap_anchor = QPoint(0, 0)

        self.snap_anim = QPropertyAnimation(controller.ball_window, b"geometry")
        self.snap_anim.setDuration(250)
        self.snap_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.snap_anim.finished.connect(self._on_snap_finished)

        self.unsnap_anim = QPropertyAnimation(controller.ball_window, b"geometry")
        self.unsnap_anim.setDuration(300)
        self.unsnap_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.unsnap_anim.finished.connect(self._on_unsnap_finished)

        self.collapse_timer = QTimer()
        self.collapse_timer.setInterval(180)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.timeout.connect(self.collapse)

        self.hover_timer = QTimer()
        self.hover_timer.setInterval(100)
        self.hover_timer.timeout.connect(self.check_global_hover)

        self.drag_follow_timer = QTimer()
        self.drag_follow_timer.setInterval(16)
        self.drag_follow_timer.setSingleShot(True)
        self.drag_follow_timer.timeout.connect(self._flush_drag_follow_updates)
        self._pending_drag_anchor: Optional[QPoint] = None

    def nearest_edge(self) -> Optional[str]:
        c = self._controller
        screen = screen_at(c.ball_anchor + QPoint(c.ball_size // 2, c.ball_size // 2)) or QApplication.primaryScreen()
        sg = screen.geometry()
        center_x = c.ball_anchor.x() + c.ball_size / 2
        center_y = c.ball_anchor.y() + c.ball_size / 2
        distances = {
            "right": sg.x() + sg.width() - center_x,
            "left": center_x - sg.x(),
            "bottom": sg.y() + sg.height() - center_y,
            "top": center_y - sg.y(),
        }
        return min(distances, key=distances.get)

    def determine_expand_direction(self) -> None:
        c = self._controller
        ball_center = c.ball_anchor + QPoint(c.ball_size // 2, c.ball_size // 2)
        screen = screen_at(ball_center) or QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        c.expand_direction = "left" if ball_center.x() > screen_geometry.center().x() else "right"
        c.v_expand_direction = (
            "down"
            if c.ball_anchor.y() - screen_geometry.y() < c.expanded_height - c.ball_size
            else "up"
        )
        c.panel_window.set_direction(c.expand_direction, c.v_expand_direction)

    def is_hovering_any(self) -> bool:
        c = self._controller
        global_pos = QCursor.pos()
        return c.ball_window.geometry().contains(global_pos) or (
            c.panel_window.isVisible() and c.panel_window.geometry().contains(global_pos)
        )

    def check_global_hover(self) -> None:
        c = self._controller
        if not self._should_run_hover_timer():
            self.hover_timer.stop()
            return
        if c.is_dragging or c.is_edge_hidden or c.panel_window.is_animating():
            return
        if (
            self.snap_anim.state() == QAbstractAnimation.Running
            or self.unsnap_anim.state() == QAbstractAnimation.Running
        ):
            return
        if self.is_hovering_any():
            c._mark_voice_user_interaction()
            self.collapse_timer.stop()
            if not c.panel_window.target_visible:
                self.expand()
            return
        if (
            c.panel_window.target_visible
            and not c.is_pinned
            and not c._task_active()
            and not c._is_waiting_for_tts()
            and not self.collapse_timer.isActive()
        ):
            self.collapse_timer.start()
        if not c.panel_window.target_visible and not c.is_pinned and not c._task_active():
            edge = self.check_edge_snap()
            if edge:
                self.snap_to_edge(edge)

    def _should_run_hover_timer(self) -> bool:
        c = self._controller
        if c.is_edge_hidden or c.is_dragging:
            return False
        if not c.ball_window.isVisible():
            return False
        if (
            self.snap_anim.state() == QAbstractAnimation.Running
            or self.unsnap_anim.state() == QAbstractAnimation.Running
        ):
            return False
        return True

    def _sync_hover_timer(self) -> None:
        if self._should_run_hover_timer():
            if not self.hover_timer.isActive():
                self.hover_timer.start()
            return
        self.hover_timer.stop()

    def on_ball_hover_enter(self) -> None:
        c = self._controller
        if not self._should_run_hover_timer():
            return
        c._mark_voice_user_interaction()
        self.collapse_timer.stop()
        if not c.panel_window.target_visible:
            self.expand()

    def expand(self) -> None:
        c = self._controller
        if c.panel_window.target_visible:
            return
        begin = getattr(c, "begin_interaction", None)
        if callable(begin):
            begin("panel")
        self.collapse_timer.stop()
        self.determine_expand_direction()
        c.panel_window.pinned_active = c.is_pinned
        c.panel_window.show_expanding(c.ball_anchor)
        if not c._task_active():
            QTimer.singleShot(50, c._show_history_if_idle)
        c.keep_ball_on_top()
        c._sync_voice_interaction_state()
        c._reposition_companion_window()
        self._sync_hover_timer()

    def collapse(self) -> None:
        c = self._controller
        if (
            c.is_pinned
            or c._task_active()
            or c._is_waiting_for_tts()
            or (not c.panel_window.target_visible and not c.panel_window.isVisible())
        ):
            return
        self.collapse_timer.stop()
        c.panel_window.hide_collapsing(c.ball_anchor)
        c.keep_ball_on_top(raise_windows=False)
        c._sync_voice_interaction_state()
        self._sync_hover_timer()

    def collapse_instantly(self) -> None:
        c = self._controller
        self.collapse_timer.stop()
        c.panel_window.hide_immediately()
        c.keep_ball_on_top(raise_windows=False)
        c._sync_voice_interaction_state()
        c._reposition_companion_window()
        self._sync_hover_timer()

    def on_ball_click(self) -> None:
        c = self._controller
        c._mark_voice_user_interaction()
        if c._task_active():
            return
        c.is_pinned = not c.is_pinned
        c.panel_window.pinned_active = c.is_pinned
        if c.is_pinned:
            self.expand()
        elif not self.is_hovering_any():
            self.collapse()
        c.ball_window.update()
        c.panel_window.update()
        c._sync_voice_interaction_state()

    def on_ball_long_press(self) -> None:
        c = self._controller
        c._mark_voice_user_interaction()
        begin = getattr(c, "begin_interaction", None)
        if callable(begin):
            begin("drag")
        c.is_dragging = True
        if c.is_pinned:
            c.is_pinned = False
            c.panel_window.pinned_active = False
            c.panel_window.update()
            c.ball_window.update()
        self.collapse_timer.stop()
        self.collapse_instantly()
        self._sync_hover_timer()

    def on_ball_drag(self, new_anchor: QPoint) -> None:
        c = self._controller
        c._mark_voice_user_interaction()
        c.ball_anchor = QPoint(new_anchor)
        c.ball_window.move_to_anchor(c.ball_anchor)
        self._pending_drag_anchor = QPoint(c.ball_anchor)
        self._sync_hover_timer()
        if not self.drag_follow_timer.isActive():
            self.drag_follow_timer.start()

    def on_ball_drag_finished(self) -> None:
        c = self._controller
        c._mark_voice_user_interaction()
        c.is_dragging = False
        end = getattr(c, "end_interaction", None)
        if callable(end):
            end("drag")
        self._force_drag_follow_updates()
        self._sync_hover_timer()
        if c._task_active():
            c.keep_ball_on_top()
            return
        edge = self.check_edge_snap()
        if edge:
            self.snap_to_edge(edge)
            return
        c.keep_ball_on_top()
        if c.ball_window.global_ball_rect().contains(QCursor.pos()) and not c.is_pinned:
            self.expand()

    def _flush_drag_follow_updates(self) -> None:
        c = self._controller
        if self._pending_drag_anchor is None:
            return
        self._pending_drag_anchor = None
        if c.is_edge_hidden:
            return
        if c.panel_window.target_visible or c.panel_window.isVisible():
            c.panel_window.reposition_for_anchor(c.ball_anchor)
        c.keep_ball_on_top(raise_windows=False, sync_helpers=False)
        c._reposition_companion_window()
        c._reposition_toast_window()

    def _force_drag_follow_updates(self) -> None:
        if self.drag_follow_timer.isActive():
            self.drag_follow_timer.stop()
        self._flush_drag_follow_updates()

    def check_edge_snap(self) -> Optional[str]:
        c = self._controller
        screen = screen_at(c.ball_anchor + QPoint(c.ball_size // 2, c.ball_size // 2)) or QApplication.primaryScreen()
        sg = screen.geometry()
        threshold = c.ball_size / 5
        offsets = {
            "left": max(0, sg.x() - c.ball_anchor.x()),
            "right": max(0, (c.ball_anchor.x() + c.ball_size) - sg.right()),
            "top": max(0, sg.y() - c.ball_anchor.y()),
            "bottom": max(0, (c.ball_anchor.y() + c.ball_size) - sg.bottom()),
        }
        best = max(offsets, key=offsets.get)
        return best if offsets[best] > threshold else None

    def snap_to_edge(self, edge_side: str) -> None:
        c = self._controller
        c.is_edge_hidden = True
        self._sync_hover_timer()
        c.edge_side = edge_side
        if c.is_pinned:
            c.is_pinned = False
            c.panel_window.pinned_active = False
            c.panel_window.update()
            c._sync_voice_interaction_state()
        self.collapse_instantly()
        c._hide_toast_window()
        c._hide_companion_suggestions()

        screen = screen_at(c.ball_anchor + QPoint(c.ball_size // 2, c.ball_size // 2)) or QApplication.primaryScreen()
        off_anchor = edge_anchor(edge_side, screen.geometry(), c.ball_size, anchor=c.ball_anchor)
        self._snap_anchor = off_anchor
        self.snap_anim.stop()
        self.snap_anim.setStartValue(c.ball_window.geometry())
        self.snap_anim.setEndValue(
            QRect(
                off_anchor.x() - c.ball_window.shadow_margin,
                off_anchor.y() - c.ball_window.shadow_margin,
                c.ball_window.width(),
                c.ball_window.height(),
            )
        )
        self.snap_anim.start()

    def _on_snap_finished(self) -> None:
        c = self._controller
        c.ball_anchor = self._snap_anchor
        c.ball_window.hide()
        c.edge_bar.show_at_edge(c.edge_side, c.ball_anchor)
        self._sync_hover_timer()

    def unsnap_from_edge(self, global_pos: QPoint) -> None:
        c = self._controller
        c.is_edge_hidden = False
        c.edge_bar.hide_bar()
        self._sync_hover_timer()

        screen = screen_at(global_pos) or QApplication.primaryScreen()
        sg = screen.geometry()
        bs = c.ball_size
        pad = 5
        start_anchor = edge_anchor(
            c.edge_side,
            sg,
            bs,
            anchor=QPoint(
                min(max(sg.x(), global_pos.x() - bs // 2), sg.right() - bs),
                min(max(sg.y(), global_pos.y() - bs // 2), sg.bottom() - bs),
            ),
        )
        inside_anchor = edge_anchor_in(c.edge_side, sg, bs, pad)
        if c.edge_side in ("left", "right"):
            end_anchor = QPoint(inside_anchor.x(), start_anchor.y())
        else:
            end_anchor = QPoint(start_anchor.x(), inside_anchor.y())

        c.ball_anchor = start_anchor
        c.ball_window.move_to_anchor(c.ball_anchor)
        c.ball_window.show()

        self.unsnap_anim.stop()
        self.unsnap_anim.setStartValue(c.ball_window.geometry())
        c.ball_anchor = end_anchor
        self.unsnap_anim.setEndValue(
            QRect(
                end_anchor.x() - c.ball_window.shadow_margin,
                end_anchor.y() - c.ball_window.shadow_margin,
                c.ball_window.width(),
                c.ball_window.height(),
            )
        )
        self.unsnap_anim.start()
        c._reposition_companion_window()
        self._sync_hover_timer()

    def _on_unsnap_finished(self) -> None:
        c = self._controller
        self._sync_hover_timer()
        c.keep_ball_on_top()
        if self._pending_expand_after_unsnap:
            self._pending_expand_after_unsnap = False
            c.is_pinned = True
            c.panel_window.pinned_active = True
            c.ball_window.update()
            self.expand()
            c._sync_voice_interaction_state()

    def activate_from_hotkey(self) -> bool:
        c = self._controller
        c._mark_voice_user_interaction()
        was_running = c._task_active()
        waiting_tts = c._is_waiting_for_tts()

        if c._ui_task_state.status_key == "running":
            c.handle_stop_request()

        if was_running:
            c.panel_window.set_idle_state()
            c._set_runtime_state("ready", c._t("agent_ready"))

        if waiting_tts:
            c._tts.stop()
            c.panel_window.set_idle_state()
            c._set_runtime_state("ready", c._t("agent_ready"))
            c._show_history_if_idle()

        if c.is_edge_hidden:
            self._pending_expand_after_unsnap = True
            self.unsnap_from_edge(c.ball_anchor + QPoint(c.ball_size // 2, c.ball_size // 2))
            return True

        c.is_pinned = True
        c.panel_window.pinned_active = True
        c.ball_window.update()

        if not c.panel_window.target_visible:
            self.expand()
        else:
            c.panel_window.input_area.setFocus()
            c._sync_voice_interaction_state()
        return True

    def hide_to_edge(self) -> None:
        c = self._controller
        c._mark_voice_user_interaction()
        if c._task_active() or c.is_edge_hidden:
            return
        c.is_pinned = False
        c.panel_window.pinned_active = False
        c.ball_window.update()
        c._sync_voice_interaction_state()
        self.collapse_timer.stop()
        self.collapse_instantly()
        edge = self.nearest_edge()
        if edge:
            self.snap_to_edge(edge)

    def collapse_from_hotkey(self) -> None:
        c = self._controller
        c._mark_voice_user_interaction()
        if c._task_active() or c.is_edge_hidden:
            return
        c.is_pinned = False
        c.panel_window.pinned_active = False
        c.ball_window.update()
        c.panel_window.update()
        c._sync_voice_interaction_state()
        self.collapse_timer.stop()
        self.collapse_instantly()
