"""Goal/taskboard 自动推进（P4）：定时 tick 驱动 spine 状态机。

设计要点：
- **opt-in**：只有 goal metadata `auto_advance=true` 的 goal 才会被 tick
  （`POST /api/v1/spine/goals/{id}/auto-advance` 开启）；`auto_execute=true`
  才会真正起 run（花 LLM 费用），否则只做状态推进（激活/recovery 解阻）。
- **recovery 自动解阻**：blocker 命中瞬态模式（超时/429/连接类）且重试次数
  未达 `max_retries`（重试计数存 goal metadata，免迁移）→ 任务回 ready；
  非瞬态或超限 → 留在 recovery 等人处理。
- **多实例防重**：配置 Redis 时按 goal_id 抢 `spine-advance:{goal_id}` 锁。
- tick 由 scheduler 主循环每 2 个周期（~60s）驱动一次。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.infra.logging import get_logger
from xagent.infra.models.spine import GoalORM

logger = get_logger("xagent.spine.advance")

# 瞬态 blocker 模式（小写匹配）：这些失败值得自动重试
TRANSIENT_BLOCKER_PATTERNS = (
    "timeout", "超时", "429", "rate limit", "限流",
    "connection", "连接", "temporar", "暂时",
    "unavailable", "不可用", "overload", "过载", "econnreset",
)

DEFAULT_MAX_RETRIES = 3


@dataclass
class AdvanceConfig:
    enabled: bool = False
    auto_execute: bool = False
    max_retries: int = DEFAULT_MAX_RETRIES


def is_transient_blocker(reason: str) -> bool:
    """判断 blocker 是否瞬态（可自动重试）。"""
    text = (reason or "").lower()
    return any(p in text for p in TRANSIENT_BLOCKER_PATTERNS)


def parse_advance_config(metadata: dict[str, Any]) -> AdvanceConfig:
    return AdvanceConfig(
        enabled=bool(metadata.get("auto_advance")),
        auto_execute=bool(metadata.get("auto_execute")),
        max_retries=int(metadata.get("advance_max_retries") or DEFAULT_MAX_RETRIES),
    )


def _goal_metadata(row: GoalORM) -> dict[str, Any]:
    try:
        data = json.loads(row.metadata_json or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


async def list_advance_candidates(session: AsyncSession) -> list[GoalORM]:
    """列出可能开启自动推进的 goal（pending/active），metadata 过滤在内存做。"""
    stmt = select(GoalORM).where(GoalORM.status.in_(["pending", "active"]))
    rows = (await session.execute(stmt)).scalars().all()
    return [r for r in rows if parse_advance_config(_goal_metadata(r)).enabled]


def _retry_counters(metadata: dict[str, Any]) -> dict[str, int]:
    raw = metadata.get("advance_retries")
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items()}


async def advance_goal(session: AsyncSession, goal: GoalORM) -> dict[str, Any]:
    """对单个 goal 执行一次推进。返回采取的动作清单（供日志/证据）。"""
    from xagent.infra.repos.spine import load_goal_snapshot

    metadata = _goal_metadata(goal)
    config = parse_advance_config(metadata)
    actions: list[dict[str, Any]] = []

    if goal.status == "pending":
        goal.status = "active"
        actions.append({"kind": "goal_activated", "goal_id": goal.goal_id})

    snapshot = await load_goal_snapshot(session, goal.goal_id, goal.tenant_id)
    if snapshot is None:
        return {"goal_id": goal.goal_id, "actions": actions}

    tasks = snapshot.get("tasks") or []
    retries = _retry_counters(metadata)
    changed = False

    # 1) recovery 解阻：瞬态 blocker 且未超限 → 回 ready
    for task in tasks:
        if str(task.get("status")) != "recovery":
            continue
        task_id = str(task.get("task_id"))
        reason = str(task.get("blocker_reason") or "")
        used = retries.get(task_id, 0)
        if is_transient_blocker(reason) and used < config.max_retries:
            retries[task_id] = used + 1
            changed = True
            # 直接改 ORM 行（snapshot 是 dict 视图）
            from xagent.infra.models.spine import DeliveryTaskORM

            row = await session.get(DeliveryTaskORM, task_id)
            if row is not None:
                row.status = "ready"
                row.blocker_reason = ""
                actions.append({
                    "kind": "task_retried",
                    "task_id": task_id,
                    "attempt": used + 1,
                    "max_retries": config.max_retries,
                    "previous_blocker": reason[:120],
                })
        else:
            actions.append({
                "kind": "task_needs_human",
                "task_id": task_id,
                "blocker": reason[:120],
                "retries_used": used,
            })

    if changed:
        metadata["advance_retries"] = retries
        goal.metadata_json = json.dumps(metadata, ensure_ascii=False)

    # 2) 执行推进：仅 auto_execute 且当前无 recovery/blocked 时，取一个 ready 任务起 run
    recovery_left = [t for t in tasks if str(t.get("status")) == "recovery"]
    blocked_left = [t for t in tasks if str(t.get("status")) == "blocked"]
    if config.auto_execute and not recovery_left and not blocked_left:
        in_progress = [t for t in tasks if str(t.get("status")) == "in_progress"]
        ready = [t for t in tasks if str(t.get("status")) == "ready"]
        if ready and not in_progress:
            task = sorted(ready, key=lambda t: t.get("position") or 0)[0]
            action = await _execute_task(session, goal, task)
            actions.append(action)

    if actions:
        logger.info("spine_advanced", goal_id=goal.goal_id, actions=len(actions))
    return {"goal_id": goal.goal_id, "actions": actions}


async def _execute_task(
    session: AsyncSession, goal: GoalORM, task: dict[str, Any]
) -> dict[str, Any]:
    """为一个 ready 任务起一次 agent run（同步等待，300s 封顶）。"""
    from xagent.core.orchestration import run_agent
    from xagent.enterprise.auth.principal import Principal
    from xagent.infra.repos.spine import (
        attach_run_to_task,
        update_task_status_by_run_id,
    )

    run_id = uuid.uuid4().hex
    task_id = str(task.get("task_id"))
    await attach_run_to_task(
        session,
        tenant_id=goal.tenant_id,
        run_id=run_id,
        spine_task_id=task_id,
        goal_id=goal.goal_id,
        next_status="in_progress",
    )
    await session.flush()
    principal = Principal(
        user_id=goal.owner_id or "spine-advance",
        tenant_id=goal.tenant_id,
        roles=frozenset({"admin"}),
    )
    goal_text = f"{task.get('title') or ''}\n{task.get('detail') or ''}".strip()
    try:
        result = await asyncio.wait_for(
            run_agent(goal_text, principal=principal), timeout=300
        )
        await update_task_status_by_run_id(
            session, tenant_id=goal.tenant_id, run_id=run_id, next_status="review"
        )
        return {
            "kind": "task_executed",
            "task_id": task_id,
            "run_id": run_id,
            "status": "succeeded",
            "steps": getattr(result, "steps", 0),
        }
    except Exception as exc:  # noqa: BLE001 - 失败转入 recovery，由下次 tick 分类
        await update_task_status_by_run_id(
            session,
            tenant_id=goal.tenant_id,
            run_id=run_id,
            next_status="recovery",
            blocker_reason=str(exc)[:500],
        )
        return {
            "kind": "task_executed",
            "task_id": task_id,
            "run_id": run_id,
            "status": "failed",
            "error": str(exc)[:200],
        }


async def advance_all_goals() -> dict[str, Any]:
    """对所有开启 auto_advance 的 goal 执行一次 tick（调度器驱动）。

    配置 Redis 时按 goal 抢分布式锁；无 Redis（单实例/lite）直接执行。
    任何单 goal 异常不影响其他 goal。
    """
    from xagent.core.scheduler import RedisJobLock
    from xagent.infra.db import get_sessionmaker
    from xagent.infra.settings import get_settings

    redis_url = get_settings().cache.redis_url
    lock = RedisJobLock(redis_url, instance_id="spine-advance") if redis_url else None
    results: list[dict[str, Any]] = []

    async with get_sessionmaker()() as session:
        candidates = await list_advance_candidates(session)
        goal_ids = [g.goal_id for g in candidates]

    for goal_id in goal_ids:
        if lock is not None:
            acquired = await lock.acquire(f"spine-advance:{goal_id}", 120)
            if not acquired:
                continue
        try:
            async with get_sessionmaker()() as session:
                goal = await session.get(GoalORM, goal_id)
                if goal is None:
                    continue
                results.append(await advance_goal(session, goal))
                await session.commit()
        except Exception as exc:  # noqa: BLE001 - 单 goal 失败不阻断全局 tick
            logger.warning("spine_advance_goal_failed", goal_id=goal_id, error=str(exc))
    return {"ticked_goals": len(results), "results": results}
