"""编排、角色匹配、工具、审计链测试。"""

from __future__ import annotations

import asyncio

import pytest
from xagent.adapters.llm.base import LLMClient, LLMResponse, Message
from xagent.adapters.llm.litellm_client import LiteLLMClient, StreamChunk
from xagent.adapters.tools.base import ToolResult
from xagent.core.agents import get_role_registry, match_role
from xagent.core.orchestration import run_agent
from xagent.core.orchestration.conversation import get_conversation_manager
from xagent.core.orchestration.loop import (
    _detect_final_answer,
)
from xagent.core.orchestration.loop import (
    run_agent as run_agent_builtin,
)
from xagent.core.orchestration.state import AgentRun, AgentState, StepEvent, StepKind
from xagent.core.skills import SkillStore
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal


def test_role_match_by_capability() -> None:
    assert match_role({"research", "rag"}).name == "researcher"
    assert match_role({"planning"}).name == "planner"
    assert match_role({"unknown-cap"}).name in {r.name for r in get_role_registry().all()}


def test_agent_run_status_fields_preserve_positional_events_compatibility() -> None:
    event = StepEvent(kind=StepKind.final, content="done", step=1)

    run = AgentRun("run", "goal", "role", "tenant", "done", 1, [event])

    assert run.events == [event]
    assert run.status == "succeeded"
    assert run.error == ""


def test_detect_final_answer_accepts_executed_all_subtasks_summary() -> None:
    state = AgentState(goal="create artifact", role_name="developer", tenant_id="t1")
    state.messages.append(
        Message(
            role="tool",
            name="file_write",
            tool_call_id="call-1",
            content="[file_write 执行成功] 已写入 R2_AGENT_RESULT.md",
        )
    )

    assert _detect_final_answer(
        "✅ 所有子任务执行完毕\n最终结果：R2_AGENT_RESULT.md 已正确创建",
        state,
    )


async def test_run_agent_converges_offline() -> None:
    # mock LLM 返回纯文本 -> 第一步 final，循环收敛
    p = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))
    run = await run_agent("介绍一下你自己", principal=p, role_name="general")
    assert run.final_answer
    assert run.steps >= 1
    assert run.events[-1].kind == StepKind.final
    assert run.tenant_id == "t1"
    assert run.status == "succeeded"
    assert run.error == ""
    assert run.to_dict()["status"] == "succeeded"


async def test_run_agent_records_run_id() -> None:
    p = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))
    run = await run_agent("任务", principal=p)
    assert run.run_id


async def test_run_agent_reuses_external_run_id() -> None:
    p = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))
    run = await run_agent("任务", principal=p, run_id="external-run-id")
    assert run.run_id == "external-run-id"


