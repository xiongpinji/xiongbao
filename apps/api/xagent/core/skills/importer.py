"""SKILL.md（agentskills.io 开放格式）导入器。

把 Hermes Agent / Claude Code / Cursor 生态的 SKILL.md 技能导入 X-Agent 技能库，
**强制过 gate_candidate 质量门禁**（与 auto_distill 同一标准），导入失败给逐条原因。

格式（YAML frontmatter + Markdown 正文）：

    ---
    name: my-skill
    description: Use when the user needs to ...
    metadata:
      tags: [devops, automation]        # 或 metadata.hermes.tags
    ---
    # 正文 → system_prompt_hint（截断 3000 字符）

字段映射：
- name / description → 同名字段（必填，缺失过不了门禁）
- trigger_pattern → 从 name 分词 + tags 派生（"|" 分隔关键词，与 match() 子串语义对齐）
- 正文 → system_prompt_hint（SKILL.md 的 Procedure 是散文而非工具调用，steps 留空）
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from xagent.infra.logging import get_logger

logger = get_logger("xagent.skills.importer")

_MAX_HINT_CHARS = 3000  # 与 core/instructions 单文件注入上限一致
_MIN_KEYWORD_LEN = 2

_FRONTMATTER_RE = re.compile(r"\A\s*---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def parse_skillmd(content: str) -> dict[str, Any]:
    """解析 SKILL.md 文本，返回 {frontmatter, body}。

    无 frontmatter 时容错为：整个文件视为正文，name/description 留空
    （会在门禁处以 incomplete_field 拒绝，原因可读）。
    """
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {"frontmatter": {}, "body": content.strip()}
    try:
        frontmatter = yaml.safe_load(m.group(1)) or {}
        if not isinstance(frontmatter, dict):
            frontmatter = {}
    except yaml.YAMLError:
        frontmatter = {}
    return {"frontmatter": frontmatter, "body": m.group(2).strip()}


def _extract_tags(frontmatter: dict[str, Any]) -> list[str]:
    """从 metadata.tags / metadata.hermes.tags / 顶层 tags 提取标签。"""
    tags: list[str] = []
    meta = frontmatter.get("metadata") or {}
    if isinstance(meta, dict):
        for key in ("tags",):
            v = meta.get(key)
            if isinstance(v, list):
                tags.extend(str(t) for t in v)
        hermes = meta.get("hermes") or {}
        if isinstance(hermes, dict) and isinstance(hermes.get("tags"), list):
            tags.extend(str(t) for t in hermes["tags"])
    top = frontmatter.get("tags")
    if isinstance(top, list):
        tags.extend(str(t) for t in top)
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        t = t.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def _derive_trigger_pattern(name: str, tags: list[str]) -> str:
    """从 name 分词 + tags 派生触发关键词（与 match() 的子串包含语义对齐）。"""
    tokens = re.split(r"[-_\s/]+", name.lower())
    keywords = [t for t in tokens if len(t) >= _MIN_KEYWORD_LEN and t.isalnum()]
    keywords.extend(t.lower() for t in tags if len(t) >= _MIN_KEYWORD_LEN)
    # 去重保序；name 整体（如 github-code-review）也作为一个长尾关键词
    seen: set[str] = set()
    out: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            out.append(kw)
    slug = name.strip().lower()
    if slug and len(slug) >= _MIN_KEYWORD_LEN and slug not in seen:
        out.append(slug)
    return "|".join(out)


def candidate_from_skillmd(content: str, origin: str = "") -> dict[str, Any]:
    """把 SKILL.md 文本映射为门禁候选 dict（字段与 gate_candidate 对齐）。"""
    parsed = parse_skillmd(content)
    fm = parsed["frontmatter"]
    body = parsed["body"]

    name = str(fm.get("name", "")).strip()
    description = str(fm.get("description", "")).strip()
    tags = _extract_tags(fm)

    return {
        "name": name,
        "description": description,
        "trigger_pattern": _derive_trigger_pattern(name, tags),
        "system_prompt_hint": body[:_MAX_HINT_CHARS],
        "steps": [],
        "tags": tags + ["imported"],
        "source_task": origin or "skillmd-import",
    }


def import_skillmd(
    store: Any, content: str, origin: str = "", tenant_id: str = ""
) -> tuple[Any | None, str]:
    """导入单个 SKILL.md：映射 → 质量门禁 → 入库。

    Returns:
        (skill 或 None, 失败原因)。门禁语境 goal 用 name+description+tags——
        与"Use when ..."语义一致：触发词应能命中技能自身的用途描述。
    """
    candidate = candidate_from_skillmd(content, origin)
    goal = f"{candidate['name']} {candidate['description']} {' '.join(candidate['tags'])}"
    ok, reason = store.gate_candidate(candidate, goal, tenant_id=tenant_id)
    if not ok:
        logger.info("skillmd_import_reject", origin=origin, reason=reason)
        return None, reason
    skill = store.create_skill(
        name=candidate["name"],
        description=candidate["description"],
        trigger_pattern=candidate["trigger_pattern"],
        steps=candidate["steps"],
        system_prompt_hint=candidate["system_prompt_hint"],
        tags=candidate["tags"],
        source="import",
        source_task=candidate["source_task"],
        tenant_id=tenant_id,
    )
    logger.info("skillmd_imported", skill_id=skill.skill_id, name=skill.name, origin=origin)
    return skill, ""


def import_skillmd_batch(
    store: Any, items: list[dict[str, str]], tenant_id: str = ""
) -> dict[str, Any]:
    """批量导入。items: [{"origin": "path/name", "content": "..."}]."""
    results = []
    imported = 0
    for item in items:
        origin = item.get("origin", "")
        content = item.get("content", "")
        if not content.strip():
            results.append({"origin": origin, "status": "rejected", "reason": "empty_content"})
            continue
        skill, reason = import_skillmd(store, content, origin, tenant_id)
        if skill is not None:
            imported += 1
            results.append(
                {"origin": origin, "status": "imported", "skill_id": skill.skill_id}
            )
        else:
            results.append({"origin": origin, "status": "rejected", "reason": reason})
    return {"total": len(items), "imported": imported, "results": results}
