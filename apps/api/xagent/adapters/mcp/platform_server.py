"""X-Agent Platform MCP Server — 把平台能力暴露给外部 agent（V3-4）。

对标 Codex CLI 的 MCP 双向能力：Claude Code / Codex / Cursor 等外部 agent
可以把 X-Agent 作为 MCP 工具源直接调用。

暴露工具：
- ``xagent_run``             跑一次 agent 任务（内置编排循环），返回最终回答
- ``xagent_code_review``     代码评审（diff 直传或 repo+base..head，三维并行）
- ``xagent_skill_match``     技能匹配 + prompt 注入文本
- ``xagent_skill_import``    SKILL.md（agentskills.io）导入（强制过质量门禁）

传输：
- stdio（默认）：被宿主 agent 进程拉起，同机使用
- streamable HTTP：``--http --port 8100``，网络可达部署；
  设 ``XAGENT_PLATFORM_MCP_TOKEN`` 后强制 Bearer 校验

安全边界：run/review 走平台既有权限与工具注册表（shell/python 默认禁用等
安全默认不变）；HTTP 模式默认仅绑 127.0.0.1。
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server import MCPServer

from xagent.infra.logging import get_logger

logger = get_logger("xagent.mcp.platform_server")

server = MCPServer(name="xagent-platform")


def _system_principal():
    """MCP 调用主体：platform-mcp 用户 + admin 角色（走平台既有权限语义）。"""
    from xagent.enterprise.auth.principal import Principal

    return Principal(
        user_id="platform-mcp", tenant_id="default",
        roles=frozenset({"admin"}), scopes=frozenset(), is_anonymous=False,
    )


async def xagent_run(goal: str, role: str = "") -> dict[str, Any]:
    """运行一次 X-Agent 任务（内置 observe→reason→act→reflect 编排），返回最终回答。"""
    goal = goal.strip()
    if not goal:
        return {"ok": False, "error": "missing_goal"}
    from xagent.core.orchestration import run_agent

    run = await run_agent(goal, principal=_system_principal(), role_name=role or None)
    return {"ok": True, "run_id": run.run_id, "answer": run.final_answer, "steps": run.steps}


async def xagent_code_review(
    diff: str = "", repo: str = "", base: str = "", head: str = "HEAD",
) -> dict[str, Any]:
    """代码评审：逻辑/安全/规范三维并行。传 diff 文本，或 repo+base..head。"""
    from xagent.domains.code_review.service import review_diff

    try:
        result = await review_diff(
            diff=diff or None, repo=repo or None, base=base or None, head=head,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "result": result.to_dict()}


async def xagent_skill_match(goal: str) -> dict[str, Any]:
    """按任务目标匹配 X-Agent 技能库，返回命中技能与 prompt 注入文本。"""
    goal = goal.strip()
    if not goal:
        return {"ok": False, "error": "missing_goal"}
    from xagent.core.skills import get_skill_store

    store = get_skill_store()
    return {
        "ok": True,
        "matched": [s.to_dict() for s in store.match(goal)],
        "prompt_injection": store.build_prompt_injection(goal),
    }


async def xagent_skill_import(content: str, origin: str = "mcp") -> dict[str, Any]:
    """导入 SKILL.md（agentskills.io 格式）到 X-Agent 技能库（强制质量门禁）。"""
    if not content.strip():
        return {"ok": False, "error": "missing_content"}
    from xagent.core.skills import get_skill_store
    from xagent.core.skills.importer import import_skillmd

    skill, reason = import_skillmd(get_skill_store(), content, origin)
    if skill is None:
        return {"ok": False, "reason": reason}
    return {"ok": True, "skill_id": skill.skill_id, "name": skill.name}


server.add_tool(xagent_run, description="运行一次 X-Agent 任务，返回最终回答")
server.add_tool(xagent_code_review, description="代码评审：逻辑/安全/规范三维并行")
server.add_tool(xagent_skill_match, description="按任务目标匹配技能库 + prompt 注入文本")
server.add_tool(xagent_skill_import, description="导入 SKILL.md（agentskills.io，强制质量门禁）")


class _BearerAuthMiddleware:
    """纯 ASGI Bearer 校验（仅当 XAGENT_PLATFORM_MCP_TOKEN 设置时启用）。"""

    def __init__(self, app: Any, token: str) -> None:
        self._app = app
        self._token = token

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode()
            if auth != f"Bearer {self._token}":
                body = b'{"error":"unauthorized"}'
                await send({
                    "type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self._app(scope, receive, send)


def build_http_app(token: str | None = None) -> Any:
    """构建 streamable HTTP ASGI 应用（无状态模式，每次调用独立）。"""
    app = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True)
    token = token if token is not None else os.environ.get("XAGENT_PLATFORM_MCP_TOKEN", "")
    if token:
        app = _BearerAuthMiddleware(app, token)
    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http", action="store_true", help="streamable HTTP 模式（默认 stdio）")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP 绑定地址（默认仅本机）")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()

    if args.http:
        import uvicorn

        logger.info("platform_mcp_http_start", host=args.host, port=args.port)
        uvicorn.run(build_http_app(), host=args.host, port=args.port)
        return 0

    # stdio：被宿主 agent 拉起
    import anyio

    anyio.run(server.run_stdio_async)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
