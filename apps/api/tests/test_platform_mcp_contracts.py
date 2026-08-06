"""Platform MCP tenant/RBAC/audit contracts for durable Web/API resources."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from xagent.adapters.mcp import platform_server
from xagent.core.orchestration.conversation import (
    ConversationSession,
    persist_conversation,
    persist_message,
)
from xagent.enterprise.audit import get_audit_log
from xagent.infra.db import Base, get_engine, get_sessionmaker
from xagent.infra.models.development_task import DevelopmentTaskORM
from xagent.infra.models.scheduled_job import ScheduledJobORM, ScheduledJobRunORM
from xagent.infra.models.skill_package import SkillPackageORM
from xagent.worker import get_task_runner


@pytest.fixture
async def mcp_tenant(monkeypatch):
    tenant_id = f"tenant-mcp-{uuid.uuid4().hex}"
    other_tenant = f"tenant-other-{uuid.uuid4().hex}"
    monkeypatch.setenv("XAGENT_PLATFORM_MCP_TENANT_ID", tenant_id)
    monkeypatch.setenv("XAGENT_PLATFORM_MCP_USER_ID", "mcp-contract-user")
    monkeypatch.setenv("XAGENT_PLATFORM_MCP_ROLES", "admin")
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return tenant_id, other_tenant


async def test_conversation_reads_are_tenant_scoped_and_redacted(mcp_tenant) -> None:
    tenant_id, other_tenant = mcp_tenant
    own_id = f"conversation-{uuid.uuid4().hex}"
    other_id = f"conversation-{uuid.uuid4().hex}"
    async with get_sessionmaker()() as session:
        for conversation_id, tenant in ((own_id, tenant_id), (other_id, other_tenant)):
            conversation = ConversationSession(conversation_id, tenant)
            conversation.add_user("Authorization: Bearer top-secret-token")
            await persist_conversation(session, conversation)
            await persist_message(
                session, conversation_id, "user", conversation.messages[0].content
            )
        await session.commit()

    listed = await platform_server.xagent_conversation_list()
    assert listed["ok"] is True
    assert [item["conversation_id"] for item in listed["items"]] == [own_id]
    own = await platform_server.xagent_conversation_get(own_id)
    assert own["ok"] is True
    assert "top-secret-token" not in str(own)
    assert "[REDACTED]" in str(own)
    assert await platform_server.xagent_conversation_get(other_id) == {
        "ok": False,
        "error": "conversation_not_found",
    }


async def test_approval_list_and_resolve_require_exact_confirmation(mcp_tenant) -> None:
    tenant_id, other_tenant = mcp_tenant
    task_id = f"task-{uuid.uuid4().hex}"
    other_task_id = f"task-{uuid.uuid4().hex}"
    async with get_sessionmaker()() as session:
        for current_id, tenant in ((task_id, tenant_id), (other_task_id, other_tenant)):
            session.add(
                DevelopmentTaskORM(
                    task_id=current_id,
                    parent_run_id=f"run-{current_id}",
                    sub_run_id=f"sub-{current_id}",
                    tenant_id=tenant,
                    owner_id="owner",
                    goal="review safely",
                    status="awaiting_review",
                    main_workspace="C:/private/workspace",
                    base_commit="base",
                    target_branch="main",
                    work_branch=f"work/{current_id}",
                    worktree_path="C:/private/worktree",
                    result_commit="result",
                    patch_path="C:/private/patch.diff",
                )
            )
        await session.commit()

    approval_id = f"development_task:{task_id}"
    listed = await platform_server.xagent_approval_list()
    assert [item["approval_id"] for item in listed["items"]] == [approval_id]
    assert "private" not in str(listed)
    mismatch = await platform_server.xagent_approval_resolve(
        approval_id, "approve", "wrong"
    )
    assert mismatch == {"ok": False, "error": "confirmation_mismatch"}
    approved = await platform_server.xagent_approval_resolve(
        approval_id, "approve", approval_id
    )
    assert approved["ok"] is True
    assert approved["approval"]["status"] == "approved"
    assert get_audit_log().list(tenant_id)[-1].action == "mcp.approval.approve"


async def test_workflow_approval_can_be_denied_without_crossing_tenant(
    mcp_tenant,
) -> None:
    tenant_id, _ = mcp_tenant
    from xagent.core.workflow import (
        ApprovalGate,
        WorkflowSpec,
        WorkflowStep,
        get_engine,
    )

    principal = platform_server._system_principal()
    assert principal.tenant_id == tenant_id
    engine = get_engine()
    run = engine.create_run(
        WorkflowSpec(
            name="mcp approval probe",
            steps=[
                WorkflowStep(
                    id="release",
                    name="Release",
                    approval=ApprovalGate(message="confirm release"),
                )
            ],
        ),
        principal,
    )
    await engine.execute(run.run_id, principal)
    approval_id = f"workflow:{run.run_id}:release"
    listed = await platform_server.xagent_approval_list()
    assert approval_id in {item["approval_id"] for item in listed["items"]}
    denied = await platform_server.xagent_approval_resolve(
        approval_id, "deny", approval_id
    )
    assert denied["ok"] is True
    assert denied["approval"]["status"] == "cancelled"
    assert get_audit_log().list(tenant_id)[-1].action == "mcp.approval.deny"


async def test_scheduler_and_skill_package_reads_hide_other_tenants_and_paths(
    mcp_tenant,
) -> None:
    tenant_id, other_tenant = mcp_tenant
    now = datetime.now(UTC)
    job_id = f"job-{uuid.uuid4().hex}"
    other_job_id = f"job-{uuid.uuid4().hex}"
    run_id = f"scheduled-run-{uuid.uuid4().hex}"
    package_id = f"package-{uuid.uuid4().hex}"
    async with get_sessionmaker()() as session:
        for current_job_id, tenant in ((job_id, tenant_id), (other_job_id, other_tenant)):
            session.add(
                ScheduledJobORM(
                    job_id=current_job_id,
                    tenant_id=tenant,
                    owner_id="owner",
                    name="nightly",
                    goal="token=super-secret-value",
                    interval_seconds=60,
                    next_run=now,
                )
            )
        session.add(
            ScheduledJobRunORM(
                run_id=run_id,
                job_id=job_id,
                tenant_id=tenant_id,
                scheduled_for=now,
                status="succeeded",
                attempt=0,
            )
        )
        session.add(
            SkillPackageORM(
                package_id=package_id,
                skill_id=f"skill-{uuid.uuid4().hex}",
                tenant_id=tenant_id,
                owner_id="owner",
                name="MCP package",
                version="1",
                content_hash=uuid.uuid4().hex * 2,
                manifest_json='{"files": [{"path": "SKILL.md"}]}',
                frontmatter_json='{"name": "MCP package"}',
                body="password: should-not-leak",
                root_path="C:/private/skill-package",
                source="test",
                file_count=1,
                total_size=20,
            )
        )
        await session.commit()

    jobs = await platform_server.xagent_scheduler_job_read()
    assert [item["job_id"] for item in jobs["items"]] == [job_id]
    assert "super-secret-value" not in str(jobs)
    runs = await platform_server.xagent_scheduler_run_read(run_id=run_id)
    assert runs["items"][0]["run_id"] == run_id
    package = await platform_server.xagent_skill_package_read(package_id)
    assert package["ok"] is True
    assert "root_path" not in str(package)
    assert "should-not-leak" not in str(package)
    package_list = await platform_server.xagent_skill_package_read()
    assert "body" not in package_list["items"][0]
    assert "frontmatter" not in package_list["items"][0]


async def test_run_events_are_redacted_and_inproc_run_can_be_cancelled(
    mcp_tenant,
) -> None:
    tenant_id, _ = mcp_tenant
    runner = get_task_runner()

    async def event_result():
        return {
            "events": [
                {"kind": "progress", "content": "Bearer secret-event-token"}
            ]
        }

    event_run = runner.submit(
        event_result,
        kind="agent.run",
        tenant_id=tenant_id,
        owner_id="mcp-contract-user",
    )
    await asyncio.sleep(0.05)
    events = await platform_server.xagent_run_events(event_run)
    assert events["ok"] is True
    assert "secret-event-token" not in str(events)

    blocker = asyncio.Event()

    async def wait_forever():
        await blocker.wait()

    cancellable_run = runner.submit(
        wait_forever,
        kind="agent.run",
        tenant_id=tenant_id,
        owner_id="mcp-contract-user",
    )
    await asyncio.sleep(0.05)
    mismatch = await platform_server.xagent_run_cancel(cancellable_run, "wrong")
    assert mismatch == {"ok": False, "error": "confirmation_mismatch"}
    cancelled = await platform_server.xagent_run_cancel(
        cancellable_run, cancellable_run
    )
    assert cancelled["ok"] is True
    assert cancelled["status"] == "cancelled"
    await asyncio.sleep(0)
    assert runner.get(cancellable_run, tenant_id).status.value == "cancelled"
    assert get_audit_log().list(tenant_id)[-1].action == "mcp.run.cancel"


async def test_mcp_run_is_persisted_for_run_get_and_events(
    mcp_tenant, monkeypatch
) -> None:
    tenant_id, _ = mcp_tenant

    class FakeRun:
        def __init__(self, run_id: str) -> None:
            self.run_id = run_id

        def to_dict(self):
            return {
                "run_id": self.run_id,
                "final_answer": "done",
                "steps": 2,
                "events": [
                    {"kind": "final", "content": "Bearer persisted-secret-token"}
                ],
            }

    async def fake_run_agent(goal, **kwargs):  # noqa: ARG001
        return FakeRun(kwargs["run_id"])

    monkeypatch.setattr("xagent.core.orchestration.run_agent", fake_run_agent)
    created = await platform_server.xagent_run("persist this run")
    assert created["ok"] is True
    detail = await platform_server.xagent_run_get(created["run_id"])
    assert detail["ok"] is True
    assert detail["run"]["task"]["status"] == "succeeded"
    events = await platform_server.xagent_run_events(created["run_id"])
    assert events["ok"] is True
    assert "persisted-secret-token" not in str(events)
    assert get_audit_log().list(tenant_id)[-1].action == "mcp.run.events"


async def test_viewer_cannot_mutate_conversation(mcp_tenant, monkeypatch) -> None:
    monkeypatch.setenv("XAGENT_PLATFORM_MCP_ROLES", "viewer")
    denied = await platform_server.xagent_conversation_message("missing", "hello")
    assert denied["ok"] is False
    assert denied["error"] == "forbidden"
