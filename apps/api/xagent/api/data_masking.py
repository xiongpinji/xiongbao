"""数据脱敏：敏感字段自动遮蔽。

支持：
- 手机号：138****1234
- 邮箱：a***@example.com
- 身份证：110***********1234
- 银行卡：6222 **** **** 1234
- API Key：sk-****abcd
- IP 地址：192.168.*.*
- 自定义规则

用法：
    from xagent.api.data_masking import mask_response, MaskingRule
    masked = mask_response(data, rules=[MaskingRule(field="phone", type="phone")])
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class MaskType(str, Enum):
    PHONE = "phone"
    EMAIL = "email"
    ID_CARD = "id_card"
    BANK_CARD = "bank_card"
    API_KEY = "api_key"
    IP_ADDRESS = "ip_address"
    NAME = "name"
    CUSTOM = "custom"


@dataclass
class MaskingRule:
    """脱敏规则。"""

    field: str  # 字段名（支持嵌套：user.phone）
    type: MaskType = MaskType.CUSTOM
    pattern: str | None = None  # 自定义正则
    replacement: str = "***"  # 自定义替换


def mask_phone(value: str) -> str:
    """手机号脱敏：138****1234"""
    if len(value) >= 11:
        return value[:3] + "****" + value[-4:]
    return "***"


def mask_email(value: str) -> str:
    """邮箱脱敏：a***@example.com"""
    parts = value.split("@")
    if len(parts) == 2:
        name = parts[0]
        masked_name = name[0] + "***" if len(name) > 1 else "***"
        return f"{masked_name}@{parts[1]}"
    return "***"


def mask_id_card(value: str) -> str:
    """身份证脱敏：110***********1234"""
    if len(value) >= 18:
        return value[:3] + "*" * (len(value) - 7) + value[-4:]
    return "***"


def mask_bank_card(value: str) -> str:
    """银行卡脱敏：6222 **** **** 1234"""
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 16:
        return digits[:4] + " **** **** " + digits[-4:]
    return "***"


def mask_api_key(value: str) -> str:
    """API Key 脱敏：sk-****abcd"""
    if len(value) > 8:
        prefix = value[:3] if "-" in value[:5] else value[:2]
        return f"{prefix}****{value[-4:]}"
    return "****"


def mask_ip(value: str) -> str:
    """IP 脱敏：192.168.*.*"""
    parts = value.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.*.*"
    return "***"


def mask_name(value: str) -> str:
    """姓名脱敏：张*"""
    if len(value) >= 2:
        return value[0] + "*" * (len(value) - 1)
    return "*"


MASK_FUNCTIONS = {
    MaskType.PHONE: mask_phone,
    MaskType.EMAIL: mask_email,
    MaskType.ID_CARD: mask_id_card,
    MaskType.BANK_CARD: mask_bank_card,
    MaskType.API_KEY: mask_api_key,
    MaskType.IP_ADDRESS: mask_ip,
    MaskType.NAME: mask_name,
}


def apply_mask(value: str, rule: MaskingRule) -> str:
    """应用脱敏规则。"""
    if rule.type == MaskType.CUSTOM:
        if rule.pattern:
            return re.sub(rule.pattern, rule.replacement, value)
        return rule.replacement
    fn = MASK_FUNCTIONS.get(rule.type)
    return fn(value) if fn else value


def mask_response(data: Any, rules: list[MaskingRule]) -> Any:
    """递归脱敏响应数据。"""
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            # 检查是否有匹配规则
            matched_rule = next((r for r in rules if r.field == k or r.field.endswith(f".{k}")), None)
            if matched_rule and isinstance(v, str):
                result[k] = apply_mask(v, matched_rule)
            else:
                result[k] = mask_response(v, rules)
        return result
    elif isinstance(data, list):
        return [mask_response(item, rules) for item in data]
    return data


# 预置规则集
SENSITIVE_RULES = [
    MaskingRule(field="phone", type=MaskType.PHONE),
    MaskingRule(field="mobile", type=MaskType.PHONE),
    MaskingRule(field="email", type=MaskType.EMAIL),
    MaskingRule(field="id_card", type=MaskType.ID_CARD),
    MaskingRule(field="bank_card", type=MaskType.BANK_CARD),
    MaskingRule(field="api_key", type=MaskType.API_KEY),
    MaskingRule(field="secret", type=MaskType.API_KEY),
    MaskingRule(field="ip", type=MaskType.IP_ADDRESS),
]
