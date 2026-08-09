"""file_write 必须在当前 workspace 内安全、原子地写入。"""

from __future__ import annotations

from pathlib import Path

import pytest
from xagent.adapters.tools.base import ToolContext
from xagent.adapters.tools.power_tools import FileWriteTool
from xagent.core import workspace as ws_mod
from xagent.enterprise.auth.principal import Principal


@pytest.fixture
def workspace(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    token = ws_mod.set_workspace(root)
    try:
        yield root
    finally:
        ws_mod.reset_workspace(token)


def _context() -> ToolContext:
    return ToolContext(
        principal=Principal(
            user_id="u",
            tenant_id="t",
            roles=frozenset({"member"}),
        )
    )


async def test_file_write_rejects_empty_path_without_side_effects(
    workspace: Path,
) -> None:
    result = await FileWriteTool().run(
        {"path": "", "content": "blocked"}, _context()
    )

    assert result.ok is False
    assert "路径不能为空" in str(result.error)
    assert list(workspace.iterdir()) == []


async def test_file_write_rejects_parent_traversal(workspace: Path) -> None:
    outside = workspace.parent / "escape.txt"

    result = await FileWriteTool().run(
        {"path": "../escape.txt", "content": "blocked"}, _context()
    )

    assert result.ok is False
    assert "穿越" in str(result.error)
    assert not outside.exists()


async def test_file_write_rejects_absolute_escape(workspace: Path) -> None:
    outside = workspace.parent / "absolute-escape.txt"

    result = await FileWriteTool().run(
        {"path": str(outside), "content": "blocked"}, _context()
    )

    assert result.ok is False
    assert "workspace" in str(result.error)
    assert not outside.exists()


async def test_file_write_rejects_git_metadata_path(workspace: Path) -> None:
    result = await FileWriteTool().run(
        {"path": ".git/config", "content": "blocked"}, _context()
    )

    assert result.ok is False
    assert "Git 元数据" in str(result.error)
    assert not (workspace / ".git").exists()


async def test_file_write_rejects_symlink_escape(workspace: Path) -> None:
    outside = workspace.parent / "outside"
    outside.mkdir()
    link = workspace / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"当前 Windows 权限无法创建符号链接: {exc}")

    result = await FileWriteTool().run(
        {"path": "link/escape.txt", "content": "blocked"}, _context()
    )

    assert result.ok is False
    assert "workspace" in str(result.error)
    assert not (outside / "escape.txt").exists()


async def test_file_write_atomically_writes_relative_workspace_path(
    workspace: Path,
) -> None:
    target = workspace / "nested" / "artifact.txt"
    target.parent.mkdir()
    target.write_text("old", encoding="utf-8")

    result = await FileWriteTool().run(
        {"path": "nested/artifact.txt", "content": "new"}, _context()
    )

    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "new"
    assert list(target.parent.glob(".artifact.txt.*.tmp")) == []


async def test_file_write_allows_absolute_path_inside_workspace(
    workspace: Path,
) -> None:
    target = workspace / "absolute-inside.txt"

    result = await FileWriteTool().run(
        {"path": str(target), "content": "inside"}, _context()
    )

    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "inside"
