"""真实多源 provider：PyPI / npm / DuckDuckGo（与 GitHub provider 同接口）。

各源独立失败不阻断（engine 已 try/except）。带简单 HTTP 超时。
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus

from xagent.domains.open_source_discovery.models import Candidate


class PyPIProvider:
    """PyPI 包搜索（JSON API）。"""

    name = "pypi"

    async def search(self, query: str, *, limit: int = 10) -> list[Candidate]:
        import httpx

        results: list[Candidate] = []
        # 策略1: 直接查询包名（精确匹配）
        keywords = [w for w in query.lower().split() if len(w) > 2][:3]
        names_to_try = [query.lower().replace(" ", "-"), *keywords]
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=12) as client:
            for name in names_to_try:
                if name in seen or len(results) >= limit:
                    break
                try:
                    resp = await client.get(f"https://pypi.org/pypi/{quote_plus(name)}/json")
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    info = data.get("info", {})
                    pkg_name = info.get("name", name)
                    if pkg_name.lower() in seen:
                        continue
                    seen.add(pkg_name.lower())
                    results.append(
                        Candidate(
                            name=pkg_name,
                            source="pypi",
                            url=f"https://pypi.org/project/{pkg_name}/",
                            description=info.get("summary", "") or "",
                            license=info.get("license", "") or "",
                            last_updated="",
                            language="python",
                            topics=[k for k in (info.get("keywords") or "").split(",") if k][:5],
                        )
                    )
                except Exception:
                    continue

            # 策略2: 用 simple index 做前缀匹配（最多扫 200 行）
            if len(results) < limit and keywords:
                try:
                    resp = await client.get(
                        "https://pypi.org/simple/",
                        headers={"Accept": "text/html"},
                    )
                    if resp.status_code == 200:
                        all_names = re.findall(r'>([^<]+)</a>', resp.text)
                        kw = keywords[0]
                        matches = [n for n in all_names if kw in n.lower()][:limit - len(results)]
                        for m in matches:
                            if m.lower() not in seen:
                                seen.add(m.lower())
                                results.append(
                                    Candidate(
                                        name=m,
                                        source="pypi",
                                        url=f"https://pypi.org/project/{m}/",
                                        description="",
                                        license="",
                                        last_updated="",
                                        language="python",
                                    )
                                )
                except Exception:
                    pass
        return results[:limit]


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


class DuckDuckGoProvider:
    """DuckDuckGo 通用搜索（无需 API key），提取 GitHub/开源相关结果。"""

    name = "duckduckgo"

    async def search(self, query: str, *, limit: int = 10) -> list[Candidate]:
        import httpx

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": f"{query} open source github"},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            resp.raise_for_status()

        # 解析搜索结果
        results: list[Candidate] = []
        # 提取链接和标题
        links = re.findall(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            resp.text,
        )
        for url, title_raw in links[:limit * 2]:
            title = re.sub(r'<[^>]+>', '', title_raw).strip()
            # 优先 GitHub 链接
            if "github.com" in url:
                parts = url.rstrip("/").split("github.com/")
                if len(parts) > 1:
                    repo_path = parts[1].split("/")
                    if len(repo_path) >= 2:
                        repo_name = f"{repo_path[0]}/{repo_path[1]}"
                        results.append(
                            Candidate(
                                name=repo_name,
                                source="github",
                                url=f"https://github.com/{repo_name}",
                                description=title,
                                stars=0,
                                license="",
                                last_updated="",
                                language="",
                                topics=[w for w in query.lower().split() if len(w) > 2],
                            )
                        )
            elif any(d in url for d in ("gitlab.com", "sourceforge.net", "codeberg.org")):
                results.append(
                    Candidate(
                        name=title[:60],
                        source="web",
                        url=url,
                        description=title,
                        stars=0,
                        license="",
                        last_updated="",
                        language="",
                    )
                )
            if len(results) >= limit:
                break
        return results[:limit]
