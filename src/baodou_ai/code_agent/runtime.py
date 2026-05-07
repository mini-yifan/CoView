"""后台任务运行器。"""

from __future__ import annotations

import threading
from typing import Callable

from baodou_ai.core.error_envelope import (
    CODE_CODE_AGENT_FAILED,
    KIND_EXECUTION_FAILED,
    SOURCE_CODE_AGENT,
    from_exception,
)
from .dispatcher import CodeAgentDispatcher
from .models import BackgroundJobResult, CodeAgentRequest


class BackgroundJobWorker:
    """单个后台 Code Agent 任务的线程运行器。"""

    def __init__(
        self,
        request: CodeAgentRequest,
        dispatcher: CodeAgentDispatcher,
        on_complete: Callable[[BackgroundJobResult], None],
        on_log: Callable[[str], None],
        on_pid: Callable[[int], None],
    ) -> None:
        self._request = request
        self._dispatcher = dispatcher
        self._on_complete = on_complete
        self._on_log = on_log
        self._on_pid = on_pid
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"code-agent-{request.job_id}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def cancel(self) -> None:
        self._stop_event.set()

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout=timeout)

    def _should_stop(self) -> bool:
        return self._stop_event.is_set()

    def _run(self) -> None:
        try:
            result = self._dispatcher.run(
                request=self._request,
                on_log=self._on_log,
                on_pid=self._on_pid,
                should_stop=self._should_stop,
            )
        except Exception as exc:  # pragma: no cover - 兜底防止后台线程失联
            envelope = from_exception(
                exc,
                source=SOURCE_CODE_AGENT,
                kind=KIND_EXECUTION_FAILED,
                user_message="后台代码任务执行异常",
                code=CODE_CODE_AGENT_FAILED,
                retryable=True,
            )
            result = BackgroundJobResult(
                ok=False,
                summary="后台代码任务执行异常",
                provider=self._request.provider,
                error=str(exc),
                error_envelope=envelope.to_dict(),
            )
        self._on_complete(result)
