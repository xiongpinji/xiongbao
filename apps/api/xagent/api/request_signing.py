"""请求签名验证：HMAC 请求完整性校验。

功能：
- HMAC-SHA256 请求签名
- 时间戳防重放（默认 5 分钟窗口）
- 签名头标准化
- 验证中间件

用法：
    from xagent.api.request_signing import SigningMiddleware, sign_request

    # 客户端签名：
    headers = sign_request(method="POST", path="/api/v1/agents", body=b'...', secret="key")

    # 服务端验证：
    app.add_middleware(SigningMiddleware, secrets={"client1": "secret1"})
"""

from __future__ import annotations

import hashlib
import hmac
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.signing")

# 签名头名称
HEADER_SIGNATURE = "X-Signature"
HEADER_TIMESTAMP = "X-Timestamp"
HEADER_KEY_ID = "X-Key-Id"

# 时间窗口（秒）
DEFAULT_MAX_AGE = 300  # 5 分钟


def compute_signature(
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
    secret: str,
) -> str:
    """计算 HMAC-SHA256 签名。"""
    payload = f"{method.upper()}\n{path}\n{timestamp}\n".encode() + body
    return hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()


def sign_request(
    method: str,
    path: str,
    body: bytes = b"",
    secret: str = "",
    key_id: str = "default",
) -> dict[str, str]:
    """生成签名请求头。"""
    timestamp = str(int(time.time()))
    signature = compute_signature(method, path, timestamp, body, secret)
    return {
        HEADER_SIGNATURE: signature,
        HEADER_TIMESTAMP: timestamp,
        HEADER_KEY_ID: key_id,
    }


def verify_signature(
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
    signature: str,
    secret: str,
    max_age: int = DEFAULT_MAX_AGE,
) -> tuple[bool, str]:
    """验证签名。返回 (valid, reason)。"""
    # 时间窗口检查
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False, "invalid timestamp"

    age = abs(time.time() - ts)
    if age > max_age:
        return False, f"timestamp expired ({age:.0f}s > {max_age}s)"

    # 计算期望签名
    expected = compute_signature(method, path, timestamp, body, secret)

    # 恒定时间比较
    if not hmac.compare_digest(expected, signature):
        return False, "signature mismatch"

    return True, ""


class SigningMiddleware(BaseHTTPMiddleware):
    """请求签名验证中间件。"""

    def __init__(
        self,
        app,
        secrets: dict[str, str] | None = None,
        max_age: int = DEFAULT_MAX_AGE,
        exclude_prefixes: list[str] | None = None,
    ):
        super().__init__(app)
        self.secrets = secrets or {}
        self.max_age = max_age
        self.exclude_prefixes = exclude_prefixes or ["/health", "/docs", "/openapi"]

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # 排除路径
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        # 提取签名头
        signature = request.headers.get(HEADER_SIGNATURE, "")
        timestamp = request.headers.get(HEADER_TIMESTAMP, "")
        key_id = request.headers.get(HEADER_KEY_ID, "default")

        if not signature or not timestamp:
            return JSONResponse(
                status_code=401,
                content={"error": "missing_signature", "message": "请求缺少签名头"},
            )

        # 查找密钥
        secret = self.secrets.get(key_id)
        if not secret:
            return JSONResponse(
                status_code=401,
                content={"error": "unknown_key", "message": f"未知密钥ID: {key_id}"},
            )

        # 读取请求体
        body = await request.body()

        # 验证
        valid, reason = verify_signature(
            method=request.method,
            path=path,
            timestamp=timestamp,
            body=body,
            signature=signature,
            secret=secret,
            max_age=self.max_age,
        )

        if not valid:
            logger.warning("signature verification failed: %s (%s)", path, reason)
            return JSONResponse(
                status_code=401,
                content={"error": "invalid_signature", "message": reason},
            )

        return await call_next(request)
