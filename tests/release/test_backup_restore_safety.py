import hashlib
import json
from pathlib import Path

import pytest

from scripts import backup, restore


ROOT = Path(__file__).resolve().parents[2]


def test_backup_manifest_binds_project_collection_and_sha(tmp_path: Path) -> None:
    artifact = tmp_path / "postgres.dump"
    artifact.write_bytes(b"pg")

    manifest = backup.build_backup_manifest(
        output_root=tmp_path,
        compose_project="xagent-rollback-candidate-a1b2c3d4",
        source_sha="a1b2c3d4" + "a" * 32,
        qdrant_collection="xagent_memory_a1b2c3d4",
        qdrant_vector_size=256,
        artifacts=[artifact],
    )

    assert manifest["compose_project"] == "xagent-rollback-candidate-a1b2c3d4"
    assert manifest["qdrant_collection"] == "xagent_memory_a1b2c3d4"
    assert manifest["qdrant_vector_size"] == 256
    assert manifest["artifacts"][0]["sha256"] == hashlib.sha256(b"pg").hexdigest()


def test_backup_reads_vector_size_from_qdrant_collection(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "result": {
                    "config": {"params": {"vectors": {"size": 256}}}
                }
            }

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: Response())

    assert (
        backup.get_qdrant_vector_size(
            qdrant_url="http://qdrant:6333",
            collection="xagent_memory_a1b2c3d4",
        )
        == 256
    )


def test_backup_rejects_invalid_qdrant_vector_size(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "result": {
                    "config": {"params": {"vectors": {"size": 0}}}
                }
            }

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: Response())

    with pytest.raises(RuntimeError, match="vector size"):
        backup.get_qdrant_vector_size(
            qdrant_url="http://qdrant:6333",
            collection="xagent_memory_a1b2c3d4",
        )


def test_backup_rejects_generic_project_and_collection(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        backup.validate_scope("xagent-r2", "xagent_memory", "a" * 40, tmp_path)


def test_backup_rejects_the_webapi_project_even_for_the_same_sha(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="source SHA"):
        backup.validate_scope(
            "xagent-commercial-aaaaaaaa",
            "xagent_memory_aaaaaaaa",
            "a" * 40,
            tmp_path,
        )


def test_backup_output_must_be_inside_sha_rollback_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"

    with pytest.raises(ValueError, match="rollback"):
        backup.validate_scope(
            "xagent-rollback-candidate-aaaaaaaa",
            "xagent_memory_aaaaaaaa",
            "a" * 40,
            outside,
            repo_root=repo,
        )


def test_restore_requires_new_restore_project_and_collection() -> None:
    scope = restore.validate_restore_scope(
        compose_project="xagent-restore-a1b2c3d4",
        qdrant_collection="xagent_restore_a1b2c3d4",
        source_sha="a1b2c3d4" + "a" * 32,
    )

    assert scope.compose_project == "xagent-restore-a1b2c3d4"
    assert scope.qdrant_collection == "xagent_restore_a1b2c3d4"


def test_restore_source_has_no_qdrant_delete_call() -> None:
    source = (ROOT / "scripts/restore.py").read_text(encoding="utf-8")

    assert "httpx.delete" not in source
    assert "DELETE" not in source


def test_restore_manifest_output_accepts_rollback_evidence_root(
    tmp_path: Path,
) -> None:
    backup_root = tmp_path / "rollback" / "backup"
    backup_root.mkdir(parents=True)
    manifest = backup_root / "backup-manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    output = tmp_path / "rollback" / "restore-manifest.json"

    assert restore.validate_restore_manifest_output(manifest, output) == output.resolve()


def test_restore_manifest_output_rejects_path_outside_rollback_root(
    tmp_path: Path,
) -> None:
    backup_root = tmp_path / "rollback" / "backup"
    backup_root.mkdir(parents=True)
    manifest = backup_root / "backup-manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="rollback evidence root"):
        restore.validate_restore_manifest_output(
            manifest, tmp_path / "outside" / "restore-manifest.json"
        )


def test_restore_rejects_tampered_backup_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "postgres.dump"
    artifact.write_bytes(b"original")
    manifest = {
        "schema_version": "1.0",
        "source_sha": "a" * 40,
        "compose_project": "xagent-commercial-aaaaaaaa",
        "qdrant_collection": "xagent_memory_aaaaaaaa",
        "artifacts": [
            {
                "path": "postgres.dump",
                "size_bytes": len(b"original"),
                "sha256": hashlib.sha256(b"original").hexdigest(),
            }
        ],
    }
    manifest_path = tmp_path / "backup-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    artifact.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="size|sha256"):
        restore.load_and_verify_manifest(manifest_path)
