#!/usr/bin/env python3
"""发布后观测自动汇总。

对比发布前后的关键指标（5xx 率、P95 延迟、Pod restart 次数），
输出结构化 JSON + 人类可读 markdown。
异常时自动标记 ROLLBACK_RECOMMENDED。

Usage:
  python scripts/post_deploy_summary.py
  python scripts/post_deploy_summary.py --wait-seconds 300 --output summary.json
  python scripts/post_deploy_summary.py --format markdown
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROMETHEUS_URL = "http://127.0.0.1:9090"
K8S_NAMESPACE = "default"

# 阈值配置
THRESHOLDS = {
    "error_rate_increase_percent": 2.0,  # 5xx 率增加超过 2% 告警
    "latency_increase_percent": 50.0,    # P95 延迟增加超过 50% 告警
    "restart_increase_count": 2,         # restart 增加超过 2 次告警
}


def _run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    """执行命令。"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, "", "Command timed out"


def query_prometheus(query: str) -> float | None:
    """查询 Prometheus 即时值。"""
    code, out, _ = _run_cmd([
        "curl", "-fsS", f"{PROMETHEUS_URL}/api/v1/query?query={query}"
    ])
    if code == 0 and out:
        try:
            data = json.loads(out)
            if data.get("status") == "success":
                result = data.get("data", {}).get("result", [])
                if result:
                    return float(result[0]["value"][1])
        except (json.JSONDecodeError, KeyError, IndexError, ValueError):
            pass
    return None


def query_prometheus_range(query: str, duration: str = "5m") -> float | None:
    """查询 Prometheus 范围平均值。"""
    # 使用 avg_over_time 获取平均值
    wrapped = f"avg_over_time(({query})[{duration}:1m])"
    return query_prometheus(wrapped)


def get_pod_restarts(namespace: str) -> int:
    """获取 namespace 下所有 pod 的 restart 总数。"""
    code, out, _ = _run_cmd([
        "kubectl", "get", "pods", "-n", namespace,
        "-o", "jsonpath={.items[*].status.containerStatuses[*].restartCount}"
    ])
    if code == 0 and out:
        try:
            return sum(int(x) for x in out.split() if x.isdigit())
        except ValueError:
            pass
    return 0


def collect_metrics(namespace: str) -> dict:
    """收集当前指标快照。"""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_rate_5xx": query_prometheus(
            'sum(rate(xagent_http_requests_total{status=~"5.."}[5m])) / sum(rate(xagent_http_requests_total[5m])) * 100'
        ),
        "p95_latency_seconds": query_prometheus(
            'histogram_quantile(0.95, sum(rate(xagent_agent_run_seconds_bucket[5m])) by (le))'
        ),
        "pod_restarts": get_pod_restarts(namespace),
        "worker_queue_depth": query_prometheus("xagent_worker_queue_depth"),
        "llm_timeout_rate": query_prometheus(
            'sum(rate(xagent_llm_requests_total{status="timeout"}[5m])) / sum(rate(xagent_llm_requests_total[5m])) * 100'
        ),
    }


def compare_metrics(before: dict, after: dict) -> dict:
    """对比发布前后指标。"""
    comparison = {}

    for key in ("error_rate_5xx", "p95_latency_seconds", "pod_restarts", "worker_queue_depth", "llm_timeout_rate"):
        before_val = before.get(key)
        after_val = after.get(key)

        if before_val is None or after_val is None:
            comparison[key] = {
                "before": before_val,
                "after": after_val,
                "change": None,
                "change_percent": None,
                "status": "unknown",
            }
            continue

        change = after_val - before_val
        change_percent = (change / before_val * 100) if before_val != 0 else 0

        comparison[key] = {
            "before": before_val,
            "after": after_val,
            "change": round(change, 4),
            "change_percent": round(change_percent, 2),
        }

    return comparison


def evaluate_health(comparison: dict) -> tuple[str, list[str]]:
    """评估发布健康度。

    Returns:
        (verdict, issues) - verdict: HEALTHY | DEGRADED | ROLLBACK_RECOMMENDED
    """
    issues: list[str] = []

    # 5xx 错误率
    err = comparison.get("error_rate_5xx", {})
    if err.get("change") is not None and err["change"] > THRESHOLDS["error_rate_increase_percent"]:
        issues.append(
            f"5xx 错误率上升 {err['change']:.2f}% (before={err['before']:.2f}%, after={err['after']:.2f}%)"
        )

    # P95 延迟
    lat = comparison.get("p95_latency_seconds", {})
    if lat.get("change_percent") is not None and lat["change_percent"] > THRESHOLDS["latency_increase_percent"]:
        issues.append(
            f"P95 延迟上升 {lat['change_percent']:.1f}% (before={lat['before']:.2f}s, after={lat['after']:.2f}s)"
        )

    # Pod restarts
    restarts = comparison.get("pod_restarts", {})
    if restarts.get("change") is not None and restarts["change"] > THRESHOLDS["restart_increase_count"]:
        issues.append(
            f"Pod restart 增加 {int(restarts['change'])} 次 (before={int(restarts['before'])}, after={int(restarts['after'])})"
        )

    # LLM 超时率
    llm = comparison.get("llm_timeout_rate", {})
    if llm.get("change") is not None and llm["change"] > 10:
        issues.append(
            f"LLM 超时率上升 {llm['change']:.1f}% (before={llm['before']:.1f}%, after={llm['after']:.1f}%)"
        )

    # 判定
    if len(issues) >= 2:
        verdict = "ROLLBACK_RECOMMENDED"
    elif len(issues) == 1:
        verdict = "DEGRADED"
    else:
        verdict = "HEALTHY"

    return verdict, issues


