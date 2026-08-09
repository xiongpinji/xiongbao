"""恢复运行把 checkpoint 消息和 step 注入内置编排器。"""

from __future__ import annotations

import asyncio

import pytest
from xagent.adapters.llm.base import LLMClient, LLMResponse, Message
from xagent.core.orchestration.loop import run_agent
from xagent.enterprise.auth.principal import Principal
from xagent.infra.db import Base, get_engine, get_sessionmaker


class _ResumeLLM(LLMClient):
    supports_tools = False

    async def complete(
        self, messages: list[Message], **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        assert any("checkpoint context" in item.content for item in messages)
        return LLMResponse(
            content='{"action":"final","answer":"resumed safely"}', model="test"
        )

    async def complete_with_tools(
        self, messages, tools, **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        raise NotImplementedError

    async def health(self) -> bool:
        return True


class _FinalLLM(LLMClient):
    supports_tools = False

    def __init__(self, *, fail: bool = False, cancel: bool = False) -> None:
        self.fail = fail
        self.cancel = cancel

    async def complete(
        self, messages: list[Message], **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        if self.cancel:
            raise asyncio.CancelledError
        if self.fail:
            raise RuntimeError("llm failed")
        return LLMResponse(
            content='{"action":"final","answer":"terminal safely"}', model="test"
        )

    async def complete_with_tools(
        self, messages, tools, **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        raise NotImplementedError

    async def health(self) -> bool:
        return True


async def test_resume_continues_from_checkpoint_messages_and_step(monkeypatch) -> None:
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client", lambda: _ResumeLLM()
    )
    principal = Principal(
        user_id="resume-user",
        tenant_id="resume-tenant",
        roles=frozenset({"member"}),
    )

    result = await run_agent(
        "continue release validation",
        principal=principal,
        resume_messages=[{"role": "assistant", "content": "checkpoint context"}],
        resume_step=5,
        resume_changed_files=[],
        resume_from_checkpoint_id="checkpoint-parent",
    )

    assert result.final_answer == "resumed safely"
    assert result.steps > 5


async def _prepare_checkpoint_tables() -> None:
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def _list_run_checkpoints(tenant_id: str, run_id: str):
    from xagent.domains.checkpoints import list_checkpoints

    async with get_sessionmaker()() as session:
        return await list_checkpoints(session, tenant_id, run_id=run_id)


async def test_successful_short_run_saves_single_terminal_checkpoint(
    monkeypatch,
) -> None:
    await _prepare_checkpoint_tables()
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client", lambda: _FinalLLM()
    )
    principal = Principal(
        user_id="terminal-user",
        tenant_id="terminal-tenant",
        roles=frozenset({"member"}),
    )

    result = await run_agent(
        "finish in one step",
        principal=principal,
        run_id="terminal-run-one",
    )

    assert result.final_answer == "terminal safely"
    checkpoints = await _list_run_checkpoints(principal.tenant_id, result.run_id)
    assert [checkpoint.step for checkpoint in checkpoints] == [1]
    assert checkpoints[0].messages[-2:] == [
        {"role": "user", "content": "finish in one step"},
        {"role": "assistant", "content": "terminal safely"},
    ]


async def test_terminal_checkpoint_does_not_duplicate_periodic_boundary(
    monkeypatch,
) -> None:
    await _prepare_checkpoint_tables()
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client", lambda: _FinalLLM()
    )
    principal = Principal(
        user_id="periodic-user",
        tenant_id="periodic-tenant",
        roles=frozenset({"member"}),
    )

    result = await run_agent(
        "finish on checkpoint boundary",
        principal=principal,
        run_id="terminal-run-boundary",
        resume_step=4,
    )

    assert result.steps == 5
    checkpoints = await _list_run_checkpoints(principal.tenant_id, result.run_id)
    assert [checkpoint.step for checkpoint in checkpoints] == [5]


@pytest.mark.parametrize(
    ("llm", "expected_answer"),
    [
        (_FinalLLM(fail=True), "执行过程中出错：llm failed"),
        (_FinalLLM(cancel=True), "任务被用户中断（已执行 1 步）。"),
    ],
)
async def test_terminal_checkpoint_keeps_failure_and_cancel_contracts(
    monkeypatch, llm, expected_answer
) -> None:
    await _prepare_checkpoint_tables()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(
        user_id="non-success-user",
        tenant_id=f"non-success-tenant-{id(llm)}",
        roles=frozenset({"member"}),
    )

    result = await run_agent(
        "do not mark unsuccessful as terminal success",
        principal=principal,
        run_id=f"non-success-run-{id(llm)}",
    )

    assert result.final_answer.startswith(expected_answer)
    checkpoints = await _list_run_checkpoints(principal.tenant_id, result.run_id)
    expected_steps = [1] if llm.cancel else []
    assert [checkpoint.step for checkpoint in checkpoints] == expected_steps