async def test_tool_mode_none_forces_builtin_orchestration(monkeypatch) -> None:
    import xagent.core.orchestration as orchestration
    from xagent.core.orchestration import deerflow_loop, loop

    principal = Principal(
        user_id="chat-user", tenant_id="tenant-chat", roles=frozenset({"member"})
    )

    async def _unexpected_deerflow(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("no-tools Chat 不得被 DeerFlow 截获")

    async def _builtin(goal: str, **kwargs) -> AgentRun:
        assert kwargs["tool_mode"] == "none"
        return AgentRun(
            run_id="chat-run",
            goal=goal,
            role_name="general",
            tenant_id=principal.tenant_id,
            final_answer="chat answer",
            steps=1,
        )

    monkeypatch.setattr(orchestration, "_has_deerflow", lambda: True)
    monkeypatch.setattr(deerflow_loop, "run_agent_deerflow", _unexpected_deerflow)
    monkeypatch.setattr(loop, "run_agent", _builtin)

    result = await orchestration.run_agent(
        "chat prompt", principal=principal, tool_mode="none"
    )

    assert result.final_answer == "chat answer"


class _FailingLLM(LLMClient):
    supports_tools = False

    def __init__(self, error: BaseException) -> None:
        self.error = error

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        raise self.error

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        raise AssertionError("无工具模型不得进入原生工具路径")

    async def health(self) -> bool:
        return True


class _NoToolsChatLLM(LiteLLMClient):
    def __init__(self, content: str = "exact chat answer") -> None:
        self.messages: list[Message] = []
        self.calls = 0
        self.content = content

    async def complete_chat(self, messages, **kwargs) -> LLMResponse:
        self.calls += 1
        self.messages = list(messages)
        assert kwargs["max_tokens"] >= 512
        return LLMResponse(
            content=self.content,
            model="ollama_chat/qwen3:4b",
        )

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        raise AssertionError("no-tools Chat 必须走明确 chat completion")

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        raise AssertionError("no-tools Chat 不得传入 tools schema")

    async def stream_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        raise AssertionError("no-tools Chat 不得进入工具流式路径")
        yield

    async def health(self) -> bool:
        return True


class _LengthFinishChoice:
    finish_reason = "length"


class _LengthLimitedNoToolsChatLLM(_NoToolsChatLLM):
    def __init__(self) -> None:
        super().__init__(content="")
        self.max_tokens_calls: list[int] = []

    async def complete_chat(self, messages, **kwargs) -> LLMResponse:
        max_tokens = kwargs["max_tokens"]
        self.max_tokens_calls.append(max_tokens)
        if max_tokens < 1024:
            return LLMResponse(
                content="",
                model="ollama_chat/qwen3:4b",
                completion_tokens=0,
                raw={"choices": [_LengthFinishChoice()]},
            )
        return LLMResponse(
            content="R2-RESTORE-OK",
            model="ollama_chat/qwen3:4b",
            completion_tokens=640,
            raw={"choices": [{"finish_reason": "stop"}]},
        )


class _NonEmptyTruncatedNoToolsChatLLM(_NoToolsChatLLM):
    def __init__(self, *, recovery_still_truncated: bool = False) -> None:
        super().__init__(content="")
        self.recovery_still_truncated = recovery_still_truncated
        self.max_tokens_calls: list[int] = []

    async def complete_chat(self, messages, **kwargs) -> LLMResponse:
        max_tokens = kwargs["max_tokens"]
        self.max_tokens_calls.append(max_tokens)
        if max_tokens < 1024:
            return LLMResponse(
                content="R3-CHAT-TRUNCATED-PREFIX",
                model="ollama_chat/qwen3:4b",
                completion_tokens=512,
                raw={"choices": [{"finish_reason": "stop"}]},
            )
        if self.recovery_still_truncated:
            return LLMResponse(
                content="R3-CHAT-STILL-TRUNCATED",
                model="ollama_chat/qwen3:4b",
                completion_tokens=128,
                raw={"choices": [{"finish_reason": "length"}]},
            )
        return LLMResponse(
            content="R3-CHAT-COMPLETE",
            model="ollama_chat/qwen3:4b",
            completion_tokens=96,
            raw={"choices": [{"finish_reason": "stop"}]},
        )


async def test_builtin_tool_mode_none_expands_length_limited_recovery_budget(
    monkeypatch,
) -> None:
    llm = _LengthLimitedNoToolsChatLLM()
    principal = Principal(
        user_id="restore-user",
        tenant_id="restore-tenant",
        roles=frozenset({"member"}),
    )
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client", lambda: llm
    )

    run = await run_agent_builtin(
        "请只回复：R2-RESTORE-OK",
        principal=principal,
        tool_mode="none",
    )

    assert run.status == "succeeded", run.error
    assert run.final_answer == "R2-RESTORE-OK"
    assert llm.max_tokens_calls == [512, 1024]


async def test_builtin_tool_mode_none_recovers_nonempty_truncated_response(
    monkeypatch,
) -> None:
    llm = _NonEmptyTruncatedNoToolsChatLLM()
    principal = Principal(
        user_id="r3-user",
        tenant_id="r3-tenant",
        roles=frozenset({"member"}),
    )
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client", lambda: llm
    )

    run = await run_agent_builtin(
        "请只回复：R3-CHAT-COMPLETE",
        principal=principal,
        tool_mode="none",
    )

    assert run.status == "succeeded", run.error
    assert run.final_answer == "R3-CHAT-COMPLETE"
    assert llm.max_tokens_calls == [512, 1024]


async def test_builtin_tool_mode_none_fails_when_recovery_is_still_truncated(
    monkeypatch,
) -> None:
    llm = _NonEmptyTruncatedNoToolsChatLLM(recovery_still_truncated=True)
    principal = Principal(
        user_id="r3-user",
        tenant_id="r3-tenant",
        roles=frozenset({"member"}),
    )
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client", lambda: llm
    )

    run = await run_agent_builtin(
        "请只回复：R3-CHAT-COMPLETE",
        principal=principal,
        tool_mode="none",
    )

    assert run.status == "failed"
    assert run.error == "model_incomplete_response_after_retry"
    assert "R3-CHAT-STILL-TRUNCATED" not in run.final_answer
    assert not any(event.kind == StepKind.final for event in run.events)
    assert llm.max_tokens_calls == [512, 1024]


