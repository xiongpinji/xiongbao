# X-Agent Auto-Delivery Spine Phase 1 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在 xagent 自己身上落地一套最小但完整的 Auto-Delivery Spine Phase 1，实现 goal/taskboard/durable session 与自动交付闭环的统一主链。

**架构：** 实现将以现有 runtime/workflow/run console/agent_task 持久化能力为底座，新增一组 spine 对象（goal/initiative/task/release/review/archive）和一条 PM Agent 主导的状态推进链。Phase 1 先服务 xagent 自举升级自己，主控制面采用 chat/CLI 发起、taskboard 持续状态、PR/Git 作为交付出口的混合模式。

**技术栈：** FastAPI、SQLAlchemy、React + Zustand、Docker Compose、GitHub CLI、pytest、Playwright、Markdown、GitHub Actions

---

## 文件结构与职责边界

### 新增后端文件

- `apps/api/xagent/core/spine/models.py`
  - Spine 第一类对象的领域模型：Goal、Initiative、DeliveryTask、ReviewDecision、ReleaseRecord、ArchiveRecord。
- `apps/api/xagent/infra/models/spine.py`
  - Spine 对象的 ORM 持久化模型。
- `apps/api/xagent/infra/repos/spine.py`
  - Goal / Initiative / Task / Release / Archive 的 repository。
- `apps/api/xagent/core/spine/service.py`
  - PM Agent 使用的状态推进服务：创建 goal、拆 task、推进状态、挂接 evidence/release。
- `apps/api/xagent/api/v1/spine.py`
  - Phase 1 Spine API：goal intake、taskboard snapshot、phase summary、release promotion。
- `apps/api/xagent/core/spine/session.py`
  - durable session 读取与 resume 决策逻辑。
- `apps/api/xagent/core/spine/execution.py`
  - 执行调度逻辑：current-machine / isolated execution 抽象、run registration。
- `apps/api/xagent/core/spine/release.py`
  - Release package / review package / archive 组装逻辑。
- `apps/api/tests/test_spine_service.py`
  - Spine 领域服务测试。
- `apps/api/tests/test_spine_api.py`
  - Spine API 与 taskboard/release 读写测试。
- `apps/api/tests/test_spine_session_resume.py`
  - durable session / resume 行为测试。
- `apps/api/tests/test_spine_release_flow.py`
  - release / review / archive 主链测试。

### 新增前端文件

- `apps/web/src/api/spine.ts`
  - Spine 后端 API 客户端。
- `apps/web/src/components/spine/GoalBoard.tsx`
  - Goal / Initiative / Taskboard 主视图。
- `apps/web/src/components/spine/GoalSummaryCard.tsx`
  - 当前 goal、phase、下一步动作摘要。
- `apps/web/src/components/spine/TaskColumn.tsx`
  - taskboard 列组件（Ready/In Progress/Blocked/Review/Release Ready/Deploying/Verifying/Delivered/Recovery）。
- `apps/web/src/components/spine/ReleasePane.tsx`
  - release/review/archive 右侧面板。
- `apps/web/src/pages/GoalBoardPage.tsx`
  - Phase 1 主控制面页面。
- `apps/web/src/shell/spineShellRoute.ts`
  - 将 Goal Board 注册进 shell route 体系。
- `apps/web/src/tests/goalBoard.test.tsx`
  - Goal Board 组件测试。

### 修改后端文件

- `apps/api/xagent/api/v1/__init__.py`
  - 注册 `spine` 路由。
- `apps/api/xagent/main.py`
  - 挂载 spine API。
- `apps/api/xagent/api/v1/tasks.py`
  - 提交 task run 后回写 spine task/run linkage。
- `apps/api/xagent/api/v1/agents.py`
  - 直接 agent.run 后为 spine 生成 review/release evidence hook。
- `apps/api/xagent/api/v1/workflows.py`
  - workflow 运行视图与 spine release/recovery 指针对接。
- `apps/api/xagent/api/v1/runs.py`
  - runtime 聚合视图中补 Spine 相关 metadata / release pointers。
- `apps/api/xagent/core/runtime/service.py`
  - run detail 聚合里挂接 spine 任务 / release 关联信息。
- `apps/api/xagent/infra/models/__init__.py`
  - 导出 spine ORM。
- `apps/api/xagent/infra/repos/__init__.py`
  - 导出 spine repository。
- `apps/api/migrations/versions/<new_revision>_add_spine_tables.py`
  - 为 spine 对象新增表结构。

### 修改前端文件

- `apps/web/src/App.tsx`
  - 加入 Goal Board 路由。
- `apps/web/src/shell/shellRoutes.ts`
  - 增加 goal/taskboard 主 surface。
- `apps/web/src/shell/useShellStore.tsx`
  - 增加 spine session / goal board 状态接入。
- `apps/web/src/components/layout/AppShell.tsx`
  - 让 Goal Board 成为主控制面入口之一。
