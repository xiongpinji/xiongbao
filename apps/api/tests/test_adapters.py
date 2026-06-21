"""适配层降级与三链路测试（离线，不依赖外部服务/key）。"""

from __future__ import annotations

from xagent.adapters.llm import Message, get_llm_client
from xagent.adapters.llm.mock import MockLLMClient
from xagent.adapters.memory import MemoryRecord, get_vector_store
from xagent.adapters.memory.embedder import HashEmbedder
from xagent.adapters.memory.factory import get_embedder
from xagent.adapters.observability import NoopTracer, get_tracer


def test_llm_degrades_to_mock() -> None:
    assert isinstance(get_llm_client(), MockLLMClient)


def test_tracer_degrades_to_noop() -> None:
    assert isinstance(get_tracer(), NoopTracer)


def test_embedder_degrades_to_hash() -> None:
    assert isinstance(get_embedder(), HashEmbedder)


async def test_mock_llm_complete() -> None:
    resp = await get_llm_client().complete([Message(role="user", content="hi")])
    assert resp.content
    assert resp.model


async def test_hash_embedder_deterministic() -> None:
    emb = HashEmbedder(dim=64)
    a = await emb.embed(["hello world"])
    b = await emb.embed(["hello world"])
    assert a == b
    assert len(a[0]) == 64


async def test_vector_store_roundtrip() -> None:
    store = get_vector_store()
    await store.upsert(
        [
            MemoryRecord(id="r1", text="企业自主智能体", metadata={"tenant_id": "t1"}),
            MemoryRecord(id="r2", text="短剧工厂工作流", metadata={"tenant_id": "t1"}),
        ]
    )
    hits = await store.search("智能体", top_k=2, tenant_id="t1")
    assert hits
    assert all(h.metadata.get("tenant_id") == "t1" for h in hits)


async def test_tenant_isolation_in_search() -> None:
    store = get_vector_store()
    await store.upsert(
        [MemoryRecord(id="iso1", text="租户A数据", metadata={"tenant_id": "A"})]
    )
    # 用租户 B 检索，不应看到租户 A 的数据
    hits = await store.search("数据", top_k=5, tenant_id="B")
    assert all(h.id != "iso1" for h in hits)


async def test_three_chains_smoke() -> None:
    from xagent.scripts.smoke_three_chains import run_smoke

    assert await run_smoke() == 0
