"""Run the complete API test suite for the commercial delivery gate."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"


def pytest_args() -> list[str]:
    return ["-ra", "-q", "tests"]


def main() -> int:
    os.chdir(API_ROOT)
    sys.path.insert(0, str(API_ROOT))
    return pytest.main(pytest_args())


if __name__ == "__main__":
    raise SystemExit(main())
