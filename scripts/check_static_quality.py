"""以精确指纹约束 Ruff 与 mypy 的限时存量豁免。"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any


RUFF_GROUPS = {
    "ruff_line_length": {"E501"},
    "ruff_exception_fallback": {"S110", "S112"},
    "ruff_controlled_subprocess": {"S603", "S604", "S607"},
    "ruff_async_blocking": {"ASYNC221", "ASYNC230", "ASYNC240"},
}
MYPY_SHORT_DRAMA_PREFIXES = (
    "xagent/api/v1/creative_studio.py",
    "xagent/domains/creative_studio/",
)


def _stable_digest(findings: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        sorted(findings, key=lambda item: json.dumps(item, sort_keys=True)),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _relative_source_path(filename: str) -> str:
    normalized = filename.replace("\\", "/")
    marker = "/apps/api/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return normalized.removeprefix("./")


def parse_ruff_findings(output: str) -> dict[str, list[dict[str, Any]]]:
    raw = json.loads(output)
    if not isinstance(raw, list):
        raise ValueError("Ruff JSON 输出必须是数组")
    groups = {name: [] for name in RUFF_GROUPS}
    for item in raw:
        code = str(item.get("code") or "")
        group = next((name for name, codes in RUFF_GROUPS.items() if code in codes), None)
        if group is None:
            raise ValueError(f"存在未分类 Ruff 问题: {code}")
        location = item.get("location") or {}
        groups[group].append(
            {
                "path": _relative_source_path(str(item.get("filename") or "")),
                "code": code,
                "row": int(location.get("row") or 0),
                "column": int(location.get("column") or 0),
            }
        )
    return groups


_MYPY_ERROR = re.compile(
    r"^(?P<path>.+?):(?P<row>\d+): error: .+?\s+\[(?P<code>[^\]]+)\]\s*$"
)


def parse_mypy_findings(output: str) -> dict[str, list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    for line in output.splitlines():
        if ": error:" not in line:
            continue
        match = _MYPY_ERROR.match(line.strip())
        if match is None:
            raise ValueError(f"无法解析 mypy 问题: {line}")
        path = _relative_source_path(match.group("path"))
        if not path.startswith(MYPY_SHORT_DRAMA_PREFIXES):
            raise ValueError(f"Web/API 范围出现未豁免 mypy 问题: {path}")
        findings.append(
            {
                "path": path,
                "code": match.group("code"),
                "row": int(match.group("row")),
            }
        )
    return {"mypy_short_drama_excluded": findings}


def summarize(groups: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    return {
        name: {"count": len(findings), "sha256": _stable_digest(findings)}
        for name, findings in groups.items()
    }


def validate_baseline(
    current: dict[str, dict[str, Any]],
    baseline: dict[str, Any],
    *,
    today: date,
) -> list[str]:
    errors: list[str] = []
    if set(current) != set(baseline):
        return ["质量豁免分组与当前扫描分组不一致"]
    required = {"count", "sha256", "owner", "reason", "expires_on", "scope"}
    for name, actual in current.items():
        expected = baseline[name]
        if not isinstance(expected, dict) or set(expected) != required:
            errors.append(f"{name}: 豁免元数据字段不完整")
            continue
        try:
            expiry = date.fromisoformat(str(expected["expires_on"]))
        except ValueError:
            errors.append(f"{name}: expires_on 不是 ISO 日期")
            continue
        if today > expiry:
            errors.append(f"{name}: 豁免已于 {expiry.isoformat()} 到期")
        for field in ("owner", "reason", "scope"):
            if not isinstance(expected[field], str) or not expected[field].strip():
                errors.append(f"{name}: {field} 不能为空")
        if actual != {"count": expected["count"], "sha256": expected["sha256"]}:
            errors.append(
                f"{name}: 精确指纹不匹配，当前 {actual['count']} / {actual['sha256']}"
            )
    return errors


def _tool_command(tool: str, *args: str) -> list[str]:
    if tool == "mypy":
        bootstrap = (
            "import runpy,sys,sysconfig;"
            "sys.path.append(sysconfig.get_paths()['purelib']);"
            "module=sys.argv.pop(1);"
            "runpy.run_module(module,run_name='__main__')"
        )
        return [sys.executable, "-S", "-c", bootstrap, tool, *args]
    suffix = ".exe" if sys.platform == "win32" else ""
    adjacent = Path(sys.executable).with_name(f"{tool}{suffix}")
    executable = str(adjacent) if adjacent.is_file() else shutil.which(tool)
    if not executable:
        raise RuntimeError(f"找不到静态检查工具: {tool}")
    return [executable, *args]


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
        ruff = _run(
            _tool_command("ruff", "check", "xagent", "tests", "--output-format", "json"),
            cwd=api_root,
        )
        mypy = _run(
            _tool_command("mypy", "xagent", "--ignore-missing-imports"),
            cwd=api_root,
        )
        current = summarize(
            {
                **parse_ruff_findings(ruff.stdout),
                **parse_mypy_findings(mypy.stdout + "\n" + mypy.stderr),
            }
        )
        errors = validate_baseline(current, baseline, today=date.today())
    except (
        OSError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"静态质量门禁执行失败: {exc}", file=sys.stderr)
        return 1

    for name, actual in current.items():
        meta = baseline.get(name, {})
        print(
            f"{name}: {actual['count']} findings, sha256={actual['sha256']}, "
            f"owner={meta.get('owner')}, "
            f"expires_on={meta.get('expires_on')}"
        )
    if errors:
        for error in errors:
            print(f"静态质量门禁失败: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
