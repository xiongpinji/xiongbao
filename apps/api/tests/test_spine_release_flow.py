from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.enterprise.auth import create_access_token
from xagent.infra.db import dispose_engine
from xagent.infra.settings import get_settings
from xagent.main import create_app


def _current_site_packages() -> str:
    purelib = sysconfig.get_path("purelib")
    if purelib:
        return purelib
    raise RuntimeError("could not resolve current environment site-packages path")


def _run_alembic_upgrade(db_file: Path, revision: str) -> None:
    url = f"sqlite+aiosqlite:///{db_file}"
    api_dir = Path(__file__).resolve().parent.parent
    site_packages = _current_site_packages()
    env = {
        **os.environ,
        "XAGENT_DB__URL": url,
        "PYTHONPATH": str(api_dir),
        "PYTHONUTF8": "1",
    }
    script = (
        "import sys; "
        f"sys.path[:0] = [{str(site_packages)!r}, {str(api_dir)!r}]; "
        "from alembic.config import main; "
        "raise SystemExit(main(argv=['upgrade', sys.argv[1]]))"
    )
    subprocess.run(
        [sys.executable, "-S", "-c", script, revision],
        cwd=api_dir,
        env=env,
        check=True,
        capture_output=True,
    )


@pytest.fixture
async def migrated_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_file = tmp_path / "spine-release-flow.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setenv("XAGENT_DB__URL", url)
    get_settings.cache_clear()
    await dispose_engine()

    _run_alembic_upgrade(db_file, "head")

    yield url

    await dispose_engine()
    get_settings.cache_clear()


@pytest.fixture
async def client(migrated_db: str):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c



def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_goal(client: AsyncClient, token: str) -> dict:
    response = await client.post(
        "/api/v1/spine/goals",
        json={"title": "Spine Flow", "description": "Track task execution"},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _get_first_ready_spine_task(client: AsyncClient, token: str, goal_id: str) -> dict:
    board_response = await client.get(f"/api/v1/spine/goals/{goal_id}/board", headers=_auth(token))
    assert board_response.status_code == 200, board_response.text
    return board_response.json()["columns"]["ready"][0]


async def _assert_spine_task_attached(
    client: AsyncClient,
    token: str,
    goal_id: str,
    spine_task: dict,
    run_id: str,
) -> None:
    board_after_response = await client.get(
        f"/api/v1/spine/goals/{goal_id}/board",
        headers=_auth(token),
    )
    assert board_after_response.status_code == 200, board_after_response.text
    board_after = board_after_response.json()

    assert not any(
        task["task_id"] == spine_task["task_id"]
        for task in board_after["columns"]["ready"]
    )
    updated = next(
        task
        for task in board_after["columns"]["in_progress"]
        if task["task_id"] == spine_task["task_id"]
    )
    assert updated["run_id"] == run_id
    assert updated["status"] == "in_progress"


async def _assert_run_spine_linkage(
    client: AsyncClient,
    token: str,
    run_id: str,
    *,
    goal_id: str,
    initiative_id: str,
) -> None:
    run_response = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["spine"] == {
        "goal_id": goal_id,
        "initiative_id": initiative_id,
    }


async def test_task_submission_updates_delivery_task_with_run_id(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token)
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)

    response = await client.post(
        "/api/v1/tasks",
        json={"goal": spine_task["title"]},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]

    await _assert_spine_task_attached(client, token, goal_id, spine_task, run_id)
    await _assert_run_spine_linkage(
        client,
        token,
        run_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
    )


async def test_agent_run_updates_delivery_task_with_run_id(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token)
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)

    response = await client.post(
        "/api/v1/agents/run",
        json={"goal": spine_task["title"]},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]

    await _assert_spine_task_attached(client, token, goal_id, spine_task, run_id)
    await _assert_run_spine_linkage(
        client,
        token,
        run_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
    )


async def test_workflow_run_updates_delivery_task_with_run_id(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token)
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)

    response = await client.post(
        "/api/v1/workflows",
        json={
            "name": spine_task["title"],
            "steps": [{"id": "s1", "name": "执行", "goal": "最小 workflow 接线"}],
        },
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]

    await _assert_spine_task_attached(client, token, goal_id, spine_task, run_id)
    await _assert_run_spine_linkage(
        client,
        token,
        run_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
    )
