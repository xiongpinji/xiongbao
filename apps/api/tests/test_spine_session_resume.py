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


def test_choose_next_action_prefers_recovery_column() -> None:
    snapshot = {
        "goal": {"phase": "recovery", "status": "active"},
        "columns": {
            "recovery": [
                {
                    "task_id": "t-9",
                    "title": "Rollback deploy",
                    "blocker_reason": "rollback running",
                }
            ],
        },
    }

    action = choose_next_action(snapshot)

    assert action == {
        "kind": "recovery",
        "task_id": "t-9",
        "reason": "rollback running",
    }


def test_choose_next_action_follows_in_progress_task() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "columns": {
            "in_progress": [
                {
                    "task_id": "t-4",
                    "title": "Run checks",
                    "run_id": "run-4",
                }
            ],
        },
    }

    action = choose_next_action(snapshot)

    assert action == {
        "kind": "follow",
        "task_id": "t-4",
    }


def test_choose_next_action_releases_release_ready_task() -> None:
    snapshot = {
        "goal": {"phase": "release", "status": "active"},
        "columns": {
            "release_ready": [{"task_id": "t-5", "title": "Cut release"}],
        },
    }

    action = choose_next_action(snapshot)

    assert action == {
        "kind": "release",
        "task_id": "t-5",
    }


def test_choose_next_action_monitors_deploying_task() -> None:
    snapshot = {
        "goal": {"phase": "deploy", "status": "active"},
        "columns": {
            "deploying": [{"task_id": "t-6", "title": "Deploy app"}],
        },
    }

    action = choose_next_action(snapshot)

    assert action == {
        "kind": "monitor",
        "task_id": "t-6",
    }


def test_choose_next_action_monitors_verifying_task() -> None:
    snapshot = {
        "goal": {"phase": "deploy", "status": "active"},
        "columns": {
            "verifying": [{"task_id": "t-7", "title": "Verify app"}],
        },
    }

    action = choose_next_action(snapshot)

    assert action == {
        "kind": "monitor",
        "task_id": "t-7",
    }


def test_choose_next_action_follows_ready_task_with_run_id() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "columns": {
            "ready": [
                {
                    "task_id": "t-8",
                    "title": "Continue run",
                    "run_id": "run-8",
                }
            ],
        },
    }

    action = choose_next_action(snapshot)

    assert action == {
        "kind": "follow",
        "task_id": "t-8",
    }


def test_choose_next_action_executes_ready_task_when_no_higher_priority_work() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "columns": {
            "blocked": [],
            "review": [],
            "ready": [{"task_id": "t-2", "title": "Write docs"}],
        },
    }

    action = choose_next_action(snapshot)

    assert action == {
        "kind": "execute",
        "task_id": "t-2",
    }


def test_choose_next_action_returns_idle_when_columns_are_empty() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "columns": {},
    }

    action = choose_next_action(snapshot)

    assert action == {"kind": "idle"}


def test_choose_next_action_in_deploy_phase_prefers_active_deploy_work() -> None:
    snapshot = {
        "goal": {"phase": "deploy", "status": "active"},
        "columns": {
            "blocked": [
                {
                    "task_id": "t-old",
                    "title": "Old blocker",
                    "blocker_reason": "stale planning issue",
                }
            ],
            "verifying": [{"task_id": "t-10", "title": "Verify deploy"}],
            "ready": [{"task_id": "t-11", "title": "Write docs"}],
        },
    }

    action = choose_next_action(snapshot)

    assert action == {
        "kind": "monitor",
        "task_id": "t-10",
    }


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

    assert [task["task_id"] for task in summary["columns"]["release_ready"]] == ["t-release"]
    assert summary["next_action"] == {
        "kind": "release",
        "task_id": "t-release",
    }
