"""bcrypt 异步化测试：校验/哈希移入线程池，不阻塞事件循环。"""

from __future__ import annotations

import asyncio

from xagent.enterprise.auth.users import UserStore


async def test_aauthenticate_roundtrip() -> None:
    store = UserStore()
    await store.aadd("u1", "t1", ["member"], "secret123")
    user = await store.aauthenticate("u1", "secret123")
    assert user is not None and user.user_id == "u1"
    assert await store.aauthenticate("u1", "wrong") is None
    # 用户不存在时短路（不做 verify），与同步版时序语义一致
    assert await store.aauthenticate("nouser", "x") is None


async def test_achange_password() -> None:
    store = UserStore()
    await store.aadd("u1", "t1", ["member"], "oldpass123")
    assert await store.achange_password("u1", "newpass123")
    assert await store.aauthenticate("u1", "oldpass123") is None
    assert (await store.aauthenticate("u1", "newpass123")) is not None
    assert await store.achange_password("ghost", "x") is False


async def test_bcrypt_verify_offloaded_from_event_loop() -> None:
    """并发校验期间事件循环保持调度：若 bcrypt 同步阻塞，ticker 将停滞。"""
    store = UserStore()
    await store.aadd("u1", "t1", ["member"], "secret123")

    ticks = 0
    stopped = False

    async def ticker() -> None:
        nonlocal ticks
        while not stopped:
            ticks += 1
            await asyncio.sleep(0.01)

    task = asyncio.create_task(ticker())
    results = await asyncio.gather(
        *(store.aauthenticate("u1", "secret123") for _ in range(4))
    )
    stopped = True
    await task

    assert all(r is not None for r in results)
    # 4 次 ~300ms 校验若同步执行，事件循环将被独占 ~1.2s+（ticker 仍会因
    # gather 间的调度偶尔运行，但远少于此阈值）；线程池卸载后 ticker 应持续运行
    assert ticks >= 10