async def test_builtin_tool_mode_none_preserves_tenant_context_without_dev_hints(
    monkeypatch,
    tmp_path,
) -> None:
    llm = _NoToolsChatLLM()
    principal = Principal(
        user_id="chat-user", tenant_id="tenant-chat", roles=frozenset({"member"})
    )
    conversation_id = "no-tools-context"
    conversation = get_conversation_manager().get_or_create(
        conversation_id, principal.tenant_id
    )
    conversation.add_user("previous user turn")
    conversation.add_assistant("previous assistant turn")
    skill_store = SkillStore(tmp_path / "skills")
    skill_store.create_skill(
        name="tenant-chat-skill",
        description="tenant chat context",
        trigger_pattern="exact chat prompt",
        system_prompt_hint="tenant skill hint",
        tenant_id=principal.tenant_id,
    )

    async def _memory_context(goal: str, tenant_id: str) -> str:
        assert goal == "exact chat prompt"
        assert tenant_id == principal.tenant_id
        return "tenant memory context"

    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client", lambda: llm
    )
    monkeypatch.setattr(
        "xagent.core.orchestration.loop._retrieve_relevant_memories", _memory_context
    )
    monkeypatch.setattr("xagent.core.skills.get_skill_store", lambda: skill_store)

    run = await run_agent_builtin(
        "exact chat prompt",
        principal=principal,
        role_name="coder",
        capabilities={"coding"},
        conversation_id=conversation_id,
        tool_mode="none",
    )

    assert run.status == "succeeded", run.error
    assert run.role_name == "general"
    assert run.final_answer == "exact chat answer"
    assert llm.calls == 1
    assert [message.content for message in llm.messages[1:]] == [
        "previous user turn",
        "previous assistant turn",
        "exact chat prompt",
    ]
    system = llm.messages[0].content
    assert "X-Agent 通用智能体" in system
    assert "tenant memory context" in system
    assert "tenant skill hint" in system
    assert "## 核心行为准则" not in system
    assert "## 项目指令" not in system
    assert "## 项目环境" not in system
    assert "[任务类型: 代码开发]" not in "\n".join(
        message.content for message in llm.messages
    )
    assert not any(event.kind == StepKind.tool_call for event in run.events)


async def test_builtin_tool_mode_none_treats_tool_json_as_plain_final(
    monkeypatch,
) -> None:
    tool_json = '{"action":"tool","tool":"echo","args":{"text":"pong"}}'
    llm = _NoToolsChatLLM(content=tool_json)
    principal = Principal(
        user_id="chat-user", tenant_id="tenant-chat", roles=frozenset({"member"})
    )
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client", lambda: llm
    )

    run = await run_agent_builtin(
        "return tool-shaped text",
        principal=principal,
        tool_mode="none",
    )

    assert run.status == "succeeded"
    assert run.final_answer == tool_json
    assert not any(
        event.kind in {StepKind.tool_call, StepKind.tool_result}
        for event in run.events
    )


async def test_builtin_tool_mode_none_rejects_required_first_tool() -> None:
    principal = Principal(
        user_id="chat-user", tenant_id="tenant-chat", roles=frozenset({"member"})
    )

    with pytest.raises(ValueError, match="tool_mode=none"):
        await run_agent_builtin(
            "invalid strict chat",
            principal=principal,
            tool_mode="none",
            required_first_tool="file_write",
        )


class _BlockingLLM(LLMClient):
    supports_tools = False

    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        self.started.set()
        await asyncio.Event().wait()

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        raise AssertionError("无工具模型不得进入原生工具路径")

    async def health(self) -> bool:
        return True


async def test_builtin_run_reports_provider_failure(monkeypatch) -> None:
    llm = _FailingLLM(ValueError("provider failed"))
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin("provider failure", principal=principal)

    assert run.status == "failed"
    assert "provider failed" in run.error
    assert run.to_dict()["error"] == run.error
    assert [event.kind for event in run.events if event.kind == StepKind.error] == [
        StepKind.error
    ]
    assert not any(event.kind == StepKind.final for event in run.events)


async def test_builtin_run_reports_memory_error(monkeypatch) -> None:
    llm = _FailingLLM(MemoryError("out of memory"))
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin("memory failure", principal=principal)

    assert run.status == "failed"
    assert "memory_pressure" in run.error
    assert [event.kind for event in run.events if event.kind == StepKind.error] == [
        StepKind.error
    ]
    assert not any(event.kind == StepKind.final for event in run.events)


async def test_builtin_run_keeps_graceful_cancel_for_regular_calls(monkeypatch) -> None:
    llm = _BlockingLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    task = asyncio.create_task(
        run_agent_builtin("regular cancel", principal=principal)
    )
    await asyncio.wait_for(llm.started.wait(), timeout=5)
    task.cancel()
    run = await task

    assert run.status == "cancelled"
    assert "cancelled" in run.error
    assert [event.kind for event in run.events if event.kind == StepKind.error] == [
        StepKind.error
    ]
    assert not any(event.kind == StepKind.final for event in run.events)


