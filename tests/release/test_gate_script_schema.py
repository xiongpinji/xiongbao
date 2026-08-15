from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("script", "gate"),
    [
        ("run_commercial_kernel_gate.ps1", "commercial_kernel"),
        ("run_webapi_commercial_gate.ps1", "webapi"),
        ("run_short_drama_commercial_gate.ps1", "short_drama"),
        ("run_desktop_commercial_gate.ps1", "desktop"),
    ],
)
def test_gate_script_writes_shared_schema(script: str, gate: str) -> None:
    text = (ROOT / "scripts" / script).read_text(encoding="utf-8")

    assert "gate_evidence.py" in text
    assert gate in text
    assert "source_sha" in text
    assert "commands" in text
    assert "artifacts" in text
    assert "not_authorized" in text


def test_kernel_gate_imports_api_from_the_current_worktree() -> None:
    text = (ROOT / "scripts/run_commercial_kernel_gate.ps1").read_text(
        encoding="utf-8"
    )

    assert "$env:PYTHONPATH" in text
    assert "Join-Path $RepoRoot 'apps/api'" in text


def test_kernel_gate_uses_the_preflight_cli_contract() -> None:
    text = (ROOT / "scripts/run_commercial_kernel_gate.ps1").read_text(
        encoding="utf-8"
    )

    assert "'--init-env' $temporaryEnv" in text
    assert "'--output' $temporaryReport" in text
    assert "'scripts/r2_preflight.py' 'init-env'" not in text


def test_kernel_gate_audits_the_cross_platform_lock_without_installing() -> None:
    text = (ROOT / "scripts/run_commercial_kernel_gate.ps1").read_text(
        encoding="utf-8"
    )

    assert (
        "Invoke-Checked 'pip-audit' '-r' 'apps/api/requirements.lock' "
        "'--no-deps' '--disable-pip'"
    ) in text
