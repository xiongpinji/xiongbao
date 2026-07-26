#!/usr/bin/env python3
"""Compare two Helm environment values files and output a structured diff.

Usage:
  python scripts/render_env_diff.py --from dev --to prod
  python scripts/render_env_diff.py --from staging --to enterprise
  python scripts/render_env_diff.py --from dev --to prod --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    raise SystemExit(1)


REPO_ROOT = Path(__file__).resolve().parents[1]
HELM_DIR = REPO_ROOT / "deploy" / "helm"
ENVIRONMENTS_DIR = HELM_DIR / "environments"


def load_values(env: str) -> dict:
    """Load base values merged with environment overlay."""
    base_path = HELM_DIR / "values.yaml"
    with open(base_path, encoding="utf-8") as f:
        base = yaml.safe_load(f) or {}

    env_path = ENVIRONMENTS_DIR / f"values-{env}.yaml"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            overlay = yaml.safe_load(f) or {}
        base = _deep_merge(base, overlay)

    return base


def _deep_merge(base: dict, overlay: dict) -> dict:
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def flatten(d: dict, prefix: str = "") -> dict[str, str]:
    """Flatten nested dict into dotted keys."""
    items: dict[str, str] = {}
    for key, value in d.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            items.update(flatten(value, full_key))
        else:
            items[full_key] = repr(value)
    return items


def compute_diff(from_vals: dict, to_vals: dict) -> list[dict[str, str]]:
    """Compute differences between two flattened value sets."""
    flat_from = flatten(from_vals)
    flat_to = flatten(to_vals)

    all_keys = sorted(set(flat_from.keys()) | set(flat_to.keys()))
    diffs: list[dict[str, str]] = []

    for key in all_keys:
        old = flat_from.get(key, "<absent>")
        new = flat_to.get(key, "<absent>")
        if old != new:
            diffs.append({"key": key, "from": old, "to": new})

    return diffs


def render_markdown(diffs: list[dict[str, str]], env_from: str, env_to: str) -> str:
    lines = [
        f"# Values Diff: {env_from} -> {env_to}",
        "",
        f"Total differences: {len(diffs)}",
        "",
        "| Key | From | To |",
        "|-----|------|----|",
    ]
    for d in diffs:
        lines.append(f"| `{d['key']}` | `{d['from']}` | `{d['to']}` |")
    lines.append("")
    return "\n".join(lines)


def render_json(diffs: list[dict[str, str]], env_from: str, env_to: str) -> str:
    return json.dumps(
        {"from": env_from, "to": env_to, "total_diffs": len(diffs), "changes": diffs},
        indent=2,
        ensure_ascii=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="env_from", required=True, choices=["dev", "staging", "prod", "enterprise"])
    parser.add_argument("--to", dest="env_to", required=True, choices=["dev", "staging", "prod", "enterprise"])
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()

    from_vals = load_values(args.env_from)
    to_vals = load_values(args.env_to)
    diffs = compute_diff(from_vals, to_vals)

    if args.format == "json":
        print(render_json(diffs, args.env_from, args.env_to))
    else:
        print(render_markdown(diffs, args.env_from, args.env_to))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
