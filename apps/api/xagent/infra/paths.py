"""Runtime data-path helpers shared by source and installed-package layouts."""

from __future__ import annotations

import os
from pathlib import Path

_SOURCE_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def data_dir() -> Path:
    """Return the writable runtime data root."""

    configured = os.environ.get("XAGENT_DATA_DIR", "").strip()
    return Path(configured).expanduser() if configured else _SOURCE_DATA_DIR


def data_path(*parts: str) -> Path:
    """Return a path below the configured runtime data root."""

    return data_dir().joinpath(*parts)