class _ToolJsonLLM(LLMClient):
    supports_tools = False

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages: list[Message], **kw) -> LLMResponse:  # noqa: ARG002
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content='{"action":"tool","tool":"echo","args":{"text":"pong"}}',
                model="test",
            )
        # loop.py 当前实现把工具结果以 role="tool" 消息追加（内容为原始结果 '"pong"'），
        # 不再是旧的 user 消息"工具 echo 结果：..."包装。整合失败时 loop 会降级为
        # "工具已执行完成，但模型整合结果时出错…原始结果"——该 fallback 文案诚实且合理，
        # 因此这里按现行消息结构断言，验证工具结果确实回传给模型后才给出 final。
        assert any(m.role == "tool" and "pong" in m.content for m in messages)
        return LLMResponse(
            content='{"action":"final","answer":"done"}',
            model="test",
        )

    async def complete_with_tools(self, messages, tools, **kw):  # noqa: ARG002
        raise NotImplementedError

    async def health(self) -> bool:
        return True


async def test_run_agent_prompt_tool_action_awaits_tool_result(monkeypatch) -> None:
    llm = _ToolJsonLLM()
    p = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)

    run = await run_agent_builtin("调用工具", principal=p, role_name="general")

    assert llm.calls == 2
    assert run.final_answer == "done"
    # loop.py 现在每次迭代会额外发 progress 事件（SSE 进度推送，合理漂移），
    # 过滤后断言核心事件序列
    kinds = [e.kind for e in run.events if e.kind != StepKind.progress]
    assert kinds == [
        StepKind.reason,
        StepKind.tool_call,
        StepKind.tool_result,
        StepKind.reason,
        StepKind.final,
    ]
    tool_events = [e for e in run.events if e.kind == StepKind.tool_call]
    result_events = [e for e in run.events if e.kind == StepKind.tool_result]
    assert tool_events[0].tool == "echo"
    # echo 工具返回 str 时 loop 直接透传（不再 json.dumps 包装）
    assert result_events[0].content == 'pong'


def test_audit_chain_integrity() -> None:
    log = get_audit_log()
    log.record(tenant_id="t1", actor="u", action="a1", resource="agent")
    log.record(tenant_id="t1", actor="u", action="a2", resource="memory")
    ok, broken = log.verify()
    assert ok
    assert broken is None


def test_audit_chain_detects_tampering() -> None:
    from xagent.enterprise.audit.chain import AuditLog

    log = AuditLog(secret="s")
    log.record(tenant_id="t1", actor="u", action="a1", resource="agent")
    e2 = log.record(tenant_id="t1", actor="u", action="a2", resource="memory")
    # 篡改第二条的 action（绕过不可变 dataclass：直接动内部列表替换）
    tampered = type(e2)(
        seq=e2.seq, ts=e2.ts, tenant_id=e2.tenant_id, actor=e2.actor,
        action="HACKED", resource=e2.resource, detail=e2.detail,
        prev_hash=e2.prev_hash, hash=e2.hash,
    )
    log._events[1] = tampered  # noqa: SLF001 测试内部校验
    ok, broken = log.verify()
    assert not ok
    assert broken == 1


def test_audit_tenant_filter() -> None:
    from xagent.enterprise.audit.chain import AuditLog

    log = AuditLog(secret="s")
    log.record(tenant_id="tA", actor="u", action="x", resource="agent")
    log.record(tenant_id="tB", actor="u", action="y", resource="agent")
    assert len(log.list("tA")) == 1
    assert len(log.list()) == 2


async def test_tool_registry_tenant_scoped_memory() -> None:
    from xagent.adapters.tools import get_tool_registry
    from xagent.adapters.tools.base import ToolContext

    reg = get_tool_registry()
    ctx = ToolContext(principal=Principal(user_id="u", tenant_id="tT", roles=frozenset({"member"})))
    w = await reg.call("memory_write", {"id": "m1", "text": "工具写入"}, ctx)
    assert w.ok
    s = await reg.call("memory_search", {"query": "工具写入"}, ctx)
    assert s.ok
    assert any(item["id"] == "m1" for item in s.output)



# ─── #3 复现：原生 tool_calls 场景下工具执行异常必须回填 tool 消息 ──────────


class _HangingToolRegistry:
    """模拟工具调用抛异常（等价于 asyncio.wait_for 超时）的注册表。"""

    def specs(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "echo",
                    "description": "回显文本",
                    "parameters": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                    },
                },
            }
        ]

    async def call(self, name, args, ctx):  # noqa: ARG002
        raise TimeoutError("tool hung")


