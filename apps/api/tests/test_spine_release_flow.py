from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.core.workflow import get_engine, reset_engine
from xagent.enterprise.auth import create_access_token
from xagent.infra.db import dispose_engine, get_sessionmaker
from xagent.infra.models.spine import DeliveryTaskORM
from xagent.infra.settings import get_settings
from xagent.main import create_app
from xagent.worker import get_task_runner
from xagent.worker.celery_app import persist_agent_task_record, persist_submitted_agent_task

ENTRYPOINT_CASES = (
    ("task", "review"),
    ("agent", "review"),
    ("workflow", "review"),
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
    spine_task_id: str | None = None,
) -> None:
    run_response = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))
    assert run_response.status_code == 200, run_response.text
    actual = run_response.json()["spine"]
    assert actual["goal_id"] == goal_id
    assert actual["initiative_id"] == initiative_id
    if spine_task_id is not None:
        assert actual["spine_task_id"] == spine_task_id


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
    if entrypoint == "task":
        await _wait_for_task_terminal(client, token, run_id)

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
        spine_task_id=spine_task["task_id"],
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
    if entrypoint == "task":
        await _wait_for_task_terminal(client, token, run_id)

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
        spine_task_id=spine_task_b["task_id"],
    )

    board_a = await _get_board(client, token, goal_a_id)
    _, other_task = _find_task(board_a, spine_task_a["task_id"])
    assert other_task["status"] == "ready"
    assert other_task["run_id"] == ""


@pytest.mark.parametrize(("entrypoint", "expected_status"), ENTRYPOINT_CASES)
async def test_explicit_spine_ids_rebind_latest_run_without_losing_old_run_provenance(
    client: AsyncClient,
    entrypoint: str,
    expected_status: str,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token)
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)

    first_run_id = await _start_entrypoint(client, token, entrypoint, spine_task)
    if entrypoint == "task":
        await _wait_for_task_terminal(client, token, first_run_id)
    second_run_id = await _start_entrypoint(client, token, entrypoint, spine_task)
    if entrypoint == "task":
        await _wait_for_task_terminal(client, token, second_run_id)

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
        first_run_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
        spine_task_id=spine_task["task_id"],
    )
    await _assert_run_spine_linkage(
        client,
        token,
        second_run_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
        spine_task_id=spine_task["task_id"],
    )


@pytest.mark.parametrize(("entrypoint", "expected_status"), ENTRYPOINT_CASES)
async def test_legacy_title_fallback_preserves_old_run_provenance_after_rerun(
    client: AsyncClient,
    entrypoint: str,
    expected_status: str,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token)
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)
    path, payload = _build_entrypoint_request(entrypoint, spine_task)
    payload.pop("goal_id")
    payload.pop("spine_task_id")

    first_response = await client.post(path, json=payload, headers=_auth(token))
    assert first_response.status_code == 200, first_response.text
    first_run_id = first_response.json()["run_id"]
    if entrypoint == "task":
        await _wait_for_task_terminal(client, token, first_run_id)

    async with get_sessionmaker()() as session:
        candidate = await session.get(DeliveryTaskORM, spine_task["task_id"])
        assert candidate is not None
        candidate.status = "ready"
        candidate.run_id = ""
        await session.commit()

    second_response = await client.post(path, json=payload, headers=_auth(token))
    assert second_response.status_code == 200, second_response.text
    second_run_id = second_response.json()["run_id"]
    if entrypoint == "task":
        await _wait_for_task_terminal(client, token, second_run_id)

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
        first_run_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
        spine_task_id=spine_task["task_id"],
    )
    await _assert_run_spine_linkage(
        client,
        token,
        second_run_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
        spine_task_id=spine_task["task_id"],
    )


@pytest.mark.parametrize("entrypoint", ["task", "agent", "workflow"])
@pytest.mark.parametrize("missing_field", ["goal_id", "spine_task_id"])
async def test_partial_spine_ids_are_rejected(
    client: AsyncClient,
    entrypoint: str,
    missing_field: str,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token)
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)
    path, payload = _build_entrypoint_request(entrypoint, spine_task)
    payload.pop(missing_field)

    response = await client.post(path, json=payload, headers=_auth(token))

    assert response.status_code == 422, response.text
    board = await _get_board(client, token, goal_id)
    _, task = _find_task(board, spine_task["task_id"])
    assert task["status"] == "ready"
    assert task["run_id"] == ""


