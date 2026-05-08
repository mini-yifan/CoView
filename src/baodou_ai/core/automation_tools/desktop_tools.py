"""Desktop interaction tools."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import pyautogui
import pyperclip

from .constants import automation_exports
from .runtime import ToolContext, ToolOutcome


class DesktopToolsMixin:
    def tool_click(
        self,
        screen_index: int,
        position: List[float],
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return self._execute_single_point_tool(
            screen_index=screen_index,
            position=position,
            action="click",
            success_summary="已点击",
            failure_summary="点击失败",
            screen_info=screen_info,
        )

    def tool_double_click(
        self,
        screen_index: int,
        position: List[float],
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return self._execute_single_point_tool(
            screen_index=screen_index,
            position=position,
            action="double_click",
            success_summary="已双击",
            failure_summary="双击失败",
            screen_info=screen_info,
        )

    def tool_long_press(
        self,
        screen_index: int,
        position: List[float],
        duration_seconds: float = 3.0,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        return self._execute_single_point_tool(
            screen_index=screen_index,
            position=position,
            action="long_press",
            success_summary="已长按",
            failure_summary="长按失败",
            screen_info=screen_info,
            long_press_duration_seconds=duration_seconds,
            should_stop=should_stop,
        )

    def tool_right_click(
        self,
        screen_index: int,
        position: List[float],
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return self._execute_single_point_tool(
            screen_index=screen_index,
            position=position,
            action="right_click",
            success_summary="已右击",
            failure_summary="右击失败",
            screen_info=screen_info,
        )

    def tool_drag(
        self,
        start_screen_index: int,
        start_position: List[float],
        end_screen_index: int,
        end_position: List[float],
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return self._execute_drag_tool(
            start_screen_index=start_screen_index,
            start_position=start_position,
            end_screen_index=end_screen_index,
            end_position=end_position,
            success_summary="已拖拽",
            failure_summary="拖拽失败",
            screen_info=screen_info,
        )

    def tool_scroll_up(
        self,
        screen_index: int,
        position: List[float],
        scroll_level: int = 5,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return self._execute_single_point_tool(
            screen_index=screen_index,
            position=position,
            action="scroll_up",
            success_summary="已向上滚动",
            failure_summary="向上滚动失败",
            screen_info=screen_info,
            scroll_level=scroll_level,
        )

    def tool_scroll_down(
        self,
        screen_index: int,
        position: List[float],
        scroll_level: int = 5,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return self._execute_single_point_tool(
            screen_index=screen_index,
            position=position,
            action="scroll_down",
            success_summary="已向下滚动",
            failure_summary="向下滚动失败",
            screen_info=screen_info,
            scroll_level=scroll_level,
        )

    def tool_hotkey(
        self,
        keys: List[str],
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        context = self._build_tool_context(screen_info)

        def operation(_context: ToolContext) -> ToolOutcome:
            self.hotkey(*keys)
            return self._build_tool_outcome(True, "已执行快捷键")

        return self._execute_tool_runtime(
            context=context,
            operation=operation,
            failure_summary="执行快捷键失败",
        )

    def tool_page_loading(
        self,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        context = self._build_tool_context(screen_info)

        def operation(_context: ToolContext) -> ToolOutcome:
            print("检测到页面正在加载，暂停...")
            return self._build_tool_outcome(True, "已等待页面稳定")

        return self._execute_tool_runtime(
            context=context,
            operation=operation,
            failure_summary="等待页面稳定失败",
        )

    def tool_launch_app(
        self,
        app_name: str,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        context = self._build_tool_context(screen_info)

        def operation(_context: ToolContext) -> ToolOutcome:
            result = self._platform_adapter.launch_app(app_name)
            if not result.get("matched", False):
                error = str(result.get("error") or "").strip()
                fallback = result.get("fallback")
                return self._build_tool_outcome(
                    False,
                    "启动应用失败" if error else "未找到应用",
                    error or "未找到应用",
                    fallback=fallback if isinstance(fallback, dict) else None,
                )
            return self._build_tool_outcome(True, "已启动应用")

        return self._execute_tool_runtime(
            context=context,
            operation=operation,
            failure_summary="启动应用失败",
        )

    def tool_open_app_launcher(
        self,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        context = self._build_tool_context(screen_info)

        def operation(_context: ToolContext) -> ToolOutcome:
            platform_result = self._platform_adapter.open_app_launcher()
            app_names = platform_result.get("app_names")
            return self._build_tool_outcome(
                True,
                "已打开应用启动器并获取应用列表",
                app_names=list(app_names) if isinstance(app_names, list) else [],
            )

        return self._execute_tool_runtime(
            context=context,
            operation=operation,
            failure_summary="打开应用启动器失败",
        )

    def tool_open_in_browser(
        self,
        url: Optional[str] = None,
        query: Optional[str] = None,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        context = self._build_tool_context(screen_info)

        def operation(_context: ToolContext) -> ToolOutcome:
            self._platform_adapter.open_in_browser(url=url, query=query)
            return self._build_tool_outcome(True, "已在默认浏览器中打开内容")

        return self._execute_tool_runtime(
            context=context,
            operation=operation,
            failure_summary="在默认浏览器中打开内容失败",
        )

    def tool_open_in_finder(
        self,
        path: Optional[str] = None,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        context = self._build_tool_context(screen_info)

        def operation(_context: ToolContext) -> ToolOutcome:
            result = self._platform_adapter.open_in_finder(path=path)
            if result.get("error"):
                return self._build_tool_outcome(False, result["error"])
            if path:
                return self._build_tool_outcome(True, f"已在访达中打开: {path}")
            return self._build_tool_outcome(True, "已打开桌面目录")

        return self._execute_tool_runtime(
            context=context,
            operation=operation,
            failure_summary="打开访达失败",
        )

    def _map_position_to_absolute(
        self,
        position: Union[List, Tuple],
        target_screen: Optional[Dict[str, Any]] = None,
    ) -> List[float]:
        """将 0-1000 范围坐标映射为绝对屏幕坐标。"""
        x, y = position

        if target_screen:
            screen_width = target_screen["width"]
            screen_height = target_screen["height"]
            screen_offset_x = target_screen["x"]
            screen_offset_y = target_screen["y"]
        else:
            screen_width, screen_height = self._platform_adapter.get_logical_screen_size()
            screen_offset_x = 0
            screen_offset_y = 0

        mapped_x, mapped_y = self._coordinate_mapper.map_to_screen(
            x,
            y,
            screen_width,
            screen_height,
        )
        return [mapped_x + screen_offset_x, mapped_y + screen_offset_y]

    def _move_to_position(
        self,
        position: Union[List, Tuple],
        duration: float,
        target_screen: Optional[Dict[str, Any]] = None,
        label: str = "坐标",
    ) -> Tuple[List[float], str]:
        """移动光标到目标位置，并返回映射后的绝对坐标。"""
        mapped_coordinates = self._map_position_to_absolute(position, target_screen)
        x, y = mapped_coordinates
        self._move_cursor_smooth(x, y, duration)
        print(f"鼠标已移动到{label}: ({x}, {y})")
        return mapped_coordinates, f"鼠标已移动到{label}\n"

    def _handle_drag(
        self,
        coordinates: List,
        duration: float,
        target_screen: Optional[Dict[str, Any]] = None,
        end_screen: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List, str]:
        """处理拖拽操作（支持跨屏幕）"""
        start_x, start_y = coordinates[0]
        end_x, end_y = coordinates[1]

        start_coordinates, action_str = self._move_to_position(
            [start_x, start_y],
            duration,
            target_screen=target_screen,
            label="拖拽起点",
        )
        end_coordinates = self._map_position_to_absolute(
            [end_x, end_y],
            target_screen=end_screen,
        )
        start_x, start_y = start_coordinates
        end_x, end_y = end_coordinates

        self._platform_adapter.drag_to(
            end_x,
            end_y,
            duration=max(self._get_smooth_move_duration(duration) * 4, 0.6),
            button="left",
        )

        print(f"已完成拖拽操作: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
        action_str += "已完成拖拽操作\n"

        return [[start_x, start_y], [end_x, end_y]], action_str

    def _handle_single_point(
        self,
        coordinates: Union[List, Tuple],
        action: str,
        duration: float,
        target_screen: Optional[Dict[str, Any]] = None,
        scroll_amount: Optional[int] = None,
        long_press_duration_seconds: Optional[float] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Tuple[List, str]:
        """处理单点操作"""
        mapped_coordinates, action_str = self._move_to_position(
            coordinates,
            duration,
            target_screen=target_screen,
            label="坐标",
        )
        x, y = mapped_coordinates

        resolved_scroll_amount = (
            int(scroll_amount) if scroll_amount is not None else self._resolve_scroll_amount()
        )

        def perform_long_press() -> Tuple[None, str]:
            hold_seconds = float(long_press_duration_seconds or 3.0)
            self._platform_adapter.mouse_down(button="left")
            try:
                completed = self._sleep_interruptibly(hold_seconds, should_stop=should_stop)
            finally:
                self._platform_adapter.mouse_up(button="left")
            if not completed:
                raise RuntimeError("长按已中断")
            return None, f"已长按 {hold_seconds:g} 秒"

        action_handlers = {
            "click": lambda: (self._platform_adapter.click(button="left"), "已点击"),
            "double_click": lambda: (
                self._platform_adapter.click(button="left", clicks=2),
                "已双击",
            ),
            "long_press": perform_long_press,
            "right_click": lambda: (self._platform_adapter.click(button="right"), "已右键点击"),
            "scroll_up": lambda: (
                self._platform_adapter.scroll(resolved_scroll_amount),
                f"已向上滚动 {resolved_scroll_amount}",
            ),
            "scroll_down": lambda: (
                self._platform_adapter.scroll(-resolved_scroll_amount),
                f"已向下滚动 {resolved_scroll_amount}",
            ),
        }

        if action in action_handlers:
            handler_result, action_msg = action_handlers[action]()
            print(f"{action_msg} ({x}, {y})")
            action_str += f"{action_msg}\n"
        else:
            print(f"未知操作: {action}")

        return [x, y], action_str

    def _backup_clipboard_text(self) -> Tuple[bool, str]:
        """备份当前文本剪贴板内容。"""
        try:
            previous = automation_exports().pyperclip.paste()
            if previous is None:
                previous = ""
            elif not isinstance(previous, str):
                previous = str(previous)
            return True, previous
        except Exception as exc:
            print(f"读取剪贴板失败，将在输入后跳过恢复: {exc}")
            return False, ""

    def _restore_clipboard_text(self, has_backup: bool, previous_text: str) -> None:
        """恢复之前备份的文本剪贴板内容。"""
        if not has_backup:
            return
        try:
            automation_exports().pyperclip.copy(previous_text)
        except Exception as exc:
            print(f"恢复剪贴板失败: {exc}")

    def _handle_type_input(
        self,
        type_information: str,
        coordinates: Optional[Union[List, Tuple]],
        *,
        replace: bool = False,
        submit: bool = False,
    ) -> str:
        """处理文本输入"""
        has_backup, previous_clipboard = self._backup_clipboard_text()
        try:
            automation_exports().pyperclip.copy(type_information)
            automation_exports().time.sleep(0.1)

            if coordinates:
                x, y = coordinates[0] if isinstance(coordinates[0], list) else coordinates
                self._platform_adapter.click(button="left")
                print(f"已点击 ({x}, {y})")

                if replace:
                    if self._current_os == "Darwin":
                        automation_exports().time.sleep(0.1)
                        self._platform_adapter.key_down("command")
                        automation_exports().time.sleep(0.1)
                        self._platform_adapter.key_press("a")
                        automation_exports().time.sleep(0.1)
                        self._platform_adapter.key_up("command")
                    else:
                        automation_exports().pyautogui.hotkey("ctrl", "a")

            if self._current_os == "Darwin":
                automation_exports().time.sleep(0.1)
                self._platform_adapter.key_down("command")
                automation_exports().time.sleep(0.1)
                self._platform_adapter.key_press("v")
                automation_exports().time.sleep(0.1)
                self._platform_adapter.key_up("command")
            else:
                automation_exports().pyautogui.hotkey("ctrl", "v")

            print(f"已粘贴: {type_information}")
            automation_exports().time.sleep(0.2)

            if submit:
                self._platform_adapter.key_press("enter")
                automation_exports().time.sleep(0.3)
                print("已提交")
                return f"已提交: {type_information}\n"

            print("已输入（未按回车）")
            return f"已输入: {type_information}\n"
        finally:
            self._restore_clipboard_text(has_backup, previous_clipboard)

    def click(self, x: float, y: float, duration: float = 0.1) -> None:
        """点击指定坐标"""
        self._move_cursor_smooth(x, y, duration)
        self._platform_adapter.click(button="left")

    def double_click(self, x: float, y: float, duration: float = 0.1) -> None:
        """双击指定坐标"""
        self._move_cursor_smooth(x, y, duration)
        self._platform_adapter.click(button="left", clicks=2)

    def right_click(self, x: float, y: float, duration: float = 0.1) -> None:
        """右键点击指定坐标"""
        self._move_cursor_smooth(x, y, duration)
        self._platform_adapter.click(button="right")

    def drag(
        self, start_x: float, start_y: float, end_x: float, end_y: float, duration: float = 0.1
    ) -> None:
        """从起点拖拽到终点"""
        self._move_cursor_smooth(start_x, start_y, duration)
        self._platform_adapter.drag_to(
            end_x,
            end_y,
            duration=max(self._get_smooth_move_duration(duration) * 4, 0.6),
            button="left",
        )

    def type_text(self, text: str) -> None:
        """输入文本"""
        has_backup, previous_clipboard = self._backup_clipboard_text()
        try:
            automation_exports().pyperclip.copy(text)
            if self._current_os == "Darwin":
                self._platform_adapter.key_down("command")
                self._platform_adapter.key_press("v")
                self._platform_adapter.key_up("command")
            else:
                automation_exports().pyautogui.hotkey("ctrl", "v")
        finally:
            self._restore_clipboard_text(has_backup, previous_clipboard)

    def hotkey(self, *keys: str) -> None:
        """执行快捷键"""
        keys = self._platform_adapter.translate_hotkey_keys(list(keys))
        if not keys:
            return

        modifier_keys = {"command", "control", "ctrl", "shift", "option", "alt", "win"}
        held_modifiers: List[str] = []
        try:
            for key in keys[:-1]:
                if key in modifier_keys:
                    self._platform_adapter.key_down(key)
                    held_modifiers.append(key)
                else:
                    self._platform_adapter.key_press(key)
            self._platform_adapter.key_press(keys[-1])
        finally:
            for key in reversed(held_modifiers):
                self._platform_adapter.key_up(key)

    def scroll(self, amount: int, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """滚动滚轮"""
        if x is not None and y is not None:
            self._move_cursor_smooth(x, y, self._config.mouse_config.get("move_duration", 0.1))
        self._platform_adapter.scroll(amount)
