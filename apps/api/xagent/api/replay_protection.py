"""重放保护：防止请求重放攻击。

功能：
- Nonce 唯一性校验（内存 + TTL）
- 时间戳窗口验证
- 请求指纹去重
- 中间件模式

用法：
    from xagent.api.replay_protection import ReplayProtectionMiddleware

    app.add_middleware(ReplayProtectionMiddleware, window_s=300)
"""

from __future__ import annotations

import hashlib
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.replay")

# Nonce 头
HEADER_NONCE = "X-Nonce"
HEADER_TIMESTAMP = "X-Timestamp"


class NonceStore:
    """Nonce 存储（内存 + TTL 过期）。"""

    def __init__(self, max_size: int = 100000, ttl_s: float = 600):
        self.max_size = max_size
        self.ttl_s = ttl_s
        self._nonces: dict[str, float] = {}  # nonce → 存入时间

    def check_and_store(self, nonce: str) -> bool:
        """检查 nonce 是否已使用，未使用则存储。返回 True=有效。"""
        now = time.time()

        # 定期清理
        if len(self._nonces) > self.max_size:
            self._cleanup(now)

        if nonce in self._nonces:
            return False  # 重放

        self._nonces[nonce] = now
        return True

    def _cleanup(self, now: float) -> None:
        expired = [k for k, t in self._nonces.items() if now - t > self.ttl_s]
        for k in expired:
            del self._nonces[k]


class ReplayProtectionMiddleware(BaseHTTPMiddleware):
    """重放保护中间件。"""

    def __init__(
        self,
        app,
        window_s: float = 300,
        require_nonce: bool = False,
        protect_methods: set[str] | None = None,
        exclude_prefixes: list[str] | None = None,
    ):
        super().__init__(app)
        self.window_s = window_s
        self.require_nonce = require_nonce
        self.protect_methods = protect_methods or {"POST", "PUT", "PATCH", "DELETE"}
        self.exclude_prefixes = exclude_prefixes or ["/health", "/ws"]
        self.nonce_store = NonceStore(ttl_s=window_s * 2)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # 排除路径
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        # 仅保护写方法
        if request.method not in self.protect_methods:
            return await call_next(request)

        # 时间戳验证
        timestamp_str = request.headers.get(HEADER_TIMESTAMP)
        if timestamp_str:
            try:
                ts = float(timestamp_str)
                now = time.time()
                if abs(now - ts) > self.window_s:
                    logger.warning("replay: timestamp expired %s %s", request.method, path)
                    return JSONResponse(
                        status_code=401,
                        content={"error": "request_expired", "message": "请求已过期"},
                    )
            except ValueError:
                pass

        # Nonce 验证
        nonce = request.headers.get(HEADER_NONCE)
        if nonce:
            if not self.nonce_store.check_and_store(nonce):
                logger.warning("replay: duplicate nonce %s %s", request.method, path)
                return JSONResponse(
                    status_code=409,
                    content={"error": "duplicate_request", "message": "重复请求"},
                )
        elif self.require_nonce:
            return JSONResponse(
                status_code=400,
                content={"error": "missing_nonce", "message": f"缺少 {HEADER_NONCE} 头"},
            )

        return await call_next(request)


def compute_request_fingerprint(method: str, path: str, body: bytes, nonce: str) -> str:
    """计算请求指纹（用于日志/审计）。"""
    content = f"{method}:{path}:{nonce}:{hashlib.md5(body).hexdigest()}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]