class _NativeToolLLM(LLMClient):
    """支持原生 function-calling 的 mock：第一轮下 tool_calls，第二轮给最终回答。"""

    supports_tools = True

    def __init__(self) -> None:
        self.calls = 0
        self.second_call_messages: list[Message] = []

    async def complete(self, messages: list[Message], **kw) -> LLMResponse:  # noqa: ARG002
        return LLMResponse(content="最终总结：全部完成。已调用工具并取得结果。", model="test")

    async def complete_with_tools(self, messages, tools, **kw) -> LLMResponse:  # noqa: ARG002
        from xagent.adapters.llm.base import ToolCall

        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                model="test",
                tool_calls=[ToolCall(id="call_1", name="echo", args={"text": "hi"})],
            )
        self.second_call_messages = list(messages)
        return LLMResponse(content="最终总结：全部完成。已调用工具并取得结果。", model="test")

    async def health(self) -> bool:
        return True


class _ParallelEchoRegistry:
    """返回真实回显结果，用于覆盖流式并发工具路径。"""

    def specs(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "echo",
                    "description": "回显文本",
                    "parameters": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                    },
                },
            }
        ]

    async def call(self, name, args, ctx):  # noqa: ARG002
        return ToolResult(ok=True, output=args["text"])


class _StreamingParallelLLM(LiteLLMClient):
    """第一轮流式返回两个工具调用，第二轮返回最终回答。"""

    def __init__(self) -> None:
        self.calls = 0
        self.second_call_messages: list[Message] = []

    async def stream_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        self.calls += 1
        if self.calls == 1:
            yield StreamChunk(
                tool_call_deltas=[
                    {
                        "index": 0,
                        "id": "call_a",
                        "function": {"name": "echo", "arguments": '{"text":"a"}'},
                    },
                    {
                        "index": 1,
                        "id": "call_b",
                        "function": {"name": "echo", "arguments": '{"text":"b"}'},
                    },
                ],
                finished=True,
            )
            return
        self.second_call_messages = list(messages)
        yield StreamChunk(delta_content="并发工具执行完成。", finished=True)

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        return LLMResponse(content="并发工具执行完成。", model="test")

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        raise AssertionError("流式回归不得进入非流式路径")

    async def health(self) -> bool:
        return True


class _EmptyRecoveryStreamingLLM(LiteLLMClient):
    """流式工具请求与纯文本恢复均返回空内容。"""

    def __init__(self, recovery_content: str = "") -> None:
        self.recovery_content = recovery_content

    async def stream_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        yield StreamChunk(finished=True)

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        return LLMResponse(content=self.recovery_content, model="test")

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        raise AssertionError("流式合同测试不得进入非流式路径")

    async def health(self) -> bool:
        return True


async def test_stream_empty_response_after_recovery_is_failed(monkeypatch) -> None:
    llm = _EmptyRecoveryStreamingLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin(
        "回答当前问题",
        principal=principal,
        role_name="general",
    )

    assert run.status == "failed"
    assert run.error == "model_empty_response_after_retry"
    assert "页面动态渲染" not in run.final_answer
    assert "README" not in run.final_answer


async def test_stream_empty_response_can_recover_with_real_content(monkeypatch) -> None:
    llm = _EmptyRecoveryStreamingLLM("恢复后的真实模型回答。")
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin(
        "回答当前问题",
        principal=principal,
        role_name="general",
    )

    assert run.status == "succeeded"
    assert run.error == ""
    assert run.final_answer == "恢复后的真实模型回答。"


class _EmptyRecoveryNativeLLM(LLMClient):
    supports_tools = True

    def __init__(self, recovery_content: str = "") -> None:
        self.recovery_content = recovery_content

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        return LLMResponse(content=self.recovery_content, model="test")

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        return LLMResponse(content="", model="test")

    async def health(self) -> bool:
        return True


async def test_nonstream_native_empty_response_after_recovery_is_failed(
    monkeypatch,
) -> None:
    llm = _EmptyRecoveryNativeLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin(
        "回答当前问题",
        principal=principal,
        role_name="general",
    )

    assert run.status == "failed"
    assert run.error == "model_empty_response_after_retry"
    assert "页面动态渲染" not in run.final_answer


class _EmptyRecoveryPlainLLM(LLMClient):
    supports_tools = False

    def __init__(self, recovery_content: str = "") -> None:
        self.recovery_content = recovery_content
        self.calls = 0

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        self.calls += 1
        content = "" if self.calls == 1 else self.recovery_content
        return LLMResponse(content=content, model="test")

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        raise AssertionError("无工具模型不得进入原生工具路径")

    async def health(self) -> bool:
        return True


async def test_nonstream_plain_empty_response_after_recovery_is_failed(
    monkeypatch,
) -> None:
    llm = _EmptyRecoveryPlainLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin(
        "回答当前问题",
        principal=principal,
        role_name="general",
    )

    assert run.status == "failed"
    assert run.error == "model_empty_response_after_retry"
    assert "页面动态渲染" not in run.final_answer


