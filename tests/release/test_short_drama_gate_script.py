from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_short_drama_gate_is_offline_by_default() -> None:
    text = (ROOT / "scripts/run_short_drama_commercial_gate.ps1").read_text(
        encoding="utf-8"
    )

    for provider in (
        "XAGENT_MEDIA__DEFAULT_IMAGE_PROVIDER",
        "XAGENT_MEDIA__DEFAULT_VIDEO_PROVIDER",
        "XAGENT_MEDIA__DEFAULT_AUDIO_PROVIDER",
    ):
        assert provider in text
    assert "short-drama-delivery.spec.ts" in text
    assert "scripts/run_backend_commercial_tests.py" in text
    assert "external_provider_acceptance" in text
    assert "not_authorized" in text
    assert "paid_submission_attempted" in text
    assert "pollinations.ai" not in text
    assert "down -v" not in text


def test_short_drama_gate_binds_evidence_to_clean_source_sha() -> None:
    text = (ROOT / "scripts/run_short_drama_commercial_gate.ps1").read_text(
        encoding="utf-8"
    )

    assert "rev-parse HEAD" in text
    assert "status --porcelain" in text
    assert "source_sha" in text
    assert "Test-DeliveryBundle" in text
    assert "playwright_retries = 0" in text
