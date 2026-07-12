from __future__ import annotations


def _task_or_none(columns: dict, column: str) -> dict | None:
    tasks = columns.get(column) or []
    if not tasks:
        return None
    return tasks[0]


def _recovery_action(task: dict, *, default_reason: str) -> dict:
    return {
        "kind": "recovery",
        "task_id": task["task_id"],
        "reason": task.get("blocker_reason") or default_reason,
    }


def _ready_action(task: dict) -> dict:
    return {
        "kind": "follow" if task.get("run_id") else "execute",
        "task_id": task["task_id"],
    }


_PHASE_PRIORITIES = {
    "deploy": (
        "verifying",
        "deploying",
        "recovery",
        "blocked",
        "review",
        "release_ready",
        "in_progress",
        "ready",
    ),
    "release": (
        "release_ready",
        "recovery",
        "blocked",
        "review",
        "deploying",
        "verifying",
        "in_progress",
        "ready",
    ),
    "recovery": (
        "recovery",
        "blocked",
        "review",
        "in_progress",
        "ready",
    ),
}

_DEFAULT_PRIORITY = (
    "blocked",
    "recovery",
    "review",
    "release_ready",
    "deploying",
    "verifying",
    "in_progress",
    "ready",
)


def choose_next_action(snapshot: dict) -> dict:
    goal = snapshot.get("goal") or {}
    phase = goal.get("phase")
    columns = snapshot.get("columns") or {}
    priority = _PHASE_PRIORITIES.get(phase, _DEFAULT_PRIORITY)

    for column in priority:
        task = _task_or_none(columns, column)
        if task is None:
            continue
        if column == "blocked":
            return _recovery_action(task, default_reason="blocked")
        if column == "recovery":
            return _recovery_action(task, default_reason="recovery")
        if column == "review":
            return {"kind": "review", "task_id": task["task_id"]}
        if column == "release_ready":
            return {"kind": "release", "task_id": task["task_id"]}
        if column in {"deploying", "verifying"}:
            return {"kind": "monitor", "task_id": task["task_id"]}
        if column == "in_progress":
            return {"kind": "follow", "task_id": task["task_id"]}
        if column == "ready":
            return _ready_action(task)

    return {"kind": "idle"}
