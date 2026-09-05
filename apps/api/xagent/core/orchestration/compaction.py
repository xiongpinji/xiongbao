"""上下文压缩（对标 Codex compaction）：token 预算 + 摘要折叠 + 近期原样保留。

策略（V3-5）：
- 未超预算：原样返回，零开销。
- 超预算：把较早消息折叠为一条摘要消息（优先 LLM 摘要；LLM 不可用时
  降级为首尾截取启发式），近期 ``recent_keep`` 条始终原样保留。
- 全程无重依赖：token 用轻量启发式估算（CJK ~1 字/token，其余 ~4 字符/token），
  不引入 tokenizer。

预算默认 24000 tokens，可用 ``XAGENT_LLM__CONTEXT_BUDGET_TOKENS`` 覆盖；
设为 0 可关闭压缩。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from xagent.adapters.llm import Message

if TYPE_CHECKING:  # 仅供类型标注，避免运行时循环导入
    from xagent.adapters.llm.base import LLMClient

DEFAULT_BUDGET_TOKENS = 24000
RECENT_KEEP_MESSAGES = 8
MIN_MESSAGES_TO_COMPACT = 6
_SUMMARY_HEAD_TOKENS = 400  # 启发式降级时每条消息保留的估算 token 上限

_SUMMARY_PROMPT = (
    "请把以下多轮对话历史压缩为一段简明摘要（中文，不超过 500 字）。"
    "必须保留：用户目标、已确认的事实与决定、已完成的动作、未解决的问题。"
    "省略寒暄与重复内容。直接输出摘要正文，不要任何前缀。\n\n=== 对话历史 ===\n"
)


@dataclass(frozen=True)
class CompactionResult:
    """压缩结果：``strategy`` 为 none/llm_summary/heuristic 之一。"""

    messages: list[Message]
    changed: bool
    estimated_tokens_before: int
    estimated_tokens_after: int
    strategy: str


def estimate_tokens(text: str) -> int:
    """轻量 token 估算：CJK 字符按 1 字/token，其余按 4 字符/token。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return cjk + (other + 3) // 4


def estimate_messages_tokens(messages: list[Message]) -> int:
    return sum(estimate_tokens(getattr(m, "content", "") or "") for m in messages)


async def compact_history(
    messages: list[Message],
    *,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
    llm: "LLMClient | None" = None,
    recent_keep: int = RECENT_KEEP_MESSAGES,
) -> CompactionResult:
    """按 token 预算压缩历史：摘要折叠旧消息 + 原样保留近期消息。

    不修改入参列表；返回新列表。任何 LLM 失败都降级为启发式，绝不抛出。
    """
    before = estimate_messages_tokens(messages)
    if (
        budget_tokens <= 0
        or before <= budget_tokens
        or len(messages) <= max(recent_keep, MIN_MESSAGES_TO_COMPACT)
    ):
        return CompactionResult(
            messages=messages,
            changed=False,
            estimated_tokens_before=before,
            estimated_tokens_after=before,
            strategy="none",
        )

    old, recent = messages[:-recent_keep], messages[-recent_keep:]
    summary_text, strategy = await _summarize(old, llm=llm)
    summary_message = Message(
        role="user",
        content=(
            f"[上下文摘要] 以下为此前对话的压缩摘要（{len(old)} 条消息已折叠，"
            f"估算 {estimate_messages_tokens(old)} tokens → {estimate_tokens(summary_text)} tokens）：\n"
            f"{summary_text}"
        ),
    )
    compacted = [summary_message, *recent]
    return CompactionResult(
        messages=compacted,
        changed=True,
        estimated_tokens_before=before,
        estimated_tokens_after=estimate_messages_tokens(compacted),
        strategy=strategy,
    )


async def _summarize(
    messages: list[Message], *, llm: "LLMClient | None"
) -> tuple[str, str]:
    """优先 LLM 摘要；客户端缺失或调用失败时降级为首尾截取启发式。"""
    transcript = "\n".join(
        f"{m.role}: {getattr(m, 'content', '') or ''}" for m in messages
    )
    if llm is None:
        return _heuristic_summary(messages), "heuristic"
    try:
        response = await llm.complete(
            [Message(role="user", content=_SUMMARY_PROMPT + transcript)],
            temperature=0.0,
            max_tokens=800,
        )
        text = (response.content or "").strip()
        if text:
            return text, "llm_summary"
    except Exception:  # noqa: BLE001  摘要失败绝不阻断编排
        pass
    return _heuristic_summary(messages), "heuristic"


def _heuristic_summary(messages: list[Message]) -> str:
    """无 LLM 时的降级摘要：每条消息保留下限（首段 + 尾行）。"""
    lines: list[str] = []
    for m in messages:
        content = (getattr(m, "content", "") or "").strip().replace("\n", " ")
        if not content:
            continue
        cap = _SUMMARY_HEAD_TOKENS * 3  # 约 400 tokens 的字符上限
        text = content[: cap // 2] + ("…" if len(content) > cap // 2 else "")
        lines.append(f"- {m.role}: {text}")
    return "\n".join(lines)[:2000]