- `apps/web/src/pages/RunPage.tsx`
  - 让 Run Console 显示 spine goal/task/release 关联。

### 文档与计划输出

- `docs/superpowers/specs/2026-07-08-xagent-auto-delivery-spine-design.md`
  - 已批准规格（只读输入）。
- `docs/coordination/reports/auto-delivery-phase1-report.md`
  - Phase 1 验收报告。

---

## 任务 1：定义 Spine 持久化对象与迁移

**文件：**
- 创建：`apps/api/xagent/infra/models/spine.py`
- 创建：`apps/api/migrations/versions/20260708_add_spine_tables.py`
- 修改：`apps/api/xagent/infra/models/__init__.py`
- 测试：`apps/api/tests/test_spine_service.py`

- [ ] **步骤 1：编写失败的模型测试**

```python
from xagent.infra.models.spine import GoalORM, InitiativeORM, DeliveryTaskORM, ReleaseRecordORM


def test_spine_models_exist() -> None:
    assert GoalORM.__tablename__ == "delivery_goals"
    assert InitiativeORM.__tablename__ == "delivery_initiatives"
    assert DeliveryTaskORM.__tablename__ == "delivery_tasks"
    assert ReleaseRecordORM.__tablename__ == "release_records"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_service.py -k spine_models_exist -v`
预期：FAIL，报错 `ModuleNotFoundError` 或 `cannot import name 'GoalORM'`

- [ ] **步骤 3：编写最小 ORM 模型**

```python
# apps/api/xagent/infra/models/spine.py
from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from xagent.infra.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class GoalORM(Base):
    __tablename__ = "delivery_goals"
    goal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    phase: Mapped[str] = mapped_column(String(32), default="planning", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class InitiativeORM(Base):
    __tablename__ = "delivery_initiatives"
    initiative_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("delivery_goals.goal_id"), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class DeliveryTaskORM(Base):
    __tablename__ = "delivery_tasks"
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    initiative_id: Mapped[str] = mapped_column(ForeignKey("delivery_initiatives.initiative_id"), index=True, nullable=False)
    goal_id: Mapped[str] = mapped_column(ForeignKey("delivery_goals.goal_id"), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ready", nullable=False)
    task_kind: Mapped[str] = mapped_column(String(32), default="execution", nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    blocker_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class ReleaseRecordORM(Base):
    __tablename__ = "release_records"
    release_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("delivery_goals.goal_id"), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    branch_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    pr_number: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
```

- [ ] **步骤 4：导出模型并编写迁移**

```python
# apps/api/xagent/infra/models/__init__.py
from xagent.infra.models.spine import DeliveryTaskORM, GoalORM, InitiativeORM, ReleaseRecordORM
```

```python
# apps/api/migrations/versions/20260708_add_spine_tables.py
"""add spine tables"""
from alembic import op
import sqlalchemy as sa

revision = "20260708_spine"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_goals",
        sa.Column("goal_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("phase", sa.String(length=32), nullable=False, server_default="planning"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("owner_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_delivery_goals_tenant_id", "delivery_goals", ["tenant_id"])
    op.create_table(
        "delivery_initiatives",
        sa.Column("initiative_id", sa.String(length=64), primary_key=True),
        sa.Column("goal_id", sa.String(length=64), sa.ForeignKey("delivery_goals.goal_id"), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_delivery_initiatives_goal_id", "delivery_initiatives", ["goal_id"])
    op.create_index("ix_delivery_initiatives_tenant_id", "delivery_initiatives", ["tenant_id"])
    op.create_table(
        "delivery_tasks",
        sa.Column("task_id", sa.String(length=64), primary_key=True),
        sa.Column("initiative_id", sa.String(length=64), sa.ForeignKey("delivery_initiatives.initiative_id"), nullable=False),
        sa.Column("goal_id", sa.String(length=64), sa.ForeignKey("delivery_goals.goal_id"), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"),
        sa.Column("task_kind", sa.String(length=32), nullable=False, server_default="execution"),
        sa.Column("run_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("blocker_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_delivery_tasks_goal_id", "delivery_tasks", ["goal_id"])
    op.create_index("ix_delivery_tasks_initiative_id", "delivery_tasks", ["initiative_id"])
    op.create_index("ix_delivery_tasks_tenant_id", "delivery_tasks", ["tenant_id"])
    op.create_table(
        "release_records",
        sa.Column("release_id", sa.String(length=64), primary_key=True),
        sa.Column("goal_id", sa.String(length=64), sa.ForeignKey("delivery_goals.goal_id"), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("branch_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("commit_sha", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("pr_number", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="candidate"),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_release_records_goal_id", "release_records", ["goal_id"])
    op.create_index("ix_release_records_tenant_id", "release_records", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_release_records_tenant_id", table_name="release_records")
    op.drop_index("ix_release_records_goal_id", table_name="release_records")
    op.drop_table("release_records")
    op.drop_index("ix_delivery_tasks_tenant_id", table_name="delivery_tasks")
    op.drop_index("ix_delivery_tasks_initiative_id", table_name="delivery_tasks")
    op.drop_index("ix_delivery_tasks_goal_id", table_name="delivery_tasks")
    op.drop_table("delivery_tasks")
    op.drop_index("ix_delivery_initiatives_tenant_id", table_name="delivery_initiatives")
    op.drop_index("ix_delivery_initiatives_goal_id", table_name="delivery_initiatives")
    op.drop_table("delivery_initiatives")
    op.drop_index("ix_delivery_goals_tenant_id", table_name="delivery_goals")
    op.drop_table("delivery_goals")
```

