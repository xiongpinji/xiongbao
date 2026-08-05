"""Prometheus 指标 + /metrics 端点。

指标：
  xagent_http_requests_total{method,path,status}
  xagent_agent_runs_total{role}
  xagent_agent_run_seconds{role}
  xagent_llm_requests_total{provider,status}
  xagent_llm_request_seconds{provider}
  xagent_worker_queue_depth
  xagent_worker_task_seconds{task_name}
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest

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

# --- LLM 指标 ---
llm_requests = Counter(
    "xagent_llm_requests_total",
    "LLM 调用总数",
    ["provider", "status"],  # status: success | timeout | error
)
llm_request_seconds = Histogram(
    "xagent_llm_request_seconds",
    "LLM 调用耗时",
    ["provider"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

# --- Worker 指标 ---
worker_queue_depth = Gauge(
    "xagent_worker_queue_depth",
    "Celery 队列当前深度",
)
worker_task_seconds = Histogram(
    "xagent_worker_task_seconds",
    "Worker 任务执行耗时",
    ["task_name"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600),
)


def metrics_output() -> bytes:
    return generate_latest()
