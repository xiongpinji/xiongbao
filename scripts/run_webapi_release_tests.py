"""Run the backend tests that belong to the Web/API release scope."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"

# Product areas explicitly excluded from the Web/API R2 release candidate.
EXCLUDED_TEST_MODULES = (
    "tests/test_audio_providers.py",
    "tests/test_canvas_extras.py",
    "tests/test_canvas_workflow.py",
    "tests/test_creative_persistence.py",
    "tests/test_creative_studio.py",
    "tests/test_e2e_drama_canvas.py",
    "tests/test_editor.py",
    "tests/test_media.py",
    "tests/test_media_task.py",
    "tests/test_pipeline.py",
    "tests/test_producer.py",
    "tests/test_sandbox_e2b.py",
)
EXCLUDED_TEST_NODES = (
    "tests/test_runtime_runs.py::test_runs_api_normalizes_creative_production_status",
)


def main() -> int:
    os.chdir(API_ROOT)
    sys.path.insert(0, str(API_ROOT))
    args = ["-ra", "-q"]
    args.extend(f"--ignore={path}" for path in EXCLUDED_TEST_MODULES)
    args.extend(f"--deselect={node}" for node in EXCLUDED_TEST_NODES)
    return pytest.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
