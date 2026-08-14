#!/usr/bin/env python3
"""E2B L2 云沙箱接入验证脚本。

给定 E2B_API_KEY，通过 X-Agent 自己的 E2BSandbox 适配器实跑一次代码执行，
验证商用交付中「L2 E2B 未实测」这一边界项。

用法（在 apps/api 环境内）：
  cd apps/api
  E2B_API_KEY=xxx python ../../scripts/verify_e2b_sandbox.py
  # 或 python ../../scripts/verify_e2b_sandbox.py --api-key xxx [--template my-tpl]

退出码：0 = E2B 沙箱健康且代码实跑通过；1 = 失败；2 = 缺少 key（明确跳过）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from xagent.adapters.sandbox.e2b_sandbox import E2BSandbox, E2BUnavailableError  # noqa: E402


async def run(api_key: str, template: str | None) -> int:
    sandbox = E2BSandbox(api_key=api_key, template=template, timeout_seconds=60)

    healthy = await sandbox.health()
    print(f"[{'PASS' if healthy else 'FAIL'}] e2b-health —— SDK 连通性检查")
    if not healthy:
        return 1

    result = await sandbox.run_code("python", "print('xagent-e2b-ok')", timeout=60)
    ok = result.ok and "xagent-e2b-ok" in (result.stdout or "")
    print(f"[{'PASS' if ok else 'FAIL'}] e2b-run-code —— "
          f"stdout={(result.stdout or '').strip()!r} stderr={(result.stderr or '').strip()[:120]!r}")
    if not ok:
        return 1

    print("\nE2B VERIFY: PASS —— L2 云沙箱接入实跑通过，可将该证据归档到交付记录")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify X-Agent E2B L2 sandbox integration")
    parser.add_argument("--api-key", default=os.environ.get("E2B_API_KEY", ""))
    parser.add_argument("--template", default=os.environ.get("XAGENT_SANDBOX__E2B_TEMPLATE") or None)
    args = parser.parse_args()

    if not args.api_key:
        print("[SKIP] 未提供 E2B_API_KEY——这是外部输入项，获取 key 后重跑本脚本即完成验证")
        return 2

    try:
        return asyncio.run(run(args.api_key, args.template))
    except E2BUnavailableError as exc:
        print(f"[FAIL] E2B 适配器不可用: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
