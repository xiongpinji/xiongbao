from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_desktop_gate_requires_quality_build_install_and_uninstall() -> None:
    text = (ROOT / "scripts/run_desktop_commercial_gate.ps1").read_text(
        encoding="utf-8"
    )

    for required in (
        "cargo fmt",
        "cargo clippy",
        "cargo test",
        "cargo audit",
        "cargo tauri build",
        "collect_desktop_artifacts.py",
        "verify_desktop_installer.ps1",
        "unsigned_local_candidate",
        "source_sha",
    ):
        assert required in text
    assert "status --porcelain" in text
    assert "code_signing = 'not_authorized'" in text


def test_windows_ci_builds_and_uploads_desktop_installers() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    desktop = workflow["jobs"]["desktop"]

    assert desktop["runs-on"] == "windows-latest"
    steps = desktop["steps"]
    step_text = "\n".join(str(step) for step in steps)
    assert "cargo tauri build --bundles msi,nsis" in step_text
    assert "collect_desktop_artifacts.py" in step_text
    assert "desktop-installers" in step_text
    assert "verify_desktop_installer.ps1" not in step_text

    assert "desktop" in workflow["jobs"]["docker-build"]["needs"]
    assert "desktop" in workflow["jobs"]["release"]["needs"]
