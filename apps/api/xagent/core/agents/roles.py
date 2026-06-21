"""AgentRole 定义。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentRole:
    name: str
    description: str
    system_prompt: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    # 偏好模型（None 用全局默认）
    preferred_model: str | None = None
    # 允许使用的工具名（空集合表示允许全部已注册工具）
    allowed_tools: frozenset[str] = field(default_factory=frozenset)

    def can_use(self, tool_name: str) -> bool:
        return not self.allowed_tools or tool_name in self.allowed_tools
