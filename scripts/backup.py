#!/usr/bin/env python
"""数据备份脚本：Postgres + Qdrant + 审计链。

用法：
  python scripts/backup.py --pg-url "postgresql://..." --qdrant-url "http://..." --output ./backups
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone


def backup_postgres(pg_url: str, output_dir: str) -> str | None:
    """pg_dump 备份 Postgres。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"pg_backup_{ts}.sql")
    try:
        subprocess.run(
            ["pg_dump", pg_url, "-f", path],
            check=True, capture_output=True,
        )
        print(f"✅ Postgres 备份: {path} ({os.path.getsize(path)} bytes)")
        return path
    except Exception as exc:
        print(f"❌ Postgres 备份失败: {exc}")
        return None


def backup_qdrant(qdrant_url: str, output_dir: str) -> str | None:
    """Qdrant collection 快照（通过 HTTP API）。"""
    import httpx

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    try:
        # 创建快照
        resp = httpx.post(f"{qdrant_url}/collections/xagent_memory/snapshots", timeout=60)
        resp.raise_for_status()
        snap_name = resp.json().get("result", {}).get("name", f"snap_{ts}")
        # 下载快照
        dl = httpx.get(
            f"{qdrant_url}/collections/xagent_memory/snapshots/{snap_name}",
            timeout=300,
        )
        dl.raise_for_status()
        path = os.path.join(output_dir, f"qdrant_{ts}.snapshot")
        with open(path, "wb") as f:
            f.write(dl.content)
        print(f"✅ Qdrant 备份: {path} ({os.path.getsize(path)} bytes)")
        return path
    except Exception as exc:
        print(f"❌ Qdrant 备份失败: {exc}")
        return None


def backup_audit(api_url: str, token: str, output_dir: str) -> str | None:
    """审计链导出（通过 API）。"""
    import httpx

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    try:
        resp = httpx.get(
            f"{api_url}/api/v1/audit/export",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        resp.raise_for_status()
        path = os.path.join(output_dir, f"audit_{ts}.json")
        with open(path, "wb") as f:
            f.write(resp.content)
        print(f"✅ 审计链备份: {path} ({os.path.getsize(path)} bytes)")
        return path
    except Exception as exc:
        print(f"❌ 审计链备份失败: {exc}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="X-Agent 数据备份")
    ap.add_argument("--pg-url", default=os.environ.get("XAGENT_DB__URL", ""))
    ap.add_argument("--qdrant-url", default=os.environ.get("XAGENT_MEMORY__QDRANT_URL", ""))
    ap.add_argument("--api-url", default="http://localhost:8000")
    ap.add_argument("--token", default="")
    ap.add_argument("--output", default="./backups")
    ap.add_argument("--retain", type=int, default=7, help="保留最近 N 份备份（默认 7）")
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)
    ok = True

    if args.pg_url:
        if backup_postgres(args.pg_url, args.output) is None:
            ok = False
    if args.qdrant_url:
        if backup_qdrant(args.qdrant_url, args.output) is None:
            ok = False
    if args.token:
        if backup_audit(args.api_url, args.token, args.output) is None:
            ok = False

    # 保留策略：删除超出 N 份的旧备份
    _cleanup_old_backups(args.output, args.retain)

    print("\n" + ("✅ 备份完成" if ok else "❌ 部分备份失败"))
    return 0 if ok else 1


def _cleanup_old_backups(output_dir: str, retain: int) -> None:
    """按文件修改时间保留最近 N 份，删除更早的。"""
    from pathlib import Path

    p = Path(output_dir)
    files = sorted(p.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)
    for old in files[retain:]:
        if old.is_file():
            old.unlink()
            print(f"🗑️ 已清理旧备份: {old.name}")


if __name__ == "__main__":
    sys.exit(main())
