from pathlib import Path

import pytest

from scripts.prepare_e2e_workspace import workspace_commands


def test_commands_target_only_named_project_and_workspace() -> None:
    commands = workspace_commands(
        compose_file=Path("deploy/compose/docker-compose.yml"),
        project="xagent-commercial-a1b2c3d4-deadbeef",
    )

    assert commands[0][-4:] == ["api", "mkdir", "-p", "/data/workspace"]
    assert commands[1][-5:] == ["api", "git", "-C", "/data/workspace", "init"]
    assert all(
        "xagent-commercial-a1b2c3d4-deadbeef" in command for command in commands
    )
    assert all("/data/workspace" in command for command in commands)


@pytest.mark.parametrize("project", ["xagent;remove", "xagent-commercial-a1b2c3d4"])
def test_project_name_rejects_invalid_or_legacy_scope(project: str) -> None:
    with pytest.raises(ValueError, match="invalid compose project"):
        workspace_commands(Path("deploy/compose/docker-compose.yml"), project)
