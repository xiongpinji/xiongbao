"""租户隔离的完整 Skill Package 上传与读取 API。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.skills import get_skill_store
from xagent.domains.skill_packages import (
    SkillPackageLimits,
    SkillPackageRecord,
    get_skill_package,
    import_skill_package_zip,
    list_skill_packages,
)
from xagent.domains.skill_packages.service import DEFAULT_PACKAGES_ROOT
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session

router = APIRouter(prefix="/skill-packages", tags=["skill-packages"])
PACKAGES_ROOT = DEFAULT_PACKAGES_ROOT


def _view(record: SkillPackageRecord, *, detail: bool) -> dict[str, Any]:
    value = asdict(record)
    value.pop("root_path", None)
    if not detail:
        value.pop("body", None)
        value.pop("frontmatter", None)
    return value


@router.get("", summary="列出租户 Skill Package")
async def list_packages(
    principal: Principal = Depends(require_permission("system", "read")),
    session: AsyncSession = Depends(get_session),
):
    packages = await list_skill_packages(session, principal.tenant_id)
    return {"packages": [_view(item, detail=False) for item in packages], "total": len(packages)}


@router.get("/{package_id}", summary="读取 Skill Package 详情")
async def get_package(
    package_id: str,
    principal: Principal = Depends(require_permission("system", "read")),
    session: AsyncSession = Depends(get_session),
):
    package = await get_skill_package(session, principal.tenant_id, package_id)
    if package is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill Package 不存在")
    return _view(package, detail=True)


@router.post("/import", status_code=status.HTTP_201_CREATED, summary="上传 ZIP Skill Package")
async def import_package(
    file: UploadFile = File(...),
    principal: Principal = Depends(require_permission("system", "manage")),
    session: AsyncSession = Depends(get_session),
):
    limits = SkillPackageLimits()
    try:
        archive = await file.read(limits.max_archive_bytes + 1)
    finally:
        await file.close()
    if len(archive) > limits.max_archive_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "archive_size_limit")
    try:
        package = await import_skill_package_zip(
            session,
            get_skill_store(),
            tenant_id=principal.tenant_id,
            owner_id=principal.user_id,
            archive_bytes=archive,
            source=Path(file.filename or "upload.zip").name,
            packages_root=PACKAGES_ROOT,
            limits=limits,
        )
        await session.commit()
    except ValueError as exc:
        code = (
            status.HTTP_409_CONFLICT
            if str(exc).startswith("duplicate_package")
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(code, str(exc)) from exc
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="skill_package.import",
        resource="skill_package",
        detail={
            "package_id": package.package_id,
            "skill_id": package.skill_id,
            "content_hash": package.content_hash,
            "file_count": package.file_count,
        },
    )
    return {"imported": True, "package": _view(package, detail=True)}
