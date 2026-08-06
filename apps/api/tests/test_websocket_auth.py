"""WebSocket 认证身份映射回归测试。"""

from __future__ import annotations

import json

import pytest
from starlette.websockets import WebSocketDisconnect, WebSocketState
from xagent.api import ws as ws_api
from xagent.enterprise.auth import create_access_token
from xagent.infra.settings import get_settings


class _DisconnectingWebSocket:
    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTED
        self.sent: list[dict] = []

    async def accept(self) -> None:
        return None

    async def send_text(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def receive_text(self) -> str:
        raise WebSocketDisconnect()

    async def close(self, *, code: int, reason: str) -> None:
        raise AssertionError(f"valid token was rejected: {code} {reason}")


@pytest.mark.asyncio
async def test_websocket_uses_principal_attributes_for_authenticated_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XAGENT_SECURITY__REQUIRE_AUTH", "true")
    get_settings.cache_clear()
    ws_api._manager = None
    socket = _DisconnectingWebSocket()
    token = create_access_token(
        user_id="ws-user",
        tenant_id="tenant-ws",
        roles=["member"],
    )

    await ws_api.websocket_endpoint(socket, token)

    assert socket.sent[0]["event"] == "connected"
    assert socket.sent[0]["data"]["user_id"] == "ws-user"
    assert ws_api.get_ws_manager().online_count("tenant-ws") == 0
