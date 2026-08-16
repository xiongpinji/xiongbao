from __future__ import annotations

import hashlib
import json
from pathlib import Path


SHA = "b" * 40


def _ref(root: Path, name: str, payload: bytes, *, source_sha: str = SHA) -> str:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    evidence = json.dumps(
        {"source_sha": source_sha, "payload": payload.decode("utf-8")},
        sort_keys=True,
    ).encode("utf-8")
    path.write_bytes(evidence)
    return f"{name} | sha256={hashlib.sha256(evidence).hexdigest()}"


def _packet(root: Path, *, source_sha: str = SHA) -> str:
    return "\n".join(
        [
            "# Target environment release packet",
            "",
            "- Release ID: v1.1.3-rc.1",
            f"- Source SHA: {source_sha}",
            "- Environment: customer-staging-a",
            "- Explicit authorization: approved-for-target-env",
            f"- Hosted CI evidence: {_ref(root, 'hosted-ci.json', b'ci')}",
            f"- Paid model evidence: {_ref(root, 'paid-model.json', b'model')}",
            f"- Signed desktop evidence: {_ref(root, 'signed-desktop.json', b'signed')}",
            f"- Backup evidence: {_ref(root, 'backup.json', b'backup')}",
            f"- Migration evidence: {_ref(root, 'migration.json', b'alembic')}",
            f"- Health evidence: {_ref(root, 'health.json', b'/health /ready')}",
            f"- Browser evidence: {_ref(root, 'browser.json', b'playwright')}",
            f"- Rollback evidence: {_ref(root, 'rollback.json', b'rollback')}",
            "- TL signoff: tech-lead / 2026-08-16",
            "- QA signoff: qa-owner / 2026-08-16",
            "- DevOps signoff: release-owner / 2026-08-16",
            "- Owner signoff: product-owner / 2026-08-16",
            "- Final disposition: approved-for-target-env",
            "",
        ]
    )


def test_target_env_gate_binds_sha_and_recomputes_evidence_hashes(tmp_path: Path) -> None:
    from scripts.target_env_release_gate import validate_packet

    packet = tmp_path / "packet.md"
    packet.write_text(_packet(tmp_path), encoding="utf-8")

    result = validate_packet(packet, evidence_root=tmp_path, source_sha=SHA)

    assert result["source_sha"] == SHA
    assert result["status"] == "passed"
    assert result["environment"] == "customer-staging-a"
    assert len(result["evidence"]) == 8


def test_target_env_gate_rejects_sha_mismatch_and_tampered_evidence(
    tmp_path: Path,
) -> None:
    from scripts.target_env_release_gate import TargetEnvGateError, validate_packet

    packet = tmp_path / "packet.md"
    packet.write_text(_packet(tmp_path, source_sha="c" * 40), encoding="utf-8")
    try:
        validate_packet(packet, evidence_root=tmp_path, source_sha=SHA)
    except TargetEnvGateError as exc:
        assert "source sha" in str(exc).lower()
    else:
        raise AssertionError("source SHA mismatch was accepted")

    packet.write_text(_packet(tmp_path), encoding="utf-8")
    (tmp_path / "health.json").write_text("tampered", encoding="utf-8")
    try:
        validate_packet(packet, evidence_root=tmp_path, source_sha=SHA)
    except TargetEnvGateError as exc:
        assert "sha256" in str(exc).lower()
    else:
        raise AssertionError("tampered evidence was accepted")


def test_target_env_gate_rejects_evidence_from_another_source_sha(
    tmp_path: Path,
) -> None:
    from scripts.target_env_release_gate import TargetEnvGateError, validate_packet

    packet = tmp_path / "packet.md"
    content = _packet(tmp_path)
    valid_health = next(
        line for line in content.splitlines() if line.startswith("- Health evidence:")
    )[19:]
    foreign_health = _ref(
        tmp_path,
        "health.json",
        b"foreign",
        source_sha="c" * 40,
    )
    packet.write_text(content.replace(valid_health, foreign_health), encoding="utf-8")

    try:
        validate_packet(packet, evidence_root=tmp_path, source_sha=SHA)
    except TargetEnvGateError as exc:
        assert "source sha" in str(exc).lower()
    else:
        raise AssertionError("foreign-SHA evidence was accepted")


def test_target_env_gate_rejects_placeholders_and_path_escape(tmp_path: Path) -> None:
    from scripts.target_env_release_gate import TargetEnvGateError, validate_packet

    packet = tmp_path / "packet.md"
    packet.write_text(_packet(tmp_path).replace("product-owner / 2026-08-16", "TBD"), encoding="utf-8")
    try:
        validate_packet(packet, evidence_root=tmp_path, source_sha=SHA)
    except TargetEnvGateError as exc:
        assert "owner signoff" in str(exc).lower()
    else:
        raise AssertionError("placeholder signoff was accepted")

    outside = tmp_path.parent / "outside-target-evidence.json"
    outside.write_bytes(b"outside")
    escaped = f"../{outside.name} | sha256={hashlib.sha256(b'outside').hexdigest()}"
    packet.write_text(
        _packet(tmp_path).replace(
            next(line for line in _packet(tmp_path).splitlines() if line.startswith("- Health evidence:"))[19:],
            escaped,
        ),
        encoding="utf-8",
    )
    try:
        validate_packet(packet, evidence_root=tmp_path, source_sha=SHA)
    except TargetEnvGateError as exc:
        assert "escaped" in str(exc).lower()
    else:
        raise AssertionError("escaped evidence path was accepted")
