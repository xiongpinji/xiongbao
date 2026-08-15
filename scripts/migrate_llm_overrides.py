"""Remove plaintext provider keys from the persisted LLM override file."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from xagent.infra.secrets import is_secret_ref  # noqa: E402
from xagent.infra.secure_json import write_private_json  # noqa: E402

SENSITIVE_FIELDS = frozenset({
    "proxy_api_key",
    "openai_api_key",
    "anthropic_api_key",
    "deepseek_api_key",
})
DEFAULT_PATH = ROOT / "apps" / "data" / "llm_config_overrides.json"


@dataclass(frozen=True)
class MigrationReport:
    path: Path
    removed_fields: tuple[str, ...]
    changed: bool


def migrate(path: Path, *, apply: bool) -> MigrationReport:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("LLM override root must be an object")

    removed_fields = tuple(sorted(
        key
        for key, value in data.items()
        if key in SENSITIVE_FIELDS and not is_secret_ref(value)
    ))
    if apply and removed_fields:
        sanitized = {key: value for key, value in data.items() if key not in removed_fields}
        write_private_json(path, sanitized)
    return MigrationReport(
        path=path,
        removed_fields=removed_fields,
        changed=bool(removed_fields),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remove plaintext keys from persisted LLM overrides"
    )
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--apply", action="store_true", help="write sanitized JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    path = args.path.resolve()
    mode = "apply" if args.apply else "dry-run"
    if not path.is_file():
        print(f"path={path} mode={mode} status=missing")
        return 0
    try:
        report = migrate(path, apply=args.apply)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            f"path={path} mode={mode} status=failed error_type={type(exc).__name__}",
            file=sys.stderr,
        )
        return 1

    removed = ",".join(report.removed_fields) or "none"
    print(
        f"path={path} mode={mode} changed={'yes' if report.changed else 'no'} "
        f"removed_fields={removed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
