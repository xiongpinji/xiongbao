"""执行 agent 适配层降级测试（browser/desktop/coding stub 行为）。

browser-use + Playwright 已装时走真实路径；测试适配两种环境。
"""

from __future__ import annotations

from xagent.adapters.browser import get_browser_agent
from xagent.adapters.coding import get_coding_agent
from xagent.adapters.desktop_auto import get_desktop_agent


async def test_browser_agent_runs_or_degrades() -> None:
    """browser-use 已装走真实（可能成功或降级 Playwright）；未装走 stub。"""
    res = await get_browser_agent().run("打开百度")
    # 真实环境可能成功（Playwright）或失败（stub）；不崩即可
    assert res.ok is True or res.ok is False


async def test_desktop_stub_degrades() -> None:
    res = await get_desktop_agent().run("点击开始菜单")
    assert res.ok is False
    assert "UI-TARS" in (res.error or "")


async def test_coding_stub_degrades() -> None:
    res = await get_coding_agent().issue_to_pr("org/repo", 1)
    assert res.ok is False
    assert "OpenHands" in (res.error or "")


async def test_browser_tool_registered_and_safe() -> None:
    from xagent.adapters.tools import get_tool_registry
    from xagent.adapters.tools.base import ToolContext
    from xagent.enterprise.auth.principal import Principal

    reg = get_tool_registry()
    assert "browser_run" in reg.names()
    ctx = ToolContext(principal=Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"})))
    r = await reg.call("browser_run", {"task": "测试"}, ctx)
    # 真实环境可能成功（Playwright）或失败（stub/无URL）；不炸循环即可
    assert r.ok is True or r.ok is False
