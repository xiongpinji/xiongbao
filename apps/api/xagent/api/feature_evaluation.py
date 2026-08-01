"""特性评估引擎：基于规则的特性开关评估。

功能：
- 多条件特性规则（用户/租户/百分比/环境）
- 规则优先级与短路
- 特性依赖链
- 评估审计日志

用法：
    from xagent.api.feature_evaluation import FeatureEngine

    engine = FeatureEngine()
    engine.define("dark_mode", rules=[
        {"type": "whitelist", "users": ["admin"]},
        {"type": "percentage", "value": 20},
    ])
    enabled = engine.evaluate("dark_mode", context={"user": "u1", "tenant": "t1"})
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.feature_eval")


@dataclass
class FeatureRule:
    """特性规则。"""

    type: str  # whitelist | blacklist | percentage | environment | segment
    users: list[str] = field(default_factory=list)
    tenants: list[str] = field(default_factory=list)
    percentage: float = 0.0
    environments: list[str] = field(default_factory=list)
    segment_fn: str = ""  # 自定义段名称
    enabled: bool = True


@dataclass
class Feature:
    """特性定义。"""

    name: str
    enabled: bool = False
    rules: list[FeatureRule] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    description: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class EvalContext:
    """评估上下文。"""

    user: str = ""
    tenant: str = ""
    environment: str = "production"
    attributes: dict[str, Any] = field(default_factory=dict)


class FeatureEngine:
    """特性评估引擎。"""

    def __init__(self) -> None:
        self._features: dict[str, Feature] = {}
        self._audit_log: list[dict[str, Any]] = []
        self._max_audit = 1000

    def define(
        self,
        name: str,
        *,
        enabled: bool = False,
        rules: list[dict[str, Any]] | None = None,
        dependencies: list[str] | None = None,
        description: str = "",
    ) -> None:
        """定义/更新特性。"""
        parsed_rules = []
        for r in rules or []:
            parsed_rules.append(FeatureRule(
                type=r.get("type", "percentage"),
                users=r.get("users", []),
                tenants=r.get("tenants", []),
                percentage=r.get("percentage", r.get("value", 0.0)),
                environments=r.get("environments", []),
                segment_fn=r.get("segment_fn", ""),
                enabled=r.get("enabled", True),
            ))

        self._features[name] = Feature(
            name=name,
            enabled=enabled,
            rules=parsed_rules,
            dependencies=dependencies or [],
            description=description,
        )
        logger.info("feature defined: %s (enabled=%s, rules=%d)", name, enabled, len(parsed_rules))

    def remove(self, name: str) -> None:
        """移除特性。"""
        self._features.pop(name, None)

    def evaluate(self, name: str, context: EvalContext | dict[str, Any] | None = None) -> bool:
        """评估特性是否开启。"""
        if isinstance(context, dict):
            context = EvalContext(**{k: v for k, v in context.items() if k in ("user", "tenant", "environment", "attributes")})
        ctx = context or EvalContext()

        feature = self._features.get(name)
        if feature is None:
            self._audit(name, ctx, False, "not_found")
            return False

        if not feature.enabled:
            self._audit(name, ctx, False, "disabled")
            return False

        # 检查依赖
        for dep in feature.dependencies:
            if not self.evaluate(dep, ctx):
                self._audit(name, ctx, False, f"dependency_unmet:{dep}")
                return False

        # 无规则时，enabled=True 即通过
        if not feature.rules:
            self._audit(name, ctx, True, "no_rules")
            return True

        # 逐规则评估（OR 语义：任一规则通过即开启）
        for rule in feature.rules:
            if not rule.enabled:
                continue
            if self._eval_rule(rule, ctx):
                self._audit(name, ctx, True, f"rule:{rule.type}")
                return True

        self._audit(name, ctx, False, "no_rule_matched")
        return False

    def _eval_rule(self, rule: FeatureRule, ctx: EvalContext) -> bool:
        """评估单条规则。"""
        if rule.type == "whitelist":
            return ctx.user in rule.users or ctx.tenant in rule.tenants

        if rule.type == "blacklist":
            return ctx.user not in rule.users and ctx.tenant not in rule.tenants

        if rule.type == "percentage":
            return self._hash_percentage(ctx) < rule.percentage

        if rule.type == "environment":
            return ctx.environment in rule.environments

        if rule.type == "segment":
            # 预留自定义段扩展
            return False

        return False

    def _hash_percentage(self, ctx: EvalContext) -> float:
        """基于用户+租户哈希的确定性百分比（0-100）。"""
        key = f"{ctx.tenant}:{ctx.user}"
        digest = hashlib.md5(key.encode()).hexdigest()
        return int(digest[:8], 16) / 0xFFFFFFFF * 100

    def _audit(self, feature: str, ctx: EvalContext, result: bool, reason: str) -> None:
        """记录审计。"""
        entry = {
            "feature": feature,
            "user": ctx.user,
            "tenant": ctx.tenant,
            "result": result,
            "reason": reason,
            "ts": time.time(),
        }
        self._audit_log.append(entry)
        if len(self._audit_log) > self._max_audit:
            self._audit_log = self._audit_log[-self._max_audit:]

    def get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取最近审计记录。"""
        return self._audit_log[-limit:]

    def list_features(self) -> list[dict[str, Any]]:
        """列出所有特性。"""
        return [
            {
                "name": f.name,
                "enabled": f.enabled,
                "rules": len(f.rules),
                "dependencies": f.dependencies,
                "description": f.description,
            }
            for f in self._features.values()
        ]


# 全局实例
feature_engine = FeatureEngine()
