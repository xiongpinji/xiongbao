"""DeerFlow 2.0 编排适配器（替代纯 LangGraph）。

DeerFlow 是字节跳动开源的超级智能体框架（72k★ MIT），基于 LangGraph 构建，
内置子 agent 并行 + 沙箱 + 记忆 + 技能系统 + IM 通道。

本适配器把 DeerFlowClient 封装为 X-Agent 的编排后端：
- run_agent() 走 DeerFlow 的 chat/stream 接口
- 未安装/未配置时回退到 LangGraph 或内置循环
"""

from __future__ import annotations

import uuid
from typing import Any

from xagent.core.orchestration.state import AgentRun, StepEvent, StepKind
from xagent.enterprise.auth.principal import Principal
from xagent.infra.logging import get_logger

logger = get_logger("xagent.deerflow")


def _has_deerflow() -> bool:
    try:
        from deerflow.client import DeerFlowClient  # noqa: F401

        return True
    except ImportError:
        return False


async def run_agent_deerflow(
    goal: str,
    *,
    principal: Principal,
    role_name: str | None = None,
    capabilities: set[str] | None = None,
    model: str | None = None,
    on_event: Any = None,
    session: Any = None,
    run_id: str | None = None,
) -> AgentRun:
    """用 DeerFlow 2.0 跑 agent（与 run_agent 相同签名）。"""
    from deerflow.client import DeerFlowClient

    client = DeerFlowClient()
    resolved_run_id = run_id or uuid.uuid4().hex
    thread_id = f"xagent-{principal.tenant_id}-{resolved_run_id[:8]}"

    events: list[StepEvent] = []
    final_answer = ""

    # 用 stream 获取实时事件
    try:
        for event in client.stream(goal, thread_id=thread_id):
            event_type = getattr(event, "type", "")
            data = getattr(event, "data", {})

            if event_type == "messages-tuple":
                msg_type = data.get("type", "")
                content = data.get("content", "")

                if msg_type == "ai":
                    step = len(events) + 1
                    ev = StepEvent(
                        kind=StepKind.reason, content=content, step=step
                    )
                    events.append(ev)
                    if on_event:
                        await on_event(ev)
                    final_answer = content
                elif msg_type == "tool":
                    step = len(events) + 1
                    tool_name = data.get("name", "unknown")
                    ev = StepEvent(
                        kind=StepKind.tool_call, tool=tool_name,
                        content=data.get("input", {}), step=step,
                    )
                    events.append(ev)
                    if on_event:
                        await on_event(ev)

            elif event_type == "end":
                step = len(events) + 1
                ev = StepEvent(
                    kind=StepKind.final, content=final_answer, step=step
                )
                events.append(ev)
                if on_event:
                    await on_event(ev)

    except Exception as exc:
        logger.warning("deerflow_stream_failed", error=str(exc))
        # 降级：用 chat 一次性获取
        try:
            response = client.chat(goal, thread_id=thread_id)
            final_answer = (
                response.get("content", "")
                if isinstance(response, dict)
                else str(response)
            )
            events.append(StepEvent(
                kind=StepKind.final, content=final_answer, step=1
            ))
        except Exception as exc2:
            logger.error("deerflow_chat_failed", error=str(exc2))
            final_answer = f"[DeerFlow 错误] {exc2}"
            events.append(StepEvent(
                kind=StepKind.error, content=str(exc2), step=1
            ))

    return AgentRun(
        run_id=resolved_run_id,
        goal=goal,
        role_name=role_name or "deerflow",
        tenant_id=principal.tenant_id,
        final_answer=final_answer,
        steps=len(events),
        events=events,
    )