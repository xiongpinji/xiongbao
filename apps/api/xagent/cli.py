"""命令行入口：``xagent <command>``。

命令：
    serve     启动 API 服务（uvicorn）
    info      打印当前配置摘要
    smoke     运行三链路冒烟（LLM / trace / 向量）
"""

from __future__ import annotations

import argparse
import sys


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "xagent.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
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


def _cmd_migrate(args: argparse.Namespace) -> int:
    """运行 Alembic 迁移到 head。"""
    import os
    import subprocess
    import sys

    api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=api_dir,
        env=env,
    )
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xagent", description="X-Agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="启动 API 服务")
    p_serve.add_argument("--host", default="0.0.0.0")  # noqa: S104
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    p_info = sub.add_parser("info", help="打印配置摘要")
    p_info.set_defaults(func=_cmd_info)

    p_smoke = sub.add_parser("smoke", help="三链路冒烟测试")
    p_smoke.set_defaults(func=_cmd_smoke)

    p_migrate = sub.add_parser("migrate", help="运行数据库迁移到最新版本")
    p_migrate.set_defaults(func=_cmd_migrate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
