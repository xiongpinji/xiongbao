"""Webhook 通知系统：任务完成 / 工作流状态变更时推送 HTTP 回调。"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from xagent.infra.logging import get_logger

logger = get_logger("xagent.webhooks")


@dataclass
class WebhookConfig:
    webhook_id: str
    tenant_id: str
    url: str
    events: list[str] = field(default_factory=lambda: ["*"])
    secret: str = ""  # HMAC 签名密钥
    active: bool = True
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("secret", None)  # 不暴露 secret
        return d


class WebhookManager:
    """Webhook 注册 + 触发。"""

    def __init__(self) -> None:
        self._hooks: dict[str, WebhookConfig] = {}

    def register(
        self, tenant_id: str, url: str, events: list[str], secret: str = "",
    ) -> WebhookConfig:
        hook = WebhookConfig(
            webhook_id=uuid.uuid4().hex[:12],
            tenant_id=tenant_id,
            url=url,
            events=events,
            secret=secret,
        )
        self._hooks[hook.webhook_id] = hook
        # 持久化
        try:
            import asyncio

            from xagent.core.persistence import save_webhook
            asyncio.get_event_loop().create_task(save_webhook({
                "webhook_id": hook.webhook_id, "tenant_id": tenant_id,
                "url": url, "events": events, "secret": secret,
            }))
        except Exception:  # noqa: S110
            pass
        logger.info("webhook_registered", webhook_id=hook.webhook_id, url=url)
        return hook

    def list(self, tenant_id: str) -> list[WebhookConfig]:
        return [h for h in self._hooks.values() if h.tenant_id == tenant_id]

    def delete(self, webhook_id: str, tenant_id: str) -> bool:
        hook = self._hooks.get(webhook_id)
        if not hook or hook.tenant_id != tenant_id:
            return False
        del self._hooks[webhook_id]
        try:
            import asyncio

            from xagent.core.persistence import delete_webhook
            asyncio.get_event_loop().create_task(delete_webhook(webhook_id))
        except Exception:  # noqa: S110
            pass
        return True

    async def emit(self, tenant_id: str, event: str, payload: dict) -> None:
        """触发事件 → 推送所有匹配的 webhook。"""
        targets = [
            h for h in self._hooks.values()
            if h.tenant_id == tenant_id and h.active
            and ("*" in h.events or event in h.events)
        ]
        if not targets:
            return

        body = json.dumps({
            "event": event,
            "timestamp": time.time(),
            "data": payload,
        }, ensure_ascii=False)

        async with httpx.AsyncClient(timeout=10) as client:
            for hook in targets:
                headers = {"Content-Type": "application/json"}
                if hook.secret:
                    sig = hmac.new(
                        hook.secret.encode(), body.encode(), hashlib.sha256,
                    ).hexdigest()
                    headers["X-Webhook-Signature"] = f"sha256={sig}"
                try:
                    resp = await client.post(hook.url, content=body, headers=headers)
                    logger.info(
                        "webhook_delivered", webhook_id=hook.webhook_id,
                        status=resp.status_code, event=event,
                    )
                except Exception as exc:
                    logger.warning(
                        "webhook_failed", webhook_id=hook.webhook_id,
                        error=str(exc)[:200], event=event,
                    )


_manager: WebhookManager | None = None


def get_webhook_manager() -> WebhookManager:
    global _manager
    if _manager is None:
        _manager = WebhookManager()
    return _manager
