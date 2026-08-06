"""Webhook delivery receipts."""

from unittest.mock import AsyncMock, patch

from xagent.core.webhooks import WebhookManager


async def test_emit_reports_http_failure() -> None:
    manager = WebhookManager()
    hook = manager.register(
        "tenant-webhook",
        "https://example.invalid/hook",
        ["scheduler.job_run.completed"],
    )
    response = AsyncMock()
    response.status_code = 503

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)):
        delivery = await manager.emit(
            "tenant-webhook",
            "scheduler.job_run.completed",
            {"run_id": "run-1"},
        )

    assert delivery.target_count == 1
    assert delivery.delivered_count == 0
    assert delivery.errors == (f"{hook.webhook_id}: HTTP 503",)


async def test_emit_reports_not_configured() -> None:
    delivery = await WebhookManager().emit(
        "tenant-none", "scheduler.job_run.completed", {"run_id": "run-none"}
    )

    assert delivery.target_count == 0
    assert delivery.delivered_count == 0
    assert delivery.errors == ()
