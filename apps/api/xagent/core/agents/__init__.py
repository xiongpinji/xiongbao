"""agent 角色注册与能力匹配。

角色 = system prompt + 能力标签 + 模型偏好 + 允许工具。借鉴 CrewAI 的角色化协作，
但保持轻量。能力匹配：据任务需要的能力标签挑选最合适角色。
"""

from xagent.core.agents.registry import (
    RoleRegistry,
    get_role_registry,
    match_role,
    reset_role_registry,
)
from xagent.core.agents.roles import AgentRole

__all__ = [
    "AgentRole",
    "RoleRegistry",
    "get_role_registry",
    "reset_role_registry",
    "match_role",
]
