"""编排：agent 状态机循环（observe → reason → act → reflect）。

优先级（按环境变量控制）：
  XAGENT_USE_DEERFLOW=true → DeerFlow 2.0（超级智能体框架，需完整运行时）
  XAGENT_USE_LANGGRAPH=true → LangGraph 状态图
  默认 → 内置循环（离线/lite/CI 可用）
对外只暴露 ``run_agent``，调用方无感。
"""

from __future__ import annotations

import os
from typing import Any

from xagent.core.orchestration.state import AgentRun, AgentState, StepEvent
from xagent.enterprise.auth.principal import Principal


def _has_deerflow() -> bool:
    if os.environ.get("XAGENT_USE_DEERFLOW", "").lower() != "true":
        return False
    try:
        from deerflow.client import DeerFlowClient  # noqa: F401
        return True
    except ImportError:
        return False


def _has_langgraph() -> bool:
    try:
        from langgraph.graph import StateGraph  # noqa: F401
        return True
    except ImportError:
        return False


async def run_agent(
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
    """运行一次 agent 任务。DeerFlow(opt-in) > LangGraph > 内置循环。"""
    if _has_deerflow():
        from xagent.core.orchestration.deerflow_loop import run_agent_deerflow
        return await run_agent_deerflow(
            goal, principal=principal, role_name=role_name,
            capabilities=capabilities, model=model, on_event=on_event,
            session=session, run_id=run_id,
        )
    if _has_langgraph():
        from xagent.core.orchestration.langgraph_loop import run_agent_langgraph
        return await run_agent_langgraph(
            goal, principal=principal, role_name=role_name,
            capabilities=capabilities, model=model, on_event=on_event,
            session=session, run_id=run_id,
        )
    from xagent.core.orchestration.loop import run_agent as run_agent_builtin
    return await run_agent_builtin(
        goal, principal=principal, role_name=role_name,
        capabilities=capabilities, model=model, on_event=on_event,
        session=session, run_id=run_id,
    )


__all__ = ["AgentRun", "AgentState", "StepEvent", "run_agent"]
