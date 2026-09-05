"""上下文压缩（V3-5，对标 Codex compaction）合同测试。"""

from __future__ import annotations

from xagent.adapters.llm import LLMResponse, Message
from xagent.core.orchestration.compaction import (
    DEFAULT_BUDGET_TOKENS,
    RECENT_KEEP_MESSAGES,
    compact_history,
    estimate_messages_tokens,
    estimate_tokens,
)


def _mk(n: int, chars: int = 2000) -> list[Message]:
    return [
        Message(role="user" if i % 2 == 0 else "assistant", content="话" * chars)
        for i in range(n)
    ]


def test_estimate_tokens_cjk_vs_ascii() -> None:
    assert estimate_tokens("你好") == 2
    assert estimate_tokens("abcd") == 1          # 4 ascii ≈ 1 token
    assert estimate_tokens("") == 0
    # 混合：2 CJK + 4 ascii = 2 + 1
    assert estimate_tokens("你好abcd") == 3


async def test_under_budget_returns_unchanged() -> None:
    messages = _mk(4)
    result = await compact_history(messages, budget_tokens=DEFAULT_BUDGET_TOKENS)
    assert result.changed is False
    assert result.strategy == "none"
    assert result.messages is messages


async def test_over_budget_compacts_with_heuristic_when_no_llm() -> None:
    messages = _mk(20)  # 20 × 2000 CJK chars = 40k tokens 估算
    result = await compact_history(messages, budget_tokens=1000, llm=None)
    assert result.changed is True
    assert result.strategy == "heuristic"
    assert result.estimated_tokens_before > 1000
    assert result.estimated_tokens_after < result.estimated_tokens_before
    # 结构：1 条摘要 + 近期 N 条原样保留
    assert len(result.messages) == 1 + RECENT_KEEP_MESSAGES
    assert "[上下文摘要]" in result.messages[0].content
    assert result.messages[-1] is messages[-1]


async def test_recent_messages_kept_verbatim() -> None:
    messages = _mk(12)
    result = await compact_history(messages, budget_tokens=100)
    tail = result.messages[-RECENT_KEEP_MESSAGES:]
    assert tail == messages[-RECENT_KEEP_MESSAGES:]


async def test_llm_summary_preferred_over_heuristic() -> None:
    class StubLLM:
        supports_tools = False

        async def complete(self, messages, *, model=None, temperature=0.7,
                           max_tokens=None, **kwargs):
            return LLMResponse(
                content="用户要求生成报表；已完成数据拉取；剩余：导出 Excel。",
                model="stub",
                prompt_tokens=1,
                completion_tokens=1,
            )

    messages = _mk(10)
    result = await compact_history(messages, budget_tokens=500, llm=StubLLM())
    assert result.strategy == "llm_summary"
    assert "报表" in result.messages[0].content


async def test_llm_failure_degrades_to_heuristic() -> None:
    class BrokenLLM:
        supports_tools = False

        async def complete(self, messages, **kwargs):
            raise RuntimeError("provider down")

    messages = _mk(10)
    result = await compact_history(messages, budget_tokens=500, llm=BrokenLLM())
    assert result.strategy == "heuristic"
    assert result.changed is True


async def test_budget_zero_disables_compaction() -> None:
    messages = _mk(20)
    result = await compact_history(messages, budget_tokens=0)
    assert result.changed is False
    assert result.strategy == "none"


async def test_short_history_not_compacted_even_over_budget() -> None:
    # 消息数 ≤ recent_keep 时不压缩
    messages = _mk(4, chars=20000)
    result = await compact_history(messages, budget_tokens=100, recent_keep=8)
    assert result.changed is False


async def test_input_list_not_mutated() -> None:
    messages = _mk(14)
    snapshot = list(messages)
    await compact_history(messages, budget_tokens=500)
    assert messages == snapshot


def test_estimate_messages_tokens_sums() -> None:
    msgs = [Message(role="user", content="你好"), Message(role="assistant", content="abcd")]
    assert estimate_messages_tokens(msgs) == 3
