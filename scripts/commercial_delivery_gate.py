"""Verify all local commercial gates against one clean Git SHA."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping

GATE_DIRECTORIES = {
    "commercial_kernel": "kernel",
    "webapi": "webapi",
    "short_drama": "short-drama",
    "desktop": "desktop",
    "rollback": "rollback",
}
AUTHORIZATION_KEYS = (
    "remote_release",
    "production_deployment",
    "paid_provider_acceptance",
    "customer_production_acceptance",
)
SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")


class GateError(RuntimeError):
    """Commercial evidence failed closed."""


def _verify_artifact(root: Path, item: Mapping[str, object]) -> None:
    original = root / str(item.get("path") or "")
    if original.is_symlink():
        raise GateError("artifact must not be a symlink")
    try:
        path = original.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise GateError(f"artifact is missing: {original.name}") from exc
    resolved_root = root.resolve(strict=True)
    if resolved_root not in path.parents or not path.is_file():
        raise GateError("artifact path escaped evidence root")
    payload = path.read_bytes()
    if len(payload) != int(item.get("size_bytes", -1)):
        raise GateError(f"artifact size mismatch: {path.name}")
    if hashlib.sha256(payload).hexdigest() != str(item.get("sha256") or ""):
        raise GateError(f"artifact sha256 mismatch: {path.name}")


def verify_evidence(root: Path, source_sha: str) -> dict[str, object]:
    if SHA_PATTERN.fullmatch(source_sha) is None:
        raise GateError("source_sha must be 40 lowercase hexadecimal characters")
    evidence_root = Path(root).resolve(strict=True)
    missing = [
        gate
        for gate, directory in GATE_DIRECTORIES.items()
        if not (evidence_root / directory / "gate.json").is_file()
    ]
    if missing:
        raise GateError(f"missing gates: {', '.join(missing)}")

    branch: str | None = None
    command_totals = {"passed": 0, "failed": 0, "skipped": 0}
    artifact_count = 0
    for gate, directory in GATE_DIRECTORIES.items():
        gate_root = (evidence_root / directory).resolve(strict=True)
        gate_path = gate_root / "gate.json"
        try:
            evidence = json.loads(gate_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GateError(f"invalid gate JSON: {gate}") from exc
        if evidence.get("schema_version") != "1.0":
            raise GateError(f"invalid schema for gate {gate}")
        if evidence.get("gate") != gate or evidence.get("repository") != "xagent":
            raise GateError(f"gate identity mismatch: {gate}")
        if evidence.get("source_sha") != source_sha:
            raise GateError(f"source_sha mismatch: {gate}")
        if evidence.get("dirty") is not False:
            raise GateError(f"dirty evidence: {gate}")
        if evidence.get("status") != "passed":
            raise GateError(f"gate did not pass: {gate}")
        if evidence.get("classification") != "candidate_local":
            raise GateError(f"classification mismatch: {gate}")
        gate_branch = str(evidence.get("branch") or "")
        if not gate_branch:
            raise GateError(f"branch is missing: {gate}")
        if branch is None:
            branch = gate_branch
        elif gate_branch != branch:
            raise GateError(f"branch mismatch: {gate}")

        commands = evidence.get("commands")
        if not isinstance(commands, list) or not commands:
            raise GateError(f"command evidence is missing: {gate}")
        for command in commands:
            if not isinstance(command, dict):
                raise GateError(f"invalid command evidence: {gate}")
            if int(command.get("exit_code", -1)) != 0 or int(
                command.get("failed", -1)
            ) != 0:
                raise GateError(f"command failure recorded: {gate}")
            for key in command_totals:
                value = int(command.get(key, 0))
                if value < 0:
                    raise GateError(f"negative command count: {gate}")
                command_totals[key] += value

        authorizations = evidence.get("authorizations")
        if not isinstance(authorizations, dict) or set(authorizations) != set(
            AUTHORIZATION_KEYS
        ):
            raise GateError(f"authorization fields are invalid: {gate}")
        if set(authorizations.values()) != {"not_authorized"}:
            raise GateError(f"authorization boundary exceeded: {gate}")

        artifacts = evidence.get("artifacts")
        if not isinstance(artifacts, list):
            raise GateError(f"artifact evidence is invalid: {gate}")
        for item in artifacts:
            if not isinstance(item, dict):
                raise GateError(f"artifact evidence is invalid: {gate}")
            _verify_artifact(gate_root, item)
            artifact_count += 1

    result: dict[str, object] = {
        "schema_version": "1.0",
        "repository": "xagent",
        "branch": branch,
        "source_sha": source_sha,
        "classification": "candidate_local",
        "gates": {gate: "passed" for gate in GATE_DIRECTORIES},
        "command_totals": command_totals,
        "artifact_count": artifact_count,
        "remote_release": "not_authorized",
        "production_deployment": "not_authorized",
        "paid_provider_acceptance": "not_authorized",
        "customer_production_acceptance": "not_authorized",
    }
    return result


def _write_atomic(path: Path, payload: bytes) -> None:
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


def _report(result: Mapping[str, object]) -> str:
    gates = result["gates"]
    assert isinstance(gates, dict)
    lines = [
        "# X-Agent Commercial Delivery Evidence",
        "",
        f"- Source SHA: `{result['source_sha']}`",
        f"- Branch: `{result['branch']}`",
        f"- Classification: `{result['classification']}`",
        "",
        "## Local gates",
        "",
    ]
    lines.extend(f"- {gate}: `{status}`" for gate, status in gates.items())
    lines.extend(
        [
            "",
            "## External authorization boundary",
            "",
            f"- Remote release: `{result['remote_release']}`",
            f"- Deployment: `{result['production_deployment']}`",
            f"- Paid provider acceptance: `{result['paid_provider_acceptance']}`",
            f"- Customer acceptance: `{result['customer_production_acceptance']}`",
            "",
        ]
    )
    return "\n".join(lines)


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--evidence-root", type=Path, required=True)
    verify.add_argument("--source-sha", required=True)
    verify.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    evidence_root = args.evidence_root.resolve(strict=True)
    if args.require_clean:
        repo_root = Path(__file__).resolve().parents[1]
        if _git(repo_root, "rev-parse", "HEAD") != args.source_sha:
            raise GateError("current HEAD does not match source_sha")
        if _git(repo_root, "status", "--porcelain"):
            raise GateError("current worktree is dirty")
        expected_root = (
            repo_root / "output" / "commercial-delivery" / args.source_sha
        ).resolve()
        if evidence_root != expected_root:
            raise GateError("evidence root does not match the current source SHA")
    result = verify_evidence(evidence_root, args.source_sha)
    _write_atomic(
        evidence_root / "commercial-delivery-manifest.json",
        (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
    )
    _write_atomic(
        evidence_root / "commercial-delivery-report.md",
        _report(result).encode("utf-8"),
    )
    print("commercial delivery candidate: candidate_local")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
