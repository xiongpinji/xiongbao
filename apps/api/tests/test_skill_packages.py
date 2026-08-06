"""完整 Skill Package 的持久化与安全导入。"""

from __future__ import annotations

import stat
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from xagent.core.skills import SkillStore
from xagent.domains.skill_packages import (
    SkillPackageLimits,
    get_skill_package,
    import_skill_package_directory,
    import_skill_package_zip,
    list_skill_packages,
)
from xagent.infra.db import Base


def _skillmd(body: str = "") -> str:
    procedure = body or "1. Read references/checklist.md\n2. Produce an evidence report"
    return f"""---
name: release-audit
description: Use when auditing a Web API release before publication.
version: 2.1.0
metadata:
  tags: [release, audit]
---
# Release Audit

## Procedure
{procedure}
"""


def _zip(files: dict[str, str | bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


@pytest.fixture
async def package_env(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'packages.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield sessions, SkillStore(tmp_path / "skills"), tmp_path / "package-roots"
    await engine.dispose()


async def test_zip_import_preserves_complete_package_and_is_tenant_isolated(
    package_env,
) -> None:
    sessions, store, packages_root = package_env
    long_body = "verify evidence\n" * 400
    archive = _zip(
        {
            "release-audit/SKILL.md": _skillmd(long_body),
            "release-audit/references/checklist.md": "# Checklist\n- migration\n",
            "release-audit/scripts/audit.py": "raise RuntimeError('must not execute')\n",
            "release-audit/assets/template.txt": "evidence template",
        }
    )

    async with sessions() as session:
        package = await import_skill_package_zip(
            session,
            store,
            tenant_id="tenant-a",
            owner_id="owner-a",
            archive_bytes=archive,
            source="release-audit.zip",
            packages_root=packages_root,
        )
        await session.commit()

    assert package.name == "release-audit"
    assert package.version == "2.1.0"
    assert len(package.content_hash) == 64
    assert package.file_count == 4
    assert {item["path"] for item in package.manifest["files"]} == {
        "SKILL.md",
        "references/checklist.md",
        "scripts/audit.py",
        "assets/template.txt",
    }
    root = Path(package.root_path)
    assert (root / "SKILL.md").read_text(encoding="utf-8") == _skillmd(long_body)
    assert (root / "references" / "checklist.md").is_file()
    assert not (packages_root / "executed.marker").exists()
    skill = store.get(package.skill_id)
    assert skill is not None
    assert long_body.strip() in skill.system_prompt_hint
    assert len(skill.system_prompt_hint) > 3000

    async with sessions() as session:
        assert await get_skill_package(session, "tenant-b", package.package_id) is None
        assert await list_skill_packages(session, "tenant-b") == []
        restored = await get_skill_package(session, "tenant-a", package.package_id)
    assert restored is not None
    assert restored.manifest == package.manifest


@pytest.mark.parametrize(
    ("files", "reason"),
    [
        ({"../SKILL.md": _skillmd()}, "unsafe_path"),
        ({"C:/SKILL.md": _skillmd()}, "unsafe_path"),
        ({"SKILL.md": _skillmd(), "assets/file.txt:payload": "x"}, "unsafe_path"),
        ({"SKILL.md": _skillmd(), "skill.md": _skillmd()}, "duplicate_path"),
    ],
)
async def test_zip_import_rejects_unsafe_or_duplicate_paths(
    package_env, files, reason
) -> None:
    sessions, store, packages_root = package_env
    async with sessions() as session:
        with pytest.raises(ValueError, match=reason):
            await import_skill_package_zip(
                session,
                store,
                tenant_id="tenant-a",
                owner_id="owner-a",
                archive_bytes=_zip(files),
                source="unsafe.zip",
                packages_root=packages_root,
            )
    assert not packages_root.exists() or list(packages_root.iterdir()) == []


async def test_zip_import_rejects_symlink(package_env) -> None:
    sessions, store, packages_root = package_env
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("SKILL.md", _skillmd())
        link = ZipInfo("references/escape")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "../../outside")

    async with sessions() as session:
        with pytest.raises(ValueError, match="symlink_not_allowed"):
            await import_skill_package_zip(
                session,
                store,
                tenant_id="tenant-a",
                owner_id="owner-a",
                archive_bytes=output.getvalue(),
                source="symlink.zip",
                packages_root=packages_root,
            )


async def test_zip_import_enforces_file_count_and_total_size(package_env) -> None:
    sessions, store, packages_root = package_env
    archive = _zip({"SKILL.md": _skillmd(), "references/a.md": "12345"})
    async with sessions() as session:
        with pytest.raises(ValueError, match="file_count_limit"):
            await import_skill_package_zip(
                session,
                store,
                tenant_id="tenant-a",
                owner_id="owner-a",
                archive_bytes=archive,
                source="too-many.zip",
                packages_root=packages_root,
                limits=SkillPackageLimits(max_files=1),
            )
        with pytest.raises(ValueError, match="total_size_limit"):
            await import_skill_package_zip(
                session,
                store,
                tenant_id="tenant-a",
                owner_id="owner-a",
                archive_bytes=archive,
                source="too-large.zip",
                packages_root=packages_root,
                limits=SkillPackageLimits(max_total_bytes=10),
            )


async def test_directory_import_preserves_files_and_rejects_symlink(
    package_env, tmp_path: Path
) -> None:
    sessions, store, packages_root = package_env
    source = tmp_path / "source-skill"
    (source / "references").mkdir(parents=True)
    (source / "SKILL.md").write_text(_skillmd(), encoding="utf-8")
    (source / "references" / "guide.md").write_text("guide", encoding="utf-8")

    async with sessions() as session:
        package = await import_skill_package_directory(
            session,
            store,
            tenant_id="tenant-directory",
            owner_id="owner-directory",
            source_dir=source,
            source="local/source-skill",
            packages_root=packages_root,
        )
        await session.commit()
    assert package.file_count == 2
    assert (Path(package.root_path) / "references" / "guide.md").read_text() == "guide"

    unsafe_source = tmp_path / "unsafe-source"
    unsafe_source.mkdir()
    (unsafe_source / "SKILL.md").write_text(_skillmd("another procedure"), encoding="utf-8")
    link = unsafe_source / "references"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("当前 Windows 环境不允许创建测试符号链接")
    async with sessions() as session:
        with pytest.raises(ValueError, match="symlink_not_allowed"):
            await import_skill_package_directory(
                session,
                store,
                tenant_id="tenant-directory",
                owner_id="owner-directory",
                source_dir=unsafe_source,
                source="local/unsafe-source",
                packages_root=packages_root,
            )
