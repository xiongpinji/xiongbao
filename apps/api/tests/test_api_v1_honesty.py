"""端点诚实化回归测试（工作流 C）。

覆盖审计发现的假成功/静默降级/校验缺失问题：
- bulk 批量操作必须作用于真实存储 + 资源白名单
- llm-config PUT 后 GET 一致 + 持久化
- open-source discover 降级标识
- knowledge ingest -> list/search 一致性（不串会话记忆）
- mcp stdio 命令校验 + 连接结果诚实化
- editor transitions clip_id 校验
- skills 不存在资源返回 404
- data/export/audit 与 /audit/export 同源
"""

from __future__ import annotations

import sys

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.enterprise.auth import create_access_token
from xagent.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _h(roles=("member",)) -> dict:
    token = create_access_token(user_id="u", tenant_id="t1", roles=list(roles))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _no_mcp_config_persist(monkeypatch):
    """MCP manager add_server 会写 apps/data/mcp_servers.json，测试中禁用持久化。"""
    monkeypatch.setattr(
        "xagent.adapters.mcp.client.MCPManager._save_config", lambda self: None
    )


# ─── bulk ───


async def test_bulk_unknown_resource_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/bulk/foobar", json={"items": [{"data": {"x": 1}}]}, headers=_h()
    )
    assert resp.status_code == 404


