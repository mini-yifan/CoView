"""
平台适配器基类

定义平台适配器的接口规范。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class UnsupportedPlatformError(RuntimeError):
    """Raised when the current operating system has no supported adapter."""


class PlatformAdapter(ABC):
    """平台适配器基类"""
    
    @abstractmethod
    def get_resource_path(self, relative_path: str) -> Optional[str]:
        """
        获取资源文件路径
        
        Args:
            relative_path: 相对路径
        
        Returns:
            绝对路径，如果不存在返回None
        """
        pass
    
    @abstractmethod
    def setup_window(self, window) -> None:
        """
        设置窗口属性
        
        Args:
            window: 窗口对象
        """
        pass

    def prepare_overlay_window(self, window) -> None:
        """为悬浮主 UI 的顶层浮窗补充平台原生初始化。"""
        self.setup_window(window)

    def refresh_overlay_window(self, window) -> None:
        """在几何或透明度变化后刷新悬浮浮窗的原生状态。"""
        self.setup_window(window)

    def apply_overlay_region(self, window, kind: str, radius_or_bounds=None) -> bool:
        """应用平台原生裁剪区域。默认实现为 no-op。"""
        return False

    def clear_overlay_region(self, window) -> bool:
        """清除平台原生裁剪区域。默认实现为 no-op。"""
        return False
    
    @abstractmethod
    def prevent_screenshot(self, window) -> bool:
        """
        防止窗口被截图
        
        Args:
            window: 窗口对象
        
        Returns:
            是否设置成功
        """
        pass
    
    @abstractmethod
    def allow_screenshot(self, window) -> bool:
        """
        允许窗口被截图
        
        Args:
            window: 窗口对象
        
        Returns:
            是否设置成功
        """
        pass
    
    @abstractmethod
    def translate_hotkey_keys(self, keys: List[str]) -> List[str]:
        """
        翻译快捷键
        
        Args:
            keys: 快捷键列表
        
        Returns:
            翻译后的快捷键列表
        """
        pass
    
    @abstractmethod
    def get_hotkey_modifier(self) -> str:
        """
        获取快捷键修饰符
        
        Returns:
            修饰键名称 (ctrl/command/win)
        """
        pass
    
    @abstractmethod
    def is_app_bundle(self) -> bool:
        """
        检测是否在打包的应用程序中运行
        
        Returns:
            是否在打包的应用程序中
        """
        pass
    
    @abstractmethod
    def enter_transparent_mode(self, window) -> bool:
        """
        进入透明穿透模式
        
        窗口变为完全透明且鼠标可穿透，用于执行自动化操作时
        不干扰用户对其他软件的操作。
        
        Args:
            window: 窗口对象
        
        Returns:
            是否设置成功
        """
        pass
    
    @abstractmethod
    def exit_transparent_mode(self, window) -> bool:
        """
        退出透明穿透模式

        窗口恢复不透明且鼠标不可穿透，恢复正常的窗口交互。
        此操作不会抢占焦点。
        
        Args:
            window: 窗口对象
        
        Returns:
            是否设置成功
        """
        pass
    
    @abstractmethod
    def get_scaling_factor(self) -> float:
        """
        获取屏幕缩放因子（DPI缩放/Retina缩放）

        在 macOS Retina 屏幕上，物理分辨率是逻辑分辨率的 2 倍。
        在 Windows 高 DPI 屏幕上，可能有不同的缩放比例。

        Returns:
            缩放因子，例如 Retina 屏幕返回 2.0，普通屏幕返回 1.0
        """
        pass
    
    @abstractmethod
    def get_logical_screen_size(self) -> tuple:
        """
        获取逻辑屏幕尺寸

        逻辑尺寸是 pyautogui 鼠标操作使用的坐标系统。

        Returns:
            (width, height) 逻辑屏幕尺寸
        """
        pass
    
    @abstractmethod
    def get_screen_count(self) -> int:
        """
        获取屏幕数量
        
        Returns:
            屏幕数量
        """
        pass
    
    @abstractmethod
    def get_all_screens_info(self) -> List[Dict[str, Any]]:
        """
        获取所有屏幕信息
        
        Returns:
            屏幕信息列表，每个元素包含:
            - index: 屏幕索引
            - x: 屏幕左上角X坐标（虚拟桌面坐标系）
            - y: 屏幕左上角Y坐标（虚拟桌面坐标系）
            - width: 逻辑宽度
            - height: 逻辑高度
            - is_primary: 是否为主屏幕
        """
        pass

    @abstractmethod
    def get_capture_screens_info(self) -> List[Dict[str, Any]]:
        """
        获取用于截图的屏幕信息

        Returns:
            屏幕信息列表，每个元素包含:
            - index
            - is_primary
            - logical_x
            - logical_y
            - logical_width
            - logical_height
            - capture_x
            - capture_y
            - capture_width
            - capture_height
        """
        pass
    
    @abstractmethod
    def get_screen_rect(self, screen_index: int) -> Tuple[int, int, int, int]:
        """
        获取指定屏幕的矩形区域
        
        Args:
            screen_index: 屏幕索引
        
        Returns:
            (x, y, width, height) 屏幕在虚拟桌面中的位置和尺寸
        """
        pass

    @abstractmethod
    def move_cursor(self, x: float, y: float, duration: float = 0.0) -> None:
        """
        移动鼠标到指定全局坐标

        Args:
            x: 全局X坐标
            y: 全局Y坐标
            duration: 移动时长
        """
        pass

    @abstractmethod
    def click(self, button: str = "left", clicks: int = 1) -> None:
        """
        在当前鼠标位置执行点击

        Args:
            button: 鼠标按键名称
            clicks: 点击次数
        """
        pass

    @abstractmethod
    def mouse_down(self, button: str = "left") -> None:
        """
        按下鼠标按键

        Args:
            button: 鼠标按键名称
        """
        pass

    @abstractmethod
    def mouse_up(self, button: str = "left") -> None:
        """
        释放鼠标按键

        Args:
            button: 鼠标按键名称
        """
        pass

    @abstractmethod
    def drag_to(self, x: float, y: float, duration: float = 0.0, button: str = "left") -> None:
        """
        从当前位置拖拽到指定全局坐标

        Args:
            x: 目标全局X坐标
            y: 目标全局Y坐标
            duration: 拖拽时长
            button: 鼠标按键名称
        """
        pass

    @abstractmethod
    def scroll(self, amount: int) -> None:
        """
        在当前鼠标位置执行滚轮操作

        Args:
            amount: 滚动量
        """
        pass

    @abstractmethod
    def key_down(self, key: str) -> None:
        """
        按下键盘按键。

        Args:
            key: 按键名称
        """
        pass

    @abstractmethod
    def key_up(self, key: str) -> None:
        """
        释放键盘按键。

        Args:
            key: 按键名称
        """
        pass

    @abstractmethod
    def launch_app(self, app_name: str) -> Dict[str, Any]:
        """
        按名称启动或激活应用。

        Args:
            app_name: 目标应用名称

        Returns:
            最小结果对象，至少包含:
            - matched: 是否找到可启动应用
            - app_name: 命中的应用名称
            - suggestions: 高置信度候选名称列表
            - fallback: 可选兜底指引，例如 spotlight_search
        """
        pass

    @abstractmethod
    def open_app_launcher(self) -> Dict[str, Any]:
        """
        打开应用启动器并返回当前电脑上的应用名称列表。

        Returns:
            最小结果对象，至少包含:
            - app_names: 当前电脑上扫描到的应用名称列表
        """
        pass

    @abstractmethod
    def open_in_finder(self, path: Optional[str] = None) -> Dict[str, Any]:
        """
        打开访达并显示指定目录。

        传入文件夹路径时直接打开该文件夹；传入文件路径时打开该文件所在的文件夹并选中该文件；
        不传路径时默认打开桌面目录。

        macOS 上应以前台访达显示目录；
        Windows 上应以前台文件资源管理器显示目录。

        Args:
            path: 可选的文件夹或文件路径。不传时默认打开桌面。

        Returns:
            最小结果对象，至少包含:
            - target_path: 实际打开的目录路径
            - revealed_file: 如果传入的是文件路径，该文件的路径；否则为 None
        """
        pass

    @abstractmethod
    def get_active_document_path(self, app_name: str) -> Optional[str]:
        """
        获取当前前台文档应用中活跃文档的绝对路径。

        仅当 app_name 属于支持的文档应用或文件管理器时才执行查询；
        不支持的应用直接返回 None。

        Args:
            app_name: 前台应用名称，如 "Microsoft Word"。

        Returns:
            文档或当前目录的绝对路径；文档未保存或当前文件管理器不在文件系统目录时返回空字符串 ""；
            不支持的应用或查询失败时返回 None。
        """
        pass

    @abstractmethod
    def move_to_trash(self, path: str) -> Dict[str, Any]:
        """
        将文件或文件夹移动到废纸篓。

        Args:
            path: 文件或文件夹的 POSIX 绝对路径。

        Returns:
            最小结果对象，至少包含:
            - ok: 是否成功
            - error: 失败时的错误信息（成功时为 None）
        """
        pass

    @abstractmethod
    def get_default_browser_info(self) -> Dict[str, Any]:
        """
        获取当前系统默认浏览器信息。

        Returns:
            最小结果对象，至少包含:
            - app_name: 浏览器显示名称
            - identifier: 稳定标识（bundle id / prog id / executable）
            - is_chrome_family: 是否属于 Chrome 系列
        """
        pass

    @abstractmethod
    def open_in_browser(self, url: Optional[str] = None, query: Optional[str] = None) -> Dict[str, Any]:
        """
        使用系统默认浏览器打开网址或搜索文本。

        Args:
            url: 直接打开的网址
            query: 需要搜索的文本

        Returns:
            最小结果对象，至少包含:
            - browser: 默认浏览器信息
            - target_url: 实际打开的目标 URL
        """
        pass

    @abstractmethod
    def get_frontmost_app_info(self) -> Dict[str, Any]:
        """
        获取当前前台应用信息。

        Returns:
            最小结果对象，至少包含:
            - app_name: 应用显示名称
            - bundle_id / identifier: 稳定标识
            - pid: 进程 ID
        """
        pass

    def get_frontmost_window_info(self) -> Dict[str, Any]:
        """
        获取当前前台窗口信息（用于伴随推荐等轻量场景）。

        默认实现为 no-op，返回空字典；平台适配器可按需覆盖。

        Returns:
            最小结果对象，建议包含:
            - pid: 进程 ID
            - app_name: 应用显示名称（可选）
            - bundle_id / identifier: 稳定标识（可选）
            - title: 前台窗口标题（可选）
            - bounds: {x, y, width, height}（可选，逻辑屏幕坐标）
        """
        return {}

    @abstractmethod
    def activate_app(self, app_info: Dict[str, Any]) -> bool:
        """
        将指定应用激活到前台。

        Args:
            app_info: 前台应用信息对象

        Returns:
            是否成功激活
        """
        pass
