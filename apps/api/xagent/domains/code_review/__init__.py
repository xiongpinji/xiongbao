"""Code Review 领域（对标 OpenAI Codex Code Review）。

能力：输入 git diff（直接粘贴或 repo + base..head 跑 git diff），
加载被审仓库的分层 AGENTS.md 规则作为评审约束，按维度（逻辑正确性 /
安全 / 规范符合度）并行子评审，综合为按严重度分级的结构化结论。
"""

from xagent.domains.code_review.diff_parser import FileDiff, parse_unified_diff
from xagent.domains.code_review.models import (
    SEVERITIES,
    VERDICTS,
    Finding,
    ReviewResult,
)
from xagent.domains.code_review.service import (
    get_review,
    reset_review_store,
    review_diff,
    run_review,
    save_review,
)

__all__ = [
    "SEVERITIES",
    "VERDICTS",
    "FileDiff",
    "Finding",
    "ReviewResult",
    "get_review",
    "parse_unified_diff",
    "reset_review_store",
    "review_diff",
    "run_review",
    "save_review",
]
