#!/usr/bin/env python
"""Restore a verified commercial backup into a new isolated target."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")
PROJECT_PATTERN = re.compile(
    r"^xagent-restore-(?P<sha>[a-f0-9]{8})-(?P<nonce>[a-f0-9]{8})$"
)
QDRANT_PATTERN = re.compile(
    r"^xagent_restore_(?P<sha>[a-f0-9]{8})_(?P<nonce>[a-f0-9]{8})$"
)


@dataclass(frozen=True)
class RestoreScope:
    compose_project: str
    qdrant_collection: str
    source_sha: str


def validate_restore_scope(
    *, compose_project: str, qdrant_collection: str, source_sha: str
) -> RestoreScope:
    if SHA_PATTERN.fullmatch(source_sha) is None:
        raise ValueError("source SHA must be 40 lowercase hexadecimal characters")
    sha8 = source_sha[:8]
    project_match = PROJECT_PATTERN.fullmatch(compose_project)
    collection_match = QDRANT_PATTERN.fullmatch(qdrant_collection)
    if project_match is None or project_match.group("sha") != sha8:
        raise ValueError("restore project does not match the source SHA")
    if collection_match is None or collection_match.group("sha") != sha8:
        raise ValueError("restore collection does not match the source SHA")
    if project_match.group("nonce") != collection_match.group("nonce"):
        raise ValueError("restore project and collection run nonce do not match")
    return RestoreScope(compose_project, qdrant_collection, source_sha)


def load_and_verify_manifest(path: Path) -> tuple[dict[str, object], dict[str, Path]]:
    manifest_path = Path(path).resolve(strict=True)
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.0":
        raise ValueError("unsupported backup manifest schema")
    source_sha = str(manifest.get("source_sha") or "")
    if SHA_PATTERN.fullmatch(source_sha) is None:
        raise ValueError("backup manifest has an invalid source SHA")
    artifacts: dict[str, Path] = {}
    for item in manifest.get("artifacts", []):
        relative = Path(str(item["path"]))
        original = root / relative
        if original.is_symlink():
            raise ValueError("backup artifact must not be a symlink")
        candidate = original.resolve(strict=True)
        if root not in candidate.parents or not candidate.is_file():
            raise ValueError("backup artifact escaped the manifest root")
        payload = candidate.read_bytes()
        if len(payload) != int(item["size_bytes"]):
            raise ValueError(f"backup artifact size mismatch: {candidate.name}")
        if hashlib.sha256(payload).hexdigest() != str(item["sha256"]):
            raise ValueError(f"backup artifact sha256 mismatch: {candidate.name}")
        artifacts[candidate.name] = candidate
    if "postgres.dump" not in artifacts or "qdrant.snapshot" not in artifacts:
        raise ValueError("backup manifest is missing required database artifacts")
    return manifest, artifacts


def validate_restore_manifest_output(manifest_path: Path, output: Path) -> Path:
    resolved_manifest = Path(manifest_path).resolve(strict=True)
    rollback_root = resolved_manifest.parent.parent
    resolved_output = Path(output).resolve()
    if rollback_root not in resolved_output.parents:
        raise ValueError("restore manifest must stay inside the rollback evidence root")
    if resolved_output == resolved_manifest:
        raise ValueError("restore manifest must not overwrite the backup manifest")
    return resolved_output


def _compose_command(project: str, compose_file: Path, *args: str) -> list[str]:
    return ["docker", "compose", "-p", project, "-f", str(compose_file), *args]


def validate_compose_labels(project: str, compose_file: Path) -> None:
    listed = subprocess.run(
        _compose_command(project, compose_file, "ps", "-q"),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    container_ids = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
    if not container_ids:
        raise ValueError("restore project has no running containers")
    for container_id in container_ids:
        inspected = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                '{{ index .Config.Labels "com.docker.compose.project" }}',
                container_id,
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if inspected.stdout.strip() != project:
            raise ValueError("restore container label does not match target project")


def ensure_postgres_empty(
    project: str, compose_file: Path, pg_user: str, pg_database: str
) -> None:
    query = (
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema NOT IN ('pg_catalog','information_schema');"
    )
    result = subprocess.run(
        _compose_command(
            project,
            compose_file,
            "exec",
            "-T",
            "postgres",
            "psql",
            "--username",
            pg_user,
            "--dbname",
            pg_database,
            "--tuples-only",
            "--no-align",
            "--command",
            query,
        ),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.stdout.strip() != "0":
        raise ValueError("target Postgres is not empty")


def restore_postgres(
    *,
    project: str,
    compose_file: Path,
    pg_user: str,
    pg_database: str,
    dump_path: Path,
) -> int:
    result = subprocess.run(
        _compose_command(
            project,
            compose_file,
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            "--username",
            pg_user,
            "--dbname",
            pg_database,
        ),
        input=dump_path.read_bytes(),
        check=True,
        capture_output=True,
    )
    return result.returncode


def restore_qdrant(
    *, qdrant_url: str, collection: str, vector_size: int, snapshot: Path
) -> int:
    import httpx

    base = qdrant_url.rstrip("/")
    existing = httpx.get(f"{base}/collections/{collection}", timeout=30)
    if existing.status_code != 404:
        raise ValueError("target Qdrant collection already exists")
    created = httpx.put(
        f"{base}/collections/{collection}",
        json={"vectors": {"size": vector_size, "distance": "Cosine"}},
        timeout=30,
    )
    created.raise_for_status()
    with snapshot.open("rb") as stream:
        uploaded = httpx.post(
            f"{base}/collections/{collection}/snapshots/upload",
            files={"snapshot": stream},
            timeout=300,
        )
    uploaded.raise_for_status()
    return uploaded.status_code


def _write_json_atomic(path: Path, value: object) -> None:
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target-project", required=True)
    parser.add_argument("--target-pg-url", required=True)
    parser.add_argument("--target-qdrant-url", required=True)
    parser.add_argument("--target-qdrant-collection", required=True)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--pg-user", default="xagent")
    parser.add_argument("--pg-database", default="xagent")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve(strict=True)
    manifest, artifacts = load_and_verify_manifest(manifest_path)
    source_sha = str(manifest["source_sha"])
    scope = validate_restore_scope(
        compose_project=args.target_project,
        qdrant_collection=args.target_qdrant_collection,
        source_sha=source_sha,
    )
    parsed_pg_url = urlparse(args.target_pg_url)
    if parsed_pg_url.scheme not in {"postgres", "postgresql"} or not parsed_pg_url.path:
        raise ValueError("target Postgres URL is invalid")
    output = validate_restore_manifest_output(
        manifest_path,
        args.output or manifest_path.with_name("restore-manifest.json"),
    )
    compose_file = args.compose_file.resolve(strict=True)
    validate_compose_labels(scope.compose_project, compose_file)
    ensure_postgres_empty(
        scope.compose_project, compose_file, args.pg_user, args.pg_database
    )

    pg_exit = restore_postgres(
        project=scope.compose_project,
        compose_file=compose_file,
        pg_user=args.pg_user,
        pg_database=args.pg_database,
        dump_path=artifacts["postgres.dump"],
    )
    qdrant_status = restore_qdrant(
        qdrant_url=args.target_qdrant_url,
        collection=scope.qdrant_collection,
        vector_size=int(manifest.get("qdrant_vector_size", 1536)),
        snapshot=artifacts["qdrant.snapshot"],
    )
    backup_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    _write_json_atomic(
        output,
        {
            "schema_version": "1.0",
            "source_sha": source_sha,
            "source_backup_sha256": backup_hash,
            "target_project": scope.compose_project,
            "target_qdrant_collection": scope.qdrant_collection,
            "postgres_restore_exit_code": pg_exit,
            "qdrant_restore_status": qdrant_status,
            "finished_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        },
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
