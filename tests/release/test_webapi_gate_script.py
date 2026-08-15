from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_playwright_commercial_config_disables_retries() -> None:
    text = (ROOT / "tests/e2e/playwright.config.ts").read_text(encoding="utf-8")

    assert "retries: 0" in text
    assert "E2E_EVIDENCE_DIR" in text


def test_gate_script_requires_real_ollama_and_same_sha() -> None:
    text = (ROOT / "scripts/run_webapi_commercial_gate.ps1").read_text(
        encoding="utf-8"
    )

    for required in (
        "git rev-parse HEAD",
        "git status --porcelain",
        "docker compose",
        "alembic upgrade head",
        "prepare_e2e_workspace.py",
        "ollama",
        "webapi-r2-full-compose.spec.ts",
        "source_sha",
        "passed",
        "production_deployment",
    ):
        assert required in text
    assert "MockLLM" not in text
    assert "down -v" not in text
    assert "--config" in text
    assert "tests/e2e/playwright.config.ts" in text
