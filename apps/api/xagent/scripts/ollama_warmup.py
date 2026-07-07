from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx

from xagent.adapters.llm.base import Message
from xagent.adapters.llm.litellm_client import LiteLLMClient
from xagent.infra.logging import get_logger
from xagent.infra.settings import LLMSettings

logger = get_logger("xagent.ollama_warmup")


@dataclass(eq=True)
class WarmupResult:
    ok: bool
    skipped: bool
    detail: str


def _raw_ollama_model_name(cfg: LLMSettings) -> str:
    model = cfg.ollama_model or cfg.default_model
    return model.removeprefix("ollama/")


def _target_model(cfg: LLMSettings) -> str:
    if cfg.proxy_url:
        return LiteLLMClient(cfg).effective_model
    return _raw_ollama_model_name(cfg)


async def _warmup_via_proxy(cfg: LLMSettings) -> None:
    client = LiteLLMClient(cfg)
    await client.complete(
        [Message(role="user", content=cfg.warmup_prompt)],
        temperature=0,
        max_tokens=cfg.warmup_max_tokens,
    )


async def _warmup_via_ollama(cfg: LLMSettings) -> None:
    base_url = cfg.ollama_base_url.rstrip("/")
    model = _raw_ollama_model_name(cfg)
    timeout = httpx.Timeout(cfg.request_timeout_seconds)

    async with httpx.AsyncClient(timeout=timeout) as client:
        tags = await client.get(f"{base_url}/api/tags")
        tags.raise_for_status()
        resp = await client.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": cfg.warmup_prompt}],
                "stream": False,
                "options": {"num_predict": cfg.warmup_max_tokens},
            },
        )
        resp.raise_for_status()


async def warmup_ollama_model(cfg: LLMSettings) -> WarmupResult:
    if not cfg.warmup_enabled:
        return WarmupResult(ok=True, skipped=True, detail="warmup disabled")
    if not cfg.proxy_url and not cfg.ollama_base_url:
        return WarmupResult(ok=True, skipped=True, detail="proxy or ollama base url not configured")

    route = "proxy" if cfg.proxy_url else "ollama"
    model = _target_model(cfg)
    started = time.perf_counter()
    deadline = time.monotonic() + max(cfg.warmup_wait_timeout_seconds, 0)
    last_error: Exception | None = None

    while True:
        try:
            if cfg.proxy_url:
                await _warmup_via_proxy(cfg)
            else:
                await _warmup_via_ollama(cfg)
            elapsed = round(time.perf_counter() - started, 2)
            logger.info(
                "ollama_warmup_succeeded",
                model=model,
                route=route,
                elapsed_seconds=elapsed,
            )
            return WarmupResult(ok=True, skipped=False, detail="ok")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(cfg.warmup_poll_interval_seconds, remaining))

    detail = str(last_error) if last_error is not None else "warmup failed"
    logger.warning(
        "ollama_warmup_failed",
        error=detail,
        model=model,
        route=route,
        wait_timeout_seconds=cfg.warmup_wait_timeout_seconds,
    )
    return WarmupResult(ok=False, skipped=False, detail=detail)
