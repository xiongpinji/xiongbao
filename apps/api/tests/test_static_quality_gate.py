"""静态质量基线门禁测试。"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_quality_gate():
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "check_static_quality.py"
    spec = importlib.util.spec_from_file_location("check_static_quality", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载静态质量脚本: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_static_quality_parsers_and_baseline_rejection() -> None:
    gate = _load_quality_gate()

    assert gate.parse_ruff_count('[{"code":"E501"},{"code":"F821"}]') == 2
    assert gate.parse_mypy_count(
        "xagent/a.py:1: error: first\nxagent/b.py:2: note: detail\n"
        "xagent/c.py:3: error: second"
    ) == 2
    assert gate.exceeded(
        {"ruff": 287, "mypy": 74}, {"ruff": 286, "mypy": 74}
    ) == {"ruff": (287, 286)}
