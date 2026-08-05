"""内容安全审计 + 数据脱敏。

功能：
- 输入/输出内容扫描（敏感词、注入攻击检测）
- PII 脱敏（手机号、身份证、邮箱、银行卡）
- 审计日志导出（JSON / CSV）
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.content_security")

# ─── 敏感词 / 注入检测 ───

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"system\s*prompt\s*[:=]", re.I),
    re.compile(r"you\s+are\s+now\s+(?:DAN|evil|unrestricted)", re.I),
    re.compile(r"<\s*/?\s*system\s*>", re.I),
    re.compile(r"\bACT\s+AS\b.*\bwithout\s+restrictions\b", re.I),
]

_SENSITIVE_KEYWORDS = [
    "内部机密", "绝密", "top secret", "classified",
]


@dataclass
class ScanResult:
    safe: bool
    risks: list[str]
    masked_text: str = ""


def scan_input(text: str) -> ScanResult:
    """扫描用户输入：注入攻击 + 敏感词。"""
    risks: list[str] = []
    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            risks.append(f"prompt_injection: {pat.pattern[:40]}")
    for kw in _SENSITIVE_KEYWORDS:
        if kw.lower() in text.lower():
            risks.append(f"sensitive_keyword: {kw}")
    if risks:
        logger.warning("content_scan_risk", risks=risks, text_len=len(text))
    return ScanResult(safe=len(risks) == 0, risks=risks, masked_text=text)


def scan_output(text: str) -> ScanResult:
    """扫描 Agent 输出：PII 泄露检测 + 脱敏。"""
    risks: list[str] = []
    masked = text

    # 手机号
    phone_pat = re.compile(r"1[3-9]\d{9}")
    if phone_pat.search(masked):
        risks.append("pii_phone")
        masked = phone_pat.sub("1**********", masked)

    # 身份证
    id_pat = re.compile(r"\d{17}[\dXx]")
    if id_pat.search(masked):
        risks.append("pii_id_card")
        masked = id_pat.sub("******************", masked)

    # 邮箱
    email_pat = re.compile(r"[\w.-]+@[\w.-]+\.\w+")
    if email_pat.search(masked):
        risks.append("pii_email")
        masked = email_pat.sub("***@***.***", masked)

    # 银行卡
    bank_pat = re.compile(r"\d{16,19}")
    if bank_pat.search(masked):
        risks.append("pii_bank_card")
        masked = bank_pat.sub("****", masked)

    if risks:
        logger.info("output_pii_masked", risks=risks)
    return ScanResult(safe=len(risks) == 0, risks=risks, masked_text=masked)


# ─── 数据脱敏工具 ───


def mask_value(value: str, kind: str = "generic") -> str:
    """通用脱敏：保留前2后2，中间用 * 替代。"""
    if len(value) <= 4:
        return "****"
    if kind == "phone":
        return value[:3] + "****" + value[-4:]
    if kind == "email":
        parts = value.split("@")
        return parts[0][:2] + "***@" + parts[1] if len(parts) == 2 else "****"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


# ─── 审计日志导出 ───


def export_audit_json(events: list[Any]) -> str:
    """导出审计日志为 JSON。"""
    data = [e.to_dict() if hasattr(e, "to_dict") else e for e in events]
    return json.dumps(data, ensure_ascii=False, indent=2)


def export_audit_csv(events: list[Any]) -> str:
    """导出审计日志为 CSV。"""
    rows = [e.to_dict() if hasattr(e, "to_dict") else e for e in events]
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()