@pytest.mark.parametrize(
    "llm_type",
    [_EmptyRecoveryNativeLLM, _EmptyRecoveryPlainLLM],
    ids=["native-tools", "plain"],
)
async def test_nonstream_empty_response_can_recover_with_real_content(
    monkeypatch,
    llm_type,
) -> None:
    llm = llm_type("恢复后的真实模型回答。")
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin(
        "回答当前问题",
        principal=principal,
        role_name="general",
    )

    assert run.status == "succeeded"
    assert run.error == ""
    assert run.final_answer == "恢复后的真实模型回答。"


class _FailingRecoveryStreamingLLM(_EmptyRecoveryStreamingLLM):
    async def complete(self, messages, **kwargs):  # noqa: ARG002
        raise ValueError("recovery provider failed")


async def test_stream_empty_response_reports_recovery_failure(monkeypatch) -> None:
    llm = _FailingRecoveryStreamingLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin(
        "回答当前问题",
        principal=principal,
        role_name="general",
    )

    assert run.status == "failed"
    assert run.error == "model_response_recovery_failed: recovery provider failed"


class _BlockingRecoveryStreamingLLM(_EmptyRecoveryStreamingLLM):
    def __init__(self) -> None:
        super().__init__()
        self.recovery_started = asyncio.Event()

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        self.recovery_started.set()
        await asyncio.Event().wait()


async def test_stream_empty_response_recovery_preserves_cancellation(monkeypatch) -> None:
    llm = _BlockingRecoveryStreamingLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    task = asyncio.create_task(
        run_agent_builtin(
            "回答当前问题",
            principal=principal,
            role_name="general",
        )
    )
    await asyncio.wait_for(llm.recovery_started.wait(), timeout=5)
    task.cancel()
    run = await task

    assert run.status == "cancelled"
    assert run.error == "cancelled_by_user"


class _RequiredFileWriteLLM(LLMClient):
    """首轮忽略 required tool 给纯文本，第二轮才调用 file_write。"""

    supports_tools = True

    def __init__(self) -> None:
        self.tool_choices: list[object] = []
        self.calls = 0

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        return LLMResponse(content="已完成开发任务。", model="test")

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        from xagent.adapters.llm.base import ToolCall

        self.calls += 1
        self.tool_choices.append(kwargs.get("tool_choice"))
        if self.calls == 1:
            return LLMResponse(content="我会创建文件。", model="test")
        if self.calls == 2:
            return LLMResponse(
                content="",
                model="test",
                tool_calls=[
                    ToolCall(
                        id="call_write",
                        name="file_write",
                        args={"path": "artifact.txt", "content": "ok"},
                    )
                ],
            )
        return LLMResponse(content="已完成开发任务并写入产物。", model="test")

    async def health(self) -> bool:
        return True


class _WrongThenRequiredFileWriteLLM(_RequiredFileWriteLLM):
    """非流式：首轮忽略 named choice 调 echo，第二轮才写文件。"""

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        from xagent.adapters.llm.base import ToolCall

        self.calls += 1
        self.tool_choices.append(kwargs.get("tool_choice"))
        if self.calls == 1:
            return LLMResponse(
                content="",
                model="test",
                tool_calls=[ToolCall(id="call_wrong", name="echo", args={})],
            )
        if self.calls == 2:
            return LLMResponse(
                content="",
                model="test",
                tool_calls=[
                    ToolCall(
                        id="call_write",
                        name="file_write",
                        args={"path": "artifact.txt", "content": "ok"},
                    )
                ],
            )
        return LLMResponse(content="已完成开发任务并写入产物。", model="test")


class _RequiredStreamingFileWriteLLM(LiteLLMClient):
    """流式：首轮调错工具，第二轮可配置为正确或继续错误。"""

    def __init__(self, *, second_tool: str = "file_write") -> None:
        self.second_tool = second_tool
        self.calls = 0
        self.tool_choices: list[object] = []

    async def stream_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        self.calls += 1
        self.tool_choices.append(kwargs.get("tool_choice"))
        if self.calls <= 2:
            tool_name = "echo" if self.calls == 1 else self.second_tool
            arguments = (
                '{"path":"artifact.txt","content":"ok"}'
                if tool_name == "file_write"
                else "{}"
            )
            yield StreamChunk(
                tool_call_deltas=[
                    {
                        "index": 0,
                        "id": f"call_{self.calls}",
                        "function": {
                            "name": tool_name,
                            "arguments": arguments,
                        },
                    }
                ],
                finished=True,
            )
            return
        yield StreamChunk(
            delta_content="已完成开发任务并写入产物。",
            finished=True,
        )

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        return LLMResponse(content="已完成开发任务并写入产物。", model="test")

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        raise AssertionError("流式合同测试不得进入非流式路径")

    async def health(self) -> bool:
        return True


