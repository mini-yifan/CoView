"""后台任务轻量内存存储。"""

from __future__ import annotations

from typing import Dict, Iterable, Optional

from .models import BackgroundJob


class InMemoryJobStore:
    """V1 使用内存保存后台任务状态。"""

    def __init__(self) -> None:
        self._jobs: Dict[str, BackgroundJob] = {}

    def put(self, job: BackgroundJob) -> None:
        self._jobs[job.job_id] = job

    def get(self, job_id: str) -> Optional[BackgroundJob]:
        return self._jobs.get(job_id)

    def values(self) -> Iterable[BackgroundJob]:
        return self._jobs.values()
