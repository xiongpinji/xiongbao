"""Artifact view helpers：统一 delivery / artifact 视图拼装。"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from xagent.infra.models.artifact import ArtifactORM

_CONTENT_TYPES_BY_SUFFIX = {
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}


def infer_artifact_content_type(uri: str, *, media_kind: str | None = None) -> str:
    normalized_uri = str(uri or "").strip()
    if not normalized_uri:
        return "application/octet-stream"
    if normalized_uri.startswith("placeholder://"):
        return "application/octet-stream"

    path = urlparse(normalized_uri).path.lower()
    for suffix, content_type in _CONTENT_TYPES_BY_SUFFIX.items():
        if path.endswith(suffix):
            return content_type

    if media_kind == "image":
        return "image/png"
    if media_kind == "video":
        return "video/mp4"
    if media_kind == "audio":
        return "audio/mpeg"
    return "application/octet-stream"


def build_artifact_view(
    *,
    artifact_id: str,
    run_id: str,
    task_id: str,
    tenant_id: str,
    kind: str,
    name: str,
    uri: str,
    content_type: str,
    size_bytes: int = 0,
    checksum: str = "",
    validation_summary: dict[str, Any] | None = None,
    delivery_summary: dict[str, Any] | None = None,
    lineage_summary: dict[str, Any] | None = None,
    preview_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "run_id": run_id,
        "task_id": task_id,
        "tenant_id": tenant_id,
        "kind": kind,
        "name": name,
        "uri": uri,
        "content_type": content_type,
        "size_bytes": int(size_bytes or 0),
        "checksum": checksum or "",
        "validation_summary": deepcopy(validation_summary or {}),
        "delivery_summary": deepcopy(delivery_summary or {}),
        "lineage_summary": deepcopy(lineage_summary or {}),
        "preview_summary": deepcopy(preview_summary or {}),
    }


async def upsert_artifact_record(
    session: AsyncSession,
    *,
    artifact_view: dict[str, Any],
) -> None:
    artifact_id = str(artifact_view["artifact_id"])
    payload = build_artifact_view(
        artifact_id=artifact_id,
        run_id=str(artifact_view.get("run_id") or ""),
        task_id=str(artifact_view.get("task_id") or ""),
        tenant_id=str(artifact_view.get("tenant_id") or ""),
        kind=str(artifact_view.get("kind") or ""),
        name=str(artifact_view.get("name") or ""),
        uri=str(artifact_view.get("uri") or ""),
        content_type=str(artifact_view.get("content_type") or "application/octet-stream"),
        size_bytes=int(artifact_view.get("size_bytes") or 0),
        checksum=str(artifact_view.get("checksum") or ""),
        validation_summary=artifact_view.get("validation_summary") or {},
        delivery_summary=artifact_view.get("delivery_summary") or {},
        lineage_summary=artifact_view.get("lineage_summary") or {},
        preview_summary=artifact_view.get("preview_summary") or {},
    )
    existing = await session.get(ArtifactORM, artifact_id)
    if existing is None:
        session.add(
            ArtifactORM(
                artifact_id=artifact_id,
                run_id=payload["run_id"],
                task_id=payload["task_id"],
                tenant_id=payload["tenant_id"],
                kind=payload["kind"],
                name=payload["name"],
                uri=payload["uri"],
                content_type=payload["content_type"],
                size_bytes=payload["size_bytes"],
                checksum=payload["checksum"],
                validation_summary=json.dumps(payload["validation_summary"], ensure_ascii=False),
                delivery_summary=json.dumps(payload["delivery_summary"], ensure_ascii=False),
                lineage_summary=json.dumps(payload["lineage_summary"], ensure_ascii=False),
                preview_summary=json.dumps(payload["preview_summary"], ensure_ascii=False),
            )
        )
        return

    existing.run_id = payload["run_id"]
    existing.task_id = payload["task_id"]
    existing.tenant_id = payload["tenant_id"]
    existing.kind = payload["kind"]
    existing.name = payload["name"]
    existing.uri = payload["uri"]
    existing.content_type = payload["content_type"]
    existing.size_bytes = payload["size_bytes"]
    existing.checksum = payload["checksum"]
    existing.validation_summary = json.dumps(payload["validation_summary"], ensure_ascii=False)
    existing.delivery_summary = json.dumps(payload["delivery_summary"], ensure_ascii=False)
    existing.lineage_summary = json.dumps(payload["lineage_summary"], ensure_ascii=False)
    existing.preview_summary = json.dumps(payload["preview_summary"], ensure_ascii=False)
