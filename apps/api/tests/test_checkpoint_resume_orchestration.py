"""恢复运行把 checkpoint 消息和 step 注入内置编排器。"""

from __future__ import annotations

from xagent.adapters.llm.base import LLMClient, LLMResponse, Message
from xagent.core.orchestration.loop import run_agent
from xagent.enterprise.auth.principal import Principal


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
