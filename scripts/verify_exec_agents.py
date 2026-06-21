#!/usr/bin/env python
"""执行 agent 接入验证脚本：检查各 agent 是否真实启用或 stub 降级。

用法：python scripts/verify_exec_agents.py
退出码 0 = 全部可访问（真实或 stub 安全降级）。
"""

from __future__ import annotations

import asyncio
import sys


async def main() -> int:
    ok = True

    # 浏览器
    from xagent.adapters.browser import get_browser_agent

    b = get_browser_agent()
    r = await b.run("打开 https://example.com")
    print(f"[browser] backend={b.backend} ok={r.ok} {r.error or r.summary}")
    if b.backend == "stub" and not r.ok:
        print("  -> stub 降级（正常，未装 browser-use）")
    elif not r.ok:
        ok = False

    # 桌面
    from xagent.adapters.desktop_auto import get_desktop_agent

    d = get_desktop_agent()
    r = await d.run("截屏")
    print(f"[desktop] backend={d.backend} ok={r.ok} {r.error or r.summary}")
    if d.backend == "stub" and not r.ok:
        print("  -> stub 降级（正常，未配 UI-TARS URL）")
    elif not r.ok:
        ok = False

    # 编码
    from xagent.adapters.coding import get_coding_agent

    c = get_coding_agent()
    r = await c.issue_to_pr("org/repo", 1)
    print(f"[coding]  backend={c.backend} ok={r.ok} {r.error or r.summary}")
    if c.backend == "stub" and not r.ok:
        print("  -> stub 降级（正常，未配 OpenHands URL）")
    elif not r.ok:
        ok = False

    print("\n" + ("PASS ✅" if ok else "FAIL ❌"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
