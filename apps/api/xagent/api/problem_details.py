"""API 错误标准化：RFC 7807 Problem Details。

标准化错误响应格式：
{
  "type": "https://xagent.dev/errors/validation",
  "title": "Validation Error",
  "status": 422,
  "detail": "Field 'name' is required",
  "instance": "/api/v1/agents",
  "errors": [{"field": "name", "message": "required"}]
}

用法：
    from xagent.api.problem_details import ProblemDetail, validation_error, not_found

    raise not_found("Agent", agent_id)
    raise validation_error([{"field": "name", "message": "required"}])
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

BASE_URI = "https://xagent.dev/errors"


class ProblemDetail(HTTPException):
    """RFC 7807 Problem Details 异常。"""

    def __init__(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        type_uri: str | None = None,
        instance: str | None = None,
        extensions: dict[str, Any] | None = None,
    ):
        self.problem = {
            "type": type_uri or f"{BASE_URI}/{title.lower().replace(' ', '-')}",
            "title": title,
            "status": status,
        }
        if detail:
            self.problem["detail"] = detail
        if instance:
            self.problem["instance"] = instance
        if extensions:
            self.problem.update(extensions)

        super().__init__(status_code=status, detail=detail or title)


# ─── 快捷工厂函数 ───


def bad_request(detail: str = "Bad Request", **ext: Any) -> ProblemDetail:
    return ProblemDetail(400, "Bad Request", detail, extensions=ext)


def unauthorized(detail: str = "Authentication required") -> ProblemDetail:
    return ProblemDetail(401, "Unauthorized", detail)


def forbidden(detail: str = "Insufficient permissions") -> ProblemDetail:
    return ProblemDetail(403, "Forbidden", detail)


def not_found(resource: str = "Resource", resource_id: str | None = None) -> ProblemDetail:
    detail = f"{resource} not found"
    if resource_id:
        detail = f"{resource} '{resource_id}' not found"
    return ProblemDetail(404, "Not Found", detail)


def conflict(detail: str = "Resource conflict") -> ProblemDetail:
    return ProblemDetail(409, "Conflict", detail)


def too_many_requests(retry_after: int = 60) -> ProblemDetail:
    return ProblemDetail(
        429,
        "Too Many Requests",
        f"Rate limit exceeded. Retry after {retry_after}s",
        extensions={"retry_after": retry_after},
    )


def validation_error(
    errors: list[dict[str, str]],
    detail: str = "Request validation failed",
) -> ProblemDetail:
    return ProblemDetail(
        422,
        "Validation Error",
        detail,
        type_uri=f"{BASE_URI}/validation",
        extensions={"errors": errors},
    )


def internal_error(detail: str = "An unexpected error occurred") -> ProblemDetail:
    return ProblemDetail(500, "Internal Server Error", detail)


def service_unavailable(detail: str = "Service temporarily unavailable") -> ProblemDetail:
    return ProblemDetail(503, "Service Unavailable", detail)


# ─── 异常处理器 ───


async def problem_detail_handler(request: Request, exc: ProblemDetail) -> JSONResponse:
    """FastAPI 异常处理器。

    注册：app.add_exception_handler(ProblemDetail, problem_detail_handler)
    """
    problem = {**exc.problem, "instance": str(request.url.path)}
    return JSONResponse(
        status_code=exc.status_code,
        content=problem,
        media_type="application/problem+json",
    )
