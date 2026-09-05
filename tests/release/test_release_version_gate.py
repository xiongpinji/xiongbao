from __future__ import annotations

import re
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


def _api_version() -> str:
    """从版本事实源（apps/api/pyproject.toml）动态读取当前产品版本。"""
    text = (ROOT / "apps/api/pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
    assert match is not None, "pyproject.toml 缺少 version 字段"
    return match.group(1)


V = _api_version()


def _copy_version_files(target_root: Path) -> None:
    for relative in VERSION_FILES:
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    replacements = {
        "apps/api/xagent/__init__.py": (('__version__ = "1.0.0"', f'__version__ = "{V}"'),),
        "deploy/helm/Chart.yaml": (
            ("version: 1.0.0", f"version: {V}"),
            ('appVersion: "1.0.0"', f'appVersion: "{V}"'),
        ),
        "apps/desktop/Cargo.toml": (('version = "0.1.0"', f'version = "{V}"'),),
        "apps/desktop/tauri.conf.json": (
            ('"version": "0.1.0"', f'"version": "{V}"'),
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
    assert verify_versions(ROOT, tag=f"v{V}") == []


@pytest.mark.parametrize(
    ("relative", "old", "new", "expected"),
    (
        (
            "apps/api/xagent/__init__.py",
            f'__version__ = "{V}"',
            '__version__ = "9.9.9"',
            f"Python runtime version 9.9.9 != API version {V}",
        ),
        (
            "deploy/helm/Chart.yaml",
            f"version: {V}",
            "version: 9.9.9",
            f"Helm chart version 9.9.9 != API version {V}",
        ),
        (
            "deploy/helm/Chart.yaml",
            f'appVersion: "{V}"',
            'appVersion: "9.9.9"',
            f"Helm appVersion 9.9.9 != API version {V}",
        ),
        (
            "apps/desktop/Cargo.toml",
            f'version = "{V}"',
            'version = "9.9.9"',
            f"Tauri Cargo version 9.9.9 != API version {V}",
        ),
        (
            "apps/desktop/tauri.conf.json",
            f'"version": "{V}"',
            '"version": "9.9.9"',
            f"Tauri config version 9.9.9 != API version {V}",
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
