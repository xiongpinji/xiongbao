from __future__ import annotations

import uuid

from xagent.core.spine.models import DeliveryTask, Goal, Initiative

INITIATIVE_BLUEPRINTS = [
    "Goal / Taskboard / Session Core",
    "Execution Environment Orchestrator",
    "PR / Review / Release Packaging Core",
    "Deploy / Verify / Recover Core",
    "Control / Policy / Safety Core",
    "Evidence / Archive / Continuous Learning Core",
]


def create_goal(*, tenant_id: str, owner_id: str, title: str, description: str) -> Goal:
    return Goal(
        goal_id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        owner_id=owner_id,
        title=title,
        description=description,
    )


def decompose_goal(goal: Goal) -> tuple[list[Initiative], list[DeliveryTask]]:
    initiatives: list[Initiative] = []
    tasks: list[DeliveryTask] = []
    for title in INITIATIVE_BLUEPRINTS:
        initiative = Initiative(
            initiative_id=uuid.uuid4().hex,
            goal_id=goal.goal_id,
            tenant_id=goal.tenant_id,
            title=title,
        )
        initiatives.append(initiative)
        tasks.append(
            DeliveryTask(
                task_id=uuid.uuid4().hex,
                initiative_id=initiative.initiative_id,
                goal_id=goal.goal_id,
                tenant_id=goal.tenant_id,
                title=f"Initialize {title}",
                detail=f"Bootstrap the first execution path for {title}",
            )
        )
    return initiatives, tasks
