"""响应转换管道：统一响应格式包装。

功能：
- 统一响应信封 {code, message, data, meta}
- 字段过滤（?fields=name,email）
- 字段重命名映射
- 分页包装

用法：
    from xagent.api.response_transform import transform_response, ResponseEnvelope

    @router.get("/api/v1/agents")
    async def list_agents(request: Request):
        data = await get_agents()
        return transform_response(request, data, message="success")
"""

from __future__ import annotations

import time
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from xagent.infra.logging import get_logger

logger = get_logger("xagent.transform")


def transform_response(
    request: Request,
    data: Any,
    code: int = 0,
    message: str = "success",
    meta: dict[str, Any] | None = None,
    status_code: int = 200,
) -> JSONResponse:
    """统一响应信封包装。"""
    # 字段过滤
    fields_param = request.query_params.get("fields", "")
    if fields_param and isinstance(data, list):
        fields = [f.strip() for f in fields_param.split(",") if f.strip()]
        if fields:
            data = [_filter_fields(item, fields) for item in data]
    elif fields_param and isinstance(data, dict):
        fields = [f.strip() for f in fields_param.split(",") if f.strip()]
        if fields:
            data = _filter_fields(data, fields)

    envelope = {
        "code": code,
        "message": message,
        "data": data,
        "meta": meta or {},
        "timestamp": int(time.time() * 1000),
    }

    return JSONResponse(content=envelope, status_code=status_code)


def _filter_fields(item: Any, fields: list[str]) -> Any:
    """过滤字典字段。"""
    if not isinstance(item, dict):
        return item
    return {k: v for k, v in item.items() if k in fields}


def paginated_response(
    request: Request,
    items: list[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
    message: str = "success",
) -> JSONResponse:
    """分页响应包装。"""
    fields_param = request.query_params.get("fields", "")
    if fields_param:
        fields = [f.strip() for f in fields_param.split(",") if f.strip()]
        if fields:
            items = [_filter_fields(item, fields) for item in items]

    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

    envelope = {
        "code": 0,
        "message": message,
        "data": items,
        "meta": {
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            }
        },
        "timestamp": int(time.time() * 1000),
    }

    return JSONResponse(content=envelope)


def error_response(
    message: str,
    code: int = -1,
    status_code: int = 400,
    details: Any = None,
) -> JSONResponse:
    """错误响应包装。"""
    envelope = {
        "code": code,
        "message": message,
        "data": None,
        "meta": {"details": details} if details else {},
        "timestamp": int(time.time() * 1000),
    }
    return JSONResponse(content=envelope, status_code=status_code)
