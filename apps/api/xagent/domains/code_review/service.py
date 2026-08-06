"""Code Review 服务：supervisor 式分工并行评审 + 结构化综合。

流程（对齐 core/orchestration/supervisor 的 分解→并行→综合 模式）：
    1. 解析 diff 为逐文件片段（分解）
    2. 按维度并行子评审：logic（逻辑正确性）/ security（安全）/
       standards（风格与项目规范符合度，注入被审仓库 AGENTS.md 规则）
    3. 综合：合并 findings、按严重度分级、推导 verdict、生成摘要

结果暂存进程内存（review_id → (tenant_id, ReviewResult)），
与 creative_studio 草稿存储同一风格；后续可平滑落 agent_tasks 表。
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from xagent.domains.code_review.diff_parser import FileDiff, parse_unified_diff
from xagent.domains.code_review.models import (
    SEVERITIES,
    Finding,
    ReviewResult,
    decide_verdict,
)
from xagent.infra.logging import get_logger

logger = get_logger("xagent.code_review")

DIMENSIONS = ("logic", "security", "standards")

_DIMENSION_LABELS = {
    "logic": "逻辑正确性（边界条件、空值、并发、错误处理、业务逻辑错误）",
    "security": "安全（注入、密钥硬编码、越权、不安全反序列化、敏感信息泄露）",
    "standards": "风格与项目规范符合度（命名、结构、以及下方仓库自定义规则）",
}

_REVIEW_PROMPT = """\
你是资深代码评审专家，只负责【{label}】这一个维度。

仓库自定义规则（来自 AGENTS.md，必须严格遵守）：
{instructions}

被评审的 git diff：
{diff}

要求：
- 仅报告该 diff 引入的问题，不要评论未改动的代码
- 每条发现给出：file（文件路径）、line（新文件行号，不确定给 0）、
  severity（critical/high/medium/low/info）、issue（问题描述）、
  suggestion（修复建议）、rule_ref（违反的自定义规则原文摘录；无则空字符串）
- 没有发现问题就返回空 findings

仅输出 JSON，不要其他文字：
{{"findings": [{{"file": "...", "line": 0, "severity": "...",
  "issue": "...", "suggestion": "...", "rule_ref": ""}}]}}
"""

_SYNTHESIS_PROMPT = """\
你是评审 Supervisor。各维度评审结果如下（JSON）：
{findings}

请用 2-3 句话给出本次代码评审的总体摘要（中文），
说明变更质量、最关键的风险点（如有）、以及是否建议合并。
仅输出摘要文本。
"""


def _extract_json(text: str) -> dict[str, Any] | None:
    """从 LLM 输出中提取第一个 JSON 对象。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = text.rsplit("```", 1)[0]
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        pass
    # 兜底：截取首个 { 到末个 }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except (ValueError, TypeError):
            return None
    return None


def _build_diff_text(files: list[FileDiff]) -> str:
    return "\n".join(fd.patch for fd in files)


async def _review_dimension(
    dimension: str,
    diff_text: str,
    instructions: str,
    llm: Any,
) -> list[Finding]:
    """单维度子评审（Worker）。解析失败返回空列表。"""
    from xagent.adapters.llm import Message

    prompt = _REVIEW_PROMPT.format(
        label=_DIMENSION_LABELS[dimension],
        instructions=instructions or "（无自定义规则，按通用最佳实践评审）",
        diff=diff_text,
    )
    resp = await llm.complete(
        messages=[Message(role="user", content=prompt)],
        temperature=0.2,
    )
    text = resp.content if hasattr(resp, "content") else str(resp)
    obj = _extract_json(text)
    if obj is None:
        raise ValueError(f"维度 {dimension} 输出非 JSON，无法解析")
    findings: list[Finding] = []
    for item in obj.get("findings") or []:
        if not isinstance(item, dict) or not item.get("issue"):
            continue
        findings.append(
            Finding(
                file=str(item.get("file", "")),
                line=item.get("line", 0),
                severity=str(item.get("severity", "info")).lower(),
                issue=str(item["issue"]),
                suggestion=str(item.get("suggestion", "")),
                dimension=dimension,
                rule_ref=str(item.get("rule_ref", "")),
            )
        )
    return findings


def _dedupe(findings: list[Finding]) -> list[Finding]:
    """按 (file, line, issue 前 40 字) 去重，保留严重度更高的一条。"""
    rank = {s: i for i, s in enumerate(SEVERITIES)}
    best: dict[tuple, Finding] = {}
    for f in findings:
        key = (f.file, f.line, f.issue[:40])
        cur = best.get(key)
        if cur is None or rank[f.severity] < rank[cur.severity]:
            best[key] = f
    return sorted(best.values(), key=lambda f: (rank[f.severity], f.file, f.line))


