"""发现引擎 + 统一评分函数（护城河核心）。

评分维度（归一化 0-1 加权）：
  popularity  热度（stars 对数缩放）
  maintenance 维护活跃度（最近更新距今）
  fit         与查询语义契合（关键词重合）
  license     许可证是否可商用（一票否决式扣分）

provider 接口统一：``search(query) -> list[Candidate]``。Phase 3 内置 mock provider
+ GitHub provider 骨架；真实接入按需补网络层。
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol

from xagent.domains.open_source_discovery.models import Candidate, ScoredCandidate
from xagent.infra.logging import get_logger

logger = get_logger("xagent.osd")

# 可商用许可白名单（与 license_check.py 对齐）
_COMMERCIAL_LICENSES = {
    "mit", "apache-2.0", "apache 2.0", "bsd-2-clause", "bsd-3-clause",
    "isc", "mpl-2.0", "lgpl", "unlicense", "zlib",
}
# 禁用许可（一票否决）
_FORBIDDEN = {"agpl", "gpl", "gplv3", "gplv2", "sspl", "busl", "elastic"}


class Provider(Protocol):
    name: str
    async def search(self, query: str, *, limit: int = 10) -> list[Candidate]: ...


class MockProvider:
    """离线/CI 用的确定性 provider。"""

    name = "mock"

    async def search(self, query: str, *, limit: int = 10) -> list[Candidate]:
        q = query.lower()
        return [
            Candidate(
                name=f"awesome-{q.replace(' ', '-')}-lib",
                source="mock",
                url=f"https://example.com/{q}",
                description=f"与 {query} 相关的示例库",
                stars=1200,
                license="mit",
                last_updated="2026-05-01",
                language="python",
                topics=[q],
            )
        ]


class GitHubProvider:
    """GitHub provider 骨架（需 token，未配置时由上层跳过）。"""

    name = "github"

    async def search(self, query: str, *, limit: int = 10) -> list[Candidate]:
        import os

        token = os.environ.get("XAGENT_OSD__GITHUB_TOKEN", "")
        if not token:
            return []
        import httpx

        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "stars", "per_page": limit},
                headers=headers,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
        return [
            Candidate(
                name=i["full_name"],
                source="github",
                url=i["html_url"],
                description=i.get("description") or "",
                stars=i.get("stargazers_count", 0),
                license=(i.get("license") or {}).get("spdx_id", "") or "",
                last_updated=i.get("updated_at", "")[:10],
                language=i.get("language") or "",
                topics=i.get("topics", []),
            )
            for i in items
        ]


def _norm_popularity(stars: int) -> float:
    return min(1.0, math.log1p(max(0, stars)) / math.log1p(50000))


def _norm_maintenance(last_updated: str) -> float:
    if not last_updated:
        return 0.0
    try:
        d = datetime.fromisoformat(last_updated).replace(tzinfo=UTC)
    except ValueError:
        return 0.0
    days = (datetime.now(UTC) - d).days
    return max(0.0, 1.0 - days / 365.0)


def _norm_fit(query: str, c: Candidate) -> float:
    q = set(query.lower().split())
    blob = {c.name.lower()} | {c.description.lower()} | {t.lower() for t in c.topics}
    blob_text = " ".join(blob)
    if not q:
        return 0.0
    hits = sum(1 for w in q if w in blob_text)
    return hits / len(q)


def _license_check(license_str: str) -> tuple[float, bool]:
    low = (license_str or "").lower()
    if any(f in low for f in _FORBIDDEN):
        return 0.0, False
    if any(ok in low for ok in _COMMERCIAL_LICENSES):
        return 1.0, True
    return 0.5, True  # 未知许可：中性分，可商用标记保守为 True 待人工核


def score_candidate(query: str, c: Candidate) -> ScoredCandidate:
    pop = _norm_popularity(c.stars)
    maint = _norm_maintenance(c.last_updated)
    fit = _norm_fit(query, c)
    lic_score, lic_ok = _license_check(c.license)
    # 加权：契合度 > 维护 > 热度；许可证作为门槛倍率
    raw = 0.4 * fit + 0.3 * maint + 0.3 * pop
    score = raw * (0.5 + 0.5 * lic_score)
    return ScoredCandidate(
        candidate=c,
        score=round(score, 4),
        breakdown={
            "popularity": round(pop, 3),
            "maintenance": round(maint, 3),
            "fit": round(fit, 3),
            "license": round(lic_score, 3),
        },
        license_ok=lic_ok,
        notes="" if lic_ok else f"可疑许可: {c.license}",
    )


class DiscoveryEngine:
    def __init__(self, providers: list[Provider] | None = None) -> None:
        # 真实源优先；Mock 仅作最终兜底
        from xagent.domains.open_source_discovery.providers import (
            DuckDuckGoProvider,
            NpmProvider,
            PyPIProvider,
        )

        self._providers: list[Provider] = providers or [
            DuckDuckGoProvider(),
            GitHubProvider(),
            PyPIProvider(),
            NpmProvider(),
            MockProvider(),  # 离线兜底，所有真实源失败时保底
        ]

    async def discover(self, query: str, *, limit: int = 10) -> list[ScoredCandidate]:
        results, _meta = await self.discover_with_meta(query, limit=limit)
        return results

    async def discover_with_meta(
        self, query: str, *, limit: int = 10
    ) -> tuple[list[ScoredCandidate], dict]:
        """发现 + 元信息：provider 健康状况与降级标记。

        degraded=True 表示结果中含 MockProvider 假数据（真实源全部失败/无结果），
        调用方必须在响应中显式暴露，不得静默充当真实结果。
        """
        # Redis 缓存：同 query 短期复用结果
        cache_key = f"osd:{query}:{limit}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            results, meta = cached
            meta["cached"] = True
            return results, meta

        seen: dict[str, Candidate] = {}
        providers_ok: list[str] = []
        providers_failed: list[str] = []
        for p in self._providers:
            try:
                results = await p.search(query, limit=limit)
                providers_ok.append(p.name)
            except Exception as exc:  # 单个 provider 失败不阻断
                logger.warning("osd_provider_failed", provider=p.name, error=str(exc))
                providers_failed.append(p.name)
                continue
            for c in results:
                key = (c.source, c.name.lower())
                # 去重：同名同源取 stars 更高的
                if key not in seen or c.stars > seen[key].stars:
                    seen[key] = c
        scored = [score_candidate(query, c) for c in seen.values()]
        scored.sort(key=lambda s: s.score, reverse=True)
        result = scored[:limit]

        # 降级判定：结果来自 mock（假数据），或真实源全部失败
        real_providers = [p.name for p in self._providers if p.name != "mock"]
        real_all_failed = all(p in providers_failed for p in real_providers)
        has_mock_data = any(c.candidate.source == "mock" for c in result)
        degraded = has_mock_data or (real_all_failed and not result)
        if has_mock_data:
            degraded_reason = "所有真实源失败或无结果，结果含 MockProvider 示例数据（非真实开源项目）"
        elif degraded:
            degraded_reason = "所有真实源请求失败，无可用结果"
        else:
            degraded_reason = ""
        meta = {
            "providers_ok": providers_ok,
            "providers_failed": providers_failed,
            "degraded": degraded,
            "degraded_reason": degraded_reason,
            "cached": False,
        }
        await self._cache_set(cache_key, (result, meta), ttl=300)
        return result, meta

    async def _cache_get(self, key: str) -> tuple[list[ScoredCandidate], dict] | None:
        try:
            from xagent.infra.cache import get_cache

            raw = await get_cache().get(key)
            if raw:
                import json

                data = json.loads(raw)
                results = [
                    ScoredCandidate(
                        candidate=Candidate(**c),
                        score=s,
                        breakdown=b,
                        license_ok=lo,
                        notes=n,
                    )
                    for c, s, b, lo, n in data["results"]
                ]
                return results, data.get("meta", {})
        except Exception:  # noqa: S110  缓存读失败降级为重新发现
            pass
        return None

    async def _cache_set(
        self, key: str, value: tuple[list[ScoredCandidate], dict], *, ttl: int
    ) -> None:
        try:
            import json

            from xagent.infra.cache import get_cache

            results, meta = value
            payload = {
                "results": [
                    [
                        c.candidate.__dict__,
                        c.score,
                        c.breakdown,
                        c.license_ok,
                        c.notes,
                    ]
                    for c in results
                ],
                "meta": meta,
            }
            await get_cache().set(key, json.dumps(payload), ttl=ttl)
        except Exception:  # noqa: S110  缓存写失败不影响发现
            pass


@lru_cache
def get_discovery_engine() -> DiscoveryEngine:
    return DiscoveryEngine()


def reset_discovery_engine() -> None:
    get_discovery_engine.cache_clear()


async def discover_and_rank(query: str, *, limit: int = 10) -> list[ScoredCandidate]:
    return await get_discovery_engine().discover(query, limit=limit)


async def discover_and_rank_with_meta(
    query: str, *, limit: int = 10
) -> tuple[list[ScoredCandidate], dict]:
    """发现 + 评分 + 元信息（含 degraded 降级标记，供 API 层透传）。"""
    return await get_discovery_engine().discover_with_meta(query, limit=limit)
