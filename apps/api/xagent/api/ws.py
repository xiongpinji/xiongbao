"""WebSocket 实时通信端点。

提供：
- 双向 WebSocket 连接（通知推送 + 客户端消息）
- 在线状态追踪（ConnectionManager）
- 租户级广播
- Agent 运行状态实时推送

用法：
  前端连接: ws://localhost:8000/ws?token=<jwt>
  服务端推送: await get_ws_manager().broadcast(tenant_id, "agent.progress", {...})
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from xagent.infra.logging import get_logger

router = APIRouter(tags=["websocket"])
logger = get_logger("xagent.ws")


@dataclass
class WSConnection:
    """单个 WebSocket 连接。"""

    ws: WebSocket
    user_id: str
    tenant_id: str
    connected_at: float = field(default_factory=time.time)


class ConnectionManager:
    """WebSocket 连接管理器：追踪在线用户、支持广播。"""

    def __init__(self) -> None:
        self._connections: dict[str, WSConnection] = {}  # conn_id -> WSConnection
        self._tenant_index: dict[str, set[str]] = {}  # tenant_id -> {conn_ids}
        self._lock = asyncio.Lock()

    async def connect(self, conn_id: str, ws: WebSocket, user_id: str, tenant_id: str) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[conn_id] = WSConnection(ws=ws, user_id=user_id, tenant_id=tenant_id)
            self._tenant_index.setdefault(tenant_id, set()).add(conn_id)
        logger.info("ws_connected", conn_id=conn_id, user_id=user_id, tenant_id=tenant_id)

    async def disconnect(self, conn_id: str) -> None:
        async with self._lock:
            conn = self._connections.pop(conn_id, None)
            if conn:
                self._tenant_index.get(conn.tenant_id, set()).discard(conn_id)
        if conn:
            logger.info("ws_disconnected", conn_id=conn_id, user_id=conn.user_id)

    async def send_personal(self, conn_id: str, event: str, data: dict) -> None:
        conn = self._connections.get(conn_id)
        if conn and conn.ws.client_state == WebSocketState.CONNECTED:
            await conn.ws.send_text(json.dumps({"event": event, "data": data}, ensure_ascii=False))

    async def broadcast(self, tenant_id: str, event: str, data: dict) -> None:
        """向租户内所有连接广播。"""
        conn_ids = list(self._tenant_index.get(tenant_id, set()))
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        for cid in conn_ids:
            conn = self._connections.get(cid)
            if conn and conn.ws.client_state == WebSocketState.CONNECTED:
                try:
                    await conn.ws.send_text(payload)
                except Exception:  # noqa: S110
                    await self.disconnect(cid)

    async def notify_user(self, tenant_id: str, user_id: str, event: str, data: dict) -> None:
        """向特定用户的所有连接推送。"""
        conn_ids = list(self._tenant_index.get(tenant_id, set()))
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        for cid in conn_ids:
            conn = self._connections.get(cid)
            if conn and conn.user_id == user_id and conn.ws.client_state == WebSocketState.CONNECTED:
                try:
                    await conn.ws.send_text(payload)
                except Exception:  # noqa: S110
                    pass

    def online_count(self, tenant_id: str = "") -> int:
        if tenant_id:
            return len(self._tenant_index.get(tenant_id, set()))
        return len(self._connections)

    def online_users(self, tenant_id: str) -> list[str]:
        conn_ids = self._tenant_index.get(tenant_id, set())
        users = set()
        for cid in conn_ids:
            conn = self._connections.get(cid)
            if conn:
                users.add(conn.user_id)
        return list(users)


# 全局单例
_manager: ConnectionManager | None = None


def get_ws_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = ""):
    """WebSocket 入口。

    连接时通过 query param 传 token 进行认证。
    消息格式: {"event": "...", "data": {...}}
    """
    import uuid

    from xagent.enterprise.auth.dependencies import decode_token
    from xagent.infra.settings import get_settings

    settings = get_settings()

    # 认证
    user_id = "anonymous"
    tenant_id = "default"
    if token and settings.security.require_auth:
        try:
            payload = decode_token(token)
            user_id = payload.get("sub", "anonymous")
            tenant_id = payload.get("tenant_id", "default")
        except Exception:
            await ws.close(code=4001, reason="Invalid token")
            return

    conn_id = uuid.uuid4().hex[:12]
    mgr = get_ws_manager()
    await mgr.connect(conn_id, ws, user_id, tenant_id)

    # 发送欢迎消息
    await mgr.send_personal(conn_id, "connected", {
        "conn_id": conn_id,
        "user_id": user_id,
        "online": mgr.online_count(tenant_id),
    })

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                event = msg.get("event", "")
                data = msg.get("data", {})

                if event == "ping":
                    await mgr.send_personal(conn_id, "pong", {"ts": time.time()})
                elif event == "status":
                    await mgr.send_personal(conn_id, "status", {
                        "online": mgr.online_count(tenant_id),
                        "users": mgr.online_users(tenant_id),
                    })
                elif event == "broadcast":
                    # 客户端发起租户广播
                    await mgr.broadcast(tenant_id, "user.message", {
                        "from": user_id,
                        "message": str(data.get("message", ""))[:500],
                    })
                else:
                    await mgr.send_personal(conn_id, "ack", {"event": event})
            except json.JSONDecodeError:
                await mgr.send_personal(conn_id, "error", {"message": "Invalid JSON"})
    except WebSocketDisconnect:
        pass
    finally:
        await mgr.disconnect(conn_id)
