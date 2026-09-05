from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_api_runtime_disables_uvicorn_access_log() -> None:
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")
    runtime_command = dockerfile.split("CMD [\"uvicorn\"", 1)[1]

    assert '"--no-access-log"' in runtime_command


def test_compose_and_helm_api_disable_uvicorn_access_log() -> None:
    compose = yaml.safe_load(
        (ROOT / "deploy/compose/docker-compose.yml").read_text(encoding="utf-8")
    )
    helm = (ROOT / "deploy/helm/templates/deployment.yaml").read_text(encoding="utf-8")

    assert "--no-access-log" in compose["services"]["api"]["command"]
    assert "--no-access-log" in helm


def test_ci_load_test_disables_uvicorn_access_log() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    steps = {
        step["name"]: step
        for step in workflow["jobs"]["load-test"]["steps"]
        if "name" in step
    }

    assert "--no-access-log" in steps["Start API"]["run"]
