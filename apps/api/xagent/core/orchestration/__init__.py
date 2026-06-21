"""编排：agent 状态机循环（observe → reason → act → reflect）。

LangGraph 已安装时走 LangGraph 状态图（生产推荐）；
未安装时回退内置循环（离线/lite/CI 可用）。
对外只暴露 ``run_agent``，调用方无感。
"""

from __future__ import annotations

from typing import Any

from xagent.core.orchestration.state import AgentRun, AgentState, StepEvent
from xagent.enterprise.auth.principal import Principal


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
) -> AgentRun:
    """运行一次 agent 任务。LangGraph 可用走图执行，否则内置循环。"""
    if _has_langgraph():
        from xagent.core.orchestration.langgraph_loop import run_agent_langgraph

        return await run_agent_langgraph(
            goal,
            principal=principal,
            role_name=role_name,
            capabilities=capabilities,
            model=model,
            on_event=on_event,
        )
    from xagent.core.orchestration.loop import run_agent as run_agent_builtin

    return await run_agent_builtin(
        goal,
        principal=principal,
        role_name=role_name,
        capabilities=capabilities,
        model=model,
        on_event=on_event,
    )


__all__ = ["AgentRun", "AgentState", "StepEvent", "run_agent"]
