"""v1.2.0 compaction 行为实测：低预算多轮对话后，早期关键信息（暗号）仍可召回。

用法：在 apps/api 下用 venv python 运行（后端需以低预算运行于 :8123）。
判定：最终回答包含暗号 ZEBRA-77 → 摘要折叠保留了早期上下文。
"""

from __future__ import annotations

import asyncio
import json
import sys

import httpx

BASE = "http://127.0.0.1:8123/api/v1"
CODE = "ZEBRA-77"
FILLER = "这是一段用于撑大多轮对话 token 体积的填充文本，讨论供应链协同平台的库存优化策略。" * 60  # ~5400 字


async def login(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{BASE}/auth/login", json={"username": "admin", "password": "admin"})
    return r.json()["access_token"]


async def chat(client: httpx.AsyncClient, token: str, conv: str, goal: str) -> str:
    final_parts: list[str] = []
    async with client.stream(
        "POST",
        f"{BASE}/stream/agents/run",
        json={"goal": goal, "mode": "full-auto", "conversation_id": conv},
        headers={"Authorization": f"Bearer {token}"},
        timeout=300,
    ) as r:
        if r.status_code != 200:
            return f"HTTP {r.status_code}: {(await r.aread())[:200]!r}"
        event = ""
        async for line in r.aiter_lines():
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: ") and event in ("token", "final"):
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if event == "token":
                    final_parts.append(str(data.get("content", "")))
                elif event == "final":
                    final_parts.append(str(data.get("content", "")))
    return "".join(final_parts)


async def main() -> int:
    async with httpx.AsyncClient() as client:
        token = await login(client)
        conv = "cmp-live-test-001"

        t1 = f"记住我们的项目暗号是 {CODE}（蓝鲸计划）。" + FILLER
        print("turn1: 发送含暗号的长消息（~5.4k tokens）...")
        a1 = await chat(client, token, conv, t1)
        print(f"  reply len={len(a1)}")

        t2 = "继续讨论第二个议题：物流路径规划。" + FILLER[:3600]
        print("turn2: 第二轮长消息（累计将超 6000 token 预算，触发压缩）...")
        a2 = await chat(client, token, conv, t2)
        print(f"  reply len={len(a2)}")

        t3 = f"只回答一个问题：我们之前约定的项目暗号是什么？只输出暗号本身，不要其他文字。"
        print("turn3: 召回暗号...")
        a3 = await chat(client, token, conv, t3)
        print(f"  answer: {a3[:200]}")

        ok = CODE in a3
        print(f"\n判定: {'PASS ✅ 压缩后早期关键信息保留' if ok else 'FAIL ❌ 召回失败'}")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