@pytest.mark.parametrize("entrypoint", ["task", "agent", "workflow"])
async def test_mismatched_spine_ids_are_rejected_without_binding_wrong_goal(
    client: AsyncClient,
    entrypoint: str,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    goal_a = await _create_goal(client, token, title="Goal A")
    goal_b = await _create_goal(client, token, title="Goal B")
    goal_a_id = goal_a["goal"]["goal_id"]
    goal_b_id = goal_b["goal"]["goal_id"]
    spine_task_a = await _get_first_ready_spine_task(client, token, goal_a_id)
    spine_task_b = await _get_first_ready_spine_task(client, token, goal_b_id)
    path, payload = _build_entrypoint_request(entrypoint, spine_task_a)
    payload["goal_id"] = goal_b_id

    response = await client.post(path, json=payload, headers=_auth(token))

    assert response.status_code == 409, response.text
    board_a = await _get_board(client, token, goal_a_id)
    _, task_a = _find_task(board_a, spine_task_a["task_id"])
    assert task_a["status"] == "ready"
    assert task_a["run_id"] == ""
    board_b = await _get_board(client, token, goal_b_id)
    _, task_b = _find_task(board_b, spine_task_b["task_id"])
    assert task_b["status"] == "ready"
    assert task_b["run_id"] == ""


async def test_agent_run_returns_409_for_mismatched_explicit_ids(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    goal_a = await _create_goal(client, token, title="Agent Goal A")
    goal_b = await _create_goal(client, token, title="Agent Goal B")
    goal_a_id = goal_a["goal"]["goal_id"]
    goal_b_id = goal_b["goal"]["goal_id"]
    spine_task_a = await _get_first_ready_spine_task(client, token, goal_a_id)
    spine_task_b = await _get_first_ready_spine_task(client, token, goal_b_id)

    response = await client.post(
        "/api/v1/agents/run",
        json={
            "goal": spine_task_a["title"],
            "goal_id": goal_b_id,
            "spine_task_id": spine_task_a["task_id"],
        },
        headers=_auth(token),
    )

    assert response.status_code == 409, response.text
    board_a = await _get_board(client, token, goal_a_id)
    _, task_a = _find_task(board_a, spine_task_a["task_id"])
    assert task_a["status"] == "ready"
    assert task_a["run_id"] == ""
    board_b = await _get_board(client, token, goal_b_id)
    _, task_b = _find_task(board_b, spine_task_b["task_id"])
    assert task_b["status"] == "ready"
    assert task_b["run_id"] == ""


async def test_task_strict_attach_fails_before_submit_side_effect(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    goal_a = await _create_goal(client, token, title="Task Strict Goal A")
    goal_b = await _create_goal(client, token, title="Task Strict Goal B")
    goal_a_id = goal_a["goal"]["goal_id"]
    goal_b_id = goal_b["goal"]["goal_id"]
    spine_task_a = await _get_first_ready_spine_task(client, token, goal_a_id)

    response = await client.post(
        "/api/v1/tasks",
        json={
            "goal": spine_task_a["title"],
            "goal_id": goal_b_id,
            "spine_task_id": spine_task_a["task_id"],
        },
        headers=_auth(token),
    )

    assert response.status_code == 409, response.text
    assert get_task_runner().list("tenant-1") == []
    board_a = await _get_board(client, token, goal_a_id)
    _, task_a = _find_task(board_a, spine_task_a["task_id"])
    assert task_a["status"] == "ready"
    assert task_a["run_id"] == ""


async def test_agent_strict_attach_fails_before_run_side_effect(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    goal_a = await _create_goal(client, token, title="Agent Strict Goal A")
    goal_b = await _create_goal(client, token, title="Agent Strict Goal B")
    goal_a_id = goal_a["goal"]["goal_id"]
    goal_b_id = goal_b["goal"]["goal_id"]
    spine_task_a = await _get_first_ready_spine_task(client, token, goal_a_id)
    mocked_run_agent = AsyncMock()
    monkeypatch.setattr("xagent.api.v1.agents.run_agent", mocked_run_agent)

    response = await client.post(
        "/api/v1/agents/run",
        json={
            "goal": spine_task_a["title"],
            "goal_id": goal_b_id,
            "spine_task_id": spine_task_a["task_id"],
        },
        headers=_auth(token),
    )

    assert response.status_code == 409, response.text
    assert mocked_run_agent.await_count == 0
    board_a = await _get_board(client, token, goal_a_id)
    _, task_a = _find_task(board_a, spine_task_a["task_id"])
    assert task_a["status"] == "ready"
    assert task_a["run_id"] == ""


async def test_workflow_strict_attach_fails_before_run_side_effect(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    goal_a = await _create_goal(client, token, title="Workflow Strict Goal A")
    goal_b = await _create_goal(client, token, title="Workflow Strict Goal B")
    goal_a_id = goal_a["goal"]["goal_id"]
    goal_b_id = goal_b["goal"]["goal_id"]
    spine_task_a = await _get_first_ready_spine_task(client, token, goal_a_id)

    response = await client.post(
        "/api/v1/workflows",
        json={
            "name": spine_task_a["title"],
            "goal_id": goal_b_id,
            "spine_task_id": spine_task_a["task_id"],
            "steps": [{"id": "s1", "name": "执行", "goal": "workflow strict"}],
        },
        headers=_auth(token),
    )

    assert response.status_code == 409, response.text
    assert get_engine().list_runs("tenant-1") == []
    board_a = await _get_board(client, token, goal_a_id)
    _, task_a = _find_task(board_a, spine_task_a["task_id"])
    assert task_a["status"] == "ready"
    assert task_a["run_id"] == ""


@pytest.mark.parametrize(("entrypoint", "expected_status"), ENTRYPOINT_CASES)
async def test_legacy_fallback_binds_unique_ready_unbound_candidate(
    client: AsyncClient,
    entrypoint: str,
    expected_status: str,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    goal_a = await _create_goal(client, token, title="Legacy Goal A")
    goal_b = await _create_goal(client, token, title="Legacy Goal B")
    goal_a_id = goal_a["goal"]["goal_id"]
    goal_b_id = goal_b["goal"]["goal_id"]
    spine_task_a = await _get_first_ready_spine_task(client, token, goal_a_id)
    spine_task_b = await _get_first_ready_spine_task(client, token, goal_b_id)

    async with get_sessionmaker()() as session:
        historical = await session.get(DeliveryTaskORM, spine_task_b["task_id"])
        assert historical is not None
        historical.status = "review"
        historical.run_id = "historical-run"
        await session.commit()

    path, payload = _build_entrypoint_request(entrypoint, spine_task_a)
    payload.pop("goal_id")
    payload.pop("spine_task_id")

    response = await client.post(path, json=payload, headers=_auth(token))
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    if entrypoint == "task":
        await _wait_for_task_terminal(client, token, run_id)

    await _assert_board_task_state(
        client,
        token,
        goal_id=goal_a_id,
        spine_task_id=spine_task_a["task_id"],
        expected_status=expected_status,
        expected_run_id=run_id,
    )
    board_b = await _get_board(client, token, goal_b_id)
    _, historical_task = _find_task(board_b, spine_task_b["task_id"])
    assert historical_task["status"] == "review"
    assert historical_task["run_id"] == "historical-run"


async def test_celery_persistence_retains_spine_provenance_on_terminal_update(
    client: AsyncClient,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token, title="Celery Provenance Goal")
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)
    run_id = "celery-provenance-run"

    await persist_submitted_agent_task(
        task_id=run_id,
        tenant_id="tenant-1",
        owner_id="goal-owner",
        kind="agent.run",
        backend="celery",
        input_payload={
            "goal": spine_task["title"],
            "goal_id": goal_id,
            "spine_task_id": spine_task["task_id"],
            "role": None,
            "capabilities": [],
        },
        status="pending",
    )
    await persist_agent_task_record(
        task_id=run_id,
        run_id=run_id,
        tenant_id="tenant-1",
        owner_id="goal-owner",
        kind="agent.run",
        backend="celery",
        status="succeeded",
        input_payload={
            "goal": spine_task["title"],
            "role": None,
            "capabilities": [],
        },
        result_payload={"run_id": run_id, "final_answer": "done"},
    )

    await _assert_run_spine_linkage(
        client,
        token,
        run_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
        spine_task_id=spine_task["task_id"],
    )


async def test_workflow_replay_reads_persisted_view_after_engine_reset(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    create_response = await client.post(
        "/api/v1/workflows",
        json={
            "name": "persisted-workflow-replay",
            "steps": [{"id": "s1", "name": "执行", "goal": "回放持久化视图"}],
        },
        headers=_auth(token),
    )
    assert create_response.status_code == 200, create_response.text
    run_id = create_response.json()["run_id"]

    reset_engine()

    replay_response = await client.get(f"/api/v1/workflows/{run_id}", headers=_auth(token))
    assert replay_response.status_code == 200, replay_response.text
    assert replay_response.json()["run_id"] == run_id
    assert replay_response.json()["status"] == "completed"
    assert replay_response.json()["steps"]


async def _wait_for_task_terminal(
    client: AsyncClient,
    token: str,
    task_id: str,
) -> dict:
    for _ in range(40):
        response = await client.get(f"/api/v1/tasks/{task_id}", headers=_auth(token))
        assert response.status_code == 200, response.text
        body = response.json()
        if body["status"] in {"succeeded", "failed"}:
            return body
        await asyncio.sleep(0.05)
    raise AssertionError(f"task {task_id} did not reach terminal status")


async def test_task_success_updates_board_to_review(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token, title="Task Success Goal")
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)

    response = await client.post(
        "/api/v1/tasks",
        json={
            "goal": spine_task["title"],
            "goal_id": goal_id,
            "spine_task_id": spine_task["task_id"],
        },
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]

    terminal = await _wait_for_task_terminal(client, token, task_id)
    assert terminal["status"] == "succeeded"
    await _assert_board_task_state(
        client,
        token,
        goal_id=goal_id,
        spine_task_id=spine_task["task_id"],
        expected_status="review",
        expected_run_id=task_id,
    )
    await _assert_run_spine_linkage(
        client,
        token,
        task_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
        spine_task_id=spine_task["task_id"],
    )


async def test_task_failure_updates_board_to_recovery(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token, title="Task Failure Goal")
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)
    monkeypatch.setattr(
        "xagent.api.v1.tasks.run_agent",
        AsyncMock(side_effect=RuntimeError("task exploded")),
    )

    response = await client.post(
        "/api/v1/tasks",
        json={
            "goal": spine_task["title"],
            "goal_id": goal_id,
            "spine_task_id": spine_task["task_id"],
        },
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]

    terminal = await _wait_for_task_terminal(client, token, task_id)
    assert terminal["status"] == "failed"
    await _assert_board_task_state(
        client,
        token,
        goal_id=goal_id,
        spine_task_id=spine_task["task_id"],
        expected_status="recovery",
        expected_run_id=task_id,
    )


async def test_agent_failure_updates_board_to_recovery(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token, title="Agent Failure Goal")
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)
    monkeypatch.setattr(
        "xagent.api.v1.agents.run_agent",
        AsyncMock(side_effect=RuntimeError("agent exploded")),
    )

    response = await client.post(
        "/api/v1/agents/run",
        json={
            "goal": spine_task["title"],
            "goal_id": goal_id,
            "spine_task_id": spine_task["task_id"],
        },
        headers=_auth(token),
    )
    assert response.status_code == 500, response.text
    run_id = response.json()["detail"]["run_id"]

    await _assert_board_task_state(
        client,
        token,
        goal_id=goal_id,
        spine_task_id=spine_task["task_id"],
        expected_status="recovery",
        expected_run_id=run_id,
    )


async def test_legacy_agent_failure_updates_board_to_recovery(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token, title="Legacy Agent Failure Goal")
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)
    monkeypatch.setattr(
        "xagent.api.v1.agents.run_agent",
        AsyncMock(side_effect=RuntimeError("legacy agent exploded")),
    )

    response = await client.post(
        "/api/v1/agents/run",
        json={"goal": spine_task["title"]},
        headers=_auth(token),
    )
    assert response.status_code == 500, response.text
    run_id = response.json()["detail"]["run_id"]

    await _assert_board_task_state(
        client,
        token,
        goal_id=goal_id,
        spine_task_id=spine_task["task_id"],
        expected_status="recovery",
        expected_run_id=run_id,
    )


async def test_workflow_execution_failure_updates_board_to_recovery(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token, title="Workflow Failure Goal")
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)

    class _WorkflowEngineStub:
        def create_run(self, spec, principal, run_id=None):
            assert run_id
            return type("WorkflowRunStub", (), {"run_id": run_id})()

        async def execute(self, run_id, principal):
            raise RuntimeError("workflow exploded")

    monkeypatch.setattr("xagent.api.v1.workflows.get_engine", lambda: _WorkflowEngineStub())

    response = await client.post(
        "/api/v1/workflows",
        json={
            "name": spine_task["title"],
            "goal_id": goal_id,
            "spine_task_id": spine_task["task_id"],
            "steps": [{"id": "s1", "name": "执行", "goal": "workflow failure"}],
        },
        headers=_auth(token),
    )
    assert response.status_code == 500, response.text
    run_id = response.json()["detail"]["run_id"]
    assert run_id

    await _assert_board_task_state(
        client,
        token,
        goal_id=goal_id,
        spine_task_id=spine_task["task_id"],
        expected_status="recovery",
        expected_run_id=run_id,
    )


async def test_workflow_create_run_failure_updates_board_to_recovery(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token, title="Workflow Create Failure Goal")
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)

    class _WorkflowEngineStub:
        def create_run(self, spec, principal, run_id=None):
            assert run_id
            raise RuntimeError("workflow create_run exploded")

        async def execute(self, run_id, principal):
            raise AssertionError("execute should not be called when create_run fails")

    monkeypatch.setattr("xagent.api.v1.workflows.get_engine", lambda: _WorkflowEngineStub())

    response = await client.post(
        "/api/v1/workflows",
        json={
            "name": spine_task["title"],
            "goal_id": goal_id,
            "spine_task_id": spine_task["task_id"],
            "steps": [{"id": "s1", "name": "执行", "goal": "workflow create failure"}],
        },
        headers=_auth(token),
    )
    assert response.status_code == 500, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "workflow create_run exploded"
    run_id = detail["run_id"]
    assert run_id

    await _assert_board_task_state(
        client,
        token,
        goal_id=goal_id,
        spine_task_id=spine_task["task_id"],
        expected_status="recovery",
        expected_run_id=run_id,
    )


