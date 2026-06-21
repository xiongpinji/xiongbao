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
    """浏览器 agent：Playwright 原生驱动 + 可选 browser-use LLM 决策。

    browser-use 0.13+ 有 pydantic provider 兼容问题时自动降级 Playwright。
    """

    backend = "browser-use"

    def __init__(self, llm_model: str) -> None:
        self._llm_model = llm_model

    async def run(self, task: str, *, max_steps: int = 15) -> BrowserResult:
        try:
            return await self._run_browser_use(task, max_steps)
        except Exception:
            return await self._run_playwright(task)

    async def _run_browser_use(self, task: str, max_steps: int) -> BrowserResult:
        from browser_use import Agent
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=self._llm_model,
            base_url="http://localhost:11434/v1",
            api_key="not-needed",
        )
        object.__setattr__(llm, "provider", "openai")
        agent = Agent(task=task, llm=llm)
        result = await agent.run(max_steps=max_steps)
        return BrowserResult(ok=True, summary=str(result))

    async def _run_playwright(self, task: str) -> BrowserResult:
        import re

        from playwright.async_api import async_playwright

        url_match = re.search(r"https?://[^\s]+", task)
        if not url_match:
            return BrowserResult(ok=False, error="任务中未找到 URL")
        url = url_match.group()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            title = await page.title()
            text = await page.inner_text("body")
            await browser.close()
        return BrowserResult(
            ok=True, summary=f"页面标题: {title}\n内容摘要: {text[:200]}"
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
