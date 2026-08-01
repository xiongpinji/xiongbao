"""Agent 智能深化：多轮对话记忆 + 策略自适应选择。

- ConversationMemory: 滑动窗口 + 摘要压缩，保持上下文连贯
- StrategySelector: 根据任务复杂度自动选择 ReAct / Plan-Execute / Supervisor
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger(__name__)


# ─── 多轮对话记忆 ──────────────────────────────────────────


@dataclass
class Turn:
    role: str  # user / assistant / system
    content: str
    ts: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class ConversationMemory:
    """滑动窗口 + 摘要压缩的对话记忆。

    - 保留最近 `window` 轮完整对话
    - 超出窗口的历史压缩为摘要
    - 支持关键事实提取与持久化
    """

    def __init__(self, session_id: str, *, window: int = 10) -> None:
        self.session_id = session_id
        self.window = window
        self._turns: list[Turn] = []
        self._summary: str = ""
        self._facts: list[str] = []

    def add(self, role: str, content: str, **meta: Any) -> None:
        self._turns.append(Turn(role=role, content=content, metadata=meta))
        # 超出窗口时压缩
        if len(self._turns) > self.window * 2:
            self._compress()

    def _compress(self) -> None:
        """将窗口外的历史压缩为摘要。"""
        overflow = self._turns[: -self.window]
        self._turns = self._turns[-self.window:]
        # 简单摘要：提取关键句
        key_parts = []
        for t in overflow:
            if len(t.content) > 50:
                key_parts.append(f"[{t.role}]: {t.content[:100]}...")
            else:
                key_parts.append(f"[{t.role}]: {t.content}")
        new_summary = " | ".join(key_parts[-5:])
        self._summary = f"{self._summary} {new_summary}".strip()
        logger.debug(
            "memory_compressed",
            session=self.session_id,
            summary_len=len(self._summary),
        )

    def extract_fact(self, fact: str) -> None:
        """记录关键事实（跨会话可用）。"""
        if fact not in self._facts:
            self._facts.append(fact)

    def build_context(self, max_chars: int = 2000) -> str:
        """构建注入 LLM 的上下文文本。"""
        parts: list[str] = []
        if self._summary:
            parts.append(f"[历史摘要] {self._summary[:500]}")
        if self._facts:
            parts.append(f"[已知事实] {'; '.join(self._facts[-10:])}")
        # 最近对话
        recent = self._turns[-self.window:]
        for t in recent:
            parts.append(f"{t.role}: {t.content[:300]}")
        context = "\n".join(parts)
        return context[:max_chars]

    @property
    def turn_count(self) -> int:
        return len(self._turns)


# 会话记忆注册表
_sessions: dict[str, ConversationMemory] = {}


def get_conversation_memory(session_id: str, *, window: int = 10) -> ConversationMemory:
    if session_id not in _sessions:
        _sessions[session_id] = ConversationMemory(session_id, window=window)
    return _sessions[session_id]


# ─── 策略自适应选择 ────────────────────────────────────────


class StrategySelector:
    """根据任务特征自动选择执行策略。

    策略:
    - react: 简单单步任务（工具调用 ≤ 2）
    - plan_execute: 多步骤复杂任务（需要规划）
    - supervisor: 多角色协作任务（需要分解 + 并行）
    """

    # 复杂度信号关键词
    _MULTI_STEP_SIGNALS = [
        "然后", "接着", "之后", "第一步", "第二步", "首先",
        "步骤", "流程", "分别", "依次",
        "then", "next", "after that", "first", "second", "finally",
    ]
    _MULTI_ROLE_SIGNALS = [
        "协作", "团队", "分工", "并行", "多个角色",
        "collaborate", "team", "parallel", "multiple agents",
    ]

    def select(self, goal: str, *, context: str = "") -> str:
        """返回策略名称: react / plan_execute / supervisor。"""
        text = f"{goal} {context}".lower()

        # 多角色信号 → supervisor
        role_score = sum(1 for kw in self._MULTI_ROLE_SIGNALS if kw in text)
        if role_score >= 2:
            logger.info("strategy_selected", strategy="supervisor", reason="multi-role")
            return "supervisor"

        # 多步骤信号 → plan_execute
        step_score = sum(1 for kw in self._MULTI_STEP_SIGNALS if kw in text)
        if step_score >= 2 or len(goal) > 200:
            logger.info("strategy_selected", strategy="plan_execute", reason="multi-step")
            return "plan_execute"

        # 默认 → react
        logger.info("strategy_selected", strategy="react", reason="simple")
        return "react"

    def select_with_confidence(self, goal: str, *, context: str = "") -> dict[str, Any]:
        """返回策略 + 置信度 + 原因。"""
        text = f"{goal} {context}".lower()
        role_score = sum(1 for kw in self._MULTI_ROLE_SIGNALS if kw in text)
        step_score = sum(1 for kw in self._MULTI_STEP_SIGNALS if kw in text)

        if role_score >= 2:
            return {
                "strategy": "supervisor",
                "confidence": min(0.9, 0.6 + role_score * 0.1),
                "reason": f"检测到 {role_score} 个多角色协作信号",
            }
        if step_score >= 2 or len(goal) > 200:
            return {
                "strategy": "plan_execute",
                "confidence": min(0.85, 0.55 + step_score * 0.1),
                "reason": f"检测到 {step_score} 个多步骤信号" + (
                    "，目标较长" if len(goal) > 200 else ""
                ),
            }
        return {
            "strategy": "react",
            "confidence": 0.8,
            "reason": "简单直接任务，无需规划",
        }


_selector: StrategySelector | None = None


def get_strategy_selector() -> StrategySelector:
    global _selector
    if _selector is None:
        _selector = StrategySelector()
    return _selector
