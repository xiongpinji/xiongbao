"""Durable scheduler API 租户隔离与变更确认。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.enterprise.auth import create_access_token
from xagent.infra.db import Base, get_engine
from xagent.main import create_app


@pytest.fixture
async def client() -> AsyncClient:
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as value:
        yield value


def _auth(tenant: str) -> dict[str, str]:
    token = create_access_token(user_id=f"owner-{tenant}", tenant_id=tenant, roles=["member"])
    return {"Authorization": f"Bearer {token}"}


async def test_scheduler_api_is_tenant_isolated_and_requires_confirmation(
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/scheduler/jobs",
        json={
            "name": "API audit",
            "goal": "audit release",
            "interval_seconds": 300,
            "max_retries": 3,
        },
        headers=_auth("scheduler-a"),
    )
    assert created.status_code == 200
    job_id = created.json()["job_id"]

    own = await client.get("/api/v1/scheduler/jobs", headers=_auth("scheduler-a"))
    hidden = await client.get("/api/v1/scheduler/jobs", headers=_auth("scheduler-b"))
    assert [job["job_id"] for job in own.json()["jobs"]] == [job_id]
    assert hidden.json()["jobs"] == []

    missing = await client.patch(
        f"/api/v1/scheduler/jobs/{job_id}/toggle",
        json={"enabled": False},
        headers=_auth("scheduler-a"),
    )
    assert missing.status_code == 422

    toggled = await client.patch(
        f"/api/v1/scheduler/jobs/{job_id}/toggle",
        json={"confirm_job_id": job_id, "enabled": False},
        headers=_auth("scheduler-a"),
    )
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is False

    cross_tenant = await client.get(
        f"/api/v1/scheduler/jobs/{job_id}/runs", headers=_auth("scheduler-b")
    )
    assert cross_tenant.status_code == 404
