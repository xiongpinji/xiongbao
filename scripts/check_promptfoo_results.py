from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the Promptfoo CI result matrix"
    )
    parser.add_argument("result", type=Path)
    parser.add_argument("--expected", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        payload = json.loads(args.result.read_text(encoding="utf-8"))
        stats = payload["results"]["stats"]
        successes = stats["successes"]
        failures = stats["failures"]
        errors = stats["errors"]
        if any(
            type(value) is not int or value < 0
            for value in (successes, failures, errors)
        ):
            raise TypeError("promptfoo stats must be non-negative integers")
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"invalid promptfoo result: {type(exc).__name__}", file=sys.stderr)
        return 1

    executed = successes + failures + errors
    if executed != args.expected:
        print(
            f"expected {args.expected} evaluations, got {executed}",
            file=sys.stderr,
        )
        return 1
    if failures or errors or successes != args.expected:
        print(
            "promptfoo quality gate failed: "
            f"successes={successes}, failures={failures}, errors={errors}",
            file=sys.stderr,
        )
        return 1

    print(f"promptfoo quality gate passed: {successes}/{args.expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
