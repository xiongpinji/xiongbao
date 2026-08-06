"""Web/API 发布版本一致性测试。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_version_verifier():
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "verify_release_versions.py"
    spec = importlib.util.spec_from_file_location("verify_release_versions", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载版本校验脚本: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_release_files(root: Path) -> None:
    (root / "apps" / "api").mkdir(parents=True)
    (root / "apps" / "web").mkdir(parents=True)
    (root / "apps" / "api" / "pyproject.toml").write_text(
        '[project]\nname = "xagent"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (root / "apps" / "web" / "package.json").write_text(
        json.dumps({"name": "xagent-web", "version": "1.0.0"}), encoding="utf-8"
    )
    (root / "README.md").write_text(
        "**当前 Web/API 版本：1.0.0**\n", encoding="utf-8"
    )


def test_verify_release_versions_rejects_readme_and_tag_drift(tmp_path: Path) -> None:
    verifier = _load_version_verifier()
    _write_release_files(tmp_path)

    assert verifier.verify_versions(tmp_path, tag="v1.0.0") == []

    (tmp_path / "README.md").write_text(
        "**当前 Web/API 版本：0.1.0**\n", encoding="utf-8"
    )
    assert "README" in "\n".join(verifier.verify_versions(tmp_path, tag="v1.0.0"))
    assert "tag" in "\n".join(verifier.verify_versions(tmp_path, tag="v1.0.1"))
