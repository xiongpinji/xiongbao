from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_ci_component_evidence_does_not_claim_local_candidate() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["commercial-evidence"]

    assert set(job["needs"]) == {
        "commercial-kernel",
        "backend-commercial",
        "frontend",
        "short-drama",
        "desktop",
        "supply-chain",
    }
    text = "\n".join(str(step) for step in job["steps"])
    assert "ci_component_evidence" in text
    assert "candidate_local" not in text
    assert "commercial-component-evidence" in text


def test_remote_publish_jobs_require_explicit_authorization_variable() -> None:
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert text.count("vars.XAGENT_RELEASE_AUTHORIZED == 'true'") >= 2


def test_ci_discovers_external_ga_gate_contracts() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["config-governance"]["steps"]
    commands = "\n".join(str(step.get("run", "")) for step in steps)

    for contract in (
        "test_paid_model_eval_gate.py",
        "test_target_env_release_gate.py",
        "test_collect_desktop_artifacts.py",
    ):
        assert contract in commands
