"""对象存储抽象 + local FS 实现 + S3 接入点。

local FS：按 tenant_id 分目录；S3：bucket + key 前缀。
接口：put(key, data, tenant) -> url；get(url) -> bytes；delete(url)。
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class StoredObject:
    key: str
    url: str
    size: int


@runtime_checkable
class ObjectStore(Protocol):
    backend: str

    async def put(
        self, key: str, data: bytes, *, tenant_id: str, content_type: str = ""
    ) -> StoredObject: ...

    async def get(self, url: str) -> bytes: ...
    async def delete(self, url: str) -> None: ...


class LocalObjectStore:
    """本地文件系统存储（lite/单机）。"""

    backend = "local"

    def __init__(self, root: str = "./data/storage") -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    async def put(
        self, key: str, data: bytes, *, tenant_id: str, content_type: str = ""
    ) -> StoredObject:
        # 安全：tenant_id 限字符，防路径穿越
        safe_tenant = "".join(c for c in tenant_id if c.isalnum() or c in "-_") or "default"
        ext = Path(key).suffix or ".bin"
        obj_id = f"{uuid.uuid4().hex}{ext}"
        dest = self._root / safe_tenant / obj_id
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        url = f"local://{safe_tenant}/{obj_id}"
        return StoredObject(key=key, url=url, size=len(data))

    async def get(self, url: str) -> bytes:
        if not url.startswith("local://"):
            raise ValueError(f"非 local URL: {url}")
        rel = url[len("local://"):]
        path = self._root / rel
        if not path.exists():
            raise FileNotFoundError(url)
        return path.read_bytes()

    async def delete(self, url: str) -> None:
        if url.startswith("local://"):
            rel = url[len("local://"):]
            path = self._root / rel
            path.unlink(missing_ok=True)


class S3ObjectStore:
    """S3 兼容存储（full/enterprise）。需 boto3。"""

    backend = "s3"

    def __init__(self, bucket: str, prefix: str = "") -> None:
        self._bucket = bucket
        self._prefix = prefix

    async def put(
        self, key: str, data: bytes, *, tenant_id: str, content_type: str = ""
    ) -> StoredObject:
        import boto3

        client = boto3.client("s3")
        obj_id = f"{self._prefix}{tenant_id}/{uuid.uuid4().hex}/{key}"
        client.put_object(Bucket=self._bucket, Key=obj_id, Body=data, ContentType=content_type)
        url = f"s3://{self._bucket}/{obj_id}"
        return StoredObject(key=key, url=url, size=len(data))

    async def get(self, url: str) -> bytes:
        import boto3

        client = boto3.client("s3")
        # s3://bucket/key
        parts = url.replace("s3://", "").split("/", 1)
        bucket, key = parts[0], parts[1]
        resp = client.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()

    async def delete(self, url: str) -> None:
        import boto3

        client = boto3.client("s3")
        parts = url.replace("s3://", "").split("/", 1)
        client.delete_object(Bucket=parts[0], Key=parts[1])


@lru_cache
def get_object_store() -> ObjectStore:
    s3_bucket = os.environ.get("XAGENT_STORAGE__S3_BUCKET", "")
    if s3_bucket:
        try:
            return S3ObjectStore(
                bucket=s3_bucket,
                prefix=os.environ.get("XAGENT_STORAGE__S3_PREFIX", ""),
            )
        except Exception:  # noqa: S110  S3 初始化失败降级本地
            pass
    return LocalObjectStore(
        root=os.environ.get("XAGENT_STORAGE__LOCAL_ROOT", "./data/storage")
    )


def reset_object_store() -> None:
    get_object_store.cache_clear()
