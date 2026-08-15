"""Build fail-closed, machine-verifiable commercial gate evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

ALLOWED_GATES = frozenset(
    {"commercial_kernel", "webapi", "short_drama", "desktop", "rollback"}
)
SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")
AUTHORIZATION_KEYS = (
    "remote_release",
    "production_deployment",
    "paid_provider_acceptance",
    "customer_production_acceptance",
)


@dataclass(frozen=True)
class CommandEvidence:
    command: str
    exit_code: int
    passed: int = 0
    failed: int = 0
    skipped: int = 0


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed


def artifact_evidence(path: Path, evidence_root: Path) -> dict[str, object]:
    resolved = Path(path).resolve(strict=True)
    root = Path(evidence_root).resolve(strict=True)
    if root not in resolved.parents:
        raise ValueError("artifact must be inside evidence root")
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError("artifact must be a regular file")
    payload = resolved.read_bytes()
    return {
        "path": resolved.relative_to(root).as_posix(),
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _validate_public_metadata(value: Mapping[str, str], label: str) -> None:
    for key, item in value.items():
        lowered = key.lower()
        if any(word in lowered for word in ("secret", "token", "password", "credential")):
            raise ValueError(f"{label} contains a sensitive key")
        if not isinstance(item, str):
            raise ValueError(f"{label} values must be strings")
        if re.search(r"https?://[^/\s:@]+:[^/\s@]+@", item):
            raise ValueError(f"{label} contains URL credentials")


def build_gate_evidence(
    *,
    gate: str,
    repository: str,
    branch: str,
    source_sha: str,
    dirty: bool,
    started_at: str,
    finished_at: str,
    tools: Mapping[str, str],
    commands: Sequence[CommandEvidence],
    artifacts: Sequence[Path],
    evidence_root: Path,
    classification: str,
    environment: Mapping[str, str] | None = None,
    authorizations: Mapping[str, str] | None = None,
) -> dict[str, object]:
    if SHA_PATTERN.fullmatch(source_sha) is None:
        raise ValueError("source_sha must be 40 lowercase hexadecimal characters")
    if gate not in ALLOWED_GATES:
        raise ValueError(f"unknown gate: {gate}")
    if repository != "xagent":
        raise ValueError("repository must be xagent")
    if not branch.strip():
        raise ValueError("branch must not be empty")
    if dirty:
        raise ValueError("dirty evidence is not eligible")
    if not commands:
        raise ValueError("commands must not be empty")
    if any(command.exit_code != 0 or command.failed != 0 for command in commands):
        raise ValueError("command evidence contains a failure")
    if any(
        value < 0
        for command in commands
        for value in (
            command.passed,
            command.failed,
            command.skipped,
        )
    ):
        raise ValueError("command counts must not be negative")
    if _parse_timestamp(finished_at) < _parse_timestamp(started_at):
        raise ValueError("finished_at must not be earlier than started_at")
    if classification != "candidate_local":
        raise ValueError("commercial gate classification must be candidate_local")
    _validate_public_metadata(tools, "tools")
    safe_environment = dict(environment or {})
    _validate_public_metadata(safe_environment, "environment")

    safe_authorizations = {
        key: "not_authorized" for key in AUTHORIZATION_KEYS
    }
    if authorizations is not None:
        if set(authorizations) != set(AUTHORIZATION_KEYS):
            raise ValueError("authorizations must contain the fixed authorization keys")
        if set(authorizations.values()) != {"not_authorized"}:
            raise ValueError("commercial evidence cannot authorize external actions")
        safe_authorizations = dict(authorizations)

    root = Path(evidence_root).resolve(strict=True)
    artifact_items = [artifact_evidence(path, root) for path in artifacts]
    return {
        "schema_version": "1.0",
        "gate": gate,
        "repository": repository,
        "branch": branch,
        "source_sha": source_sha,
        "dirty": False,
        "started_at": started_at,
        "finished_at": finished_at,
        "tools": dict(sorted(tools.items())),
        "environment": dict(sorted(safe_environment.items())),
        "commands": [asdict(command) for command in commands],
        "artifacts": artifact_items,
        "status": "passed",
        "classification": classification,
        "authorizations": safe_authorizations,
    }


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _command_from_mapping(value: Mapping[str, object]) -> CommandEvidence:
    return CommandEvidence(
        command=str(value["command"]),
        exit_code=int(value["exit_code"]),
        passed=int(value.get("passed", 0)),
        failed=int(value.get("failed", 0)),
        skipped=int(value.get("skipped", 0)),
    )


def _main_build(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve(strict=True)
    evidence_root = args.artifacts_root.resolve(strict=True)
    output = args.output.resolve()
    if evidence_root not in output.parents:
        raise ValueError("gate output must be inside artifacts root")
    if _git(repo_root, "rev-parse", "HEAD") != args.source_sha:
        raise ValueError("current HEAD does not match source_sha")
    dirty = bool(_git(repo_root, "status", "--porcelain"))
    command_values = json.loads(args.commands.read_text(encoding="utf-8"))
    commands = [_command_from_mapping(item) for item in command_values]

    excluded = {
        output.resolve(),
        args.commands.resolve(strict=True),
    }
    if args.artifact:
        artifacts = [path.resolve(strict=True) for path in args.artifact]
    else:
        artifacts = [
            path
            for path in evidence_root.rglob("*")
            if path.is_file()
            and path.resolve() not in excluded
            and not path.name.endswith(".tmp")
            and path.name != "gate.json"
        ]
    evidence = build_gate_evidence(
        gate=args.gate,
        repository="xagent",
        branch=_git(repo_root, "branch", "--show-current") or "detached",
        source_sha=args.source_sha,
        dirty=dirty,
        started_at=args.started_at,
        finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        tools={"python": platform.python_version()},
        environment={"os": platform.system(), "architecture": platform.machine()},
        commands=commands,
        artifacts=artifacts,
        evidence_root=evidence_root,
        classification="candidate_local",
    )
    _write_json_atomic(output, evidence)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--gate", choices=sorted(ALLOWED_GATES), required=True)
    build.add_argument("--repo-root", type=Path, required=True)
    build.add_argument("--source-sha", required=True)
    build.add_argument("--started-at", required=True)
    build.add_argument("--commands", type=Path, required=True)
    build.add_argument("--artifacts-root", type=Path, required=True)
    build.add_argument("--artifact", type=Path, action="append")
    build.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "build":
        return _main_build(args)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
