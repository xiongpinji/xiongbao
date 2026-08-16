#!/usr/bin/env python3
"""Fail-closed preflight and evidence builder for one paid Promptfoo batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path


SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")
AUTHORIZATION = "one_batch_8_calls"
PROVIDER = "deepseek"
MODEL = "deepseek-chat"
MAX_VERIFICATION_AGE = timedelta(hours=24)


class PaidModelGateError(RuntimeError):
    """Paid model evaluation failed closed before or after the authorized batch."""


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


def _fresh_timestamp(name: str, value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PaidModelGateError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise PaidModelGateError(f"{name} must include a timezone")
    now = datetime.now(UTC)
    parsed = parsed.astimezone(UTC)
    if parsed > now + timedelta(minutes=5) or now - parsed > MAX_VERIFICATION_AGE:
        raise PaidModelGateError(f"{name} must be verified within 24 hours")
    return parsed.isoformat()


def build_preflight(
    *, source_sha: str, expected_calls: int, environ: Mapping[str, str]
) -> dict[str, object]:
    if SHA_PATTERN.fullmatch(source_sha) is None:
        raise PaidModelGateError("source SHA must be 40 lowercase hexadecimal characters")
    if expected_calls != 8:
        raise PaidModelGateError("paid evaluation authorization is fixed to exactly 8 calls")
    if environ.get("GITHUB_SHA", "") != source_sha:
        raise PaidModelGateError("GITHUB_SHA does not match the authorized source SHA")
    if environ.get("XAGENT_PAID_EVAL_AUTHORIZATION", "") != AUTHORIZATION:
        raise PaidModelGateError(f"authorization must equal {AUTHORIZATION}")
    if environ.get("XAGENT_LLM__DEFAULT_MODEL", "") != MODEL:
        raise PaidModelGateError(f"model must equal {MODEL}")
    if environ.get("XAGENT_LLM__MAX_ATTEMPTS", "") != "1":
        raise PaidModelGateError("application LLM attempts must equal 1")
    provider_key = environ.get("XAGENT_LLM__DEEPSEEK_API_KEY", "")
    if len(provider_key.strip()) < 16:
        raise PaidModelGateError("DeepSeek provider credential is missing")
    pricing_source = environ.get("XAGENT_PAID_EVAL_PRICING_SOURCE", "").strip()
    if not pricing_source.startswith("https://"):
        raise PaidModelGateError("pricing source must be an HTTPS URL")
    price_verified_at = _fresh_timestamp(
        "price verification", environ.get("XAGENT_PAID_EVAL_PRICE_VERIFIED_AT", "")
    )
    balance_verified_at = _fresh_timestamp(
        "balance verification", environ.get("XAGENT_PAID_EVAL_BALANCE_VERIFIED_AT", "")
    )
    try:
        maximum_cost = Decimal(environ.get("XAGENT_PAID_EVAL_MAX_USD", ""))
    except InvalidOperation as exc:
        raise PaidModelGateError("maximum cost must be a decimal USD amount") from exc
    if (
        not maximum_cost.is_finite()
        or maximum_cost <= 0
        or maximum_cost > Decimal("1.00")
    ):
        raise PaidModelGateError("maximum cost must be greater than 0 and at most 1 USD")
    return {
        "schema_version": "1.0",
        "status": "passed",
        "source_sha": source_sha,
        "provider": PROVIDER,
        "model": MODEL,
        "authorization": AUTHORIZATION,
        "authorized_evaluations": expected_calls,
        "application_max_attempts": 1,
        "promptfoo_max_retries": 0,
        "max_cost_usd": str(maximum_cost),
        "pricing_source": pricing_source,
        "price_verified_at": price_verified_at,
        "balance_verified_at": balance_verified_at,
        "paid_call_started": False,
    }


def _validate_preflight_document(preflight: object) -> dict[str, object]:
    if not isinstance(preflight, dict):
        raise PaidModelGateError("paid model preflight must be a JSON object")
    expected = {
        "schema_version": "1.0",
        "status": "passed",
        "provider": PROVIDER,
        "model": MODEL,
        "authorization": AUTHORIZATION,
        "authorized_evaluations": 8,
        "application_max_attempts": 1,
        "promptfoo_max_retries": 0,
        "paid_call_started": False,
    }
    for key, value in expected.items():
        if type(preflight.get(key)) is not type(value) or preflight.get(key) != value:
            raise PaidModelGateError(f"paid model preflight {key} must equal {value}")
    source_sha = preflight.get("source_sha")
    if not isinstance(source_sha, str) or SHA_PATTERN.fullmatch(source_sha) is None:
        raise PaidModelGateError("paid model preflight source SHA is invalid")
    pricing_source = preflight.get("pricing_source")
    if not isinstance(pricing_source, str) or not pricing_source.startswith("https://"):
        raise PaidModelGateError("paid model preflight pricing source is invalid")
    for key, label in (
        ("price_verified_at", "price verification"),
        ("balance_verified_at", "balance verification"),
    ):
        value = preflight.get(key)
        if not isinstance(value, str):
            raise PaidModelGateError(f"paid model preflight {key} is invalid")
        _fresh_timestamp(label, value)
    try:
        maximum_cost = Decimal(str(preflight.get("max_cost_usd", "")))
    except InvalidOperation as exc:
        raise PaidModelGateError("paid model preflight maximum cost is invalid") from exc
    if (
        not maximum_cost.is_finite()
        or maximum_cost <= 0
        or maximum_cost > Decimal("1.00")
    ):
        raise PaidModelGateError("paid model preflight maximum cost is outside the limit")
    return preflight


def verify_results(preflight_path: Path, results_path: Path) -> dict[str, object]:
    try:
        preflight = json.loads(preflight_path.read_text(encoding="utf-8-sig"))
        results_bytes = results_path.read_bytes()
        results = json.loads(results_bytes.decode("utf-8-sig"))
        stats = results["results"]["stats"]
        successes = stats["successes"]
        failures = stats["failures"]
        errors = stats["errors"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PaidModelGateError("paid model evidence is missing or invalid") from exc
    preflight = _validate_preflight_document(preflight)
    expected = preflight.get("authorized_evaluations")
    if any(type(value) is not int for value in (expected, successes, failures, errors)):
        raise PaidModelGateError("Promptfoo statistics must be integers")
    if successes != expected or failures != 0 or errors != 0:
        raise PaidModelGateError(
            f"paid model quality gate failed: successes={successes}, "
            f"failures={failures}, errors={errors}"
        )
    return {
        **preflight,
        "status": "passed",
        "successes": successes,
        "failures": failures,
        "errors": errors,
        "paid_call_started": True,
        "paid_call_completed": True,
        "promptfoo_results_sha256": hashlib.sha256(results_bytes).hexdigest(),
        "finished_at": datetime.now(UTC).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--source-sha", required=True)
    preflight.add_argument("--expected-calls", type=int, required=True)
    preflight.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--preflight", type=Path, required=True)
    verify.add_argument("--promptfoo-results", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "preflight":
            payload = build_preflight(
                source_sha=args.source_sha,
                expected_calls=args.expected_calls,
                environ=os.environ,
            )
            _write_json_atomic(args.output, payload)
            print("PAID MODEL PREFLIGHT: PASS (no provider call made)")
            return 0
        payload = verify_results(args.preflight, args.promptfoo_results)
        _write_json_atomic(args.output, payload)
        print(f"PAID MODEL EVALUATION: PASS ({payload['successes']}/8)")
        return 0
    except PaidModelGateError as exc:
        phase = "PREFLIGHT" if args.operation == "preflight" else "EVALUATION"
        print(f"PAID MODEL {phase}: BLOCKED ({exc})", file=sys.stderr)
        return 2 if args.operation == "preflight" else 1


if __name__ == "__main__":
    raise SystemExit(main())
