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
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
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
SIGNOFF_PATTERN = re.compile(
    r"^(?P<identity>[^/]+?)\s*/\s*(?P<date>\d{4}-\d{2}-\d{2})$"
)
HOSTED_CI_COMPONENTS = frozenset(
    {
        "backend-commercial",
        "commercial-kernel",
        "desktop",
        "frontend",
        "load-test",
        "short-drama",
        "supply-chain",
    }
)
GENERIC_EVIDENCE_GATES = {
    "Backup evidence": "backup",
    "Migration evidence": "migration",
    "Health evidence": "health",
    "Browser evidence": "browser",
    "Rollback evidence": "rollback",
}


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
            label = match.group("label").strip()
            if label in result:
                raise TargetEnvGateError(f"duplicate packet field: {label}")
            result[label] = match.group("value").strip()
    return result


def _require(document: dict[str, object], label: str, key: str, expected: object) -> None:
    if document.get(key) != expected:
        raise TargetEnvGateError(f"{label} must prove {key}={expected}")


def _validate_hosted_ci(label: str, document: dict[str, object]) -> None:
    _require(document, label, "classification", "ci_component_evidence")
    components = document.get("components")
    if not isinstance(components, dict) or any(
        components.get(name) != "passed_by_needs" for name in HOSTED_CI_COMPONENTS
    ):
        raise TargetEnvGateError(f"{label} must prove every required CI component passed")


def _validate_paid_model(label: str, document: dict[str, object]) -> None:
    expected = {
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
    }
    for key, value in expected.items():
        if type(document.get(key)) is not type(value) or document.get(key) != value:
            raise TargetEnvGateError(f"{label} must prove {key}={value}")
    digest = document.get("promptfoo_results_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
        raise TargetEnvGateError(f"{label} must bind the raw Promptfoo result digest")
    try:
        maximum_cost = Decimal(str(document.get("max_cost_usd", "")))
    except InvalidOperation as exc:
        raise TargetEnvGateError(f"{label} has an invalid maximum cost") from exc
    if (
        not maximum_cost.is_finite()
        or maximum_cost <= 0
        or maximum_cost > Decimal("1.00")
    ):
        raise TargetEnvGateError(f"{label} maximum cost is outside the limit")
    pricing_source = document.get("pricing_source")
    if not isinstance(pricing_source, str) or not pricing_source.startswith("https://"):
        raise TargetEnvGateError(f"{label} must preserve the HTTPS pricing source")
    for field in ("price_verified_at", "balance_verified_at"):
        value = document.get(field)
        if not isinstance(value, str):
            raise TargetEnvGateError(f"{label} is missing {field}")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise TargetEnvGateError(f"{label} has an invalid {field}") from exc
        if parsed.tzinfo is None:
            raise TargetEnvGateError(f"{label} {field} must include a timezone")


def _validate_signed_desktop(label: str, document: dict[str, object]) -> None:
    _require(document, label, "classification", "signed_timestamped_candidate")
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise TargetEnvGateError(f"{label} must contain exactly two installers")
    if {
        item.get("format") for item in artifacts if isinstance(item, dict)
    } != {"msi", "nsis"}:
        raise TargetEnvGateError(f"{label} must contain MSI and NSIS installers")
    for item in artifacts:
        if not isinstance(item, dict):
            raise TargetEnvGateError(f"{label} contains an invalid installer entry")
        if item.get("signature") != "valid" or item.get("arch") != "x64":
            raise TargetEnvGateError(f"{label} installers must be valid signed x64 artifacts")
        for field in ("signer_subject", "timestamp_subject"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise TargetEnvGateError(f"{label} installer is missing {field}")
        for field in ("signer_thumbprint", "timestamp_thumbprint"):
            value = item.get(field)
            if not isinstance(value, str) or re.fullmatch(r"[A-Fa-f0-9]{40}", value) is None:
                raise TargetEnvGateError(f"{label} installer has invalid {field}")


def _validate_evidence_document(label: str, document: dict[str, object]) -> None:
    _require(document, label, "schema_version", "1.0")
    if label == "Hosted CI evidence":
        _validate_hosted_ci(label, document)
    elif label == "Paid model evidence":
        _validate_paid_model(label, document)
    elif label == "Signed desktop evidence":
        _validate_signed_desktop(label, document)
    else:
        _require(document, label, "gate", GENERIC_EVIDENCE_GATES[label])
        _require(document, label, "status", "passed")


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
    _validate_evidence_document(label, document)
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
    for label in SIGNOFF_FIELDS:
        match = SIGNOFF_PATTERN.fullmatch(fields[label])
        if match is None or _placeholder(match.group("identity")):
            raise TargetEnvGateError(
                f"{label} must contain a named identity and ISO date: identity / YYYY-MM-DD"
            )
        try:
            date.fromisoformat(match.group("date"))
        except ValueError as exc:
            raise TargetEnvGateError(f"{label} contains an invalid ISO date") from exc
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
