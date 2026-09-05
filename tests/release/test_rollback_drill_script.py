from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_rollback_drill_uses_only_audited_projects() -> None:
    text = (ROOT / "scripts/run_rollback_drill.ps1").read_text(encoding="utf-8")

    assert "xagent-rollback-candidate-" in text
    assert 'candidate project must be new and empty' in text
    assert "xagent-restore-" in text
    assert "com.docker.compose.project" in text
    assert "backup-manifest.json" in text
    assert "restore-manifest.json" in text
    assert "gate_evidence.py" in text
    assert "docker volume rm" not in text
    assert "docker system prune" not in text
    assert "Remove-Item -Recurse" not in text
    assert "production" not in text.lower()


def test_rollback_drill_pins_compatible_baseline_and_exact_service_switch() -> None:
    text = (ROOT / "scripts/run_rollback_drill.ps1").read_text(encoding="utf-8")

    assert "5256f6a8c8df998b92740d5dd9a18bc3b2e1c268" in text
    assert "--no-deps" in text
    assert "--no-build" in text
    for service in ("api", "worker", "web"):
        assert f"'{service}'" in text
    assert "'worktree' 'remove' '--force'" in text


def test_rollback_runtime_switch_disables_model_warmup() -> None:
    text = (ROOT / "scripts/run_rollback_drill.ps1").read_text(encoding="utf-8")

    assert 'XAGENT_LLM__WARMUP_ENABLED: "false"' in text


def test_rollback_drill_cleans_owned_projects_and_ephemeral_worktree() -> None:
    text = (ROOT / "scripts/run_rollback_drill.ps1").read_text(encoding="utf-8")

    for required in (
        "$runNonce = [Guid]::NewGuid().ToString('N').Substring(0, 8)",
        "function Assert-ProjectOwnership",
        "function Remove-AuditedComposeProject",
        "$candidateProjectOwned = $true",
        "$restoreProjectOwned = $true",
        "Remove-AuditedComposeProject -Project $candidateProject",
        "Remove-AuditedComposeProject -Project $restoreProject",
        "'down' '--remove-orphans' '--volumes'",
        "'worktree' 'remove' '--force' $baseWorktree",
        "$primaryError = $null",
        "$cleanupErrors = [System.Collections.Generic.List[string]]::new()",
        "catch { $primaryError = $_ }",
        "$cleanupErrors.Add(\"restore project: $($_.Exception.Message)\")",
        "$cleanupErrors.Add(\"candidate project: $($_.Exception.Message)\")",
        "$cleanupErrors.Add(\"baseline worktree: $($_.Exception.Message)\")",
        "function Write-CleanupEvidence",
        "function Close-GateLock",
        "Write-CleanupEvidence -CleanupErrors $cleanupErrors",
        "Close-GateLock -GateLock $gateLock -CleanupErrors $cleanupErrors",
        "if ($primaryError) { throw $primaryError }",
    ):
        assert required in text