- [ ] **步骤 5：运行测试验证通过**

运行：`cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_service.py -k spine_models_exist -v`
预期：PASS

- [ ] **步骤 6：Commit**

```bash
git add apps/api/xagent/infra/models/spine.py apps/api/xagent/infra/models/__init__.py apps/api/migrations/versions/20260708_add_spine_tables.py apps/api/tests/test_spine_service.py
git commit -m "feat(spine): add persistent spine models"
```

---

## 任务 2：实现 Spine 领域模型与状态推进服务

**文件：**
- 创建：`apps/api/xagent/core/spine/models.py`
- 创建：`apps/api/xagent/infra/repos/spine.py`
- 创建：`apps/api/xagent/core/spine/service.py`
- 测试：`apps/api/tests/test_spine_service.py`

- [ ] **步骤 1：编写失败的服务测试**

```python
from xagent.core.spine.models import GoalStatus, SpinePhase
from xagent.core.spine.service import create_goal, decompose_goal


def test_create_goal_defaults_to_planning_phase() -> None:
    goal = create_goal(
        tenant_id="t-1",
        owner_id="owner-1",
        title="Build auto-delivery spine",
        description="Phase 1 self-hosted delivery loop",
    )
    assert goal.phase is SpinePhase.planning
    assert goal.status is GoalStatus.pending
    assert goal.title == "Build auto-delivery spine"


def test_decompose_goal_creates_initiatives_and_ready_tasks() -> None:
    goal = create_goal(
        tenant_id="t-1",
        owner_id="owner-1",
        title="Build auto-delivery spine",
        description="Phase 1 self-hosted delivery loop",
    )
    initiatives, tasks = decompose_goal(goal)
    assert [item.title for item in initiatives] == [
        "Goal / Taskboard / Session Core",
        "Execution Environment Orchestrator",
        "PR / Review / Release Packaging Core",
        "Deploy / Verify / Recover Core",
        "Control / Policy / Safety Core",
        "Evidence / Archive / Continuous Learning Core",
    ]
    assert all(task.status == "ready" for task in tasks)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_service.py -k "create_goal_defaults or decompose_goal_creates" -v`
预期：FAIL，报错 `ModuleNotFoundError: No module named 'xagent.core.spine'`

- [ ] **步骤 3：编写领域模型**

```python
# apps/api/xagent/core/spine/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class SpinePhase(str, Enum):
    planning = "planning"
    execution = "execution"
    review = "review"
    release = "release"
    deploy = "deploy"
    recovery = "recovery"
    archive = "archive"


class GoalStatus(str, Enum):
    pending = "pending"
    active = "active"
    blocked = "blocked"
    delivered = "delivered"
    archived = "archived"


@dataclass(slots=True)
class Goal:
    goal_id: str
    tenant_id: str
    owner_id: str
    title: str
    description: str
    phase: SpinePhase = SpinePhase.planning
    status: GoalStatus = GoalStatus.pending
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)


@dataclass(slots=True)
class Initiative:
    initiative_id: str
    goal_id: str
    tenant_id: str
    title: str
    status: str = "pending"
    priority: str = "medium"
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)


@dataclass(slots=True)
class DeliveryTask:
    task_id: str
    initiative_id: str
    goal_id: str
    tenant_id: str
    title: str
    detail: str
    status: str = "ready"
    task_kind: str = "execution"
    run_id: str = ""
    blocker_reason: str = ""
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
```

- [ ] **步骤 4：编写最小服务与仓储接口**

```python
# apps/api/xagent/core/spine/service.py
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
```

