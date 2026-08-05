"""断点续传：长任务中断后从 checkpoint 恢复执行。

对标 Codex 的 session persistence：
- 每 N 步自动保存 checkpoint（messages + step + changed_files）
- 服务重启或超时后，可从最近 checkpoint 恢复
- 通过 conversation_id 关联 checkpoint
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.checkpoint")

# checkpoint 存储目录
_CHECKPOINT_DIR = Path.home() / "xagent_workspace" / ".checkpoints"
# 每 N 步保存一次
_CHECKPOINT_INTERVAL = 5
# 最多保留的 checkpoint 数量（per conversation）
_MAX_CHECKPOINTS = 3


def _ensure_dir() -> None:
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def save_checkpoint(
    conversation_id: str,
    run_id: str,
    step: int,
    messages: list[dict[str, Any]],
    changed_files: list[str],
    goal: str,
) -> None:
    """保存 checkpoint 到磁盘。"""
    try:
        _ensure_dir()
        ckpt = {
            "conversation_id": conversation_id,
            "run_id": run_id,
            "step": step,
            "goal": goal,
            "changed_files": changed_files,
            "messages": messages[-30:],  # 只保留最近 30 条（防文件过大）
            "timestamp": time.time(),
        }
        path = _CHECKPOINT_DIR / f"{conversation_id}_{run_id[:8]}.json"
        path.write_text(json.dumps(ckpt, ensure_ascii=False, default=str), encoding="utf-8")
        # 清理旧 checkpoint（只保留最近 N 个）
        _cleanup_old(conversation_id)
    except Exception as e:
        logger.debug("checkpoint_save_failed", error=str(e))


def load_checkpoint(conversation_id: str) -> dict[str, Any] | None:
    """加载最近的 checkpoint。返回 None 表示无可用 checkpoint。"""
    try:
        _ensure_dir()
        candidates = sorted(
            _CHECKPOINT_DIR.glob(f"{conversation_id}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return None
        data = json.loads(candidates[0].read_text(encoding="utf-8"))
        # 超过 30 分钟的 checkpoint 视为过期
        if time.time() - data.get("timestamp", 0) > 1800:
            return None
        return data
    except Exception:
        return None


def clear_checkpoints(conversation_id: str) -> None:
    """任务成功完成后清理 checkpoint。"""
    try:
        _ensure_dir()
        for f in _CHECKPOINT_DIR.glob(f"{conversation_id}_*.json"):
            f.unlink(missing_ok=True)
    except Exception:
        pass


def _cleanup_old(conversation_id: str) -> None:
    """只保留最近 N 个 checkpoint。"""
    try:
        candidates = sorted(
            _CHECKPOINT_DIR.glob(f"{conversation_id}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in candidates[_MAX_CHECKPOINTS:]:
            old.unlink(missing_ok=True)
    except Exception:
        pass


def should_checkpoint(step: int) -> bool:
    """判断当前步数是否应保存 checkpoint。"""
    return step > 0 and step % _CHECKPOINT_INTERVAL == 0
