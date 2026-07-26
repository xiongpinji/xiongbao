#!/usr/bin/env python3
"""Collect minimal ops evidence for xagent roadmap v2.

This script captures a small, repeatable snapshot of runtime health and
service state that can be attached to incident handling or release evidence.

Usage:
  python scripts/collect_ops_evidence.py --output ops-evidence.txt
  python scripts/collect_ops_evidence.py --output ops-evidence.json --format json
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_DIR = REPO_ROOT / "deploy" / "compose"
PROMETHEUS_URL = "http://127.0.0.1:9090"


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


def _run_json(cmd: list[str], *, cwd: Path | None = None) -> dict:
    """Run command and return structured result."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=cwd)
    except FileNotFoundError as exc:
        return {"command": " ".join(cmd), "error": str(exc), "exit_code": -1}
    return {
        "command": " ".join(cmd),
        "exit_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip() if result.stderr else None,
    }


def _query_prometheus(query: str) -> dict:
    """Query Prometheus API and return result."""
    result = _run_json([
        "curl", "-fsS", f"{PROMETHEUS_URL}/api/v1/query?query={query}"
    ])
    if result.get("exit_code") == 0 and result.get("stdout"):
        try:
            data = json.loads(result["stdout"])
            if data.get("status") == "success":
                values = data.get("data", {}).get("result", [])
                return {"value": values[0]["value"][1] if values else None, "raw_count": len(values)}
        except (json.JSONDecodeError, KeyError, IndexError):
            pass
    return {"value": None, "error": result.get("stderr") or "query failed"}


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
    lines.append("## prometheus_metrics")
    lines.append(_collect_prometheus_text())
    return "\n".join(lines)


def _collect_prometheus_text() -> str:
    """Collect Prometheus metrics as text."""
    queries = {
        "error_rate_5xx": 'sum(rate(xagent_http_requests_total{status=~"5.."}[5m])) / sum(rate(xagent_http_requests_total[5m])) * 100',
        "p95_latency": 'histogram_quantile(0.95, sum(rate(xagent_agent_run_seconds_bucket[5m])) by (le))',
        "worker_queue_depth": "xagent_worker_queue_depth",
    }
    lines = []
    for name, query in queries.items():
        result = _query_prometheus(query)
        lines.append(f"{name}: {result.get('value', 'N/A')}")
    return "\n".join(lines)


def build_report_json() -> dict:
    """Build structured JSON report."""
    report: dict = {
        "version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "health": {},
        "ready": {},
        "compose": {},
        "logs": {},
        "prometheus": {},
    }

    # Health endpoints
    report["health"] = _run_json(["curl", "-fsS", "http://127.0.0.1:8000/health"])
    report["ready"] = _run_json(["curl", "-fsS", "http://127.0.0.1:8000/ready"])

    # Compose state
    report["compose"]["ps"] = _run_json(["docker", "compose", "ps"], cwd=COMPOSE_DIR)

    # Logs (tail 50)
    for svc in ("api", "worker", "web"):
        report["logs"][svc] = _run_json(
            ["docker", "compose", "logs", "--tail=50", svc], cwd=COMPOSE_DIR
        )

    # Prometheus metrics
    queries = {
        "error_rate_5xx": 'sum(rate(xagent_http_requests_total{status=~"5.."}[5m])) / sum(rate(xagent_http_requests_total[5m])) * 100',
        "p95_latency": 'histogram_quantile(0.95, sum(rate(xagent_agent_run_seconds_bucket[5m])) by (le))',
        "worker_queue_depth": "xagent_worker_queue_depth",
        "llm_timeout_rate": 'sum(rate(xagent_llm_requests_total{status="timeout"}[5m])) / sum(rate(xagent_llm_requests_total[5m])) * 100',
    }
    for name, query in queries.items():
        report["prometheus"][name] = _query_prometheus(query)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ops-evidence.txt"),
        help="Write the snapshot to this file.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format: text (human-readable) or json (structured).",
    )
    args = parser.parse_args()

    if args.format == "json":
        report = build_report_json()
        output = json.dumps(report, indent=2, ensure_ascii=False)
    else:
        output = build_report()

    args.output.write_text(output, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
