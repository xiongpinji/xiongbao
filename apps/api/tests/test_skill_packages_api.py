"""Skill Package 租户 API 与上传门禁。"""

from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from xagent.core.skills import SkillStore
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.jwt_auth import create_access_token
from xagent.infra.db import Base, get_engine
from xagent.main import create_app


def _archive(name: str = "api-package") -> bytes:
    skillmd = f"""---
name: {name}
description: Use when validating a tenant-scoped package import through the API.
version: 1.2.0
metadata:
  tags: [package, validation]
---
# API Package

Read references/guide.md and return the complete validation result.
{"validate every release artifact before publication. " * 30}
"""
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("SKILL.md", skillmd)
        archive.writestr("references/guide.md", "tenant-safe guide")
        archive.writestr("scripts/check.py", "raise SystemExit('never execute')")
    return output.getvalue()


def _headers(tenant_id: str) -> dict[str, str]:
    token = create_access_token(
        user_id=f"admin-{tenant_id}", tenant_id=tenant_id, roles=["admin"]
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def package_client(tmp_path, monkeypatch):
    import xagent.core.skills as skills_mod

    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = SkillStore(tmp_path / "skills")
    monkeypatch.setattr(skills_mod, "_store", store)
    monkeypatch.setenv("XAGENT_SKILL_PACKAGES_ROOT", str(tmp_path / "packages"))
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, store


async def test_zip_upload_list_detail_and_tenant_isolation(package_client) -> None:
    client, store = package_client
    response = await client.post(
        "/api/v1/skill-packages/import",
        files={"file": ("api-package.zip", _archive(), "application/zip")},
        headers=_headers("tenant-package-a"),
    )
    assert response.status_code == 201
    package = response.json()["package"]
    assert package["name"] == "api-package"
    assert package["version"] == "1.2.0"
    assert package["file_count"] == 3
    assert len(package["content_hash"]) == 64
    assert "root_path" not in package
    events = get_audit_log().list("tenant-package-a")
    assert events[-1].action == "skill_package.import"
    assert events[-1].detail["package_id"] == package["package_id"]

    listed = await client.get(
        "/api/v1/skill-packages", headers=_headers("tenant-package-a")
    )
    assert [item["package_id"] for item in listed.json()["packages"]] == [
        package["package_id"]
    ]
    assert "body" not in listed.json()["packages"][0]

    detail = await client.get(
        f"/api/v1/skill-packages/{package['package_id']}",
        headers=_headers("tenant-package-a"),
    )
    assert detail.status_code == 200
    assert "complete validation result" in detail.json()["body"]
    assert {item["path"] for item in detail.json()["manifest"]["files"]} == {
        "SKILL.md",
        "references/guide.md",
        "scripts/check.py",
    }

    other_list = await client.get(
        "/api/v1/skill-packages", headers=_headers("tenant-package-b")
    )
    assert other_list.json()["packages"] == []
    other_detail = await client.get(
        f"/api/v1/skill-packages/{package['package_id']}",
        headers=_headers("tenant-package-b"),
    )
    assert other_detail.status_code == 404
    assert store.match("api package", tenant_id="tenant-package-b") == []
    other_skills = await client.get(
        "/api/v1/skills", headers=_headers("tenant-package-b")
    )
    assert package["skill_id"] not in {
        skill["skill_id"] for skill in other_skills.json()["skills"]
    }
    own_skills = await client.get(
        "/api/v1/skills", headers=_headers("tenant-package-a")
    )
    own_skill = next(
        skill
        for skill in own_skills.json()["skills"]
        if skill["skill_id"] == package["skill_id"]
    )
    assert own_skill["system_prompt_truncated"] is True
    assert len(own_skill["system_prompt_hint"]) == 500
    full_skill = await client.get(
        f"/api/v1/skills/{package['skill_id']}",
        headers=_headers("tenant-package-a"),
    )
    assert len(full_skill.json()["system_prompt_hint"]) > 500


async def test_upload_rejects_path_traversal(package_client) -> None:
    client, _ = package_client
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("../SKILL.md", "unsafe")
    response = await client.post(
        "/api/v1/skill-packages/import",
        files={"file": ("unsafe.zip", output.getvalue(), "application/zip")},
        headers=_headers("tenant-package-a"),
    )
    assert response.status_code == 422
    assert "unsafe_path" in response.json()["detail"]


async def test_commit_failure_removes_package_files_and_runtime_skill(
    package_client, tmp_path, monkeypatch
) -> None:
    client, store = package_client

    async def fail_commit(_session) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        await client.post(
            "/api/v1/skill-packages/import",
            files={
                "file": (
                    "commit-failure.zip",
                    _archive("commit-failure"),
                    "application/zip",
                )
            },
            headers=_headers("tenant-package-commit-failure"),
        )

    assert store.match("commit failure", tenant_id="tenant-package-commit-failure") == []
    packages_root = tmp_path / "packages"
    assert not packages_root.exists() or list(packages_root.iterdir()) == []
