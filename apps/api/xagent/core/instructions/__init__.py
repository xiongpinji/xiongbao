"""AGENTS.md 分层指令加载（对标 OpenAI Codex 分层指令合并）。

三层优先级（低 → 高，冲突时高优先级覆盖低优先级）：

1. **用户级**：``~/.xagent/AGENTS.md``（可用 ``XAGENT_USER_HOME`` 覆盖目录）
2. **工作区根**：``<workspace>/AGENTS.md``
3. **子目录级**：任务涉及路径就近的 AGENTS.md，目录越深优先级越高

合并策略：按优先级从低到高拼接，并显式标注来源层级与覆盖规则，
与 Codex「根/子目录/用户级严格优先级合并」语义对齐。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from xagent.infra.logging import get_logger

logger = get_logger("xagent.instructions")

INSTRUCTIONS_FILENAME = "AGENTS.md"
_PER_FILE_MAX_CHARS = 3000   # 单个指令文件注入上限
_TOTAL_MAX_CHARS = 6000      # 合并后总注入上限


@dataclass
class InstructionLayer:
    """一层指令。"""

    level: str      # user | workspace | subdir
    path: Path
    content: str
    depth: int = 0  # 相对工作区根的目录深度（子目录层用于排序）


def _default_user_dir() -> Path:
    return Path(os.environ.get("XAGENT_USER_HOME", str(Path.home() / ".xagent")))


def _read_instructions(path: Path) -> str:
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()[:_PER_FILE_MAX_CHARS]
    except OSError:
        pass
    return ""


def _find_subdir_layers(workspace: Path, task_paths: list[str]) -> list[InstructionLayer]:
    """收集任务路径就近的子目录级 AGENTS.md（root→leaf 顺序，越深越靠后）。"""
    found: dict[Path, InstructionLayer] = {}
    ws = workspace.resolve()
    for rel in task_paths:
        p = (ws / rel).resolve()
        # 路径指向文件时从其所在目录开始；不存在的路径按目录语义向上找
        start = p if p.is_dir() else p.parent
        # 从任务目录向上走到工作区根，收集沿途 AGENTS.md
        chain: list[Path] = []
        cur: Path | None = start
        while cur is not None and cur != ws.parent:
            try:
                cur.relative_to(ws)
            except ValueError:
                break  # 越出工作区，停止
            chain.append(cur)
            if cur == ws:
                break
            cur = cur.parent
        for d in chain:
            if d == ws:
                continue  # 工作区根属于第 2 层，不重复
            f = d / INSTRUCTIONS_FILENAME
            content = _read_instructions(f)
            if content and f not in found:
                depth = len(d.relative_to(ws).parts)
                found[f] = InstructionLayer(level="subdir", path=f, content=content, depth=depth)
    # 深度升序：浅的（优先级低）在前，深的（优先级高）在后
    return sorted(found.values(), key=lambda layer: layer.depth)


def load_layers(
    workspace: str | Path,
    task_paths: list[str] | None = None,
    user_dir: str | Path | None = None,
) -> list[InstructionLayer]:
    """按优先级从低到高返回所有命中的指令层。"""
    ws = Path(workspace)
    layers: list[InstructionLayer] = []

    # 第 1 层：用户级
    udir = Path(user_dir) if user_dir else _default_user_dir()
    content = _read_instructions(udir / INSTRUCTIONS_FILENAME)
    if content:
        layers.append(InstructionLayer(level="user", path=udir / INSTRUCTIONS_FILENAME, content=content))

    # 第 2 层：工作区根
    content = _read_instructions(ws / INSTRUCTIONS_FILENAME)
    if content:
        layers.append(InstructionLayer(level="workspace", path=ws / INSTRUCTIONS_FILENAME, content=content))

    # 第 3 层：子目录级（任务路径就近，越深优先级越高）
    if task_paths:
        layers.extend(_find_subdir_layers(ws, task_paths))

    return layers


def get_layered_instructions(
    workspace: str | Path,
    task_paths: list[str] | None = None,
    user_dir: str | Path | None = None,
) -> str:
    """加载并合并三层 AGENTS.md 指令，返回注入 system prompt 的文本。

    无命中时返回空字符串。合并结果按优先级从低到高排列，
    并附覆盖规则说明，供模型在指令冲突时仲裁。
    """
    layers = load_layers(workspace, task_paths=task_paths, user_dir=user_dir)
    if not layers:
        return ""

    _LEVEL_LABEL = {
        "user": "用户级",
        "workspace": "工作区根",
        "subdir": "子目录级",
    }
    parts: list[str] = []
    total = 0
    for layer in layers:
        section = f"### {_LEVEL_LABEL[layer.level]}指令（{layer.path}）\n{layer.content}"
        total += len(section)
        if total > _TOTAL_MAX_CHARS:
            remaining = _TOTAL_MAX_CHARS - (total - len(section))
            if remaining <= 0:
                break
            section = section[:remaining]
            parts.append(section)
            break
        parts.append(section)

    parts.append(
        "以上指令按优先级从低到高排列；相互冲突时，以层级更高"
        "（更靠后、更靠近任务路径）的指令为准。"
    )
    merged = "\n\n".join(parts)
    logger.debug("layered_instructions_loaded", layers=len(layers), chars=len(merged))
    return merged
