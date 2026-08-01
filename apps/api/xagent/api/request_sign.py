"""API 请求签名验证：防篡改 + 防重放。

签名算法：HMAC-SHA256
签名内容：METHOD + PATH + TIMESTAMP + BODY_MD5
有效期：±5 分钟

用法（客户端）：
    headers = sign_request("POST", "/api/v1/agents", body, api_key, api_secret)

用法（服务端中间件）：
    app.add_middleware(RequestSignMiddleware, enabled=True)
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from xagent.infra.logging import get_logger

logger = get_logger("xagent.sign")

# 签名有效期（秒）
SIGN_WINDOW = 300  # 5 分钟

# 需要签名的路径前缀（可选，默认全部）
SIGN_PREFIXES = ("/api/v1/",)

# 豁免路径
EXEMPT_PATHS = ("/health", "/docs", "/openapi.json", "/redoc", "/metrics")


def compute_signature(
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
    api_secret: str,
) -> str:
    """计算 HMAC-SHA256 签名。"""
    body_md5 = hashlib.md5(body).hexdigest() if body else ""
    payload = f"{method.upper()}\n{path}\n{timestamp}\n{body_md5}"
    return hmac.new(
        api_secret.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


def sign_request(
    method: str,
    path: str,
    body: bytes,
    api_key: str,
    api_secret: str,
) -> dict[str, str]:
    """生成签名请求头（客户端使用）。"""
    timestamp = str(int(time.time()))
    signature = compute_signature(method, path, timestamp, body, api_secret)
    return {
        "X-Api-Key": api_key,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
    }


class RequestSignMiddleware(BaseHTTPMiddleware):
    """请求签名验证中间件。"""

    def __init__(self, app, enabled: bool = False, api_secret: str = ""):
        super().__init__(app)
        self.enabled = enabled
        self.api_secret = api_secret

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        # 豁免路径
        if any(path.startswith(p) for p in EXEMPT_PATHS):
            return await call_next(request)

        # 仅验证指定前缀
        if not any(path.startswith(p) for p in SIGN_PREFIXES):
            return await call_next(request)

        # 提取签名头
        api_key = request.headers.get("x-api-key", "")
        timestamp = request.headers.get("x-timestamp", "")
        signature = request.headers.get("x-signature", "")

        if not all([api_key, timestamp, signature]):
            return Response(
                content='{"detail":"缺少签名头 (X-Api-Key, X-Timestamp, X-Signature)"}',
                status_code=401,
                media_type="application/json",
            )

        # 时间窗口校验（防重放）
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > SIGN_WINDOW:
                return Response(
                    content='{"detail":"签名已过期（±5分钟有效）"}',
                    status_code=401,
                    media_type="application/json",
                )
        except ValueError:
            return Response(
                content='{"detail":"无效时间戳"}',
                status_code=401,
                media_type="application/json",
            )

        # 读取 body 计算签名
        body = await request.body()
        expected = compute_signature(
            request.method,
            path,
            timestamp,
            body,
            self.api_secret,
        )

        if not hmac.compare_digest(signature, expected):
            logger.warning("sign_mismatch", path=path, api_key=api_key[:8])
            return Response(
                content='{"detail":"签名验证失败"}',
                status_code=403,
                media_type="application/json",
            )

        return await call_next(request)
