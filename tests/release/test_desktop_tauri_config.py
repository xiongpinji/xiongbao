import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_tauri_hooks_resolve_web_from_monorepo_apps_directory() -> None:
    config = json.loads(
        (ROOT / "apps/desktop/tauri.conf.json").read_text(encoding="utf-8")
    )

    assert config["build"]["beforeDevCommand"] == "npm --prefix web run dev"
    assert config["build"]["beforeBuildCommand"] == "npm --prefix web run build"
    assert config["build"]["frontendDist"] == "../web/dist"
    assert config["bundle"]["targets"] == ["msi", "nsis"]
    assert "icons/icon.ico" in config["bundle"]["icon"]
