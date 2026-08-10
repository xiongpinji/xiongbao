#!/usr/bin/env python3
"""证据自动归档脚本。

定时收集 recovery log + ops evidence + health snapshot，
打包为带时间戳的 tar.gz，可选上传到 S3/MinIO。

Usage:
  python scripts/auto_archive_evidence.py
  python scripts/auto_archive_evidence.py --hours 12 --output-dir ./data/evidence-archive
  python scripts/auto_archive_evidence.py --s3-bucket my-bucket --s3-prefix xagent/evidence/
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = API_ROOT / "scripts"


def _run_cmd(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """执行命令并返回 (returncode, stdout, stderr)。"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, cwd=cwd, timeout=120
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, "", f"Command timed out: {' '.join(cmd)}"


def collect_health_snapshot() -> dict:
    """收集健康快照。"""
    snapshot = {
        "timestamp": datetime.now(UTC).isoformat(),
        "health": {},
        "ready": {},
    }

    # /health
    code, out, err = _run_cmd(["curl", "-fsS", "http://127.0.0.1:8000/health"])
    snapshot["health"] = {"status_code": code, "body": out, "error": err}

    # /ready
    code, out, err = _run_cmd(["curl", "-fsS", "http://127.0.0.1:8000/ready"])
    try:
        snapshot["ready"] = {"status_code": code, "body": json.loads(out) if out else {}, "error": err}
    except json.JSONDecodeError:
        snapshot["ready"] = {"status_code": code, "body": out, "error": err}

    return snapshot


def collect_recovery_logs(hours: int, evidence_dir: Path) -> list[Path]:
    """收集最近 N 小时的 recovery log 文件。"""
    files: list[Path] = []
    if not evidence_dir.exists():
        return files

    cutoff = datetime.now(UTC).timestamp() - hours * 3600

    for log_file in evidence_dir.glob("recovery-*.jsonl"):
        try:
            if log_file.stat().st_mtime >= cutoff:
                files.append(log_file)
        except OSError:
            continue

    return sorted(files)


def collect_ops_evidence(output_file: Path) -> bool:
    """调用 collect_ops_evidence.py 收集运营证据。"""
    script = SCRIPTS_DIR / "collect_ops_evidence.py"
    if not script.exists():
        return False

    code, _, err = _run_cmd(
        ["python", str(script), "--output", str(output_file), "--format", "json"],
        cwd=API_ROOT,
    )
    return code == 0


def collect_db_evidence_records(hours: int, output_file: Path) -> int:
    """导出最近 N 小时的 evidence_records（JSONL）。

    P1 证据链接通：run.summary / workflow.summary / alert:* 等自动生成的
    证据记录随归档包一起导出，供离线审计。失败（如 DB 不可达）返回 -1，
    归档继续（诚实降级，不阻断其他证据）。
    """
    import asyncio

    async def _dump() -> int:
        from datetime import datetime, timedelta

        from sqlalchemy import select
        from xagent.infra.db import get_sessionmaker
        from xagent.infra.models.evidence import EvidenceORM

        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        stmt = (
            select(EvidenceORM)
            .where(EvidenceORM.created_at >= cutoff)
            .order_by(EvidenceORM.created_at.asc())
        )
        async with get_sessionmaker()() as session:
            rows = (await session.execute(stmt)).scalars().all()
        with output_file.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps({
                    "tenant_id": r.tenant_id,
                    "evidence_id": r.evidence_id,
                    "run_id": r.run_id,
                    "task_id": r.task_id,
                    "kind": r.kind,
                    "payload": json.loads(r.payload or "{}"),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }, ensure_ascii=False) + "\n")
        return len(rows)

    try:
        return asyncio.run(_dump())
    except Exception as exc:  # noqa: BLE001 - 归档降级不阻断
        print(f"[warn] db evidence export skipped: {exc}", file=sys.stderr)
        return -1


def collect_prometheus_metrics() -> dict:
    """从 Prometheus 抓取关键指标（如果可达）。"""
    metrics = {"available": False, "data": {}}

    # 尝试从本地 Prometheus 查询
    queries = {
        "error_rate_5xx": 'sum(rate(xagent_http_requests_total{status=~"5.."}[5m])) / sum(rate(xagent_http_requests_total[5m])) * 100',
        "p95_latency": 'histogram_quantile(0.95, sum(rate(xagent_agent_run_seconds_bucket[5m])) by (le))',
        "worker_queue_depth": "xagent_worker_queue_depth",
        "llm_timeout_rate": 'sum(rate(xagent_llm_requests_total{status="timeout"}[5m])) / sum(rate(xagent_llm_requests_total[5m])) * 100',
    }

    for name, query in queries.items():
        code, out, _ = _run_cmd([
            "curl", "-fsS",
            f"http://127.0.0.1:9090/api/v1/query?query={query}"
        ])
        if code == 0 and out:
            try:
                result = json.loads(out)
                if result.get("status") == "success":
                    data = result.get("data", {}).get("result", [])
                    metrics["data"][name] = data[0]["value"][1] if data else None
                    metrics["available"] = True
            except (json.JSONDecodeError, KeyError, IndexError):
                metrics["data"][name] = None

    return metrics