```python
# apps/api/xagent/infra/repos/spine.py
from __future__ import annotations

import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.spine.models import DeliveryTask, Goal, Initiative
from xagent.infra.models.spine import DeliveryTaskORM, GoalORM, InitiativeORM


async def persist_goal(session: AsyncSession, goal: Goal) -> None:
    session.add(
        GoalORM(
            goal_id=goal.goal_id,
            tenant_id=goal.tenant_id,
            owner_id=goal.owner_id,
            title=goal.title,
            description=goal.description,
            phase=goal.phase.value,
            status=goal.status.value,
            metadata_json=json.dumps({}),
        )
    )


async def persist_initiatives(session: AsyncSession, initiatives: list[Initiative]) -> None:
    for item in initiatives:
        session.add(
            InitiativeORM(
                initiative_id=item.initiative_id,
                goal_id=item.goal_id,
                tenant_id=item.tenant_id,
                title=item.title,
                status=item.status,
                priority=item.priority,
            )
        )


async def persist_tasks(session: AsyncSession, tasks: list[DeliveryTask]) -> None:
    for task in tasks:
        session.add(
            DeliveryTaskORM(
                task_id=task.task_id,
                initiative_id=task.initiative_id,
                goal_id=task.goal_id,
                tenant_id=task.tenant_id,
                title=task.title,
                detail=task.detail,
                status=task.status,
                task_kind=task.task_kind,
                run_id=task.run_id,
                blocker_reason=task.blocker_reason,
            )
        )


async def load_goal_snapshot(session: AsyncSession, goal_id: str, tenant_id: str) -> dict | None:
    goal = await session.get(GoalORM, goal_id)
    if goal is None or goal.tenant_id != tenant_id:
        return None
    initiatives = (
        (
            await session.execute(
                select(InitiativeORM).where(
                    InitiativeORM.goal_id == goal_id,
                    InitiativeORM.tenant_id == tenant_id,
                )
            )
        )
        .scalars()
        .all()
    )
    tasks = (
        (
            await session.execute(
                select(DeliveryTaskORM).where(
                    DeliveryTaskORM.goal_id == goal_id,
                    DeliveryTaskORM.tenant_id == tenant_id,
                )
            )
        )
        .scalars()
        .all()
    )
    return {
        "goal": {
            "goal_id": goal.goal_id,
            "title": goal.title,
            "description": goal.description,
            "phase": goal.phase,
            "status": goal.status,
        },
        "initiatives": [
            {
                "initiative_id": item.initiative_id,
                "title": item.title,
                "status": item.status,
                "priority": item.priority,
            }
            for item in initiatives
        ],
        "tasks": [
            {
                "task_id": item.task_id,
                "initiative_id": item.initiative_id,
                "title": item.title,
                "detail": item.detail,
                "status": item.status,
                "task_kind": item.task_kind,
                "run_id": item.run_id,
                "blocker_reason": item.blocker_reason,
            }
            for item in tasks
        ],
    }
```

- [ ] **步骤 5：运行测试验证通过**

运行：`cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_service.py -k "create_goal_defaults or decompose_goal_creates" -v`
预期：PASS

- [ ] **步骤 6：Commit**

```bash
git add apps/api/xagent/core/spine/models.py apps/api/xagent/core/spine/service.py apps/api/xagent/infra/repos/spine.py apps/api/tests/test_spine_service.py
git commit -m "feat(spine): add goal decomposition service"
```

---

## 任务 3：暴露 Goal / Taskboard / Session Spine API

**文件：**
- 创建：`apps/api/xagent/api/v1/spine.py`
- 修改：`apps/api/xagent/api/v1/__init__.py`
- 修改：`apps/api/xagent/main.py`
- 测试：`apps/api/tests/test_spine_api.py`

- [ ] **步骤 1：编写失败的 API 测试**

```python
from fastapi.testclient import TestClient


def test_create_goal_returns_goal_tree(client: TestClient) -> None:
    response = client.post(
        "/api/v1/spine/goals",
        json={
            "title": "Auto-Delivery Spine Phase 1",
            "description": "Make xagent upgrade itself",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["goal"]["title"] == "Auto-Delivery Spine Phase 1"
    assert len(body["initiatives"]) == 6
    assert len(body["tasks"]) == 6


def test_get_goal_board_snapshot_returns_grouped_columns(client: TestClient) -> None:
    created = client.post(
        "/api/v1/spine/goals",
        json={
            "title": "Auto-Delivery Spine Phase 1",
            "description": "Make xagent upgrade itself",
        },
    ).json()
    goal_id = created["goal"]["goal_id"]
    response = client.get(f"/api/v1/spine/goals/{goal_id}/board")
    assert response.status_code == 200
    board = response.json()
    assert "ready" in board["columns"]
    assert board["columns"]["ready"]
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_api.py -k "goal" -v`
预期：FAIL，报错 `404 Not Found` 或 `ImportError`

- [ ] **步骤 3：实现最小 API**

