"""编码 agent 抽象 + stub 降级。

OpenHands（MIT）：issue 拆解 → PR，可自托管。X-Agent 保留 PR 交付/审批门语义：
产物 PR 需经审批门通过才合并。未配置 OpenHands -> StubCodingAgent。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, runtime_checkable


@dataclass
class IssueToPrResult:
    ok: bool
    pr_url: str | None = None
    branch: str | None = None
    summary: str = ""
    error: str | None = None


@runtime_checkable
class CodingAgent(Protocol):
    backend: str
    async def issue_to_pr(
        self, repo: str, issue_number: int, *, base_branch: str = "main"
    ) -> IssueToPrResult: ...
    async def health(self) -> bool: ...


class StubCodingAgent:
    backend = "stub"

    async def issue_to_pr(
        self, repo: str, issue_number: int, *, base_branch: str = "main"
    ) -> IssueToPrResult:
        return IssueToPrResult(
            ok=False,
            error="编码 agent 未启用：未配置 OpenHands 运行时（XAGENT_CODING__OPENHANDS_URL）。",
        )

    async def health(self) -> bool:
        return True


class OpenHandsAgent:
    """OpenHands 真实实现（Phase 2 后段接入 SDK）。"""

    backend = "openhands"

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint

    async def issue_to_pr(
        self, repo: str, issue_number: int, *, base_branch: str = "main"
    ) -> IssueToPrResult:
        import httpx

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{self._endpoint}/issue-to-pr",
                json={"repo": repo, "issue": issue_number, "base": base_branch},
            )
            resp.raise_for_status()
            data = resp.json()
        return IssueToPrResult(
            ok=True,
            pr_url=data.get("pr_url"),
            branch=data.get("branch"),
            summary=data.get("summary", ""),
        )

    async def health(self) -> bool:
        return True


@lru_cache
def get_coding_agent() -> CodingAgent:
    url = os.environ.get("XAGENT_CODING__OPENHANDS_URL", "")
    if url:
        return OpenHandsAgent(url)
    return StubCodingAgent()