class _RejectedThenSuccessfulFileWriteLLM(LiteLLMClient):
    """流式：先尝试越界路径被拒绝，再写入合法产物。"""

    def __init__(self) -> None:
        self.calls = 0

    async def stream_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        self.calls += 1
        if self.calls <= 2:
            path = "../outside.txt" if self.calls == 1 else "artifact.txt"
            yield StreamChunk(
                tool_call_deltas=[
                    {
                        "index": 0,
                        "id": f"call_{self.calls}",
                        "function": {
                            "name": "file_write",
                            "arguments": (
                                '{"path":"' + path + '","content":"ok"}'
                            ),
                        },
                    }
                ],
                finished=True,
            )
            return
        yield StreamChunk(
            delta_content="开发任务已全部完成并写入合法产物。",
            finished=True,
        )

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        return LLMResponse(
            content="开发任务已全部完成并写入合法产物。", model="test"
        )

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        raise AssertionError("流式回归不得进入非流式路径")

    async def health(self) -> bool:
        return True


class _RejectedThenSuccessfulNonStreamingFileWriteLLM(LLMClient):
    supports_tools = True

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        return LLMResponse(
            content="开发任务已全部完成并写入合法产物。", model="test"
        )

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        from xagent.adapters.llm.base import ToolCall

        self.calls += 1
        if self.calls <= 2:
            path = "../outside.txt" if self.calls == 1 else "artifact.txt"
            return LLMResponse(
                content="",
                model="test",
                tool_calls=[
                    ToolCall(
                        id=f"call_{self.calls}",
                        name="file_write",
                        args={"path": path, "content": "ok"},
                    )
                ],
            )
        return LLMResponse(
            content="开发任务已全部完成并写入合法产物。", model="test"
        )

    async def health(self) -> bool:
        return True


class _FileWriteRegistry:
    def specs(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "file_write",
                    "description": "写文件",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
            }
        ]

    async def call(self, name, args, ctx):  # noqa: ARG002
        return ToolResult(ok=True, output="written")


class _RejectingFileWriteRegistry(_FileWriteRegistry):
    async def call(self, name, args, ctx):  # noqa: ARG002
        if args.get("path") == "../outside.txt":
            return ToolResult(ok=False, error="写入路径必须位于 workspace 内")
        return ToolResult(ok=True, output="written")


@pytest.mark.parametrize(
    "llm_type",
    [
        _RejectedThenSuccessfulFileWriteLLM,
        _RejectedThenSuccessfulNonStreamingFileWriteLLM,
    ],
    ids=["stream", "non-stream"],
)
async def test_failed_file_write_is_not_persisted_as_changed_file(
    monkeypatch, llm_type
) -> None:
    llm = llm_type()
    checkpoint_files: list[list[str]] = []

    async def capture_checkpoint(*args, **kwargs):  # noqa: ARG001
        checkpoint_files.append(list(args[4]))

    async def verification_passes(*args, **kwargs):  # noqa: ARG001
        return True, "ok"

    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_tool_registry",
        lambda: _RejectingFileWriteRegistry(),
    )
    monkeypatch.setattr(
        "xagent.core.orchestration.loop._git_create_work_branch",
        lambda workspace, run_id: "agent/test",
    )
    monkeypatch.setattr(
        "xagent.core.orchestration.loop._run_verification", verification_passes
    )
    monkeypatch.setattr(
        "xagent.core.orchestration.checkpoint.save_checkpoint_snapshot",
        capture_checkpoint,
    )
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin(
        "创建开发产物",
        principal=principal,
        role_name="general",
        required_first_tool="file_write",
    )

    assert run.status == "succeeded"
    assert checkpoint_files == [["artifact.txt"]]


async def test_required_first_tool_retries_once_after_plain_text(monkeypatch) -> None:
    llm = _RequiredFileWriteLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_tool_registry",
        lambda: _FileWriteRegistry(),
    )
    monkeypatch.setattr(
        "xagent.core.orchestration.loop._git_create_work_branch",
        lambda workspace, run_id: "agent/test",
    )
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin(
        "创建开发产物",
        principal=principal,
        role_name="general",
        required_first_tool="file_write",
    )

    required_choice = {
        "type": "function",
        "function": {"name": "file_write"},
    }
    assert llm.tool_choices[:2] == [required_choice, required_choice]
    assert llm.tool_choices[2:]
    assert all(choice is None for choice in llm.tool_choices[2:])
    assert any(
        event.kind == StepKind.tool_call and event.tool == "file_write"
        for event in run.events
    )
    assert run.final_answer


