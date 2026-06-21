#!/usr/bin/env python
"""旧 X-Agent → 新 X-Agent 数据迁移脚本（可选）。

旧仓数据多为内存/SQLite 过程产物，真正需要迁移的是：
  - 记忆向量（Qdrant collection）
  - 工作流定义（YAML/JSON）
  - 用户/租户（若旧仓有）

本脚本提供骨架：从旧仓导出 → 按新契约转换 → 写入新仓。
默认 dry-run，加 --apply 才真写。按需扩展各导入器。

用法：
  python scripts/migrate_from_legacy.py --legacy ../X-Agent [--apply]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def export_legacy_memory(legacy_root: Path) -> list[dict]:
    """从旧仓导出记忆条目。旧仓 memory 多为 SQLite/JSON，按实际位置补全。"""
    # TODO: 据旧仓实际存储补全（如读 backend/.xagent_runtime/*.sqlite）
    _ = legacy_root
    return []


def transform_to_new_contract(items: list[dict]) -> list[dict]:
    """转成新 /api/v1/memory 的写入契约。"""
    return [
        {"id": it.get("id") or it.get("memory_id", f"m{i}"),
         "text": it.get("text") or it.get("content", ""),
         "metadata": it.get("metadata", {})}
        for i, it in enumerate(items)
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy", default="../X-Agent", help="旧仓根目录")
    ap.add_argument("--api", default="http://localhost:8000", help="新后端地址")
    ap.add_argument("--token", default="", help="Bearer token（full 模式必填）")
    ap.add_argument("--apply", action="store_true", help="真写入（默认 dry-run）")
    args = ap.parse_args()

    legacy = Path(args.legacy)
    if not legacy.exists():
        print(f"旧仓不存在: {legacy}", file=sys.stderr)
        return 1

    items = export_legacy_memory(legacy)
    transformed = transform_to_new_contract(items)
    print(f"待迁移记忆条目：{len(transformed)}")
    if not transformed:
        print("无可迁移数据（旧仓多为过程产物，正常）。")
        return 0

    if not args.apply:
        print("dry-run 模式，预览前 3 条：")
        print(json.dumps(transformed[:3], ensure_ascii=False, indent=2))
        print("\n加 --apply 真写入。")
        return 0

    import httpx

    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    resp = httpx.post(
        f"{args.api}/api/v1/memory",
        json={"items": transformed},
        headers=headers,
        timeout=60,
    )
    resp.raise_for_status()
    print(f"写入完成：{resp.json()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
