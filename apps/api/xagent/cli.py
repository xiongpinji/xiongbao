"""X-Agent CLI — 命令行管理工具。

命令：
    serve       启动 API 服务（uvicorn）
    run         运行 Agent 任务（支持 SSE 流式）
    skills      技能管理（list / stats）
    mcp         MCP Server 状态
    health      健康检查
    info        打印当前配置摘要
    smoke       三链路冒烟测试（LLM / trace / 向量）
    warmup      预热 Ollama 模型
    migrate     运行数据库迁移
"""

from __future__ import annotations

import argparse
import json
import sys

# ─── 本地管理命令 ───


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "xagent.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def _cmd_info(_: argparse.Namespace) -> int:
    from xagent.infra.settings import get_settings

    s = get_settings()
    print(f"X-Agent  mode={s.mode.value}  debug={s.debug}")
    print(f"  db        : {s.db.url}")
    print(f"  cache     : {s.cache.redis_url or '(in-memory)'}")
    print(f"  llm proxy : {s.llm.proxy_url or '(direct litellm)'}  model={s.llm.default_model}")
    print(f"  qdrant    : {s.memory.qdrant_url or '(:memory:)'}")
    print(f"  langfuse  : {s.observability.langfuse_host or '(disabled)'}")
    return 0


def _cmd_smoke(_: argparse.Namespace) -> int:
    import asyncio

    from xagent.scripts.smoke_three_chains import run_smoke

    return asyncio.run(run_smoke())


def _cmd_warmup(_: argparse.Namespace) -> int:
    import asyncio

    from xagent.infra.settings import get_settings
    from xagent.scripts.ollama_warmup import warmup_ollama_model

    result = asyncio.run(warmup_ollama_model(get_settings().llm))
    return 0 if result.ok or result.skipped else 1


def _cmd_migrate(_: argparse.Namespace) -> int:
    """运行 Alembic 迁移到 head。"""
    import os
    import subprocess

    api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=api_dir,
        env={**os.environ},
    )
    return result.returncode


# ─── API 客户端命令 ───


def _get_token(args: argparse.Namespace, base: str) -> str:
    if args.token:
        return args.token
    import httpx

    resp = httpx.post(f"{base}/auth/login", json={"username": args.user, "password": args.password})
    if resp.status_code != 200:
        print(f"登录失败: {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()["access_token"]


def _cmd_run(args: argparse.Namespace) -> int:
    """通过 API 运行 Agent 任务。"""
    import httpx

    base = f"http://{args.host}:{args.port}/api/v1"
    token = _get_token(args, base)
    headers = {"Authorization": f"Bearer {token}"}

    if args.stream:
        body = {"goal": args.goal, "mode": "full-auto", "strategy": args.strategy}
        with httpx.stream(
            "POST", f"{base}/stream/agents/run", json=body, headers=headers, timeout=300,
        ) as r:
            for line in r.iter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    event = data.get("event", "")
                    if event == "step":
                        step = data.get("data", {})
                        kind = step.get('kind', '')
                        tool = step.get('tool', '')
                        print(f"  [{step.get('step', '?')}] {kind} {tool}")
                    elif event == "done":
                        answer = data.get("data", {}).get("final_answer", "")
                        print(f"\n✓ 完成: {answer[:200]}")
                    elif event == "error":
                        print(f"\n✗ 错误: {data.get('data', {})}", file=sys.stderr)
    else:
        resp = httpx.post(
            f"{base}/agents/run", json={"goal": args.goal}, headers=headers, timeout=300,
        )
        if resp.status_code != 200:
            print(f"执行失败: {resp.text}", file=sys.stderr)
            return 1
        result = resp.json()
        print(f"Run ID: {result.get('run_id', '?')}")
        print(f"Steps:  {result.get('steps', 0)}")
        print(f"Answer: {result.get('final_answer', '')}")
    return 0


def _cmd_skills(args: argparse.Namespace) -> int:
    import httpx

    base = f"http://{args.host}:{args.port}/api/v1"
    token = _get_token(args, base)
    headers = {"Authorization": f"Bearer {token}"}

    if args.skills_cmd == "list":
        resp = httpx.get(f"{base}/skills", headers=headers)
        data = resp.json()
        for s in data.get("skills", []):
            print(f"  [{s['skill_id']}] {s['name']} (v{s['version']}, source={s['source']})")
        print(f"\n共 {data.get('count', 0)} 个技能")
    elif args.skills_cmd == "stats":
        resp = httpx.get(f"{base}/skills/stats", headers=headers)
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    import httpx

    base = f"http://{args.host}:{args.port}/api/v1"
    token = _get_token(args, base)
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(f"{base}/mcp/servers", headers=headers)
    data = resp.json()
    for srv in data.get("servers", []):
        status = "✓" if srv.get("connected") else "✗"
        print(f"  {status} {srv['name']} ({srv.get('tool_count', 0)} tools)")
    print(f"\n共 {data.get('total_tools', 0)} 个工具")
    return 0


def _cmd_health(args: argparse.Namespace) -> int:
    import httpx

    base = f"http://{args.host}:{args.port}"
    try:
        resp = httpx.get(f"{base}/health", timeout=5)
        print(f"Health: {resp.json()}")
        resp2 = httpx.get(f"{base}/ready", timeout=5)
        print(f"Ready:  {resp2.json()}")
    except Exception as e:
        print(f"服务不可达: {e}", file=sys.stderr)
        return 1
    return 0


# ─── Parser 构建 ───


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xagent", description="X-Agent CLI")
    parser.add_argument("--host", default="127.0.0.1", help="API host")
    parser.add_argument("--port", type=int, default=8000, help="API port")
    parser.add_argument("--token", default="", help="JWT token (跳过登录)")
    parser.add_argument("--user", default="admin", help="用户名")
    parser.add_argument("--password", default="admin", help="密码")

    sub = parser.add_subparsers(dest="command", required=True)

    # serve
    p_serve = sub.add_parser("serve", help="启动 API 服务")
    p_serve.add_argument("--reload", action="store_true", help="开发热重载")
    p_serve.set_defaults(func=_cmd_serve)

    # run
    p_run = sub.add_parser("run", help="运行 Agent 任务")
    p_run.add_argument("goal", help="任务目标")
    p_run.add_argument("--stream", action="store_true", help="SSE 流式输出")
    p_run.add_argument("--strategy", default="react", choices=["react", "plan-execute"])
    p_run.set_defaults(func=_cmd_run)

    # skills
    p_skills = sub.add_parser("skills", help="技能管理")
    skills_sub = p_skills.add_subparsers(dest="skills_cmd")
    skills_sub.add_parser("list", help="列出技能")
    skills_sub.add_parser("stats", help="技能统计")
    p_skills.set_defaults(func=_cmd_skills)

    # mcp
    p_mcp = sub.add_parser("mcp", help="MCP Server 状态")
    p_mcp.set_defaults(func=_cmd_mcp)

    # health
    p_health = sub.add_parser("health", help="健康检查")
    p_health.set_defaults(func=_cmd_health)

    # info
    p_info = sub.add_parser("info", help="打印配置摘要")
    p_info.set_defaults(func=_cmd_info)

    # smoke
    p_smoke = sub.add_parser("smoke", help="三链路冒烟测试")
    p_smoke.set_defaults(func=_cmd_smoke)

    # warmup
    p_warmup = sub.add_parser("warmup", help="预热 Ollama 模型")
    p_warmup.set_defaults(func=_cmd_warmup)

    # migrate
    p_migrate = sub.add_parser("migrate", help="运行数据库迁移")
    p_migrate.set_defaults(func=_cmd_migrate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
