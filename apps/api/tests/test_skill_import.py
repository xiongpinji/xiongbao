"""SKILL.md 导入器测试（agentskills.io 生态兼容 + 门禁强制）。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.core.skills import SkillStore
from xagent.core.skills.importer import (
    candidate_from_skillmd,
    import_skillmd,
    import_skillmd_batch,
    parse_skillmd,
)
from xagent.main import create_app

SAMPLE = """---
name: github-code-review
description: Use when reviewing a pull request. Do NOT use for writing new code.
license: MIT
metadata:
  hermes:
    tags: [devops, review]
---
# GitHub Code Review

## Procedure
1. Fetch the diff
2. Check for null pointers, SQL injection, XSS

## Common Pitfalls
- Rate limit: back off and retry
"""


@pytest.fixture
def store(tmp_path) -> SkillStore:
    return SkillStore(storage_dir=tmp_path / "skills")


# ─── 解析 ───


def test_parse_frontmatter_and_body() -> None:
    parsed = parse_skillmd(SAMPLE)
    assert parsed["frontmatter"]["name"] == "github-code-review"
    assert "Procedure" in parsed["body"]


def test_parse_without_frontmatter_tolerated() -> None:
    parsed = parse_skillmd("# Just markdown\n\nno frontmatter here")
    assert parsed["frontmatter"] == {}
    assert "Just markdown" in parsed["body"]


def test_candidate_mapping() -> None:
    cand = candidate_from_skillmd(SAMPLE, origin="tap/github-code-review")
    assert cand["name"] == "github-code-review"
    assert "reviewing a pull request" in cand["description"]
    # 触发词：name 分词 + tags + name slug
    kws = cand["trigger_pattern"].split("|")
    assert "github" in kws and "review" in kws and "devops" in kws
    assert "github-code-review" in kws
    assert cand["steps"] == []
    assert "imported" in cand["tags"]
    assert cand["source_task"] == "tap/github-code-review"


# ─── 导入 + 门禁 ───


def test_import_success_and_matchable(store: SkillStore) -> None:
    skill, reason = import_skillmd(store, SAMPLE, origin="tap/x")
    assert skill is not None and reason == ""
    assert skill.source == "import"
    # 导入后可被 matcher 命中（触发词子串语义）
    matched = store.match("please do a github code review for this PR")
    assert any(s.skill_id == skill.skill_id for s in matched)
    # 注入文本含正文
    injection = store.build_prompt_injection("github code review")
    assert "Procedure" in injection


def test_import_rejects_missing_fields(store: SkillStore) -> None:
    bad = "---\nname: only-name\n---\nbody text"
    skill, reason = import_skillmd(store, bad)
    assert skill is None
    assert reason.startswith("incomplete_field")


def test_import_rejects_duplicate(store: SkillStore) -> None:
    skill1, _ = import_skillmd(store, SAMPLE)
    assert skill1 is not None
    skill2, reason = import_skillmd(store, SAMPLE)  # 重复导入
    assert skill2 is None
    assert reason.startswith("duplicate")


def test_import_dedup_scope_survives_store_reload(tmp_path) -> None:
    storage_dir = tmp_path / "skills"
    first_store = SkillStore(storage_dir=storage_dir)
    first, reason = import_skillmd(first_store, SAMPLE, tenant_id="tenant-a")
    assert first is not None and reason == ""

    reloaded_store = SkillStore(storage_dir=storage_dir)
    second, reason = import_skillmd(reloaded_store, SAMPLE, tenant_id="tenant-b")
    assert second is not None and reason == ""
    assert second.skill_id != first.skill_id

    duplicate, reason = import_skillmd(
        reloaded_store, SAMPLE, tenant_id="tenant-b"
    )
    assert duplicate is None
    assert reason.startswith(f"duplicate:{second.skill_id}:")
    assert first.skill_id not in reason


def test_import_batch_mixed_results(store: SkillStore) -> None:
    other = """---
name: gitlab-deploy
description: Use when deploying applications to production environments via GitLab CI.
metadata:
  tags: [deploy]
---
# GitLab Deploy

## Procedure
1. Trigger pipeline
2. Wait for artifacts
"""
    report = import_skillmd_batch(
        store,
        [
            {"origin": "a", "content": SAMPLE},
            {"origin": "b", "content": other},
            {"origin": "c", "content": ""},
            {"origin": "d", "content": SAMPLE},  # 重复
        ],
    )
    assert report["total"] == 4
    assert report["imported"] == 2
    statuses = {r["origin"]: r["status"] for r in report["results"]}
    assert statuses == {"a": "imported", "b": "imported", "c": "rejected", "d": "rejected"}


# ─── API 层 ───


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def isolated_store(tmp_path, monkeypatch) -> SkillStore:
    """API 测试用隔离技能库（开发库有 150 技能，门禁去重/容量会干扰）。"""
    import xagent.core.skills as skills_mod

    s = SkillStore(storage_dir=tmp_path / "skills")
    monkeypatch.setattr(skills_mod, "_store", s)
    return s


async def _admin_headers(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_api_import_skillmd(client: AsyncClient, isolated_store) -> None:
    headers = await _admin_headers(client)
    resp = await client.post(
        "/api/v1/skills/import/skillmd",
        json={"content": SAMPLE, "origin": "test/tap"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] is True
    assert body["skill"]["name"] == "github-code-review"

    # 重复导入被拒（门禁去重）
    resp2 = await client.post(
        "/api/v1/skills/import/skillmd",
        json={"content": SAMPLE, "origin": "test/tap"},
        headers=headers,
    )
    assert resp2.json()["imported"] is False


async def test_api_import_requires_permission(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/skills/import/skillmd", json={"content": SAMPLE}
    )
    assert resp.status_code == 401


async def test_api_batch_import(client: AsyncClient, isolated_store) -> None:
    headers = await _admin_headers(client)
    resp = await client.post(
        "/api/v1/skills/import/skillmd/batch",
        json={"items": [
            {"content": SAMPLE, "origin": "t/1"},
            {"content": "no frontmatter, no name", "origin": "t/2"},
        ]},
        headers=headers,
    )
    body = resp.json()
    assert body["total"] == 2 and body["imported"] == 1
