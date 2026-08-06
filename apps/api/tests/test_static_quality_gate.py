"""精确静态质量豁免门禁测试。"""

from __future__ import annotations

import importlib.util
from datetime import date
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


def test_static_quality_uses_exact_finding_identity() -> None:
    gate = _load_quality_gate()
    groups = gate.parse_ruff_findings(
        '[{"filename":"/repo/apps/api/xagent/a.py","code":"E501",'
        '"location":{"row":3,"column":101}}]'
    )
    summary = gate.summarize(groups)

    assert summary["ruff_line_length"]["count"] == 1
    assert len(summary["ruff_line_length"]["sha256"]) == 64
    assert groups["ruff_line_length"][0] == {
        "path": "xagent/a.py",
        "code": "E501",
        "row": 3,
        "column": 101,
    }


def test_mypy_exemption_rejects_web_api_scope_error() -> None:
    gate = _load_quality_gate()

    try:
        gate.parse_mypy_findings(
            "xagent/api/v1/agents.py:10: error: broken [assignment]"
        )
    except ValueError as exc:
        assert "Web/API 范围" in str(exc)
    else:
        raise AssertionError("Web/API mypy 问题必须被拒绝")


def test_static_quality_rejects_expired_or_changed_fingerprint() -> None:
    gate = _load_quality_gate()
    current = {"group": {"count": 1, "sha256": "current"}}
    baseline = {
        "group": {
            "count": 1,
            "sha256": "old",
            "owner": "backend-platform",
            "reason": "legacy debt",
            "expires_on": "2026-08-06",
            "scope": "one finding",
        }
    }

    errors = gate.validate_baseline(current, baseline, today=date(2026, 8, 7))

    assert any("到期" in error for error in errors)
    assert any("指纹不匹配" in error for error in errors)
