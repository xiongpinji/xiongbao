"""内置 agent 循环。

策略：在 system prompt 中告知模型可用工具与「动作协议」——若需调用工具，
只输出一行 JSON：{"action":"tool","tool":"<name>","args":{...}}；
若已可作答，输出：{"action":"final","answer":"..."} 或直接自然语言。

解析鲁棒：能从混杂文本里提取 JSON；解析失败/无动作即视为 final（保证终止）。
mock LLM 返回普通文本 -> 第一步即 final，循环安全收敛。
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from xagent.adapters.llm import Message, get_llm_client
from xagent.adapters.observability import get_tracer
from xagent.adapters.tools import get_tool_registry
from xagent.adapters.tools.base import ToolContext
from xagent.core.agents import get_role_registry
from xagent.core.orchestration.state import AgentRun, AgentState, StepEvent, StepKind
from xagent.enterprise.auth.principal import Principal

MAX_STEPS = 6


def _build_system_prompt(role_system: str, tool_specs: list[dict[str, Any]]) -> str:
    lines = [role_system, "", "你可以使用以下工具："]
    for s in tool_specs:
        fn = s["function"]
        lines.append(f"- {fn['name']}: {fn['description']}")
    lines += [
        "",
        "动作协议（严格）：",
        '需要调用工具时，只输出一行 JSON：{"action":"tool","tool":"<名称>","args":{...}}',
        '已能作答时，输出：{"action":"final","answer":"<最终回答>"}',
        "不要输出多余文本。",
    ]
    return "\n".join(lines)


def _extract_action(text: str) -> dict[str, Any] | None:
    """从模型输出中尽力提取动作 JSON。失败返回 None。"""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j == -1 or j <= i:
        return None
    try:
        obj = json.loads(text[i : j + 1])
        return obj if isinstance(obj, dict) and "action" in obj else None
    except Exception:
        return None


def _tool_system_prompt_native(role_system: str, tool_specs: list[dict[str, Any]]) -> str:
    """原生 function-calling 模式下的 system prompt（工具由 API 注入，无需协议说明）。"""
    lines = [role_system, "", "按需调用工具完成任务；已无更多工具可用时直接给出最终回答。"]
    return "\n".join(lines)


async def _handle_prompt_tool_action(
    action: dict[str, Any],
    role,
    tools,
    ctx,
    state: AgentState,
    events: list[StepEvent],
) -> None:
    """提示工程路径：处理 {"action":"tool",...} 动作。"""
    tool_name = action.get("tool", "")
    args = action.get("args", {}) or {}
    events.append(
        StepEvent(kind=StepKind.tool_call, tool=tool_name, content=args, step=state.step)
    )
    if not role.can_use(tool_name):
        result_text = f"[拒绝] 角色 {role.name} 无权使用工具 {tool_name}"
    else:
        result = await tools.call(tool_name, args, ctx)
        result_text = (
            json.dumps(result.output, ensure_ascii=False)
            if result.ok
            else f"[错误] {result.error}"
        )
    events.append(
        StepEvent(
            kind=StepKind.tool_result,
            tool=tool_name,
            content=result_text,
            step=state.step,
        )
    )
    state.messages.append(
        Message(role="user", content=f"工具 {tool_name} 结果：{result_text}")
    )


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
    """运行一次 agent 任务，返回含事件序列的结果。

    on_event: 可选异步回调 (StepEvent) -> None，用于 SSE 实时推送。
    """
    registry = get_role_registry()
    role = (
        registry.get(role_name)
        if role_name
        else registry.match(capabilities or {"general"})
    )
    if role is None:
        role = registry.match({"general"})

    tools = get_tool_registry()
    resolved_run_id = run_id or uuid.uuid4().hex
    # 仅暴露该角色允许的工具
    specs = [s for s in tools.specs() if role.can_use(s["function"]["name"])]

    state = AgentState(
        goal=goal,
        role_name=role.name,
        tenant_id=principal.tenant_id,
        messages=[Message(role="user", content=goal)],
    )
    events: list[StepEvent] = []

    async def _emit(ev: StepEvent) -> None:
        events.append(ev)
        if on_event is not None:
            try:
                await on_event(ev)
            except Exception:  # noqa: S110  回调失败不影响编排
                pass

    llm = get_llm_client()
    tracer = get_tracer()
    ctx = ToolContext(principal=principal, session=session, run_id=resolved_run_id)
    target_model = model or role.preferred_model

    # 选择执行路径：支持原生 function-calling 走工具路径，否则提示工程降级
    use_native_tools = getattr(llm, "supports_tools", False) and bool(specs)
    if use_native_tools:
        system = _tool_system_prompt_native(role.system_prompt, specs)
    else:
        system = _build_system_prompt(role.system_prompt, specs)
    state.messages.insert(0, Message(role="system", content=system))

    async with tracer.trace("agent.run", role=role.name, tenant=principal.tenant_id) as span:
        span.set_input(goal)
        _run_start = time.perf_counter()
        while not state.finished and state.step < MAX_STEPS:
            state.step += 1
            if use_native_tools:
                resp = await llm.complete_with_tools(
                    state.messages, specs, model=target_model
                )
            else:
                resp = await llm.complete(state.messages, model=target_model)

            # 原生工具调用优先；无则尝试提示工程解析（兼容 mock）
            if resp.tool_calls:
                state.messages.append(
                    Message(role="assistant", content=resp.content)
                )
                for tc in resp.tool_calls:
                    await _emit(
                        StepEvent(
                            kind=StepKind.tool_call,
                            tool=tc.name,
                            content=tc.args,
                            step=state.step,
                        )
                    )
                    if not role.can_use(tc.name):
                        result_text = f"[拒绝] 角色 {role.name} 无权使用工具 {tc.name}"
                    else:
                        result = await tools.call(tc.name, tc.args, ctx)
                        result_text = (
                            json.dumps(result.output, ensure_ascii=False)
                            if result.ok
                            else f"[错误] {result.error}"
                        )
                    await _emit(
                        StepEvent(
                            kind=StepKind.tool_result,
                            tool=tc.name,
                            content=result_text,
                            step=state.step,
                        )
                    )
                    state.messages.append(
                        Message(role="user", content=f"工具 {tc.name} 结果：{result_text}")
                    )
                continue

            await _emit(
                StepEvent(kind=StepKind.reason, content=resp.content, step=state.step)
            )
            state.messages.append(Message(role="assistant", content=resp.content))

            action = _extract_action(resp.content)
            if not action or action.get("action") == "final":
                state.final_answer = (
                    action.get("answer", resp.content) if action else resp.content
                )
                state.finished = True
                await _emit(
                    StepEvent(kind=StepKind.final, content=state.final_answer, step=state.step)
                )
                break

            # 提示工程路径的 tool 动作（mock/不支持原生工具时）
            if action.get("action") == "tool":
                _handle_prompt_tool_action(action, role, tools, ctx, state, events)
                continue

            state.final_answer = resp.content
            state.finished = True
            await _emit(StepEvent(kind=StepKind.final, content=resp.content, step=state.step))

        if not state.finished:
            state.final_answer = state.messages[-1].content
            await _emit(
                StepEvent(kind=StepKind.final, content=state.final_answer, step=state.step)
            )
        span.set_output(state.final_answer)
        # Prometheus 指标
        try:
            from xagent.adapters.observability.metrics import agent_run_seconds, agent_runs

            agent_runs.labels(role=role.name).inc()
            agent_run_seconds.labels(role=role.name).observe(time.perf_counter() - _run_start)
        except Exception:  # noqa: S110  指标失败不影响运行
            pass

    return AgentRun(
        run_id=resolved_run_id,
        goal=goal,
        role_name=role.name,
        tenant_id=principal.tenant_id,
        final_answer=state.final_answer,
        steps=state.step,
        events=events,
    )
