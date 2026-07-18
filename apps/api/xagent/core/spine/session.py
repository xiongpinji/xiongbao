from __future__ import annotations


def choose_next_action(snapshot: dict) -> dict:
    columns = snapshot.get("columns") or {}
    blocked = columns.get("blocked") or []
    if blocked:
        task = blocked[0]
        return {
            "kind": "recovery",
            "task_id": task["task_id"],
            "reason": task.get("blocker_reason") or "blocked",
        }

    review = columns.get("review") or []
    if review:
        task = review[0]
        return {
            "kind": "review",
            "task_id": task["task_id"],
        }

    ready = columns.get("ready") or []
    if ready:
        task = ready[0]
        return {
            "kind": "execute",
            "task_id": task["task_id"],
        }

    return {"kind": "idle"}
