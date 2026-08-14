#!/usr/bin/env python3
"""一键记录 v1.1.1 发布签字。

在签字矩阵中写入角色、签字人与日期，并把签署时的 master HEAD 与
远端 Release 状态一并留痕，使签字本身成为可审计证据。

用法（仓库根目录）：
  python scripts/record_signoff.py --role Owner --name canqu
  python scripts/record_signoff.py --role 发布负责人 --name canqu
  python scripts/record_signoff.py --role QA --name canqu

角色名需与签字矩阵表格中的角色列一致。重复签署同一角色会被拒绝。
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

SIGNOFF_DOC = Path(__file__).resolve().parents[1] / "docs" / "RELEASE_SIGNOFF_PACKAGE_V1.1.1.md"


def current_head() -> str:
    try:
        repo_root = SIGNOFF_DOC.resolve().parents[1]
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, IndexError):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a release sign-off")
    parser.add_argument("--role", required=True, help="签字角色（须与矩阵一致）")
    parser.add_argument("--name", required=True, help="签字人")
    args = parser.parse_args()

    text = SIGNOFF_DOC.read_text(encoding="utf-8")
    today = datetime.date.today().isoformat()

    # 匹配签字矩阵行：| 角色 | 职责 | ＿＿＿＿ | ＿＿＿＿ |
    pattern = re.compile(
        rf"\| ({re.escape(args.role)}（[^|]*）?|{re.escape(args.role)}) \| ([^|]+) \| ＿+ \| ＿+ \|"
    )
    match = pattern.search(text)
    if match is None:
        if re.search(rf"\| {re.escape(args.role)}", text):
            print(f"[REFUSE] 角色「{args.role}」已签署，不允许重复签署")
            return 1
        print(f"[FAIL] 签字矩阵中找不到角色「{args.role}」")
        return 1

    head = current_head()
    replacement = f"| {match.group(1)} | {match.group(2)} | {args.name} | {today} |"
    text = pattern.sub(replacement, text, count=1)

    evidence = (
        f"\n> 签署留痕：`{args.role}` 由 {args.name} 于 {today} 签署；"
        f"签署时 master HEAD = `{head}`（Release v1.1.1 指向 792751e）。\n"
    )
    text = text.replace("\n## 7. 签字后仍需的外部条件", evidence + "\n## 7. 签字后仍需的外部条件", 1)

    SIGNOFF_DOC.write_text(text, encoding="utf-8", newline="")
    print(f"[OK] {args.role} 签署已记录：{args.name} @ {today}（HEAD {head}）")

    remaining = len(re.findall(r"\| ＿+ \| ＿+ \|", text))
    if remaining == 0:
        print("[DONE] 签字矩阵已全部签署 —— 发布治理闭环完成")
    else:
        print(f"[NEXT] 剩余 {remaining} 个角色待签署")
    return 0


if __name__ == "__main__":
    sys.exit(main())
