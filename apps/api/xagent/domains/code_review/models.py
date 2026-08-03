"""Code Review 数据模型。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# 严重度（高 → 低）
SEVERITIES = ("critical", "high", "medium", "low", "info")
# 总体结论
VERDICTS = ("approve", "comment", "request_changes")

# 达到即触发 request_changes 的严重度
_BLOCKING = {"critical", "high"}


@dataclass
class Finding:
    """单条评审发现。"""

    file: str
    line: int
    severity: str  # critical | high | medium | low | info
    issue: str
    suggestion: str = ""
    dimension: str = ""   # logic | security | standards
    rule_ref: str = ""    # 违反的 AGENTS.md 规则引用（standards 维度）

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            self.severity = "info"
        try:
            self.line = int(self.line)
        except (TypeError, ValueError):
            self.line = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "severity": self.severity,
            "issue": self.issue,
            "suggestion": self.suggestion,
            "dimension": self.dimension,
            "rule_ref": self.rule_ref,
        }


@dataclass
class ReviewResult:
    """一次评审的结构化结论。"""

    review_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "succeeded"           # succeeded | partial | failed
    verdict: str = "approve"            # approve | comment | request_changes
    summary: str = ""
    findings: list[Finding] = field(default_factory=list)
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    dimensions: list[str] = field(default_factory=list)
    failed_dimensions: list[str] = field(default_factory=list)
    instructions_applied: bool = False   # 是否注入了 AGENTS.md 规则
    error: str = ""
    created_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    def severity_counts(self) -> dict[str, int]:
        counts = dict.fromkeys(SEVERITIES, 0)
        for f in self.findings:
            counts[f.severity] += 1
        return {k: v for k, v in counts.items() if v}

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "status": self.status,
            "verdict": self.verdict,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
            "severity_counts": self.severity_counts(),
            "stats": {
                "files_changed": self.files_changed,
                "additions": self.additions,
                "deletions": self.deletions,
            },
            "dimensions": self.dimensions,
            "failed_dimensions": self.failed_dimensions,
            "instructions_applied": self.instructions_applied,
            "error": self.error,
            "created_at": self.created_at,
            "duration_ms": round(self.duration_ms, 1),
        }


def decide_verdict(findings: list[Finding]) -> str:
    """按严重度推导总体结论：critical/high → request_changes；其余有发现 → comment。"""
    if any(f.severity in _BLOCKING for f in findings):
        return "request_changes"
    if findings:
        return "comment"
    return "approve"
