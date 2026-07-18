from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import Any


def build_release_package(
    goal_id: str,
    branch_name: str,
    commit_sha: str,
    pr_number: str,
    ci_run: dict[str, Any],
    evidence_paths: Sequence[str],
) -> dict[str, Any]:
    return {
        "goal_id": goal_id,
        "candidate": {
            "branch_name": branch_name,
            "commit_sha": commit_sha,
            "pr_number": pr_number,
        },
        "review": {
            "ci_run": deepcopy(ci_run),
            "status": "ready",
        },
        "evidence": list(evidence_paths),
    }
