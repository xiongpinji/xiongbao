"""运维联动端点（P1）：Alertmanager 告警 webhook 接收与告警证据查询。

闭环：Prometheus 告警规则（deploy/grafana/alert-rules.yml，7 条）
→ Alertmanager webhook（deploy/helm/templates/alertmanager-config.yaml 的
webhookUrl 指向本端点）→ 本端点鉴权接收 → 落 evidence_records（kind=alert:*）
→ 结构化日志（critical 额外打 alert_critical_received 供巡检/自动归档关联）。

安全：webhook 使用共享令牌头 ``X-Alert-Token``（配置
``XAGENT_SECURITY__ALERT_WEBHOOK_TOKEN``）；未配置时端点 503 诚实禁用，
不暴露无鉴权写入口。
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session
from xagent.infra.logging import get_logger
from xagent.infra.models.evidence import EvidenceORM
from xagent.infra.repos.evidence import build_evidence_record, persist_evidence_record
from xagent.infra.settings import get_settings

logger = get_logger("xagent.ops")

router = APIRouter(prefix="/ops", tags=["ops"])

_OPS_TENANT = "ops"


class AlertIn(BaseModel):
    """Alertmanager v4 单条告警（字段宽松，未知字段忽略）。"""

    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str = ""
    endsAt: str = ""
    fingerprint: str = ""
    status: str = ""


class AlertGroupIn(BaseModel):
    """Alertmanager v4 webhook payload。"""

    status: str = "firing"
    receiver: str = ""
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    alerts: list[AlertIn] = Field(default_factory=list, max_length=200)


def _check_alert_token(x_alert_token: str | None) -> None:
    configured = get_settings().security.alert_webhook_token
    if not configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "告警 webhook 未启用：请配置 XAGENT_SECURITY__ALERT_WEBHOOK_TOKEN",
        )
    if not x_alert_token or x_alert_token != configured:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效告警令牌")


@router.post("/alerts/webhook", summary="接收 Alertmanager 告警（共享令牌鉴权）")
async def receive_alerts(
    body: AlertGroupIn,
    session: AsyncSession = Depends(get_session),
    x_alert_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_alert_token(x_alert_token)
    persisted = 0
    for alert in body.alerts:
        labels = {**body.commonLabels, **alert.labels}
        alertname = labels.get("alertname", "unknown")
        severity = labels.get("severity", "info")
        fingerprint = alert.fingerprint or uuid.uuid4().hex[:16]
        record = build_evidence_record(
            tenant_id=_OPS_TENANT,
            run_id=fingerprint,
            task_id=alertname,
            kind=f"alert:{severity}",
            payload={
                "group_status": body.status,
                "receiver": body.receiver,
                "labels": labels,
                "annotations": alert.annotations,
                "startsAt": alert.startsAt,
                "endsAt": alert.endsAt,
                "alert_status": alert.status,
            },
        )
        await persist_evidence_record(
            session,
            evidence_id=str(record["evidence_id"]),
            tenant_id=_OPS_TENANT,
            run_id=fingerprint,
            task_id=alertname,
            artifact_id=None,
            kind=str(record["kind"]),
            payload=record["payload"],
        )
        persisted += 1
        if severity == "critical" and body.status == "firing":
            logger.warning(
                "alert_critical_received",
                alertname=alertname,
                fingerprint=fingerprint,
                labels=labels,
            )
    await session.commit()
    logger.info(
        "alerts_received", group_status=body.status, count=persisted,
        receiver=body.receiver,
    )
    return {"received": persisted, "group_status": body.status}


@router.get("/alerts", summary="查询最近告警证据")
async def list_alerts(
    limit: int = 50,
    principal: Principal = Depends(require_permission("system", "read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    stmt = (
        select(EvidenceORM)
        .where(EvidenceORM.tenant_id == _OPS_TENANT)
        .where(EvidenceORM.kind.startswith("alert:"))
        .order_by(EvidenceORM.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "alerts": [
            {
                "evidence_id": r.evidence_id,
                "alertname": r.task_id,
                "severity": r.kind.split(":", 1)[-1],
                "fingerprint": r.run_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "payload": json.loads(r.payload or "{}"),
            }
            for r in rows
        ],
        "total": len(rows),
    }
