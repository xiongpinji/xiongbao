"""LangGraph 状态图编排循环（替代内置 loop.py）。

用 LangGraph StateGraph 实现 agent 状态机：
  reason → (tool_call → tool_result)* → final

保持与 loop.py 相同的输入输出契约（run_agent 签名不变），
通过 settings/环境变量控制走 LangGraph 还是内置循环。
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from xagent.adapters.llm import Message, get_llm_client
from xagent.adapters.observability import get_tracer
from xagent.adapters.tools import get_tool_registry
from xagent.adapters.tools.base import ToolContext
from xagent.core.agents import get_role_registry
from xagent.core.orchestration.state import (
    RUN_STATUS_FAILED,
    RUN_STATUS_SUCCEEDED,
    AgentRun,
    StepEvent,
    StepKind,
)
from xagent.enterprise.auth.principal import Principal

MAX_STEPS = 6


class GraphState(TypedDict):
    """LangGraph 节点间传递的状态。"""

    messages: list[dict]
    events: list[dict]
    step: int
    finished: bool
    final_answer: str
    role_name: str
    tenant_id: str
    goal: str


def _build_graph(
    role, tools_registry, specs: list[dict], ctx: ToolContext, llm, target_model: str | None,
) -> StateGraph:
    """构建 LangGraph 状态图。"""

    async def reason_node(state: GraphState) -> GraphState:
        """LLM 推理节点。"""
        msgs = [Message(role=m["role"], content=m["content"]) for m in state["messages"]]
        if llm.supports_tools and specs:
            resp = await llm.complete_with_tools(msgs, specs, model=target_model)
        else:
            resp = await llm.complete(msgs, model=target_model)

        state["step"] += 1
        events = list(state["events"])

        # 原生工具调用
        if resp.tool_calls:
            state["messages"].append({"role": "assistant", "content": resp.content})
            for tc in resp.tool_calls:
                events.append({"kind": "tool_call", "tool": tc.name, "content": tc.args, "step": state["step"]})
                if not role.can_use(tc.name):
                    result_text = f"[拒绝] 角色 {role.name} 无权使用工具 {tc.name}"
                else:
                    result = await tools_registry.call(tc.name, tc.args, ctx)
                    result_text = json.dumps(result.output, ensure_ascii=False) if result.ok else f"[错误] {result.error}"
                events.append({"kind": "tool_result", "tool": tc.name, "content": result_text, "step": state["step"]})
                state["messages"].append({"role": "user", "content": f"工具 {tc.name} 结果：{result_text}"})
            state["events"] = events
            return state

        # 提示工程降级（无 tool_calls）
        events.append({"kind": "reason", "content": resp.content, "step": state["step"]})
        state["messages"].append({"role": "assistant", "content": resp.content})

        # 解析动作 JSON
        action = _extract_action(resp.content)
        if not action or action.get("action") == "final":
            state["final_answer"] = action.get("answer", resp.content) if action else resp.content
            state["finished"] = True
            events.append({"kind": "final", "content": state["final_answer"], "step": state["step"]})
        elif action.get("action") == "tool":
            tool_name = action.get("tool", "")
            args = action.get("args", {}) or {}
            events.append({"kind": "tool_call", "tool": tool_name, "content": args, "step": state["step"]})
            if not role.can_use(tool_name):
                result_text = f"[拒绝] 角色 {role.name} 无权使用工具 {tool_name}"
            else:
                result = await tools_registry.call(tool_name, args, ctx)
                result_text = json.dumps(result.output, ensure_ascii=False) if result.ok else f"[错误] {result.error}"
            events.append({"kind": "tool_result", "tool": tool_name, "content": result_text, "step": state["step"]})
            state["messages"].append({"role": "user", "content": f"工具 {tool_name} 结果：{result_text}"})
        else:
            state["final_answer"] = resp.content
            state["finished"] = True
            events.append({"kind": "final", "content": resp.content, "step": state["step"]})

        state["events"] = events
        return state

    def should_continue(state: GraphState) -> str:
        """条件边：是否继续循环。"""
        if state["finished"] or state["step"] >= MAX_STEPS:
            return "end"
        return "reason"

    # 构建图
    graph = StateGraph(GraphState)
    graph.add_node("reason", reason_node)
    graph.set_entry_point("reason")
    graph.add_conditional_edges("reason", should_continue, {"reason": "reason", "end": END})
    return graph


def _extract_action(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j == -1 or j <= i:
        return None
    try:
        obj = json.loads(text[i: j + 1])
        return obj if isinstance(obj, dict) and "action" in obj else None
    except Exception:  # noqa: S110
        return None


async def run_agent_langgraph(
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
    """用 LangGraph 状态图跑 agent（与 loop.run_agent 相同签名）。"""
    registry = get_role_registry()
    role = (
        registry.get(role_name) if role_name
        else registry.match(capabilities or {"general"})
    )
    if role is None:
        role = registry.match({"general"})

    tools = get_tool_registry()
    resolved_run_id = run_id or uuid.uuid4().hex
    specs = [s for s in tools.specs() if role.can_use(s["function"]["name"])]
    ctx = ToolContext(principal=principal, session=session, run_id=resolved_run_id)
    llm = get_llm_client()
    tracer = get_tracer()
    target_model = model or role.preferred_model

    # system prompt
    system = f"{role.system_prompt}\n\n按需调用工具完成任务；已无更多工具可用时直接给出最终回答。"

    graph = _build_graph(role, tools, specs, ctx, llm, target_model)
    app = graph.compile()

    initial_state: GraphState = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": goal},
        ],
        "events": [],
        "step": 0,
        "finished": False,
        "final_answer": "",
        "role_name": role.name,
        "tenant_id": principal.tenant_id,
        "goal": goal,
    }

    _run_start = time.perf_counter()
    async with tracer.trace("agent.run.langgraph", role=role.name, tenant=principal.tenant_id) as span:
        span.set_input(goal)
        final_state = await app.ainvoke(initial_state)
        span.set_output(final_state["final_answer"])

    # Prometheus 指标
    try:
        from xagent.adapters.observability.metrics import agent_run_seconds, agent_runs
        agent_runs.labels(role=role.name).inc()
        agent_run_seconds.labels(role=role.name).observe(time.perf_counter() - _run_start)
    except Exception:  # noqa: S110
        pass

    # 触发 on_event 回调
    events = [
        StepEvent(kind=StepKind(e["kind"]), tool=e.get("tool"), content=e.get("content"), step=e.get("step", 0))
        for e in final_state["events"]
    ]
    if on_event:
        for ev in events:
            try:
                await on_event(ev)
            except Exception:  # noqa: S110
                pass

    # 步数上限兜底
    final_answer = final_state["final_answer"]
    if not final_answer and final_state["messages"]:
        final_answer = final_state["messages"][-1].get("content", "")
    succeeded = final_state["finished"] is True
    error = ""
    if not succeeded:
        error = (
            "max_steps_exceeded"
            if final_state["step"] >= MAX_STEPS
            else "incomplete_run"
        )

    return AgentRun(
        run_id=resolved_run_id,
        goal=goal,
        role_name=role.name,
        tenant_id=principal.tenant_id,
        final_answer=final_answer,
        steps=final_state["step"],
        events=events,
        status=RUN_STATUS_SUCCEEDED if succeeded else RUN_STATUS_FAILED,
        error=error,
    )
