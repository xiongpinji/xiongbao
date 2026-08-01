"""校验管道：链式请求体校验。

功能：
- 声明式校验规则（类型/范围/正则/自定义）
- 链式管道组合
- 错误收集（非短路）
- 校验结果结构化

用法：
    from xagent.api.validation_pipeline import Validator, Rule

    schema = Validator("create_agent", rules=[
        Rule("name", required=True, max_len=100),
        Rule("temperature", type_=float, min_val=0, max_val=2),
        Rule("model", pattern=r"^(gpt|claude|gemini)-"),
    ])
    errors = schema.validate(payload)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from xagent.infra.logging import get_logger

logger = get_logger("xagent.validation")


@dataclass
class ValidationError:
    """单条校验错误。"""

    field: str
    message: str
    code: str = "invalid"


@dataclass
class Rule:
    """校验规则。"""

    field: str
    required: bool = False
    type_: type | None = None
    min_val: float | None = None
    max_val: float | None = None
    min_len: int | None = None
    max_len: int | None = None
    pattern: str | None = None
    choices: list[Any] | None = None
    custom: Callable[[Any], str | None] | None = None  # 返回错误消息或 None


@dataclass
class ValidationResult:
    """校验结果。"""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [
                {"field": e.field, "message": e.message, "code": e.code}
                for e in self.errors
            ],
        }


class Validator:
    """链式校验管道。"""

    def __init__(self, name: str, rules: list[Rule] | None = None):
        self.name = name
        self.rules = rules or []

    def add_rule(self, rule: Rule) -> "Validator":
        self.rules.append(rule)
        return self

    def validate(self, data: dict[str, Any]) -> ValidationResult:
        """执行所有规则，收集错误（非短路）。"""
        errors: list[ValidationError] = []

        for rule in self.rules:
            value = data.get(rule.field)

            # 必填检查
            if rule.required and (value is None or value == ""):
                errors.append(ValidationError(rule.field, f"{rule.field} 为必填项", "required"))
                continue

            # 空值跳过后续检查
            if value is None:
                continue

            # 类型检查
            if rule.type_ and not isinstance(value, rule.type_):
                errors.append(
                    ValidationError(rule.field, f"期望类型 {rule.type_.__name__}", "type")
                )
                continue

            # 数值范围
            if isinstance(value, (int, float)):
                if rule.min_val is not None and value < rule.min_val:
                    errors.append(
                        ValidationError(rule.field, f"不能小于 {rule.min_val}", "min_value")
                    )
                if rule.max_val is not None and value > rule.max_val:
                    errors.append(
                        ValidationError(rule.field, f"不能大于 {rule.max_val}", "max_value")
                    )

            # 字符串长度
            if isinstance(value, str):
                if rule.min_len is not None and len(value) < rule.min_len:
                    errors.append(
                        ValidationError(rule.field, f"长度不能少于 {rule.min_len}", "min_length")
                    )
                if rule.max_len is not None and len(value) > rule.max_len:
                    errors.append(
                        ValidationError(rule.field, f"长度不能超过 {rule.max_len}", "max_length")
                    )
                # 正则
                if rule.pattern and not re.match(rule.pattern, value):
                    errors.append(
                        ValidationError(rule.field, f"格式不匹配: {rule.pattern}", "pattern")
                    )

            # 枚举
            if rule.choices and value not in rule.choices:
                errors.append(
                    ValidationError(rule.field, f"必须是 {rule.choices} 之一", "choices")
                )

            # 自定义
            if rule.custom:
                msg = rule.custom(value)
                if msg:
                    errors.append(ValidationError(rule.field, msg, "custom"))

        result = ValidationResult(valid=len(errors) == 0, errors=errors)
        if not result.valid:
            logger.debug("validation failed [%s]: %d errors", self.name, len(errors))
        return result


# 常用校验器预设
agent_create_validator = Validator(
    "agent_create",
    rules=[
        Rule("name", required=True, max_len=200),
        Rule("model", required=True, pattern=r"^[a-z0-9\-/.]+$"),
        Rule("temperature", type_=float, min_val=0, max_val=2),
        Rule("max_tokens", type_=int, min_val=1, max_val=128000),
    ],
)
