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

from xagent.domains.scheduled_jobs.models import ClaimedScheduledJob
from xagent.infra.logging import get_logger

logger = get_logger("xagent.scheduler")

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


class RedisJobLock:
    """基于 Redis ``SET NX PX`` 的 job 粒度分布式锁（多实例防重复触发）。

    - key：``xagent:scheduler:lock:{job_id}``，value 为实例 ID（排障用）。
    - 租约（PX）由调用方给出，必须 < 任务调度间隔：同一轮调度窗口内只有
      一个实例能抢到锁；抢到锁的实例若在租约内崩溃，锁自然过期后其他实例
      可接管（failover）。
    - Redis 调用异常时返回 False（安全降级：宁可本轮不触发，也不冒
      多实例重复触发的风险），并打 warning。
    """

    KEY_PREFIX = "xagent:scheduler:lock:"

    def __init__(
        self,
        redis_url: str,
        instance_id: str | None = None,
        *,
        client: Any | None = None,
    ) -> None:
        if client is not None:
            self._client = client  # 测试注入（fakeredis / mock）
        else:
            import redis.asyncio as aioredis  # 延迟导入，lite 模式无需 redis 服务

            self._client = aioredis.from_url(redis_url, decode_responses=True)
        self._instance_id = instance_id or uuid.uuid4().hex

    async def acquire(self, job_id: str, lease_seconds: int) -> bool:
        """尝试抢锁；抢到返回 True。Redis 异常返回 False（不触发）。"""
        try:
            ok = await self._client.set(
                self.KEY_PREFIX + job_id,
                self._instance_id,
                nx=True,
                px=max(1, int(lease_seconds * 1000)),
            )
            return bool(ok)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler_lock_redis_error", job_id=job_id, error=str(exc))
            return False

    async def release(self, job_id: str) -> bool:
        """仅释放当前实例持有的锁。"""
        from redis.exceptions import WatchError

        key = self.KEY_PREFIX + job_id
        pipe = self._client.pipeline()
        try:
            while True:
                try:
                    await pipe.watch(key)
                    if await pipe.get(key) != self._instance_id:
                        await pipe.unwatch()
                        return False
                    pipe.multi()
                    pipe.delete(key)
                    result = await pipe.execute()
                    return bool(result[0])
                except WatchError:
                    continue
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "scheduler_lock_release_error", job_id=job_id, error=str(exc)
            )
            return False
        finally:
            await pipe.reset()


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

    def __init__(
        self,
        storage_dir: Path | None = None,
        *,
        job_lock: RedisJobLock | None = None,
    ) -> None:
        base = storage_dir or _PROJECT_ROOT / "data" / "scheduler"
        self._dir = base
        self._dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, ScheduledJob] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        # 分布式锁：None 表示未初始化；start() 时按配置决定是否启用 Redis 锁
        self._lock: RedisJobLock | None = job_lock
        self._load_all()

    def _load_all(self) -> None:
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                job = ScheduledJob(**data)
                self._jobs[job.job_id] = job
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "scheduler_legacy_job_load_failed",
                    path=str(f),
                    error=str(exc),
                )
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
        self._init_job_lock()
        from xagent.domains.scheduled_jobs import recover_expired_job_runs
        from xagent.infra.db import get_sessionmaker

        async with get_sessionmaker()() as session:
            recovered = await recover_expired_job_runs(
                session, now=datetime.now(UTC)
            )
            await session.commit()
        if recovered:
            logger.warning("scheduler_runs_recovered", count=recovered)
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("scheduler_started", jobs=len(self._jobs))

    def _init_job_lock(self) -> None:
        """按配置初始化分布式锁。

        配置 ``XAGENT_CACHE__REDIS_URL`` 时启用 Redis 锁（多实例防重复触发）；
        未配置时保持单实例现状，并打一次性 warning 提示多实例风险。
        """
        if self._lock is not None:
            return
        from xagent.infra.settings import get_settings

        redis_url = get_settings().cache.redis_url
        if redis_url:
            self._lock = RedisJobLock(redis_url)
            logger.info("scheduler_distributed_lock_enabled")
        else:
            logger.warning(
                "scheduler_no_distributed_lock",
                detail="未配置 XAGENT_CACHE__REDIS_URL：多实例部署会重复触发定时任务"
                "（单实例/lite 部署可忽略此警告）",
            )

    async def _try_acquire_job_lock(self, job: ScheduledJob) -> bool:
        """多实例防重：启用分布式锁时必须抢到锁才执行；未启用直接放行。

        锁租约取调度间隔的 90%（至少 1s），保证租约 < 调度间隔：本轮执行完后
        锁先于下一次到期时间释放，不会误拦下一轮的合法触发。
        """
        if self._lock is None:
            return True
        lease = max(1, int(job.interval_seconds * 0.9))
        acquired = await self._lock.acquire(job.job_id, lease)
        if not acquired:
            logger.info("job_skipped_lock_held", job_id=job.job_id)
        return acquired

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        """主调度循环：每 30s 检查一次到期任务。启动后延迟 60s 再执行。"""
        await asyncio.sleep(60)  # 避免启动时与主应用竞争资源
        tick = 0
        while self._running:
            try:
                # 每个 tick 最多处理 20 个已到期 run，避免恢复时洪峰。
                for _ in range(20):
                    claimed = await self._claim_next_durable_run()
                    if claimed is None:
                        break
                    await self._execute_durable_run(claimed)
                # P4 goal/taskboard 自动推进：每 2 个周期（~60s）一次 tick；
                # 无候选 goal 时为空转，开销可忽略
                tick += 1
                if tick % 2 == 0:
                    from xagent.core.spine.advance import advance_all_goals
                    await advance_all_goals()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("scheduler_loop_error", error=str(exc))
            await asyncio.sleep(30)

    async def _claim_next_durable_run(self) -> ClaimedScheduledJob | None:
        from xagent.domains.scheduled_jobs import (
            claim_due_job,
            claim_due_retry,
            get_due_job_id,
            get_due_retry_job_id,
        )
        from xagent.infra.db import get_sessionmaker

        now = datetime.now(UTC)
        async with get_sessionmaker()() as session:
            if self._lock is not None:
                job_id = await get_due_retry_job_id(session, now=now)
                retry = job_id is not None
                if job_id is None:
                    job_id = await get_due_job_id(session, now=now)
                if job_id is None:
                    return None
                if not await self._lock.acquire(job_id, 360):
                    logger.info("durable_job_skipped_lock_held", job_id=job_id)
                    return None
                try:
                    if retry:
                        claimed = await claim_due_retry(
                            session,
                            now=now,
                            lease_seconds=360,
                            claim_token=uuid.uuid4().hex,
                            job_id=job_id,
                        )
                    else:
                        claimed = await claim_due_job(
                            session,
                            now=now,
                            lease_seconds=360,
                            claim_token=uuid.uuid4().hex,
                            job_id=job_id,
                        )
                    await session.commit()
                except Exception:
                    await self._lock.release(job_id)
                    raise
                if claimed is None:
                    await self._lock.release(job_id)
                return claimed
            claimed = await claim_due_retry(
                session,
                now=now,
                lease_seconds=360,
                claim_token=uuid.uuid4().hex,
            )
            if claimed is None:
                claimed = await claim_due_job(
                    session,
                    now=now,
                    lease_seconds=360,
                    claim_token=uuid.uuid4().hex,
                )
            await session.commit()
            return claimed

    async def _execute_durable_run(self, claimed: ClaimedScheduledJob) -> None:
        from xagent.core.orchestration import run_agent
        from xagent.domains.scheduled_jobs import complete_scheduled_job_run
        from xagent.enterprise.auth.principal import Principal
        from xagent.infra.db import get_sessionmaker

        principal = Principal(
            user_id=claimed.job.owner_id or "scheduler",
            tenant_id=claimed.job.tenant_id,
            roles=frozenset({"admin"}),
        )
        try:
            succeeded = False
            result_text = ""
            error = ""
            agent_run_id = ""
            try:
                result = await asyncio.wait_for(
                    run_agent(
                        claimed.job.goal,
                        principal=principal,
                        role_name=claimed.job.role or None,
                    ),
                    timeout=300,
                )
                payload = result.to_dict()
                result_text = str(payload.get("final_answer") or "")
                agent_run_id = str(payload.get("run_id") or "")
                succeeded = True
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                logger.error(
                    "durable_job_run_failed",
                    job_id=claimed.job.job_id,
                    run_id=claimed.run.run_id,
                    error=error,
                )
            async with get_sessionmaker()() as session:
                completed = await complete_scheduled_job_run(
                    session,
                    tenant_id=claimed.job.tenant_id,
                    run_id=claimed.run.run_id,
                    succeeded=succeeded,
                    now=datetime.now(UTC),
                    result=result_text,
                    error=error,
                    agent_run_id=agent_run_id,
                )
                await session.commit()
        finally:
            if self._lock is not None:
                await self._lock.release(claimed.job.job_id)
        logger.info(
            "durable_job_run_completed",
            job_id=claimed.job.job_id,
            run_id=claimed.run.run_id,
            status=completed.status,
        )
        if completed.status in {"succeeded", "failed"}:
            await self._notify_terminal_run(
                claimed, completed.status, completed.agent_run_id
            )

    async def _notify_terminal_run(
        self, claimed: ClaimedScheduledJob, status: str, agent_run_id: str
    ) -> None:
        from xagent.core.webhooks import get_webhook_manager
        from xagent.domains.scheduled_jobs import set_scheduled_job_run_notification
        from xagent.infra.db import get_sessionmaker

        try:
            delivery = await get_webhook_manager().emit(
                claimed.job.tenant_id,
                "scheduler.job_run.completed",
                {
                    "job_id": claimed.job.job_id,
                    "run_id": claimed.run.run_id,
                    "status": status,
                    "attempt": claimed.run.attempt,
                    "agent_run_id": agent_run_id,
                },
            )
            if delivery.target_count == 0:
                notification_status = "not_configured"
                notification_error = ""
            elif delivery.errors:
                notification_status = "failed"
                notification_error = "; ".join(delivery.errors)
            else:
                notification_status = "delivered"
                notification_error = ""
        except Exception as exc:  # noqa: BLE001
            notification_status = "failed"
            notification_error = str(exc)
        async with get_sessionmaker()() as session:
            await set_scheduled_job_run_notification(
                session,
                tenant_id=claimed.job.tenant_id,
                run_id=claimed.run.run_id,
                status=notification_status,
                error=notification_error,
            )
            await session.commit()

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
