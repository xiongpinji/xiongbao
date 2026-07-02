"""统一 Runtime 策略归一化 helper。"""

from __future__ import annotations

from typing import Any

_DEFAULT_ROUTE_SOURCE_BY_SOURCE = {
    "task": "fallback",
    "workflow": "planner",
    "run": "fallback",
    "unknown": "fallback",
}
_DEFAULT_SOURCE_BY_KIND = {
    "agent.run": "task",
    "repo.task": "task",
    "creative.produce": "task",
    "workflow.run": "workflow",
}
_DEFAULT_INTENT_BY_KIND = {
    "repo.task": "repo",
    "agent.run": "agent",
    "creative.produce": "creative",
    "workflow.run": "workflow",
}


def normalize_runtime_policy(policy: dict[str, Any] | None = None) -> dict[str, str]:
    payload = dict(policy or {})
    kind = str(payload.get("kind") or "").strip().lower()
    raw_source = str(payload.get("source") or "").strip().lower()
    raw_intent_type = str(payload.get("intent_type") or "").strip().lower()
    raw_route_source = str(payload.get("route_source") or "").strip().lower()

    kind_provided = bool(kind)
    known_kind = kind in _DEFAULT_SOURCE_BY_KIND if kind_provided else True
    source = raw_source or _DEFAULT_SOURCE_BY_KIND.get(kind, "unknown")
    intent_type = raw_intent_type or _DEFAULT_INTENT_BY_KIND.get(kind, "general")
    if kind_provided and not known_kind and not raw_source:
        source = "unknown"
    if kind_provided and not known_kind and not raw_intent_type:
        intent_type = "unknown"

    route_source = raw_route_source or _DEFAULT_ROUTE_SOURCE_BY_SOURCE.get(source, "fallback")

    return {
        "source": source,
        "intent_type": intent_type,
        "route_source": route_source,
    }
