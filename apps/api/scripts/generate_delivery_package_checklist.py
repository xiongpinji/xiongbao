#!/usr/bin/env python3
"""Generate a standard delivery package checklist for xagent.

This script emits a normalized list of the current delivery artifacts so the
commercial replication track has a reusable machine-generated package index.
"""

from __future__ import annotations

import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS = REPO_ROOT / "docs"

PACKAGE_ITEMS = [
    ("管理员部署手册", DOCS / "ADMIN_DEPLOYMENT_MANUAL_V1.md"),
    ("运维手册", DOCS / "OPERATIONS_MANUAL_V1.md"),
    ("升级 / 回滚说明", DOCS / "RELEASE_RUNBOOK_V1.md"),
    ("已知问题 / 试点边界", DOCS / "KNOWN_ISSUES_AND_PILOT_BOUNDARIES_V1.md"),
    ("支持与故障升级路径", DOCS / "SUPPORT_ESCALATION_PATH_V1.md"),
    ("交付材料索引", DOCS / "DELIVERY_MATERIALS_INDEX_V1.md"),
]


def build_report() -> str:
    lines = ["# xagent standard delivery package", ""]
    for title, path in PACKAGE_ITEMS:
        status = "READY" if path.exists() else "MISSING"
        lines.append(f"- [{status}] {title} -> {path.relative_to(REPO_ROOT)}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("delivery-package-checklist.md"),
        help="Write the generated checklist to this file.",
    )
    args = parser.parse_args()

    report = build_report()
    args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
