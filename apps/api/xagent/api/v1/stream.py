"""流式路由：Agent 运行 SSE（逐 token / 事件推送）。

用 StreamingResponse + async generator，把编排事件实时推给前端。
lite/mock 模式下仍能产出事件流（非真实 token，但 SSE 通道可用）。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from xagent.core.orchestration import run_agent
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_sessionmaker
from xagent.infra.logging import get_logger
from xagent.infra.repos.evidence import persist_evidence_bundle
from xagent.worker.celery_app import persist_agent_task_record_in_session

from .agents import (
    _build_commit_evidence,
    _build_failure_delivery_summary,
    _build_failure_result_summary,
    _is_runtime_persistence_schema_mismatch,
)

router = APIRouter(prefix="/stream", tags=["stream"])
logger = get_logger("xagent.api.stream")


class StreamRunIn(BaseModel):
    goal: str = Field(..., min_length=1)
    role: str | None = None
    capabilities: list[str] = Field(default_factory=list)


def _build_input_payload(goal: str, role: str | None, caps: list[str]) -> dict:
    return {
        "goal": goal,
        "role": role,
        "capabilities": list(caps),
    }


def _build_stream_result_summary(result: dict) -> dict:
    steps_value = result.get("steps")
    steps_count = steps_value if isinstance(steps_value, int) else len(steps_value or [])
    return {
        "status": "succeeded",
        "run_id": str(result.get("run_id") or ""),
        "steps_count": steps_count,
        "final_answer": str(result.get("final_answer") or "")[:400],
    }


def _build_stream_delivery_summary(result: dict) -> dict:
    summary = _build_stream_result_summary(result)
    run_id = str(result.get("run_id") or "")
    return {
        "status": "ready",
        "channel": "task_runtime",
        "kind": "agent.run",
        "summary": (
            f"流式 Agent 已完成 {summary['steps_count']} 个步骤并收束最终答复。"
            if summary["steps_count"]
            else "流式 Agent 已完成并收束最终答复。"
        ),
        "result": summary,
        "replay": {
            "mode": "task_detail",
            "label": "查看后台任务",
            "run_id": run_id,
            "task_id": run_id,
            "api_path": f"/api/v1/tasks/{run_id}",
            "console_path": f"/runs/{run_id}",
        },
        "resume": None,
        "artifacts": [],
        "validation": {"risks": []},
        "risks": [],
    }


async def _event_stream(
    goal: str, principal: Principal, role: str | None, caps: list[str]
) -> AsyncGenerator[bytes, None]:
    """跑 agent 并把事件逐条以 SSE 实时推送（step 级流式）。"""
    run_id = uuid.uuid4().hex
    yield _sse("started", {"goal": goal, "run_id": run_id})

    queue: asyncio.Queue = asyncio.Queue()
    done = object()
    input_payload = _build_input_payload(goal, role, caps)
    started_at = datetime.now(UTC)

    async def on_event(ev) -> None:
        await queue.put(
            _sse(
                ev.kind.value,
                {
                    "kind": ev.kind.value,
                    "step": ev.step,
                    "tool": ev.tool,
                    "content": ev.content,
                },
            )
        )

    async def _run():
        result = None
        try:
            async with get_sessionmaker()() as session:
                result = await run_agent(
                    goal,
                    principal=principal,
                    role_name=role,
                    capabilities=set(caps) or None,
                    on_event=on_event,
                    session=session,
                    run_id=run_id,
                )
                result_payload = result.to_dict()
                delivery_summary = _build_stream_delivery_summary(result_payload)
                evidence_records = [
                    {"kind": "request.input", "payload": input_payload},
                    {
                        "kind": "result.final",
                        "payload": _build_stream_result_summary(result_payload),
                    },
                    {"kind": "delivery.generated", "payload": delivery_summary},
                ]
                commit_evidence = _build_commit_evidence(result_payload)
                if commit_evidence is not None:
                    evidence_records.append(commit_evidence)
                await persist_agent_task_record_in_session(
                    session,
                    task_id=result.run_id,
                    run_id=result.run_id,
                    tenant_id=principal.tenant_id,
                    owner_id=principal.user_id,
                    kind="agent.run",
                    backend="stream",
                    status="succeeded",
                    input_payload=input_payload,
                    result_payload=result_payload,
                    delivery_summary=delivery_summary,
                    validation_summary={"risks": []},
                    preview_summary={
                        "final_answer": str(result_payload.get("final_answer") or "")[:160],
                        "steps_count": _build_stream_result_summary(result_payload)["steps_count"],
                    },
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
                try:
                    await persist_evidence_bundle(
                        session,
                        tenant_id=principal.tenant_id,
                        run_id=result.run_id,
                        task_id=result.run_id,
                        records=evidence_records,
                    )
                    await session.commit()
                except Exception as evidence_exc:
                    await session.rollback()
                    if _is_runtime_persistence_schema_mismatch(evidence_exc):
                        await persist_agent_task_record_in_session(
                            session,
                            task_id=result.run_id,
                            run_id=result.run_id,
                            tenant_id=principal.tenant_id,
                            owner_id=principal.user_id,
                            kind="agent.run",
                            backend="stream",
                            status="succeeded",
                            input_payload=input_payload,
                            result_payload=result_payload,
                            delivery_summary=delivery_summary,
                            validation_summary={"risks": []},
                            preview_summary={
                                "final_answer": str(result_payload.get("final_answer") or "")[:160],
                                "steps_count": _build_stream_result_summary(result_payload)[
                                    "steps_count"
                                ],
                            },
                            started_at=started_at,
                            finished_at=datetime.now(UTC),
                        )
                        await session.commit()
                    else:
                        raise
                await queue.put(_sse("done", {"steps": result.steps, "run_id": result.run_id}))
        except Exception as exc:
            if result is not None and _is_runtime_persistence_schema_mismatch(exc):
                await queue.put(_sse("done", {"steps": result.steps, "run_id": result.run_id}))
            else:
                failure_error = str(exc)
                try:
                    async with get_sessionmaker()() as session:
                        failed_result = _build_failure_result_summary(
                            run_id=run_id,
                            error=failure_error,
                            role=role,
                        )
                        failed_delivery = _build_failure_delivery_summary(
                            run_id=run_id,
                            result_summary=failed_result,
                        )
                        await persist_agent_task_record_in_session(
                            session,
                            task_id=run_id,
                            run_id=run_id,
                            tenant_id=principal.tenant_id,
                            owner_id=principal.user_id,
                            kind="agent.run",
                            backend="stream",
                            status="failed",
                            input_payload=input_payload,
                            result_payload=failed_result,
                            error=failure_error,
                            delivery_summary=failed_delivery,
                            validation_summary={"risks": []},
                            preview_summary={"error": failure_error[:160], "steps_count": 0},
                            started_at=started_at,
                            finished_at=datetime.now(UTC),
                        )
                        await persist_evidence_bundle(
                            session,
                            tenant_id=principal.tenant_id,
                            run_id=run_id,
                            task_id=run_id,
                            records=[
                                {"kind": "request.input", "payload": input_payload},
                                {
                                    "kind": "failure.evidence",
                                    "payload": {"error": failure_error, "run_id": run_id},
                                },
                                {"kind": "delivery.generated", "payload": failed_delivery},
                            ],
                        )
                        await session.commit()
                except Exception as exc:
                    logger.warning(
                        "stream_failure_persist_skipped",
                        run_id=run_id,
                        error=str(exc),
                    )
                await queue.put(_sse("error", {"error": failure_error, "run_id": run_id}))
        finally:
            await queue.put(done)

    task = asyncio.create_task(_run())
    try:
        while True:
            item = await queue.get()
            if item is done:
                break
            yield item
    finally:
        if not task.done():
            task.cancel()
    yield _sse("end", {})


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


@router.post("/agents/run", summary="Agent 运行 SSE 流")
async def stream_run(
    body: StreamRunIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(body.goal, principal, body.role, body.capabilities),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
