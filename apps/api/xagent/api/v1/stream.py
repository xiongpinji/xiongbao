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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from xagent.core.orchestration import run_agent
from xagent.core.orchestration.conversation import get_conversation_manager
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
    conversation_id: str | None = None
    mode: str = Field(
        default="full-auto",
        description="Permission mode: suggest | auto-edit | full-auto",
    )
    strategy: str = Field(
        default="react", description="Execution strategy: react | plan-execute"
    )


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


# Agent 运行最大超时（秒）—— 对标 Codex 云端沙箱 10min 限制
_AGENT_RUN_TIMEOUT = 600


async def _event_stream(
    goal: str, principal: Principal, role: str | None, caps: list[str],
    conversation_id: str | None = None, request: Request | None = None,
    mode: str = "full-auto", strategy: str = "react",
) -> AsyncGenerator[bytes, None]:
    """跑 agent 并把事件逐条以 SSE 实时推送（step 级流式）。"""
    run_id = uuid.uuid4().hex
    resolved_conv_id = conversation_id or uuid.uuid4().hex
    yield _sse(
        "started",
        {
            "goal": goal,
            "run_id": run_id,
            "conversation_id": resolved_conv_id,
            "strategy": strategy,
        },
    )

    # Plan-and-Execute 模式：先生成计划并推送给前端
    if strategy == "plan-execute":
        try:
            from xagent.adapters.llm import get_llm_client
            from xagent.core.orchestration.plan_execute import generate_plan
            llm = get_llm_client()
            from xagent.core.tools import get_registry
            tool_names = list(get_registry().list_names())
            plan = await generate_plan(goal, tool_names, llm)
            yield _sse("plan", {
                "steps": [
                    {
                        "id": s.id,
                        "description": s.description,
                        "tool_hint": s.tool_hint,
                        "depends_on": s.depends_on,
                    }
                    for s in plan.steps
                ],
                "total": len(plan.steps),
            })
            # 将计划注入目标上下文
            plan_ctx = "\n".join(f"{s.id}. {s.description}" for s in plan.steps)
            goal = f"{goal}\n\n[执行计划]\n{plan_ctx}\n请严格按计划逐步执行。"
        except Exception as exc:
            logger.debug("plan_generate_failed", error=str(exc))
            yield _sse("plan", {"steps": [], "total": 0, "error": str(exc)})

    queue: asyncio.Queue = asyncio.Queue()
    done = object()
    input_payload = _build_input_payload(goal, role, caps)
    started_at = datetime.now(UTC)

    async def on_event(ev) -> None:
        _payload = {
            "kind": ev.kind.value,
            "step": ev.step,
            "tool": ev.tool,
            "content": ev.content,
        }
        if getattr(ev, 'trace_id', ''):
            _payload["trace_id"] = ev.trace_id
        await queue.put(_sse(ev.kind.value, _payload))

    async def _run():
        result = None
        try:
            async with get_sessionmaker()() as session:
                result = await asyncio.wait_for(
                    run_agent(
                        goal,
                        principal=principal,
                        role_name=role,
                        capabilities=set(caps) or None,
                        on_event=on_event,
                        session=session,
                        run_id=run_id,
                        conversation_id=resolved_conv_id,
                        permission_mode=mode,
                    ),
                    timeout=_AGENT_RUN_TIMEOUT,
                )
                if result.status != "succeeded":
                    raise RuntimeError(result.error or f"agent_run_{result.status}")
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
                await queue.put(_sse("done", {
                    "steps": result.steps, "run_id": result.run_id,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                }))
                # Webhook 通知
                try:
                    from xagent.core.webhooks import get_webhook_manager
                    await get_webhook_manager().emit(
                        principal.tenant_id, "agent.completed",
                        {"run_id": run_id, "goal": goal[:200], "steps": result.steps},
                    )
                except Exception:  # noqa: S110
                    pass
        except TimeoutError:
            failure_error = f"Agent 运行超时（>{_AGENT_RUN_TIMEOUT}s），已自动终止。"
            await queue.put(_sse("error", {"error": failure_error, "run_id": run_id}))
        except Exception as exc:
            if result is not None and _is_runtime_persistence_schema_mismatch(exc):
                await queue.put(_sse("done", {
                    "steps": result.steps, "run_id": result.run_id,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                }))
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
    heartbeat_interval = 15  # 每 15s 发一次心跳防代理超时
    last_heartbeat = asyncio.get_running_loop().time()
    try:
        while True:
            # 检测客户端断连（对标 Codex 沙箱中断机制）
            if request and await request.is_disconnected():
                logger.info("sse_client_disconnected", run_id=run_id)
                break
            try:
                item = await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                # SSE 心跳：防止 nginx/负载均衡器超时断开
                now = asyncio.get_running_loop().time()
                if now - last_heartbeat >= heartbeat_interval:
                    yield b": heartbeat\n\n"
                    last_heartbeat = now
                continue
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
    request: Request,
    principal: Principal = Depends(require_permission("agent", "execute")),
) -> StreamingResponse:
    if body.conversation_id:
        from xagent.core.orchestration.conversation import load_conversation_from_db

        async with get_sessionmaker()() as session:
            try:
                await load_conversation_from_db(
                    session, principal.tenant_id, body.conversation_id
                )
            except LookupError as exc:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, "对话不存在或无权访问"
                ) from exc
    return StreamingResponse(
        _event_stream(
            body.goal,
            principal,
            body.role,
            body.capabilities,
            body.conversation_id,
            request,
            body.mode,
            body.strategy,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", summary="列出对话历史")
async def list_conversations(
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    from xagent.core.orchestration.conversation import load_conversations_from_db

    async with get_sessionmaker()() as session:
        conversations = await load_conversations_from_db(session, principal.tenant_id)
    # 合并内存缓存中未持久化的新会话
    mgr = get_conversation_manager()
    cached = mgr.list_sessions(principal.tenant_id)
    db_ids = {c["conversation_id"] for c in conversations}
    for c in cached:
        if c["conversation_id"] not in db_ids:
            conversations.append(c)
    conversations.sort(key=lambda x: x.get("last_active", 0), reverse=True)
    return {"conversations": conversations[:50]}


@router.get("/conversations/{conversation_id}/messages", summary="加载对话消息")
async def get_conversation_messages(
    conversation_id: str,
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    from xagent.core.orchestration.conversation import load_conversation_from_db

    async with get_sessionmaker()() as session:
        try:
            conversation = await load_conversation_from_db(
                session, principal.tenant_id, conversation_id
            )
        except LookupError as exc:
            mgr = get_conversation_manager()
            sess = mgr.get(conversation_id, principal.tenant_id)
            if sess:
                return {
                    "messages": [
                        {"role": m.role, "content": m.content} for m in sess.messages
                    ]
                }
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "对话不存在或无权访问"
            ) from exc
        if conversation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "对话不存在或无权访问")
        return {
            "messages": [
                {"role": item.role, "content": item.content}
                for item in conversation.messages
            ]
        }


@router.delete("/conversations/{conversation_id}", summary="删除对话")
async def delete_conversation(
    conversation_id: str,
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    from xagent.core.orchestration.conversation import delete_conversation_from_db

    async with get_sessionmaker()() as session:
        deleted = await delete_conversation_from_db(
            session, principal.tenant_id, conversation_id
        )
        await session.commit()
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "对话不存在或无权访问")
    mgr = get_conversation_manager()
    mgr.delete(conversation_id, principal.tenant_id)
    return {"deleted": deleted}


# ═══════════════════════════════════════════════════════════
#  并行执行 API（对标 Codex 多文件并行编辑）
# ═══════════════════════════════════════════════════════════


class ParallelRunIn(BaseModel):
    goal: str = Field(..., min_length=1)
    role: str | None = None


@router.post("/agents/parallel-run", summary="并行执行（自动分解子任务）")
async def parallel_run(
    body: ParallelRunIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    """智能判断是否适合并行，如果是则自动分解并并行执行子任务。"""
    from xagent.core.orchestration.parallel import auto_decompose_and_run

    result = await auto_decompose_and_run(body.goal, principal)
    if result is None:
        return {
            "parallel": False,
            "message": "任务不适合并行执行，请使用普通 /agents/run 端点",
        }
    return {
        "parallel": True,
        "run_id": result.run_id,
        "status": result.status,
        "summary": result.summary,
        "sub_tasks": len(result.sub_results),
        "total_duration_ms": result.total_duration_ms,
        "sub_results": [
            {"run_id": r.run_id, "status": r.status, "final_answer": r.final_answer[:200]}
            for r in result.sub_results
        ],
    }
