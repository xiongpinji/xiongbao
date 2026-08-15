from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_installer_script_scopes_all_mutation_to_test_root() -> None:
    text = (ROOT / "scripts/verify_desktop_installer.ps1").read_text(
        encoding="utf-8"
    )

    assert "$env:LOCALAPPDATA" in text
    assert "XAgentCommercialTest" in text
    assert "-WindowStyle Hidden" in text
    assert "--diagnostics-file" in text
    assert "Get-Process | Stop-Process" not in text
    assert "Remove-Item -Recurse" not in text
    assert "production" not in text.lower()


def test_installer_script_uses_exact_repo_installer_and_pid_cleanup() -> None:
    text = (ROOT / "scripts/verify_desktop_installer.ps1").read_text(
        encoding="utf-8"
    )

    assert "apps/desktop/target/release/bundle/nsis" in text
    assert "Stop-Process -Id" in text
    assert "CloseMainWindow" in text
    assert "source_sha" in text
    assert "desktop_version" in text
    assert "backend_version" in text
