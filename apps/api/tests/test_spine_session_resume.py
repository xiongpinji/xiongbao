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


def test_choose_next_action_falls_back_to_blocked_reason_for_empty_values() -> None:
    for blocker_reason in ("", None):
        snapshot = {
            "goal": {"phase": "execution", "status": "active"},
            "columns": {
                "blocked": [
                    {
                        "task_id": "t-empty",
                        "title": "Fix deploy",
                        "blocker_reason": blocker_reason,
                    }
                ],
            },
        }

        action = choose_next_action(snapshot)

        assert action == {
            "kind": "recovery",
            "task_id": "t-empty",
            "reason": "blocked",
        }


def test_choose_next_action_reviews_review_task() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "columns": {
            "review": [{"task_id": "t-3", "title": "Check PR"}],
        },
    }

    action = choose_next_action(snapshot)

    assert action == {
        "kind": "review",
        "task_id": "t-3",
    }


def test_choose_next_action_executes_ready_task_when_no_higher_priority_work() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "columns": {
            "blocked": [],
            "review": [],
            "ready": [{"task_id": "t-2", "title": "Write docs", "run_id": "run-2"}],
        },
    }

    action = choose_next_action(snapshot)

    assert action == {
        "kind": "execute",
        "task_id": "t-2",
    }


def test_choose_next_action_returns_idle_when_no_supported_columns_have_tasks() -> None:
    snapshot = {
        "goal": {"phase": "deploy", "status": "active"},
        "columns": {
            "in_progress": [{"task_id": "t-4", "title": "Run checks", "run_id": "run-4"}],
            "deploying": [{"task_id": "t-6", "title": "Deploy app"}],
            "release_ready": [{"task_id": "t-5", "title": "Cut release"}],
        },
    }

    action = choose_next_action(snapshot)

    assert action == {"kind": "idle"}


def test_summarize_goal_board_includes_review_next_action() -> None:
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
        "unknown_status_tasks": [],
        "next_action": {
            "kind": "review",
            "task_id": "t-3",
        },
    }


def test_summarize_goal_board_defaults_missing_fields_to_empty_board() -> None:
    summary = summarize_goal_board({})

    assert summary == {
        "goal": {},
        "columns": {},
        "unknown_status_tasks": [],
        "next_action": {"kind": "idle"},
    }


def test_summarize_goal_board_groups_persisted_snapshot_tasks() -> None:
    snapshot = {
        "goal": {"phase": "release", "status": "active"},
        "initiatives": [{"initiative_id": "i-1", "title": "Release"}],
        "tasks": [
            {
                "task_id": "t-old",
                "title": "Old blocker",
                "status": "blocked",
                "blocker_reason": "stale planning issue",
            },
            {
                "task_id": "t-release",
                "title": "Cut release",
                "status": "release_ready",
                "run_id": "",
            },
        ],
    }

    summary = summarize_goal_board(snapshot)

    assert [task["task_id"] for task in summary["columns"]["blocked"]] == ["t-old"]
    assert [task["task_id"] for task in summary["columns"]["release_ready"]] == ["t-release"]
    assert summary["unknown_status_tasks"] == []
    assert summary["next_action"] == {
        "kind": "recovery",
        "task_id": "t-old",
        "reason": "stale planning issue",
    }


def test_summarize_goal_board_rebuilds_from_tasks_when_columns_are_empty() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "columns": {},
        "tasks": [
            {
                "task_id": "t-1",
                "title": "Blocked task",
                "status": "blocked",
                "blocker_reason": "need rollback",
            },
            {
                "task_id": "t-2",
                "title": "Ready task",
                "status": "ready",
                "run_id": "",
            },
        ],
    }

    summary = summarize_goal_board(snapshot)

    assert [task["task_id"] for task in summary["columns"]["blocked"]] == ["t-1"]
    assert [task["task_id"] for task in summary["columns"]["ready"]] == ["t-2"]
    assert summary["next_action"] == {
        "kind": "recovery",
        "task_id": "t-1",
        "reason": "need rollback",
    }


def test_summarize_goal_board_rebuilds_from_tasks_when_columns_have_only_empty_lists() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "columns": {"blocked": [], "review": [], "ready": []},
        "tasks": [
            {
                "task_id": "t-10",
                "title": "Blocked task",
                "status": "blocked",
                "blocker_reason": "pipeline failed",
            },
            {
                "task_id": "t-11",
                "title": "Ready task",
                "status": "ready",
                "run_id": "",
            },
        ],
    }

    summary = summarize_goal_board(snapshot)

    assert [task["task_id"] for task in summary["columns"]["blocked"]] == ["t-10"]
    assert [task["task_id"] for task in summary["columns"]["ready"]] == ["t-11"]
    assert summary["next_action"] == {
        "kind": "recovery",
        "task_id": "t-10",
        "reason": "pipeline failed",
    }


def test_summarize_goal_board_keeps_unknown_status_tasks_visible() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "initiatives": [{"initiative_id": "i-1", "title": "Execution"}],
        "tasks": [
            {
                "task_id": "t-future",
                "title": "Future task",
                "status": "future_status",
            },
            {
                "task_id": "t-known",
                "title": "Write docs",
                "status": "ready",
                "run_id": "",
            },
        ],
    }

    summary = summarize_goal_board(snapshot)

    assert [task["task_id"] for task in summary["unknown_status_tasks"]] == ["t-future"]
    assert [task["task_id"] for task in summary["columns"]["ready"]] == ["t-known"]
    assert summary["next_action"] == {
        "kind": "execute",
        "task_id": "t-known",
    }
