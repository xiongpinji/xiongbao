from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
HELM = ROOT / "deploy" / "helm"
IMAGE_TEMPLATES = (
    "deployment.yaml",
    "worker.yaml",
    "job-post-deploy.yaml",
    "cronjob-health.yaml",
    "cronjob-evidence.yaml",
    "web.yaml",
)


def test_helm_images_are_immutable() -> None:
    values = yaml.safe_load((HELM / "values.yaml").read_text(encoding="utf-8"))

    assert values["image"]["tag"] == "1.1.3"
    assert values["web"]["image"]["tag"] == "1.1.3"
    assert values["image"]["digest"] == ""
    assert values["web"]["image"]["digest"] == ""
    assert "latest" not in json.dumps(values)


def test_all_application_templates_use_digest_aware_helper() -> None:
    helpers = (HELM / "templates" / "_helpers.tpl").read_text(encoding="utf-8")
    assert 'define "xagent.image"' in helpers
    for filename in IMAGE_TEMPLATES:
        template = (HELM / "templates" / filename).read_text(encoding="utf-8")
        assert 'include "xagent.image"' in template, filename


def test_helm_security_context_matches_runtime_user() -> None:
    for filename in IMAGE_TEMPLATES[:-1]:
        template = (HELM / "templates" / filename).read_text(encoding="utf-8")
        lines = {line.strip() for line in template.splitlines()}
        assert "runAsUser: 1000" not in lines, filename
        assert "fsGroup: 1000" not in lines, filename
        assert "runAsUser: 10001" in lines, filename
