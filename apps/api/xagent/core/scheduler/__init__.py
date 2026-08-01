"""定时自动化调度器。

对标 Codex Automations / Hermes cron scheduler：
- 内置 asyncio 后台调度（无需外部 cron）
- 支持自然语言定义调度规则
- 到时间自动触发 Agent 运行
- 持久化到文件，重启不丢失
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.scheduler")

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


@dataclass
class ScheduledJob:
    job_id: str
    name: str
    goal: str  # 要执行的 Agent 目标
    role: str | None = None
    cron_expr: str = ""  # cron 表达式 (min hour dom mon dow)
    interval_seconds: int = 0  # 或用固定间隔
    enabled: bool = True
    last_run: float = 0
    next_run: float = 0
    run_count: int = 0
    last_result: str = ""
    created_at: float = field(default_factory=time.time)
    tenant_id: str = ""
    owner_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_cron_interval(cron_expr: str) -> int:
    """简化 cron 解析：提取间隔秒数。支持 '* * * * *' 格式。"""
    parts = cron_expr.strip().split()
    if len(parts) < 2:
        return 3600  # 默认每小时
    minute, hour = parts[0], parts[1]
    if minute.startswith("*/"):
        return int(minute[2:]) * 60
    if hour == "*" and minute != "*":
        return 3600  # 每小时的第 N 分钟
    if hour.startswith("*/"):
        return int(hour[2:]) * 3600
    return 86400  # 默认每天


class Scheduler:
    """asyncio 后台调度器。"""

    def __init__(self, storage_dir: Path | None = None) -> None:
        base = storage_dir or _PROJECT_ROOT / "data" / "scheduler"
        self._dir = base
        self._dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, ScheduledJob] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        self._load_all()

    def _load_all(self) -> None:
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                job = ScheduledJob(**data)
                self._jobs[job.job_id] = job
            except Exception:
                continue
        logger.info("scheduler_loaded", jobs=len(self._jobs))

    def _persist(self, job: ScheduledJob) -> None:
        path = self._dir / f"{job.job_id}.json"
        path.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def add_job(
        self,
        name: str,
        goal: str,
        *,
        role: str | None = None,
        cron_expr: str = "",
        interval_seconds: int = 0,
        tenant_id: str = "",
        owner_id: str = "",
    ) -> ScheduledJob:
        """添加定时任务。"""
        interval = interval_seconds or (_parse_cron_interval(cron_expr) if cron_expr else 3600)
        job = ScheduledJob(
            job_id=uuid.uuid4().hex[:12],
            name=name,
            goal=goal,
            role=role,
            cron_expr=cron_expr,
            interval_seconds=interval,
            next_run=time.time() + interval,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        self._jobs[job.job_id] = job
        self._persist(job)
        logger.info("job_added", job_id=job.job_id, name=name, interval=interval)
        return job

    def remove_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            (self._dir / f"{job_id}.json").unlink(missing_ok=True)
            return True
        return False

    def toggle_job(self, job_id: str, enabled: bool) -> ScheduledJob | None:
        job = self._jobs.get(job_id)
        if job:
            job.enabled = enabled
            self._persist(job)
        return job

    def list_jobs(self) -> list[ScheduledJob]:
        return sorted(self._jobs.values(), key=lambda j: j.next_run)

    def get_job(self, job_id: str) -> ScheduledJob | None:
        return self._jobs.get(job_id)

    async def start(self) -> None:
        """启动后台调度循环。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("scheduler_started", jobs=len(self._jobs))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        """主调度循环：每 30s 检查一次到期任务。启动后延迟 60s 再执行。"""
        await asyncio.sleep(60)  # 避免启动时与主应用竞争资源
        while self._running:
            try:
                now = time.time()
                for job in list(self._jobs.values()):
                    if not job.enabled or job.next_run > now:
                        continue
                    # 触发执行
                    await self._execute_job(job)
                    # 更新下次运行时间
                    job.last_run = now
                    job.next_run = now + job.interval_seconds
                    job.run_count += 1
                    self._persist(job)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("scheduler_loop_error", error=str(exc))
            await asyncio.sleep(30)

    async def _execute_job(self, job: ScheduledJob) -> None:
        """执行单个定时任务（隔离在线程池中，避免破坏主事件循环）。"""
        import concurrent.futures

        from xagent.core.orchestration import run_agent
        from xagent.enterprise.auth.principal import Principal

        logger.info("job_executing", job_id=job.job_id, name=job.name)

        def _run_in_thread() -> str:
            import asyncio as _aio

            async def _inner() -> str:
                principal = Principal(
                    user_id=job.owner_id or "scheduler",
                    tenant_id=job.tenant_id or "default",
                    roles=frozenset({"admin"}),
                )
                result = await _aio.wait_for(
                    run_agent(job.goal, principal=principal, role_name=job.role),
                    timeout=300,
                )
                return str(result.to_dict().get("final_answer") or "")[:500]

            loop = _aio.new_event_loop()
            try:
                return loop.run_until_complete(_inner())
            finally:
                loop.close()

        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                job.last_result = await loop.run_in_executor(pool, _run_in_thread)
            logger.info("job_succeeded", job_id=job.job_id)
        except Exception as exc:
            job.last_result = f"ERROR: {exc}"[:500]
            logger.error("job_failed", job_id=job.job_id, error=str(exc))


# 全局单例
_scheduler: Scheduler | None = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
