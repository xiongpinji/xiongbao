"""校验 API、Web、README 与发布标签的版本一致性。"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from pathlib import Path

README_VERSION_PATTERN = re.compile(r"\*\*当前 Web/API 版本：([^*]+)\*\*")


def _read_assignment(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id == name
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                return node.value.value
    raise ValueError(f"{name} string assignment not found")


def _read_yaml_scalar(path: Path, name: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() == name:
            return value.strip().strip('"').strip("'")
    raise ValueError(f"{name} scalar not found")


def verify_versions(root: Path, *, tag: str | None = None) -> list[str]:
    errors: list[str] = []
    try:
        api_data = tomllib.loads(
            (root / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8")
        )
        api_version = str(api_data["project"]["version"])
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        return [f"API 版本读取失败: {exc}"]

    try:
        web_data = json.loads(
            (root / "apps" / "web" / "package.json").read_text(encoding="utf-8")
        )
        web_version = str(web_data["version"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"Web 版本读取失败: {exc}")
    else:
        if web_version != api_version:
            errors.append(f"Web version {web_version} != API version {api_version}")

    try:
        readme = (root / "README.md").read_text(encoding="utf-8")
        match = README_VERSION_PATTERN.search(readme)
        if match is None:
            errors.append("README 缺少当前 Web/API 版本")
        elif match.group(1).strip() != api_version:
            errors.append(
                f"README version {match.group(1).strip()} != API version {api_version}"
            )
    except OSError as exc:
        errors.append(f"README 版本读取失败: {exc}")

    try:
        runtime_version = _read_assignment(
            root / "apps" / "api" / "xagent" / "__init__.py", "__version__"
        )
    except (OSError, SyntaxError, ValueError) as exc:
        errors.append(f"Python runtime 版本读取失败: {exc}")
    else:
        if runtime_version != api_version:
            errors.append(
                f"Python runtime version {runtime_version} != API version {api_version}"
            )

    try:
        chart_path = root / "deploy" / "helm" / "Chart.yaml"
        helm_chart_version = _read_yaml_scalar(chart_path, "version")
        helm_app_version = _read_yaml_scalar(chart_path, "appVersion")
    except (OSError, ValueError) as exc:
        errors.append(f"Helm 版本读取失败: {exc}")
    else:
        if helm_chart_version != api_version:
            errors.append(
                f"Helm chart version {helm_chart_version} != API version {api_version}"
            )
        if helm_app_version != api_version:
            errors.append(
                f"Helm appVersion {helm_app_version} != API version {api_version}"
            )

    try:
        cargo_data = tomllib.loads(
            (root / "apps" / "desktop" / "Cargo.toml").read_text(encoding="utf-8")
        )
        cargo_version = str(cargo_data["package"]["version"])
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"Tauri Cargo 版本读取失败: {exc}")
    else:
        if cargo_version != api_version:
            errors.append(
                f"Tauri Cargo version {cargo_version} != API version {api_version}"
            )

    try:
        tauri_data = json.loads(
            (root / "apps" / "desktop" / "tauri.conf.json").read_text(encoding="utf-8")
        )
        tauri_version = str(tauri_data["version"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"Tauri config 版本读取失败: {exc}")
    else:
        if tauri_version != api_version:
            errors.append(
                f"Tauri config version {tauri_version} != API version {api_version}"
            )

    if tag is not None:
        tag_version = tag.removeprefix("v")
        if tag_version != api_version:
            errors.append(f"tag version {tag_version} != API version {api_version}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="待发布标签，例如 v1.0.0")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    errors = verify_versions(root, tag=args.tag)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"Web/API release versions match{f' tag {args.tag}' if args.tag else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
