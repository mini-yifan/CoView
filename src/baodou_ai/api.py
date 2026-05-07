"""
包豆电脑 API 模块

提供无 GUI 的自动化操作接口，可以被其他项目直接调用使用。
"""

from typing import Any, Callable, Optional

from baodou_ai.core.config import Config
from baodou_ai.core.runner import ControlLoopRunner
from baodou_ai.platform import cancel_current_mouse_motion


class BaodouAI:
    """包豆电脑 AI 自动化控制器

    提供无 GUI 的 API 接口，可以被其他项目直接调用。

    Example:
        >>> from baodou_ai import BaodouAI
        >>> ai = BaodouAI(api_key="your_api_key")
        >>> result = ai.execute("打开浏览器")
        >>> print(result)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        config: Optional[Config] = None,
    ):
        """初始化 BaodouAI

        Args:
            api_key: API 密钥，如果提供会覆盖配置文件中的值
            base_url: API 基础地址，如果提供会覆盖配置文件中的值
            model_name: 模型名称，如果提供会覆盖配置文件中的值
            config: 配置对象，如果不提供会自动加载默认配置
        """
        self._config = config or Config()

        if api_key:
            self._config.api_key = api_key
        if base_url:
            self._config.set("api_config.base_url", base_url)
        if model_name:
            self._config.set("api_config.model_name", model_name)

        self._should_stop = False

    def get_model_name(self) -> str:
        """获取当前使用的模型名称"""
        return self._config.api_config.get("model_name", "unknown")

    def execute(
        self,
        task: str,
        max_iterations: Optional[int] = None,
        on_iteration: Optional[Callable[[int, dict], Any]] = None,
        on_model_stream: Optional[Callable[[int, str], Any]] = None,
        on_transparent_enter: Optional[Callable[[], Any]] = None,
        on_transparent_exit: Optional[Callable[[], Any]] = None,
    ) -> str:
        """执行自动化任务

        Args:
            task: 用户任务描述
            max_iterations: 最大迭代次数，如果不提供使用配置中的默认值
            on_iteration: 每次迭代完成后的回调函数，接收迭代索引和操作信息
            on_model_stream: 模型流式输出回调，接收迭代索引和文本增量
            on_transparent_enter: 进入透明模式的回调函数
            on_transparent_exit: 退出透明模式的回调函数

        Returns:
            AI 思考结果或完成信息
        """
        self._should_stop = False

        user_content = ControlLoopRunner.build_user_content(task)
        print(f"=============用户输入内容为:{user_content}")

        runner = ControlLoopRunner(self._config)
        return runner.run(
            user_content=user_content,
            max_iterations=max_iterations,
            on_iteration=on_iteration,
            on_model_stream=on_model_stream,
            on_transparent_enter=on_transparent_enter,
            on_transparent_exit=on_transparent_exit,
            should_stop=lambda: self._should_stop,
        )

    def stop(self) -> None:
        """停止当前执行的任务"""
        self._should_stop = True
        cancel_current_mouse_motion()


def execute_task(
    task: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
    max_iterations: Optional[int] = None,
) -> str:
    """快速执行任务的便捷函数

    Args:
        task: 用户任务描述
        api_key: API 密钥
        base_url: API 基础地址
        model_name: 模型名称
        max_iterations: 最大迭代次数

    Returns:
        AI 思考结果或完成信息

    Example:
        >>> from baodou_ai import execute_task
        >>> result = execute_task("打开记事本", api_key="your_key")
    """
    ai = BaodouAI(api_key=api_key, base_url=base_url, model_name=model_name)
    return ai.execute(task, max_iterations=max_iterations)
