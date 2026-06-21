"""角色注册表 + 能力匹配。内置常用角色，可在运行时注册自定义角色。"""

from __future__ import annotations

from functools import lru_cache

from xagent.core.agents.roles import AgentRole

_BUILTIN_ROLES: list[AgentRole] = [
    AgentRole(
        name="general",
        description="通用助手，处理开放式任务。",
        system_prompt=(
            "你是 X-Agent 通用智能体。理解用户意图，必要时调用工具，"
            "给出准确、简洁、可执行的回答。"
        ),
        capabilities=frozenset({"chat", "qa", "general"}),
    ),
    AgentRole(
        name="researcher",
        description="检索与综合信息，善用记忆库。",
        system_prompt=(
            "你是研究型智能体。优先用 memory_search 检索已有知识，"
            "综合多源信息，标注不确定性，输出结构化结论。"
        ),
        capabilities=frozenset({"research", "retrieval", "rag", "qa"}),
        allowed_tools=frozenset({"memory_search", "echo"}),
    ),
    AgentRole(
        name="planner",
        description="把复杂目标拆解为可执行步骤。",
        system_prompt=(
            "你是规划型智能体。把用户目标拆解为有序、可验证的步骤，"
            "标注每步依赖与产出，必要时调用工具。"
        ),
        capabilities=frozenset({"planning", "decompose", "general"}),
    ),
    AgentRole(
        name="coder",
        description="编写与修改代码（执行交由沙箱/OpenHands）。",
        system_prompt=(
            "你是编码型智能体。产出正确、可读、可测试的代码与解释，"
            "遵循仓库既有风格；不可信代码的执行交由沙箱。"
        ),
        capabilities=frozenset({"coding", "refactor", "general"}),
    ),
]


class RoleRegistry:
    def __init__(self, roles: list[AgentRole] | None = None) -> None:
        self._roles: dict[str, AgentRole] = {}
        for r in roles or _BUILTIN_ROLES:
            self._roles[r.name] = r

    def register(self, role: AgentRole) -> None:
        self._roles[role.name] = role

    def get(self, name: str) -> AgentRole | None:
        return self._roles.get(name)

    def all(self) -> list[AgentRole]:
        return list(self._roles.values())

    def match(self, capabilities: set[str]) -> AgentRole:
        """挑选能力重合度最高的角色；无重合回退 general。"""
        best: AgentRole | None = None
        best_score = -1
        for role in self._roles.values():
            score = len(role.capabilities & capabilities)
            if score > best_score:
                best, best_score = role, score
        return best or self._roles.get("general") or next(iter(self._roles.values()))


@lru_cache
def get_role_registry() -> RoleRegistry:
    return RoleRegistry()


def reset_role_registry() -> None:
    get_role_registry.cache_clear()


def match_role(capabilities: set[str]) -> AgentRole:
    return get_role_registry().match(capabilities)
