#!/usr/bin/env python3
"""Run the roadmap-v2 capacity probe with a stable CLI wrapper.

This wrapper does not replace Locust. It standardizes how roadmap-v2 runs the
first capacity probe so operators do not need to remember the full command line.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCUSTFILE = REPO_ROOT / "tests" / "load" / "locustfile.py"


def build_command(host: str, users: int, rate: int, duration: str) -> list[str]:
    return [
        "locust",
        "-f",
        str(LOCUSTFILE),
        "--host",
        host,
        "--headless",
        "-u",
        str(users),
        "-r",
        str(rate),
        "-t",
        duration,
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="http://127.0.0.1:8000")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--rate", type=int, default=5)
    parser.add_argument("--duration", default="60s")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the Locust command without executing it.",
    )
    args = parser.parse_args()

    command = build_command(args.host, args.users, args.rate, args.duration)
    print("capacity_probe_command=")
    print(shlex.join(command))

    if args.dry_run:
        return 0

    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
