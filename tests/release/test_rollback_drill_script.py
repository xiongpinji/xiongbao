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
    assert "worktree remove" in text
