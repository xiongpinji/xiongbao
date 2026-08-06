"""Skill Package 安全解包、受控存储与租户仓储。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import stat
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any
from zipfile import BadZipFile, ZipFile, ZipInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.skills.importer import candidate_from_skillmd, parse_skillmd
from xagent.infra.models.skill_package import SkillPackageORM

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PACKAGES_ROOT = _PROJECT_ROOT / "data" / "skill-packages"


@dataclass(frozen=True)
class SkillPackageLimits:
    max_files: int = 100
    max_file_bytes: int = 2 * 1024 * 1024
    max_total_bytes: int = 20 * 1024 * 1024
    max_archive_bytes: int = 20 * 1024 * 1024


@dataclass(frozen=True)
class SkillPackageRecord:
    package_id: str
    skill_id: str
    tenant_id: str
    owner_id: str
    name: str
    version: str
    content_hash: str
    manifest: dict[str, Any]
    frontmatter: dict[str, Any]
    body: str
    root_path: str
    source: str
    file_count: int
    total_size: int
    imported_at: datetime


def _record(row: SkillPackageORM) -> SkillPackageRecord:
    imported_at = row.imported_at
    if imported_at.tzinfo is None:
        imported_at = imported_at.replace(tzinfo=UTC)
    return SkillPackageRecord(
        package_id=row.package_id,
        skill_id=row.skill_id,
        tenant_id=row.tenant_id,
        owner_id=row.owner_id,
        name=row.name,
        version=row.version,
        content_hash=row.content_hash,
        manifest=json.loads(row.manifest_json),
        frontmatter=json.loads(row.frontmatter_json),
        body=row.body,
        root_path=row.root_path,
        source=row.source,
        file_count=row.file_count,
        total_size=row.total_size,
        imported_at=imported_at,
    )


def _safe_parts(name: str) -> tuple[str, ...]:
    if not name or "\\" in name or re.match(r"^[A-Za-z]:", name):
        raise ValueError(f"unsafe_path: {name}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe_path: {name}")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
    }
    for part in path.parts:
        stem = part.split(".", 1)[0].upper()
        if ":" in part or part.endswith((" ", ".")) or stem in reserved:
            raise ValueError(f"unsafe_path: {name}")
    return path.parts


def _path_key(relative: str) -> str:
    return unicodedata.normalize("NFC", relative).casefold()


def _is_symlink(info: ZipInfo) -> bool:
    return info.create_system == 3 and stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def _strip_single_wrapper(paths: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    if ("SKILL.md",) in paths:
        return paths
    roots = {parts[0] for parts in paths}
    if len(roots) != 1:
        raise ValueError("missing_skillmd")
    stripped = [parts[1:] for parts in paths]
    if not all(stripped) or ("SKILL.md",) not in stripped:
        raise ValueError("missing_skillmd")
    return stripped


def _read_zip_entries(
    archive_bytes: bytes, limits: SkillPackageLimits
) -> dict[str, bytes]:
    if len(archive_bytes) > limits.max_archive_bytes:
        raise ValueError("archive_size_limit")
    try:
        with ZipFile(BytesIO(archive_bytes)) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if len(infos) > limits.max_files:
                raise ValueError("file_count_limit")
            raw_paths: list[tuple[str, ...]] = []
            for info in infos:
                if _is_symlink(info):
                    raise ValueError(f"symlink_not_allowed: {info.filename}")
                if info.file_size > limits.max_file_bytes:
                    raise ValueError(f"file_size_limit: {info.filename}")
                raw_paths.append(_safe_parts(info.filename))
            paths = _strip_single_wrapper(raw_paths)
            entries: dict[str, bytes] = {}
            total = 0
            seen: set[str] = set()
            for info, parts in zip(infos, paths, strict=True):
                relative = "/".join(parts)
                key = _path_key(relative)
                if key in seen:
                    raise ValueError(f"duplicate_path: {relative}")
                seen.add(key)
                chunks: list[bytes] = []
                member_size = 0
                with archive.open(info) as member:
                    while chunk := member.read(64 * 1024):
                        member_size += len(chunk)
                        if member_size > limits.max_file_bytes:
                            raise ValueError(f"file_size_limit: {relative}")
                        chunks.append(chunk)
                content = b"".join(chunks)
                total += len(content)
                if total > limits.max_total_bytes:
                    raise ValueError("total_size_limit")
                entries[relative] = content
    except BadZipFile as exc:
        raise ValueError("invalid_zip") from exc
    if "SKILL.md" not in entries:
        raise ValueError("missing_skillmd")
    return entries


def _content_hash(entries: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for path in sorted(entries):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(entries[path])
        digest.update(b"\0")
    return digest.hexdigest()


def _manifest(entries: dict[str, bytes]) -> dict[str, Any]:
    return {
        "files": [
            {
                "path": path,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for path, content in sorted(entries.items())
        ]
    }


def _materialize_entries(
    packages_root: Path, package_id: str, entries: dict[str, bytes]
) -> Path:
    packages_root.mkdir(parents=True, exist_ok=True)
    final_root = packages_root / package_id
    with TemporaryDirectory(prefix=".import-", dir=packages_root) as temp:
        temp_root = Path(temp)
        for relative, content in entries.items():
            target = temp_root.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        temp_root.replace(final_root)
    return final_root


def _read_directory_entries(
    source_dir: Path, limits: SkillPackageLimits
) -> dict[str, bytes]:
    if not source_dir.is_dir() or source_dir.is_symlink():
        raise ValueError("invalid_source_directory")
    entries: dict[str, bytes] = {}
    seen: set[str] = set()
    total = 0
    for path in sorted(source_dir.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink_not_allowed: {path.name}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"non_regular_file: {path.name}")
        if len(entries) >= limits.max_files:
            raise ValueError("file_count_limit")
        relative = path.relative_to(source_dir).as_posix()
        _safe_parts(relative)
        key = _path_key(relative)
        if key in seen:
            raise ValueError(f"duplicate_path: {relative}")
        seen.add(key)
        size = path.stat().st_size
        if size > limits.max_file_bytes:
            raise ValueError(f"file_size_limit: {relative}")
        content = path.read_bytes()
        total += len(content)
        if total > limits.max_total_bytes:
            raise ValueError("total_size_limit")
        entries[relative] = content
    if "SKILL.md" not in entries:
        raise ValueError("missing_skillmd")
    return entries


async def import_skill_package_zip(
    session: AsyncSession,
    store: Any,
    *,
    tenant_id: str,
    owner_id: str,
    archive_bytes: bytes,
    source: str,
    packages_root: Path = DEFAULT_PACKAGES_ROOT,
    limits: SkillPackageLimits | None = None,
) -> SkillPackageRecord:
    limits = limits or SkillPackageLimits()
    entries = await asyncio.to_thread(_read_zip_entries, archive_bytes, limits)
    return await _import_entries(
        session,
        store,
        tenant_id=tenant_id,
        owner_id=owner_id,
        entries=entries,
        source=source,
        packages_root=packages_root,
    )


async def _import_entries(
    session: AsyncSession,
    store: Any,
    *,
    tenant_id: str,
    owner_id: str,
    entries: dict[str, bytes],
    source: str,
    packages_root: Path,
) -> SkillPackageRecord:
    content_hash = _content_hash(entries)
    duplicate = await session.scalar(
        select(SkillPackageORM.package_id).where(
            SkillPackageORM.tenant_id == tenant_id,
            SkillPackageORM.content_hash == content_hash,
        )
    )
    if duplicate is not None:
        raise ValueError(f"duplicate_package: {duplicate}")

    try:
        skillmd = entries["SKILL.md"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid_skillmd_encoding") from exc
    parsed = parse_skillmd(skillmd)
    candidate = candidate_from_skillmd(skillmd, source)
    candidate["system_prompt_hint"] = parsed["body"]
    goal = f"{candidate['name']} {candidate['description']} {' '.join(candidate['tags'])}"
    accepted, reason = store.gate_candidate(candidate, goal)
    if not accepted:
        raise ValueError(f"quality_gate: {reason}")

    package_id = uuid.uuid4().hex
    final_root = await asyncio.to_thread(
        _materialize_entries, packages_root, package_id, entries
    )

    try:
        skill = store.create_skill(
            name=candidate["name"],
            description=candidate["description"],
            trigger_pattern=candidate["trigger_pattern"],
            steps=[],
            system_prompt_hint=candidate["system_prompt_hint"],
            tags=candidate["tags"],
            source="package_import",
            source_task=source,
        )
    except Exception:
        await asyncio.to_thread(shutil.rmtree, final_root)
        raise
    frontmatter = parsed["frontmatter"]
    row = SkillPackageORM(
        package_id=package_id,
        skill_id=skill.skill_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        name=candidate["name"],
        version=str(frontmatter.get("version") or "1"),
        content_hash=content_hash,
        manifest_json=json.dumps(_manifest(entries), ensure_ascii=False),
        frontmatter_json=json.dumps(frontmatter, ensure_ascii=False, default=str),
        body=parsed["body"],
        root_path=str(final_root.resolve()),
        source=source[:512],
        file_count=len(entries),
        total_size=sum(len(content) for content in entries.values()),
    )
    session.add(row)
    try:
        await session.flush()
    except Exception:
        store.delete(skill.skill_id)
        await asyncio.to_thread(shutil.rmtree, final_root)
        raise
    return _record(row)


async def import_skill_package_directory(
    session: AsyncSession,
    store: Any,
    *,
    tenant_id: str,
    owner_id: str,
    source_dir: Path,
    source: str,
    packages_root: Path = DEFAULT_PACKAGES_ROOT,
    limits: SkillPackageLimits | None = None,
) -> SkillPackageRecord:
    limits = limits or SkillPackageLimits()
    entries = await asyncio.to_thread(_read_directory_entries, source_dir, limits)
    return await _import_entries(
        session,
        store,
        tenant_id=tenant_id,
        owner_id=owner_id,
        entries=entries,
        source=source,
        packages_root=packages_root,
    )


async def list_skill_packages(
    session: AsyncSession, tenant_id: str
) -> list[SkillPackageRecord]:
    rows = await session.scalars(
        select(SkillPackageORM)
        .where(SkillPackageORM.tenant_id == tenant_id)
        .order_by(SkillPackageORM.imported_at.desc())
    )
    return [_record(row) for row in rows]


async def get_skill_package(
    session: AsyncSession, tenant_id: str, package_id: str
) -> SkillPackageRecord | None:
    row = await session.scalar(
        select(SkillPackageORM).where(
            SkillPackageORM.tenant_id == tenant_id,
            SkillPackageORM.package_id == package_id,
        )
    )
    return _record(row) if row is not None else None
