"""Prometheus 指标 + /metrics 端点。

指标：
  xagent_http_requests_total{method,path,status}
  xagent_agent_runs_total{role}
  xagent_agent_run_seconds{role}
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram, generate_latest

http_requests = Counter(
    "xagent_http_requests_total",
    "HTTP 请求总数",
    ["method", "path", "status"],
)
agent_runs = Counter(
    "xagent_agent_runs_total",
    "Agent 运行总数",
    ["role"],
)
agent_run_seconds = Histogram(
    "xagent_agent_run_seconds",
    "Agent 运行耗时",
    ["role"],
)


def metrics_output() -> bytes:
    return generate_latest()
