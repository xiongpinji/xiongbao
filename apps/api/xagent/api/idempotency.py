"""API 幂等性保障：Idempotency-Key 防重复提交。

对 POST/PUT 请求，客户端携带 Idempotency-Key 头：
- 首次请求：正常执行，缓存响应
- 重复请求（相同 Key）：直接返回缓存响应，不重复执行
- Key 有效期：24 小时

用法（客户端）：
    headers = {"Idempotency-Key": str(uuid4())}
    requests.post("/api/v1/agents", json=data, headers=headers)

用法（服务端）：
    app.add_middleware(IdempotencyMiddleware)
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from xagent.infra.logging import get_logger

logger = get_logger("xagent.idempotency")

# 幂等 Key 有效期（秒）
KEY_TTL = 86400  # 24 小时

# 最大缓存条目
MAX_ENTRIES = 10000

# 需要幂等保护的方法
IDEMPOTENT_METHODS = ("POST", "PUT", "PATCH")


@dataclass
class CachedResponse:
    """缓存的响应。"""

    status_code: int
    body: bytes
    content_type: str
    created_at: float = field(default_factory=time.time)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """幂等性中间件。"""

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        self._cache: dict[str, CachedResponse] = {}

    def _make_key(self, request: Request, idempotency_key: str) -> str:
        """生成缓存 key：方法 + 路径 + 幂等 Key。"""
        raw = f"{request.method}:{request.url.path}:{idempotency_key}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _cleanup(self):
        """清理过期条目。"""
        if len(self._cache) < MAX_ENTRIES:
            return
        now = time.time()
        expired = [k for k, v in self._cache.items() if now - v.created_at > KEY_TTL]
        for k in expired:
            del self._cache[k]
        # 仍超限则删除最旧 25%
        if len(self._cache) >= MAX_ENTRIES:
            sorted_keys = sorted(self._cache, key=lambda k: self._cache[k].created_at)
            for k in sorted_keys[: MAX_ENTRIES // 4]:
                del self._cache[k]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.enabled:
            return await call_next(request)

        # 仅保护写操作
        if request.method not in IDEMPOTENT_METHODS:
            return await call_next(request)

        # 提取幂等 Key
        idempotency_key = request.headers.get("idempotency-key", "")
        if not idempotency_key:
            # 无 Key 则正常执行（不强制）
            return await call_next(request)

        cache_key = self._make_key(request, idempotency_key)

        # 检查缓存
        cached = self._cache.get(cache_key)
        if cached:
            # 检查过期
            if time.time() - cached.created_at < KEY_TTL:
                logger.info("idempotent_hit", key=idempotency_key[:16], path=request.url.path)
                return Response(
                    content=cached.body,
                    status_code=cached.status_code,
                    media_type=cached.content_type,
                    headers={
                        "X-Idempotent-Replay": "true",
                        "Cache-Control": "no-store",
                    },
                )
            else:
                del self._cache[cache_key]

        # 执行实际请求
        response = await call_next(request)

        # 缓存成功/客户端错误响应（不缓存 5xx）
        if response.status_code < 500:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk if isinstance(chunk, bytes) else chunk.encode()

            self._cleanup()
            self._cache[cache_key] = CachedResponse(
                status_code=response.status_code,
                body=body,
                content_type=response.media_type or "application/json",
            )

            return Response(
                content=body,
                status_code=response.status_code,
                media_type=response.media_type,
                headers={"X-Idempotent-Replay": "false"},
            )

        return response
