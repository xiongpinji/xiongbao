"""短剧工厂持久化测试：草稿/产物/画布/媒体任务落库 roundtrip + 重启恢复语义。

用临时 SQLite 文件库；建表走 persistence.ensure_creative_tables 惰性 create，
另有一例验证 alembic 迁移 20260803_creative_studio_persistence 建表可用。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect
from xagent.domains.creative_studio import persistence as cp
from xagent.infra.db import dispose_engine
from xagent.infra.settings import get_settings


@pytest.fixture
async def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """临时 SQLite 库 + 重置建表标记（模拟全新进程）。"""
    db_file = tmp_path / "creative_test.db"
    monkeypatch.setenv("XAGENT_DB__URL", f"sqlite+aiosqlite:///{db_file}")
    get_settings.cache_clear()
    await dispose_engine()
    cp.reset_creative_table_cache()
    yield db_file
    await dispose_engine()
    get_settings.cache_clear()
    cp.reset_creative_table_cache()


async def test_draft_roundtrip_and_tenant_isolation(temp_db) -> None:
    doc = {
        "draft_id": "d1",
        "tenant_id": "t1",
        "owner": "u1",
        "status": "pending_review",
        "title": "测试草稿",
    }
    await cp.save_draft(doc)

    loaded = await cp.load_draft("d1", "t1")
    assert loaded is not None
    assert loaded["title"] == "测试草稿"
    # 租户隔离：其他租户读不到
    assert await cp.load_draft("d1", "tOTHER") is None
    # 按租户列表
    drafts = await cp.load_drafts("t1")
    assert [d["draft_id"] for d in drafts] == ["d1"]
    assert await cp.load_drafts("tOTHER") == []


async def test_draft_upsert_updates_status(temp_db) -> None:
    doc = {"draft_id": "d1", "tenant_id": "t1", "status": "pending_review"}
    await cp.save_draft(doc)
    doc["status"] = "approved"
    await cp.save_draft(doc)

    loaded = await cp.load_draft("d1", "t1")
    assert loaded is not None
    assert loaded["status"] == "approved"
    # upsert 不产生重复行
    assert len(await cp.load_drafts("t1")) == 1


async def test_production_roundtrip(temp_db) -> None:
    doc = {
        "storyboard_id": "sb1",
        "tenant_id": "t1",
        "owner": "u1",
        "status": "completed",
        "shots": [{"shot_id": "s1"}],
    }
    await cp.save_production(doc)

    loaded = await cp.load_production("sb1", "t1")
    assert loaded is not None
    assert loaded["shots"][0]["shot_id"] == "s1"
    assert await cp.load_production("sb1", "tOTHER") is None
    assert len(await cp.load_productions("t1")) == 1


async def test_canvas_roundtrip(temp_db) -> None:
    doc = {"canvas_id": "c1", "title": "画布", "nodes": [], "edges": []}
    await cp.save_canvas(doc, "t1")

    loaded = await cp.load_canvas("c1", "t1")
    assert loaded is not None
    assert loaded["title"] == "画布"
    assert await cp.load_canvas("c1", "tOTHER") is None

    all_canvases = await cp.load_all_canvases()
    assert all_canvases["c1"][1] == "t1"
    assert all_canvases["c1"][0]["canvas_id"] == "c1"


async def test_media_task_tenant_roundtrip(temp_db) -> None:
    await cp.save_media_task_tenant("task1", "t1")
    assert await cp.load_media_task_tenant("task1") == "t1"
    assert await cp.load_media_task_tenant("missing") is None
    assert await cp.load_all_media_task_tenants() == {"task1": "t1"}


def test_canvas_from_dict_roundtrip() -> None:
    """水合链路：to_dict → from_dict 可还原画布（重启恢复依赖此路径）。"""
    from xagent.domains.creative_studio.canvas import (
        NodeType,
        ProductionCanvas,
        ProductionNode,
    )

    canvas = ProductionCanvas(canvas_id="c1", title="画布", brief="b")
    canvas.nodes.append(
        ProductionNode(node_type=NodeType.voiceover, title="配音", content="台词")
    )
    restored = ProductionCanvas.from_dict(canvas.to_dict())
    assert restored.canvas_id == "c1"
    assert restored.nodes[0].node_type is NodeType.voiceover
    assert restored.nodes[0].content == "台词"
    # 非法节点静默跳过
    bad = canvas.to_dict()
    bad["nodes"].append({"node_type": "not_a_type"})
    assert len(ProductionCanvas.from_dict(bad).nodes) == 1


async def test_restart_recovery_semantics(temp_db) -> None:
    """模拟进程重启：dispose engine + 重置建表标记后，load_all_* 仍能恢复全部数据。"""
    await cp.save_draft({"draft_id": "d1", "tenant_id": "t1", "status": "approved"})
    await cp.save_production({"storyboard_id": "sb1", "tenant_id": "t1", "status": "completed"})
    await cp.save_canvas({"canvas_id": "c1", "title": "画布"}, "t1")
    await cp.save_media_task_tenant("task1", "t1")

    # 模拟重启：连接释放 + 建表标记复位（数据落盘于 temp_db 文件）
    await dispose_engine()
    get_settings.cache_clear()
    cp.reset_creative_table_cache()

    drafts = await cp.load_all_drafts()
    productions = await cp.load_all_productions()
    canvases = await cp.load_all_canvases()
    tasks = await cp.load_all_media_task_tenants()

    assert drafts["d1"]["status"] == "approved"
    assert productions["sb1"]["status"] == "completed"
    assert canvases["c1"][0]["title"] == "画布"
    assert tasks == {"task1": "t1"}


def test_alembic_migration_creates_creative_tables(tmp_path) -> None:
    """迁移 20260803_creative_studio_persistence：upgrade head 后四张表存在。"""
    db_file = tmp_path / "alembic_creative.db"
    api_dir = str(Path(__file__).resolve().parent.parent)
    env = {
        **os.environ,
        "XAGENT_DB__URL": f"sqlite+aiosqlite:///{db_file}",
        "PYTHONPATH": api_dir,
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=api_dir,
        env=env,
        check=True,
        capture_output=True,
    )

    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{db_file}")
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert {
        "creative_drafts",
        "creative_productions",
        "creative_canvases",
        "creative_media_tasks",
    } <= tables
