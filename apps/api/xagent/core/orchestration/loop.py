"""内置 agent 循环。

策略：在 system prompt 中告知模型可用工具与「动作协议」——若需调用工具，
只输出一行 JSON：{"action":"tool","tool":"<name>","args":{...}}；
若已可作答，输出：{"action":"final","answer":"..."} 或直接自然语言。

解析鲁棒：能从混杂文本里提取 JSON；解析失败/无动作即视为 final（保证终止）。
mock LLM 返回普通文本 -> 第一步即 final，循环安全收敛。
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from xagent.adapters.llm import Message, get_llm_client
from xagent.adapters.llm.litellm_client import LiteLLMClient, StreamChunk
from xagent.adapters.observability import get_tracer
from xagent.adapters.tools import get_tool_registry
from xagent.adapters.tools.base import ToolContext
from xagent.core.agents import get_role_registry
from xagent.core.orchestration.conversation import get_conversation_manager
from xagent.core.orchestration.state import AgentRun, AgentState, StepEvent, StepKind
from xagent.enterprise.auth.principal import Principal

MAX_STEPS = 40
_WORKSPACE = Path(os.environ.get("XAGENT_WORKSPACE", Path.home() / "xagent_workspace"))


def _load_agents_md() -> str:
    """Load AGENTS.md project instructions (Codex-aligned).

    Searches workspace root and common locations for AGENTS.md,
    returns content to inject into system prompt.
    """
    candidates = [
        _WORKSPACE / "AGENTS.md",
        _WORKSPACE / "agents.md",
        _WORKSPACE / ".agents" / "AGENTS.md",
        Path.cwd() / "AGENTS.md",
    ]
    for p in candidates:
        try:
            if p.is_file():
                content = p.read_text(encoding="utf-8").strip()
                if content:
                    return content[:3000]  # cap at 3000 chars
        except OSError:
            continue
    return ""


async def _compress_context(messages: list[Message], llm, model: str | None) -> list[Message]:
    """Context compression: summarize old messages when conversation is too long.

    Codex-aligned: prevents context window overflow on long tasks.
    Keeps system + last N messages intact, compresses middle history.
    """
    # Only compress if messages exceed threshold
    if len(messages) <= 20:
        return messages

    # Keep: system (first) + last 10 messages
    system_msg = messages[0] if messages[0].role == "system" else None
    keep_tail = 10
    start_idx = 1 if system_msg else 0
    end_idx = len(messages) - keep_tail

    if end_idx <= start_idx + 4:  # not enough to compress
        return messages

    # Build summary of middle section
    middle = messages[start_idx:end_idx]
    middle_text = "\n".join(
        f"{m.role}: {m.content[:200]}" for m in middle if m.content
    )[:4000]

    summary_prompt = (
        "Summarize the following conversation history into a concise context block. "
        "Focus on: what tools were called, what files were created/modified, "
        "what errors occurred, and current progress. Max 500 words.\n\n"
        + middle_text
    )

    try:
        resp = await llm.complete(
            [Message(role="user", content=summary_prompt)], model=model
        )
        summary = (resp.content or "").strip()
        if summary and len(summary) > 50:
            compressed = Message(
                role="user",
                content=f"[Context Summary - {len(middle)} messages compressed]\n{summary}",
            )
            result = []
            if system_msg:
                result.append(system_msg)
            result.append(compressed)
            result.extend(messages[end_idx:])
            return result
    except Exception:
        pass

    return messages


async def _retrieve_relevant_memories(goal: str, tenant_id: str) -> str:
    """检索与当前目标相关的记忆，返回拼接文本（空则无记忆）。"""
    try:
        from xagent.adapters.memory import get_vector_store

        hits = await get_vector_store().search(goal, top_k=3, tenant_id=tenant_id)
        if not hits:
            return ""
        lines = [f"- {h.text}" for h in hits if h.score > 0.3]
        return "\n".join(lines)
    except Exception:  # noqa: S110  记忆检索失败不影响主流程
        return ""


async def _save_to_memory(goal: str, answer: str, tenant_id: str) -> None:
    """将重要的 Q&A 对自动写入记忆库。"""
    try:
        import uuid as _uuid

        from xagent.adapters.memory import MemoryRecord, get_vector_store

        # 只保存有实质内容的回复（超过 20 字符）
        if len(answer) < 20:
            return
        record = MemoryRecord(
            id=f"conv_{_uuid.uuid4().hex[:12]}",
            text=f"用户: {goal[:200]}\n助手: {answer[:500]}",
            metadata={"tenant_id": tenant_id, "source": "auto_conversation"},
        )
        await get_vector_store().upsert([record])
    except Exception:  # noqa: S110
        pass


async def _auto_extract_skill(
    goal: str, answer: str, steps_count: int, events: list[StepEvent]
) -> None:
    """任务完成后自动提炼可复用技能（Skill 自进化核心）。

    触发条件：
    - 任务步数 >= 3（复杂任务）
    - 回答有实质内容
    - 无已有高效技能覆盖此场景
    """
    try:
        from xagent.core.skills import get_skill_store

        # 提取使用过的工具列表
        tools_used = [
            e.content.split("(")[0].strip()
            for e in events
            if e.kind == StepKind.tool_call and e.content
        ]
        store = get_skill_store()
        await store.auto_extract(
            goal=goal,
            answer=answer,
            steps_count=steps_count,
            tools_used=tools_used or None,
        )
    except Exception as _sk_exc:  # noqa: S110  技能提炼失败不影响主流程
        from xagent.infra.logging import get_logger as _gl
        _gl("xagent.skills").debug("auto_extract_failed", error=str(_sk_exc))


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


def _is_tool_echo(text: str) -> bool:
    """检测 LLM 输出是否为工具结果的原样复述。"""
    t = text.strip()
    if not t:
        return False
    if t.startswith("工具 ") and "结果：" in t[:80]:
        return True
    if t.startswith("[参考数据"):
        return True
    if t.startswith("{") and '"total_count"' in t[:200]:
        return True
    return False


def _detect_final_answer(content: str, state: AgentState) -> bool:
    """智能判断 LLM 输出是否为真正的最终回答。

    策略：综合多个信号判断，避免误判中间规划为最终回答。
    """
    text = content.strip()
    if not text:
        return True  # 空内容视为终止（由 _handle_empty_or_echo 处理）

    # ── 信号 1：包含询问用户的问句 → 中间态 ──
    _ASK_PATTERNS = (
        "要继续吗", "需要我继续", "你想从", "是否继续",
        "需要我进一步", "告诉我目标", "请确认",
        "哪一项", "哪个方向", "你希望",
    )
    if any(p in text for p in _ASK_PATTERNS):
        return False

    # ── 信号 2：包含“接下来/下一步”等继续信号且无测试结果 → 中间态 ──
    _CONTINUE_WORDS = (
        "接下来", "下一步", "现在并行", "然后我将", "准备创建",
        "开始写", "开始创建", "现在完成", "现在执行",
    )
    has_continue = any(w in text for w in _CONTINUE_WORDS)

    # ── 信号 3：包含测试结果/完成总结 → 最终态 ──
    _FINAL_EVIDENCE = (
        "passed", "failed", "测试通过", "测试失败",
        "全部完成", "所有测试通过", "所有子任务已完成",
        "项目完成总结", "开发完成", "✅ 全部",
        "exit code: 0", "RETURNCODE: 0",
    )
    has_final_evidence = any(e in text for e in _FINAL_EVIDENCE)

    # ── 信号 4：工具调用历史 — 如果之前有工具调用，纯文本更可能是中间态 ──
    # 检查消息历史中是否有工具结果（说明之前在执行工具）
    recent_tool_results = sum(
        1 for m in state.messages[-10:]
        if m.role == "user" and m.content.startswith("[参考数据")
    )
    has_recent_tools = recent_tool_results > 0

    # ── 综合判断 ──
    # 规则 1：有明确完成证据 → 最终
    if has_final_evidence and not has_continue:
        return True
    # 规则 2：有继续信号 → 中间
    if has_continue:
        return False
    # 规则 3：有询问 → 中间
    # (已在上面处理)
    # 规则 4：之前有工具调用 + 文本较短(<800字) + 无完成证据 → 中间
    if has_recent_tools and len(text) < 800 and not has_final_evidence:
        return False
    # 规则 5：步数很少(<3)且无完成证据 → 可能是第一轮分析，允许终止
    #   但如果用户 goal 含多个子任务（数字列表），则不允许
    if state.step <= 2 and not has_final_evidence:
        # 检查 goal 是否含多步骤
        goal = ""
        for m in state.messages:
            if m.role == "user" and not m.content.startswith("["):
                goal = m.content
                break
        multi_step = bool(re.search(r'[1-9]\)', goal)) or goal.count("、") >= 2
        if multi_step:
            return False
    # 默认：允许终止
    return True


async def _handle_empty_or_echo(
    content_buf: str,
    state: AgentState,
    llm,
    target_model: str | None,
) -> str:
    """处理 LLM 返回空内容或回显工具结果的情况，返回修正后的内容。"""
    if _is_tool_echo(content_buf):
        state.messages.append(Message(role="assistant", content=content_buf))
        state.messages.append(Message(
            role="user",
            content=(
                "[指令] 你刚才只是复述了工具的原始返回数据，这不是合格的回答。"
                "请你现在基于这些数据，用你自己的语言写一份结构化的分析/总结/方案。"
                "要求：1)不要出现'工具xx结果'字样 2)提炼关键信息 3)给出结论或建议。"
            ),
        ))
        try:
            retry_resp = await llm.complete(state.messages, model=target_model)
            content_buf = retry_resp.content or ""
        except Exception:
            content_buf = ""
        if _is_tool_echo(content_buf):
            content_buf = ""

    if not content_buf.strip():
        state.messages.append(Message(
            role="user",
            content=(
                "[系统提示] 请基于已有的工具执行结果和你的知识，"
                "尽可能回答用户的问题。不要原样复述工具结果，要综合分析。"
            ),
        ))
        try:
            retry_resp = await llm.complete(state.messages, model=target_model)
            content_buf = retry_resp.content or ""
        except Exception:
            content_buf = ""
        if not content_buf.strip():
            content_buf = (
                "我已尝试获取相关信息，但受限于页面动态渲染或工具调用次数，"
                "未能获取完整内容。\n\n"
                "建议：\n"
                "1. 请告诉我该网站/项目的具体功能，我可以帮你分析\n"
                "2. 如果有 GitHub 仓库地址，我可以查看 README\n"
                "3. 如果有 API 文档链接，我可以获取更详细的信息"
            )
    return content_buf


def _tool_system_prompt_native(role_system: str, tool_specs: list[dict[str, Any]]) -> str:
    """原生 function-calling 模式下的 system prompt（工具由 API 注入，无需协议说明）。"""
    lines = [
        role_system,
        "",
        "## 核心行为准则（必须严格遵守）",
        "1. **行动优先**：当用户要求开发/创建/修复/执行时，直接调用工具执行，不要先写分析报告再问用户确认。",
        "2. **少说多做**：每轮回复中，工具调用应占主导。文字只用于简短说明你正在做什么（1-2句），不要写长篇分析。",
        "3. **绝对禁止中途停止**：在用户的所有子任务全部完成之前，绝对禁止：",
        "   - 问用户“要继续吗？”“需要我继续推进哪一项？”“你想从哪里开始？”",
        "   - 输出中间规划/待办列表然后等待用户指令",
        "   - 说“接下来我将...”然后不调用工具",
        "   你必须自己判断下一步并立即执行，直到全部完成。",
        "4. **连续执行**：完成一步后立即执行下一步，中间不要停顿。",
        "5. **文件操作**：创建/修改代码文件时，直接用 file_write 工具写入完整内容，不要把代码贴在回复里让用户复制。",
        "6. **命令执行**：需要安装依赖/启动服务/运行测试时，直接用 shell_exec 执行，不要给用户“手动操作指南”。",
        "7. **完成标准**：只有当用户要求的所有子任务都已执行完毕（文件已创建、测试已运行、结果已确认）后，才可以输出最终总结。最终总结必须包含“全部完成”或测试结果。",
        "",
        "## 工具使用规则",
        "1. 按需调用工具完成任务；已无更多工具可用时直接给出最终回答。",
        "2. **禁止原样复述工具返回的原始结果**。你必须对工具结果进行分析、总结、提炼，用你自己的语言回答用户。",
        "3. 如果工具未能获取有效信息，基于已有信息合理推断并给出建议。",
        "4. 最终回答应该是结构化的分析/方案/总结，而不是工具日志的复制粘贴。",
    ]
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
        Message(role="user", content=f"[参考数据 | {tool_name}]\n{result_text}")
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
    conversation_id: str | None = None,
    permission_mode: str = "full-auto",
) -> AgentRun:
    """运行一次 agent 任务，返回含事件序列的结果。

    on_event: 可选异步回调 (StepEvent) -> None，用于 SSE 实时推送。
    conversation_id: 会话 ID，传入则启用多轮对话。
    permission_mode: 权限模式 (suggest | auto-edit | full-auto)。
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

    # ── 多轮对话：加载历史 ──
    conv_mgr = get_conversation_manager()
    conv_session = conv_mgr.get_or_create(conversation_id, principal.tenant_id)
    history = conv_session.get_history(max_turns=8)

    # ── 自动记忆注入：检索相关记忆 ──
    memory_context = await _retrieve_relevant_memories(goal, principal.tenant_id)

    # 构建消息列表：system + 历史 + 当前 goal
    messages: list[Message] = []
    # 历史消息放在 goal 之前
    messages.extend(history)
    messages.append(Message(role="user", content=goal))

    state = AgentState(
        goal=goal,
        role_name=role.name,
        tenant_id=principal.tenant_id,
        messages=messages,
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
    # 注入记忆上下文
    if memory_context:
        system += f"\n\n相关记忆（供参考）：\n{memory_context}"
    # 注入 AGENTS.md 项目指令（Codex 对齐）
    agents_md = _load_agents_md()
    if agents_md:
        system += f"\n\n## 项目指令 (AGENTS.md)\n{agents_md}"
    # 注入权限模式说明（Codex 对齐）
    _MODE_DESC = {
        "suggest": "\n\n## 权限模式: suggest\n你只能建议代码修改，不能直接执行文件写入或 shell 命令。输出建议让用户确认。",
        "auto-edit": "\n\n## 权限模式: auto-edit\n你可以直接读写文件，但执行 shell 命令前应说明意图。",
        "full-auto": "",  # 默认模式，无额外限制
    }
    system += _MODE_DESC.get(permission_mode, "")
    # 注入匹配的技能（Skill 系统）
    try:
        from xagent.core.skills import get_skill_store
        skill_hint = get_skill_store().build_prompt_injection(goal)
        if skill_hint:
            system += f"\n\n{skill_hint}"
    except Exception:  # noqa: S110
        pass
    state.messages.insert(0, Message(role="system", content=system))

    async with tracer.trace("agent.run", role=role.name, tenant=principal.tenant_id) as span:
        span.set_input(goal)
        _run_start = time.perf_counter()
        # 判断是否支持流式
        can_stream = isinstance(llm, LiteLLMClient) and use_native_tools

        try:
            while not state.finished and state.step < MAX_STEPS:
              state.step += 1

              # 上下文压缩：每 10 步检查一次，防止上下文窗口溢出
              if state.step % 10 == 0 and len(state.messages) > 20:
                  state.messages = await _compress_context(
                      state.messages, llm, target_model
                  )

              if can_stream:
                  # ── 流式路径：逐 token 推送 ──
                  content_buf = ""
                  tool_calls_buf: dict[int, dict] = {}  # index -> {id, name, arguments}

                  async for chunk in llm.stream_with_tools(
                      state.messages, specs, model=target_model
                  ):
                      # 累积 content
                      if chunk.delta_content:
                          content_buf += chunk.delta_content
                          await _emit(
                              StepEvent(kind=StepKind.token, content=chunk.delta_content, step=state.step)
                          )
                      # 累积 tool_call deltas
                      for tc_delta in chunk.tool_call_deltas:
                          idx = tc_delta.get("index", 0)
                          if idx not in tool_calls_buf:
                              tool_calls_buf[idx] = {"id": "", "name": "", "arguments": ""}
                          fn = tc_delta.get("function") or {}
                          if tc_delta.get("id"):
                              tool_calls_buf[idx]["id"] = tc_delta["id"]
                          if fn.get("name"):
                              tool_calls_buf[idx]["name"] += fn["name"]
                          if fn.get("arguments"):
                              tool_calls_buf[idx]["arguments"] += fn["arguments"]

                  # 流结束：判断是工具调用还是最终回答
                  if tool_calls_buf:
                      state.messages.append(Message(role="assistant", content=content_buf or ""))
                      for _idx in sorted(tool_calls_buf.keys()):
                          tc_raw = tool_calls_buf[_idx]
                          tc_name = tc_raw["name"]
                          try:
                              tc_args = json.loads(tc_raw["arguments"] or "{}")
                          except Exception:
                              tc_args = {}
                          await _emit(
                              StepEvent(kind=StepKind.tool_call, tool=tc_name, content=tc_args, step=state.step)
                          )
                          if not role.can_use(tc_name):
                              result_text = f"[拒绝] 角色 {role.name} 无权使用工具 {tc_name}"
                          else:
                              result = await tools.call(tc_name, tc_args, ctx)
                              result_text = (
                                  json.dumps(result.output, ensure_ascii=False)
                                  if result.ok
                                  else f"[错误] {result.error}"
                              )
                          await _emit(
                              StepEvent(kind=StepKind.tool_result, tool=tc_name, content=result_text, step=state.step)
                          )
                          state.messages.append(
                              Message(role="user", content=(
                                  f"[参考数据 | {tc_name}]\n"
                                  f"以下是工具返回的原始数据，仅供你内部参考。"
                                  f"你的回答中禁止出现此格式，必须用你自己的语言综合分析。\n"
                                  f"---\n{result_text}\n---"
                              ))
                          )
                      continue
                  else:
                      # 纯内容 → 判断是最终回答还是中间规划
                      content_buf = await _handle_empty_or_echo(
                          content_buf, state, llm, target_model
                      )
                      await _emit(
                          StepEvent(kind=StepKind.reason, content=content_buf, step=state.step)
                      )
                      state.messages.append(Message(role="assistant", content=content_buf))

                      # ── 防过早终止：智能完成检测 ──
                      # 策略：综合判断是否为真正的最终回答
                      _is_final = _detect_final_answer(content_buf, state)
                      if not _is_final and state.step < MAX_STEPS - 2:
                          # 不是最终回答 → 注入继续指令
                          state.messages.append(Message(
                              role="user",
                              content=(
                                  "[系统指令] 你的任务尚未完成。禁止停下来询问用户或输出中间规划。"
                                  "立即调用工具执行下一步操作。"
                                  "只有当所有子任务全部执行完毕后，才输出包含测试结果或‘全部完成’的最终总结。"
                              ),
                          ))
                          continue

                      action = _extract_action(content_buf)
                      if not action or action.get("action") == "final":
                          state.final_answer = (
                              action.get("answer", content_buf) if action else content_buf
                          )
                      else:
                          state.final_answer = content_buf
                      state.finished = True
                      await _emit(
                          StepEvent(kind=StepKind.final, content=state.final_answer, step=state.step)
                      )
                      break

              elif use_native_tools:
                  # ── 非流式原生工具路径（回退） ──
                  resp = await llm.complete_with_tools(
                      state.messages, specs, model=target_model
                  )
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
                              Message(role="user", content=(
                                  f"[参考数据 | {tc.name}]\n"
                                  f"以下是工具返回的原始数据，仅供你内部参考。"
                                  f"你的回答中禁止出现此格式，必须用你自己的语言综合分析。\n"
                                  f"---\n{result_text}\n---"
                              ))
                          )
                      continue

                  await _emit(
                      StepEvent(kind=StepKind.reason, content=resp.content, step=state.step)
                  )
                  state.messages.append(Message(role="assistant", content=resp.content))

                  # 防过早终止（非流式路径）— 智能完成检测
                  _is_final_ns = _detect_final_answer(resp.content, state)
                  if not _is_final_ns and state.step < MAX_STEPS - 2:
                      state.messages.append(Message(
                          role="user",
                          content=(
                              "[系统指令] 你的任务尚未完成。禁止停下来询问用户或输出中间规划。"
                              "立即调用工具执行下一步操作。"
                              "只有当所有子任务全部执行完毕后，才输出包含测试结果或‘全部完成’的最终总结。"
                          ),
                      ))
                      continue

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
                  if action.get("action") == "tool":
                      await _handle_prompt_tool_action(action, role, tools, ctx, state, events)
                      continue
                  state.final_answer = resp.content
                  state.finished = True
                  await _emit(StepEvent(kind=StepKind.final, content=resp.content, step=state.step))

              else:
                  # ── 提示工程路径（mock / 不支持工具） ──
                  resp = await llm.complete(state.messages, model=target_model)
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

                  if action.get("action") == "tool":
                      await _handle_prompt_tool_action(action, role, tools, ctx, state, events)
                      continue

                  state.final_answer = resp.content
                  state.finished = True
                  await _emit(StepEvent(kind=StepKind.final, content=resp.content, step=state.step))

            if not state.finished:
                # MAX_STEPS 耗尽 — 让 LLM 做最终总结
                state.messages.append(Message(
                    role="user",
                    content=(
                        "[系统指令] 你已达到最大执行轮次。"
                        "请立即停止调用工具，基于你已完成的所有工作，"
                        "输出一份完整的总结报告，包括：已完成的子任务、未完成的部分、以及后续建议。"
                    ),
                ))
                try:
                    final_resp = await llm.complete(state.messages, model=target_model)
                    _fc = (final_resp.content or "").strip()
                    # 回显检测
                    if _fc and not (
                        _fc.startswith("工具 ") or _fc.startswith("[参考数据")
                        or (_fc.startswith("{") and '"total_count"' in _fc[:200])
                    ):
                        state.final_answer = _fc
                    else:
                        state.final_answer = ""
                except Exception:
                    state.final_answer = ""
                # 兆底
                if not state.final_answer:
                    state.final_answer = (
                        f"任务已执行 {state.step} 步，达到最大轮次限制。\n\n"
                        "已完成部分工作，但未能全部完成。\n"
                        "建议：可以继续对话让我完成剩余部分。"
                    )
                await _emit(
                    StepEvent(kind=StepKind.final, content=state.final_answer, step=state.step)
                )
        except Exception as loop_exc:
            # LLM 调用失败（超时/上下文过长等）——用已有工具结果兆底
            if not state.final_answer:
                # 从消息历史中提取最后的工具结果作为回答
                tool_results = [
                    m.content for m in state.messages
                    if m.role == "user" and (
                        m.content.startswith("工具") or m.content.startswith("[参考数据")
                    )
                ]
                if tool_results:
                    state.final_answer = (
                        "工具已执行完成，但模型整合结果时出错。\n\n"
                        "以下是工具返回的原始结果：\n\n"
                        + "\n---\n".join(tool_results[-3:])[:3000]
                    )
                else:
                    state.final_answer = f"执行过程中出错：{loop_exc!s:.200}"
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

    # ── 保存对话历史 ──
    conv_session.add_user(goal)
    conv_session.add_assistant(state.final_answer)
    # ── 持久化到 DB ──
    try:
        from xagent.core.orchestration.conversation import persist_conversation, persist_message
        from xagent.infra.db import get_sessionmaker

        async with get_sessionmaker()() as db_sess:
            await persist_conversation(db_sess, conv_session)
            await persist_message(db_sess, conv_session.conversation_id, "user", goal)
            await persist_message(db_sess, conv_session.conversation_id, "assistant", state.final_answer)
            await db_sess.commit()
    except Exception:  # noqa: S110  持久化失败不影响主流程
        pass
    # ── 自动写入记忆库 ──
    await _save_to_memory(goal, state.final_answer, principal.tenant_id)
    # ── 自动技能提炼（Skill 自进化） ──
    await _auto_extract_skill(goal, state.final_answer, state.step, events)

    return AgentRun(
        run_id=resolved_run_id,
        goal=goal,
        role_name=role.name,
        tenant_id=principal.tenant_id,
        final_answer=state.final_answer,
        steps=state.step,
        events=events,
        conversation_id=conv_session.conversation_id,
    )
