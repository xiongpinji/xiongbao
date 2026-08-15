from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_playwright_commercial_config_disables_retries() -> None:
    text = (ROOT / "tests/e2e/playwright.config.ts").read_text(encoding="utf-8")

    assert "retries: 0" in text
    assert "E2E_EVIDENCE_DIR" in text
