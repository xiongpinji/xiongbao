"""Evidence repository：运行期 evidence 持久化与查询。"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.infra.logging import get_logger
from xagent.infra.models.evidence import EvidenceORM

logger = get_logger("xagent.repos.evidence")


def build_evidence_id(
    *, tenant_id: str, run_id: str, task_id: str, kind: str, payload: dict[str, Any] | None = None
) -> str:
    normalized_payload = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(  # noqa: S324 - deterministic evidence ID, not a security boundary
        f"{tenant_id}|{run_id}|{task_id}|{kind}|{normalized_payload}".encode()
    ).hexdigest()
    return digest[:40]


def build_evidence_record(
    *,
    tenant_id: str,
    run_id: str,
    task_id: str,
    kind: str,
    payload: dict[str, Any] | None = None,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    payload_copy = deepcopy(payload or {})
    return {
        "evidence_id": build_evidence_id(
            tenant_id=tenant_id,
            run_id=run_id,
            task_id=task_id,
            kind=kind,
            payload=payload_copy,
        ),
        "tenant_id": tenant_id,
        "run_id": run_id,
        "task_id": task_id,
        "artifact_id": artifact_id,
        "kind": kind,
        "payload": payload_copy,
    }


async def persist_evidence_bundle(
    session: AsyncSession,
    *,
    tenant_id: str,
    run_id: str,
    task_id: str,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    persisted: list[dict[str, Any]] = []
    for record in records:
        evidence = build_evidence_record(
            tenant_id=tenant_id,
            run_id=run_id,
            task_id=task_id,
            artifact_id=str(record.get("artifact_id") or "").strip() or None,
            kind=str(record.get("kind") or "evidence.record"),
            payload=record.get("payload") if isinstance(record.get("payload"), dict) else {},
        )
        await persist_evidence_record(
            session,
            evidence_id=str(evidence["evidence_id"]),
            tenant_id=tenant_id,
            run_id=run_id,
            task_id=task_id,
            artifact_id=evidence["artifact_id"],
            kind=str(evidence["kind"]),
            payload=evidence["payload"],
        )
        persisted.append(evidence)
    return persisted


logger = get_logger("xagent.repos.evidence")


async def persist_evidence_record(
    session: AsyncSession,
    *,
    evidence_id: str,
    tenant_id: str,
    run_id: str,
    task_id: str,
    artifact_id: str | None,
    kind: str,
    payload: dict | None = None,
) -> None:
    encoded_payload = json.dumps(payload or {}, ensure_ascii=False)
    existing = await session.get(EvidenceORM, {"tenant_id": tenant_id, "evidence_id": evidence_id})
    if existing is not None:
        existing.run_id = run_id
        existing.task_id = task_id
        existing.artifact_id = artifact_id
        existing.kind = kind
        existing.payload = encoded_payload
        return

    session.add(
        EvidenceORM(
            evidence_id=evidence_id,
            tenant_id=tenant_id,
            run_id=run_id,
            task_id=task_id,
            artifact_id=artifact_id,
            kind=kind,
            payload=encoded_payload,
        )
    )


async def load_evidence_records(
    session: AsyncSession,
    tenant_id: str,
    *,
    run_id: str | None = None,
    task_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    try:
        stmt = select(EvidenceORM).where(EvidenceORM.tenant_id == tenant_id)
        if run_id:
            stmt = stmt.where(EvidenceORM.run_id == run_id)
        if task_id:
            stmt = stmt.where(EvidenceORM.task_id == task_id)
        stmt = stmt.order_by(EvidenceORM.created_at.asc()).limit(limit)
        result = await session.execute(stmt)
    except Exception as exc:
        logger.warning(
            "load_evidence_failed",
            tenant_id=tenant_id,
            run_id=run_id,
            task_id=task_id,
            error=str(exc),
        )
        return []

    records: list[dict] = []
    for row in result.scalars():
        try:
            payload_dict = json.loads(row.payload) if row.payload else {}
        except json.JSONDecodeError as exc:
            logger.warning(
                "load_evidence_payload_invalid",
                tenant_id=tenant_id,
                evidence_id=row.evidence_id,
                error=str(exc),
            )
            payload_dict = {}
        records.append(
            {
                "evidence_id": row.evidence_id,
                "tenant_id": row.tenant_id,
                "run_id": row.run_id,
                "task_id": row.task_id,
                "artifact_id": row.artifact_id,
                "kind": row.kind,
                "payload": payload_dict,
            }
        )
    return records