async def test_workflow_awaiting_approval_updates_board_to_review(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token, title="Workflow Review Goal")
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)

    response = await client.post(
        "/api/v1/workflows",
        json={
            "name": spine_task["title"],
            "goal_id": goal_id,
            "spine_task_id": spine_task["task_id"],
            "steps": [
                {
                    "id": "approve-step",
                    "name": "人工审批",
                    "goal": "等待审批",
                    "approver_role": "admin",
                    "approval_message": "请审批",
                }
            ],
        },
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    assert response.json()["status"] == "awaiting_approval"

    await _assert_board_task_state(
        client,
        token,
        goal_id=goal_id,
        spine_task_id=spine_task["task_id"],
        expected_status="review",
        expected_run_id=run_id,
    )
    await _assert_run_spine_linkage(
        client,
        token,
        run_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
        spine_task_id=spine_task["task_id"],
    )


async def test_workflow_cancelled_updates_board_to_recovery(client: AsyncClient) -> None:
    token = create_access_token(user_id="goal-owner", tenant_id="tenant-1", roles=["member"])
    created = await _create_goal(client, token, title="Workflow Cancel Goal")
    goal_id = created["goal"]["goal_id"]
    spine_task = await _get_first_ready_spine_task(client, token, goal_id)

    create_response = await client.post(
        "/api/v1/workflows",
        json={
            "name": spine_task["title"],
            "goal_id": goal_id,
            "spine_task_id": spine_task["task_id"],
            "steps": [
                {
                    "id": "approve-step",
                    "name": "人工审批",
                    "goal": "等待审批",
                    "approver_role": "admin",
                    "approval_message": "请审批",
                }
            ],
        },
        headers=_auth(token),
    )
    assert create_response.status_code == 200, create_response.text
    run_id = create_response.json()["run_id"]
    assert create_response.json()["status"] == "awaiting_approval"

    deny_response = await client.post(
        f"/api/v1/workflows/{run_id}/deny/approve-step",
        headers=_auth(token),
    )
    assert deny_response.status_code == 200, deny_response.text
    assert deny_response.json()["status"] == "cancelled"

    await _assert_board_task_state(
        client,
        token,
        goal_id=goal_id,
        spine_task_id=spine_task["task_id"],
        expected_status="recovery",
        expected_run_id=run_id,
    )
    await _assert_run_spine_linkage(
        client,
        token,
        run_id,
        goal_id=goal_id,
        initiative_id=spine_task["initiative_id"],
        spine_task_id=spine_task["task_id"],
    )
