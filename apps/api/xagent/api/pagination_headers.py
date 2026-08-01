"""分页元数据：标准化响应头 + Link 头。

遵循 RFC 8288 (Web Linking) 和 GitHub API 分页规范：
- Link: <url?page=2>; rel="next", <url?page=5>; rel="last"
- X-Total-Count / X-Page / X-Per-Page / X-Total-Pages

用法：
    from xagent.api.pagination_headers import add_pagination_headers

    response = JSONResponse(content=items)
    add_pagination_headers(response, page=2, per_page=20, total=95, base_url=str(request.url))
"""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from starlette.responses import Response


def build_page_url(base_url: str, page: int) -> str:
    """构建指定页码的 URL。"""
    parsed = urlparse(base_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params["page"] = [str(page)]

    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def add_pagination_headers(
    response: Response,
    *,
    page: int,
    per_page: int,
    total: int,
    base_url: str,
) -> Response:
    """为响应添加标准分页头。

    Headers:
    - X-Total-Count: 总条数
    - X-Page: 当前页
    - X-Per-Page: 每页条数
    - X-Total-Pages: 总页数
    - Link: RFC 8288 链接头
    """
    total_pages = max(1, math.ceil(total / per_page))

    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(page)
    response.headers["X-Per-Page"] = str(per_page)
    response.headers["X-Total-Pages"] = str(total_pages)

    # Link 头
    links: list[str] = []

    if page > 1:
        links.append(f'<{build_page_url(base_url, 1)}>; rel="first"')
        links.append(f'<{build_page_url(base_url, page - 1)}>; rel="prev"')

    if page < total_pages:
        links.append(f'<{build_page_url(base_url, page + 1)}>; rel="next"')
        links.append(f'<{build_page_url(base_url, total_pages)}>; rel="last"')

    if links:
        response.headers["Link"] = ", ".join(links)

    # 暴露头（CORS 场景）
    response.headers["Access-Control-Expose-Headers"] = (
        "X-Total-Count, X-Page, X-Per-Page, X-Total-Pages, Link"
    )

    return response


def parse_pagination_params(
    page: int | None = None,
    per_page: int | None = None,
    default_per_page: int = 20,
    max_per_page: int = 100,
) -> tuple[int, int, int]:
    """解析并验证分页参数。

    返回 (page, per_page, offset)。
    """
    effective_page = max(1, page or 1)
    effective_per_page = min(max(1, per_page or default_per_page), max_per_page)
    offset = (effective_page - 1) * effective_per_page

    return effective_page, effective_per_page, offset