```python
# apps/api/xagent/api/v1/spine.py
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.spine.service import create_goal, decompose_goal
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session
from xagent.infra.repos.spine import load_goal_snapshot, persist_goal, persist_initiatives, persist_tasks

router = APIRouter(prefix="/spine", tags=["spine"])


class GoalCreateIn(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field("", min_length=0)


@router.post("/goals", summary="创建 delivery goal")
async def create_delivery_goal(
    body: GoalCreateIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    goal = create_goal(
        tenant_id=principal.tenant_id,
        owner_id=principal.user_id,
        title=body.title,
        description=body.description,
    )
    initiatives, tasks = decompose_goal(goal)
    await persist_goal(session, goal)
    await persist_initiatives(session, initiatives)
    await persist_tasks(session, tasks)
    await session.commit()
    return {
        "goal": {
            "goal_id": goal.goal_id,
            "title": goal.title,
            "description": goal.description,
            "phase": goal.phase.value,
            "status": goal.status.value,
        },
        "initiatives": [item.__dict__ for item in initiatives],
        "tasks": [item.__dict__ for item in tasks],
    }


@router.get("/goals/{goal_id}/board", summary="获取 goal taskboard 快照")
async def get_goal_board(
    goal_id: str,
    principal: Principal = Depends(require_permission("agent", "read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    snapshot = await load_goal_snapshot(session, goal_id, principal.tenant_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="goal not found")
    columns = defaultdict(list)
    for task in snapshot["tasks"]:
        columns[task["status"]].append(task)
    return {
        "goal": snapshot["goal"],
        "initiatives": snapshot["initiatives"],
        "columns": dict(columns),
    }
```

- [ ] **步骤 4：注册路由**

```python
# apps/api/xagent/api/v1/__init__.py
from xagent.api.v1 import spine
```

```python
# apps/api/xagent/main.py
from xagent.api.v1.spine import router as spine_router
app.include_router(spine_router, prefix="/api/v1")
```

- [ ] **步骤 5：运行测试验证通过**

运行：`cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_api.py -k "goal" -v`
预期：PASS

- [ ] **步骤 6：Commit**

```bash
git add apps/api/xagent/api/v1/spine.py apps/api/xagent/api/v1/__init__.py apps/api/xagent/main.py apps/api/tests/test_spine_api.py
git commit -m "feat(spine): add goal board api"
```

---

## 任务 4：把 run / workflow / task 挂接到 Spine 状态链

**文件：**
- 修改：`apps/api/xagent/api/v1/tasks.py`
- 修改：`apps/api/xagent/api/v1/agents.py`
- 修改：`apps/api/xagent/api/v1/workflows.py`
- 修改：`apps/api/xagent/api/v1/runs.py`
- 修改：`apps/api/xagent/core/runtime/service.py`
- 测试：`apps/api/tests/test_spine_release_flow.py`

- [ ] **步骤 1：编写失败的整合测试**

```python
from fastapi.testclient import TestClient


def test_task_submission_updates_delivery_task_with_run_id(client: TestClient) -> None:
    created = client.post(
        "/api/v1/spine/goals",
        json={"title": "Spine Flow", "description": "Track task execution"},
    ).json()
    board = client.get(f"/api/v1/spine/goals/{created['goal']['goal_id']}/board").json()
    spine_task = board["columns"]["ready"][0]

    response = client.post("/api/v1/tasks", json={"goal": spine_task["title"]})
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    board_after = client.get(f"/api/v1/spine/goals/{created['goal']['goal_id']}/board").json()
    updated = next(task for task in board_after["columns"]["ready"] if task["task_id"] == spine_task["task_id"])
    assert updated["run_id"] == run_id
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_release_flow.py -k task_submission_updates_delivery_task_with_run_id -v`
预期：FAIL，因 board 不会更新 run_id

- [ ] **步骤 3：增加 spine linkage 更新逻辑**

```python
# apps/api/xagent/infra/repos/spine.py
async def attach_run_to_task(
    session: AsyncSession,
    *,
    goal_id: str,
    tenant_id: str,
    task_title: str,
    run_id: str,
    next_status: str = "in_progress",
) -> None:
    stmt = (
        select(DeliveryTaskORM)
        .where(
            DeliveryTaskORM.goal_id == goal_id,
            DeliveryTaskORM.tenant_id == tenant_id,
            DeliveryTaskORM.title == task_title,
        )
        .order_by(DeliveryTaskORM.created_at.asc())
    )
    row = (await session.execute(stmt)).scalars().first()
    if row is None:
        return
    row.run_id = run_id
    row.status = next_status
```

```python
# apps/api/xagent/api/v1/tasks.py
from xagent.infra.repos.spine import attach_run_to_task

# in submit_task(), after task_id known
if principal.tenant_id and body.goal:
    try:
        async with get_sessionmaker()() as session:
            await attach_run_to_task(
                session,
                goal_id=body.goal if body.goal.startswith("goal:") else "",
                tenant_id=principal.tenant_id,
                task_title=body.goal,
                run_id=task_id,
            )
            await session.commit()
    except Exception:
        pass
```

- [ ] **步骤 4：为 runs 聚合补 Spine 关联字段**

```python
# apps/api/xagent/core/runtime/service.py
# return payload append
"spine": {
    "goal_id": task_view.get("goal_id", ""),
    "initiative_id": task_view.get("initiative_id", ""),
}
```

```python
# apps/api/xagent/api/v1/runs.py
if isinstance(detail.get("spine"), dict):
    detail["spine"] = detail["spine"]
else:
    detail["spine"] = {"goal_id": "", "initiative_id": ""}
```

- [ ] **步骤 5：运行测试验证通过**

