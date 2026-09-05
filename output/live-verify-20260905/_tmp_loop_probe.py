"""编排空响应探针：包装 LLM 客户端抓 run_agent 实际发送的消息与原始返回。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

DUMP = Path("_tmp_loop_probe_dump.jsonl")


class ProbeClient:
    def __init__(self, inner):
        self._inner = inner
        self.supports_tools = inner.supports_tools

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def complete(self, messages, **kw):
        r = await self._inner.complete(messages, **kw)
        DUMP.open("a", encoding="utf-8").write(json.dumps({
            "kind": "complete", "kw": {k: v for k, v in kw.items()},
            "messages": [{"role": m.role, "len": len(m.content or ""), "head": (m.content or "")[:80]} for m in messages],
            "content": (r.content or "")[:200], "ct": r.completion_tokens,
            "raw_choices": (r.raw.get("choices") or [{}])[0],
        }, ensure_ascii=False) + "\n")
        return r

    async def complete_with_tools(self, messages, tools=None, **kw):
        r = await self._inner.complete_with_tools(messages, tools=tools, **kw)
        DUMP.open("a", encoding="utf-8").write(json.dumps({
            "kind": "cwt", "kw": {k: v for k, v in kw.items()}, "tools": len(tools or []),
            "messages": [{"role": m.role, "len": len(m.content or ""), "head": (m.content or "")[:120]} for m in messages],
            "content": (r.content or "")[:200], "tc": len(r.tool_calls), "ct": r.completion_tokens,
            "finish": ((r.raw.get("choices") or [{}])[0].get("finish_reason")) if r.raw else None,
        }, ensure_ascii=False) + "\n")
        return r


async def main() -> int:
    import xagent.core.orchestration.loop as loop_mod
    from xagent.adapters.llm import get_llm_client
    from xagent.enterprise.auth.principal import Principal

    real = get_llm_client()
    probe = ProbeClient(real)
    loop_mod.get_llm_client = lambda: probe

    principal = Principal(
        user_id="probe", tenant_id="probe-tenant", roles=["member"], scopes=[]
    )
    events = []

    async def on_event(ev):
        events.append(ev.kind.value)

    try:
        result = await loop_mod.run_agent(
            goal="用一句话回答：中国的首都是哪里？",
            principal=principal,
            session=None,
            on_event=on_event,
        )
        ans = getattr(result, "final_answer", "") or ""
        print("final_answer:", ans[:120])
    except Exception as exc:
        print("EXC:", str(exc)[:150])
    print("events:", events[:10])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
