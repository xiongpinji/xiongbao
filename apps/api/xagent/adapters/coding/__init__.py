"""自主编码 agent 适配层：OpenHands（Issue→PR）。

保留 X-Agent 的 PR 交付/审批门语义；Phase 2 提供 stub 降级，
真实 OpenHands SDK 接入在具备运行时后启用。
"""

from xagent.adapters.coding.base import (
    CodingAgent,
    IssueToPrResult,
    get_coding_agent,
)

__all__ = ["CodingAgent", "IssueToPrResult", "get_coding_agent"]