@pytest.mark.parametrize(
    "llm_type",
    [_WrongThenRequiredFileWriteLLM, _RequiredStreamingFileWriteLLM],
    ids=["non-stream", "stream"],
)
async def test_required_tool_corrects_wrong_first_tool(
    monkeypatch, llm_type
) -> None:
    llm = llm_type()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_tool_registry",
        lambda: _FileWriteRegistry(),
    )
    monkeypatch.setattr(
        "xagent.core.orchestration.loop._git_create_work_branch",
        lambda workspace, run_id: "agent/test",
    )
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin(
        "创建开发产物",
        principal=principal,
        role_name="general",
        required_first_tool="file_write",
    )

    required_choice = {
        "type": "function",
        "function": {"name": "file_write"},
    }
    assert llm.tool_choices[:2] == [required_choice, required_choice]
    assert llm.tool_choices[2:]
    assert all(choice is None for choice in llm.tool_choices[2:])
    assert [
        event.tool for event in run.events if event.kind == StepKind.tool_call
    ] == ["file_write"]
    assert run.final_answer


async def test_stream_required_tool_stops_after_one_wrong_tool_correction(
    monkeypatch,
) -> None:
    llm = _RequiredStreamingFileWriteLLM(second_tool="echo")
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_tool_registry",
        lambda: _FileWriteRegistry(),
    )
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin(
        "创建开发产物",
        principal=principal,
        role_name="general",
        required_first_tool="file_write",
    )

    required_choice = {
        "type": "function",
        "function": {"name": "file_write"},
    }
    assert llm.calls == 2
    assert llm.tool_choices == [required_choice, required_choice]
    assert not any(event.kind == StepKind.tool_call for event in run.events)
    assert "未调用必需工具 file_write" in run.final_answer
    assert "已纠偏重试 1 次" in run.final_answer


async def test_required_first_tool_fails_after_single_correction(monkeypatch) -> None:
    llm = _RequiredFileWriteLLM()

    async def _always_plain_text(messages, tools, **kwargs):  # noqa: ARG001
        llm.tool_choices.append(kwargs.get("tool_choice"))
        return LLMResponse(content="只返回文本，不调用工具。", model="test")

    monkeypatch.setattr(llm, "complete_with_tools", _always_plain_text)
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_tool_registry",
        lambda: _FileWriteRegistry(),
    )
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin(
        "创建开发产物",
        principal=principal,
        role_name="general",
        required_first_tool="file_write",
    )

    assert len(llm.tool_choices) == 2
    assert "未调用必需工具 file_write" in run.final_answer
    assert "已纠偏重试 1 次" in run.final_answer


async def test_required_first_tool_must_exist_in_tool_schema(monkeypatch) -> None:
    llm = _NativeToolLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_tool_registry",
        lambda: _ParallelEchoRegistry(),
    )
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    with pytest.raises(RuntimeError, match="未在当前角色的工具 schema 中"):
        await run_agent_builtin(
            "创建开发产物",
            principal=principal,
            role_name="general",
            required_first_tool="file_write",
        )


async def test_native_tool_exception_backfills_tool_message(monkeypatch) -> None:
    """工具执行抛异常（超时等）时：run 不应中途崩溃，且第二轮 LLM 调用前
    必须回填与 assistant tool_calls 配对的 tool 消息（DeepSeek 硬性要求）。"""
    llm = _NativeToolLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_tool_registry", lambda: _HangingToolRegistry()
    )
    p = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin("调用工具", principal=p, role_name="general")

    # 修复前：异常穿透循环，run 在第一步崩溃，第二轮 LLM 调用永远不会发生
    assert llm.calls == 2, "工具异常后 run 应继续第二轮 LLM 调用，而非中途崩溃"
    # 第二轮下发前必须存在与 call_1 配对的 tool 回填消息（错误结果也要回填）
    tool_msgs = [m for m in llm.second_call_messages if m.role == "tool"]
    assert any(m.tool_call_id == "call_1" for m in tool_msgs), (
        "缺 tool message 回填：assistant tool_calls 无配对 tool 消息"
    )
    assert any("[错误]" in m.content for m in tool_msgs)
    assert run.final_answer


async def test_streaming_parallel_tools_return_real_results(monkeypatch) -> None:
    llm = _StreamingParallelLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_tool_registry", lambda: _ParallelEchoRegistry()
    )
    principal = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))

    run = await run_agent_builtin("并发调用两个 echo", principal=principal, role_name="general")

    results = [event.content for event in run.events if event.kind == StepKind.tool_result]
    assert results == ["a", "b"]
    assert all("UnboundLocalError" not in str(value) for value in results)
    assert "2 次工具调用, 成功率 100%" in run.final_answer
    assert {
        message.tool_call_id
        for message in llm.second_call_messages
        if message.role == "tool"
    } == {"call_a", "call_b"}
