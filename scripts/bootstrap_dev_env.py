"""一键重建开发/验收环境（审计 2026-09-05 F-4：venv 消失导致接手卡壳）。

用法（仓库根或任意位置）：
    python scripts/bootstrap_dev_env.py            # 后端 venv + 前端 node_modules
    python scripts/bootstrap_dev_env.py --skip-web # 仅后端
    python scripts/bootstrap_dev_env.py --check    # 只诊断不安装

要求：uv（https://docs.astral.sh/uv/）与 Node >= 20。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "api"
WEB = ROOT / "apps" / "web"
PY = "3.13"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str], cwd: Path) -> int:
    print(f"$ {' '.join(cmd)}  (cwd={cwd})")
    return subprocess.run(cmd, cwd=cwd, env={**os.environ}).returncode


def check() -> int:
    problems: list[str] = []
    if not _have("uv"):
        problems.append("uv 未安装（pip install uv 或见 https://docs.astral.sh/uv/）")
    if not _have("node"):
        problems.append("node 未安装（需 >= 20）")
    venv = API / ".venv"
    if not (venv / "Scripts" / "python.exe").exists() and not (venv / "bin" / "python").exists():
        problems.append(f"后端 venv 缺失: {venv}（本脚本可重建）")
    else:
        print(f"✓ 后端 venv 存在: {venv}")
    if not (WEB / "node_modules").exists():
        problems.append(f"前端 node_modules 缺失: {WEB}（本脚本可重建）")
    else:
        print(f"✓ 前端 node_modules 存在: {WEB}")
    for p in problems:
        print(f"✗ {p}", file=sys.stderr)
    return 1 if problems else 0


def bootstrap(skip_web: bool) -> int:
    if not _have("uv"):
        print("✗ uv 未安装：pip install uv，或 https://docs.astral.sh/uv/#install", file=sys.stderr)
        return 1
    if rc := _run(["uv", "venv", "--python", PY, ".venv"], API):
        return rc
    if rc := _run(["uv", "pip", "install", "-e", ".[dev]"], API):
        return rc
    py = API / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if rc := _run([str(py), "-c", "import xagent; print('xagent', xagent.__version__, 'OK')"], API):
        return rc
    if not skip_web:
        if not _have("node"):
            print("✗ node 未安装，跳过前端（--skip-web 可静默）", file=sys.stderr)
            return 1
        if rc := _run(["npm", "install", "--no-audit", "--no-fund"], WEB):
            return rc
    print(
        "\n✓ 环境就绪。验收命令：\n"
        "  cd apps/api && .venv/Scripts/python -m pytest tests -q   # 后端全量\n"
        "  cd apps/api && .venv/Scripts/python -m ruff check xagent tests --select F821,F822,F823,B023\n"
        "  cd apps/web && npm run lint && npm run typecheck && npm test && npm run build"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="X-Agent 开发环境一键重建")
    parser.add_argument("--skip-web", action="store_true", help="跳过前端依赖")
    parser.add_argument("--check", action="store_true", help="只诊断不安装")
    args = parser.parse_args()
    return check() if args.check else bootstrap(args.skip_web)


if __name__ == "__main__":
    sys.exit(main())
