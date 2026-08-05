"""运行时配置热更新：无需重启即可变更配置。

支持：
- 通过 API 动态修改 LLM / 限流 / 功能开关
- 配置变更事件广播（WebSocket 通知前端刷新）
- 变更审计日志
- 配置快照回滚

用法：
    from xagent.api.runtime_config import get_runtime_config
    cfg = get_runtime_config()
    cfg.set("llm.default_model", "qwen3:8b", operator="admin")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.logging import get_logger

router = APIRouter(prefix="/runtime-config", tags=["system"])
logger = get_logger("xagent.config")


@dataclass
class ConfigChange:
    """配置变更记录。"""

    key: str
    old_value: Any
    new_value: Any
    operator: str
    timestamp: float = field(default_factory=time.time)


class RuntimeConfigManager:
    """运行时配置管理器。"""

    def __init__(self):
        self._overrides: dict[str, Any] = {}
        self._history: list[ConfigChange] = []
        self._listeners: list = []

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（优先取 override）。"""
        return self._overrides.get(key, default)

    def set(self, key: str, value: Any, operator: str = "system") -> None:
        """设置配置并记录变更。"""
        old = self._overrides.get(key)
        self._overrides[key] = value
        change = ConfigChange(key=key, old_value=old, new_value=value, operator=operator)
        self._history.append(change)
        # 保留最近 200 条
        if len(self._history) > 200:
            self._history = self._history[-200:]
        logger.info("config_changed", key=key, old=old, new=value, operator=operator)
        # 通知监听者
        for listener in self._listeners:
            try:
                listener(change)
            except Exception:
                pass

    def delete(self, key: str, operator: str = "system") -> bool:
        """删除 override，恢复默认。"""
        if key in self._overrides:
            old = self._overrides.pop(key)
            self._history.append(ConfigChange(key=key, old_value=old, new_value=None, operator=operator))
            return True
        return False

    def snapshot(self) -> dict[str, Any]:
        """当前配置快照。"""
        return dict(self._overrides)

    def rollback(self, steps: int = 1) -> list[ConfigChange]:
        """回滚最近 N 步变更。"""
        rolled = []
        for _ in range(min(steps, len(self._history))):
            change = self._history.pop()
            if change.old_value is None:
                self._overrides.pop(change.key, None)
            else:
                self._overrides[change.key] = change.old_value
            rolled.append(change)
        return rolled

    @property
    def history(self) -> list[ConfigChange]:
        return list(self._history)

    def add_listener(self, fn) -> None:
        self._listeners.append(fn)


# 单例
_manager: RuntimeConfigManager | None = None


def get_runtime_config() -> RuntimeConfigManager:
    global _manager
    if _manager is None:
        _manager = RuntimeConfigManager()
    return _manager


# ─── API 端点 ───


class ConfigSetIn(BaseModel):
    key: str
    value: Any


class ConfigRollbackIn(BaseModel):
    steps: int = 1


@router.get("", summary="查看当前运行时配置")
async def get_config(
    principal: Principal = Depends(require_permission("system", "read")),
):
    mgr = get_runtime_config()
    return {
        "overrides": mgr.snapshot(),
        "history_count": len(mgr.history),
    }


@router.put("", summary="设置运行时配置")
async def set_config(
    body: ConfigSetIn,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    mgr = get_runtime_config()
    mgr.set(body.key, body.value, operator=principal.user_id)

    # 特殊 key 联动
    if body.key.startswith("llm."):
        try:
            from xagent.adapters.llm.factory import reset_llm_client
            reset_llm_client()
        except Exception:
            pass

    return {"status": "ok", "key": body.key, "value": body.value}


@router.delete("/{key}", summary="删除配置覆盖")
async def delete_config(
    key: str,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    mgr = get_runtime_config()
    deleted = mgr.delete(key, operator=principal.user_id)
    return {"deleted": deleted, "key": key}


@router.get("/history", summary="配置变更历史")
async def config_history(
    principal: Principal = Depends(require_permission("system", "read")),
):
    mgr = get_runtime_config()
    return {
        "history": [
            {
                "key": c.key,
                "old": c.old_value,
                "new": c.new_value,
                "operator": c.operator,
                "at": c.timestamp,
            }
            for c in reversed(mgr.history[-50:])
        ]
    }


@router.post("/rollback", summary="回滚配置变更")
async def rollback_config(
    body: ConfigRollbackIn,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    mgr = get_runtime_config()
    rolled = mgr.rollback(body.steps)
    return {
        "rolled_back": len(rolled),
        "keys": [c.key for c in rolled],
    }
