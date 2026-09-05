from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

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
    # LiteLLM 路由前缀（ollama/ 走 generate、ollama_chat/ 走 chat）都不是
    # Ollama 原生模型名，调 Ollama HTTP API 前必须全部剥离；
    # 漏剥 ollama_chat/ 会让 warmup 用不存在的模型名打到 /api/chat 而超时。
    return model.removeprefix("ollama_chat/").removeprefix("ollama/")


def _target_model(cfg: LLMSettings) -> str:
    if cfg.proxy_url:
        return cfg.default_model
    return _raw_ollama_model_name(cfg)


async def _warmup_via_proxy(cfg: LLMSettings, *, timeout_seconds: float | None = None) -> None:
    client = LiteLLMClient(cfg)
    call_kwargs: dict[str, Any] = {}
    if timeout_seconds is not None:
        call_kwargs["timeout"] = timeout_seconds
    await client.complete(
        [Message(role="user", content=cfg.warmup_prompt)],
        temperature=0,
        max_tokens=cfg.warmup_max_tokens,
        **call_kwargs,
    )


async def _warmup_via_ollama(cfg: LLMSettings, *, timeout_seconds: float | None = None) -> None:
    base_url = cfg.ollama_base_url.rstrip("/")
    model = _raw_ollama_model_name(cfg)
    effective_timeout = cfg.request_timeout_seconds if timeout_seconds is None else timeout_seconds
    timeout = httpx.Timeout(effective_timeout)
    options = {"num_predict": cfg.warmup_max_tokens}
    if cfg.ollama_num_ctx > 0:
        options["num_ctx"] = cfg.ollama_num_ctx

    async with httpx.AsyncClient(timeout=timeout) as client:
        tags = await client.get(f"{base_url}/api/tags")
        tags.raise_for_status()
        resp = await client.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": cfg.warmup_prompt}],
                "stream": False,
                "options": options,
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
    wait_budget = max(cfg.warmup_wait_timeout_seconds, 0)
    deadline = time.monotonic() + wait_budget if wait_budget > 0 else None
    last_error: Exception | None = None

    attempt_timeout: float
    while True:
        if deadline is None:
            attempt_timeout = cfg.request_timeout_seconds
        else:
            remaining = max(deadline - time.monotonic(), 0)
            attempt_timeout = min(cfg.request_timeout_seconds, remaining)
        try:
            if cfg.proxy_url:
                await _warmup_via_proxy(cfg, timeout_seconds=attempt_timeout)
            else:
                await _warmup_via_ollama(cfg, timeout_seconds=attempt_timeout)
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
            if deadline is None:
                break
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
