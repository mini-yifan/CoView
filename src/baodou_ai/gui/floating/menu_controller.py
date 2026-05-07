"""Context menu controller for the floating ball."""

from __future__ import annotations

import platform

from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QMenu, QMessageBox

from baodou_ai.gui.floating.theme import menu_style
from baodou_ai.gui.i18n import t


class FloatingMenuController:
    def __init__(
        self,
        open_console,
        clear_history,
        shutdown,
        is_companion_enabled=lambda: True,
        toggle_companion=lambda: None,
        begin_interaction=lambda _reason: None,
        end_interaction=lambda _reason: None,
    ) -> None:
        self._open_console = open_console
        self._clear_history = clear_history
        self._shutdown = shutdown
        self._is_companion_enabled = is_companion_enabled
        self._toggle_companion = toggle_companion
        self._begin_interaction = begin_interaction
        self._end_interaction = end_interaction
        self._menu = None
        self._view_action = None
        self._settings_action = None
        self._toggle_companion_action = None
        self._clear_history_action = None
        self._close_action = None

    @staticmethod
    def _skip_confirmation_dialogs() -> bool:
        return platform.system() == "Windows"

    def _ensure_menu(self) -> QMenu:
        if self._menu is not None:
            return self._menu
        menu = QMenu()
        menu.setStyleSheet(menu_style())
        view_action = menu.addAction(t("tray_view"))
        settings_action = menu.addAction(t("tray_settings"))
        toggle_companion_action = menu.addAction("")
        clear_history_action = menu.addAction(t("tray_clear_history"))
        menu.addSeparator()
        close_action = menu.addAction(t("tray_close"))
        view_action.triggered.connect(lambda: self._open_console(6))
        settings_action.triggered.connect(lambda: self._open_console(0))
        toggle_companion_action.triggered.connect(self._toggle_companion)
        clear_history_action.triggered.connect(self._handle_clear_history)
        close_action.triggered.connect(self._handle_close)
        menu.aboutToShow.connect(lambda: self._begin_interaction("menu"))
        menu.aboutToHide.connect(lambda: self._end_interaction("menu"))
        self._menu = menu
        self._view_action = view_action
        self._settings_action = settings_action
        self._toggle_companion_action = toggle_companion_action
        self._clear_history_action = clear_history_action
        self._close_action = close_action
        return menu

    def show_ball_context_menu(self, global_pos: QPoint) -> None:
        menu = self._ensure_menu()
        self._refresh_menu_text()
        menu.popup(global_pos)

    def _refresh_menu_text(self) -> None:
        if self._view_action is not None:
            self._view_action.setText(t("tray_view"))
        if self._settings_action is not None:
            self._settings_action.setText(t("tray_settings"))
        companion_enabled = bool(self._is_companion_enabled())
        if self._toggle_companion_action is not None:
            self._toggle_companion_action.setText(
                t("tray_disable_companion") if companion_enabled else t("tray_enable_companion")
            )
        if self._clear_history_action is not None:
            self._clear_history_action.setText(t("tray_clear_history"))
        if self._close_action is not None:
            self._close_action.setText(t("tray_close"))

    def _handle_clear_history(self) -> None:
        if self._skip_confirmation_dialogs():
            self._clear_history()
            return
        msg_box = QMessageBox()
        msg_box.setWindowTitle(t("clear_history_title"))
        msg_box.setText(t("clear_history_text"))
        msg_box.setIcon(QMessageBox.Question)
        msg_box.addButton(t("clear_history_cancel"), QMessageBox.RejectRole)
        confirm_btn = msg_box.addButton(t("clear_history_confirm"), QMessageBox.AcceptRole)
        msg_box.exec_()
        if msg_box.clickedButton() == confirm_btn:
            self._clear_history()

    def _handle_close(self) -> None:
        if self._skip_confirmation_dialogs():
            self._shutdown()
            return
        msg_box = QMessageBox()
        msg_box.setWindowTitle(t("close_title"))
        msg_box.setText(t("close_text"))
        msg_box.setIcon(QMessageBox.Question)
        msg_box.addButton(t("close_cancel"), QMessageBox.RejectRole)
        confirm_btn = msg_box.addButton(t("close_confirm"), QMessageBox.AcceptRole)
        msg_box.exec_()
        if msg_box.clickedButton() == confirm_btn:
            self._shutdown()
