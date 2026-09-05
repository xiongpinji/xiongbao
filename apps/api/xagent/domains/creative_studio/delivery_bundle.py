"""Build deterministic, tenant-scoped short-drama delivery archives."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_OUTPUT_FIELDS = ("image_outputs", "video_outputs", "audio_outputs")


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _file_entry(path: str, payload: bytes) -> dict[str, object]:
    return {
        "path": path,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _is_within(path: Path, roots: Sequence[Path]) -> bool:
    resolved = path.resolve(strict=True)
    return any(resolved == root or root in resolved.parents for root in roots)


def _safe_basename(path: Path) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", path.name).strip(". ")
    return safe or "asset.bin"


def _reference(
    *,
    shot_id: str,
    kind: str,
    uri: str,
    classification: str,
) -> dict[str, str]:
    return {
        "shot_id": shot_id,
        "kind": kind,
        "uri": uri,
        "classification": classification,
    }


def _write_member(archive: ZipFile, path: str, payload: bytes) -> None:
    info = ZipInfo(path, date_time=_FIXED_ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(
        info,
        payload,
        compress_type=ZIP_DEFLATED,
        compresslevel=9,
    )


def build_delivery_bundle(
    production: dict[str, object],
    allowed_roots: Sequence[Path],
) -> bytes:
    """Return a deterministic ZIP without reading media outside ``allowed_roots``."""

    resolved_roots = tuple(Path(root).resolve() for root in allowed_roots)
    members: dict[str, bytes] = {
        "production.json": _json_bytes(production),
        "timeline.json": _json_bytes(production.get("timeline")),
    }
    references: list[dict[str, str]] = []
    placeholder_seen = False

    shots = production.get("shots")
    if not isinstance(shots, list):
        shots = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        shot_id = str(shot.get("shot_id") or "")
        for field in _OUTPUT_FIELDS:
            outputs = shot.get(field)
            if not isinstance(outputs, list):
                continue
            kind = field.removesuffix("_outputs")
            for value in outputs:
                uri = str(value)
                if uri.startswith("placeholder://"):
                    placeholder_seen = True
                    references.append(
                        _reference(
                            shot_id=shot_id,
                            kind=kind,
                            uri=uri,
                            classification="placeholder_fixture",
                        )
                    )
                    continue
                if "://" in uri:
                    references.append(
                        _reference(
                            shot_id=shot_id,
                            kind=kind,
                            uri=uri,
                            classification="external_uri",
                        )
                    )
                    continue

                candidate = Path(uri)
                try:
                    resolved = candidate.resolve(strict=True)
                except OSError:
                    references.append(
                        _reference(
                            shot_id=shot_id,
                            kind=kind,
                            uri=uri,
                            classification="missing_local_file",
                        )
                    )
                    continue
                if not _is_within(resolved, resolved_roots):
                    references.append(
                        _reference(
                            shot_id=shot_id,
                            kind=kind,
                            uri=uri,
                            classification="outside_allowed_roots",
                        )
                    )
                    continue
                if candidate.is_symlink() or not resolved.is_file():
                    references.append(
                        _reference(
                            shot_id=shot_id,
                            kind=kind,
                            uri=uri,
                            classification="not_regular_file",
                        )
                    )
                    continue

                payload = resolved.read_bytes()
                digest = hashlib.sha256(payload).hexdigest()
                member_path = f"assets/{digest[:12]}-{_safe_basename(resolved)}"
                existing = members.get(member_path)
                if existing is not None and existing != payload:
                    raise ValueError(f"delivery bundle member collision: {member_path}")
                members[member_path] = payload

    file_entries = [
        _file_entry(path, payload)
        for path, payload in sorted(members.items())
    ]
    manifest = {
        "schema_version": "1.0",
        "storyboard_id": str(production.get("storyboard_id") or ""),
        "production_status": str(production.get("status") or ""),
        "provider_classification": (
            "fixture_local" if placeholder_seen else "local_files"
        ),
        "external_provider_acceptance": "not_authorized",
        "files": file_entries,
        "references": references,
        "failures": production.get("failures", []),
    }
    members["manifest.json"] = _json_bytes(manifest)

    buffer = BytesIO()
    with ZipFile(buffer, mode="w") as archive:
        for path, payload in sorted(members.items()):
            _write_member(archive, path, payload)
    return buffer.getvalue()
