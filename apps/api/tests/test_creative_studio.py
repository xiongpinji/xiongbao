"""短剧工厂 + 媒体 provider + 质量门测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.domains.creative_studio import build_draft_from_brief
from xagent.domains.creative_studio.media import (
    GenerationRequest,
    GenerationTask,
    MediaKind,
    get_media_registry,
    reset_media_registry,
)
from xagent.domains.creative_studio.quality import run_gates
from xagent.domains.creative_studio.storyboard import (
    Shot,
    Storyboard,
)
from xagent.enterprise.auth import create_access_token
from xagent.infra.db import dispose_engine, get_sessionmaker
from xagent.infra.models.agent_task import AgentTaskORM
from xagent.infra.models.artifact import ArtifactORM
from xagent.infra.settings import get_settings
from xagent.main import create_app


def test_registry_image_defaults_to_null(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings.media, "default_image_provider", "null")
    reset_media_registry()

    registry = get_media_registry()

    assert registry.get(MediaKind.image) is registry.null


def test_registry_pollinations_requires_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings.media, "default_image_provider", "pollinations")
    reset_media_registry()

    assert get_media_registry().get(MediaKind.image).name == "pollinations"


def test_openai_without_key_falls_back_to_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings.media, "default_image_provider", "openai")
    monkeypatch.setattr(settings.media, "openai_image_api_key", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reset_media_registry()

    registry = get_media_registry()

    assert registry.get(MediaKind.image) is registry.null


def test_draft_node_chain_has_review_gate() -> None:
    draft = build_draft_from_brief("霸总逆袭短剧", genre="逆袭", platform="抖音")
    assert draft.status == "pending_review"
    types = [n.node_type for n in draft.nodes]
    assert "人工审核导出" in types
    assert "关键帧" in types and "视频" in types
    # 末节点为审核门
    assert draft.nodes[-1].needs_review is True


async def test_null_media_provider_returns_placeholder() -> None:
    reg = get_media_registry()
    task = await reg.get(MediaKind.image).submit(
        GenerationRequest(kind=MediaKind.image, prompt="测试画面")
    )
    assert task.status == "succeeded"
    assert task.outputs


def test_quality_gates_pass_on_valid_storyboard() -> None:
    sb = Storyboard(
        title="t",
        brief="b",
        target_duration_seconds=12.0,
        shots=[
            Shot(duration_seconds=4, plot_purpose="引入", dialogue="你好", subtitle="你好"),
            Shot(duration_seconds=4, plot_purpose="冲突", dialogue="不行", subtitle="不行"),
            Shot(duration_seconds=4, plot_purpose="收尾", dialogue="再见", subtitle="再见"),
        ],
    )
    gates = run_gates(sb)
    assert all(g.passed for g in gates), [g.detail for g in gates]


def test_quality_gates_fail_on_missing_fields() -> None:
    sb = Storyboard(
        target_duration_seconds=12.0,
        shots=[Shot(), Shot()],  # 空 shot，缺字段且数量不足
    )
    gates = run_gates(sb)
    field_gate = next(g for g in gates if g.name == "storyboard_fields")
    assert not field_gate.passed
    count_gate = next(g for g in gates if g.name == "shot_count")
    assert not count_gate.passed


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def migrated_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_file = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setenv("XAGENT_DB__URL", url)
    get_settings.cache_clear()
    await dispose_engine()

    api_dir = str(Path(__file__).resolve().parent.parent)
    env = {**os.environ, "XAGENT_DB__URL": url, "PYTHONPATH": api_dir}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=api_dir,
        env=env,
        check=True,
        capture_output=True,
    )

    yield url

    await dispose_engine()
    get_settings.cache_clear()


@pytest.fixture
async def db_client(migrated_db):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def test_media_delivery_summary_pending_message_is_not_success_like() -> None:
    import xagent.api.v1.creative_studio as creative_api

    summary = creative_api._build_media_delivery_summary(
        kind="creative.media.image",
        provider="stub",
        outputs=[],
    )

    assert summary == {
        "status": "pending",
        "channel": "media_outputs",
        "kind": "creative.media",
        "summary": "image 产物尚未生成，等待媒体任务完成。",
        "outputs": [],
        "provider": "stub",
    }


async def test_creative_draft_api(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.post(
        "/api/v1/creative-studio/workflow-draft",
        json={"brief": "甜宠短剧", "genre": "甜宠", "platform": "快手"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["status"] == "pending_review"
    assert doc["tenant_id"] == "t1"
    draft_id = doc["draft_id"]

    # 审核通过
    r2 = await client.post(
        f"/api/v1/creative-studio/workflow-draft/{draft_id}/review",
        json={"approved": True, "comment": "ok"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "approved"


async def test_creative_media_generate_same_prompt_allocates_distinct_task_ids(
    client: AsyncClient,
) -> None:
    token = create_access_token(user_id="u-same", tenant_id="tenant-1", roles=["member"])
    first = await client.post(
        "/api/v1/creative-studio/media/generate",
        json={"kind": "image", "prompt": "同一个提示词", "mode": "text_to_image", "wait": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    second = await client.post(
        "/api/v1/creative-studio/media/generate",
        json={"kind": "image", "prompt": "同一个提示词", "mode": "text_to_image", "wait": False},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["task_id"] != second.json()["task_id"]


async def test_creative_media_poll_without_runtime_cache_still_persists_final_state(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.api.v1.creative_studio as creative_api

    queued_task_id = "queued-image-task-no-cache"
    token = create_access_token(user_id="u-async-no-cache", tenant_id="tenant-1", roles=["member"])

    async def _fake_generate(req, *, wait=True):  # noqa: ARG001
        return GenerationTask(task_id=queued_task_id, provider="stub", status="queued", outputs=[])

    async def _fake_poll(task_id: str):
        assert task_id == queued_task_id
        return GenerationTask(
            task_id=queued_task_id,
            provider="stub",
            status="succeeded",
            outputs=["https://cdn.example.com/final-image-no-cache.png"],
        )

    registry = creative_api.get_media_registry()
    monkeypatch.setattr(registry, "generate", _fake_generate)
    monkeypatch.setattr(registry, "poll_task", _fake_poll)
    monkeypatch.setattr(
        registry, "kind_of", lambda task_id: MediaKind.image if task_id == queued_task_id else None
    )

    generate_resp = await db_client.post(
        "/api/v1/creative-studio/media/generate",
        json={
            "kind": "image",
            "prompt": "异步媒体产物-无缓存",
            "mode": "text_to_image",
            "wait": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert generate_resp.status_code == 200, generate_resp.text

    creative_api._media_runtime_tasks.clear()
    creative_api._media_task_tenants[queued_task_id] = "tenant-1"

    poll_resp = await db_client.get(
        f"/api/v1/creative-studio/media/tasks/{queued_task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert poll_resp.status_code == 200, poll_resp.text
    assert poll_resp.json()["status"] == "succeeded"
    assert poll_resp.json()["outputs"] == ["https://cdn.example.com/final-image-no-cache.png"]

    creative_api._media_runtime_tasks.clear()
    creative_api._media_task_tenants[queued_task_id] = "tenant-1"

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{queued_task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["task"]["status"] == "succeeded"
    assert body["task"]["result"] == {
        "outputs": ["https://cdn.example.com/final-image-no-cache.png"]
    }
    evidence_kinds = [item["kind"] for item in body["evidence"]]
    assert evidence_kinds[0] == "request.input"
    assert "media.poll_result" in evidence_kinds
    assert "delivery.generated" in evidence_kinds
    assert body["delivery"]["provider"] == "stub"
    assert body["delivery"]["artifacts"] == [
        {
            "artifact_id": queued_task_id,
            "task_id": queued_task_id,
            "kind": "creative.media.image",
            "name": "image-output-1",
            "uri": "https://cdn.example.com/final-image-no-cache.png",
            "content_type": "image/png",
            "preview_summary": {"prompt": "异步媒体产物-无缓存", "mode": "text_to_image"},
        }
    ]
    assert body["delivery"]["validation"] == {"risks": []}
    assert body["delivery"]["outputs"] == [
        {
            "label": "image-1",
            "uri": "https://cdn.example.com/final-image-no-cache.png",
            "media_kind": "image",
        }
    ]
    assert body["artifacts"] == [
        {
            "artifact_id": queued_task_id,
            "run_id": queued_task_id,
            "task_id": queued_task_id,
            "tenant_id": "tenant-1",
            "kind": "creative.media.image",
            "name": "image-output-1",
            "uri": "https://cdn.example.com/final-image-no-cache.png",
            "content_type": "image/png",
            "size_bytes": 0,
            "checksum": "",
            "validation_summary": {},
            "delivery_summary": {
                "label": "image-1",
                "media_kind": "image",
                "provider": "stub",
            },
            "lineage_summary": {},
            "preview_summary": {"prompt": "异步媒体产物-无缓存", "mode": "text_to_image"},
        }
    ]


async def test_creative_media_poll_persists_final_state_to_db_after_memory_clear(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.api.v1.creative_studio as creative_api

    queued_task_id = "queued-image-task"
    token = create_access_token(user_id="u-async-media", tenant_id="tenant-1", roles=["member"])

    async def _fake_generate(req, *, wait=True):  # noqa: ARG001
        return GenerationTask(task_id=queued_task_id, provider="stub", status="running", outputs=[])

    async def _fake_poll(task_id: str):
        assert task_id == queued_task_id
        return GenerationTask(
            task_id=queued_task_id,
            provider="stub",
            status="succeeded",
            outputs=["https://cdn.example.com/final-image.png"],
        )

    monkeypatch.setattr(creative_api.get_media_registry(), "generate", _fake_generate)
    monkeypatch.setattr(creative_api.get_media_registry(), "poll_task", _fake_poll)
    monkeypatch.setattr(
        creative_api.get_media_registry(),
        "kind_of",
        lambda task_id: MediaKind.image if task_id == queued_task_id else None,
    )

    generate_resp = await db_client.post(
        "/api/v1/creative-studio/media/generate",
        json={
            "kind": "image",
            "prompt": "异步媒体产物",
            "mode": "text_to_image",
            "wait": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert generate_resp.status_code == 200, generate_resp.text
    assert generate_resp.json() == {
        "task_id": queued_task_id,
        "provider": "stub",
        "status": "running",
        "outputs": [],
        "error": None,
    }

    poll_resp = await db_client.get(
        f"/api/v1/creative-studio/media/tasks/{queued_task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert poll_resp.status_code == 200, poll_resp.text
    assert poll_resp.json() == {
        "task_id": queued_task_id,
        "kind": "image",
        "provider": "stub",
        "status": "succeeded",
        "outputs": ["https://cdn.example.com/final-image.png"],
        "error": None,
    }

    creative_api._media_runtime_tasks.clear()
    creative_api._media_task_tenants[queued_task_id] = "tenant-1"

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{queued_task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["task"]["status"] == "succeeded"
    assert body["task"]["backend"] == "stub"
    assert body["task"]["result"] == {"outputs": ["https://cdn.example.com/final-image.png"]}
    evidence_kinds = [item["kind"] for item in body["evidence"]]
    assert evidence_kinds[0] == "request.input"
    assert "media.poll_result" in evidence_kinds
    assert "delivery.generated" in evidence_kinds
    assert body["delivery"] == {
        "status": "ready",
        "channel": "media_outputs",
        "kind": "creative.media",
        "summary": "已生成 1 个image 产物，可直接用于交付。",
        "outputs": [
            {
                "label": "image-1",
                "uri": "https://cdn.example.com/final-image.png",
                "media_kind": "image",
            }
        ],
        "provider": "stub",
        "artifacts": [
            {
                "artifact_id": queued_task_id,
                "task_id": queued_task_id,
                "kind": "creative.media.image",
                "name": "image-output-1",
                "uri": "https://cdn.example.com/final-image.png",
                "content_type": "image/png",
                "preview_summary": {"prompt": "异步媒体产物", "mode": "text_to_image"},
            }
        ],
        "validation": {"risks": []},
        "replay": {
            "mode": "task_detail",
            "label": "查看后台任务",
            "run_id": queued_task_id,
            "task_id": queued_task_id,
            "api_path": f"/api/v1/tasks/{queued_task_id}",
            "console_path": f"/runs/{queued_task_id}",
        },
        "resume": None,
        "failure": None,
        "risks": [],
    }
    assert body["artifacts"] == [
        {
            "artifact_id": queued_task_id,
            "run_id": queued_task_id,
            "task_id": queued_task_id,
            "tenant_id": "tenant-1",
            "kind": "creative.media.image",
            "name": "image-output-1",
            "uri": "https://cdn.example.com/final-image.png",
            "content_type": "image/png",
            "size_bytes": 0,
            "checksum": "",
            "validation_summary": {},
            "delivery_summary": {
                "label": "image-1",
                "media_kind": "image",
                "provider": "stub",
            },
            "lineage_summary": {},
            "preview_summary": {"prompt": "异步媒体产物", "mode": "text_to_image"},
        }
    ]


async def test_creative_media_runtime_persists_to_db_after_memory_clear(
    db_client: AsyncClient,
) -> None:
    import xagent.api.v1.creative_studio as creative_api

    token = create_access_token(user_id="u-db-media", tenant_id="tenant-1", roles=["member"])
    generate_resp = await db_client.post(
        "/api/v1/creative-studio/media/generate",
        json={
            "kind": "image",
            "prompt": "持久化媒体主视觉",
            "mode": "text_to_image",
            "wait": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert generate_resp.status_code == 200, generate_resp.text
    task_id = generate_resp.json()["task_id"]

    creative_api._media_runtime_tasks.clear()
    creative_api._media_task_tenants[task_id] = "tenant-1"

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["task"]["task_id"] == task_id
    assert body["task"]["source"] == "task"
    assert body["task"]["intent_type"] == "creative"
    assert body["task"]["route_source"] == "fallback"
    assert body["evidence"]
    assert body["delivery"]["kind"] == "creative.media"
    assert body["delivery"]["artifacts"]
    assert len(body["artifacts"]) == 1

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        task_row = await session.get(AgentTaskORM, task_id)
        artifact_row = await session.get(ArtifactORM, task_id)

    assert task_row is not None
    assert task_row.kind == "creative.media.image"
    assert task_row.source == "task"
    assert task_row.intent_type == "creative"
    assert task_row.route_source == "fallback"
    assert artifact_row is not None
    assert artifact_row.run_id == task_id
    assert artifact_row.task_id == task_id


async def test_creative_media_artifact_schema_mismatch_still_keeps_task_and_delivery(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.api.v1.creative_studio as creative_api

    original_table_exists = creative_api._table_exists

    async def _fake_table_exists(session, table_name: str):  # noqa: ARG001
        if table_name == "artifacts":
            return False
        return await original_table_exists(session, table_name)

    monkeypatch.setattr(creative_api, "_table_exists", _fake_table_exists)
    token = create_access_token(user_id="u-art-missing", tenant_id="tenant-1", roles=["member"])

    generate_resp = await db_client.post(
        "/api/v1/creative-studio/media/generate",
        json={
            "kind": "image",
            "prompt": "仅保留 task 与 delivery",
            "mode": "text_to_image",
            "wait": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert generate_resp.status_code == 200, generate_resp.text
    task_id = generate_resp.json()["task_id"]

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        task_row = await session.get(AgentTaskORM, task_id)
        artifact_row = await session.get(ArtifactORM, task_id)

    assert task_row is not None
    assert artifact_row is None
    assert creative_api._media_runtime_tasks[task_id]["artifacts"]

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["task"]["task_id"] == task_id
    assert body["delivery"]["kind"] == "creative.media"
    assert body["artifacts"] == []


async def test_creative_produce_non_schema_programming_error_is_not_silently_swallowed(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.api.v1.creative_studio as creative_api
    from sqlalchemy.exc import ProgrammingError

    async def _boom(*args, **kwargs):
        raise ProgrammingError(
            "INSERT INTO agent_tasks VALUES (...)", {}, Exception("constraint failed")
        )

    monkeypatch.setattr(creative_api, "_persist_creative_runtime_state", _boom)
    token = create_access_token(user_id="u-produce-boom", tenant_id="tenant-1", roles=["member"])

    with pytest.raises(ProgrammingError):
        await db_client.post(
            "/api/v1/creative-studio/produce",
            json={"brief": "produce 持久化异常", "with_video": False},
            headers={"Authorization": f"Bearer {token}"},
        )


async def test_creative_production_runtime_persists_to_db_after_memory_clear(
    db_client: AsyncClient,
) -> None:
    import xagent.api.v1.creative_studio as creative_api

    token = create_access_token(user_id="u-db-produce", tenant_id="tenant-1", roles=["member"])
    produce_resp = await db_client.post(
        "/api/v1/creative-studio/produce",
        json={"brief": "DB 持久化短剧", "with_video": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert produce_resp.status_code == 200, produce_resp.text
    storyboard_id = produce_resp.json()["storyboard_id"]

    creative_api._production_runtime_runs.clear()

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{storyboard_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["task"]["task_id"] == storyboard_id
    assert body["task"]["kind"] == "creative.produce"
    assert body["task"]["source"] == "task"
    assert body["task"]["intent_type"] == "creative"
    assert body["task"]["route_source"] == "fallback"
    assert [item["kind"] for item in body["evidence"]] == [
        "request.input",
        "production.result",
        "delivery.generated",
    ]
    assert body["delivery"]["kind"] == "creative.production"
    assert body["delivery"]["artifacts"]
    assert body["delivery"]["validation"] == body["validation"]
    assert body["artifacts"]

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        task_row = await session.get(AgentTaskORM, storyboard_id)
        artifact_rows = (
            await session.execute(
                ArtifactORM.__table__.select().where(ArtifactORM.run_id == storyboard_id)
            )
        ).all()

    assert task_row is not None
    assert task_row.kind == "creative.produce"
    assert task_row.source == "task"
    assert task_row.intent_type == "creative"
    assert task_row.route_source == "fallback"
    assert artifact_rows


async def test_creative_media_task_exposes_delivery_summary_via_runs(
    db_client: AsyncClient,
) -> None:
    token = create_access_token(user_id="u-media", tenant_id="tenant-1", roles=["member"])
    generate_resp = await db_client.post(
        "/api/v1/creative-studio/media/generate",
        json={
            "kind": "image",
            "prompt": "霓虹都市主视觉",
            "mode": "text_to_image",
            "wait": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert generate_resp.status_code == 200, generate_resp.text
    task_id = generate_resp.json()["task_id"]

    poll_resp = await db_client.get(
        f"/api/v1/creative-studio/media/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert poll_resp.status_code == 200, poll_resp.text

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["task"]["kind"] == "creative.media.image"
    evidence_kinds = [item["kind"] for item in body["evidence"]]
    assert evidence_kinds[0] == "request.input"
    assert "media.poll_result" in evidence_kinds
    assert "delivery.generated" in evidence_kinds
    assert body["delivery"] == {
        "status": "ready",
        "channel": "media_outputs",
        "kind": "creative.media",
        "summary": "已生成 1 个image 产物，可直接用于交付。",
        "outputs": [
            {
                "label": "image-1",
                "uri": body["task"]["result"]["outputs"][0],
                "media_kind": "image",
            }
        ],
        "provider": "null",
        "artifacts": [
            {
                "artifact_id": task_id,
                "task_id": task_id,
                "kind": "creative.media.image",
                "name": "image-output-1",
                "uri": body["task"]["result"]["outputs"][0],
                "content_type": "application/octet-stream",
                "preview_summary": {"prompt": "霓虹都市主视觉", "mode": "text_to_image"},
            }
        ],
        "validation": {"risks": []},
        "replay": {
            "mode": "task_detail",
            "label": "查看后台任务",
            "run_id": task_id,
            "task_id": task_id,
            "api_path": f"/api/v1/tasks/{task_id}",
            "console_path": f"/runs/{task_id}",
        },
        "resume": None,
        "failure": None,
        "risks": [],
    }
    assert body["artifacts"] == [
        {
            "artifact_id": task_id,
            "run_id": task_id,
            "task_id": task_id,
            "tenant_id": "tenant-1",
            "kind": "creative.media.image",
            "name": "image-output-1",
            "uri": body["task"]["result"]["outputs"][0],
            "content_type": "application/octet-stream",
            "size_bytes": 0,
            "checksum": "",
            "validation_summary": {},
            "delivery_summary": {
                "label": "image-1",
                "media_kind": "image",
                "provider": "null",
            },
            "lineage_summary": {},
            "preview_summary": {"prompt": "霓虹都市主视觉", "mode": "text_to_image"},
        }
    ]


async def test_canvas_run_persists_workflow_for_run_console(
    db_client: AsyncClient,
) -> None:
    token = create_access_token(user_id="u-canvas-run", tenant_id="tenant-1", roles=["member"])
    headers = {"Authorization": f"Bearer {token}"}
    canvas_resp = await db_client.post(
        "/api/v1/canvas",
        json={"title": "E2E canvas", "brief": "霸总逆袭短剧"},
        headers=headers,
    )
    assert canvas_resp.status_code == 200, canvas_resp.text
    canvas_id = canvas_resp.json()["canvas_id"]

    run_resp = await db_client.post(f"/api/v1/canvas/{canvas_id}/run", headers=headers)
    assert run_resp.status_code == 200, run_resp.text
    workflow_run_id = run_resp.json()["workflow_run_id"]

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{workflow_run_id}",
        headers=headers,
    )
    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["run_id"] == workflow_run_id
    assert body["workflow"]["run_id"] == workflow_run_id
    assert body["workflow"]["steps"]
    assert body["delivery"]["kind"] == "workflow.summary"
    assert body["delivery"]["replay"]["console_path"] == f"/runs/{workflow_run_id}"


async def test_creative_production_exposes_delivery_summary_via_runs(
    db_client: AsyncClient,
) -> None:
    token = create_access_token(user_id="u-produce", tenant_id="tenant-1", roles=["member"])
    produce_resp = await db_client.post(
        "/api/v1/creative-studio/produce",
        json={"brief": "都市逆袭短剧", "with_video": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert produce_resp.status_code == 200, produce_resp.text
    storyboard_id = produce_resp.json()["storyboard_id"]

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{storyboard_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    output_count = sum(
        len(shot["image_outputs"]) + len(shot["video_outputs"])
        for shot in body["task"]["result"]["shots"]
    )
    assert body["task"]["kind"] == "creative.produce"
    evidence_kinds = [item["kind"] for item in body["evidence"]]
    assert evidence_kinds == ["request.input", "production.result", "delivery.generated"]
    assert body["delivery"] == {
        "status": "ready",
        "channel": "creative_production",
        "kind": "creative.production",
        "summary": (
            f"短剧已生成，{body['task']['result']['shots_count']} 个镜头，"
            f"共 {output_count} 个媒体产物。"
        ),
        "storyboard_id": storyboard_id,
        "title": body["task"]["result"]["title"],
        "timeline_id": body["task"]["result"]["timeline_id"],
        "quality_passed": body["validation"]["all_passed"],
        "output_count": output_count,
        "failure": None,
        "artifacts": body["delivery"]["artifacts"],
        "validation": body["validation"],
        "replay": {
            "mode": "task_detail",
            "label": "查看后台任务",
            "run_id": storyboard_id,
            "task_id": storyboard_id,
            "api_path": f"/api/v1/tasks/{storyboard_id}",
            "console_path": f"/runs/{storyboard_id}",
        },
        "resume": None,
        "risks": body["validation"]["risks"],
    }
    assert len(body["artifacts"]) == output_count


async def test_creative_partial_production_maps_delivery_to_blocked(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.api.v1.creative_studio as creative_api

    class _PartialResult:
        storyboard_id = "partial-storyboard"
        status = "partial"
        shots = [object()]

        def to_dict(self) -> dict:
            return {
                "storyboard_id": self.storyboard_id,
                "title": "部分完成短剧",
                "brief": "部分完成",
                "genre": "逆袭",
                "platform": "抖音",
                "status": self.status,
                "quality_passed": False,
                "quality_gates": [{"name": "shot_count", "passed": False, "detail": "镜头不足"}],
                "timeline_id": None,
                "shots": [
                    {
                        "shot_id": "shot-1",
                        "scene": "办公室",
                        "plot_purpose": "引入",
                        "image_outputs": ["placeholder://image/text_to_image/1"],
                        "video_outputs": [],
                        "image_error": None,
                        "video_error": "生成失败",
                    }
                ],
            }

    async def _fake_produce_short_drama(*args, **kwargs):
        return _PartialResult()

    monkeypatch.setattr(creative_api, "produce_short_drama", _fake_produce_short_drama)
    token = create_access_token(user_id="u-partial", tenant_id="tenant-1", roles=["member"])

    produce_resp = await db_client.post(
        "/api/v1/creative-studio/produce",
        json={"brief": "部分完成短剧", "with_video": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert produce_resp.status_code == 200, produce_resp.text

    runtime_resp = await db_client.get(
        "/api/v1/runs/partial-storyboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["task"]["status"] == "failed"
    assert body["delivery"] == {
        "status": "blocked",
        "channel": "creative_production",
        "kind": "creative.production",
        "summary": "短剧产出部分完成，1 个镜头，共 1 个媒体产物。",
        "storyboard_id": "partial-storyboard",
        "title": "部分完成短剧",
        "timeline_id": None,
        "quality_passed": False,
        "output_count": 1,
        "failure": {
            "code": "partial",
            "source": "creative",
            "message": "镜头 shot-1 生成失败，当前短剧产出部分阻塞。",
            "blocking_step": "shot-1",
            "step_name": "办公室",
            "retryable": True,
            "recommended_action": "检查失败镜头与质量门后重新生成短剧产物",
            "details": {
                "workflow_status": "partial",
                "quality_gate_failures": [{"name": "shot_count", "detail": "镜头不足"}],
                "shot_error": "生成失败",
                "validation_risks": ["镜头不足"],
            },
            "reason": "生成失败",
        },
        "artifacts": body["delivery"]["artifacts"],
        "validation": body["validation"],
        "replay": {
            "mode": "task_detail",
            "label": "查看后台任务",
            "run_id": "partial-storyboard",
            "task_id": "partial-storyboard",
            "api_path": "/api/v1/tasks/partial-storyboard",
            "console_path": "/runs/partial-storyboard",
        },
        "resume": None,
        "risks": ["镜头不足"],
    }
    assert len(body["artifacts"]) == 1


async def test_creative_tenant_isolation(client: AsyncClient) -> None:
    token_a = create_access_token(user_id="a", tenant_id="tA", roles=["member"])
    token_b = create_access_token(user_id="b", tenant_id="tB", roles=["member"])
    resp = await client.post(
        "/api/v1/creative-studio/workflow-draft",
        json={"brief": "x"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    draft_id = resp.json()["draft_id"]
    # 租户 B 审核租户 A 的草稿 -> 404
    r = await client.post(
        f"/api/v1/creative-studio/workflow-draft/{draft_id}/review",
        json={"approved": True},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
