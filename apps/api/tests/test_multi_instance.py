"""多实例部署就绪测试：登录限流双后端 + 调度器分布式锁。

无运行中的 Redis：Redis 行为用 fakeredis 验证，降级语义用抛异常的 mock 客户端验证。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from xagent.core.scheduler import RedisJobLock, Scheduler
from xagent.enterprise.auth.login_rate_limit import (
    InMemoryBackend,
    LoginRateLimiter,
    RedisBackend,
    get_login_rate_limiter,
    reset_login_rate_limiter,
)


@pytest.fixture
def fake_redis():
    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis(decode_responses=True)


class _BrokenPipeline:
    async def __aenter__(self):  # noqa: ANN202
        raise ConnectionError("redis down (pipeline)")

    async def __aexit__(self, *args) -> bool:  # noqa: ANN002
        return False


class _BrokenRedis:
    """所有调用都抛异常的 mock 客户端（模拟 Redis 挂掉）。"""

    def pipeline(self, *args, **kwargs) -> _BrokenPipeline:  # noqa: ANN002, ANN003
        return _BrokenPipeline()

    def __getattr__(self, name):  # noqa: ANN001, ANN202
        async def _raise(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            raise ConnectionError(f"redis down ({name})")

        return _raise


# ─── 登录限流：内存后端（默认）──────────────────────────────────────


async def test_in_memory_backend_matches_sync_semantics() -> None:
    """内存后端异步接口与同步接口语义一致。"""
    backend = InMemoryBackend(max_failures=3, window_seconds=60, lockout_seconds=30)
    key = "1.2.3.4:alice"
    assert await backend.record_failure(key) == 0.0
    assert await backend.record_failure(key) == 0.0
    assert await backend.record_failure(key) == 30.0
    assert 0 < await backend.locked_seconds(key) <= 30
    await backend.record_success(key)
    assert await backend.locked_seconds(key) == 0.0


def test_get_login_rate_limiter_defaults_to_memory() -> None:
    """未配置 XAGENT_CACHE__REDIS_URL：单例无 Redis 后端（lite/单实例）。"""
    reset_login_rate_limiter()
    try:
        limiter = get_login_rate_limiter()
        assert limiter.backend_name == "InMemoryBackend"
    finally:
        reset_login_rate_limiter()


# ─── 登录限流：Redis 后端（fakeredis）──────────────────────────────


async def test_redis_backend_sliding_window_and_lockout(fake_redis) -> None:
    """Redis 后端：窗口内失败达阈值锁定，锁定带 TTL，成功清零。"""
    backend = RedisBackend(
        "redis://unused", max_failures=3, window_seconds=60, lockout_seconds=30,
        client=fake_redis,
    )
    key = "1.2.3.4:bob"
    assert await backend.record_failure(key) == 0.0
    assert await backend.record_failure(key) == 0.0
    assert await backend.record_failure(key) == 30.0  # 第 3 次触发锁定

    locked = await backend.locked_seconds(key)
    assert 0 < locked <= 30
    # 锁定期间继续失败仍返回锁定（计数已清空，重新累计）
    assert await backend.record_failure(key) == 0.0

    await backend.record_success(key)
    assert await backend.locked_seconds(key) == 0.0
    # 计数已清零：再失败 2 次不锁定
    assert await backend.record_failure(key) == 0.0
    assert await backend.record_failure(key) == 0.0


async def test_redis_backend_state_shared_across_instances(fake_redis) -> None:
    """两个 backend 实例连同一 Redis（模拟两个 API 实例）：计数合并，锁定共享。"""
    a = RedisBackend("redis://unused", max_failures=4, client=fake_redis)
    b = RedisBackend("redis://unused", max_failures=4, client=fake_redis)
    key = "1.2.3.4:carol"
    await a.record_failure(key)
    await b.record_failure(key)
    await a.record_failure(key)
    assert await b.record_failure(key) == 60.0  # 跨实例累计到第 4 次，b 触发锁定
    assert 0 < await a.locked_seconds(key) <= 60  # a 也能看到锁定（共享状态）


async def test_redis_backend_degrades_to_memory_on_failure() -> None:
    """Redis 挂掉：降级内存实现并继续限流（功能不中断）。"""
    backend = RedisBackend(
        "redis://unused", max_failures=2, window_seconds=60, lockout_seconds=30,
        client=_BrokenRedis(),
    )
    key = "1.2.3.4:dave"
    assert await backend.record_failure(key) == 0.0
    assert await backend.record_failure(key) == 30.0  # 内存降级后仍累计并锁定
    assert 0 < await backend.locked_seconds(key) <= 30
    await backend.record_success(key)  # 不抛异常
    assert await backend.locked_seconds(key) == 0.0


def test_get_login_rate_limiter_uses_redis_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """配置 XAGENT_CACHE__REDIS_URL 后单例自动启用 Redis 后端。"""
    from xagent.infra.settings import get_settings

    monkeypatch.setenv("XAGENT_CACHE__REDIS_URL", "redis://localhost:6379/0")
    get_settings.cache_clear()
    reset_login_rate_limiter()
    try:
        limiter = get_login_rate_limiter()
        assert limiter.backend_name == "RedisBackend"
    finally:
        reset_login_rate_limiter()
        get_settings.cache_clear()


async def test_limiter_async_facade_without_backend() -> None:
    """无 Redis 后端时异步入口走内存实现（路由默认路径）。"""
    limiter = LoginRateLimiter(max_failures=2, lockout_seconds=30)
    key = limiter.make_key("1.2.3.4", "Eve")
    assert await limiter.arecord_failure(key) == 0.0
    assert await limiter.arecord_failure(key) == 30.0
    assert 0 < await limiter.alocked_seconds(key) <= 30
    await limiter.arecord_success(key)
    assert await limiter.alocked_seconds(key) == 0.0


# ─── 调度器分布式锁 ────────────────────────────────────────────────


async def test_scheduler_without_lock_passes(tmp_path: Path) -> None:
    """无分布式锁（单实例现状）：直接放行。"""
    sched = Scheduler(storage_dir=tmp_path, job_lock=None)
    job = sched.add_job(name="j", goal="g", interval_seconds=3600)
    assert await sched._try_acquire_job_lock(job) is True


async def test_scheduler_lock_held_skips(tmp_path: Path) -> None:
    """抢不到锁（其他实例在执行）：跳过本轮，不触发。"""
    sched = Scheduler(storage_dir=tmp_path, job_lock=_AlwaysDenyLock())  # type: ignore[arg-type]
    job = sched.add_job(name="j", goal="g", interval_seconds=3600)
    assert await sched._try_acquire_job_lock(job) is False


class _AlwaysDenyLock:
    async def acquire(self, job_id: str, lease_seconds: int) -> bool:
        return False


class _CapturingLock:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def acquire(self, job_id: str, lease_seconds: int) -> bool:
        self.calls.append((job_id, lease_seconds))
        return True


async def test_scheduler_lock_lease_below_interval(tmp_path: Path) -> None:
    """锁租约必须 < 调度间隔（取 90%），不拦截下一轮合法触发。"""
    lock = _CapturingLock()
    sched = Scheduler(storage_dir=tmp_path, job_lock=lock)  # type: ignore[arg-type]
    job = sched.add_job(name="j", goal="g", interval_seconds=3600)
    assert await sched._try_acquire_job_lock(job) is True
    assert lock.calls == [(job.job_id, 3240)]
    assert lock.calls[0][1] < job.interval_seconds


async def test_redis_job_lock_mutual_exclusion(fake_redis) -> None:
    """两个实例（两个 RedisJobLock）对同一 job 只能一个抢到锁。"""
    lock_a = RedisJobLock("redis://unused", instance_id="a", client=fake_redis)
    lock_b = RedisJobLock("redis://unused", instance_id="b", client=fake_redis)
    assert await lock_a.acquire("job-1", lease_seconds=300) is True
    assert await lock_b.acquire("job-1", lease_seconds=300) is False  # a 持有
    # 不同 job 互不影响
    assert await lock_b.acquire("job-2", lease_seconds=300) is True
    # 锁带 TTL（租约），到期后自然释放
    ttl = await fake_redis.pttl("xagent:scheduler:lock:job-1")
    assert 0 < ttl <= 300_000


async def test_redis_job_lock_degrades_closed_on_error() -> None:
    """Redis 挂掉：acquire 返回 False（宁可不触发也不重复触发）。"""
    lock = RedisJobLock("redis://unused", client=_BrokenRedis())
    assert await lock.acquire("job-1", lease_seconds=300) is False


def test_scheduler_start_warns_once_without_redis(tmp_path: Path) -> None:
    """未配置 Redis：start() 打一次性 warning，锁保持关闭（单实例现状不变）。"""
    sched = Scheduler(storage_dir=tmp_path)
    sched._init_job_lock()
    assert sched._lock is None
    sched._init_job_lock()  # 幂等，不重复初始化
    assert sched._lock is None


def test_scheduler_start_enables_lock_with_redis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """配置 XAGENT_CACHE__REDIS_URL：start() 自动启用 Redis 分布式锁。"""
    from xagent.infra.settings import get_settings

    monkeypatch.setenv("XAGENT_CACHE__REDIS_URL", "redis://localhost:6379/0")
    get_settings.cache_clear()
    try:
        sched = Scheduler(storage_dir=tmp_path)
        sched._init_job_lock()
        assert isinstance(sched._lock, RedisJobLock)
    finally:
        get_settings.cache_clear()
