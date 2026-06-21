"""Langfuse trace 验证脚本：配置后端到端验证 trace 上报。

前置：
  1. Langfuse 运行（compose 已含，:3001）
  2. 在 Langfuse 创建项目，拿到 public_key / secret_key
  3. 设置环境变量：
     XAGENT_OBSERVABILITY__LANGFUSE_HOST=http://localhost:3001
     XAGENT_OBSERVABILITY__LANGFUSE_PUBLIC_KEY=pk-...
     XAGENT_OBSERVABILITY__LANGFUSE_SECRET_KEY=sk-...

用法：python scripts/verify_langfuse.py
"""

from __future__ import annotations

import asyncio
import os
import sys


async def main() -> int:
    # 检查配置
    host = os.environ.get("XAGENT_OBSERVABILITY__LANGFUSE_HOST", "")
    pk = os.environ.get("XAGENT_OBSERVABILITY__LANGFUSE_PUBLIC_KEY", "")
    sk = os.environ.get("XAGENT_OBSERVABILITY__LANGFUSE_SECRET_KEY", "")

    if not (host and pk and sk):
        print("⚠️  Langfuse 未配置（环境变量缺失），跳过验证")
        print("   设置 XAGENT_OBSERVABILITY__LANGFUSE_HOST/PUBLIC_KEY/SECRET_KEY 后重试")
        return 0

    print(f"[langfuse] host={host}")

    # 重置 tracer 单例以加载新配置
    from xagent.adapters.observability import get_tracer, reset_tracer
    from xagent.infra.settings import get_settings

    get_settings.cache_clear()
    reset_tracer()
    tracer = get_tracer()
    print(f"[langfuse] tracer={type(tracer).__name__}")

    if type(tracer).__name__ == "NoopTracer":
        print("❌ tracer 仍为 Noop（配置未生效）")
        return 1

    # health 检查
    healthy = await tracer.health()
    print(f"[langfuse] health={healthy}")
    if not healthy:
        print("❌ Langfuse 连接失败（检查 key/host）")
        return 1

    # 发一个 trace + span
    async with tracer.trace("verify.langfuse") as span:
        span.set_input("验证输入")
        span.set_output("验证输出")
        span.set_metadata(test="langfuse_verify")

    await tracer.flush()
    print("✅ trace 已上报，请在 Langfuse UI 查看项目 trace 列表")
    print(f"   {host} -> 项目 traces -> 搜索 'verify.langfuse'")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
