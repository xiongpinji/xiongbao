from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_release_versions import verify_versions


ROOT = Path(__file__).resolve().parents[2]
VERSION_FILES = (
    "apps/api/pyproject.toml",
    "apps/web/package.json",
    "apps/api/xagent/__init__.py",
    "deploy/helm/Chart.yaml",
    "apps/desktop/Cargo.toml",
    "apps/desktop/tauri.conf.json",
    "README.md",
)


def _copy_version_files(target_root: Path) -> None:
    for relative in VERSION_FILES:
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    replacements = {
        "apps/api/xagent/__init__.py": (('__version__ = "1.0.0"', '__version__ = "1.1.3"'),),
        "deploy/helm/Chart.yaml": (
            ("version: 1.0.0", "version: 1.1.3"),
            ('appVersion: "1.0.0"', 'appVersion: "1.1.3"'),
        ),
        "apps/desktop/Cargo.toml": (('version = "0.1.0"', 'version = "1.1.3"'),),
        "apps/desktop/tauri.conf.json": (
            ('"version": "0.1.0"', '"version": "1.1.3"'),
        ),
    }
    for relative, pairs in replacements.items():
        target = target_root / relative
        content = target.read_text(encoding="utf-8")
        for old, new in pairs:
            if old in content:
                content = content.replace(old, new, 1)
            else:
                assert new in content
        target.write_text(content, encoding="utf-8")


def test_current_tree_has_one_product_version() -> None:
    assert verify_versions(ROOT, tag="v1.1.3") == []


@pytest.mark.parametrize(
    ("relative", "old", "new", "expected"),
    (
        (
            "apps/api/xagent/__init__.py",
            '__version__ = "1.1.3"',
            '__version__ = "9.9.9"',
            "Python runtime version 9.9.9 != API version 1.1.3",
        ),
        (
            "deploy/helm/Chart.yaml",
            "version: 1.1.3",
            "version: 9.9.9",
            "Helm chart version 9.9.9 != API version 1.1.3",
        ),
        (
            "deploy/helm/Chart.yaml",
            'appVersion: "1.1.3"',
            'appVersion: "9.9.9"',
            "Helm appVersion 9.9.9 != API version 1.1.3",
        ),
        (
            "apps/desktop/Cargo.toml",
            'version = "1.1.3"',
            'version = "9.9.9"',
            "Tauri Cargo version 9.9.9 != API version 1.1.3",
        ),
        (
            "apps/desktop/tauri.conf.json",
            '"version": "1.1.3"',
            '"version": "9.9.9"',
            "Tauri config version 9.9.9 != API version 1.1.3",
        ),
    ),
)
def test_runtime_manifest_drift_is_rejected(
    tmp_path: Path,
    relative: str,
    old: str,
    new: str,
    expected: str,
) -> None:
    _copy_version_files(tmp_path)
    target = tmp_path / relative
    content = target.read_text(encoding="utf-8")
    assert old in content
    target.write_text(content.replace(old, new, 1), encoding="utf-8")

    assert verify_versions(tmp_path) == [expected]