async def test_bulk_skills_real_create_update_delete(client: AsyncClient) -> None:
    # 创建：必须写入真实技能库
    resp = await client.post(
        "/api/v1/bulk/skills",
        json={"items": [
            {"data": {"name": "bulk-s1", "trigger_pattern": "bulkkw1"}},
            {"data": {"name": "bulk-s2", "trigger_pattern": "bulkkw2"}},
            {"data": {"description": "缺 name 与 trigger"}},  # 必失败
        ]},
        headers=_h(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["succeeded"] == 2
    assert body["failed"] == 1
    created_id = body["results"][0]["id"]

    # 技能库真实可见
    resp = await client.get("/api/v1/skills", headers=_h())
    names = {s["name"] for s in resp.json()["skills"]}
    assert "bulk-s1" in names and "bulk-s2" in names

    # 更新真实 id：成功
    resp = await client.patch(
        "/api/v1/bulk/skills",
        json={"items": [{"id": created_id, "data": {"description": "updated"}}]},
        headers=_h(),
    )
    assert resp.json()["succeeded"] == 1

    # 更新不存在的 id：明确失败而非假成功
    resp = await client.patch(
        "/api/v1/bulk/skills",
        json={"items": [{"id": "no-such-id", "data": {"description": "x"}}]},
        headers=_h(),
    )
    assert resp.json()["failed"] == 1
    assert "不存在" in resp.json()["results"][0]["error"]

    # 删除真实 id：成功；再删：失败
    resp = await client.request(
        "DELETE", "/api/v1/bulk/skills",
        json={"items": [{"id": created_id}]}, headers=_h(),
    )
    assert resp.json()["succeeded"] == 1
    resp = await client.request(
        "DELETE", "/api/v1/bulk/skills",
        json={"items": [{"id": created_id}]}, headers=_h(),
    )
    assert resp.json()["failed"] == 1

    # 清理：SkillStore 全局持久化，避免污染其他测试/工作流
    from xagent.core.skills import get_skill_store

    store = get_skill_store()
    for s in store.list_all(include_retired=True):
        if s.name in {"bulk-s1", "bulk-s2"}:
            store.delete(s.skill_id)


# ─── llm-config ───


async def test_llm_config_put_get_consistent_and_persisted(
    client: AsyncClient, monkeypatch, tmp_path
) -> None:
    # 覆盖文件指向临时路径，避免污染真实 data/
    import xagent.api.v1.system as system_module

    monkeypatch.setattr(
        system_module, "_LLM_OVERRIDES_PATH", tmp_path / "llm_config_overrides.json"
    )
    resp = await client.put(
        "/api/v1/system/llm-config",
        json={"default_model": "honesty-test-model"},
        headers=_h(),
    )
    assert resp.status_code == 200
    assert resp.json()["persisted"] is True

    # 写后读一致
    resp = await client.get("/api/v1/system/llm-config", headers=_h())
    assert resp.json()["default_model"] == "honesty-test-model"

    # 模拟重启：清掉 settings 单例后 GET 仍读到持久化值
    from xagent.infra.settings import get_settings

    get_settings.cache_clear()
    resp = await client.get("/api/v1/system/llm-config", headers=_h())
    assert resp.json()["default_model"] == "honesty-test-model"


# ─── open-source discover degraded ───


async def test_discover_mock_fallback_marked_degraded(client: AsyncClient, monkeypatch) -> None:
    # 只挂 MockProvider 的引擎：模拟"真实源全部失败"场景
    from xagent.domains.open_source_discovery.engine import DiscoveryEngine, MockProvider

    monkeypatch.setattr(
        "xagent.domains.open_source_discovery.engine.get_discovery_engine",
        lambda: DiscoveryEngine(providers=[MockProvider()]),
    )
    resp = await client.post(
        "/api/v1/open-source/discover",
        json={"query": "vector db", "limit": 3},
        headers=_h(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"]  # mock 兜底仍有结果
    assert body["degraded"] is True
    assert body["degraded_reason"]
    assert body["providers"]["ok"] == ["mock"]


async def test_discover_real_provider_not_degraded(client: AsyncClient, monkeypatch) -> None:
    from xagent.domains.open_source_discovery.engine import DiscoveryEngine
    from xagent.domains.open_source_discovery.models import Candidate

    class _FakeRealProvider:
        name = "pypi"

        async def search(self, query: str, *, limit: int = 10):
            return [
                Candidate(
                    name="real-lib", source="pypi", url="https://pypi.org/project/real-lib/",
                    description="real", stars=100, license="mit", last_updated="2026-07-01",
                )
            ]

    monkeypatch.setattr(
        "xagent.domains.open_source_discovery.engine.get_discovery_engine",
        lambda: DiscoveryEngine(providers=[_FakeRealProvider()]),
    )
    resp = await client.post(
        "/api/v1/open-source/discover",
        json={"query": "real lib", "limit": 3},
        headers=_h(),
    )
    body = resp.json()
    assert body["degraded"] is False
    assert body["results"][0]["source"] == "pypi"


# ─── knowledge ───


class _FakeVectorStore:
    """进程内存向量库替身：避免测试与并发进程争抢 apps/data/qdrant 磁盘锁。

    用简单关键词重合度模拟语义检索，满足 API 一致性断言。
    """

    def __init__(self) -> None:
        from xagent.adapters.memory.base import SearchHit

        self._records = []
        self._hit_cls = SearchHit

    async def ensure_collection(self) -> None:
        return None

    async def upsert(self, records) -> None:
        self._records.extend(records)

    async def search(self, query: str, *, top_k: int = 5, tenant_id: str | None = None):
        hits = []
        for r in self._records:
            if tenant_id and r.metadata.get("tenant_id") != tenant_id:
                continue
            overlap = len(set(query) & set(r.text))
            hits.append(self._hit_cls(
                id=r.id, text=r.text, score=float(overlap), metadata=r.metadata
            ))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    async def health(self) -> bool:
        return True


async def test_knowledge_ingest_list_search_consistent(client: AsyncClient, monkeypatch) -> None:
    store = _FakeVectorStore()
    monkeypatch.setattr("xagent.adapters.memory.get_vector_store", lambda: store)
    h = _h(("admin",))
    resp = await client.post(
        "/api/v1/knowledge/ingest",
        json={"text": "熊宝短剧工厂支持一句话生成完整生产工作流。", "title": "honesty-doc"},
        headers=h,
    )
    assert resp.status_code == 200
    doc_id = resp.json()["document"]["doc_id"]

    # 立即可列出
    resp = await client.get("/api/v1/knowledge/documents", headers=h)
    docs = resp.json()["documents"]
    assert any(d["doc_id"] == doc_id for d in docs)

    # 搜索只返回入库文档（doc_id 非空），不串会话记忆
    resp = await client.post(
        "/api/v1/knowledge/search", json={"query": "短剧工厂"}, headers=h
    )
    results = resp.json()["results"]
    assert results
    assert all(r["doc_id"] for r in results)
    assert any(r["doc_id"] == doc_id for r in results)

    # 清理 SQLite 持久层（ingest 会写 knowledge_docs/knowledge_chunks）
    from xagent.core.persistence import delete_document as _persist_delete

    await _persist_delete(doc_id)


# ─── 依赖不可用 → 诚实 503 ───


class _DownVectorStore:
    """向量库替身：所有操作抛 RuntimeError（模拟 qdrant 本地锁冲突）。"""

    async def ensure_collection(self) -> None:
        raise RuntimeError("mock: qdrant local lock conflict")

    async def upsert(self, records) -> None:
        raise RuntimeError("mock: qdrant local lock conflict")

    async def search(self, query: str, *, top_k: int = 5, tenant_id: str | None = None):
        raise RuntimeError("mock: qdrant local lock conflict")

    async def health(self) -> bool:
        return False


async def test_knowledge_ingest_vector_store_down_returns_503(
    client: AsyncClient, monkeypatch
) -> None:
    """qdrant 锁冲突（RuntimeError）时 ingest 应 503 + 明确 detail，而非 500 + traceback。"""
    monkeypatch.setattr(
        "xagent.adapters.memory.get_vector_store", lambda: _DownVectorStore()
    )
    resp = await client.post(
        "/api/v1/knowledge/ingest",
        json={"text": "依赖不可用测试文档", "title": "down-doc"},
        headers=_h(("admin",)),
    )
    assert resp.status_code == 503
    assert "依赖服务不可用" in resp.json()["detail"]


async def test_knowledge_search_vector_store_down_returns_503(
    client: AsyncClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        "xagent.adapters.memory.get_vector_store", lambda: _DownVectorStore()
    )
    resp = await client.post(
        "/api/v1/knowledge/search", json={"query": "任意"}, headers=_h(("admin",))
    )
    assert resp.status_code == 503
    assert "依赖服务不可用" in resp.json()["detail"]


async def test_memory_write_vector_store_down_returns_503(
    client: AsyncClient, monkeypatch
) -> None:
    """构造期就抛 RuntimeError（锁冲突发生在 client 初始化）也应 503。"""

    def _raise():
        raise RuntimeError("mock: qdrant local lock conflict")

    monkeypatch.setattr("xagent.api.v1.memory.get_vector_store", _raise)
    resp = await client.post(
        "/api/v1/memory",
        json={"items": [{"id": "m1", "text": "hello"}]},
        headers=_h(),
    )
    assert resp.status_code == 503
    assert "依赖服务不可用" in resp.json()["detail"]


async def test_memory_search_vector_store_down_returns_503(
    client: AsyncClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        "xagent.api.v1.memory.get_vector_store", lambda: _DownVectorStore()
    )
    resp = await client.post(
        "/api/v1/memory/search", json={"query": "任意"}, headers=_h()
    )
    assert resp.status_code == 503
    assert "依赖服务不可用" in resp.json()["detail"]


# ─── mcp ───


async def test_mcp_add_server_bad_command_400(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/mcp/servers",
        json={"name": "bad-cmd", "transport": "stdio",
              "command": "nonexistent-cmd-xyz-123"},
        headers=_h(),
    )
    assert resp.status_code == 400


async def test_mcp_add_server_valid_config(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/mcp/servers",
        json={"name": "honesty-srv", "transport": "stdio",
              "command": sys.executable, "enabled": False},
        headers=_h(),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "added"


async def test_mcp_connect_non_mcp_process_reports_failure(client: AsyncClient) -> None:
    # 注册一个真实存在但不是 MCP server 的命令：连接必须诚实报错，
    # 不得 ok=true + tools_discovered=0 假成功
    await client.post(
        "/api/v1/mcp/servers",
        json={"name": "not-mcp", "transport": "stdio",
              "command": sys.executable, "args": ["-c", "pass"], "enabled": False},
        headers=_h(),
    )
    resp = await client.post("/api/v1/mcp/servers/not-mcp/connect", headers=_h())
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]


async def test_mcp_connect_unknown_server_404(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/mcp/servers/ghost/connect", headers=_h())
    assert resp.status_code == 404


# ─── editor transitions ───


async def test_editor_transition_requires_existing_clip(client: AsyncClient) -> None:
    h = _h()
    resp = await client.post(
        "/api/v1/creative-studio/editor/timelines", json={"name": "t"}, headers=h
    )
    tl_id = resp.json()["id"]

    # 空 clip_id -> 400
    resp = await client.post(
        f"/api/v1/creative-studio/editor/timelines/{tl_id}/transitions",
        json={"clip_id": "", "type": "dissolve"}, headers=h,
    )
    assert resp.status_code == 400

    # 不存在的 clip_id -> 404
    resp = await client.post(
        f"/api/v1/creative-studio/editor/timelines/{tl_id}/transitions",
        json={"clip_id": "ghost-clip", "type": "dissolve"}, headers=h,
    )
    assert resp.status_code == 404

    # 真实 clip -> 200
    resp = await client.post(
        f"/api/v1/creative-studio/editor/timelines/{tl_id}/clips",
        json={"track_type": "video", "timeline_start": 0, "timeline_end": 2}, headers=h,
    )
    clip_id = resp.json()["clips"][0]["id"]
    resp = await client.post(
        f"/api/v1/creative-studio/editor/timelines/{tl_id}/transitions",
        json={"clip_id": clip_id, "type": "dissolve"}, headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["transitions"]


# ─── skills 404 ───

# 注意：DELETE /api/v1/skills/{id} 与 POST /api/v1/skills 被
# automation.py 中的重复路由（注册顺序在前）shadow，无法在此验证 404 行为，
# 已在报告中标注遗留问题。GET /skills/{id} 无重复路由，可正常验证。


async def test_skill_get_missing_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/skills/no-such-skill", headers=_h())
    assert resp.status_code == 404


# ─── data/export/audit 与 /audit/export 同源 ───


async def test_data_export_audit_matches_audit_chain(client: AsyncClient) -> None:
    from xagent.enterprise.audit import get_audit_log

    for i in range(3):
        get_audit_log().record(
            tenant_id="t1", actor="u", action=f"honesty.test{i}", resource="test"
        )
    resp = await client.get("/api/v1/data/export/audit", headers=_h())
    assert resp.status_code == 200
    data_count = resp.json()["count"]
    assert data_count >= 3

    resp = await client.get("/api/v1/audit", headers=_h())
    chain_count = len(resp.json()["events"])
    assert data_count == chain_count
