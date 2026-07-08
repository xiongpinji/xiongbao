from __future__ import annotations

from xagent.infra.models.spine import (
    DeliveryTaskORM,
    GoalORM,
    InitiativeORM,
    ReleaseRecordORM,
)


def test_spine_models_exist() -> None:
    assert GoalORM.__tablename__ == "delivery_goals"
    assert InitiativeORM.__tablename__ == "delivery_initiatives"
    assert DeliveryTaskORM.__tablename__ == "delivery_tasks"
    assert ReleaseRecordORM.__tablename__ == "release_records"
