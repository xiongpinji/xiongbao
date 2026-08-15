#!/usr/bin/env python
"""Create a scoped, hash-verifiable backup for a commercial drill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")
PROJECT_PATTERN = re.compile(r"^xagent-rollback-candidate-[a-f0-9]{8}$")


def validate_scope(
    compose_project: str,
    qdrant_collection: str,
    source_sha: str,
    output: Path,
    *,
    repo_root: Path | None = None,
) -> Path:
    if SHA_PATTERN.fullmatch(source_sha) is None:
        raise ValueError("source SHA must be 40 lowercase hexadecimal characters")
    sha8 = source_sha[:8]
    if (
        PROJECT_PATTERN.fullmatch(compose_project) is None
        or compose_project != f"xagent-rollback-candidate-{sha8}"
    ):
        raise ValueError("compose project does not match the source SHA")
    if qdrant_collection != f"xagent_memory_{sha8}":
        raise ValueError("Qdrant collection does not match the source SHA")
    resolved_output = Path(output).resolve()
    if repo_root is not None:
        root = Path(repo_root).resolve(strict=True)
        rollback_root = (
            root / "output" / "commercial-delivery" / source_sha / "rollback"
        ).resolve()
        if resolved_output != rollback_root and rollback_root not in resolved_output.parents:
            raise ValueError("backup output must stay inside the SHA rollback root")
    return resolved_output


def _artifact_item(path: Path, root: Path) -> dict[str, object]:
    original = Path(path)
    if original.is_symlink():
        raise ValueError("backup artifact must not be a symlink")
    resolved = original.resolve(strict=True)
    if root not in resolved.parents:
        raise ValueError("backup artifact escaped the output root")
    payload = resolved.read_bytes()
    return {
        "path": resolved.relative_to(root).as_posix(),
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def build_backup_manifest(
    *,
    output_root: Path,
    compose_project: str,
    source_sha: str,
    qdrant_collection: str,
    qdrant_vector_size: int,
    artifacts: Sequence[Path],
) -> dict[str, object]:
    root = Path(output_root).resolve(strict=True)
    validate_scope(compose_project, qdrant_collection, source_sha, root)
    if not artifacts:
        raise ValueError("backup manifest requires artifacts")
    if (
        isinstance(qdrant_vector_size, bool)
        or not isinstance(qdrant_vector_size, int)
        or qdrant_vector_size <= 0
    ):
        raise ValueError("Qdrant vector size must be a positive integer")
    return {
        "schema_version": "1.0",
        "source_sha": source_sha,
        "compose_project": compose_project,
        "qdrant_collection": qdrant_collection,
        "qdrant_vector_size": qdrant_vector_size,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifacts": [_artifact_item(path, root) for path in artifacts],
    }


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomic(path: Path, value: object) -> None:
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_bytes_atomic(path, payload)


def backup_postgres(
    *,
    output: Path,
    compose_project: str,
    compose_file: Path,
    pg_user: str,
    pg_database: str,
    pg_url: str | None,
) -> Path:
    if pg_url and shutil.which("pg_dump"):
        subprocess.run(
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                pg_url,
                "--file",
                str(output),
            ],
            check=True,
            capture_output=True,
        )
    else:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                compose_project,
                "-f",
                str(compose_file),
                "exec",
                "-T",
                "postgres",
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--username",
                pg_user,
                "--dbname",
                pg_database,
            ],
            check=True,
            capture_output=True,
        )
        _write_bytes_atomic(output, result.stdout)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("Postgres backup is empty")
    return output


def backup_qdrant(*, qdrant_url: str, collection: str, output: Path) -> Path:
    import httpx

    created = httpx.post(
        f"{qdrant_url.rstrip('/')}/collections/{collection}/snapshots",
        timeout=60,
    )
    created.raise_for_status()
    snapshot_name = str(created.json().get("result", {}).get("name") or "")
    if not snapshot_name or "/" in snapshot_name or "\\" in snapshot_name:
        raise RuntimeError("Qdrant returned an invalid snapshot name")
    downloaded = httpx.get(
        f"{qdrant_url.rstrip('/')}/collections/{collection}/snapshots/{snapshot_name}",
        timeout=300,
    )
    downloaded.raise_for_status()
    _write_bytes_atomic(output, downloaded.content)
    if output.stat().st_size == 0:
        raise RuntimeError("Qdrant snapshot is empty")
    return output


def get_qdrant_vector_size(*, qdrant_url: str, collection: str) -> int:
    import httpx

    response = httpx.get(
        f"{qdrant_url.rstrip('/')}/collections/{collection}", timeout=30
    )
    response.raise_for_status()
    try:
        vector_size = response.json()["result"]["config"]["params"]["vectors"][
            "size"
        ]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Qdrant collection has no single vector size") from exc
    if (
        isinstance(vector_size, bool)
        or not isinstance(vector_size, int)
        or vector_size <= 0
    ):
        raise RuntimeError("Qdrant collection returned an invalid vector size")
    return vector_size


def backup_audit(*, api_url: str, token: str, output: Path) -> Path:
    import httpx

    response = httpx.get(
        f"{api_url.rstrip('/')}/api/v1/audit/export",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    response.raise_for_status()
    _write_bytes_atomic(output, response.content)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-project", required=True)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--qdrant-collection", required=True)
    parser.add_argument("--qdrant-url", required=True)
    parser.add_argument("--pg-url")
    parser.add_argument("--pg-user", default="xagent")
    parser.add_argument("--pg-database", default="xagent")
    parser.add_argument("--api-url")
    parser.add_argument("--token")
    parser.add_argument("--audit-file", type=Path)
    parser.add_argument("--short-drama-bundle", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    output_root = validate_scope(
        args.compose_project,
        args.qdrant_collection,
        args.source_sha,
        args.output,
        repo_root=repo_root,
    )
    compose_file = args.compose_file.resolve(strict=True)
    if repo_root not in compose_file.parents:
        raise ValueError("compose file must be inside the repository")
    output_root.mkdir(parents=True, exist_ok=True)
    if bool(args.api_url) != bool(args.token):
        raise ValueError("audit backup requires both api URL and token")

    qdrant_vector_size = get_qdrant_vector_size(
        qdrant_url=args.qdrant_url,
        collection=args.qdrant_collection,
    )
    artifacts = [
        backup_postgres(
            output=output_root / "postgres.dump",
            compose_project=args.compose_project,
            compose_file=compose_file,
            pg_user=args.pg_user,
            pg_database=args.pg_database,
            pg_url=args.pg_url,
        ),
        backup_qdrant(
            qdrant_url=args.qdrant_url,
            collection=args.qdrant_collection,
            output=output_root / "qdrant.snapshot",
        ),
    ]
    if args.api_url and args.token:
        artifacts.append(
            backup_audit(
                api_url=args.api_url,
                token=args.token,
                output=output_root / "audit.json",
            )
        )
    if args.audit_file:
        if args.api_url or args.token:
            raise ValueError("use either an audit file or API audit parameters")
        audit_source = args.audit_file.resolve(strict=True)
        if not audit_source.is_file() or audit_source.is_symlink():
            raise ValueError("audit export must be a regular file")
        audit_destination = output_root / "audit.json"
        shutil.copyfile(audit_source, audit_destination)
        artifacts.append(audit_destination)
    for index, source in enumerate(args.short_drama_bundle, start=1):
        resolved = source.resolve(strict=True)
        if not resolved.is_file() or resolved.is_symlink():
            raise ValueError("short-drama bundle must be a regular file")
        destination = output_root / f"short-drama-{index}.zip"
        shutil.copyfile(resolved, destination)
        artifacts.append(destination)

    manifest = build_backup_manifest(
        output_root=output_root,
        compose_project=args.compose_project,
        source_sha=args.source_sha,
        qdrant_collection=args.qdrant_collection,
        qdrant_vector_size=qdrant_vector_size,
        artifacts=artifacts,
    )
    manifest_path = output_root / "backup-manifest.json"
    _write_json_atomic(manifest_path, manifest)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
