"""API Key 管理 — 支持程序化访问（SDK / 自动化 / CI）。

每个 Key 绑定 tenant + 权限范围(scopes)，可独立吊销。
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache

from xagent.infra.logging import get_logger

logger = get_logger("xagent.api_keys")


@dataclass
class ApiKey:
    key_id: str
    tenant_id: str
    name: str
    prefix: str  # 前 8 字符，用于列表展示
    key_hash: str  # SHA-256 哈希
    scopes: list[str] = field(default_factory=lambda: ["*"])
    created_at: str = ""
    expires_at: str | None = None
    revoked: bool = False
    last_used_at: str | None = None

    def to_view(self) -> dict:
        return {
            "key_id": self.key_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "prefix": self.prefix,
            "scopes": self.scopes,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
            "last_used_at": self.last_used_at,
        }


class ApiKeyStore:
    """内存 API Key 存储（生产可替换为 DB）。"""

    def __init__(self) -> None:
        self._keys: dict[str, ApiKey] = {}  # key_id -> ApiKey
        self._hash_index: dict[str, str] = {}  # hash -> key_id

    def create(self, tenant_id: str, name: str, scopes: list[str] | None = None,
               expires_at: str | None = None) -> tuple[ApiKey, str]:
        """创建 Key，返回 (ApiKey, raw_key)。raw_key 仅此一次可见。"""
        raw = f"xak_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw.encode()).hexdigest()
        key_id = secrets.token_hex(8)
        now = datetime.now(UTC).isoformat()
        ak = ApiKey(
            key_id=key_id,
            tenant_id=tenant_id,
            name=name,
            prefix=raw[:12],
            key_hash=key_hash,
            scopes=scopes or ["*"],
            created_at=now,
            expires_at=expires_at,
        )
        self._keys[key_id] = ak
        self._hash_index[key_hash] = key_id
        logger.info("api_key_created", key_id=key_id, tenant_id=tenant_id, name=name)
        return ak, raw

    def validate(self, raw_key: str) -> ApiKey | None:
        """验证 raw key，返回 ApiKey 或 None。"""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_id = self._hash_index.get(key_hash)
        if not key_id:
            return None
        ak = self._keys.get(key_id)
        if not ak or ak.revoked:
            return None
        # 过期检查
        if ak.expires_at:
            try:
                exp = datetime.fromisoformat(ak.expires_at)
                if datetime.now(UTC) > exp:
                    return None
            except ValueError:
                pass
        # 更新最后使用时间
        ak.last_used_at = datetime.now(UTC).isoformat()
        return ak

    def list_keys(self, tenant_id: str) -> list[ApiKey]:
        return [k for k in self._keys.values() if k.tenant_id == tenant_id]

    def revoke(self, key_id: str, tenant_id: str) -> bool:
        ak = self._keys.get(key_id)
        if not ak or ak.tenant_id != tenant_id:
            return False
        ak.revoked = True
        logger.info("api_key_revoked", key_id=key_id, tenant_id=tenant_id)
        return True

    def delete(self, key_id: str, tenant_id: str) -> bool:
        ak = self._keys.get(key_id)
        if not ak or ak.tenant_id != tenant_id:
            return False
        del self._keys[key_id]
        self._hash_index.pop(ak.key_hash, None)
        return True


@lru_cache
def get_api_key_store() -> ApiKeyStore:
    return ApiKeyStore()