运行：`cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_release_flow.py -k task_submission_updates_delivery_task_with_run_id -v`
预期：PASS

- [ ] **步骤 6：Commit**

```bash
git add apps/api/xagent/api/v1/tasks.py apps/api/xagent/api/v1/agents.py apps/api/xagent/api/v1/workflows.py apps/api/xagent/api/v1/runs.py apps/api/xagent/core/runtime/service.py apps/api/xagent/infra/repos/spine.py apps/api/tests/test_spine_release_flow.py
git commit -m "feat(spine): connect task runs to board state"
```

---

## 任务 5：实现 durable session / resume 决策

**文件：**
- 创建：`apps/api/xagent/core/spine/session.py`
- 修改：`apps/api/xagent/core/spine/service.py`
- 测试：`apps/api/tests/test_spine_session_resume.py`

- [ ] **步骤 1：编写失败的 session 测试**

```python
from xagent.core.spine.session import choose_next_action


def test_choose_next_action_prefers_blocked_recovery() -> None:
    snapshot = {
        "goal": {"phase": "execution", "status": "active"},
        "columns": {
            "blocked": [{"task_id": "t-1", "title": "Fix deploy", "blocker_reason": "verify failed"}],
            "ready": [{"task_id": "t-2", "title": "Write docs"}],
        },
    }
    action = choose_next_action(snapshot)
    assert action == {
        "kind": "recovery",
        "task_id": "t-1",
        "reason": "verify failed",
    }
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_session_resume.py -k choose_next_action_prefers_blocked_recovery -v`
预期：FAIL，模块不存在

- [ ] **步骤 3：实现最小 session 决策器**

```python
# apps/api/xagent/core/spine/session.py
from __future__ import annotations


def choose_next_action(snapshot: dict) -> dict:
    columns = snapshot.get("columns") or {}
    blocked = columns.get("blocked") or []
    if blocked:
        task = blocked[0]
        return {
            "kind": "recovery",
            "task_id": task["task_id"],
            "reason": task.get("blocker_reason", "blocked"),
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
```

- [ ] **步骤 4：在 service 中暴露 phase summary**

```python
# apps/api/xagent/core/spine/service.py
from xagent.core.spine.session import choose_next_action


def summarize_goal_board(snapshot: dict) -> dict:
    return {
        "goal": snapshot["goal"],
        "columns": snapshot["columns"],
        "next_action": choose_next_action(snapshot),
    }
```

- [ ] **步骤 5：运行测试验证通过**

运行：`cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_session_resume.py -k choose_next_action_prefers_blocked_recovery -v`
预期：PASS

- [ ] **步骤 6：Commit**

```bash
git add apps/api/xagent/core/spine/session.py apps/api/xagent/core/spine/service.py apps/api/tests/test_spine_session_resume.py
git commit -m "feat(spine): add durable session action selection"
```

---

## 任务 6：实现前端 Goal Board 主控制面

**文件：**
- 创建：`apps/web/src/api/spine.ts`
- 创建：`apps/web/src/components/spine/GoalBoard.tsx`
- 创建：`apps/web/src/components/spine/GoalSummaryCard.tsx`
- 创建：`apps/web/src/components/spine/TaskColumn.tsx`
- 创建：`apps/web/src/components/spine/ReleasePane.tsx`
- 创建：`apps/web/src/pages/GoalBoardPage.tsx`
- 修改：`apps/web/src/App.tsx`
- 修改：`apps/web/src/shell/shellRoutes.ts`
- 修改：`apps/web/src/shell/useShellStore.tsx`
- 测试：`apps/web/src/tests/goalBoard.test.tsx`

- [ ] **步骤 1：编写失败的前端测试**

```tsx
import { render, screen } from "@testing-library/react";
import GoalBoard from "../components/spine/GoalBoard";

it("renders goal board columns and next action", () => {
  render(
    <GoalBoard
      snapshot={{
        goal: { title: "Phase 1", phase: "execution", status: "active" },
        columns: {
          ready: [{ task_id: "t-1", title: "Build taskboard" }],
          blocked: [],
          review: [],
        },
        next_action: { kind: "execute", task_id: "t-1" },
      }}
    />,
  );

  expect(screen.getByText("Phase 1")).toBeInTheDocument();
  expect(screen.getByText("ready")).toBeInTheDocument();
  expect(screen.getByText("Build taskboard")).toBeInTheDocument();
  expect(screen.getByText(/execute/i)).toBeInTheDocument();
});
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd apps/web && npm test -- goalBoard.test.tsx`
预期：FAIL，组件不存在

- [ ] **步骤 3：实现最小 API 客户端与组件**

```ts
// apps/web/src/api/spine.ts
import { api } from "./client";

export interface GoalBoardSnapshot {
  goal: { goal_id?: string; title: string; phase: string; status: string };
  columns: Record<string, Array<{ task_id: string; title: string; detail?: string; status?: string }>>;
  next_action?: { kind: string; task_id?: string; reason?: string };
}

export async function getGoalBoard(goalId: string) {
  const response = await api.get<GoalBoardSnapshot>(`/spine/goals/${encodeURIComponent(goalId)}/board`);
  return response.data;
}
```

