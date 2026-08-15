"""Idempotently initialize the isolated Compose acceptance workspace."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

PROJECT_PATTERN = re.compile(r"^xagent-commercial-[a-f0-9]{8}$")
WORKSPACE = "/data/workspace"


def compose_prefix(compose_file: Path, project: str) -> list[str]:
    if PROJECT_PATTERN.fullmatch(project) is None:
        raise ValueError("invalid compose project")
    return ["docker", "compose", "-p", project, "-f", str(compose_file)]


def workspace_commands(compose_file: Path, project: str) -> list[list[str]]:
    prefix = compose_prefix(compose_file, project) + ["exec", "-T", "api"]
    return [
        prefix + ["mkdir", "-p", WORKSPACE],
        prefix + ["git", "-C", WORKSPACE, "init"],
        prefix
        + ["git", "-C", WORKSPACE, "config", "user.name", "X-Agent E2E"],
        prefix
        + ["git", "-C", WORKSPACE, "config", "user.email", "e2e@xagent.local"],
        prefix
        + [
            "git",
            "-C",
            WORKSPACE,
            "commit",
            "--allow-empty",
            "-m",
            "e2e baseline",
        ],
    ]


def prepare_workspace(compose_file: Path, project: str) -> None:
    prefix = compose_prefix(compose_file, project)
    running = subprocess.run(
        prefix + ["ps", "--services", "--filter", "status=running"],
        check=True,
        capture_output=True,
        text=True,
    )
    if "api" not in running.stdout.splitlines():
        raise RuntimeError("target compose project API is not running")

    exec_prefix = prefix + ["exec", "-T", "api"]
    head = subprocess.run(
        exec_prefix + ["git", "-C", WORKSPACE, "rev-parse", "--verify", "HEAD"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if head.returncode == 0:
        print("workspace already initialized")
        return

    for command in workspace_commands(compose_file, project):
        subprocess.run(command, check=True)
    print("workspace initialized")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    prepare_workspace(args.compose_file, args.project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
