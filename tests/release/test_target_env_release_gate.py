from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SHA = "b" * 40


def _valid_evidence(label: str, *, source_sha: str = SHA) -> dict[str, Any]:
    common: dict[str, Any] = {"schema_version": "1.0", "source_sha": source_sha}
    if label == "Hosted CI evidence":
        return {
            **common,
            "classification": "ci_component_evidence",
            "components": {
                name: "passed_by_needs"
                for name in (
                    "backend-commercial",
                    "commercial-kernel",
                    "desktop",
                    "frontend",
                    "load-test",
                    "short-drama",
                    "supply-chain",
                )
            },
        }
    if label == "Paid model evidence":
        return {
            **common,
            "status": "passed",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "authorization": "one_batch_8_calls",
            "authorized_evaluations": 8,
            "application_max_attempts": 1,
            "promptfoo_max_retries": 0,
            "successes": 8,
            "failures": 0,
            "errors": 0,
            "paid_call_started": True,
            "paid_call_completed": True,
            "promptfoo_results_sha256": "d" * 64,
            "max_cost_usd": "0.25",
            "pricing_source": "https://api-docs.deepseek.com/quick_start/pricing",
            "price_verified_at": "2026-08-16T00:00:00+00:00",
            "balance_verified_at": "2026-08-16T00:00:00+00:00",
        }
    if label == "Signed desktop evidence":
        return {
            **common,
            "classification": "signed_timestamped_candidate",
            "version": "1.1.3",
            "artifacts": [
                {
                    "format": format_name,
                    "arch": "x64",
                    "signature": "valid",
                    "signer_subject": "CN=Commercial Publisher",
                    "signer_thumbprint": "a" * 40,
                    "timestamp_subject": "CN=Trusted Timestamp Authority",
                    "timestamp_thumbprint": "c" * 40,
                }
                for format_name in ("msi", "nsis")
            ],
        }
    gates = {
        "Backup evidence": "backup",
        "Migration evidence": "migration",
        "Health evidence": "health",
        "Browser evidence": "browser",
        "Rollback evidence": "rollback",
    }
    return {**common, "gate": gates[label], "status": "passed"}


def _ref(
    root: Path,
    name: str,
    *,
    label: str,
    source_sha: str = SHA,
    overrides: dict[str, Any] | None = None,
) -> str:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    document = _valid_evidence(label, source_sha=source_sha)
    document.update(overrides or {})
    evidence = json.dumps(document, sort_keys=True).encode("utf-8")
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
            f"- Hosted CI evidence: {_ref(root, 'hosted-ci.json', label='Hosted CI evidence', source_sha=source_sha)}",
            f"- Paid model evidence: {_ref(root, 'paid-model.json', label='Paid model evidence', source_sha=source_sha)}",
            f"- Signed desktop evidence: {_ref(root, 'signed-desktop.json', label='Signed desktop evidence', source_sha=source_sha)}",
            f"- Backup evidence: {_ref(root, 'backup.json', label='Backup evidence', source_sha=source_sha)}",
            f"- Migration evidence: {_ref(root, 'migration.json', label='Migration evidence', source_sha=source_sha)}",
            f"- Health evidence: {_ref(root, 'health.json', label='Health evidence', source_sha=source_sha)}",
            f"- Browser evidence: {_ref(root, 'browser.json', label='Browser evidence', source_sha=source_sha)}",
            f"- Rollback evidence: {_ref(root, 'rollback.json', label='Rollback evidence', source_sha=source_sha)}",
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
        label="Health evidence",
        source_sha="c" * 40,
    )
    packet.write_text(content.replace(valid_health, foreign_health), encoding="utf-8")

    try:
        validate_packet(packet, evidence_root=tmp_path, source_sha=SHA)
    except TargetEnvGateError as exc:
        assert "source sha" in str(exc).lower()
    else:
        raise AssertionError("foreign-SHA evidence was accepted")


def test_target_env_gate_rejects_evidence_that_does_not_prove_its_gate(
    tmp_path: Path,
) -> None:
    from scripts.target_env_release_gate import TargetEnvGateError, validate_packet

    cases = (
        ("Paid model evidence", "paid-model.json", {"status": "failed"}),
        ("Paid model evidence", "paid-model.json", {"max_cost_usd": None}),
        ("Paid model evidence", "paid-model.json", {"pricing_source": None}),
        ("Paid model evidence", "paid-model.json", {"price_verified_at": None}),
        ("Paid model evidence", "paid-model.json", {"balance_verified_at": None}),
        (
            "Signed desktop evidence",
            "signed-desktop.json",
            {"classification": "unsigned_local_candidate"},
        ),
        ("Health evidence", "health.json", {"status": "failed"}),
    )
    for label, name, overrides in cases:
        content = _packet(tmp_path)
        current = next(
            line for line in content.splitlines() if line.startswith(f"- {label}:")
        ).split(":", 1)[1].strip()
        replacement = _ref(
            tmp_path,
            name,
            label=label,
            overrides=overrides,
        )
        packet = tmp_path / "packet.md"
        packet.write_text(content.replace(current, replacement), encoding="utf-8")

        try:
            validate_packet(packet, evidence_root=tmp_path, source_sha=SHA)
        except TargetEnvGateError as exc:
            assert label.lower() in str(exc).lower()
        else:
            raise AssertionError(f"{label} without passing semantics was accepted")


def test_target_env_gate_rejects_duplicate_fields_and_unstructured_signoffs(
    tmp_path: Path,
) -> None:
    from scripts.target_env_release_gate import TargetEnvGateError, validate_packet

    packet = tmp_path / "packet.md"
    packet.write_text(
        _packet(tmp_path).replace(
            "- Environment: customer-staging-a",
            "- Environment: human-readable\n- Environment: machine-selected",
        ),
        encoding="utf-8",
    )
    try:
        validate_packet(packet, evidence_root=tmp_path, source_sha=SHA)
    except TargetEnvGateError as exc:
        assert "duplicate" in str(exc).lower()
    else:
        raise AssertionError("duplicate packet field was accepted")

    packet.write_text(
        _packet(tmp_path).replace(
            "tech-lead / 2026-08-16",
            "approved",
        ),
        encoding="utf-8",
    )
    try:
        validate_packet(packet, evidence_root=tmp_path, source_sha=SHA)
    except TargetEnvGateError as exc:
        assert "tl signoff" in str(exc).lower()
    else:
        raise AssertionError("unstructured signoff was accepted")


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
