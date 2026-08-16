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


@pytest.mark.parametrize(
    "script",
    [
        "run_commercial_kernel_gate.ps1",
        "run_webapi_commercial_gate.ps1",
        "run_short_drama_commercial_gate.ps1",
        "run_desktop_commercial_gate.ps1",
        "run_rollback_drill.ps1",
    ],
)
def test_commercial_gates_require_python_311(script: str) -> None:
    text = (ROOT / "scripts" / script).read_text(encoding="utf-8")

    assert "function Assert-Python311" in text
    assert "sys.version_info[:2]" in text
    assert "(3, 11)" in text
    assert "Assert-Python311 -PythonCommand $pythonCommand" in text


def test_kernel_gate_audits_the_cross_platform_lock_without_installing() -> None:
    text = (ROOT / "scripts/run_commercial_kernel_gate.ps1").read_text(
        encoding="utf-8"
    )

    assert (
        "Invoke-Checked 'pip-audit' '-r' 'apps/api/requirements.lock' "
        "'--no-deps' '--disable-pip'"
    ) in text


@pytest.mark.parametrize(
    "script",
    [
        "run_webapi_commercial_gate.ps1",
        "run_short_drama_commercial_gate.ps1",
        "run_rollback_drill.ps1",
    ],
)
def test_real_model_gates_bound_ollama_context(script: str) -> None:
    text = (ROOT / "scripts" / script).read_text(encoding="utf-8")

    assert "$env:XAGENT_LLM__OLLAMA_NUM_CTX = '8192'" in text


@pytest.mark.parametrize(
    "script",
    [
        "run_webapi_commercial_gate.ps1",
        "run_short_drama_commercial_gate.ps1",
    ],
)
def test_compose_gates_remove_only_the_project_owned_by_this_run(script: str) -> None:
    text = (ROOT / "scripts" / script).read_text(encoding="utf-8")

    for required in (
        "$runNonce = [Guid]::NewGuid().ToString('N').Substring(0, 8)",
        "function Assert-ProjectAbsent",
        "function Assert-ProjectOwnership",
        "function Remove-AuditedComposeProject",
        "$composeProjectOwned = $true",
        "com.docker.compose.project",
        "'down' '--remove-orphans' '--volumes'",
        "Remove-AuditedComposeProject",
        "$primaryError = $null",
        "$cleanupErrors = [System.Collections.Generic.List[string]]::new()",
        "catch { $primaryError = $_ }",
        "function Write-CleanupEvidence",
        "function Close-GateLock",
        "Write-CleanupEvidence -CleanupErrors $cleanupErrors",
        "Close-GateLock -GateLock $gateLock -CleanupErrors $cleanupErrors",
        "if ($primaryError) { throw $primaryError }",
    ):
        assert required in text
