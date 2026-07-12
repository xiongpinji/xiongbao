from __future__ import annotations

from xagent.core.spine.service import summarize_goal_board
from xagent.core.spine.session import choose_next_action


def test_choose_next_action_prefers_blocked_recovery() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "columns": {
            "blocked": [
                {
                    "task_id": "t-1",
                    "title": "Fix deploy",
                    "blocker_reason": "verify failed",
                }
            ],
            "ready": [{"task_id": "t-2", "title": "Write docs"}],
        },
    }

    action = choose_next_action(snapshot)

    assert action == {
        "kind": "recovery",
        "task_id": "t-1",
        "reason": "verify failed",
    }


def test_summarize_goal_board_includes_next_action() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "columns": {
            "blocked": [],
            "review": [{"task_id": "t-3", "title": "Check PR"}],
            "ready": [{"task_id": "t-2", "title": "Write docs"}],
        },
    }

    summary = summarize_goal_board(snapshot)

    assert summary == {
        "goal": snapshot["goal"],
        "columns": snapshot["columns"],
        "next_action": {
            "kind": "review",
            "task_id": "t-3",
        },
    }
