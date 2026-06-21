"""审计路由：查看/导出审计链 + 校验完整性。强鉴权 + RBAC。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.audit.persistence import export_chain, export_json
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", summary="查看审计事件（当前租户）")
async def list_audit(
    principal: Principal = Depends(require_permission("audit", "read")),
) -> dict:
    log = get_audit_log()
    ok, broken = log.verify()
    return {
        "integrity": {"valid": ok, "first_broken_seq": broken},
        "events": [e.to_dict() for e in log.list(principal.tenant_id)],
    }


@router.get("/export", summary="导出审计链 JSON（含完整性校验）", response_class=PlainTextResponse)
async def export_audit(
    principal: Principal = Depends(require_permission("audit", "read")),
) -> str:
    return export_json(get_audit_log(), principal.tenant_id)


@router.get("/verify", summary="校验整条审计链完整性")
async def verify_audit(
    principal: Principal = Depends(require_permission("audit", "read")),
) -> dict:
    ok, broken = get_audit_log().verify()
    return {"valid": ok, "first_broken_seq": broken}


@router.get("/export-full", summary="导出全部审计（admin）", response_class=PlainTextResponse)
async def export_full(
    principal: Principal = Depends(require_permission("audit", "manage")),
) -> str:
    # admin 可导出全链（不限租户）
    import json

    log = get_audit_log()
    ok, broken = log.verify()
    return json.dumps(
        {
            "integrity": {"valid": ok, "first_broken_seq": broken},
            "events": [e.to_dict() for e in log.list()],
        },
        ensure_ascii=False,
        indent=2,
    )


# 消除未使用导入告警（export_chain 在导出逻辑中可用）
_ = export_chain
