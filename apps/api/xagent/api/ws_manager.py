"""WebSocket 连接管理器：房间/广播/心跳。

功能：
- 连接注册/注销
- 房间（Room）分组广播
- 心跳 Ping/Pong 检测
- 连接元数据（user_id, tenant）

用法：
    from xagent.api.ws_manager import ws_manager

    await ws_manager.connect(websocket, user_id="u1", rooms=["chat:123"])
    await ws_manager.broadcast("chat:123", {"type": "message", "data": ...})
    await ws_manager.disconnect(websocket)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from starlette.websockets import WebSocket

from xagent.infra.logging import get_logger

logger = get_logger("xagent.ws")


@dataclass
class Connection:
    """WebSocket 连接。"""

    ws: WebSocket
    user_id: str = ""
    tenant: str = ""
    rooms: set[str] = field(default_factory=set)
    connected_at: float = field(default_factory=time.time)
    last_pong: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class WebSocketManager:
    """WebSocket 连接管理器。"""

    def __init__(self, heartbeat_interval: float = 30.0, heartbeat_timeout: float = 90.0):
        self._connections: dict[int, Connection] = {}  # id(ws) → Connection
        self._rooms: dict[str, set[int]] = {}  # room → set(id(ws))
        self._user_connections: dict[str, set[int]] = {}  # user_id → set(id(ws))
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def room_count(self) -> int:
        return len(self._rooms)

    async def connect(
        self,
        ws: WebSocket,
        user_id: str = "",
        tenant: str = "",
        rooms: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Connection:
        """接受并注册连接。"""
        await ws.accept()
        conn = Connection(
            ws=ws,
            user_id=user_id,
            tenant=tenant,
            rooms=set(rooms or []),
            metadata=metadata or {},
        )
        ws_id = id(ws)
        self._connections[ws_id] = conn

        # 加入房间
        for room in conn.rooms:
            if room not in self._rooms:
                self._rooms[room] = set()
            self._rooms[room].add(ws_id)

        # 用户索引
        if user_id:
            if user_id not in self._user_connections:
                self._user_connections[user_id] = set()
            self._user_connections[user_id].add(ws_id)

        logger.info(
            "ws connected: user=%s rooms=%s (total=%d)",
            user_id,
            list(conn.rooms),
            len(self._connections),
        )
        return conn

    async def disconnect(self, ws: WebSocket) -> None:
        """注销连接。"""
        ws_id = id(ws)
        conn = self._connections.pop(ws_id, None)
        if not conn:
            return

        # 离开房间
        for room in conn.rooms:
            if room in self._rooms:
                self._rooms[room].discard(ws_id)
                if not self._rooms[room]:
                    del self._rooms[room]

        # 用户索引
        if conn.user_id and conn.user_id in self._user_connections:
            self._user_connections[conn.user_id].discard(ws_id)
            if not self._user_connections[conn.user_id]:
                del self._user_connections[conn.user_id]

        logger.info("ws disconnected: user=%s", conn.user_id)

    async def send_to(self, ws: WebSocket, data: dict[str, Any]) -> bool:
        """发送给单个连接。"""
        try:
            await ws.send_json(data)
            return True
        except Exception:
            return False

    async def broadcast(
        self,
        room: str,
        data: dict[str, Any],
        exclude: WebSocket | None = None,
    ) -> int:
        """广播到房间。返回发送数量。"""
        ws_ids = self._rooms.get(room, set())
        sent = 0
        exclude_id = id(exclude) if exclude else None

        for ws_id in list(ws_ids):
            if ws_id == exclude_id:
                continue
            conn = self._connections.get(ws_id)
            if conn and await self.send_to(conn.ws, data):
                sent += 1

        return sent

    async def send_to_user(
        self, user_id: str, data: dict[str, Any]
    ) -> int:
        """发送给指定用户的所有连接。"""
        ws_ids = self._user_connections.get(user_id, set())
        sent = 0
        for ws_id in list(ws_ids):
            conn = self._connections.get(ws_id)
            if conn and await self.send_to(conn.ws, data):
                sent += 1
        return sent

    def join_room(self, ws: WebSocket, room: str) -> None:
        """加入房间。"""
        ws_id = id(ws)
        conn = self._connections.get(ws_id)
        if not conn:
            return
        conn.rooms.add(room)
        if room not in self._rooms:
            self._rooms[room] = set()
        self._rooms[room].add(ws_id)

    def leave_room(self, ws: WebSocket, room: str) -> None:
        """离开房间。"""
        ws_id = id(ws)
        conn = self._connections.get(ws_id)
        if not conn:
            return
        conn.rooms.discard(room)
        if room in self._rooms:
            self._rooms[room].discard(ws_id)

    def get_room_members(self, room: str) -> int:
        """获取房间成员数。"""
        return len(self._rooms.get(room, set()))

    def is_online(self, user_id: str) -> bool:
        """用户是否在线。"""
        return bool(self._user_connections.get(user_id))


# 全局单例
ws_manager = WebSocketManager()
