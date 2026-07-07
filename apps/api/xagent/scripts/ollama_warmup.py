from __future__ import annotations

from dataclasses import dataclass
import time

import httpx

from xagent.infra.logging import get_logger
from xagent.infra.settings import LLMSettings

logger = get_logger("xagent.ollama_warmup")


@dataclass(eq=True)
class WarmupResult:
    ok: bool
    skipped: bool
    detail: str


async def warmup_ollama_model(cfg: LLMSettings) -> WarmupResult:
    if not cfg.warmup_enabled:
        return WarmupResult(ok=True, skipped=True, detail="warmup disabled")
    if not cfg.ollama_base_url:
        return WarmupResult(ok=True, skipped=True, detail="ollama base url not configured")

    model = cfg.ollama_model or cfg.default_model
    tags_url = cfg.ollama_base_url.rstrip("/") + "/api/tags"
    chat_url = cfg.ollama_base_url.rstrip("/") + "/api/chat"
    timeout = httpx.Timeout(cfg.request_timeout_seconds)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            started = time.perf_counter()
            tags = await client.get(tags_url)
            tags.raise_for_status()
            resp = await client.post(
                chat_url,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": cfg.warmup_prompt}],
                    "stream": False,
                    "options": {"num_predict": cfg.warmup_max_tokens},
                },
            )
            resp.raise_for_status()
            elapsed = round(time.perf_counter() - started, 2)
            logger.info("ollama_warmup_succeeded", model=model, elapsed_seconds=elapsed)
            return WarmupResult(ok=True, skipped=False, detail="ok")
    except Exception as exc:  # noqa: BLE001
        logger.warning("ollama_warmup_failed", error=str(exc), model=model)
        return WarmupResult(ok=False, skipped=False, detail=str(exc))