async def _summarize(findings: list[Finding], llm: Any) -> str:
    """LLM 综合摘要，失败降级为确定性摘要。"""
    if findings:
        payload = json.dumps([f.to_dict() for f in findings][:20], ensure_ascii=False)
        try:
            from xagent.adapters.llm import Message

            resp = await llm.complete(
                messages=[Message(role="user", content=_SYNTHESIS_PROMPT.format(findings=payload))],
                temperature=0.3,
            )
            text = resp.content if hasattr(resp, "content") else str(resp)
            if text.strip():
                return text.strip()[:1000]
        except Exception as exc:  # noqa: BLE001 - 摘要失败不应拖垮整个评审
            logger.warning("review_summary_fallback", error=str(exc))
    if not findings:
        return "未发现明确问题，变更可以合并。"
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    parts = "、".join(f"{k} {v} 条" for k, v in counts.items())
    return f"共发现 {len(findings)} 个问题（{parts}），请逐条处理后合并。"


async def run_review(
    diff_text: str,
    *,
    instructions: str = "",
    llm: Any = None,
    max_files: int = 10,
) -> ReviewResult:
    """执行一次代码评审。

    diff_text 为空或无法解析出文件时返回 failed 状态的 ReviewResult。
    """
    if llm is None:
        from xagent.adapters.llm import get_llm_client

        llm = get_llm_client()

    t0 = time.time()
    files = parse_unified_diff(diff_text)
    if not files:
        return ReviewResult(
            status="failed",
            error="diff 为空或无法解析出文件变更",
            duration_ms=(time.time() - t0) * 1000,
        )

    files = files[:max_files]
    diff_text_built = _build_diff_text(files)

    # 分解 → 并行子评审
    results = await asyncio.gather(
        *[
            _review_dimension(dim, diff_text_built, instructions, llm)
            for dim in DIMENSIONS
        ],
        return_exceptions=True,
    )

    findings: list[Finding] = []
    failed_dimensions: list[str] = []
    for dim, res in zip(DIMENSIONS, results, strict=True):
        if isinstance(res, BaseException):
            logger.warning("review_dimension_failed", dimension=dim, error=str(res))
            failed_dimensions.append(dim)
        else:
            findings.extend(res)

    findings = _dedupe(findings)
    verdict = decide_verdict(findings)
    summary = await _summarize(findings, llm)

    if len(failed_dimensions) == len(DIMENSIONS):
        status = "failed"
    elif failed_dimensions:
        status = "partial"
    else:
        status = "succeeded"

    result = ReviewResult(
        status=status,
        verdict=verdict,
        summary=summary,
        findings=findings,
        files_changed=len(files),
        additions=sum(fd.additions for fd in files),
        deletions=sum(fd.deletions for fd in files),
        dimensions=[d for d in DIMENSIONS if d not in failed_dimensions],
        failed_dimensions=failed_dimensions,
        instructions_applied=bool(instructions.strip()),
        duration_ms=(time.time() - t0) * 1000,
    )
    logger.info(
        "code_review_done",
        review_id=result.review_id,
        status=status,
        verdict=verdict,
        findings=len(findings),
        files=len(files),
    )
    return result


# ─── 结果暂存（进程内存，租户隔离；后续可落 agent_tasks）───

_reviews: dict[str, tuple[str, ReviewResult]] = {}


def save_review(result: ReviewResult, tenant_id: str) -> ReviewResult:
    _reviews[result.review_id] = (tenant_id, result)
    return result


def get_review(review_id: str, tenant_id: str) -> ReviewResult | None:
    entry = _reviews.get(review_id)
    if entry is None or entry[0] != tenant_id:
        return None
    return entry[1]


def reset_review_store() -> None:
    _reviews.clear()


# ─── 便捷入口：从 repo 跑 git diff 再评审 ───


async def review_diff(
    *,
    diff: str | None = None,
    repo: str | None = None,
    base: str | None = None,
    head: str = "HEAD",
    llm: Any = None,
    max_files: int = 10,
) -> ReviewResult:
    """统一入口：优先用直接给出的 diff；否则从 repo 跑 ``git diff base..head``。

    AGENTS.md 规则经 core/instructions 分层加载（task_paths 取 diff 涉及的文件，
    使子目录级规则就近生效）。
    """
    from xagent.core.instructions import get_layered_instructions
    from xagent.domains.code_review.diff_parser import diff_from_repo_async

    diff_text = (diff or "").strip()
    if not diff_text:
        if not repo or not base:
            raise ValueError("必须提供 diff 文本，或 repo + base")
        diff_text = await diff_from_repo_async(repo, base, head)
    if not diff_text.strip():
        raise ValueError("git diff 结果为空（base..head 无差异）")

    instructions = ""
    if repo:
        task_paths = [fd.path for fd in parse_unified_diff(diff_text)]
        instructions = get_layered_instructions(repo, task_paths=task_paths)

    return await run_review(
        diff_text, instructions=instructions, llm=llm, max_files=max_files
    )