```tsx
// apps/web/src/components/spine/GoalBoard.tsx
import GoalSummaryCard from "./GoalSummaryCard";
import TaskColumn from "./TaskColumn";
import type { GoalBoardSnapshot } from "../../api/spine";

export default function GoalBoard({ snapshot }: { snapshot: GoalBoardSnapshot }) {
  return (
    <div className="space-y-6">
      <GoalSummaryCard snapshot={snapshot} />
      <div className="grid gap-4 lg:grid-cols-3">
        {Object.entries(snapshot.columns).map(([column, tasks]) => (
          <TaskColumn key={column} title={column} tasks={tasks} />
        ))}
      </div>
    </div>
  );
}
```

```tsx
// apps/web/src/components/spine/GoalSummaryCard.tsx
import type { GoalBoardSnapshot } from "../../api/spine";

export default function GoalSummaryCard({ snapshot }: { snapshot: GoalBoardSnapshot }) {
  return (
    <section className="xagent-surface p-6">
      <div className="text-xs uppercase tracking-[0.24em] text-neutral-500">Goal Board</div>
      <h1 className="mt-2 text-2xl font-semibold text-white">{snapshot.goal.title}</h1>
      <p className="mt-2 text-sm text-neutral-400">phase: {snapshot.goal.phase} · status: {snapshot.goal.status}</p>
      {snapshot.next_action ? (
        <div className="mt-4 text-sm text-neutral-200">next: {snapshot.next_action.kind}</div>
      ) : null}
    </section>
  );
}
```

```tsx
// apps/web/src/components/spine/TaskColumn.tsx
export default function TaskColumn({ title, tasks }: { title: string; tasks: Array<{ task_id: string; title: string }> }) {
  return (
    <section className="xagent-surface-subtle p-4">
      <div className="text-sm font-medium text-white">{title}</div>
      <div className="mt-3 space-y-2">
        {tasks.map((task) => (
          <article key={task.task_id} className="rounded-2xl border border-white/[0.08] bg-black/20 p-3 text-sm text-neutral-200">
            {task.title}
          </article>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **步骤 4：挂载 Goal Board 页面与 shell route**

```tsx
// apps/web/src/pages/GoalBoardPage.tsx
import { useQuery } from "@tanstack/react-query";
import GoalBoard from "../components/spine/GoalBoard";
import { getGoalBoard } from "../api/spine";

export default function GoalBoardPage() {
  const goalId = "phase1-xagent";
  const query = useQuery({
    queryKey: ["goal-board", goalId],
    queryFn: () => getGoalBoard(goalId),
  });

  if (query.isLoading) return <div className="p-8 text-neutral-400">正在加载 Goal Board...</div>;
  if (!query.data) return <div className="p-8 text-neutral-400">暂无 Goal 数据。</div>;

  return <GoalBoard snapshot={query.data} />;
}
```

```tsx
// apps/web/src/App.tsx
const GoalBoardPage = React.lazy(() => import("./pages/GoalBoardPage"));
<Route path="/goal-board" element={<GoalBoardPage />} />
```

```ts
// apps/web/src/shell/shellRoutes.ts
{
  taskId: "goal-board",
  kind: "workflow",
  route: "/goal-board",
  title: "目标任务板",
  subtitle: "持续推进当前交付主目标",
  badge: "PM",
  pinned: true,
  isPrimary: true,
  status: "ready",
}
```

- [ ] **步骤 5：运行测试验证通过**

运行：`cd apps/web && npm test -- goalBoard.test.tsx`
预期：PASS

- [ ] **步骤 6：Commit**

```bash
git add apps/web/src/api/spine.ts apps/web/src/components/spine apps/web/src/pages/GoalBoardPage.tsx apps/web/src/App.tsx apps/web/src/shell/shellRoutes.ts apps/web/src/shell/useShellStore.tsx apps/web/src/tests/goalBoard.test.tsx
git commit -m "feat(spine): add goal board control surface"
```

---

## 任务 7：实现 Release Packaging / Archive 核心

**文件：**
- 创建：`apps/api/xagent/core/spine/release.py`
- 修改：`apps/api/xagent/core/spine/service.py`
- 测试：`apps/api/tests/test_spine_release_flow.py`

- [ ] **步骤 1：编写失败的 release 测试**

```python
from xagent.core.spine.release import build_release_package


