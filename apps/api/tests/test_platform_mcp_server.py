"""X-Agent Platform MCP Server 测试（V3-4）。

直接调用工具函数与 server 注册表验证工具面，不拉起真实 stdio/HTTP 进程。
"""

from __future__ import annotations

import pytest
from xagent.adapters.mcp import platform_server
from xagent.core.skills import SkillStore

SAMPLE_SKILLMD = """---
name: mcp-import-probe
description: Use when probing the MCP skill import path.
metadata:
  tags: [probe]
---
# Probe

## Procedure
1. ping
"""


@pytest.fixture
def isolated_store(tmp_path, monkeypatch) -> SkillStore:
    import xagent.core.skills as skills_mod

    s = SkillStore(storage_dir=tmp_path / "skills")
    monkeypatch.setattr(skills_mod, "_store", s)
    return s


# ─── 工具面注册 ───


def test_tools_registered() -> None:
    tools = platform_server.server._tool_manager.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "xagent_run", "xagent_code_review", "xagent_skill_match", "xagent_skill_import",
    }


# ─── 参数校验 ───


async def test_run_missing_goal_rejected() -> None:
    assert await platform_server.xagent_run("") == {"ok": False, "error": "missing_goal"}


async def test_skill_import_missing_content() -> None:
    payload = await platform_server.xagent_skill_import("")
    assert payload["ok"] is False


async def test_skill_match_missing_goal() -> None:
    payload = await platform_server.xagent_skill_match("  ")
    assert payload["ok"] is False


# ─── 技能工具（隔离库）───


async def test_skill_import_then_match(isolated_store: SkillStore) -> None:
    payload = await platform_server.xagent_skill_import(SAMPLE_SKILLMD, origin="mcp/test")
    assert payload["ok"] is True
    assert payload["name"] == "mcp-import-probe"

    # 重复导入过门禁去重
    dup = await platform_server.xagent_skill_import(SAMPLE_SKILLMD)
    assert dup["ok"] is False
    assert dup["reason"].startswith("duplicate")

    matched = await platform_server.xagent_skill_match("please run the mcp import probe")
    assert matched["ok"] is True
    assert any(s["name"] == "mcp-import-probe" for s in matched["matched"])
    assert "ping" in matched["prompt_injection"]


# ─── 代码评审（无 LLM 诚实降级，不伪造结果）───


async def test_code_review_without_llm_degrades() -> None:
    diff = (
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
        "+import os\n+os.system('ls')\n"
    )
    payload = await platform_server.xagent_code_review(diff=diff)
    assert payload["ok"] is True
    assert "verdict" in payload["result"] or "status" in payload["result"]


async def test_code_review_missing_input() -> None:
    payload = await platform_server.xagent_code_review()
    assert payload["ok"] is False


# ─── HTTP 模式：Bearer 中间件与应用构建 ───


def _http_scope(auth: str = "") -> dict:
    return {
        "type": "http", "method": "POST", "path": "/mcp",
        "headers": [(b"authorization", auth.encode())] if auth else [],
    }


async def _status_of(app, scope: dict) -> int:
    statuses: list[int] = []

    async def send(msg):
        if msg["type"] == "http.response.start":
            statuses.append(msg["status"])

    async def receive():
        return {"type": "http.request"}

    await app(scope, receive, send)
    return statuses[0]


async def test_bearer_middleware_blocks_and_passes() -> None:
    async def ok_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    app = platform_server._BearerAuthMiddleware(ok_app, "secret-token")
    assert await _status_of(app, _http_scope()) == 401
    assert await _status_of(app, _http_scope("Bearer wrong")) == 401
    assert await _status_of(app, _http_scope("Bearer secret-token")) == 200


def test_build_http_app_constructs() -> None:
    """HTTP 应用可构建（stateless streamable HTTP），带不带 token 均可。"""
    assert platform_server.build_http_app(token="") is not None
    assert platform_server.build_http_app(token="t") is not None
