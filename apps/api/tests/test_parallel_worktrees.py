"""V3-3 并行子代理 git worktree 隔离测试。

- 工作区 contextvar 解析与并发隔离
- worktree 隔离执行：两子代理各自工作区写文件 → 主工作区零污染 + 各自 diff 采集 + 清理
- 非 git 工作区降级为非隔离执行（诚实标记 isolated=False）
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from xagent.core import workspace as ws_mod
from xagent.core.orchestration import parallel
from xagent.core.orchestration.parallel import SubTask, run_parallel_agents
from xagent.enterprise.auth.principal import Principal


def _principal() -> Principal:
    return Principal(
        user_id="t", tenant_id="default", roles=frozenset({"admin"}),
        scopes=frozenset(), is_anonymous=False,
    )


class _FakeRun:
    def __init__(self, answer: str):
        self._answer = answer

    def to_dict(self) -> dict:
        return {"final_answer": self._answer, "steps": 1}


def _make_fake_run_agent(write_file: str | None = None):
    """假 run_agent：记录当前工作区；可选在工作区写一个文件。"""

    async def _fake(goal, *, principal, role_name=None, capabilities=None, run_id=None):
        ws = ws_mod.get_workspace()
        if write_file:
            (ws / write_file).write_text(f"by {run_id}", encoding="utf-8")
        return _FakeRun(f"done in {ws}")

    return _fake


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init", "-b", "main"],
        ["config", "user.email", "t@t"],
        ["config", "user.name", "t"],
    ):
        subprocess.run(["git", *args], cwd=path, check=True,
                       capture_output=True)
    (path / "README.md").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True,
                   capture_output=True)


# ─── contextvar 工作区解析 ───


def test_workspace_default_and_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XAGENT_WORKSPACE", str(tmp_path))
    # 进程默认（模块加载时快照，与 env 一致或回退 home）——这里只验证覆盖语义
    token = ws_mod.set_workspace(tmp_path / "wt-a")
    try:
        assert ws_mod.get_workspace() == tmp_path / "wt-a"
    finally:
        ws_mod.reset_workspace(token)
    assert ws_mod.get_workspace() == ws_mod.default_workspace()


async def test_workspace_concurrent_isolation(tmp_path) -> None:
    """两个并发任务各自覆盖工作区，互不可见。"""
    seen: dict[str, str] = {}

    async def worker(name: str, path: Path) -> None:
        token = ws_mod.set_workspace(path)
        try:
            await asyncio.sleep(0.01)  # 让出事件循环制造并发交叉
            seen[name] = str(ws_mod.get_workspace())
        finally:
            ws_mod.reset_workspace(token)

    await asyncio.gather(
        worker("a", tmp_path / "wt-a"), worker("b", tmp_path / "wt-b")
    )
    assert seen["a"].endswith("wt-a")
    assert seen["b"].endswith("wt-b")


# ─── worktree 隔离执行 ───


async def test_parallel_with_worktrees_isolation(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setenv("XAGENT_WORKSPACE", str(repo))
    ws_token = ws_mod.set_workspace(repo)
    monkeypatch.setattr(
        parallel, "run_agent", _make_fake_run_agent(write_file="out.txt")
    )
    try:
        result = await run_parallel_agents(
            [SubTask(goal="task one"), SubTask(goal="task two")],
            _principal(),
            use_worktrees=True,
        )
    finally:
        ws_mod.reset_workspace(ws_token)

    assert result.status == "succeeded"
    assert len(result.sub_results) == 2
    for sub in result.sub_results:
        assert sub.isolated is True
        assert ".xagent-worktrees" in sub.worktree_path
        # 各自 worktree 的 diff 已采集（out.txt 新增）
        assert "out.txt" in sub.diff_stat
        assert "out.txt" in sub.diff
        # worktree 已清理
        assert not Path(sub.worktree_path).exists()
    # 主工作区零污染：无 out.txt、git 状态干净、无残留分支
    assert not (repo / "out.txt").exists()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True,
    ).stdout.strip()
    assert status == ""
    branches = subprocess.run(
        ["git", "branch", "--list", "agent/*"], cwd=repo, capture_output=True, text=True,
    ).stdout.strip()
    assert branches == ""


async def test_parallel_worktree_degrades_outside_git_repo(tmp_path, monkeypatch) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("XAGENT_WORKSPACE", str(plain))
    ws_token = ws_mod.set_workspace(plain)
    monkeypatch.setattr(parallel, "run_agent", _make_fake_run_agent())
    try:
        result = await run_parallel_agents(
            [SubTask(goal="solo")], _principal(), use_worktrees=True,
        )
    finally:
        ws_mod.reset_workspace(ws_token)
    assert result.status == "succeeded"
    assert result.sub_results[0].isolated is False  # 诚实降级标记


async def test_parallel_default_no_worktrees(tmp_path, monkeypatch) -> None:
    """默认不启用 worktree（向后兼容）。"""
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setenv("XAGENT_WORKSPACE", str(repo))
    ws_token = ws_mod.set_workspace(repo)
    monkeypatch.setattr(parallel, "run_agent", _make_fake_run_agent())
    try:
        result = await run_parallel_agents([SubTask(goal="solo")], _principal())
    finally:
        ws_mod.reset_workspace(ws_token)
    assert result.sub_results[0].isolated is False
    assert not (repo.parent / ".xagent-worktrees").exists()


async def test_parallel_worktree_result_serializable(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setenv("XAGENT_WORKSPACE", str(repo))
    ws_token = ws_mod.set_workspace(repo)
    monkeypatch.setattr(
        parallel, "run_agent", _make_fake_run_agent(write_file="f.md")
    )
    try:
        result = await run_parallel_agents(
            [SubTask(goal="g")], _principal(), use_worktrees=True,
        )
    finally:
        ws_mod.reset_workspace(ws_token)
    d = result.to_dict()
    assert d["sub_results"][0]["isolated"] is True
    assert "f.md" in d["sub_results"][0]["diff_stat"]
