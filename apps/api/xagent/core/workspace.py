"""工作区解析：进程默认 + 每任务 contextvar 覆盖。

默认工作区来自 ``XAGENT_WORKSPACE``（未设置时为 ``~/xagent_workspace``）。
并行子代理（V3-3 worktree 隔离）通过 ``set_workspace`` 在各自 asyncio 任务内
覆盖工作区，互不干扰；未覆盖时回落进程默认。

用法：

    token = set_workspace(path)
    try:
        ...  # 本任务内 get_workspace() 返回 path
    finally:
        reset_workspace(token)
"""

from __future__ import annotations

import contextvars
import os
from pathlib import Path

_DEFAULT = Path(os.environ.get("XAGENT_WORKSPACE", Path.home() / "xagent_workspace"))

_workspace_var: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "xagent_workspace", default=None
)


def default_workspace() -> Path:
    """进程默认工作区（环境变量快照）。"""
    return _DEFAULT


def get_workspace() -> Path:
    """当前任务工作区：contextvar 覆盖优先，否则进程默认。"""
    return _workspace_var.get() or _DEFAULT


def set_workspace(path: str | Path) -> contextvars.Token:
    """为当前 asyncio 任务设置工作区覆盖，返回 reset 用 token。"""
    return _workspace_var.set(Path(path))


def reset_workspace(token: contextvars.Token) -> None:
    """撤销 set_workspace 覆盖。"""
    _workspace_var.reset(token)
