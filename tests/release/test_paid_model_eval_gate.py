from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "paid_model_eval_gate.py"
SHA = "a" * 40


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    assert SCRIPT.is_file(), "paid model gate script is missing"
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _authorized_env() -> dict[str, str]:
    now = datetime.now(UTC).isoformat()
    return {
        **os.environ,
        "GITHUB_SHA": SHA,
        "XAGENT_PAID_EVAL_AUTHORIZATION": "one_batch_8_calls",
        "XAGENT_LLM__DEFAULT_MODEL": "deepseek-chat",
        "XAGENT_LLM__MAX_ATTEMPTS": "1",
        "XAGENT_LLM__DEEPSEEK_API_KEY": "test-provider-secret-value",
        "XAGENT_PAID_EVAL_PRICING_SOURCE": "https://api-docs.deepseek.com/quick_start/pricing",
        "XAGENT_PAID_EVAL_PRICE_VERIFIED_AT": now,
        "XAGENT_PAID_EVAL_BALANCE_VERIFIED_AT": now,
        "XAGENT_PAID_EVAL_MAX_USD": "0.25",
    }


def test_preflight_fails_closed_without_explicit_authorization(tmp_path: Path) -> None:
    env = _authorized_env()
    env.pop("XAGENT_PAID_EVAL_AUTHORIZATION")
    result = _run(
        "preflight",
        "--source-sha",
        SHA,
        "--expected-calls",
        "8",
        "--output",
        str(tmp_path / "preflight.json"),
        env=env,
    )

    assert result.returncode == 2
    assert "authorization" in result.stderr.lower()
    assert env["XAGENT_LLM__DEEPSEEK_API_KEY"] not in result.stdout + result.stderr
    assert not (tmp_path / "preflight.json").exists()


def test_preflight_records_safe_fresh_cost_and_balance_boundary(tmp_path: Path) -> None:
    output = tmp_path / "preflight.json"
    env = _authorized_env()
    result = _run(
        "preflight",
        "--source-sha",
        SHA,
        "--expected-calls",
        "8",
        "--output",
        str(output),
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["source_sha"] == SHA
    assert payload["provider"] == "deepseek"
    assert payload["model"] == "deepseek-chat"
    assert payload["authorized_evaluations"] == 8
    assert payload["application_max_attempts"] == 1
    assert payload["paid_call_started"] is False
    assert "secret" not in json.dumps(payload).lower()


def test_preflight_rejects_non_finite_cost_without_a_traceback(tmp_path: Path) -> None:
    env = _authorized_env()
    env["XAGENT_PAID_EVAL_MAX_USD"] = "NaN"
    result = _run(
        "preflight",
        "--source-sha",
        SHA,
        "--expected-calls",
        "8",
        "--output",
        str(tmp_path / "preflight.json"),
        env=env,
    )

    assert result.returncode == 2
    assert "maximum cost" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()


def test_verify_requires_exact_success_matrix_and_writes_same_sha_evidence(
    tmp_path: Path,
) -> None:
    preflight = tmp_path / "preflight.json"
    result = _run(
        "preflight",
        "--source-sha",
        SHA,
        "--expected-calls",
        "8",
        "--output",
        str(preflight),
        env=_authorized_env(),
    )
    assert result.returncode == 0, result.stderr

    promptfoo = tmp_path / "promptfoo.json"
    promptfoo.write_text(
        json.dumps(
            {"results": {"stats": {"successes": 8, "failures": 0, "errors": 0}}}
        ),
        encoding="utf-8",
    )
    output = tmp_path / "paid-model-evidence.json"
    result = _run(
        "verify",
        "--preflight",
        str(preflight),
        "--promptfoo-results",
        str(promptfoo),
        "--output",
        str(output),
        env=_authorized_env(),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source_sha"] == SHA
    assert payload["status"] == "passed"
    assert payload["successes"] == payload["authorized_evaluations"] == 8
    assert payload["failures"] == payload["errors"] == 0
    assert payload["provider"] == "deepseek"
    assert payload["model"] == "deepseek-chat"


def test_verify_rejects_a_tampered_preflight_contract(tmp_path: Path) -> None:
    preflight = tmp_path / "preflight.json"
    result = _run(
        "preflight",
        "--source-sha",
        SHA,
        "--expected-calls",
        "8",
        "--output",
        str(preflight),
        env=_authorized_env(),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(preflight.read_text(encoding="utf-8"))
    payload["provider"] = "unverified-provider"
    preflight.write_text(json.dumps(payload), encoding="utf-8")

    promptfoo = tmp_path / "promptfoo.json"
    promptfoo.write_text(
        json.dumps(
            {"results": {"stats": {"successes": 8, "failures": 0, "errors": 0}}}
        ),
        encoding="utf-8",
    )
    output = tmp_path / "paid-model-evidence.json"
    result = _run(
        "verify",
        "--preflight",
        str(preflight),
        "--promptfoo-results",
        str(promptfoo),
        "--output",
        str(output),
        env=_authorized_env(),
    )

    assert result.returncode == 1
    assert "provider" in result.stderr.lower()
    assert not output.exists()
