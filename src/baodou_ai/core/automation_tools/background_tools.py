"""Memory and background code-agent automation tools."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from baodou_ai.core.error_envelope import (
    CODE_CODE_AGENT_FAILED,
    CODE_TOOL_EXEC_FAILED,
    KIND_EXECUTION_FAILED,
    KIND_VALIDATION_FAILED,
    SOURCE_CODE_AGENT,
    SOURCE_TOOL,
    from_exception,
    from_message,
)
from baodou_ai.core.task_memory_store import TaskMemoryStore

from .constants import automation_exports


class BackgroundToolsMixin:
    def tool_remember(
        self,
        content: str,
        screen_info: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        try:
            self.handle_remember(content, 0, screen_info)
            return self._build_tool_result(True, "已记录重要信息", None)
        except Exception as exc:
            envelope = from_exception(
                exc,
                source=SOURCE_TOOL,
                kind=KIND_EXECUTION_FAILED,
                user_message="记录重要信息失败",
                code=CODE_TOOL_EXEC_FAILED,
                retryable=True,
            )
            return envelope.to_tool_result("记录重要信息失败", ok=False, error=str(exc))

    def tool_code_agent(
        self,
        task: str,
        title: Optional[str] = None,
        goal: Optional[str] = None,
        job_id: Optional[str] = None,
        workspace_path: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        del screen_info
        try:
            if should_stop is not None and should_stop():
                envelope = from_message(
                    source=SOURCE_CODE_AGENT,
                    kind=KIND_VALIDATION_FAILED,
                    user_message="后台代码任务未启动",
                    dev_detail="当前任务已被用户中断",
                    code=CODE_CODE_AGENT_FAILED,
                    retryable=True,
                )
                return envelope.to_tool_result("后台代码任务未启动", ok=False, error="当前任务已被用户中断")
            if self._job_manager is None:
                envelope = from_message(
                    source=SOURCE_CODE_AGENT,
                    kind=KIND_VALIDATION_FAILED,
                    user_message="后台代码任务未启动",
                    dev_detail="JobManager 未初始化",
                    code=CODE_CODE_AGENT_FAILED,
                    retryable=False,
                )
                return envelope.to_tool_result("后台代码任务未启动", ok=False, error="JobManager 未初始化")

            job = self._job_manager.submit(
                task=task,
                title=title,
                goal=goal,
                job_id=job_id,
                workspace_path=workspace_path,
                timeout_seconds=timeout_seconds,
            )
            launch_summary = (
                f"后台代码任务已启动（{job['job_id']}，provider={job['provider']}，status={job['status']}）"
            )
            return self._build_tool_result(
                True,
                launch_summary,
                None,
                job_id=job["job_id"],
                job_status=job["status"],
                provider=job["provider"],
                launch_report="我已经在后台启动代码任务，你可以继续使用电脑。我完成后会向你汇报结果。",
            )
        except Exception as exc:
            envelope = from_exception(
                exc,
                source=SOURCE_CODE_AGENT,
                kind=KIND_EXECUTION_FAILED,
                user_message="后台代码任务未启动",
                code=CODE_CODE_AGENT_FAILED,
                retryable=True,
            )
            return envelope.to_tool_result("后台代码任务未启动", ok=False, error=str(exc))

    def tool_stop_code_agent(
        self,
        job_id: str,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        del screen_info
        try:
            if should_stop is not None and should_stop():
                envelope = from_message(
                    source=SOURCE_CODE_AGENT,
                    kind=KIND_VALIDATION_FAILED,
                    user_message="后台代码任务未停止",
                    dev_detail="当前任务已被用户中断",
                    code=CODE_CODE_AGENT_FAILED,
                    retryable=True,
                )
                return envelope.to_tool_result("后台代码任务未停止", ok=False, error="当前任务已被用户中断")
            if self._job_manager is None:
                envelope = from_message(
                    source=SOURCE_CODE_AGENT,
                    kind=KIND_VALIDATION_FAILED,
                    user_message="后台代码任务未停止",
                    dev_detail="JobManager 未初始化",
                    code=CODE_CODE_AGENT_FAILED,
                    retryable=False,
                )
                return envelope.to_tool_result("后台代码任务未停止", ok=False, error="JobManager 未初始化")

            snapshot = self._job_manager.get_job(job_id)
            if snapshot is None:
                envelope = from_message(
                    source=SOURCE_CODE_AGENT,
                    kind=KIND_VALIDATION_FAILED,
                    user_message="后台代码任务未停止",
                    dev_detail=f"未找到后台任务: {job_id}",
                    code=CODE_CODE_AGENT_FAILED,
                    retryable=False,
                )
                return envelope.to_tool_result("后台代码任务未停止", ok=False, error=f"未找到后台任务: {job_id}")
            if snapshot.get("dismissed"):
                envelope = from_message(
                    source=SOURCE_CODE_AGENT,
                    kind=KIND_VALIDATION_FAILED,
                    user_message="后台代码任务未停止",
                    dev_detail="该后台任务已从当前会话移除",
                    code=CODE_CODE_AGENT_FAILED,
                    retryable=False,
                )
                return envelope.to_tool_result("后台代码任务未停止", ok=False, error="该后台任务已从当前会话移除")
            if snapshot.get("status") != "running":
                envelope = from_message(
                    source=SOURCE_CODE_AGENT,
                    kind=KIND_VALIDATION_FAILED,
                    user_message="后台代码任务未停止",
                    dev_detail="该后台代码任务当前未在运行中",
                    code=CODE_CODE_AGENT_FAILED,
                    retryable=True,
                )
                return envelope.to_tool_result("后台代码任务未停止", ok=False, error="该后台代码任务当前未在运行中")

            job = self._job_manager.cancel(job_id)
            stop_summary = (
                f"后台代码任务已停止（{job['job_id']}，provider={job['provider']}，status={job['status']}）"
            )
            title = str(job.get("title") or job_id).strip()
            return self._build_tool_result(
                True,
                stop_summary,
                None,
                job_id=job["job_id"],
                job_status=job["status"],
                provider=job["provider"],
                stop_report=f"后台代码任务“{title}”已停止。",
            )
        except Exception as exc:
            envelope = from_exception(
                exc,
                source=SOURCE_CODE_AGENT,
                kind=KIND_EXECUTION_FAILED,
                user_message="后台代码任务未停止",
                code=CODE_CODE_AGENT_FAILED,
                retryable=True,
            )
            return envelope.to_tool_result("后台代码任务未停止", ok=False, error=str(exc))
    
    def handle_remember(
        self,
        type_information: str,
        screen_index: int = 0,
        screen_info: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[str, None]:
        """
        处理记忆重要信息操作
        
        Args:
            type_information: 要记忆的重要信息
            screen_index: 目标屏幕索引
            screen_info: 所有屏幕信息列表
        
        Returns:
            Tuple[str, None]: (操作描述, None)
        """
        try:
            memory_store = TaskMemoryStore(memory_file=automation_exports().MEMORY_FILE)
            memory_store.append(type_information)
            
            print(f"已记录重要信息: {type_information}")
            
            return f"已记忆重要信息: {type_information}\n", None
            
        except Exception as e:
            print(f"记忆操作失败: {e}")
            return f"记忆操作失败: {e}\n", None
