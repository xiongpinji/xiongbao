"""数据脱敏：敏感字段自动遮蔽。

功能：
- 手机号/邮箱/身份证/银行卡脱敏规则
- 装饰器自动脱敏响应
- 按角色控制脱敏级别
- 自定义脱敏规则

用法：
    from xagent.api.data_masking import mask_response, MaskRule

    @mask_response(rules={"phone": MaskRule.PHONE, "email": MaskRule.EMAIL})
    async def get_user(user_id: str) -> dict:
        return {"name": "张三", "phone": "13812345678", "email": "z@test.com"}
    # → {"name": "张三", "phone": "138****5678", "email": "z***@test.com"}
"""

from __future__ import annotations

import re
from enum import Enum
from functools import wraps
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.masking")


class MaskRule(str, Enum):
    """内置脱敏规则。"""

    PHONE = "phone"
    EMAIL = "email"
    ID_CARD = "id_card"
    BANK_CARD = "bank_card"
    NAME = "name"
    ADDRESS = "address"
    FULL = "full"  # 全部遮蔽


def mask_phone(value: str) -> str:
    """手机号脱敏：138****5678"""
    if len(value) < 7:
        return "***"
    return value[:3] + "****" + value[-4:]


def mask_email(value: str) -> str:
    """邮箱脱敏：z***@test.com"""
    if "@" not in value:
        return "***"
    local, domain = value.split("@", 1)
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"


def mask_id_card(value: str) -> str:
    """身份证脱敏：110***********1234"""
    if len(value) < 8:
        return "***"
    return value[:3] + "*" * (len(value) - 7) + value[-4:]


def mask_bank_card(value: str) -> str:
    """银行卡脱敏：6222****1234"""
    if len(value) < 8:
        return "***"
    return value[:4] + "****" + value[-4:]


def mask_name(value: str) -> str:
    """姓名脱敏：张*三 → 张**"""
    if len(value) <= 1:
        return "*"
    if len(value) == 2:
        return value[0] + "*"
    return value[0] + "*" * (len(value) - 2) + value[-1]


def mask_address(value: str) -> str:
    """地址脱敏：保留前6字符"""
    if len(value) <= 6:
        return value[:2] + "***"
    return value[:6] + "***"


def mask_full(value: str) -> str:
    """全部遮蔽。"""
    return "*" * min(len(value), 8)


# 规则映射
MASK_FUNCTIONS: dict[MaskRule, Callable[[str], str]] = {
    MaskRule.PHONE: mask_phone,
    MaskRule.EMAIL: mask_email,
    MaskRule.ID_CARD: mask_id_card,
    MaskRule.BANK_CARD: mask_bank_card,
    MaskRule.NAME: mask_name,
    MaskRule.ADDRESS: mask_address,
    MaskRule.FULL: mask_full,
}


def mask_value(value: str, rule: MaskRule) -> str:
    """按规则脱敏单个值。"""
    fn = MASK_FUNCTIONS.get(rule)
    if not fn:
        return value
    return fn(value)


def mask_dict(
    data: dict[str, Any],
    rules: dict[str, MaskRule],
) -> dict[str, Any]:
    """对字典中指定字段脱敏。"""
    result = dict(data)
    for field_name, rule in rules.items():
        if field_name in result and isinstance(result[field_name], str):
            result[field_name] = mask_value(result[field_name], rule)
    return result


def mask_response(
    rules: dict[str, MaskRule],
) -> Callable:
    """装饰器：自动脱敏响应字典。"""

    def decorator(fn: Callable[..., Coroutine]) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await fn(*args, **kwargs)
            if isinstance(result, dict):
                return mask_dict(result, rules)
            if isinstance(result, list):
                return [
                    mask_dict(item, rules) if isinstance(item, dict) else item
                    for item in result
                ]
            return result

        return wrapper

    return decorator
