#!/usr/bin/env python3
"""Collect minimal ops evidence for xagent roadmap v2.

This script captures a small, repeatable snapshot of runtime health and
service state that can be attached to incident handling or release evidence.

Usage:
  python scripts/collect_ops_evidence.py --output ops-evidence.txt
"""

from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_DIR = REPO_ROOT / "deploy" / "compose"


def _run(cmd: list[str], *, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=cwd)
    except FileNotFoundError as exc:  # pragma: no cover - environment dependent
        return f"[missing-command] {' '.join(cmd)}\n{exc}\n"
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    status = f"exit_code={result.returncode}"
    parts = [f"$ {' '.join(cmd)}", status]
    if cwd is not None:
        parts.insert(1, f"cwd={cwd}")
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(f"[stderr]\n{stderr}")
    return "\n".join(parts) + "\n"


def build_report() -> str:
    lines: list[str] = []
    lines.append("# xagent ops evidence snapshot")
    lines.append(f"generated_at={datetime.now(timezone.utc).isoformat()}")
    lines.append(f"repo_root={REPO_ROOT}")
    lines.append(f"compose_dir={COMPOSE_DIR}")
    lines.append("")
    lines.append("## health")
    lines.append(_run(["curl", "-fsS", "http://127.0.0.1:8000/health"]))
    lines.append("## ready")
    lines.append(_run(["curl", "-fsS", "http://127.0.0.1:8000/ready"]))
    lines.append("## compose_ps")
    lines.append(_run(["docker", "compose", "ps"], cwd=COMPOSE_DIR))
    lines.append("## api_logs")
    lines.append(_run(["docker", "compose", "logs", "--tail=50", "api"], cwd=COMPOSE_DIR))
    lines.append("## worker_logs")
    lines.append(_run(["docker", "compose", "logs", "--tail=50", "worker"], cwd=COMPOSE_DIR))
    lines.append("## web_logs")
    lines.append(_run(["docker", "compose", "logs", "--tail=50", "web"], cwd=COMPOSE_DIR))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ops-evidence.txt"),
        help="Write the snapshot to this file.",
    )
    args = parser.parse_args()

    report = build_report()
    args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
