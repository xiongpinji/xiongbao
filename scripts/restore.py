#!/usr/bin/env python
"""数据恢复脚本：从备份文件恢复 Postgres + Qdrant。

用法：
  # 恢复 Postgres
  python scripts/restore.py --pg-url "postgresql://..." --pg-backup ./backups/pg_backup_20260726.sql

  # 恢复 Qdrant 快照
  python scripts/restore.py --qdrant-url "http://..." --qdrant-backup ./backups/qdrant_20260726.snapshot

  # 列出可用备份
  python scripts/restore.py --list ./backups
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def list_backups(backup_dir: str) -> None:
    """列出备份目录中的可用备份。"""
    p = Path(backup_dir)
    if not p.exists():
        print(f"❌ 目录不存在: {backup_dir}")
        return

    files = sorted(p.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        print("（无备份文件）")
        return

    print(f"📂 备份目录: {backup_dir}\n")
    print(f"{'文件名':<45} {'大小':>10} {'修改时间'}")
    print("-" * 80)
    for f in files:
        if f.is_file():
            size = f.stat().st_size
            size_str = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
            from datetime import datetime
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            print(f"{f.name:<45} {size_str:>10} {mtime}")


def restore_postgres(pg_url: str, backup_file: str) -> bool:
    """从 SQL dump 恢复 Postgres。"""
    if not os.path.isfile(backup_file):
        print(f"❌ 备份文件不存在: {backup_file}")
        return False

    print(f"⏳ 正在恢复 Postgres: {backup_file}")
    try:
        with open(backup_file, "r", encoding="utf-8") as f:
            subprocess.run(
                ["psql", pg_url],
                stdin=f,
                check=True,
                capture_output=True,
            )
        print(f"✅ Postgres 恢复完成: {backup_file}")
        return True
    except subprocess.CalledProcessError as exc:
        print(f"❌ Postgres 恢复失败: {exc.stderr.decode()[:500]}")
        return False
    except Exception as exc:
        print(f"❌ Postgres 恢复失败: {exc}")
        return False


def restore_qdrant(qdrant_url: str, backup_file: str) -> bool:
    """从快照恢复 Qdrant collection。"""
    import httpx

    if not os.path.isfile(backup_file):
        print(f"❌ 备份文件不存在: {backup_file}")
        return False

    print(f"⏳ 正在恢复 Qdrant: {backup_file}")
    try:
        collection = "xagent_memory"
        # 1. 删除现有 collection（危险操作，需确认）
        resp = httpx.delete(f"{qdrant_url}/collections/{collection}", timeout=30)
        if resp.status_code not in (200, 404):
            print(f"⚠️ 删除旧 collection 返回: {resp.status_code}")

        # 2. 重建 collection
        resp = httpx.put(
            f"{qdrant_url}/collections/{collection}",
            json={"vectors": {"size": 384, "distance": "Cosine"}},
            timeout=30,
        )
        resp.raise_for_status()

        # 3. 上传快照
        with open(backup_file, "rb") as f:
            resp = httpx.post(
                f"{qdrant_url}/collections/{collection}/snapshots/upload",
                files={"snapshot": f},
                timeout=300,
            )
            resp.raise_for_status()

        print(f"✅ Qdrant 恢复完成: {backup_file}")
        return True
    except Exception as exc:
        print(f"❌ Qdrant 恢复失败: {exc}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="X-Agent 数据恢复")
    ap.add_argument("--pg-url", default=os.environ.get("XAGENT_DB__URL", ""))
    ap.add_argument("--pg-backup", default="", help="Postgres SQL dump 文件路径")
    ap.add_argument("--qdrant-url", default=os.environ.get("XAGENT_MEMORY__QDRANT_URL", ""))
    ap.add_argument("--qdrant-backup", default="", help="Qdrant 快照文件路径")
    ap.add_argument("--list", default="", help="列出指定目录的备份")
    args = ap.parse_args()

    if args.list:
        list_backups(args.list)
        return 0

    ok = True
    if args.pg_backup:
        if not args.pg_url:
            print("❌ 需要 --pg-url 参数")
            return 1
        if not restore_postgres(args.pg_url, args.pg_backup):
            ok = False

    if args.qdrant_backup:
        if not args.qdrant_url:
            print("❌ 需要 --qdrant-url 参数")
            return 1
        if not restore_qdrant(args.qdrant_url, args.qdrant_backup):
            ok = False

    if not args.pg_backup and not args.qdrant_backup:
        print("请指定 --pg-backup 或 --qdrant-backup，或用 --list 查看可用备份")
        return 1

    print("\n" + ("✅ 恢复完成" if ok else "❌ 部分恢复失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
