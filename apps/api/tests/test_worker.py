"""后台任务 Worker 测试。"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.core.orchestration.state import AgentRun
from xagent.enterprise.auth import create_access_token
from xagent.main import create_app
from xagent.worker import get_task_runner


def _current_site_packages() -> str:
    purelib = sysconfig.get_path("purelib")
    if purelib:
        return purelib
    raise RuntimeError("could not resolve current environment site-packages path")


@pytest.fixture
async def migrated_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_file = tmp_path / "worker-test.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setenv("XAGENT_DB__URL", url)

    from xagent.infra.db import dispose_engine
    from xagent.infra.settings import get_settings

    get_settings.cache_clear()
    await dispose_engine()

    api_dir = str(Path(__file__).resolve().parent.parent)
    site_packages = _current_site_packages()
    env = {
        **os.environ,
        "XAGENT_DB__URL": url,
        "PYTHONPATH": api_dir,
        "PYTHONUTF8": "1",
    }
    script = (
        "import sys; "
        f"sys.path[:0] = [{site_packages!r}, {api_dir!r}]; "
        "from alembic.config import main; "
        "raise SystemExit(main(argv=['upgrade', sys.argv[1]]))"
    )
    subprocess.run(
        [sys.executable, "-S", "-c", script, "head"],
        cwd=api_dir,
        env=env,
        check=True,
        capture_output=True,
    )

    yield url

    await dispose_engine()
    get_settings.cache_clear()


@pytest.fixture
async def client(migrated_db):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_submit_and_poll_task(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.post("/api/v1/tasks", json={"goal": "你好"}, headers=_h(token))
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    # task contract foundation：这里只验证 /tasks 对未来 /runs 聚合的最小外部合同。
    for _ in range(20):
        s = await client.get(f"/api/v1/tasks/{task_id}", headers=_h(token))
        assert s.status_code == 200
        if s.json()["status"] in ("succeeded", "failed"):
            break
        await asyncio.sleep(0.1)
    body = s.json()
    assert body["status"] == "succeeded"
    assert body["result"]["final_answer"]
    assert body["run_id"] == task_id
    assert body["source"] == "task"
    assert body["intent_type"] == "agent"
    assert body["route_source"] == "fallback"
    assert body["updated_at"]


async def test_task_detail_uses_task_id_as_compat_run_id(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.post("/api/v1/tasks", json={"goal": "兼容 run id"}, headers=_h(token))
    task_id = resp.json()["task_id"]

    detail = await client.get(f"/api/v1/tasks/{task_id}", headers=_h(token))
    assert detail.status_code == 200
    # 兼容策略：在统一 /runs 读路径落地前，task_id 暂兼作 run_id。
    assert detail.json()["run_id"] == task_id


async def test_task_tenant_isolation(client: AsyncClient) -> None:
    token_a = create_access_token(user_id="a", tenant_id="tA", roles=["member"])
    token_b = create_access_token(user_id="b", tenant_id="tB", roles=["member"])
    resp = await client.post("/api/v1/tasks", json={"goal": "x"}, headers=_h(token_a))
    task_id = resp.json()["task_id"]
    # 租户 B 看不到 A 的任务
    r = await client.get(f"/api/v1/tasks/{task_id}", headers=_h(token_b))
    assert r.status_code == 404


async def test_task_list(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    await client.post("/api/v1/tasks", json={"goal": "a"}, headers=_h(token))
    await client.post("/api/v1/tasks", json={"goal": "b"}, headers=_h(token))
    r = await client.get("/api/v1/tasks", headers=_h(token))
    assert r.status_code == 200
    assert len(r.json()["tasks"]) >= 2
    first = r.json()["tasks"][0]
    assert {"run_id", "source", "intent_type", "route_source", "updated_at"} <= set(first)
    assert first["route_source"] == "fallback"


async def test_task_runner_direct() -> None:
    runner = get_task_runner()

    async def _ok():
        await asyncio.sleep(0.01)
        return {"done": True}

    tid = runner.submit(
        _ok,
        kind="test",
        tenant_id="t1",
        owner_id="owner-1",
        input_payload={"goal": "ping"},
    )
    for _ in range(20):
        rec = runner.get(tid, "t1")
        if rec.status.value in ("succeeded", "failed"):
            break
        await asyncio.sleep(0.02)
    assert rec.status.value == "succeeded"
    assert rec.result == {"done": True}
    assert rec.started_at
    view = rec.to_dict()
    assert view["run_id"] == tid
    assert view["owner_id"] == "owner-1"
    assert view["input"] == {"goal": "ping"}
    assert view["updated_at"]


async def test_submit_task_returns_error_when_initial_celery_persist_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException
    from xagent.api.v1.tasks import submit_task
    from xagent.enterprise.auth.principal import Principal

    principal = Principal(user_id="u-fail", tenant_id="tenant-fail", roles=frozenset({"member"}))

    class _AsyncResultStub:
        def __init__(self, task_id: str) -> None:
            self.id = task_id

    class _SharedCeleryAppStub:
        def send_task(
            self,
            name: str,
            kwargs: dict,
            task_id: str | None = None,
        ) -> _AsyncResultStub:
            assert name == "xagent.run_agent"
            assert kwargs["tenant_id"] == principal.tenant_id
            assert task_id
            return _AsyncResultStub(task_id)

    async def _persist_fail(**kwargs):  # noqa: ARG001
        raise RuntimeError("persist failed")

    monkeypatch.setattr("xagent.api.v1.tasks.get_celery_app", lambda: _SharedCeleryAppStub())
    monkeypatch.setattr("xagent.api.v1.tasks.persist_submitted_agent_task", _persist_fail)
    monkeypatch.setattr("xagent.api.v1.tasks.attach_run_to_task", AsyncMock(return_value=None))

    body = type(
        "Body",
        (),
        {
            "goal": "首次持久化失败",
            "goal_id": "",
            "spine_task_id": "",
            "role": None,
            "capabilities": [],
        },
    )()

    with pytest.raises(HTTPException) as exc_info:
        await submit_task(body=body, principal=principal)

    assert exc_info.value.status_code == 503


async def test_task_submit_reuses_shared_celery_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from xagent.api.v1.tasks import submit_task
    from xagent.enterprise.auth.principal import Principal

    principal = Principal(
        user_id="u-shared", tenant_id="tenant-shared", roles=frozenset({"member"})
    )

    class _AsyncResultStub:
        def __init__(self, task_id: str) -> None:
            self.id = task_id

    class _SharedCeleryAppStub:
        def send_task(
            self,
            name: str,
            kwargs: dict,
            task_id: str | None = None,
        ) -> _AsyncResultStub:
            assert name == "xagent.run_agent"
            assert kwargs["tenant_id"] == principal.tenant_id
            assert kwargs["user_id"] == principal.user_id
            assert kwargs["tool_mode"] == "auto"
            assert task_id
            return _AsyncResultStub(task_id)

    async def _persist_stub(**kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr("xagent.api.v1.tasks.get_celery_app", lambda: _SharedCeleryAppStub())
    monkeypatch.setattr("xagent.api.v1.tasks.persist_submitted_agent_task", _persist_stub)
    monkeypatch.setattr("xagent.api.v1.tasks.attach_run_to_task", AsyncMock(return_value=None))

    body = type(
        "Body",
        (),
        {
            "goal": "复用共享 Celery app",
            "goal_id": "",
            "spine_task_id": "",
            "role": None,
            "capabilities": [],
        },
    )()
    created = await submit_task(body=body, principal=principal)

    assert created["task_id"]
    assert created["backend"] == "celery"


async def test_task_submit_tool_mode_none_forwards_to_celery_and_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from xagent.api.v1.tasks import TaskSubmitIn, submit_task
    from xagent.enterprise.auth.principal import Principal

    principal = Principal(
        user_id="u-tool-mode", tenant_id="tenant-tool-mode", roles=frozenset({"member"})
    )
    sent: dict[str, object] = {}
    persisted: dict[str, object] = {}

    class _AsyncResultStub:
        id = "celery-tool-mode-none"

    class _SharedCeleryAppStub:
        def send_task(self, name: str, kwargs: dict, task_id: str | None = None):
            sent.update(name=name, kwargs=kwargs, task_id=task_id)
            return _AsyncResultStub()

    async def _persist_stub(**kwargs) -> None:
        persisted.update(kwargs)

    monkeypatch.setattr("xagent.api.v1.tasks.get_celery_app", lambda: _SharedCeleryAppStub())
    monkeypatch.setattr("xagent.api.v1.tasks.persist_submitted_agent_task", _persist_stub)
    monkeypatch.setattr("xagent.api.v1.tasks._try_attach_spine_task", AsyncMock(return_value=None))

    created = await submit_task(
        body=TaskSubmitIn(goal="exact background chat", tool_mode="none"),
        principal=principal,
    )

    expected_input = {
        "goal": "exact background chat",
        "role": None,
        "capabilities": [],
        "tool_mode": "none",
        "route": "chat_no_tools",
    }
    assert sent["name"] == "xagent.run_agent"
    assert sent["kwargs"]["tool_mode"] == "none"
    assert persisted["input_payload"] == expected_input
    assert created["input"] == expected_input


async def test_task_submit_tool_mode_none_forwards_to_inproc_run_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from xagent.api.v1.tasks import TaskSubmitIn, submit_task
    from xagent.enterprise.auth.principal import Principal

    principal = Principal(
        user_id="u-tool-mode-inproc",
        tenant_id="tenant-tool-mode-inproc",
        roles=frozenset({"member"}),
    )
    captured: dict[str, object] = {}
    called = asyncio.Event()

    async def _fake_run_agent(goal: str, **kwargs):
        captured.update(goal=goal, **kwargs)
        called.set()

        class _Run:
            def to_dict(self) -> dict[str, object]:
                return {"status": "succeeded", "final_answer": "done"}

        return _Run()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def commit(self) -> None:
            return None

    monkeypatch.setattr("xagent.api.v1.tasks.get_celery_app", lambda: None)
    monkeypatch.setattr("xagent.api.v1.tasks.run_agent", _fake_run_agent)
    monkeypatch.setattr("xagent.api.v1.tasks._try_attach_spine_task", AsyncMock(return_value=None))
    monkeypatch.setattr("xagent.api.v1.tasks.get_sessionmaker", lambda: lambda: _Session())
    monkeypatch.setattr("xagent.api.v1.tasks.update_task_status_by_run_id", AsyncMock())

    created = await submit_task(
        body=TaskSubmitIn(goal="exact inproc chat", tool_mode="none"),
        principal=principal,
    )
    await asyncio.wait_for(called.wait(), timeout=1)
    for _ in range(50):
        record = get_task_runner().get(created["task_id"], principal.tenant_id)
        if record is not None and record.status.value == "succeeded":
            break
        await asyncio.sleep(0.01)

    assert captured["tool_mode"] == "none"
    assert record is not None
    assert record.status.value == "succeeded"
    assert created["input"] == {
        "goal": "exact inproc chat",
        "role": None,
        "capabilities": [],
        "tool_mode": "none",
        "route": "chat_no_tools",
    }


def test_task_submit_default_auto_preserves_legacy_input_shape() -> None:
    from xagent.api.v1.tasks import TaskSubmitIn, _build_input_payload

    body = TaskSubmitIn(goal="legacy task")

    assert body.tool_mode == "auto"
    assert _build_input_payload(body) == {
        "goal": "legacy task",
        "role": None,
        "capabilities": [],
    }


async def test_task_list_refreshes_celery_terminal_status_from_backend(
    monkeypatch: pytest.MonkeyPatch,
    migrated_db,
) -> None:
    from datetime import UTC, datetime

    from xagent.enterprise.auth.principal import Principal
    from xagent.infra.db import get_sessionmaker
    from xagent.infra.models.agent_task import AgentTaskORM

    principal = Principal(
        user_id="u-list-live", tenant_id="tenant-list-live", roles=frozenset({"member"})
    )

    async with get_sessionmaker()() as session:
        session.add(
            AgentTaskORM(
                task_id="celery-list-live",
                run_id="celery-list-live",
                tenant_id=principal.tenant_id,
                owner_id=principal.user_id,
                kind="agent.run",
                status="pending",
                backend="celery",
                source="task",
                intent_type="agent",
                route_source="fallback",
                input_payload=json.dumps({"goal": "列表读真实 Celery 状态"}, ensure_ascii=False),
                result_payload=json.dumps({}, ensure_ascii=False),
                started_at=datetime.now(UTC),
            )
        )
        await session.commit()

    class _AsyncResultStub:
        state = "SUCCESS"
        result = {"final_answer": "done"}

        def successful(self) -> bool:
            return True

        def failed(self) -> bool:
            return False

    class _SharedCeleryAppStub:
        def AsyncResult(self, task_id: str):  # noqa: N802
            assert task_id == "celery-list-live"
            return _AsyncResultStub()

    monkeypatch.setattr("xagent.api.v1.tasks.get_celery_app", lambda: _SharedCeleryAppStub())

    token = create_access_token(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        roles=["member"],
    )
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        resp = await http_client.get("/api/v1/tasks", headers=_h(token))

    assert resp.status_code == 200, resp.text
    item = next(task for task in resp.json()["tasks"] if task["task_id"] == "celery-list-live")
    assert item["status"] == "succeeded"
    assert item["result"]["final_answer"] == "done"


async def test_task_list_uses_persisted_celery_status(
    monkeypatch: pytest.MonkeyPatch,
    migrated_db,
) -> None:
    from datetime import UTC, datetime

    from xagent.api.v1.tasks import submit_task
    from xagent.enterprise.auth.principal import Principal
    from xagent.infra.db import get_sessionmaker
    from xagent.infra.models.agent_task import AgentTaskORM
    from xagent.infra.settings import get_settings

    principal = Principal(user_id="u-list", tenant_id="tenant-list", roles=frozenset({"member"}))

    class _AsyncResultStub:
        def __init__(self, task_id: str) -> None:
            self.id = task_id

    class _SharedCeleryAppStub:
        def send_task(
            self,
            name: str,
            kwargs: dict,
            task_id: str | None = None,
        ) -> _AsyncResultStub:
            assert name == "xagent.run_agent"
            assert kwargs["tenant_id"] == principal.tenant_id
            assert task_id
            return _AsyncResultStub(task_id)

    monkeypatch.setenv("XAGENT_CACHE__REDIS_URL", "redis://stub-broker")
    get_settings.cache_clear()
    monkeypatch.setattr("xagent.api.v1.tasks.get_celery_app", lambda: _SharedCeleryAppStub())

    body = type(
        "Body",
        (),
        {
            "goal": "列表状态回查",
            "goal_id": "",
            "spine_task_id": "",
            "role": "planner",
            "capabilities": [],
        },
    )()
    created = await submit_task(body=body, principal=principal)
    assert created["status"] == "pending"
    task_id = created["task_id"]

    async with get_sessionmaker()() as session:
        row = await session.get(AgentTaskORM, task_id)
        assert row is not None
        row.status = "succeeded"
        row.result_payload = json.dumps({"final_answer": "done"}, ensure_ascii=False)
        row.error = ""
        row.started_at = datetime.now(UTC)
        row.finished_at = datetime.now(UTC)
        await session.commit()

    token = create_access_token(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        roles=["member"],
    )
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        resp = await http_client.get("/api/v1/tasks", headers=_h(token))

    assert resp.status_code == 200, resp.text
    item = next(task for task in resp.json()["tasks"] if task["task_id"] == task_id)
    assert item["status"] == "succeeded"
    assert item["result"]["final_answer"] == "done"
    assert item["finished_at"]


def test_celery_worker_uses_task_id_as_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from xagent.worker.celery_app import run_agent_task

    captured: dict[str, object] = {}

    async def _fake_run_agent(goal: str, **kwargs):
        captured["goal"] = goal
        captured.update(kwargs)

        class _Run:
            def to_dict(self) -> dict[str, object]:
                return {
                    "run_id": kwargs["run_id"],
                    "goal": goal,
                    "final_answer": "done",
                    "events": [],
                }

        return _Run()

    class _Request:
        id = "celery-task-run-id"

    class _CurrentTask:
        request = _Request()

    monkeypatch.setattr("celery.current_task", _CurrentTask())
    monkeypatch.setattr("xagent.core.orchestration.run_agent", _fake_run_agent)
    monkeypatch.setattr("xagent.worker.celery_app.persist_submitted_agent_task", AsyncMock())
    monkeypatch.setattr(
        "xagent.worker.celery_app.persist_agent_task_record_in_session", AsyncMock()
    )
    monkeypatch.setattr("xagent.worker.celery_app.update_task_status_by_run_id", AsyncMock())

    result = run_agent_task(
        goal="Celery run id",
        role="planner",
        capabilities=["search"],
        tenant_id="tenant-celery",
        user_id="user-celery",
    )

    assert captured["run_id"] == "celery-task-run-id"
    assert captured["tool_mode"] == "auto"
    assert result["run_id"] == "celery-task-run-id"


def test_celery_worker_failed_result_does_not_persist_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from xagent.worker.celery_app import run_agent_task

    async def _fake_run_agent(goal: str, **kwargs):
        return AgentRun(
            run_id=kwargs["run_id"],
            goal=goal,
            role_name="general",
            tenant_id="tenant-celery",
            final_answer="执行过程中出错：model_empty_response_after_retry",
            steps=1,
            status="failed",
            error="model_empty_response_after_retry",
        )

    class _Request:
        id = "celery-failed-run-id"

    class _CurrentTask:
        request = _Request()

    persist_record = AsyncMock()
    update_status = AsyncMock()
    monkeypatch.setattr("celery.current_task", _CurrentTask())
    monkeypatch.setattr("xagent.core.orchestration.run_agent", _fake_run_agent)
    monkeypatch.setattr("xagent.worker.celery_app.persist_submitted_agent_task", AsyncMock())
    monkeypatch.setattr(
        "xagent.worker.celery_app.persist_agent_task_record_in_session",
        persist_record,
    )
    monkeypatch.setattr(
        "xagent.worker.celery_app.update_task_status_by_run_id",
        update_status,
    )

    with pytest.raises(RuntimeError, match="model_empty_response_after_retry"):
        run_agent_task(
            goal="空响应恢复失败",
            role="general",
            capabilities=[],
            tenant_id="tenant-celery",
            user_id="user-celery",
        )

    assert persist_record.await_args.kwargs["status"] == "failed"
    assert persist_record.await_args.kwargs["error"] == "model_empty_response_after_retry"
    assert update_status.await_args.kwargs["next_status"] == "recovery"


def test_celery_worker_tool_mode_none_forwards_and_persists_terminal_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from xagent.worker.celery_app import run_agent_task

    captured: dict[str, object] = {}

    async def _fake_run_agent(goal: str, **kwargs):
        captured.update(goal=goal, **kwargs)

        class _Run:
            status = "succeeded"

            def to_dict(self) -> dict[str, object]:
                return {"status": self.status, "final_answer": "done"}

        return _Run()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def commit(self) -> None:
            return None

    class _CurrentTask:
        request = type("Request", (), {"id": "celery-tool-mode-none"})()

    persist_running = AsyncMock()
    persist_terminal = AsyncMock()
    monkeypatch.setattr("celery.current_task", _CurrentTask())
    monkeypatch.setattr("xagent.core.orchestration.run_agent", _fake_run_agent)
    monkeypatch.setattr("xagent.worker.celery_app.persist_submitted_agent_task", persist_running)
    monkeypatch.setattr(
        "xagent.worker.celery_app.persist_agent_task_record_in_session", persist_terminal
    )
    monkeypatch.setattr("xagent.worker.celery_app.update_task_status_by_run_id", AsyncMock())
    monkeypatch.setattr("xagent.infra.db.get_sessionmaker", lambda: lambda: _Session())
    monkeypatch.setattr("xagent.infra.db.dispose_engine", AsyncMock())

    result = run_agent_task(
        goal="exact worker chat",
        role="general",
        capabilities=[],
        tenant_id="tenant-celery",
        user_id="user-celery",
        tool_mode="none",
    )

    expected_input = {
        "goal": "exact worker chat",
        "role": "general",
        "capabilities": [],
        "tool_mode": "none",
        "route": "chat_no_tools",
    }
    assert result["status"] == "succeeded"
    assert captured["tool_mode"] == "none"
    assert persist_running.await_args.kwargs["input_payload"] == expected_input
    assert persist_terminal.await_args.kwargs["input_payload"] == expected_input


@pytest.mark.parametrize(
    ("run_error", "terminal_status", "next_status"),
    [
        (None, "succeeded", "review"),
        (RuntimeError("provider failed"), "failed", "recovery"),
    ],
)
def test_celery_worker_lifecycle_uses_one_event_loop(
    monkeypatch: pytest.MonkeyPatch,
    run_error: RuntimeError | None,
    terminal_status: str,
    next_status: str,
) -> None:
    from xagent.worker.celery_app import run_agent_task

    observed_loops: list[tuple[str, asyncio.AbstractEventLoop]] = []

    def _record_loop(phase: str) -> None:
        observed_loops.append((phase, asyncio.get_running_loop()))

    async def _persist_submitted(**kwargs) -> None:
        assert kwargs["status"] == "running"
        _record_loop("running")

    async def _fake_run_agent(goal: str, **kwargs):
        _record_loop("run_agent")
        if run_error is not None:
            raise run_error

        class _Run:
            status = "succeeded"

            def to_dict(self) -> dict[str, object]:
                return {
                    "run_id": kwargs["run_id"],
                    "goal": goal,
                    "status": self.status,
                    "final_answer": "done",
                }

        return _Run()

    async def _persist_terminal(_session, **kwargs) -> None:
        assert kwargs["status"] == terminal_status
        assert kwargs["error"] == ("provider failed" if run_error else "")
        _record_loop(terminal_status)

    async def _update_status(_session, **kwargs) -> None:
        assert kwargs["next_status"] == next_status
        if run_error is not None:
            assert kwargs["blocker_reason"] == "provider failed"

    async def _dispose_engine() -> None:
        _record_loop("disposed")

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def commit(self) -> None:
            return None

    class _CurrentTask:
        request = type("Request", (), {"id": f"celery-single-loop-{terminal_status}"})()

    monkeypatch.setattr("celery.current_task", _CurrentTask())
    monkeypatch.setattr("xagent.core.orchestration.run_agent", _fake_run_agent)
    monkeypatch.setattr("xagent.worker.celery_app.persist_submitted_agent_task", _persist_submitted)
    monkeypatch.setattr(
        "xagent.worker.celery_app.persist_agent_task_record_in_session", _persist_terminal
    )
    monkeypatch.setattr("xagent.worker.celery_app.update_task_status_by_run_id", _update_status)
    monkeypatch.setattr("xagent.infra.db.get_sessionmaker", lambda: lambda: _Session())
    monkeypatch.setattr("xagent.infra.db.dispose_engine", _dispose_engine)

    if run_error is not None:
        with pytest.raises(RuntimeError, match="provider failed"):
            run_agent_task(
                goal="single loop failure",
                role="general",
                capabilities=[],
                tenant_id="tenant-celery",
                user_id="user-celery",
            )
    else:
        result = run_agent_task(
            goal="single loop success",
            role="general",
            capabilities=[],
            tenant_id="tenant-celery",
            user_id="user-celery",
        )
        assert result["status"] == "succeeded"

    assert [phase for phase, _loop in observed_loops] == [
        "running",
        "run_agent",
        terminal_status,
        "disposed",
    ]
    assert all(loop is observed_loops[0][1] for _phase, loop in observed_loops)


@pytest.mark.parametrize(
    ("provider_error", "terminal_status", "next_status"),
    [
        (None, "succeeded", "review"),
        (RuntimeError("provider failed"), "failed", "recovery"),
    ],
    ids=["success", "provider-failure"],
)
def test_celery_worker_dispose_failure_does_not_override_lifecycle_outcome(
    monkeypatch: pytest.MonkeyPatch,
    provider_error: RuntimeError | None,
    terminal_status: str,
    next_status: str,
) -> None:
    from xagent.worker.celery_app import run_agent_task

    async def _fake_run_agent(goal: str, **kwargs):
        if provider_error is not None:
            raise provider_error

        class _Run:
            status = "succeeded"

            def to_dict(self) -> dict[str, object]:
                return {
                    "run_id": kwargs["run_id"],
                    "goal": goal,
                    "status": self.status,
                    "final_answer": "done",
                }

        return _Run()

    async def _dispose_engine() -> None:
        raise RuntimeError("dispose failed")

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def commit(self) -> None:
            return None

    class _CurrentTask:
        request = type("Request", (), {"id": f"celery-dispose-{terminal_status}"})()

    persist_terminal = AsyncMock()
    update_status = AsyncMock()
    warning = Mock()
    monkeypatch.setattr("celery.current_task", _CurrentTask())
    monkeypatch.setattr("xagent.core.orchestration.run_agent", _fake_run_agent)
    monkeypatch.setattr("xagent.worker.celery_app.persist_submitted_agent_task", AsyncMock())
    monkeypatch.setattr(
        "xagent.worker.celery_app.persist_agent_task_record_in_session", persist_terminal
    )
    monkeypatch.setattr("xagent.worker.celery_app.update_task_status_by_run_id", update_status)
    monkeypatch.setattr("xagent.worker.celery_app.logger.warning", warning)
    monkeypatch.setattr("xagent.infra.db.get_sessionmaker", lambda: lambda: _Session())
    monkeypatch.setattr("xagent.infra.db.dispose_engine", _dispose_engine)

    if provider_error is not None:
        with pytest.raises(RuntimeError, match="provider failed") as exc_info:
            run_agent_task(
                goal="dispose after provider failure",
                role="general",
                capabilities=[],
                tenant_id="tenant-celery",
                user_id="user-celery",
            )
        assert exc_info.value is provider_error
    else:
        result = run_agent_task(
            goal="dispose after success",
            role="general",
            capabilities=[],
            tenant_id="tenant-celery",
            user_id="user-celery",
        )
        assert result["status"] == "succeeded"

    assert persist_terminal.await_args.kwargs["status"] == terminal_status
    assert persist_terminal.await_args.kwargs["error"] == (
        "provider failed" if provider_error else ""
    )
    assert update_status.await_args.kwargs["next_status"] == next_status
    warning.assert_called_once_with(
        "celery_db_engine_dispose_failed",
        task_id=f"celery-dispose-{terminal_status}",
        error="dispose failed",
    )


def test_late_pending_persist_does_not_clobber_terminal_result(migrated_db) -> None:
    import asyncio
    from datetime import UTC, datetime

    from xagent.infra.db import get_sessionmaker
    from xagent.infra.models.agent_task import AgentTaskORM
    from xagent.worker.celery_app import _upsert_agent_task, persist_submitted_agent_task

    async def _prepare_terminal_row() -> None:
        async with get_sessionmaker()() as session:
            await _upsert_agent_task(
                session,
                task_id="celery-race-task",
                tenant_id="tenant-race",
                owner_id="u-race",
                kind="agent.run",
                backend="celery",
                status="succeeded",
                input_payload={"goal": "worker 先完成"},
                result_payload={"final_answer": "already done"},
                error="",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
            await session.commit()

    asyncio.run(_prepare_terminal_row())

    asyncio.run(
        persist_submitted_agent_task(
            task_id="celery-race-task",
            tenant_id="tenant-race",
            owner_id="u-race",
            kind="agent.run",
            backend="celery",
            input_payload={"goal": "API 迟到 pending", "role": "planner", "capabilities": []},
            status="pending",
        )
    )

    async def _assert_row() -> None:
        async with get_sessionmaker()() as session:
            row = await session.get(AgentTaskORM, "celery-race-task")
            assert row is not None
            assert row.status == "succeeded"
            assert json.loads(row.result_payload)["final_answer"] == "already done"
            assert row.started_at is not None
            assert row.finished_at is not None
            assert row.error == ""
            payload = json.loads(row.input_payload)
            assert payload["goal"] == "API 迟到 pending"

    asyncio.run(_assert_row())


async def test_persisted_pending_task_uses_celery_terminal_status(
    monkeypatch: pytest.MonkeyPatch,
    migrated_db,
) -> None:
    from datetime import UTC, datetime

    from xagent.api.v1.tasks import get_task_runtime_view
    from xagent.infra.db import get_sessionmaker
    from xagent.infra.models.agent_task import AgentTaskORM

    async with get_sessionmaker()() as session:
        session.add(
            AgentTaskORM(
                task_id="celery-live-status",
                run_id="celery-live-status",
                tenant_id="tenant-live",
                owner_id="u-live",
                kind="agent.run",
                status="pending",
                backend="celery",
                source="task",
                intent_type="agent",
                route_source="fallback",
                input_payload=json.dumps({"goal": "等待完成"}, ensure_ascii=False),
                result_payload=json.dumps({}, ensure_ascii=False),
                started_at=datetime.now(UTC),
            )
        )
        await session.commit()

    class _AsyncResultStub:
        state = "SUCCESS"
        result = {"final_answer": "done"}

        def successful(self) -> bool:
            return True

        def failed(self) -> bool:
            return False

    class _SharedCeleryAppStub:
        def AsyncResult(self, task_id: str):  # noqa: N802
            assert task_id == "celery-live-status"
            return _AsyncResultStub()

    monkeypatch.setattr("xagent.api.v1.tasks.get_celery_app", lambda: _SharedCeleryAppStub())

    view = await get_task_runtime_view("celery-live-status", "tenant-live")

    assert view is not None
    assert view["status"] == "succeeded"
    assert view["result"]["final_answer"] == "done"


async def test_celery_task_metadata_persists_and_can_be_reloaded(
    monkeypatch: pytest.MonkeyPatch,
    migrated_db,
) -> None:
    from xagent.api.v1.tasks import (
        _task_metadata,
        _task_tenants,
        get_task_runtime_view,
        submit_task,
    )
    from xagent.enterprise.auth.principal import Principal
    from xagent.infra.db import get_sessionmaker
    from xagent.infra.models.agent_task import AgentTaskORM
    from xagent.infra.settings import get_settings

    principal = Principal(
        user_id="u-celery", tenant_id="tenant-celery", roles=frozenset({"member"})
    )

    class _AsyncResultStub:
        def __init__(self, task_id: str) -> None:
            self.id = task_id

    class _SharedCeleryAppStub:
        def send_task(
            self,
            name: str,
            kwargs: dict,
            task_id: str | None = None,
        ) -> _AsyncResultStub:
            assert name == "xagent.run_agent"
            assert kwargs["tenant_id"] == principal.tenant_id
            assert kwargs["user_id"] == principal.user_id
            assert task_id
            return _AsyncResultStub(task_id)

    monkeypatch.setenv("XAGENT_CACHE__REDIS_URL", "redis://stub-broker")
    get_settings.cache_clear()
    monkeypatch.setattr("xagent.api.v1.tasks.get_celery_app", lambda: _SharedCeleryAppStub())

    body = type(
        "Body",
        (),
        {
            "goal": "持久化 Celery 元数据",
            "goal_id": "",
            "spine_task_id": "",
            "role": "planner",
            "capabilities": ["search"],
        },
    )()
    created = await submit_task(body=body, principal=principal)

    task_id = created["task_id"]
    assert task_id
    assert created["backend"] == "celery"
    assert created["status"] == "pending"

    async with get_sessionmaker()() as session:
        row = await session.get(AgentTaskORM, task_id)
        assert row is not None
        assert row.tenant_id == principal.tenant_id
        assert row.owner_id == principal.user_id
        assert row.kind == "agent.run"
        assert row.backend == "celery"
        assert row.status == "pending"
        assert json.loads(row.input_payload) == {
            "goal": "持久化 Celery 元数据",
            "role": "planner",
            "capabilities": ["search"],
        }

    _task_tenants.clear()
    _task_metadata.clear()
    reloaded = await get_task_runtime_view(task_id, principal.tenant_id)
    assert reloaded is not None
    assert reloaded["task_id"] == task_id
    assert reloaded["backend"] == "celery"
    assert reloaded["status"] == "pending"
    assert reloaded["owner_id"] == principal.user_id
    assert reloaded["input"] == {
        "goal": "持久化 Celery 元数据",
        "role": "planner",
        "capabilities": ["search"],
    }


def test_celery_worker_updates_persisted_task_result(
    monkeypatch: pytest.MonkeyPatch, migrated_db
) -> None:
    import asyncio

    from xagent.infra.db import get_sessionmaker
    from xagent.infra.models.agent_task import AgentTaskORM
    from xagent.worker.celery_app import persist_submitted_agent_task, run_agent_task

    class _CurrentTaskStub:
        request = type("Request", (), {"id": "celery-task-final"})()

    class _AgentResult:
        def to_dict(self) -> dict:
            return {"final_answer": "done", "timeline": [{"kind": "finished"}]}

    async def _fake_run_agent(
        goal,
        principal,
        role_name=None,
        capabilities=None,
        run_id=None,
        tool_mode="auto",
    ):  # noqa: ARG001
        assert tool_mode == "auto"
        return _AgentResult()

    asyncio.run(
        persist_submitted_agent_task(
            task_id="celery-task-final",
            tenant_id="tenant-celery",
            owner_id="u-celery",
            kind="agent.run",
            backend="celery",
            input_payload={
                "goal": "执行 Celery 任务",
                "role": "planner",
                "capabilities": ["search"],
            },
            status="pending",
        )
    )

    monkeypatch.setattr("celery.current_task", _CurrentTaskStub)
    monkeypatch.setattr("xagent.core.orchestration.run_agent", _fake_run_agent)

    result = run_agent_task(
        goal="执行 Celery 任务",
        role="planner",
        capabilities=["search"],
        tenant_id="tenant-celery",
        user_id="u-celery",
    )
    assert result["final_answer"] == "done"

    async def _assert_row() -> None:
        async with get_sessionmaker()() as session:
            row = await session.get(AgentTaskORM, "celery-task-final")
            assert row is not None
            assert row.status == "succeeded"
            assert row.backend == "celery"
            assert row.started_at is not None
            assert row.finished_at is not None
            assert row.error == ""
            assert json.loads(row.result_payload)["final_answer"] == "done"

    asyncio.run(_assert_row())
