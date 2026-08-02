"""数据导入导出接口。

支持 JSON / CSV 格式的批量导入导出：
- 技能库导出/导入
- 审计日志导出
- 知识库文档列表导出
"""

from __future__ import annotations

import csv
import io
import json
import time

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/data", tags=["system"])


# ─── 导出 ───


@router.get("/export/skills", summary="导出技能库 (JSON)")
async def export_skills_json(
    principal: Principal = Depends(require_permission("system", "read")),
):
    from xagent.core.skills import get_skill_store

    store = get_skill_store()
    skills = [s.to_dict() for s in store.list_all(include_retired=True)]
    content = json.dumps({"exported_at": time.time(), "skills": skills}, ensure_ascii=False, indent=2)
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=xagent_skills_export.json"},
    )


@router.get("/export/skills/csv", summary="导出技能库 (CSV)")
async def export_skills_csv(
    principal: Principal = Depends(require_permission("system", "read")),
):
    from xagent.core.skills import get_skill_store

    store = get_skill_store()
    skills = store.list_all(include_retired=True)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["skill_id", "name", "description", "trigger_pattern", "source", "retired", "use_count"])
    for s in skills:
        d = s.to_dict()
        writer.writerow([
            d.get("skill_id", ""), d.get("name", ""), d.get("description", ""),
            d.get("trigger_pattern", ""), d.get("source", ""),
            d.get("retired", False), d.get("use_count", 0),
        ])
    content = output.getvalue()
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=xagent_skills_export.csv"},
    )


@router.get("/export/audit", summary="导出审计日志 (JSON)")
async def export_audit(
    limit: int = 500,
    principal: Principal = Depends(require_permission("audit", "read")),
):
    # 与 /audit/export 读取同一数据源（企业审计哈希链），避免两处审计源不一致
    from xagent.enterprise.audit import get_audit_log

    log = get_audit_log()
    events = log.list(principal.tenant_id)
    records = [e.to_dict() for e in events[-limit:]]

    content = json.dumps({"exported_at": time.time(), "count": len(records), "records": records}, ensure_ascii=False, indent=2, default=str)
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=xagent_audit_export.json"},
    )


# ─── 导入 ───


class SkillImportItem(BaseModel):
    name: str
    description: str = ""
    trigger_pattern: str = ""
    system_prompt_hint: str = ""
    steps: list[dict] = []
    tags: list[str] = []


class SkillImportIn(BaseModel):
    skills: list[SkillImportItem]


@router.post("/import/skills", summary="批量导入技能 (JSON)")
async def import_skills(
    body: SkillImportIn,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    from xagent.core.skills import get_skill_store

    store = get_skill_store()
    imported = 0
    errors = []
    for item in body.skills:
        try:
            store.create_skill(
                name=item.name,
                description=item.description,
                trigger_pattern=item.trigger_pattern or item.name,
                system_prompt_hint=item.system_prompt_hint,
                steps=item.steps,
                tags=item.tags,
                source="import",
            )
            imported += 1
        except Exception as exc:
            errors.append({"name": item.name, "error": str(exc)})

    return {"imported": imported, "errors": errors, "total": len(body.skills)}


@router.post("/import/skills/file", summary="上传 JSON 文件导入技能")
async def import_skills_file(
    file: UploadFile,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    from xagent.core.skills import get_skill_store

    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON file"}

    skills_data = data.get("skills", data if isinstance(data, list) else [])
    store = get_skill_store()
    imported = 0
    for item in skills_data:
        try:
            store.create_skill(
                name=item.get("name", "unnamed"),
                description=item.get("description", ""),
                trigger_pattern=item.get("trigger_pattern", item.get("name", "")),
                system_prompt_hint=item.get("system_prompt_hint", ""),
                steps=item.get("steps", []),
                tags=item.get("tags", []),
                source="import",
            )
            imported += 1
        except Exception:
            pass

    return {"imported": imported, "total": len(skills_data), "filename": file.filename}
