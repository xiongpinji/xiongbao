"""浏览器 agent 抽象 + stub 降级。

browser-use：LLM 驱动决策 + Playwright 执行；需安装 ``browser-use``(MIT)。
未安装 -> StubBrowserAgent 返回明确提示（不真跑浏览器），安全且离线可用。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, runtime_checkable

from xagent.infra.settings import get_settings


@dataclass
class BrowserResult:
    ok: bool
    summary: str = ""
    error: str | None = None
    artifacts: list[str] | None = None


@runtime_checkable
class BrowserAgent(Protocol):
    backend: str
    async def run(self, task: str, *, max_steps: int = 15) -> BrowserResult: ...
    async def health(self) -> bool: ...


class StubBrowserAgent:
    """未安装 browser-use 时的降级实现。"""

    backend = "stub"

    async def run(self, task: str, *, max_steps: int = 15) -> BrowserResult:
        return BrowserResult(
            ok=False,
            error=(
                "浏览器 agent 未启用：未安装 browser-use。"
                "请 `pip install -e .[browser]` 并安装 Playwright 浏览器后重试。"
            ),
        )

    async def health(self) -> bool:
        return True


class BrowserUseAgent:
    """browser-use 真实实现（需 extras）。"""

    backend = "browser-use"

    def __init__(self, llm_model: str) -> None:
        self._llm_model = llm_model

    async def run(self, task: str, *, max_steps: int = 15) -> BrowserResult:
        from browser_use import Agent  # 延迟导入

        # browser-use 接受一个 llm provider；这里用 litellm 兼容
        agent = Agent(task=task, llm=self._llm_model)
        result = await agent.run(max_steps=max_steps)
        return BrowserResult(
            ok=True,
            summary=str(result),
        )

    async def health(self) -> bool:
        return True


@lru_cache
def get_browser_agent() -> BrowserAgent:
    settings = get_settings()
    try:
        import browser_use  # noqa: F401
    except ImportError:
        return StubBrowserAgent()
    return BrowserUseAgent(llm_model=settings.llm.default_model)
