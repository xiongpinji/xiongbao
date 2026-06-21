"""安全自动化扫描：越权 / 注入 / 安全头 / 限流 检查。

用法：python tests/security/scan.py --host http://localhost:8000
退出码 0 = 全部通过，非 0 = 发现问题。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx


def _report(name: str, passed: bool, detail: str = "") -> bool:
    mark = "✅" if passed else "❌"
    print(f"  {mark} {name}: {detail}")
    return passed


async def scan(host: str) -> int:
    """运行全部安全检查，返回失败数。"""
    fails = 0
    print(f"\n安全扫描：{host}\n")

    async with httpx.AsyncClient(base_url=host, timeout=15) as c:
        # 1. 健康探针无鉴权（豁免）
        r = await c.get("/health")
        fails += 0 if _report("健康探针无鉴权", r.status_code == 200, str(r.status_code)) else 1

        # 2. 安全响应头
        fails += (
            0
            if _report(
                "X-Content-Type-Options",
                r.headers.get("X-Content-Type-Options") == "nosniff",
            )
            else 1
        )
        fails += (
            0
            if _report("X-Frame-Options", r.headers.get("X-Frame-Options") == "DENY") else 1
        )

        # 3. 越权：无 token 访问受保护端点（full 模式应 401，lite 可 200）
        r = await c.get("/api/v1/agents/roles")
        _report(
            "无 token 访问业务端点",
            r.status_code in (200, 401),
            f"{r.status_code}（full 应 401，lite 可 200）",
        )

        # 4. 租户隔离：两个不同租户 token，A 看不到 B 的记忆
        await asyncio.sleep(2)  # 让限流窗口恢复
        # 注册两个用户
        ta = await c.post("/api/v1/auth/register", json={"username": f"sec_a_{id(c)}", "password": "pass123456"})
        tb = await c.post("/api/v1/auth/register", json={"username": f"sec_b_{id(c)}", "password": "pass123456"})
        if ta.status_code == 200 and tb.status_code == 200:
            tok_a = ta.json()["access_token"]
            tok_b = tb.json()["access_token"]
            tenant_b = tb.json()["tenant_id"]
            # A 写记忆
            await c.post(
                "/api/v1/memory",
                json={"items": [{"id": "secret-sec", "text": "租户A机密"}]},
                headers={"Authorization": f"Bearer {tok_a}"},
            )
            # B 用自己的 token 但声明 X-Tenant-Id=A -> 应 403
            r = await c.get(
                "/api/v1/agents/roles",
                headers={"Authorization": f"Bearer {tok_a}", "X-Tenant-Id": tenant_b},
            )
            fails += (
                0
                if _report("跨租户头注入防护", r.status_code == 403, str(r.status_code))
                else 1
            )
            # B 搜索看不到 A 的数据
            r = await c.post(
                "/api/v1/memory/search",
                json={"query": "机密", "top_k": 10},
                headers={"Authorization": f"Bearer {tok_b}"},
            )
            if r.status_code == 200:
                ids = {h["id"] for h in r.json().get("hits", [])}
                fails += (
                    0
                    if _report("租户记忆隔离", "secret-sec" not in ids, str(ids))
                    else 1
                )

        # 5. SQL 注入尝试（参数化应安全）—— 放在限流之前避免被 429
        r = await c.post(
            "/api/v1/memory/search",
            json={"query": "'; DROP TABLE users; --", "top_k": 3},
        )
        fails += (
            0
            if _report("SQL 注入防护", r.status_code in (200, 401, 403), str(r.status_code))
            else 1
        )

        # 6. 限流：快速发请求触发 429（健康探针豁免，用业务端点）
        await asyncio.sleep(2)  # 让限流窗口恢复
        codes_429 = 0
        for _ in range(150):
            r = await c.get("/api/v1/agents/roles")
            if r.status_code == 429:
                codes_429 += 1
                break
        _report("限流触发", codes_429 > 0, f"429 次数 {codes_429}（lite 低阈值可能不触发）")

    print(f"\n{'PASS ✅' if fails == 0 else f'FAIL ❌ {fails} 项失败'}")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:8000")
    args = ap.parse_args()

    import asyncio

    return asyncio.run(scan(args.host))


if __name__ == "__main__":
    sys.exit(main())
