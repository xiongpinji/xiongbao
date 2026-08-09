"""恢复运行把 checkpoint 消息和 step 注入内置编排器。"""

from __future__ import annotations

import asyncio

import pytest
from xagent.adapters.llm.base import LLMClient, LLMResponse, Message, ToolCall
from xagent.core.orchestration.conversation import (
    get_conversation_manager,
    load_messages_from_db,
)
from xagent.core.orchestration.loop import run_agent
from xagent.core.orchestration.state import StepKind
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


class _PromptToolThenFinalLLM(LLMClient):
    supports_tools = False

    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self, messages: list[Message], **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content='{"action":"tool","tool":"echo","args":{"text":"pong"}}',
                model="test",
            )
        return LLMResponse(
            content='{"action":"final","answer":"multi step terminal"}',
            model="test",
        )

    async def complete_with_tools(
        self, messages, tools, **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        raise NotImplementedError

    async def health(self) -> bool:
        return True


class _NativeToolThenFinalLLM(LLMClient):
    supports_tools = True

    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self, messages: list[Message], **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        raise NotImplementedError

    async def complete_with_tools(
        self, messages, tools, **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                model="test",
                tool_calls=[
                    ToolCall(id="call_echo", name="echo", args={"text": "pong"})
                ],
            )
        return LLMResponse(
            content='{"action":"final","answer":"native terminal complete passed"}',
            model="test",
        )

    async def health(self) -> bool:
        return True


class _MaxStepsLLM(LLMClient):
    supports_tools = False

    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self, messages: list[Message], **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content='{"action":"tool","tool":"echo","args":{"text":"pong"}}',
                model="test",
            )
        return LLMResponse(content="max steps summary", model="test")

    async def complete_with_tools(
        self, messages, tools, **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        raise NotImplementedError

    async def health(self) -> bool:
        return True


class _LongFinalLLM(LLMClient):
    supports_tools = False

    async def complete(
        self, messages: list[Message], **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        return LLMResponse(
            content='{"action":"final","answer":"' + ("terminal " + "x" * 650) + '"}',
            model="test",
        )

    async def complete_with_tools(
        self, messages, tools, **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        raise NotImplementedError

    async def health(self) -> bool:
        return True


class _RepeatedToolErrorLLM(LLMClient):
    supports_tools = True

    async def complete(
        self, messages: list[Message], **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        raise NotImplementedError

    async def complete_with_tools(
        self, messages, tools, **kwargs
    ) -> LLMResponse:  # noqa: ARG002
        return LLMResponse(
            content="",
            model="test",
            tool_calls=[
                ToolCall(
                    id="call_missing_file",
                    name="file_read",
                    args={"path": "missing-repeat-error.txt"},
                )
            ],
        )

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


@pytest.mark.parametrize(("resume_step", "terminal_step"), [(4, 5), (9, 10)])
async def test_terminal_checkpoint_replaces_periodic_boundary_snapshot(
    monkeypatch, resume_step, terminal_step
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
        run_id=f"terminal-run-boundary-{terminal_step}",
        resume_step=resume_step,
    )

    assert result.steps == terminal_step
    checkpoints = await _list_run_checkpoints(principal.tenant_id, result.run_id)
    assert [checkpoint.step for checkpoint in checkpoints] == [terminal_step]
    assert checkpoints[0].messages[-2:] == [
        {"role": "user", "content": "finish on checkpoint boundary"},
        {"role": "assistant", "content": "terminal safely"},
    ]


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


async def test_repeated_error_early_termination_does_not_save_terminal_checkpoint(
    monkeypatch,
) -> None:
    await _prepare_checkpoint_tables()
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client",
        lambda: _RepeatedToolErrorLLM(),
    )
    principal = Principal(
        user_id="repeat-error-user",
        tenant_id="repeat-error-tenant",
        roles=frozenset({"member"}),
    )

    result = await run_agent(
        "trigger repeated tool error",
        principal=principal,
        run_id="repeat-error-run",
    )

    assert result.steps == 3
    assert result.final_answer.startswith("任务提前终止：同一错误重复出现 3 次。")
    assert not any(event.kind == StepKind.final for event in result.events)
    assert any(event.kind == StepKind.error for event in result.events)
    checkpoints = await _list_run_checkpoints(principal.tenant_id, result.run_id)
    assert checkpoints == []


async def test_terminal_checkpoint_failure_is_visible_and_not_success(
    monkeypatch,
) -> None:
    await _prepare_checkpoint_tables()
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client", lambda: _FinalLLM()
    )
    warnings: list[dict] = []

    def fake_warning(event, **kwargs):
        warnings.append({"event": event, **kwargs})

    async def fail_checkpoint(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("secret-token-value must not leak")

    monkeypatch.setattr("xagent.core.orchestration.loop.logger.warning", fake_warning)
    monkeypatch.setattr(
        "xagent.core.orchestration.checkpoint.save_checkpoint", fail_checkpoint
    )
    monkeypatch.setattr(
        "xagent.core.orchestration.checkpoint.save_checkpoint_snapshot",
        fail_checkpoint,
    )
    principal = Principal(
        user_id="checkpoint-failure-user",
        tenant_id="checkpoint-failure-tenant",
        roles=frozenset({"member"}),
    )

    events = []

    async def collect_event(event):
        events.append(event.kind.value)

    conversation_id = "terminal-checkpoint-failure-conversation"
    with pytest.raises(RuntimeError, match="terminal_checkpoint_save_failed"):
        await run_agent(
            "finish but checkpoint write fails",
            principal=principal,
            run_id="terminal-checkpoint-failure-run",
            conversation_id=conversation_id,
            on_event=collect_event,
        )

    assert warnings == [
        {
            "event": "terminal_checkpoint_save_failed",
            "run_id": "terminal-checkpoint-failure-run",
            "step": 1,
            "error_type": "RuntimeError",
        }
    ]
    assert "secret-token-value" not in str(warnings)
    assert "final" not in events
    session = get_conversation_manager().get(conversation_id, principal.tenant_id)
    assert session is not None
    assert session.messages == []


async def test_success_final_event_is_emitted_after_terminal_checkpoint(
    monkeypatch,
) -> None:
    await _prepare_checkpoint_tables()
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client", lambda: _FinalLLM()
    )
    import xagent.core.orchestration.checkpoint as checkpoint_module

    original_save = checkpoint_module.save_checkpoint
    sequence: list[str] = []

    async def record_checkpoint(*args, **kwargs):
        sequence.append("checkpoint")
        return await original_save(*args, **kwargs)

    async def collect_event(event):
        sequence.append(event.kind.value)

    monkeypatch.setattr(checkpoint_module, "save_checkpoint", record_checkpoint)
    monkeypatch.setattr(
        checkpoint_module,
        "save_checkpoint_snapshot",
        record_checkpoint,
        raising=False,
    )
    principal = Principal(
        user_id="event-order-user",
        tenant_id="event-order-tenant",
        roles=frozenset({"member"}),
    )

    result = await run_agent(
        "finish after checkpoint first",
        principal=principal,
        run_id="event-order-run",
        on_event=collect_event,
    )

    assert result.final_answer == "terminal safely"
    assert sequence.count("final") == 1
    assert sequence.index("checkpoint") < sequence.index("final")


async def test_multistep_non_boundary_success_saves_terminal_checkpoint(
    monkeypatch,
) -> None:
    await _prepare_checkpoint_tables()
    llm = _PromptToolThenFinalLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(
        user_id="multistep-user",
        tenant_id="multistep-tenant",
        roles=frozenset({"member"}),
    )

    events = []

    async def collect_event(event):
        events.append(event)

    result = await run_agent(
        "use prompt tool before final",
        principal=principal,
        run_id="multistep-terminal-run",
        on_event=collect_event,
    )

    assert result.final_answer.startswith("multi step terminal")
    assert result.steps == 2
    checkpoints = await _list_run_checkpoints(principal.tenant_id, result.run_id)
    assert [checkpoint.step for checkpoint in checkpoints] == [2]
    assert checkpoints[0].messages[-1] == {
        "role": "assistant",
        "content": result.final_answer,
    }
    assert [event.content for event in events if event.kind.value == "final"] == [
        result.final_answer
    ]
    async with get_sessionmaker()() as session:
        db_messages = await load_messages_from_db(
            session, principal.tenant_id, result.conversation_id
        )
    assert db_messages[-1] == {"role": "assistant", "content": result.final_answer}


async def test_terminal_checkpoint_uses_full_final_answer_without_loop_truncation(
    monkeypatch,
) -> None:
    await _prepare_checkpoint_tables()
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client", lambda: _LongFinalLLM()
    )
    principal = Principal(
        user_id="long-final-user",
        tenant_id="long-final-tenant",
        roles=frozenset({"member"}),
    )

    result = await run_agent(
        "finish with long final",
        principal=principal,
        run_id="long-final-run",
    )

    checkpoints = await _list_run_checkpoints(principal.tenant_id, result.run_id)
    assert len(result.final_answer) > 500
    assert checkpoints[0].messages[-1] == {
        "role": "assistant",
        "content": result.final_answer,
    }


async def test_native_tool_then_final_success_saves_terminal_checkpoint(
    monkeypatch,
) -> None:
    await _prepare_checkpoint_tables()
    llm = _NativeToolThenFinalLLM()
    monkeypatch.setattr("xagent.core.orchestration.loop.get_llm_client", lambda: llm)
    principal = Principal(
        user_id="native-terminal-user",
        tenant_id="native-terminal-tenant",
        roles=frozenset({"member"}),
    )

    result = await run_agent(
        "use native tool before final",
        principal=principal,
        run_id="native-terminal-run",
    )

    assert result.final_answer == "native terminal complete passed"
    assert result.steps == 2
    checkpoints = await _list_run_checkpoints(principal.tenant_id, result.run_id)
    assert [checkpoint.step for checkpoint in checkpoints] == [2]
    assert checkpoints[0].messages[-2:] == [
        {"role": "user", "content": "use native tool before final"},
        {"role": "assistant", "content": "native terminal complete passed"},
    ]


async def test_max_steps_exhaustion_does_not_save_terminal_success_checkpoint(
    monkeypatch,
) -> None:
    await _prepare_checkpoint_tables()
    monkeypatch.setattr(
        "xagent.core.orchestration.loop.get_llm_client", lambda: _MaxStepsLLM()
    )
    monkeypatch.setattr("xagent.core.orchestration.loop.MAX_STEPS", 1)
    principal = Principal(
        user_id="max-steps-user",
        tenant_id="max-steps-tenant",
        roles=frozenset({"member"}),
    )

    result = await run_agent(
        "hit max steps before terminal success",
        principal=principal,
        run_id="max-steps-run",
    )

    assert result.final_answer == "max steps summary"
    assert result.steps == 1
    assert not any(event.kind == StepKind.final for event in result.events)
    assert any(event.kind == StepKind.error for event in result.events)
    checkpoints = await _list_run_checkpoints(principal.tenant_id, result.run_id)
    assert checkpoints == []
