from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_api_runtime_image_is_non_root_and_has_no_dev_extra() -> None:
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")

    assert "AS builder" in dockerfile
    assert '".[dev]"' not in dockerfile
    assert "--require-hashes -r requirements.lock" in dockerfile
    assert "USER 10001:10001" in dockerfile
    runtime = dockerfile.split("FROM python:3.11-slim AS runtime", 1)[1]
    assert "build-essential" not in runtime
    assert "git" in runtime


def test_api_runtime_removes_build_only_python_tooling() -> None:
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile.split("FROM python:3.11-slim AS runtime", 1)[1]

    assert "/opt/venv/bin/pip uninstall --yes setuptools wheel" in runtime
    assert "/usr/local/bin/python -m pip uninstall --yes setuptools wheel" in runtime


def test_api_runtime_keeps_operational_assets() -> None:
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile.split("FROM python:3.11-slim AS runtime", 1)[1]

    assert "migrations" in runtime
    assert "alembic.ini" in runtime
    assert "scripts/post_deploy_summary.py" in runtime
    assert "scripts/collect_ops_evidence.py" in runtime
    assert "scripts/auto_archive_evidence.py" in runtime


def test_python_runtime_lock_exists_and_uses_hashes() -> None:
    lock = (ROOT / "apps/api/requirements.lock").read_text(encoding="utf-8")

    assert "--python-platform x86_64-unknown-linux-gnu" in lock
    assert "pywin32==" not in lock
    assert "--hash=sha256:" in lock
    assert "fastapi==" in lock
    assert "litellm==" in lock


def test_python_build_backend_is_locked_and_not_downloaded_in_isolation() -> None:
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")
    lock = (ROOT / "apps/api/build-requirements.lock").read_text(encoding="utf-8")

    assert "--require-hashes -r build-requirements.lock" in dockerfile
    assert "--no-build-isolation" in dockerfile
    assert "--hash=sha256:" in lock
    assert "hatchling==" in lock