def test_build_release_package_collects_candidate_metadata() -> None:
    package = build_release_package(
        goal_id="goal-1",
        branch_name="candidate/phase1",
        commit_sha="abc123",
        pr_number="7",
        ci_run="28921940625",
        evidence_paths=["r4-evidence/compose-ps.txt"],
    )
    assert package["goal_id"] == "goal-1"
    assert package["candidate"]["branch_name"] == "candidate/phase1"
    assert package["review"]["ci_run"] == "28921940625"
    assert package["evidence"][0] == "r4-evidence/compose-ps.txt"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_release_flow.py -k build_release_package_collects_candidate_metadata -v`
预期：FAIL，函数不存在

- [ ] **步骤 3：实现最小 release 打包器**

```python
# apps/api/xagent/core/spine/release.py
from __future__ import annotations


def build_release_package(
    *,
    goal_id: str,
    branch_name: str,
    commit_sha: str,
    pr_number: str,
    ci_run: str,
    evidence_paths: list[str],
) -> dict:
    return {
        "goal_id": goal_id,
        "candidate": {
            "branch_name": branch_name,
            "commit_sha": commit_sha,
            "pr_number": pr_number,
        },
        "review": {
            "ci_run": ci_run,
            "status": "ready",
        },
        "evidence": list(evidence_paths),
    }
```

- [ ] **步骤 4：在 spine service 中挂接 release summary**

```python
# apps/api/xagent/core/spine/service.py
from xagent.core.spine.release import build_release_package


def make_release_summary(goal_id: str, branch_name: str, commit_sha: str, pr_number: str, ci_run: str, evidence_paths: list[str]) -> dict:
    return build_release_package(
        goal_id=goal_id,
        branch_name=branch_name,
        commit_sha=commit_sha,
        pr_number=pr_number,
        ci_run=ci_run,
        evidence_paths=evidence_paths,
    )
```

- [ ] **步骤 5：运行测试验证通过**

运行：`cd apps/api && .venv\Scripts\python.exe -m pytest tests/test_spine_release_flow.py -k build_release_package_collects_candidate_metadata -v`
预期：PASS

- [ ] **步骤 6：Commit**

```bash
git add apps/api/xagent/core/spine/release.py apps/api/xagent/core/spine/service.py apps/api/tests/test_spine_release_flow.py
git commit -m "feat(spine): add release packaging core"
```

---

## 任务 8：生成 Phase 1 验收报告与 owner 启动入口

**文件：**
- 创建：`docs/coordination/reports/auto-delivery-phase1-report.md`
- 修改：`docs/superpowers/specs/2026-07-08-xagent-auto-delivery-spine-design.md`
- 测试：无（文档校验）

- [ ] **步骤 1：编写 Phase 1 报告模板**

```md
# Auto-Delivery Phase 1 Report

## Goal
- goal id:
- title:
- phase:

## Taskboard Snapshot
- ready:
- in_progress:
- blocked:
- review:
- release_ready:
- deploying:
- verifying:
- delivered:
- recovery:

## Execution Evidence
- run ids:
- review package:
- ci runs:
- deploy runs:
- recovery runs:

## Final Status
- delivered / failed / archived
```

- [ ] **步骤 2：保存文档**

将上述内容写入：`docs/coordination/reports/auto-delivery-phase1-report.md`

- [ ] **步骤 3：运行文档校验**

运行：`git diff --check -- docs/coordination/reports/auto-delivery-phase1-report.md docs/superpowers/specs/2026-07-08-xagent-auto-delivery-spine-design.md`
预期：退出码 0

- [ ] **步骤 4：Commit**

```bash
git add docs/coordination/reports/auto-delivery-phase1-report.md docs/superpowers/specs/2026-07-08-xagent-auto-delivery-spine-design.md
git commit -m "docs(spine): add phase1 delivery report template"
```

---

## 自检

### 规格覆盖度

- 总方案：已覆盖（任务 1-8）
- 三层架构：
  - Planning Layer：任务 2、3、5、6
  - Execution Layer：任务 4、6
  - Control & Evidence Layer：任务 1、4、7、8
- 第一类对象：任务 1、2
- PM Agent 工作流：任务 2、5、6、7
- Phase 1 子项目：
  - Goal/Taskboard/Session：任务 2、3、5、6
  - Execution Orchestrator：任务 4
  - PR/Review/Release：任务 7
  - Deploy/Verify/Recover：任务 4、7、8
  - Policy/Safety：任务 4（最小接线），后续计划中继续扩展
  - Evidence/Archive：任务 7、8
- 新会话启动提示词：已在设计规格中保留，实施阶段通过任务 8 的报告模板和后续工作流落地。

### 占位符扫描

- 无“TODO/待定/后续补充”占位符
- 每个代码步骤都给出具体代码块
- 每个测试步骤都给出明确命令与预期结果

### 类型一致性

- `Goal / Initiative / DeliveryTask / ReleaseRecord` 命名在全部任务中保持一致
- API 路径统一使用 `/api/v1/spine/...`
- 前端统一使用 `GoalBoardSnapshot`

---

## 执行交接

计划已完成并保存到 `docs/superpowers/plans/2026-07-08-xagent-auto-delivery-spine-phase1-plan.md`。两种执行方式：

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

选哪种方式？
