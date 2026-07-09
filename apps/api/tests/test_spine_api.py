from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.enterprise.auth import create_access_token
from xagent.infra.db import dispose_engine
from xagent.infra.settings import get_settings
from xagent.main import create_app

EXPECTED_BOARD_COLUMNS = [
    "ready",
    "in_progress",
    "blocked",
    "review",
    "release_ready",
    "deploying",
    "verifying",
    "delivered",
    "recovery",
]


def _run_alembic_upgrade(db_file: Path, revision: str) -> None:
    url = f"sqlite+aiosqlite:///{db_file}"
    api_dir = Path(__file__).resolve().parent.parent
    site_packages = api_dir / ".venv" / "Lib" / "site-packages"
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
    db_file = tmp_path / "spine-api.db"
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
        json={
            "title": "Auto-Delivery Spine Phase 1",
            "description": "Make xagent upgrade itself",
        },
        headers=_auth(token),
    )
    assert response.status_code == 200
    return response.json()


async def test_create_goal_returns_goal_tree(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])

    body = await _create_goal(client, token)

    assert body["goal"]["title"] == "Auto-Delivery Spine Phase 1"
    assert len(body["initiatives"]) == 6
    assert len(body["tasks"]) == 6


async def test_get_goal_board_snapshot_returns_grouped_columns(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])

    created = await _create_goal(client, token)
    goal_id = created["goal"]["goal_id"]

    response = await client.get(f"/api/v1/spine/goals/{goal_id}/board", headers=_auth(token))

    assert response.status_code == 200
    board = response.json()
    assert list(board["columns"]) == EXPECTED_BOARD_COLUMNS
    assert board["columns"]["ready"]
    for column in EXPECTED_BOARD_COLUMNS[1:]:
        assert board["columns"][column] == []


async def test_get_goal_board_returns_404_for_missing_goal(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])

    response = await client.get("/api/v1/spine/goals/missing-goal/board", headers=_auth(token))

    assert response.status_code == 404


async def test_get_goal_board_enforces_tenant_isolation(client: AsyncClient) -> None:
    token_a = create_access_token(user_id="goal-owner-a", tenant_id="tenant-a", roles=["member"])
    token_b = create_access_token(user_id="goal-owner-b", tenant_id="tenant-b", roles=["member"])

    created = await _create_goal(client, token_a)
    goal_id = created["goal"]["goal_id"]

    response = await client.get(f"/api/v1/spine/goals/{goal_id}/board", headers=_auth(token_b))

    assert response.status_code == 404
