from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CI_PATH = ROOT / ".github" / "workflows" / "ci.yml"
WINDOWS_API_LOCK_PATH = ROOT / "apps" / "api" / "requirements-windows.lock"


def _workflow() -> dict:
    return yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))


def test_release_version_job_runs_all_commercial_contracts() -> None:
    job = _workflow()["jobs"]["release-version"]
    commands = "\n".join(str(step.get("run", "")) for step in job["steps"])

    for contract in (
        "test_release_version_gate.py",
        "test_container_contract.py",
        "test_helm_image_contract.py",
        "test_compose_image_contract.py",
    ):
        assert contract in commands


def test_supply_chain_job_is_fail_closed_and_emits_both_sboms() -> None:
    workflow = _workflow()
    job = workflow["jobs"]["supply-chain"]
    commands = "\n".join(str(step.get("run", "")) for step in job["steps"])
    uses = [str(step.get("uses", "")) for step in job["steps"]]

    assert "pip-audit -r apps/api/requirements.lock" in commands
    assert "npm --prefix apps/web audit --omit=dev --audit-level=high" in commands
    assert "npm --prefix packages/sdk-ts audit --omit=dev --audit-level=high" in commands
    assert "cargo audit --file apps/desktop/Cargo.lock" in commands
    assert "docker build -t xagent-api:ci-sbom apps/api" in commands
    assert "docker build -t xagent-web:ci-sbom apps/web" in commands
    assert sum(item.startswith("anchore/sbom-action@") for item in uses) == 2
    assert any(item.startswith("actions/upload-artifact@") for item in uses)
    assert "supply-chain" in workflow["jobs"]["docker-build"]["needs"]


def test_full_backend_gate_is_separate_from_fast_feedback() -> None:
    workflow = _workflow()
    assert workflow["jobs"]["backend"]["name"] == "Backend fast feedback (Web/API scope)"

    commercial = workflow["jobs"]["backend-commercial"]
    commands = "\n".join(
        str(step.get("run", "")) for step in commercial["steps"]
    )
    assert "python scripts/run_backend_commercial_tests.py" in commands
    assert "backend-commercial" in workflow["jobs"]["release"]["needs"]


def test_windows_api_dependencies_are_locked_and_installed_by_ci() -> None:
    lock_text = WINDOWS_API_LOCK_PATH.read_text(encoding="utf-8")
    commands = "\n".join(
        str(step.get("run", "")) for step in _workflow()["jobs"]["desktop"]["steps"]
    )

    assert "--python-platform x86_64-pc-windows-msvc" in lock_text
    assert "\npywin32==" in lock_text
    assert "\nuvloop==" not in lock_text
    assert (
        "python -m pip install --require-hashes -r apps/api/requirements-windows.lock"
        in commands
    )
