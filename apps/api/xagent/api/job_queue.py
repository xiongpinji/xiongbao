"""轻量异步任务队列：后台 Job 执行 + 状态追踪。

功能：
- 提交后台任务（不阻塞请求）
- 任务状态追踪（pending → running → done/failed）
- 并发控制（最大并行数）
- 结果缓存 + 过期清理

用法：
    from xagent.api.job_queue import get_job_queue
    queue = get_job_queue()
    job_id = await queue.submit(my_async_task, arg1, arg2)
    status = queue.get_status(job_id)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.jobs")


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """任务实例。"""

    id: str
    name: str
    status: JobStatus = JobStatus.PENDING
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def duration_s(self) -> float | None:
        if self.started_at and self.finished_at:
            return round(self.finished_at - self.started_at, 3)
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": self.duration_s,
        }


class JobQueue:
    """异步任务队列。"""

    def __init__(self, max_concurrency: int = 5, max_history: int = 200):
        self.max_concurrency = max_concurrency
        self.max_history = max_history
        self._jobs: dict[str, Job] = {}
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._running_count = 0

    async def submit(
        self,
        fn: Callable[..., Coroutine],
        *args: Any,
        name: str | None = None,
        **kwargs: Any,
    ) -> str:
        """提交任务，返回 job_id。"""
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, name=name or fn.__name__)
        self._jobs[job_id] = job

        # 启动后台执行
        asyncio.create_task(self._run(job, fn, args, kwargs))

        logger.info("job_submitted", job_id=job_id, name=job.name)
        return job_id

    async def _run(self, job: Job, fn: Callable, args: tuple, kwargs: dict):
        """执行任务（受信号量控制）。"""
        async with self._semaphore:
            job.status = JobStatus.RUNNING
            job.started_at = time.time()
            self._running_count += 1

            try:
                result = await fn(*args, **kwargs)
                job.status = JobStatus.DONE
                job.result = result
                logger.info("job_done", job_id=job.id, duration=job.duration_s)
            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
                logger.warning("job_cancelled", job_id=job.id)
            except Exception as e:
                job.status = JobStatus.FAILED
                job.error = str(e)[:500]
                logger.error("job_failed", job_id=job.id, error=str(e)[:200])
            finally:
                job.finished_at = time.time()
                self._running_count -= 1
                self._cleanup()

    def _cleanup(self):
        """清理过期任务（保留最近 N 条）。"""
        if len(self._jobs) <= self.max_history:
            return
        finished = [
            j for j in self._jobs.values()
            if j.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)
        ]
        finished.sort(key=lambda j: j.finished_at or 0)
        for j in finished[: len(self._jobs) - self.max_history]:
            del self._jobs[j.id]

    def get_status(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 50) -> list[dict]:
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in jobs[:limit]]

    @property
    def stats(self) -> dict:
        statuses = [j.status for j in self._jobs.values()]
        return {
            "total": len(self._jobs),
            "running": self._running_count,
            "pending": statuses.count(JobStatus.PENDING),
            "done": statuses.count(JobStatus.DONE),
            "failed": statuses.count(JobStatus.FAILED),
            "max_concurrency": self.max_concurrency,
        }


# 单例
_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = JobQueue()
    return _queue
