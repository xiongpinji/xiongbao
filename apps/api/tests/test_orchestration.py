"""编排、角色匹配、工具、审计链测试。"""

from __future__ import annotations

from xagent.adapters.llm.base import LLMClient, LLMResponse, Message
from xagent.core.agents import get_role_registry, match_role
from xagent.core.orchestration import run_agent
from xagent.core.orchestration.loop import run_agent as run_agent_builtin
from xagent.core.orchestration.state import StepKind
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal


def test_role_match_by_capability() -> None:
    assert match_role({"research", "rag"}).name == "researcher"
    assert match_role({"planning"}).name == "planner"
    assert match_role({"unknown-cap"}).name in {r.name for r in get_role_registry().all()}


async def test_run_agent_converges_offline() -> None:
    # mock LLM 返回纯文本 -> 第一步 final，循环收敛
    p = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))
    run = await run_agent("介绍一下你自己", principal=p, role_name="general")
    assert run.final_answer
    assert run.steps >= 1
    assert run.events[-1].kind == StepKind.final
    assert run.tenant_id == "t1"


async def test_run_agent_records_run_id() -> None:
    p = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))
    run = await run_agent("任务", principal=p)
    assert run.run_id


async def test_run_agent_reuses_external_run_id() -> None:
    p = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))
    run = await run_agent("任务", principal=p, run_id="external-run-id")
    assert run.run_id == "external-run-id"


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
