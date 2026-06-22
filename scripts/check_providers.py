"""provider 真实连通性自检脚本。

从环境变量（或 .env）读取 key，分别对 DeepSeek / 中转站图像 / 火山方舟视频
发一个最小请求，输出 success / error。全程不打印 key。

用法（在 xagent/apps/api 目录运行，确保已创建 xagent/.env 并填入 key）:

    cd xagent/apps/api
    python ../../scripts/check_providers.py            # 检查全部
    python ../../scripts/check_providers.py llm         # 只检查 LLM (DeepSeek)
    python ../../scripts/check_providers.py image       # 只检查图像 (中转站)
    python ../../scripts/check_providers.py video       # 只检查视频 (火山方舟)

注意：真实请求会消耗 token / 余额。脚本默认发最小请求：
- LLM: max_tokens=16
- 图像: 1024x1024, n=1
- 视频: 720p, 5s（仅提交任务，不等待完成，避免长时间阻塞）
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# 确保能 import xagent 包
# 脚本位于 xagent/scripts/check_providers.py，xagent 包在 xagent/apps/api/xagent/
_HERE = Path(__file__).resolve().parent
_API_DIR = _HERE.parent / "apps" / "api"
sys.path.insert(0, str(_API_DIR))


def _mask(key: str | None) -> str:
    """key 脱敏显示：只露前 4 + 后 4 位。"""
    if not key:
        return "(未配置)"
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def _print_header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


async def check_llm() -> bool:
    """DeepSeek 直连：发一个最小 chat completion。"""
    _print_header("LLM (DeepSeek 直连)")
    from xagent.adapters.llm import Message, get_llm_client
    from xagent.infra.settings import get_settings

    cfg = get_settings().llm
    print(f"  default_model : {cfg.default_model}")
    print(f"  deepseek key  : {_mask(cfg.deepseek_api_key)}")
    print(f"  proxy_url     : {cfg.proxy_url or '(无)'}")
    print(f"  ollama_url    : {cfg.ollama_base_url or '(无)'}")

    if not (cfg.deepseek_api_key or cfg.openai_api_key or cfg.proxy_url or cfg.ollama_base_url):
        print("  结果: 跳过（未配置任何 LLM key）")
        return False

    client = get_llm_client()
    t0 = time.time()
    try:
        resp = await client.complete(
            [Message(role="user", content="回复一个字：好")],
            max_tokens=16,
        )
        elapsed = time.time() - t0
        print(f"  模型返回      : {resp.content!r}")
        print(f"  token 用量    : prompt={resp.prompt_tokens} completion={resp.completion_tokens}")
        print(f"  耗时          : {elapsed:.2f}s")
        print(f"  结果: ✅ 成功")
        return True
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"  耗时          : {elapsed:.2f}s")
        print(f"  结果: ❌ 失败 — {type(exc).__name__}: {exc}")
        return False


async def check_image() -> bool:
    """中转站 OpenAI 兼容图像生成：发一个最小文生图。"""
    _print_header("图像 (中转站 OpenAI 兼容 gpt-image-2)")
    from xagent.domains.creative_studio.media import (
        GenerationMode,
        GenerationRequest,
        MediaKind,
        get_media_registry,
    )
    from xagent.infra.settings import get_settings

    cfg = get_settings().media
    print(f"  default_image_provider : {cfg.default_image_provider}")
    print(f"  openai_image key       : {_mask(cfg.openai_image_api_key)}")
    print(f"  openai_image base_url  : {cfg.openai_image_base_url}")
    print(f"  openai_image model     : {cfg.openai_image_model}")

    if cfg.default_image_provider != "openai" or not cfg.openai_image_api_key:
        print("  结果: 跳过（default_image_provider 不是 openai 或 key 未配置）")
        return False

    # 重置 registry 以加载最新配置
    from xagent.domains.creative_studio.media import reset_media_registry
    reset_media_registry()
    registry = get_media_registry()
    provider = registry.get(MediaKind.image)
    if provider.name == "null":
        print("  结果: 跳过（registry 未注册 openai provider，检查 base_url/key）")
        return False

    req = GenerationRequest(
        kind=MediaKind.image,
        prompt="一只可爱的橘猫，写实风格，暖光",
        mode=GenerationMode.text_to_image,
        resolution="1024x1024",
    )
    t0 = time.time()
    try:
        task = await provider.submit(req)
        elapsed = time.time() - t0
        print(f"  provider     : {task.provider}")
        print(f"  status       : {task.status}")
        if task.outputs:
            for i, url in enumerate(task.outputs[:3]):
                print(f"  output[{i}]   : {url[:80]}{'...' if len(url) > 80 else ''}")
        if task.error:
            print(f"  error        : {task.error}")
        print(f"  耗时         : {elapsed:.2f}s")
        print(f"  结果: {'✅ 成功' if task.status == 'succeeded' and task.outputs else '❌ 失败'}")
        return task.status == "succeeded" and bool(task.outputs)
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"  耗时         : {elapsed:.2f}s")
        print(f"  结果: ❌ 异常 — {type(exc).__name__}: {exc}")
        return False


async def check_video() -> bool:
    """火山方舟视频生成：提交一个最小任务（不等待完成）。"""
    _print_header("视频 (火山方舟 VolcanoArk Seedance 2.0)")
    from xagent.domains.creative_studio.media import (
        GenerationMode,
        GenerationRequest,
        MediaKind,
        get_media_registry,
    )
    from xagent.infra.settings import get_settings

    cfg = get_settings().media
    print(f"  default_video_provider : {cfg.default_video_provider}")
    print(f"  volcano_ark key        : {_mask(cfg.volcano_ark_api_key)}")
    print(f"  volcano_ark base_url   : {cfg.volcano_ark_base_url}")
    print(f"  volcano_ark model      : {cfg.volcano_ark_model}")

    if cfg.default_video_provider != "volcano_ark" or not cfg.volcano_ark_api_key:
        print("  结果: 跳过（default_video_provider 不是 volcano_ark 或 key 未配置）")
        return False

    from xagent.domains.creative_studio.media import reset_media_registry
    reset_media_registry()
    registry = get_media_registry()
    provider = registry.get(MediaKind.video)
    if provider.name == "null":
        print("  结果: 跳过（registry 未注册 volcano_ark provider）")
        return False

    req = GenerationRequest(
        kind=MediaKind.video,
        prompt="夕阳下的海边，海浪轻拍沙滩，电影感",
        mode=GenerationMode.text_to_video,
        resolution="720p",
        duration_seconds=5,
    )
    t0 = time.time()
    try:
        task = await provider.submit(req)
        elapsed = time.time() - t0
        print(f"  provider     : {task.provider}")
        print(f"  task_id      : {task.task_id}")
        print(f"  status       : {task.status}")
        if task.error:
            print(f"  error        : {task.error}")
        print(f"  耗时         : {elapsed:.2f}s")
        ok = task.status in ("queued", "running", "succeeded") and task.task_id and not task.task_id.endswith("err")
        print(f"  结果: {'✅ 提交成功' if ok else '❌ 失败'}")
        if ok and task.task_id:
            print(f"  (如需查询产物: GET {cfg.volcano_ark_base_url}/api/v3/contents/generations/tasks/{task.task_id})")
        return ok
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"  耗时         : {elapsed:.2f}s")
        print(f"  结果: ❌ 异常 — {type(exc).__name__}: {exc}")
        return False


async def main(targets: list[str]) -> int:
    # 显式加载 .env（.env 位于 xagent 根目录，即 scripts 的上一级）
    from dotenv import load_dotenv
    env_path = _HERE.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
        print(f"(已加载 {env_path})")
    else:
        print(f"(未找到 {env_path}，将使用系统环境变量)")

    all_targets = {"llm", "image", "video"}
    selected = all_targets if not targets or "all" in targets else set(targets) & all_targets
    if not selected:
        print(f"未知目标: {targets}，可选: {all_targets} 或 all")
        return 2

    print(f"\n将检查: {sorted(selected)}")

    results: dict[str, bool] = {}
    if "llm" in selected:
        results["llm"] = await check_llm()
    if "image" in selected:
        results["image"] = await check_image()
    if "video" in selected:
        results["video"] = await check_video()

    _print_header("汇总")
    for name, ok in results.items():
        print(f"  {name:8s}: {'✅' if ok else '❌'}")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["all"]
    raise SystemExit(asyncio.run(main(targets)))
