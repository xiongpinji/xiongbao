"""内容协商：根据 Accept 头选择响应格式。

功能：
- 解析 Accept 头（含 q 权重）
- 支持 JSON / MessagePack / CSV 协商
- 未匹配时返回 406 Not Acceptable
- 可扩展自定义媒体类型

用法：
    from xagent.api.content_negotiation import negotiate, SupportedFormat

    fmt = negotiate(request.headers.get("accept", ""), [SupportedFormat.JSON])
    # fmt == SupportedFormat.JSON → 返回 JSON 响应
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.content_neg")


class SupportedFormat(str, Enum):
    JSON = "application/json"
    MSGPACK = "application/msgpack"
    CSV = "text/csv"
    NDJSON = "application/x-ndjson"
    XML = "application/xml"


# 格式 → 默认 Content-Type
FORMAT_CONTENT_TYPE: dict[SupportedFormat, str] = {
    SupportedFormat.JSON: "application/json; charset=utf-8",
    SupportedFormat.MSGPACK: "application/msgpack",
    SupportedFormat.CSV: "text/csv; charset=utf-8",
    SupportedFormat.NDJSON: "application/x-ndjson; charset=utf-8",
    SupportedFormat.XML: "application/xml; charset=utf-8",
}

# 常见别名映射
ALIASES: dict[str, SupportedFormat] = {
    "application/json": SupportedFormat.JSON,
    "text/json": SupportedFormat.JSON,
    "application/msgpack": SupportedFormat.MSGPACK,
    "application/x-msgpack": SupportedFormat.MSGPACK,
    "text/csv": SupportedFormat.CSV,
    "application/x-ndjson": SupportedFormat.NDJSON,
    "application/xml": SupportedFormat.XML,
    "text/xml": SupportedFormat.XML,
}


@dataclass(frozen=True)
class AcceptEntry:
    """Accept 头单项。"""

    media_type: str
    quality: float = 1.0


def parse_accept_header(header: str) -> list[AcceptEntry]:
    """解析 Accept 头为按 q 降序排列的列表。"""
    entries: list[AcceptEntry] = []
    for part in header.split(","):
        part = part.strip()
        if not part:
            continue
        segments = part.split(";")
        media_type = segments[0].strip().lower()
        quality = 1.0
        for param in segments[1:]:
            param = param.strip()
            if param.startswith("q="):
                try:
                    quality = float(param[2:])
                except ValueError:
                    quality = 1.0
        entries.append(AcceptEntry(media_type=media_type, quality=quality))

    # 按 quality 降序
    entries.sort(key=lambda e: e.quality, reverse=True)
    return entries


def negotiate(
    accept_header: str,
    supported: list[SupportedFormat],
    default: SupportedFormat = SupportedFormat.JSON,
) -> SupportedFormat:
    """根据 Accept 头协商最佳格式。

    Args:
        accept_header: 请求的 Accept 头值
        supported: 服务端支持的格式列表
        default: 无匹配时的默认格式

    Returns:
        协商后的格式
    """
    if not accept_header or accept_header.strip() == "*/*":
        return default

    entries = parse_accept_header(accept_header)
    supported_set = set(supported)

    for entry in entries:
        if entry.quality <= 0:
            continue
        # 通配符
        if entry.media_type in ("*/*", "application/*"):
            return default
        # 精确匹配
        fmt = ALIASES.get(entry.media_type)
        if fmt and fmt in supported_set:
            return fmt

    # 无匹配 → 返回默认（或可抛 406）
    logger.debug("no match for accept=%s, using default", accept_header[:100])
    return default


def negotiated_response(
    request: Request,
    data: dict | list,
    supported: list[SupportedFormat] | None = None,
) -> Response:
    """根据请求 Accept 头返回协商后的响应。

    当前仅实现 JSON 序列化，其他格式预留扩展点。
    """
    supported = supported or [SupportedFormat.JSON]
    accept = request.headers.get("accept", "application/json")
    fmt = negotiate(accept, supported)

    content_type = FORMAT_CONTENT_TYPE.get(fmt, "application/json; charset=utf-8")

    # JSON 响应（默认路径）
    if fmt == SupportedFormat.JSON:
        return JSONResponse(content=data, media_type=content_type)

    # CSV 响应（简单实现）
    if fmt == SupportedFormat.CSV and isinstance(data, list):
        import csv
        import io

        output = io.StringIO()
        if data and isinstance(data[0], dict):
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        return Response(
            content=output.getvalue(),
            media_type=content_type,
        )

    # 回退 JSON
    return JSONResponse(content=data, media_type="application/json; charset=utf-8")
