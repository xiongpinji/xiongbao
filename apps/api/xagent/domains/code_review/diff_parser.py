"""统一 diff（unified diff）解析与 git diff 获取。

- parse_unified_diff：把 diff 文本拆成逐文件的 FileDiff，统计增删行数。
- diff_from_repo：在本地仓库上跑 ``git diff base..head``（repo 不可访问时
  调用方应降级为直接粘贴 diff 文本）。
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path

# ref 只允许安全字符，且不允许以 '-' 开头（防被当成 git 选项）
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]*$")

# 单文件 patch 注入上限（字符）
_PER_FILE_MAX_CHARS = 8000


@dataclass
class FileDiff:
    """单个文件的 diff 片段。"""

    path: str                 # 新路径（删除文件时为旧路径）
    old_path: str = ""
    additions: int = 0
    deletions: int = 0
    patch: str = ""           # 该文件的完整 diff 文本（含 diff --git 头）
    truncated: bool = field(default=False)

    def __post_init__(self) -> None:
        if len(self.patch) > _PER_FILE_MAX_CHARS:
            self.patch = self.patch[:_PER_FILE_MAX_CHARS] + "\n... [truncated]"
            self.truncated = True


def _strip_prefix(path: str) -> str:
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    """解析 unified diff 为逐文件结构。非 diff 内容返回空列表。"""
    files: list[FileDiff] = []
    current: FileDiff | None = None
    buf: list[str] = []

    def _flush() -> None:
        nonlocal current, buf
        if current is not None:
            current.patch = "\n".join(buf)
            files.append(current)
        current = None
        buf = []

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            _flush()
            current = FileDiff(path="")
            buf = [line]
            continue
        if current is None:
            continue  # diff 头之前的噪声（commit message 等）
        buf.append(line)
        if line.startswith("+++ "):
            current.path = _strip_prefix(line[4:].strip())
        elif line.startswith("--- "):
            current.old_path = _strip_prefix(line[4:].strip())
        elif line.startswith("+") and not line.startswith("+++"):
            current.additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            current.deletions += 1
    _flush()

    # 兜底：某些 diff（如纯 git show --stat 片段）无 +++ 行，从 diff --git 头取路径
    for fd in files:
        if not fd.path:
            m = re.search(r"diff --git a/(.+?) b/", fd.patch.splitlines()[0])
            if m:
                fd.path = m.group(1)
        # /dev/null 表示新增/删除文件，回退到另一侧路径
        if fd.path == "/dev/null":
            fd.path = fd.old_path
    return [fd for fd in files if fd.path]


def validate_ref(ref: str) -> str:
    """校验 git ref 合法性，非法抛 ValueError。"""
    ref = (ref or "").strip()
    if not ref or not _REF_RE.match(ref) or ref.startswith("-"):
        raise ValueError(f"非法 git ref: {ref!r}")
    return ref


def diff_from_repo(repo: str | Path, base: str, head: str = "HEAD", timeout: int = 60) -> str:
    """在本地仓库执行 ``git diff base..head``，返回 diff 文本。

    repo 不存在 / 非 git 仓库 / ref 非法时抛 ValueError。
    """
    from xagent.adapters.tools.codex_tools import _run_git

    repo_path = Path(repo)
    if not repo_path.is_dir():
        raise ValueError(f"repo 路径不存在或不是目录: {repo}")
    if not (repo_path / ".git").exists():
        raise ValueError(f"不是 git 仓库（缺少 .git）: {repo}")

    base = validate_ref(base)
    head = validate_ref(head or "HEAD")
    out, err, rc = _run_git(["diff", f"{base}..{head}", "--"], str(repo_path), timeout=timeout)
    if rc != 0:
        raise ValueError(f"git diff 失败: {err.strip() or f'exit code {rc}'}")
    return out


async def diff_from_repo_async(
    repo: str | Path, base: str, head: str = "HEAD", timeout: int = 60
) -> str:
    """diff_from_repo 的异步包装（不阻塞事件循环）。"""
    return await asyncio.to_thread(diff_from_repo, repo, base, head, timeout)