def create_archive(
    hours: int,
    output_dir: Path,
    evidence_dir: Path,
) -> Path | None:
    """创建归档 tar.gz。"""
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    archive_name = f"evidence-archive-{timestamp}.tar.gz"
    archive_path = output_dir / archive_name

    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        staging = tmp_path / f"evidence-{timestamp}"
        staging.mkdir()

        # 1. Health snapshot
        health = collect_health_snapshot()
        (staging / "health-snapshot.json").write_text(
            json.dumps(health, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # 2. Recovery logs
        recovery_files = collect_recovery_logs(hours, evidence_dir)
        if recovery_files:
            recovery_dir = staging / "recovery-logs"
            recovery_dir.mkdir()
            for f in recovery_files:
                shutil.copy2(f, recovery_dir / f.name)

        # 3. Ops evidence
        ops_output = staging / "ops-evidence.json"
        collect_ops_evidence(ops_output)

        # 4. DB evidence records（P1 证据链：run.summary/workflow.summary/alert:*）
        db_evidence_output = staging / "evidence-records.jsonl"
        db_evidence_count = collect_db_evidence_records(hours, db_evidence_output)
        if db_evidence_count < 0:
            db_evidence_output.unlink(missing_ok=True)

        # 5. Prometheus metrics
        prom_metrics = collect_prometheus_metrics()
        (staging / "prometheus-metrics.json").write_text(
            json.dumps(prom_metrics, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # 6. Manifest
        manifest = {
            "archive_version": "1.1",
            "created_at": datetime.now(UTC).isoformat(),
            "hours_covered": hours,
            "contents": [
                "health-snapshot.json",
                "recovery-logs/" if recovery_files else None,
                "ops-evidence.json",
                "evidence-records.jsonl" if db_evidence_count >= 0 else None,
                "prometheus-metrics.json",
            ],
            "recovery_log_count": len(recovery_files),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # 打包
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(staging, arcname=f"evidence-{timestamp}")

    return archive_path


def upload_to_s3(archive_path: Path, bucket: str, prefix: str) -> bool:
    """上传归档到 S3/MinIO。"""
    if not bucket:
        return False

    key = f"{prefix}{archive_path.name}" if prefix else archive_path.name
    code, out, err = _run_cmd([
        "aws", "s3", "cp", str(archive_path), f"s3://{bucket}/{key}"
    ])

    if code == 0:
        print(f"Uploaded to s3://{bucket}/{key}")
        return True
    else:
        print(f"S3 upload failed: {err}")
        return False


def cleanup_old_archives(output_dir: Path, retention_days: int) -> int:
    """清理过期归档。"""
    if retention_days <= 0:
        return 0

    cutoff = datetime.now(UTC).timestamp() - retention_days * 86400
    removed = 0

    for archive in output_dir.glob("evidence-archive-*.tar.gz"):
        try:
            if archive.stat().st_mtime < cutoff:
                archive.unlink()
                removed += 1
        except OSError:
            continue

    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=6, help="收集最近 N 小时的数据")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./data/evidence-archive"),
        help="归档输出目录",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("./data/recovery-evidence"),
        help="Recovery log 目录",
    )
    parser.add_argument("--s3-bucket", default="", help="S3/MinIO bucket (可选)")
    parser.add_argument("--s3-prefix", default="xagent/evidence/", help="S3 key 前缀")
    parser.add_argument("--retention-days", type=int, default=30, help="保留天数")
    args = parser.parse_args()

    print(f"[auto_archive] Starting evidence archive (hours={args.hours})")

    # 创建归档
    archive_path = create_archive(args.hours, args.output_dir, args.evidence_dir)
    if archive_path:
        print(f"[auto_archive] Archive created: {archive_path}")
        size_mb = archive_path.stat().st_size / (1024 * 1024)
        print(f"[auto_archive] Archive size: {size_mb:.2f} MB")
    else:
        print("[auto_archive] ERROR: Failed to create archive")
        return 1

    # 上传 S3（可选）
    if args.s3_bucket:
        upload_to_s3(archive_path, args.s3_bucket, args.s3_prefix)

    # 清理旧归档
    removed = cleanup_old_archives(args.output_dir, args.retention_days)
    if removed:
        print(f"[auto_archive] Cleaned up {removed} old archive(s)")

    print("[auto_archive] Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
