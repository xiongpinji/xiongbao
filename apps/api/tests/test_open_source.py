"""开源候选发现 + 统一评分测试（护城河）。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.domains.open_source_discovery import discover_and_rank
from xagent.domains.open_source_discovery.engine import score_candidate
from xagent.domains.open_source_discovery.models import Candidate
from xagent.enterprise.auth import create_access_token
from xagent.main import create_app


def test_score_candidate_license_penalty() -> None:
    mit = Candidate(
        name="a", source="mock", stars=1000, license="mit", last_updated="2026-05-01"
    )
    agpl = Candidate(
        name="b", source="mock", stars=10000, license="agpl-3.0", last_updated="2026-05-01"
    )
    s_ok = score_candidate("a", mit)
    s_bad = score_candidate("a", agpl)
    assert s_ok.license_ok is True
    assert s_bad.license_ok is False
    assert s_bad.score < s_ok.score  # AGPL 被扣分


async def test_discover_returns_ranked() -> None:
    results = await discover_and_rank("web framework", limit=5)
    assert results
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)  # 降序


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_open_source_api(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.post(
        "/api/v1/open-source/discover",
        json={"query": "vector database", "limit": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"]
    assert "score" in body["results"][0]
    assert "breakdown" in body["results"][0]


async def test_open_source_viewer_allowed_readonly(client: AsyncClient) -> None:
    # open_source:read 对 viewer 开放
    token = create_access_token(user_id="v", tenant_id="t1", roles=["viewer"])
    resp = await client.post(
        "/api/v1/open-source/discover",
        json={"query": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
