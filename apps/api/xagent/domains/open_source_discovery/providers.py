"""真实多源 provider：PyPI / npm（与 GitHub provider 同接口）。

各源独立失败不阻断（engine 已 try/except）。带简单 HTTP 超时。
"""

from __future__ import annotations

from xagent.domains.open_source_discovery.models import Candidate


class PyPIProvider:
    """PyPI 包搜索。"""

    name = "pypi"

    async def search(self, query: str, *, limit: int = 10) -> list[Candidate]:
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://pypi.org/search/",
                params={"q": query, "page": 1},
                headers={"Accept": "text/html"},
            )
            resp.raise_for_status()
        # PyPI 搜索页是 HTML，无官方 JSON 搜索 API；用简单正则提取包名
        import re

        names = re.findall(r'class="package-snippet__name"[^>]*>([^<]+)<', resp.text)
        return [
            Candidate(
                name=n.strip(),
                source="pypi",
                url=f"https://pypi.org/project/{n.strip()}/",
                description="",
                license="",
                last_updated="",
                language="python",
            )
            for n in names[:limit]
        ]


class NpmProvider:
    """npm 包搜索（官方 registry JSON API）。"""

    name = "npm"

    async def search(self, query: str, *, limit: int = 10) -> list[Candidate]:
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://registry.npmjs.org/-/v1/search",
                params={"text": query, "size": limit},
            )
            resp.raise_for_status()
            data = resp.json()
        results = []
        for obj in data.get("objects", []):
            pkg = obj.get("package", {})
            name = pkg.get("name", "")
            results.append(
                Candidate(
                    name=name,
                    source="npm",
                    url=pkg.get("links", {}).get("npm", f"https://www.npmjs.com/package/{name}"),
                    description=pkg.get("description", ""),
                    license=pkg.get("license", "") or "",
                    last_updated=pkg.get("date", "")[:10],
                    language="javascript",
                    topics=pkg.get("keywords", []) or [],
                )
            )
        return results
