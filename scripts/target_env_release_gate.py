#!/usr/bin/env python3
"""Validate target-environment authorization and recompute referenced evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path


SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")
FIELD_PATTERN = re.compile(r"^\s*-\s*(?P<label>[^:]+):\s*(?P<value>.*?)\s*$")
REFERENCE_PATTERN = re.compile(
    r"^(?P<path>[^|]+?)\s*\|\s*sha256=(?P<sha>[a-f0-9]{64})$"
)
AUTHORIZATION = "approved-for-target-env"
PLACEHOLDERS = {"", "-", "n/a", "none", "pending", "todo", "tbd", "待填", "待确认"}
EVIDENCE_FIELDS = (
    "Hosted CI evidence",
    "Paid model evidence",
    "Signed desktop evidence",
    "Backup evidence",
    "Migration evidence",
    "Health evidence",
    "Browser evidence",
    "Rollback evidence",
)
SIGNOFF_FIELDS = ("TL signoff", "QA signoff", "DevOps signoff", "Owner signoff")


class TargetEnvGateError(RuntimeError):
    """Target environment packet is incomplete, inconsistent, or tampered."""


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _placeholder(value: str) -> bool:
    normalized = _normalize(value)
    return normalized in PLACEHOLDERS or normalized.startswith("<") or normalized.endswith(">")


def _fields(packet: Path) -> dict[str, str]:
    try:
        text = packet.read_text(encoding="utf-8")
    except OSError as exc:
        raise TargetEnvGateError(f"packet unreadable: {exc}") from exc
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = FIELD_PATTERN.match(line)
        if match:
            result[match.group("label").strip()] = match.group("value").strip()
    return result


def _verify_reference(
    root: Path, label: str, value: str, source_sha: str
) -> dict[str, object]:
    match = REFERENCE_PATTERN.fullmatch(value)
    if match is None:
        raise TargetEnvGateError(f"{label} must contain path | sha256=<digest>")
    original = root / match.group("path").strip()
    if original.is_symlink():
        raise TargetEnvGateError(f"{label} must not reference a symlink")
    try:
        path = original.resolve(strict=True)
    except OSError as exc:
        raise TargetEnvGateError(f"{label} file is missing") from exc
    resolved_root = root.resolve(strict=True)
    if resolved_root not in path.parents or not path.is_file():
        raise TargetEnvGateError(f"{label} escaped the evidence root")
    payload = path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != match.group("sha"):
        raise TargetEnvGateError(f"{label} sha256 mismatch")
    try:
        document = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TargetEnvGateError(f"{label} must be a JSON evidence document") from exc
    if not isinstance(document, dict) or document.get("source_sha") != source_sha:
        raise TargetEnvGateError(f"{label} source SHA mismatch")
    return {
        "label": label,
        "path": path.relative_to(resolved_root).as_posix(),
        "sha256": actual,
        "size_bytes": len(payload),
    }


def validate_packet(
    packet_path: Path, *, evidence_root: Path, source_sha: str
) -> dict[str, object]:
    if SHA_PATTERN.fullmatch(source_sha) is None:
        raise TargetEnvGateError("source SHA must be 40 lowercase hexadecimal characters")
    packet = Path(packet_path).resolve(strict=True)
    root = Path(evidence_root).resolve(strict=True)
    fields = _fields(packet)
    required = (
        "Release ID",
        "Source SHA",
        "Environment",
        "Explicit authorization",
        *EVIDENCE_FIELDS,
        *SIGNOFF_FIELDS,
        "Final disposition",
    )
    for label in required:
        value = fields.get(label, "")
        if _placeholder(value):
            raise TargetEnvGateError(f"missing or unfilled field: {label}")
    if fields["Source SHA"] != source_sha:
        raise TargetEnvGateError("source SHA does not match the authorized candidate")
    if _normalize(fields["Explicit authorization"]) != AUTHORIZATION:
        raise TargetEnvGateError(f"explicit authorization must equal {AUTHORIZATION}")
    if _normalize(fields["Final disposition"]) != AUTHORIZATION:
        raise TargetEnvGateError(f"final disposition must equal {AUTHORIZATION}")
    evidence = [
        _verify_reference(root, label, fields[label], source_sha)
        for label in EVIDENCE_FIELDS
    ]
    return {
        "schema_version": "1.0",
        "gate": "target_environment",
        "status": "passed",
        "source_sha": source_sha,
        "release_id": fields["Release ID"],
        "environment": fields["Environment"],
        "authorization": AUTHORIZATION,
        "final_disposition": AUTHORIZATION,
        "signoffs": {label: fields[label] for label in SIGNOFF_FIELDS},
        "evidence": evidence,
    }


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = validate_packet(
            args.packet,
            evidence_root=args.evidence_root,
            source_sha=args.source_sha,
        )
        _write_json_atomic(args.output, payload)
    except (OSError, TargetEnvGateError) as exc:
        print(f"TARGET ENV RELEASE GATE: BLOCKED ({exc})", file=sys.stderr)
        return 1
    print(f"TARGET ENV RELEASE GATE: PASS ({args.output})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
