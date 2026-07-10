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

ENTRYPOINT_CASES = (
    ("task", "in_progress"),
    ("agent", "ready"),
    ("workflow", "ready"),
)


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


async def _create_goal(
    client: AsyncClient,
    token: str,
    *,
    title: str = "Spine Flow",
) -> dict:
    response = await client.post(
        "/api/v1/spine/goals",
        json={"title": title, "description": "Track task execution"},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _get_board(client: AsyncClient, token: str, goal_id: str) -> dict:
    response = await client.get(f"/api/v1/spine/goals/{goal_id}/board", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


async def _get_first_ready_spine_task(client: AsyncClient, token: str, goal_id: str) -> dict:
    return (await _get_board(client, token, goal_id))["columns"]["ready"][0]


def _find_task(board: dict, task_id: str) -> tuple[str, dict]:
    for column_name, tasks in board["columns"].items():
        for task in tasks:
            if task["task_id"] == task_id:
                return column_name, task
    for task in board["unknown_status_tasks"]:
        if task["task_id"] == task_id:
            return "unknown_status_tasks", task
    raise AssertionError(f"task {task_id} not found in board")


def _build_entrypoint_request(entrypoint: str, spine_task: dict) -> tuple[str, dict]:
    base = {
        "goal_id": spine_task["goal_id"],
        "spine_task_id": spine_task["task_id"],
    }
    if entrypoint == "task":
        return "/api/v1/tasks", {**base, "goal": spine_task["title"]}
    if entrypoint == "agent":
        return "/api/v1/agents/run", {**base, "goal": spine_task["title"]}
    if entrypoint == "workflow":
        return "/api/v1/workflows", {
            **base,
            "name": spine_task["title"],
            "steps": [{"id": "s1", "name": "执行", "goal": "最小 workflow 接线"}],
        }
    raise AssertionError(f"unsupported entrypoint: {entrypoint}")


async def _start_entrypoint(
    client: AsyncClient,
    token: str,
    entrypoint: str,
    spine_task: dict,
) -> str:
    path, payload = _build_entrypoint_request(entrypoint, spine_task)
    response = await client.post(path, json=payload, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


async def _assert_board_task_state(
    client: AsyncClient,
    token: str,
    *,
    goal_id: str,
    spine_task_id: str,
    expected_status: str,
    expected_run_id: str,
) -> None:
    board = await _get_board(client, token, goal_id)
    column_name, task = _find_task(board, spine_task_id)
    assert column_name == expected_status
    assert task["status"] == expected_status
    assert task["run_id"] == expected_run_id


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


@pytest.mark.parametrize(("entrypoint", "expected_status"), ENTRYPOINT_CASES)
async def test_entrypoint_attaches_run_and_exposes_spine_linkage(
    client: AsyncClient,
    entrypoint: str,
    expected_status: str,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token)
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)

    run_id = await _start_entrypoint(client, token, entrypoint, spine_task)

    await _assert_board_task_state(
        client,
        token,
        goal_id=goal_id,
        spine_task_id=spine_task["task_id"],
        expected_status=expected_status,
        expected_run_id=run_id,
    )
    await _assert_run_spine_linkage(
        client,
        token,
        run_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
    )


@pytest.mark.parametrize(("entrypoint", "expected_status"), ENTRYPOINT_CASES)
async def test_explicit_spine_ids_bind_correct_goal_when_titles_duplicate(
    client: AsyncClient,
    entrypoint: str,
    expected_status: str,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    goal_a = await _create_goal(client, token, title="Goal A")
    goal_b = await _create_goal(client, token, title="Goal B")
    goal_a_id = goal_a["goal"]["goal_id"]
    goal_b_id = goal_b["goal"]["goal_id"]
    spine_task_a = await _get_first_ready_spine_task(client, token, goal_a_id)
    spine_task_b = await _get_first_ready_spine_task(client, token, goal_b_id)

    assert spine_task_a["title"] == spine_task_b["title"]

    run_id = await _start_entrypoint(client, token, entrypoint, spine_task_b)

    await _assert_board_task_state(
        client,
        token,
        goal_id=goal_b_id,
        spine_task_id=spine_task_b["task_id"],
        expected_status=expected_status,
        expected_run_id=run_id,
    )
    await _assert_run_spine_linkage(
        client,
        token,
        run_id,
        goal_id=goal_b_id,
        initiative_id=spine_task_b["initiative_id"],
    )

    board_a = await _get_board(client, token, goal_a_id)
    _, other_task = _find_task(board_a, spine_task_a["task_id"])
    assert other_task["status"] == "ready"
    assert other_task["run_id"] == ""


@pytest.mark.parametrize(("entrypoint", "expected_status"), ENTRYPOINT_CASES)
async def test_explicit_spine_ids_rebind_latest_run_without_silent_failure(
    client: AsyncClient,
    entrypoint: str,
    expected_status: str,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token)
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)

    first_run_id = await _start_entrypoint(client, token, entrypoint, spine_task)
    second_run_id = await _start_entrypoint(client, token, entrypoint, spine_task)

    assert second_run_id != first_run_id
    await _assert_board_task_state(
        client,
        token,
        goal_id=goal_id,
        spine_task_id=spine_task["task_id"],
        expected_status=expected_status,
        expected_run_id=second_run_id,
    )
    await _assert_run_spine_linkage(
        client,
        token,
        second_run_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
    )

    first_run_response = await client.get(f"/api/v1/runs/{first_run_id}", headers=_auth(token))
    assert first_run_response.status_code == 200, first_run_response.text
    assert first_run_response.json()["spine"] == {"goal_id": "", "initiative_id": ""}
