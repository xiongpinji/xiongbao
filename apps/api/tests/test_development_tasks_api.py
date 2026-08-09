"""开发任务 API：租户隔离、显式确认、路径脱敏与审计。"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.domains.development_tasks import (
    DevelopmentTaskCreate,
    DevelopmentTaskStatus,
    create_development_task,
)
from xagent.domains.development_tasks.git_lifecycle import development_task_paths
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth import create_access_token
from xagent.infra.db import Base, get_engine, get_sessionmaker
from xagent.main import create_app


@pytest.fixture
async def client() -> AsyncClient:
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


def _auth(tenant_id: str, *, role: str = "member") -> dict[str, str]:
    token = create_access_token(
        user_id=f"user-{tenant_id}", tenant_id=tenant_id, roles=[role]
    )
    return {"Authorization": f"Bearer {token}"}


async def _create_task(
    tmp_path: Path,
    *,
    task_id: str,
    tenant_id: str,
    status: DevelopmentTaskStatus = DevelopmentTaskStatus.awaiting_review,
    patch_text: str = "diff --git a/app.py b/app.py\n+print('ok')\n",
) -> None:
    repo = tmp_path / f"repo-{task_id}"
    repo.mkdir()
    paths = development_task_paths(repo, task_id)
    paths.patch_root.mkdir(parents=True, exist_ok=True)
    paths.patch.write_text(patch_text, encoding="utf-8")
    async with get_sessionmaker()() as session:
        await create_development_task(
            session,
            DevelopmentTaskCreate(
                task_id=task_id,
                parent_run_id=f"parent-{task_id}",
                sub_run_id=f"sub-{task_id}",
                tenant_id=tenant_id,
                owner_id=f"owner-{tenant_id}",
                goal="repair API",
                status=status,
                main_workspace=str(repo),
                base_commit="a" * 40,
                target_branch="main",
                work_branch=f"xagent/task-{task_id}",
                worktree_path=str(paths.worktree),
                patch_path=str(paths.patch),
            ),
        )
        await session.commit()


async def test_list_detail_and_patch_are_tenant_isolated_and_sanitized(
    client: AsyncClient, tmp_path: Path
) -> None:
    await _create_task(tmp_path, task_id="api-visible", tenant_id="tenant-api-a")
    await _create_task(tmp_path, task_id="api-hidden", tenant_id="tenant-api-b")

    response = await client.get(
        "/api/v1/development-tasks", headers=_auth("tenant-api-a")
    )
    assert response.status_code == 200
    assert [item["task_id"] for item in response.json()["items"]] == ["api-visible"]
    serialized = response.text
    assert "main_workspace" not in serialized
    assert "worktree_path" not in serialized
    assert "patch_path" not in serialized

    hidden = await client.get(
        "/api/v1/development-tasks/api-hidden", headers=_auth("tenant-api-a")
    )
    assert hidden.status_code == 404

    patch = await client.get(
        "/api/v1/development-tasks/api-visible/patch",
        headers=_auth("tenant-api-a"),
    )
    assert patch.status_code == 200
    assert "diff --git" in patch.json()["patch"]
    assert "patch_path" not in patch.text


async def test_cancelled_task_patch_is_not_downloadable_even_if_file_remains(
    client: AsyncClient, tmp_path: Path
) -> None:
    task_id = "api-cancelled-patch"
    tenant_id = "tenant-cancelled-patch"
    await _create_task(
        tmp_path,
        task_id=task_id,
        tenant_id=tenant_id,
        status=DevelopmentTaskStatus.cancelled,
    )

    response = await client.get(
        f"/api/v1/development-tasks/{task_id}/patch",
        headers=_auth(tenant_id),
    )

    assert response.status_code == 409
    assert "状态" in response.json()["detail"]


@pytest.mark.parametrize(
    "task_status",
    [
        DevelopmentTaskStatus.approved,
        DevelopmentTaskStatus.applied,
        DevelopmentTaskStatus.rejected,
        DevelopmentTaskStatus.conflict,
        DevelopmentTaskStatus.expired,
    ],
)
async def test_reviewed_task_patch_remains_downloadable(
    client: AsyncClient,
    tmp_path: Path,
    task_status: DevelopmentTaskStatus,
) -> None:
    task_id = f"api-patch-{task_status.value}"
    tenant_id = f"tenant-patch-{task_status.value}"
    await _create_task(
        tmp_path,
        task_id=task_id,
        tenant_id=tenant_id,
        status=task_status,
    )

    response = await client.get(
        f"/api/v1/development-tasks/{task_id}/patch",
        headers=_auth(tenant_id),
    )

    assert response.status_code == 200
    assert "diff --git" in response.json()["patch"]


async def test_mutations_require_exact_task_confirmation(
    client: AsyncClient, tmp_path: Path
) -> None:
    await _create_task(tmp_path, task_id="api-confirm", tenant_id="tenant-confirm")
    headers = _auth("tenant-confirm")
    for action in ("approve", "reject", "apply", "cancel"):
        missing = await client.post(
            f"/api/v1/development-tasks/api-confirm/{action}",
            json={},
            headers=headers,
        )
        assert missing.status_code == 422

    mismatch = await client.post(
        "/api/v1/development-tasks/api-confirm/approve",
        json={"confirm_task_id": "different-task"},
        headers=headers,
    )
    assert mismatch.status_code == 409


async def test_approve_is_audited_and_respects_review_permission(
    client: AsyncClient, tmp_path: Path
) -> None:
    task_id = "api-audit"
    tenant_id = "tenant-audit"
    await _create_task(tmp_path, task_id=task_id, tenant_id=tenant_id)

    forbidden = await client.post(
        f"/api/v1/development-tasks/{task_id}/approve",
        json={"confirm_task_id": task_id},
        headers=_auth(tenant_id, role="viewer"),
    )
    assert forbidden.status_code == 403

    response = await client.post(
        f"/api/v1/development-tasks/{task_id}/approve",
        json={"confirm_task_id": task_id},
        headers=_auth(tenant_id),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    events = get_audit_log().list(tenant_id)
    assert events[-1].action == "development_task.approve"
    assert events[-1].detail["task_id"] == task_id
