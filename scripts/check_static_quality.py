"""阻止 Ruff 与 mypy 存量问题数量反弹。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def parse_ruff_count(output: str) -> int:
    findings = json.loads(output)
    if not isinstance(findings, list):
        raise ValueError("Ruff JSON 输出必须是数组")
    return len(findings)


def parse_mypy_count(output: str) -> int:
    return sum(1 for line in output.splitlines() if ": error:" in line)


def exceeded(
    current: dict[str, int], baseline: dict[str, int]
) -> dict[str, tuple[int, int]]:
    return {
        name: (current[name], limit)
        for name, limit in baseline.items()
        if current[name] > limit
    }


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    if result.returncode not in {0, 1}:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            f"命令异常退出 ({result.returncode}): {' '.join(command)}\n{detail}"
        )
    return result


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    api_root = repo_root / "apps" / "api"
    baseline_path = repo_root / ".quality-baseline.json"

    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        if not isinstance(baseline, dict):
            raise ValueError("质量基线必须是 JSON 对象")
        expected_keys = {"ruff", "mypy"}
        if set(baseline) != expected_keys or not all(
            isinstance(value, int) and value >= 0 for value in baseline.values()
        ):
            raise ValueError("质量基线必须只包含非负整数 ruff 和 mypy")

        ruff = _run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "xagent",
                "tests",
                "--output-format",
                "json",
            ],
            cwd=api_root,
        )
        mypy = _run(
            [
                sys.executable,
                "-m",
                "mypy",
                "xagent",
                "--ignore-missing-imports",
            ],
            cwd=api_root,
        )
        current = {
            "ruff": parse_ruff_count(ruff.stdout),
            "mypy": parse_mypy_count(mypy.stdout + "\n" + mypy.stderr),
        }
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"静态质量门禁执行失败: {exc}", file=sys.stderr)
        return 1

    regressions = exceeded(current, baseline)
    for name in ("ruff", "mypy"):
        print(f"{name}: {current[name]} <= {baseline[name]}")
    if regressions:
        for name, (count, limit) in regressions.items():
            print(f"静态质量反弹: {name}={count}, baseline={limit}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