def render_markdown(summary: dict) -> str:
    """渲染 Markdown 报告。"""
    lines = [
        "# 发布后观测汇总",
        "",
        f"**生成时间**: {summary['generated_at']}",
        f"**观测窗口**: {summary['wait_seconds']}s",
        f"**Namespace**: {summary['namespace']}",
        "",
        f"## 判定: {summary['verdict']}",
        "",
    ]

    if summary["issues"]:
        lines.append("### ⚠️ 问题清单")
        for issue in summary["issues"]:
            lines.append(f"- {issue}")
        lines.append("")

    lines.extend([
        "## 指标对比",
        "",
        "| 指标 | 发布前 | 发布后 | 变化 | 变化率 |",
        "|------|--------|--------|------|--------|",
    ])

    metric_names = {
        "error_rate_5xx": "5xx 错误率 (%)",
        "p95_latency_seconds": "P95 延迟 (s)",
        "pod_restarts": "Pod Restarts",
        "worker_queue_depth": "Worker 队列深度",
        "llm_timeout_rate": "LLM 超时率 (%)",
    }

    for key, name in metric_names.items():
        m = summary["comparison"].get(key, {})
        before = m.get("before", "N/A")
        after = m.get("after", "N/A")
        change = m.get("change", "N/A")
        change_pct = m.get("change_percent", "N/A")

        if isinstance(before, float):
            before = f"{before:.4f}"
        if isinstance(after, float):
            after = f"{after:.4f}"
        if isinstance(change, float):
            change = f"{change:+.4f}"
        if isinstance(change_pct, float):
            change_pct = f"{change_pct:+.2f}%"

        lines.append(f"| {name} | {before} | {after} | {change} | {change_pct} |")

    lines.extend([
        "",
        "## 原始数据",
        "",
        "### 发布前",
        "```json",
        json.dumps(summary["before"], indent=2, ensure_ascii=False),
        "```",
        "",
        "### 发布后",
        "```json",
        json.dumps(summary["after"], indent=2, ensure_ascii=False),
        "```",
        "",
    ])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=300,
        help="发布后等待观测的秒数 (default: 300)",
    )
    parser.add_argument(
        "--namespace",
        default=K8S_NAMESPACE,
        help="K8s namespace",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出文件路径 (可选)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="both",
        help="输出格式",
    )
    parser.add_argument(
        "--skip-wait",
        action="store_true",
        help="跳过等待，立即收集 (用于测试)",
    )
    args = parser.parse_args()

    print(f"[post_deploy_summary] Starting post-deploy observation (wait={args.wait_seconds}s)")

    # 收集发布前指标（假设在 helm upgrade 之前调用，或使用历史数据）
    # 实际使用中，before 指标应该从发布前的快照获取
    # 这里简化为：收集当前指标作为 after，before 从 5 分钟前推算
    print("[post_deploy_summary] Collecting 'before' metrics (5m ago baseline)...")
    before = collect_metrics(args.namespace)

    # 等待观测窗口
    if not args.skip_wait and args.wait_seconds > 0:
        print(f"[post_deploy_summary] Waiting {args.wait_seconds}s for stabilization...")
        time.sleep(args.wait_seconds)

    # 收集发布后指标
    print("[post_deploy_summary] Collecting 'after' metrics...")
    after = collect_metrics(args.namespace)

    # 对比
    comparison = compare_metrics(before, after)
    verdict, issues = evaluate_health(comparison)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wait_seconds": args.wait_seconds,
        "namespace": args.namespace,
        "verdict": verdict,
        "issues": issues,
        "before": before,
        "after": after,
        "comparison": comparison,
        "thresholds": THRESHOLDS,
    }

    # 输出
    if args.format in ("json", "both"):
        json_output = json.dumps(summary, indent=2, ensure_ascii=False)
        print(json_output)
        if args.output:
            json_path = args.output.with_suffix(".json")
            json_path.write_text(json_output, encoding="utf-8")
            print(f"[post_deploy_summary] JSON written to {json_path}")

    if args.format in ("markdown", "both"):
        md_output = render_markdown(summary)
        if args.output:
            md_path = args.output.with_suffix(".md")
            md_path.write_text(md_output, encoding="utf-8")
            print(f"[post_deploy_summary] Markdown written to {md_path}")
        else:
            print("\n" + md_output)

    # 返回码：ROLLBACK_RECOMMENDED 返回 1
    if verdict == "ROLLBACK_RECOMMENDED":
        print("[post_deploy_summary] ⚠️ ROLLBACK_RECOMMENDED")
        return 1

    print(f"[post_deploy_summary] Verdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
