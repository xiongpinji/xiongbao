"""API 密钥轮换：安全密钥生命周期管理。

功能：
- 密钥生成（带前缀标识）
- 多密钥共存（轮换期新旧并行）
- 过期自动失效
- 密钥验证（恒定时间比较）

用法：
    from xagent.api.key_rotation import key_manager

    key = key_manager.generate("client_123", ttl_days=90)
    # key = "xag_abc123..."
    valid = key_manager.verify("client_123", provided_key)
    key_manager.rotate("client_123")  # 生成新密钥，旧密钥保留 grace period
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field

from xagent.infra.logging import get_logger

logger = get_logger("xagent.key_rotation")

# 密钥前缀
KEY_PREFIX = "xag_"


@dataclass
class APIKey:
    """API 密钥记录。"""

    key_hash: str  # SHA256 哈希（不存明文）
    prefix: str  # 前 8 字符（用于展示）
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    revoked: bool = False
    last_used: float | None = None


class KeyManager:
    """密钥轮换管理器。"""

    def __init__(self, grace_period_s: float = 86400 * 7):
        """
        Args:
            grace_period_s: 轮换后旧密钥保留时间（默认 7 天）
        """
        self.grace_period_s = grace_period_s
        # client_id → [APIKey]（最新在前）
        self._keys: dict[str, list[APIKey]] = {}

    def generate(self, client_id: str, ttl_days: int = 90) -> str:
        """生成新密钥。"""
        raw = secrets.token_urlsafe(32)
        full_key = f"{KEY_PREFIX}{raw}"
        key_hash = self._hash(full_key)

        record = APIKey(
            key_hash=key_hash,
            prefix=full_key[:12],
            expires_at=time.time() + ttl_days * 86400 if ttl_days > 0 else None,
        )

        if client_id not in self._keys:
            self._keys[client_id] = []
        self._keys[client_id].insert(0, record)

        logger.info("key generated: %s [%s...]", client_id, record.prefix)
        return full_key

    def verify(self, client_id: str, provided_key: str) -> bool:
        """验证密钥（恒定时间比较）。"""
        keys = self._keys.get(client_id, [])
        provided_hash = self._hash(provided_key)
        now = time.time()

        for key in keys:
            if key.revoked:
                continue
            if key.expires_at and now > key.expires_at:
                continue
            if hmac.compare_digest(key.key_hash, provided_hash):
                key.last_used = now
                return True
        return False

    def rotate(self, client_id: str, ttl_days: int = 90) -> str:
        """轮换密钥：生成新密钥，旧密钥进入 grace period。"""
        # 旧密钥设置过期
        now = time.time()
        for key in self._keys.get(client_id, []):
            if not key.revoked and (key.expires_at is None or key.expires_at > now):
                key.expires_at = now + self.grace_period_s

        # 生成新密钥
        new_key = self.generate(client_id, ttl_days=ttl_days)
        logger.info("key rotated: %s", client_id)
        return new_key

    def revoke(self, client_id: str) -> int:
        """撤销所有密钥。"""
        count = 0
        for key in self._keys.get(client_id, []):
            if not key.revoked:
                key.revoked = True
                count += 1
        logger.info("keys revoked: %s (%d)", client_id, count)
        return count

    def list_keys(self, client_id: str) -> list[dict]:
        """列出密钥（仅前缀，不含哈希）。"""
        now = time.time()
        result = []
        for key in self._keys.get(client_id, []):
            result.append({
                "prefix": key.prefix,
                "created_at": key.created_at,
                "expires_at": key.expires_at,
                "revoked": key.revoked,
                "active": not key.revoked and (key.expires_at is None or key.expires_at > now),
                "last_used": key.last_used,
            })
        return result

    def cleanup_expired(self) -> int:
        """清理过期密钥。"""
        now = time.time()
        removed = 0
        for client_id in list(self._keys.keys()):
            self._keys[client_id] = [
                k for k in self._keys[client_id]
                if not (k.expires_at and k.expires_at < now)
            ]
            if not self._keys[client_id]:
                del self._keys[client_id]
            removed += 1
        return removed

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()


# 全局单例
key_manager = KeyManager()
