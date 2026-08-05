from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.spine.service import create_goal, decompose_goal
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session
from xagent.infra.repos.spine import (
    load_goal_snapshot,
    persist_goal,
    persist_initiatives,
    persist_tasks,
)

router = APIRouter(prefix="/spine", tags=["spine"])

TASKBOARD_COLUMNS = (
    "ready",
    "in_progress",
    "blocked",
    "review",
    "release_ready",
    "deploying",
    "verifying",
    "delivered",
    "recovery",
)


class GoalCreateIn(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field(default="")


@router.post("/goals", summary="创建 delivery goal")
async def create_delivery_goal(
    body: GoalCreateIn,
    principal: Principal = Depends(require_permission("spine", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    goal = create_goal(
        tenant_id=principal.tenant_id,
        owner_id=principal.user_id,
        title=body.title,
        description=body.description,
    )
    initiatives, tasks = decompose_goal(goal)

    await persist_goal(session, goal)
    await session.flush()
    await persist_initiatives(session, initiatives)
    await session.flush()
    await persist_tasks(session, tasks)
    await session.commit()

    return {
        "goal": goal.to_dict(),
        "initiatives": [item.to_dict() for item in initiatives],
        "tasks": [item.to_dict() for item in tasks],
    }


@router.get("/goals/{goal_id}/board", summary="获取 goal taskboard 快照")
async def get_goal_board(
    goal_id: str,
    principal: Principal = Depends(require_permission("spine", "read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    snapshot = await load_goal_snapshot(session, goal_id, principal.tenant_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "目标不存在或无权访问")

    columns: dict[str, list[dict]] = {column: [] for column in TASKBOARD_COLUMNS}
    unknown_status_tasks: list[dict] = []
    for task in snapshot["tasks"]:
        task_status = str(task["status"])
        if task_status in columns:
            columns[task_status].append(task)
        else:
            unknown_status_tasks.append(task)

    return {
        "goal": snapshot["goal"],
        "initiatives": snapshot["initiatives"],
        "columns": columns,
        "unknown_status_tasks": unknown_status_tasks,
    }


class AutoAdvanceIn(BaseModel):
    enabled: bool = Field(..., description="是否开启自动推进 tick")
    auto_execute: bool = Field(default=False, description="是否允许 tick 自动起 run（花 LLM 费用）")
    max_retries: int = Field(default=3, ge=0, le=10, description="recovery 瞬态失败自动重试上限")


@router.post("/goals/{goal_id}/auto-advance", summary="开关 goal 自动推进（P4）")
async def set_auto_advance(
    goal_id: str,
    body: AutoAdvanceIn,
    principal: Principal = Depends(require_permission("spine", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from xagent.core.spine.advance import DEFAULT_MAX_RETRIES
    from xagent.infra.models.spine import GoalORM

    goal = await session.get(GoalORM, goal_id)
    if goal is None or goal.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "目标不存在或无权访问")

    import json as _json

    try:
        metadata = _json.loads(goal.metadata_json or "{}")
        if not isinstance(metadata, dict):
            metadata = {}
    except _json.JSONDecodeError:
        metadata = {}
    metadata["auto_advance"] = body.enabled
    metadata["auto_execute"] = body.auto_execute
    if body.max_retries != DEFAULT_MAX_RETRIES:
        metadata["advance_max_retries"] = body.max_retries
    else:
        metadata.pop("advance_max_retries", None)
    goal.metadata_json = _json.dumps(metadata, ensure_ascii=False)
    # 开启即激活（pending → active）；关闭不改 status
    if body.enabled and goal.status == "pending":
        goal.status = "active"
    await session.commit()
    return {
        "goal_id": goal_id,
        "auto_advance": body.enabled,
        "auto_execute": body.auto_execute,
        "max_retries": body.max_retries,
        "status": goal.status,
    }


class TaskReviewIn(BaseModel):
    diff: str | None = Field(None, description="待评审的 unified diff 文本")
    repo: str | None = Field(None, description="本地仓库路径（与 base 搭配）")
    base: str | None = Field(None, description="基准 ref")
    head: str = Field("HEAD", description="目标 ref")
    max_files: int = Field(10, ge=1, le=50)


# verdict → 任务状态迁移映射（review 闭环，P4 切口②）：
# approve → release_ready；request_changes → ready（重做，blocker 记录理由）；
# comment → 留 review 等人工；评审本身 partial/failed → 不迁移（安全默认）
_VERDICT_TRANSITIONS = {
    "approve": "release_ready",
    "request_changes": "ready",
}


@router.post("/goals/{goal_id}/tasks/{task_id}/review", summary="任务复检闭环（P4）")
async def review_task(
    goal_id: str,
    task_id: str,
    body: TaskReviewIn,
    principal: Principal = Depends(require_permission("spine", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """对 review 列任务执行代码复检，按 verdict 自动迁移任务状态并落证据。"""
    from xagent.domains.code_review import review_diff
    from xagent.enterprise.audit import get_audit_log
    from xagent.infra.models.spine import DeliveryTaskORM
    from xagent.infra.repos.evidence import build_evidence_record, persist_evidence_record

    if not (body.diff or "").strip() and not (body.repo and body.base):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "必须提供 diff 文本，或 repo + base",
        )

    task = await session.get(DeliveryTaskORM, task_id)
    if task is None or task.tenant_id != principal.tenant_id or task.goal_id != goal_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在或无权访问")
    if task.status != "review":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"仅 review 列任务可复检（当前: {task.status}）",
        )

    try:
        result = await review_diff(
            diff=body.diff, repo=body.repo, base=body.base,
            head=body.head, max_files=body.max_files,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    # 状态迁移（仅评审完整成功时）
    transition = "none"
    if result.status == "succeeded":
        next_status = _VERDICT_TRANSITIONS.get(result.verdict)
        if next_status:
            task.status = next_status
            if next_status == "ready":
                top = [f for f in result.findings if f.severity in ("critical", "high")][:3]
                task.blocker_reason = (
                    "复检退回: " + "; ".join(f.issue[:60] for f in top)
                )[:500] if top else "复检退回: 需修改"
            else:
                task.blocker_reason = ""
            transition = f"review->{next_status}"

    # 落 review.verdict 证据（闭环的关键：结论可审计、可归档）
    record = build_evidence_record(
        tenant_id=principal.tenant_id,
        run_id=task.run_id or task_id,
        task_id=task_id,
        kind="review.verdict",
        payload={
            "review_id": result.review_id,
            "review_status": result.status,
            "verdict": result.verdict,
            "severity_counts": result.severity_counts(),
            "summary": result.summary[:300],
            "transition": transition,
            "duration_ms": round(result.duration_ms, 1),
        },
    )
    await persist_evidence_record(
        session,
        evidence_id=str(record["evidence_id"]),
        tenant_id=principal.tenant_id,
        run_id=task.run_id or task_id,
        task_id=task_id,
        artifact_id=None,
        kind="review.verdict",
        payload=record["payload"],
    )
    await session.commit()

    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="spine.task_review",
        resource="spine",
        detail={
            "goal_id": goal_id, "task_id": task_id,
            "review_id": result.review_id, "verdict": result.verdict,
            "review_status": result.status, "transition": transition,
        },
    )
    return {
        "task_id": task_id,
        "task_status": task.status,
        "transition": transition,
        "review_id": result.review_id,
        "verdict": result.verdict,
        "review_status": result.status,
        "severity_counts": result.severity_counts(),
        "summary": result.summary,
    }


class ReleaseCreateIn(BaseModel):
    branch_name: str = Field(..., min_length=1)
    commit_sha: str = Field(..., min_length=7)
    pr_number: str = Field(default="")
    ci_run: dict = Field(default_factory=dict)
    evidence_paths: list[str] = Field(default_factory=list)


@router.post("/goals/{goal_id}/release", summary="release 收口（P4 切口③）")
async def create_release(
    goal_id: str,
    body: ReleaseCreateIn,
    principal: Principal = Depends(require_permission("spine", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """把 release_ready 列任务打包为 release 记录：ReleaseRecordORM 首写入方。

    前置：存在 release_ready 任务，且无 in_progress/blocked/recovery 任务。
    收口动作：release_ready → delivered；全部任务终态时 goal → delivered。
    """
    import json as _json
    import uuid as _uuid

    from xagent.core.spine.release import build_release_package
    from xagent.enterprise.audit import get_audit_log
    from xagent.infra.models.spine import DeliveryTaskORM, GoalORM, ReleaseRecordORM
    from xagent.infra.repos.evidence import build_evidence_record, persist_evidence_record
    from xagent.infra.repos.spine import load_goal_snapshot

    goal = await session.get(GoalORM, goal_id)
    if goal is None or goal.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "目标不存在或无权访问")

    snapshot = await load_goal_snapshot(session, goal_id, principal.tenant_id)
    tasks = snapshot["tasks"] if snapshot else []
    release_ready = [t for t in tasks if str(t["status"]) == "release_ready"]
    open_blockers = [
        t for t in tasks
        if str(t["status"]) in ("in_progress", "blocked", "recovery")
    ]
    if not release_ready:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "release_ready 列为空，无可收口任务"
        )
    if open_blockers:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"存在未决任务（{len(open_blockers)} 个 in_progress/blocked/recovery），不可收口",
        )

    package = build_release_package(
        goal_id=goal_id,
        branch_name=body.branch_name,
        commit_sha=body.commit_sha,
        pr_number=body.pr_number,
        ci_run=body.ci_run,
        evidence_paths=body.evidence_paths,
    )
    release_id = _uuid.uuid4().hex[:16]
    session.add(ReleaseRecordORM(
        release_id=release_id,
        goal_id=goal_id,
        tenant_id=principal.tenant_id,
        branch_name=body.branch_name,
        commit_sha=body.commit_sha,
        pr_number=body.pr_number,
        status="ready",
        summary_json=_json.dumps(package, ensure_ascii=False),
    ))

    delivered = 0
    for t in release_ready:
        row = await session.get(DeliveryTaskORM, t["task_id"])
        if row is not None:
            row.status = "delivered"
            delivered += 1

    remaining_open = [
        t for t in tasks
        if str(t["status"]) not in ("release_ready", "delivered")
    ]
    if not remaining_open:
        goal.status = "delivered"
        goal.phase = "release"

    record = build_evidence_record(
        tenant_id=principal.tenant_id,
        run_id=release_id,
        task_id=goal_id,
        kind="release.created",
        payload={
            "release_id": release_id,
            "commit_sha": body.commit_sha,
            "pr_number": body.pr_number,
            "tasks_delivered": delivered,
            "goal_status": goal.status,
        },
    )
    await persist_evidence_record(
        session,
        evidence_id=str(record["evidence_id"]),
        tenant_id=principal.tenant_id,
        run_id=release_id,
        task_id=goal_id,
        artifact_id=None,
        kind="release.created",
        payload=record["payload"],
    )
    await session.commit()

    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="spine.release_created",
        resource="spine",
        detail={
            "goal_id": goal_id, "release_id": release_id,
            "commit_sha": body.commit_sha, "tasks_delivered": delivered,
            "goal_status": goal.status,
        },
    )
    return {
        "release_id": release_id,
        "status": "ready",
        "tasks_delivered": delivered,
        "goal_status": goal.status,
        "package": package,
    }
