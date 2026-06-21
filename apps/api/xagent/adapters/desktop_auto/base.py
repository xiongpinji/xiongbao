"""桌面 agent 抽象 + stub 降级。

UI-TARS-desktop（Apache-2.0）：视觉 GUI agent，最强开源 computer-use 选项。
未配置 UI-TARS 端点 -> StubDesktopAgent。保留 IME/剪贴板/快捷键语义接口（独有）。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, runtime_checkable


@dataclass
class DesktopResult:
    ok: bool
    actions: list[dict] | None = None  # 执行的动作序列（点击/输入/快捷键...）
    summary: str = ""
    error: str | None = None


@runtime_checkable
class DesktopAgent(Protocol):
    backend: str
    async def run(self, task: str, *, screenshot: bytes | None = None) -> DesktopResult: ...
    async def health(self) -> bool: ...


class StubDesktopAgent:
    backend = "stub"

    async def run(self, task: str, *, screenshot: bytes | None = None) -> DesktopResult:
        return DesktopResult(
            ok=False,
            error="桌面 agent 未启用：未配置 UI-TARS 端点（XAGENT_DESKTOP__UI_TARS_URL）。",
        )

    async def health(self) -> bool:
        return True


class UITarsAgent:
    """UI-TARS 真实实现（Phase 2 后段接入模型）。"""

    backend = "ui-tars"

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint

    async def run(self, task: str, *, screenshot: bytes | None = None) -> DesktopResult:
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._endpoint}/predict",
                json={"task": task, "screenshot": bool(screenshot)},
            )
            resp.raise_for_status()
            data = resp.json()
        return DesktopResult(ok=True, actions=data.get("actions"), summary=data.get("summary", ""))

    async def health(self) -> bool:
        return True


@lru_cache
def get_desktop_agent() -> DesktopAgent:
    # settings 暂无 desktop 段；用环境变量直读以保持轻量
    import os

    url = os.environ.get("XAGENT_DESKTOP__UI_TARS_URL", "")
    if url:
        return UITarsAgent(url)
    return StubDesktopAgent()
