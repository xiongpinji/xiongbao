import hashlib
import json
from pathlib import Path

import pytest

from scripts.commercial_delivery_gate import GateError, verify_evidence


GATE_DIRECTORIES = {
    "commercial_kernel": "kernel",
    "webapi": "webapi",
    "short_drama": "short-drama",
    "desktop": "desktop",
    "rollback": "rollback",
}


def _write_gate(root: Path, gate: str, source_sha: str) -> None:
    directory = root / GATE_DIRECTORIES[gate]
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / "artifact.bin"
    artifact.write_bytes(f"{gate}-artifact".encode())
    payload = artifact.read_bytes()
    evidence = {
        "schema_version": "1.0",
        "gate": gate,
        "repository": "xagent",
        "branch": "codex/commercial-delivery-20260815",
        "source_sha": source_sha,
        "dirty": False,
        "started_at": "2026-08-15T00:00:00Z",
        "finished_at": "2026-08-15T00:01:00Z",
        "tools": {"python": "3.11.9"},
        "environment": {"os": "Windows"},
        "commands": [
            {
                "command": "verify",
                "exit_code": 0,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
            }
        ],
        "artifacts": [
            {
                "path": "artifact.bin",
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
        "status": "passed",
        "classification": "candidate_local",
        "authorizations": {
            "remote_release": "not_authorized",
            "production_deployment": "not_authorized",
            "paid_provider_acceptance": "not_authorized",
            "customer_production_acceptance": "not_authorized",
        },
    }
    (directory / "gate.json").write_text(json.dumps(evidence), encoding="utf-8")


def _write_all_gates(root: Path, source_sha: str) -> None:
    for gate in GATE_DIRECTORIES:
        _write_gate(root, gate, source_sha)


def test_verify_requires_all_five_gates(tmp_path: Path) -> None:
    _write_gate(tmp_path, "commercial_kernel", "a" * 40)

    with pytest.raises(GateError, match="missing gates"):
        verify_evidence(tmp_path, "a" * 40)


def test_verify_rejects_sha_and_artifact_drift(tmp_path: Path) -> None:
    _write_all_gates(tmp_path, "a" * 40)
    gate_path = tmp_path / "desktop" / "gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["source_sha"] = "b" * 40
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    with pytest.raises(GateError, match="source_sha"):
        verify_evidence(tmp_path, "a" * 40)

    _write_all_gates(tmp_path, "a" * 40)
    (tmp_path / "desktop" / "artifact.bin").write_bytes(b"tampered")
    with pytest.raises(GateError, match="size|sha256"):
        verify_evidence(tmp_path, "a" * 40)


def test_verified_local_candidate_does_not_claim_external_release(
    tmp_path: Path,
) -> None:
    _write_all_gates(tmp_path, "a" * 40)

    result = verify_evidence(tmp_path, "a" * 40)

    assert result["classification"] == "candidate_local"
    assert result["remote_release"] == "not_authorized"
    assert result["production_deployment"] == "not_authorized"
    assert result["customer_production_acceptance"] == "not_authorized"


def test_verify_rejects_authorization_or_failed_command(tmp_path: Path) -> None:
    _write_all_gates(tmp_path, "a" * 40)
    gate_path = tmp_path / "webapi" / "gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["authorizations"]["remote_release"] = "authorized"
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    with pytest.raises(GateError, match="authorization"):
        verify_evidence(tmp_path, "a" * 40)

    _write_all_gates(tmp_path, "a" * 40)
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["commands"][0]["failed"] = 1
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    with pytest.raises(GateError, match="command"):
        verify_evidence(tmp_path, "a" * 40)
