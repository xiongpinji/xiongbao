"""三链路冒烟：LLM 调用 → trace 上报 → 向量读写。

设计为**离线可跑**：无任何 key/服务时走 mock LLM + noop tracer + Qdrant 内存 +
hash 嵌入，依然能端到端验证三条链路的接线正确性。配齐 key/服务后即验证真实链路。

退出码 0 表示三链路全通。``xagent smoke`` 调用本模块。
"""

from __future__ import annotations

from xagent.adapters.llm import Message, get_llm_client
from xagent.adapters.memory import MemoryRecord, get_vector_store
from xagent.adapters.observability import get_tracer


async def run_smoke() -> int:
    ok = True

    # ---- 链路 2：tracer 包裹整个流程 ----
    tracer = get_tracer()
    print(f"[trace] tracer = {type(tracer).__name__}")

    async with tracer.trace("smoke.three_chains") as span:
        # ---- 链路 1：LLM ----
        llm = get_llm_client()
        span.set_metadata(llm=type(llm).__name__)
        resp = await llm.complete(
            [Message(role="user", content="用一句话介绍 X-Agent")],
        )
        print(f"[llm]   client={type(llm).__name__} model={resp.model}")
        print(f"[llm]   reply ={resp.content[:120]}")
        span.set_output(resp.content)
        if not resp.content:
            print("[llm]   FAIL: 空响应")
            ok = False

        # ---- 链路 3：向量读写 ----
        store = get_vector_store()
        print(f"[vec]   store ={type(store).__name__}")
        await store.upsert(
            [
                MemoryRecord(
                    id="smoke-1",
                    text="X-Agent 是面向企业的自主智能体框架",
                    metadata={"tenant_id": "t-smoke", "kind": "doc"},
                ),
                MemoryRecord(
                    id="smoke-2",
                    text="短剧工厂支持一句话生成生产工作流",
                    metadata={"tenant_id": "t-smoke", "kind": "doc"},
                ),
            ]
        )
        hits = await store.search("企业智能体框架", top_k=2, tenant_id="t-smoke")
        print(f"[vec]   hits  ={[(h.id, round(h.score, 3)) for h in hits]}")
        if not hits:
            print("[vec]   FAIL: 检索无结果")
            ok = False

    await tracer.flush()

    print("\n[smoke] " + ("PASS ✅ 三链路全通" if ok else "FAIL ❌"))
    return 0 if ok else 1
