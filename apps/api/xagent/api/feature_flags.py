"""特性开关（Feature Flags）：运行时功能控制。

功能：
- 声明式特性开关（开/关/百分比/用户白名单）
- 运行时动态切换（无需重启）
- API 管理接口
- 装饰器 / 依赖注入两种使用方式

用法：
    from xagent.api.feature_flags import flags, feature_enabled

    # 装饰器方式
    @feature_enabled("new_editor")
    async def new_editor_endpoint(): ...

    # 手动检查
    if flags.is_enabled("beta_search", user_id="u123"):
        use_new_search()
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from xagent.infra.logging import get_logger

logger = get_logger("xagent.features")


class FlagStrategy(str, Enum):
    """开关策略。"""

    BOOLEAN = "boolean"  # 全开/全关
    PERCENTAGE = "percentage"  # 百分比灰度
    WHITELIST = "whitelist"  # 用户白名单


@dataclass
class FeatureFlag:
    """特性开关定义。"""

    name: str
    enabled: bool = False
    strategy: FlagStrategy = FlagStrategy.BOOLEAN
    percentage: float = 0.0  # 0-100
    whitelist: list[str] = field(default_factory=list)
    description: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def is_enabled_for(self, user_id: str | None = None) -> bool:
        """判断对指定用户是否启用。"""
        if not self.enabled:
            return False

        if self.strategy == FlagStrategy.BOOLEAN:
            return True

        if self.strategy == FlagStrategy.WHITELIST:
            return user_id in self.whitelist if user_id else False

        if self.strategy == FlagStrategy.PERCENTAGE:
            if not user_id:
                return False
            # 基于用户 ID 的确定性哈希（同一用户结果一致）
            hash_val = int(
                hashlib.md5(f"{self.name}:{user_id}".encode()).hexdigest(), 16
            )
            return (hash_val % 10000) < (self.percentage * 100)

        return False


class FeatureFlagManager:
    """特性开关管理器。"""

    def __init__(self):
        self._flags: dict[str, FeatureFlag] = {}

    def register(
        self,
        name: str,
        *,
        enabled: bool = False,
        strategy: FlagStrategy = FlagStrategy.BOOLEAN,
        percentage: float = 0.0,
        whitelist: list[str] | None = None,
        description: str = "",
    ) -> FeatureFlag:
        """注册特性开关。"""
        flag = FeatureFlag(
            name=name,
            enabled=enabled,
            strategy=strategy,
            percentage=percentage,
            whitelist=whitelist or [],
            description=description,
        )
        self._flags[name] = flag
        logger.info("feature flag registered: %s (enabled=%s)", name, enabled)
        return flag

    def is_enabled(self, name: str, user_id: str | None = None) -> bool:
        """检查特性是否启用。"""
        flag = self._flags.get(name)
        if flag is None:
            return False
        return flag.is_enabled_for(user_id)

    def enable(self, name: str) -> bool:
        """启用特性。"""
        flag = self._flags.get(name)
        if flag:
            flag.enabled = True
            flag.updated_at = time.time()
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用特性。"""
        flag = self._flags.get(name)
        if flag:
            flag.enabled = False
            flag.updated_at = time.time()
            return True
        return False

    def update(self, name: str, **kwargs: Any) -> FeatureFlag | None:
        """更新特性配置。"""
        flag = self._flags.get(name)
        if not flag:
            return None

        for key, value in kwargs.items():
            if hasattr(flag, key) and key not in ("name", "created_at"):
                setattr(flag, key, value)
        flag.updated_at = time.time()
        return flag

    def get(self, name: str) -> FeatureFlag | None:
        return self._flags.get(name)

    def all_flags(self) -> list[dict]:
        """列出所有特性开关。"""
        return [
            {
                "name": f.name,
                "enabled": f.enabled,
                "strategy": f.strategy.value,
                "percentage": f.percentage,
                "whitelist_size": len(f.whitelist),
                "description": f.description,
            }
            for f in self._flags.values()
        ]


# 全局单例
flags = FeatureFlagManager()


def feature_enabled(flag_name: str, user_id_param: str = "user_id"):
    """特性开关装饰器。

    若特性未启用，返回 404。
    """

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            user_id = kwargs.get(user_id_param)
            if not flags.is_enabled(flag_name, user_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"Feature '{flag_name}' is not available",
                )
            return await fn(*args, **kwargs)

        return wrapper

    return decorator


# ─── 预注册常用特性 ───
flags.register("new_editor", description="新版编辑器", enabled=False)
flags.register("beta_search", description="Beta 搜索", strategy=FlagStrategy.PERCENTAGE, percentage=10)
flags.register("advanced_analytics", description="高级分析面板", enabled=False)
flags.register("multi_agent", description="多 Agent 协作", enabled=True)
