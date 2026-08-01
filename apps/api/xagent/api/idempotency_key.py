"""幂等键生成器：标准化 Idempotency-Key 生成。

功能：
- 基于请求内容生成确定性键
- UUID v4 随机键
- 组合键（用户 + 操作 + 时间窗口）
- 键验证

用法：
    from xagent.api.idempotency_key import generate_key, KeyStrategy

    # 随机键（前端生成）
    key = generate_key(strategy=KeyStrategy.UUID)

    # 内容哈希键（相同请求相同键）
    key = generate_key(strategy=KeyStrategy.CONTENT_HASH, body={"amount": 100})

    # 组合键（用户 + 操作 + 5分钟窗口）
    key = generate_key(strategy=KeyStrategy.COMPOSITE, user_id="u1", action="create")
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from enum import Enum
from typing import Any


class KeyStrategy(str, Enum):
    """幂等键策略。"""

    UUID = "uuid"  # 随机 UUID
    CONTENT_HASH = "content_hash"  # 内容哈希（确定性）
    COMPOSITE = "composite"  # 组合键（用户+操作+时间窗口）


def generate_key(
    strategy: KeyStrategy = KeyStrategy.UUID,
    *,
    body: dict[str, Any] | None = None,
    user_id: str | None = None,
    action: str | None = None,
    window_seconds: int = 300,
    prefix: str = "",
) -> str:
    """生成幂等键。

    Args:
        strategy: 生成策略
        body: 请求体（CONTENT_HASH 策略）
        user_id: 用户 ID（COMPOSITE 策略）
        action: 操作名（COMPOSITE 策略）
        window_seconds: 时间窗口（COMPOSITE 策略）
        prefix: 键前缀
    """
    if strategy == KeyStrategy.UUID:
        key = str(uuid.uuid4())

    elif strategy == KeyStrategy.CONTENT_HASH:
        content = json.dumps(body or {}, sort_keys=True, ensure_ascii=False)
        key = hashlib.sha256(content.encode()).hexdigest()[:32]

    elif strategy == KeyStrategy.COMPOSITE:
        # 时间窗口：同一窗口内相同操作视为重复
        window_id = int(time.time()) // window_seconds
        raw = f"{user_id or 'anon'}:{action or 'default'}:{window_id}"
        key = hashlib.md5(raw.encode()).hexdigest()[:24]

    else:
        key = str(uuid.uuid4())

    return f"{prefix}{key}" if prefix else key


def validate_key(key: str) -> bool:
    """验证幂等键格式。"""
    if not key or len(key) < 8 or len(key) > 128:
        return False
    # 只允许字母数字和连字符
    return all(c.isalnum() or c == "-" for c in key)


def extract_prefix(key: str) -> tuple[str, str]:
    """提取前缀和主体。"""
    if ":" in key:
        prefix, body = key.split(":", 1)
        return prefix, body
    return "", key
