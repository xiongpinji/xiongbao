from __future__ import annotations

import json
from pathlib import Path

from scripts.migrate_llm_overrides import MigrationReport, main, migrate


def test_migration_strips_raw_secrets_and_preserves_refs(tmp_path: Path) -> None:
    target = tmp_path / "llm_config_overrides.json"
    target.write_text(
        json.dumps({
            "default_model": "ollama/qwen3:4b",
            "openai_api_key": "historical-raw-secret",
            "deepseek_api_key": "SECRETREF:env:DEEPSEEK_API_KEY",
        }),
        encoding="utf-8",
    )

    report = migrate(target, apply=False)

    assert report == MigrationReport(
        path=target,
        removed_fields=("openai_api_key",),
        changed=True,
    )
    assert "historical-raw-secret" in target.read_text(encoding="utf-8")

    migrate(target, apply=True)

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "deepseek_api_key": "SECRETREF:env:DEEPSEEK_API_KEY",
        "default_model": "ollama/qwen3:4b",
    }


def test_migration_does_not_rewrite_clean_file(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "llm_config_overrides.json"
    target.write_text(
        '{"openai_api_key":"SECRETREF:file:/run/secrets/openai"}',
        encoding="utf-8",
    )
    writes: list[object] = []
    monkeypatch.setattr(
        "scripts.migrate_llm_overrides.write_private_json",
        lambda path, value: writes.append((path, value)),
    )

    report = migrate(target, apply=True)

    assert report.changed is False
    assert report.removed_fields == ()
    assert writes == []


def test_cli_output_contains_field_names_but_not_secret_values(
    tmp_path: Path, capsys
) -> None:
    target = tmp_path / "llm_config_overrides.json"
    target.write_text(
        '{"anthropic_api_key":"never-print-this","proxy_url":"http://proxy"}',
        encoding="utf-8",
    )

    assert main([str(target)]) == 0

    output = capsys.readouterr().out
    assert "anthropic_api_key" in output
    assert "never-print-this" not in output
    assert "dry-run" in output
