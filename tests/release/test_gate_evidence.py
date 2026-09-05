import hashlib
from pathlib import Path

import pytest

from scripts.gate_evidence import CommandEvidence, build_gate_evidence


def test_build_gate_evidence_records_source_and_commands(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.zip"
    artifact.write_bytes(b"delivery")

    evidence = build_gate_evidence(
        gate="webapi",
        repository="xagent",
        branch="codex/commercial-delivery-20260815",
        source_sha="a" * 40,
        dirty=False,
        started_at="2026-08-15T00:00:00Z",
        finished_at="2026-08-15T00:10:00Z",
        tools={"python": "3.11.9"},
        commands=[
            CommandEvidence(
                command="python -m pytest",
                exit_code=0,
                passed=10,
                failed=0,
                skipped=0,
            )
        ],
        artifacts=[artifact],
        evidence_root=tmp_path,
        classification="candidate_local",
    )

    assert evidence["source_sha"] == "a" * 40
    assert evidence["commands"][0]["exit_code"] == 0
    assert evidence["artifacts"][0]["sha256"] == hashlib.sha256(
        b"delivery"
    ).hexdigest()
    assert set(evidence["authorizations"].values()) == {"not_authorized"}


def test_invalid_gate_or_sha_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source_sha"):
        build_gate_evidence(
            gate="unknown",
            repository="xagent",
            branch="main",
            source_sha="short",
            dirty=False,
            started_at="2026-08-15T00:00:00Z",
            finished_at="2026-08-15T00:01:00Z",
            tools={},
            commands=[],
            artifacts=[],
            evidence_root=tmp_path,
            classification="candidate_local",
        )


@pytest.mark.parametrize(
    ("dirty", "commands", "match"),
    [
        (True, [CommandEvidence("pytest", 0)], "dirty"),
        (False, [], "commands"),
        (False, [CommandEvidence("pytest", 1)], "command"),
        (False, [CommandEvidence("pytest", 0, failed=1)], "command"),
    ],
)
def test_dirty_empty_or_failed_evidence_is_rejected(
    tmp_path: Path,
    dirty: bool,
    commands: list[CommandEvidence],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        build_gate_evidence(
            gate="desktop",
            repository="xagent",
            branch="main",
            source_sha="a" * 40,
            dirty=dirty,
            started_at="2026-08-15T00:00:00Z",
            finished_at="2026-08-15T00:01:00Z",
            tools={},
            commands=commands,
            artifacts=[],
            evidence_root=tmp_path,
            classification="candidate_local",
        )


def test_artifact_outside_evidence_root_is_rejected(tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"outside")

    with pytest.raises(ValueError, match="inside evidence root"):
        build_gate_evidence(
            gate="rollback",
            repository="xagent",
            branch="main",
            source_sha="a" * 40,
            dirty=False,
            started_at="2026-08-15T00:00:00Z",
            finished_at="2026-08-15T00:01:00Z",
            tools={},
            commands=[CommandEvidence("drill", 0)],
            artifacts=[outside],
            evidence_root=evidence_root,
            classification="candidate_local",
        )
