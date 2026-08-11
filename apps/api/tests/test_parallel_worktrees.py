"""V3-3 并行子代理 git worktree 隔离测试。

- 工作区 contextvar 解析与并发隔离
- worktree 隔离执行：两子代理各自工作区写文件 → 主工作区零污染 + 各自 diff 采集 + 清理
- 非 git 工作区降级为非隔离执行（诚实标记 isolated=False）
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from xagent.adapters.llm.base import LLMResponse, ToolCall
from xagent.core import workspace as ws_mod
from xagent.core.orchestration import loop as loop_mod
from xagent.core.orchestration import parallel
from xagent.core.orchestration.parallel import (
    SubTask,
    cancel_running_development_task,
    run_parallel_agents,
)
from xagent.domains.development_tasks import (
    get_development_task,
    list_development_tasks,
)
from xagent.enterprise.auth.principal import Principal
from xagent.infra.db import Base, get_engine, get_sessionmaker


def _principal() -> Principal:
    return Principal(
        user_id="t", tenant_id="default", roles=frozenset({"admin"}),
        scopes=frozenset(), is_anonymous=False,
    )


class _FakeRun:
    def __init__(
        self,
        answer: str,
        *,
        tools: tuple[str, ...] = (),
        status: str = "succeeded",
        error: str = "",
    ):
        self._answer = answer
        self._tools = tools
        self._status = status
        self._error = error

    def to_dict(self) -> dict:
        return {
            "final_answer": self._answer,
            "steps": 1,
            "status": self._status,
            "error": self._error,
            "events": [
                {"kind": "tool_call", "tool": tool, "step": 1, "content": {}}
                for tool in self._tools
            ],
        }


class _ScriptedDevelopmentLLM:
    """只替代 provider 响应；编排、真实工具与 Git 生命周期均走产品代码。"""

    supports_tools = True

    def __init__(self, actions: list[str], *, repeat_last: bool = False) -> None:
        self.actions = actions
        self.repeat_last = repeat_last
        self.calls = 0
        self.blocked = asyncio.Event()
        self.tool_schemas: list[set[str]] = []

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        return LLMResponse(content="达到执行上限，任务未完成。", model="test")

    async def complete_with_tools(self, messages, tools, **kwargs):  # noqa: ARG002
        self.calls += 1
        self.tool_schemas.append(
            {tool["function"]["name"] for tool in tools}
        )
        index = min(self.calls - 1, len(self.actions) - 1)
        if not self.repeat_last and self.calls > len(self.actions):
            action = "final"
        else:
            action = self.actions[index]
        if action == "write":
            return LLMResponse(
                content="",
                model="test",
                tool_calls=[
                    ToolCall(
                        id=f"call_write_{self.calls}",
                        name="file_write",
                        args={
                            "path": f"artifact-{self.calls}.txt",
                            "content": f"step {self.calls}",
                        },
                    )
                ],
            )
        if action == "echo":
            return LLMResponse(
                content="",
                model="test",
                tool_calls=[
                    ToolCall(id=f"call_echo_{self.calls}", name="echo", args={})
                ],
            )
        if action == "error":
            raise ValueError("provider exploded after write")
        if action == "block":
            self.blocked.set()
            await asyncio.Event().wait()
        return LLMResponse(content="全部完成，已写入真实开发产物。", model="test")

    async def health(self) -> bool:
        return True


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


def _temporary_branches(repo: Path) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads/agent",
            "refs/heads/xagent",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


async def _run_actual_strict_task(
    repo: Path,
    monkeypatch,
    llm: _ScriptedDevelopmentLLM,
    *,
    goal: str,
):
    monkeypatch.setattr(loop_mod, "get_llm_client", lambda: llm)
    ws_token = ws_mod.set_workspace(repo)
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        return await run_parallel_agents(
            [SubTask(goal=goal, capabilities=["file_write"])],
            _principal(),
            use_worktrees=True,
        )
    finally:
        ws_mod.reset_workspace(ws_token)


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
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
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
        assert sub.development_task_id
        assert sub.development_task_status == "awaiting_review"
        assert ".xagent-worktrees" in sub.worktree_path
        # 各自 worktree 的完整结果被保留等待审查。
        assert "out.txt" in sub.diff_stat
        assert "out.txt" in sub.diff
        assert Path(sub.worktree_path).exists()
        async with get_sessionmaker()() as session:
            record = await get_development_task(
                session, "default", sub.development_task_id
            )
        assert record is not None
        assert record.status.value == "awaiting_review"
        assert record.result_commit
        assert Path(record.patch_path).is_file()
        assert "out.txt" in Path(record.patch_path).read_text(encoding="utf-8")

    # 主工作区零污染：无 out.txt、git 状态干净；临时分支保留等待审查。
    assert not (repo / "out.txt").exists()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True,
    ).stdout.strip()
    assert status == ""
    branches = subprocess.run(
        ["git", "branch", "--list", "agent/*"], cwd=repo, capture_output=True, text=True,
    ).stdout.strip()
    assert len(branches.splitlines()) == 2


async def test_isolated_file_write_task_requires_file_write_on_first_turn(
    tmp_path, monkeypatch
) -> None:
    repo = tmp_path / "repo-required-tool"
    _init_git_repo(repo)
    ws_token = ws_mod.set_workspace(repo)
    seen_required_tools: list[str | None] = []

    async def _fake(
        goal,
        *,
        principal,
        role_name=None,
        capabilities=None,
        run_id=None,
        required_first_tool=None,
    ):
        seen_required_tools.append(required_first_tool)
        (ws_mod.get_workspace() / "artifact.txt").write_text(
            f"by {run_id}", encoding="utf-8"
        )
        return _FakeRun("created artifact", tools=("file_write",))

    monkeypatch.setattr(parallel, "run_agent", _fake)
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        result = await run_parallel_agents(
            [SubTask(goal="create artifact", capabilities=["file_write"])],
            _principal(),
            use_worktrees=True,
        )
    finally:
        ws_mod.reset_workspace(ws_token)

    assert result.status == "succeeded"
    assert seen_required_tools == ["file_write"]
    assert "artifact.txt" in result.sub_results[0].diff_stat


async def test_required_file_write_without_tool_call_has_diagnostic_failure(
    tmp_path, monkeypatch
) -> None:
    repo = tmp_path / "repo-missing-required-tool"
    _init_git_repo(repo)
    ws_token = ws_mod.set_workspace(repo)

    async def _fake(*args, **kwargs):  # noqa: ARG001
        return _FakeRun("claimed complete")

    monkeypatch.setattr(parallel, "run_agent", _fake)
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        result = await run_parallel_agents(
            [SubTask(goal="create artifact", capabilities=["file_write"])],
            _principal(),
            use_worktrees=True,
        )
    finally:
        ws_mod.reset_workspace(ws_token)

    sub = result.sub_results[0]
    assert sub.status == "failed"
    assert sub.development_task_status == "failed"
    assert "未调用必需工具 file_write" in sub.error
    assert not Path(sub.worktree_path).exists()
    async with get_sessionmaker()() as session:
        record = await get_development_task(
            session, "default", sub.development_task_id
        )
    assert record is not None
    assert record.status.value == "failed"
    assert "未调用必需工具 file_write" in record.error


async def test_strict_task_rejects_post_write_provider_failure(
    tmp_path, monkeypatch
) -> None:
    repo = tmp_path / "repo-provider-failure"
    _init_git_repo(repo)

    result = await _run_actual_strict_task(
        repo,
        monkeypatch,
        _ScriptedDevelopmentLLM(["write", "error"]),
        goal="provider failure after real write",
    )

    sub = result.sub_results[0]
    assert sub.status == "failed"
    assert sub.development_task_status == "failed"
    assert "provider exploded after write" in sub.error
    assert not Path(sub.worktree_path).exists()
    assert _temporary_branches(repo) == []
    async with get_sessionmaker()() as session:
        record = await get_development_task(
            session, "default", sub.development_task_id
        )
    assert record is not None
    assert record.status.value == "failed"
    assert not Path(record.patch_path).exists()


async def test_strict_task_rejects_post_write_max_steps(
    tmp_path, monkeypatch
) -> None:
    repo = tmp_path / "repo-max-steps"
    _init_git_repo(repo)
    monkeypatch.setattr(loop_mod, "MAX_STEPS", 2)

    result = await _run_actual_strict_task(
        repo,
        monkeypatch,
        _ScriptedDevelopmentLLM(["write"], repeat_last=True),
        goal="keep writing without final answer",
    )

    sub = result.sub_results[0]
    assert sub.status == "failed"
    assert sub.development_task_status == "failed"
    assert "max_steps_exceeded" in sub.error
    assert not Path(sub.worktree_path).exists()
    assert _temporary_branches(repo) == []


async def test_strict_task_schema_and_execution_reject_other_tools(
    tmp_path, monkeypatch
) -> None:
    repo = tmp_path / "repo-strict-tools"
    _init_git_repo(repo)
    llm = _ScriptedDevelopmentLLM(["write", "echo"])
    registry = loop_mod.get_tool_registry()
    original_call = registry.call
    executed_tools: list[str] = []

    async def _record_call(name, args, ctx):
        executed_tools.append(name)
        return await original_call(name, args, ctx)

    monkeypatch.setattr(registry, "call", _record_call)

    result = await _run_actual_strict_task(
        repo,
        monkeypatch,
        llm,
        goal="attempt disallowed tool after write",
    )

    sub = result.sub_results[0]
    assert llm.tool_schemas
    assert all(schema == {"file_write"} for schema in llm.tool_schemas)
    assert sub.status == "failed"
    assert "strict_tool_policy_violation: echo" in sub.error
    assert executed_tools == ["file_write"]
    assert not Path(sub.worktree_path).exists()
    assert _temporary_branches(repo) == []


async def test_strict_real_loop_cancel_after_write_is_cancelled(
    tmp_path, monkeypatch
) -> None:
    repo = tmp_path / "repo-real-cancel"
    _init_git_repo(repo)
    llm = _ScriptedDevelopmentLLM(["write", "block"])
    monkeypatch.setattr(loop_mod, "get_llm_client", lambda: llm)
    ws_token = ws_mod.set_workspace(repo)
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        parallel_task = asyncio.create_task(
            run_parallel_agents(
                [
                    SubTask(
                        goal="real loop cancel after write",
                        capabilities=["file_write"],
                    )
                ],
                _principal(),
                use_worktrees=True,
            )
        )
        await asyncio.wait_for(llm.blocked.wait(), timeout=5)
        async with get_sessionmaker()() as session:
            running = await list_development_tasks(session, "default")
        task_id = next(
            item.task_id
            for item in running
            if item.goal == "real loop cancel after write"
        )
        assert cancel_running_development_task(task_id) is True
        result = await parallel_task
    finally:
        ws_mod.reset_workspace(ws_token)

    sub = result.sub_results[0]
    assert sub.status == "cancelled"
    assert sub.development_task_status == "cancelled"
    assert not Path(sub.worktree_path).exists()
    assert _temporary_branches(repo) == []
    async with get_sessionmaker()() as session:
        record = await get_development_task(session, "default", task_id)
    assert record is not None
    assert record.status.value == "cancelled"
    assert not record.patch_path or not Path(record.patch_path).exists()


async def test_strict_real_loop_timeout_after_write_is_timeout(
    tmp_path, monkeypatch
) -> None:
    repo = tmp_path / "repo-real-timeout"
    _init_git_repo(repo)
    monkeypatch.setattr(parallel, "STRICT_FILE_WRITE_TIMEOUT", 0.05)

    result = await _run_actual_strict_task(
        repo,
        monkeypatch,
        _ScriptedDevelopmentLLM(["write", "block"]),
        goal="real loop timeout after write",
    )

    sub = result.sub_results[0]
    assert sub.status == "timeout"
    assert sub.error == "超时(>0.05s)"
    assert sub.development_task_status == "timeout"
    assert not Path(sub.worktree_path).exists()
    assert _temporary_branches(repo) == []
    async with get_sessionmaker()() as session:
        record = await get_development_task(
            session, "default", sub.development_task_id
        )
    assert record is not None
    assert record.status.value == "timeout"
    assert record.error == "超时(>0.05s)"
    assert not record.patch_path or not Path(record.patch_path).exists()


async def test_strict_file_write_uses_slo_aligned_timeout(
    tmp_path, monkeypatch
) -> None:
    repo = tmp_path / "repo-timeout-budget"
    _init_git_repo(repo)
    captured_timeouts: list[float] = []
    real_wait_for = asyncio.wait_for

    async def _capture_wait_for(awaitable, *, timeout):
        captured_timeouts.append(timeout)
        return await real_wait_for(awaitable, timeout=timeout)

    async def _failed_run_agent(*args, **kwargs):  # noqa: ARG001
        return _FakeRun("", status="failed", error="stop after timeout capture")

    monkeypatch.setattr(parallel.asyncio, "wait_for", _capture_wait_for)
    monkeypatch.setattr(parallel, "run_agent", _failed_run_agent)
    ws_token = ws_mod.set_workspace(repo)
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        result = await run_parallel_agents(
            [SubTask(goal="capture strict timeout", capabilities=["file_write"])],
            _principal(),
            use_worktrees=True,
        )
    finally:
        ws_mod.reset_workspace(ws_token)

    assert result.sub_results[0].status == "failed"
    assert captured_timeouts == [270]


async def test_regular_parallel_task_keeps_default_timeout(monkeypatch) -> None:
    captured_timeouts: list[float] = []
    real_wait_for = asyncio.wait_for

    async def _capture_wait_for(awaitable, *, timeout):
        captured_timeouts.append(timeout)
        return await real_wait_for(awaitable, timeout=timeout)

    async def _successful_run_agent(*args, **kwargs):  # noqa: ARG001
        return _FakeRun("done")

    monkeypatch.setattr(parallel.asyncio, "wait_for", _capture_wait_for)
    monkeypatch.setattr(parallel, "run_agent", _successful_run_agent)

    result = await run_parallel_agents([SubTask(goal="regular")], _principal())

    assert result.sub_results[0].status == "succeeded"
    assert captured_timeouts == [180]


async def test_multi_capability_task_does_not_force_file_write_first(
    tmp_path, monkeypatch
) -> None:
    repo = tmp_path / "repo-multi-capability"
    _init_git_repo(repo)
    ws_token = ws_mod.set_workspace(repo)
    seen_required_tools: list[str | None] = []

    async def _fake(
        *args, required_first_tool=None, run_id=None, **kwargs  # noqa: ARG001
    ):
        seen_required_tools.append(required_first_tool)
        (ws_mod.get_workspace() / "artifact.txt").write_text(
            f"by {run_id}", encoding="utf-8"
        )
        return _FakeRun("created artifact")

    monkeypatch.setattr(parallel, "run_agent", _fake)
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        result = await run_parallel_agents(
            [
                SubTask(
                    goal="inspect then create artifact",
                    capabilities=["file_write", "coding"],
                )
            ],
            _principal(),
            use_worktrees=True,
        )
    finally:
        ws_mod.reset_workspace(ws_token)

    assert result.status == "succeeded"
    assert seen_required_tools == [None]


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


async def test_parallel_worktree_failure_is_recorded_and_cleaned(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    ws_token = ws_mod.set_workspace(repo)

    async def _failing_run_agent(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("agent failed")

    monkeypatch.setattr(parallel, "run_agent", _failing_run_agent)
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        result = await run_parallel_agents(
            [SubTask(goal="will fail")], _principal(), use_worktrees=True
        )
    finally:
        ws_mod.reset_workspace(ws_token)

    sub = result.sub_results[0]
    assert sub.status == "failed"
    assert sub.development_task_status == "failed"
    assert not Path(sub.worktree_path).exists()
    async with get_sessionmaker()() as session:
        record = await get_development_task(session, "default", sub.development_task_id)
    assert record is not None
    assert record.status.value == "failed"
    branches = subprocess.run(
        ["git", "branch", "--list", "agent/*"],
        cwd=repo,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branches == ""


async def test_non_strict_worktree_failed_run_with_diff_is_not_reviewable(
    tmp_path, monkeypatch
) -> None:
    repo = tmp_path / "repo-failed-status"
    _init_git_repo(repo)
    ws_token = ws_mod.set_workspace(repo)

    async def _failed_run(*args, **kwargs):  # noqa: ARG001
        (ws_mod.get_workspace() / "failed.txt").write_text(
            "real diff before failure", encoding="utf-8"
        )
        return _FakeRun(
            "partial result",
            status="failed",
            error="provider failed after coding",
        )

    monkeypatch.setattr(parallel, "run_agent", _failed_run)
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        result = await run_parallel_agents(
            [SubTask(goal="failed coding result", capabilities=["coding"])],
            _principal(),
            use_worktrees=True,
        )
    finally:
        ws_mod.reset_workspace(ws_token)

    sub = result.sub_results[0]
    assert result.status == "failed"
    assert sub.status == "failed"
    assert sub.development_task_status == "failed"
    assert sub.error == "provider failed after coding"
    assert not Path(sub.worktree_path).exists()
    assert _temporary_branches(repo) == []
    async with get_sessionmaker()() as session:
        record = await get_development_task(
            session, "default", sub.development_task_id
        )
    assert record is not None
    assert record.status.value == "failed"
    assert record.error == "provider failed after coding"
    assert not Path(record.patch_path).exists()


async def test_cancel_during_finalize_removes_unpublished_patch(
    tmp_path, monkeypatch
) -> None:
    from xagent.domains.development_tasks import git_lifecycle

    repo = tmp_path / "repo-cancel-finalize"
    _init_git_repo(repo)
    ws_token = ws_mod.set_workspace(repo)
    patch_ready = asyncio.Event()
    original_finalize = git_lifecycle.finalize_task_worktree

    async def _blocking_finalize(*args, **kwargs):
        finalized = await original_finalize(*args, **kwargs)
        patch_ready.set()
        await asyncio.Event().wait()
        return finalized

    monkeypatch.setattr(
        git_lifecycle, "finalize_task_worktree", _blocking_finalize
    )
    monkeypatch.setattr(
        parallel, "run_agent", _make_fake_run_agent("cancelled-finalize.txt")
    )
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        parallel_task = asyncio.create_task(
            run_parallel_agents(
                [SubTask(goal="cancel during finalize", capabilities=["coding"])],
                _principal(),
                use_worktrees=True,
            )
        )
        await asyncio.wait_for(patch_ready.wait(), timeout=5)
        async with get_sessionmaker()() as session:
            running = await list_development_tasks(session, "default")
        record_before_cancel = next(
            task for task in running if task.goal == "cancel during finalize"
        )
        assert Path(record_before_cancel.patch_path).is_file()
        assert cancel_running_development_task(record_before_cancel.task_id) is True
        result = await parallel_task
    finally:
        ws_mod.reset_workspace(ws_token)

    sub = result.sub_results[0]
    assert result.status == "failed"
    assert sub.status == "cancelled"
    assert sub.development_task_status == "cancelled"
    assert not Path(sub.worktree_path).exists()
    assert _temporary_branches(repo) == []
    async with get_sessionmaker()() as session:
        record = await get_development_task(
            session, "default", record_before_cancel.task_id
        )
    assert record is not None
    assert record.status.value == "cancelled"
    assert not Path(record.patch_path).exists()


async def test_parallel_worktree_empty_result_is_failed_and_cleaned(
    tmp_path, monkeypatch
) -> None:
    """Agent 返回成功但没有产生 diff 时，不得制造可审查的空结果。"""
    repo = tmp_path / "repo-empty"
    _init_git_repo(repo)
    ws_token = ws_mod.set_workspace(repo)
    monkeypatch.setattr(parallel, "run_agent", _make_fake_run_agent())
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        result = await run_parallel_agents(
            [SubTask(goal="claim success without edits")],
            _principal(),
            use_worktrees=True,
        )
    finally:
        ws_mod.reset_workspace(ws_token)

    sub = result.sub_results[0]
    assert result.status == "failed"
    assert sub.status == "failed"
    assert sub.development_task_status == "failed"
    assert "未产生可审查变更" in sub.error
    assert not Path(sub.worktree_path).exists()
    async with get_sessionmaker()() as session:
        record = await get_development_task(
            session, "default", sub.development_task_id
        )
    assert record is not None
    assert record.status.value == "failed"
    assert not Path(record.patch_path).exists()
    branches = subprocess.run(
        ["git", "branch", "--list", "agent/*"],
        cwd=repo,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branches == ""


async def test_parallel_worktree_running_task_can_be_cancelled(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo-cancel"
    _init_git_repo(repo)
    ws_token = ws_mod.set_workspace(repo)
    started = asyncio.Event()

    async def _blocking_run_agent(*args, **kwargs):  # noqa: ARG001
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(parallel, "run_agent", _blocking_run_agent)
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        parallel_task = asyncio.create_task(
            run_parallel_agents(
                [SubTask(goal="cancel me")], _principal(), use_worktrees=True
            )
        )
        await asyncio.wait_for(started.wait(), timeout=5)
        async with get_sessionmaker()() as session:
            running = await list_development_tasks(session, "default")
        task_id = next(task.task_id for task in running if task.goal == "cancel me")
        assert cancel_running_development_task(task_id) is True
        result = await parallel_task
    finally:
        ws_mod.reset_workspace(ws_token)

    sub = result.sub_results[0]
    assert sub.status == "cancelled"
    assert sub.development_task_status == "cancelled"
    assert not Path(sub.worktree_path).exists()
    async with get_sessionmaker()() as session:
        record = await get_development_task(session, "default", task_id)
    assert record is not None
    assert record.status.value == "cancelled"


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
    assert "worktree_path" not in d["sub_results"][0]
