"""API 字段过滤：Sparse Fieldsets（?fields=id,name）。

客户端通过 fields 参数指定返回字段，减少带宽：
- GET /api/v1/agents?fields=id,name,status
- 支持嵌套：fields=id,config.model
- 支持排除：fields=-secret,-internal

用法（服务端）：
    from xagent.api.field_filter import filter_fields
    data = {"id": "1", "name": "test", "secret": "xxx"}
    result = filter_fields(data, request.query_params.get("fields"))
"""

from __future__ import annotations

from typing import Any


def parse_fields_param(fields_str: str | None) -> tuple[set[str] | None, set[str]]:
    """解析 fields 参数。

    返回 (include_set, exclude_set)：
    - include_set 为 None 表示不过滤（返回全部）
    - exclude_set 为需要排除的字段
    """
    if not fields_str:
        return None, set()

    parts = [f.strip() for f in fields_str.split(",") if f.strip()]
    includes: set[str] = set()
    excludes: set[str] = set()

    for part in parts:
        if part.startswith("-"):
            excludes.add(part[1:])
        else:
            includes.add(part)

    return (includes if includes else None), excludes


def filter_fields(data: Any, fields_str: str | None) -> Any:
    """根据 fields 参数过滤响应数据。

    支持：
    - 顶层字段：fields=id,name
    - 嵌套字段：fields=id,config.model
    - 排除模式：fields=-secret
    """
    includes, excludes = parse_fields_param(fields_str)

    if includes is None and not excludes:
        return data

    return _apply_filter(data, includes, excludes, "")


def _apply_filter(data: Any, includes: set[str] | None, excludes: set[str], prefix: str) -> Any:
    """递归应用过滤。"""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key

            # 排除检查
            if key in excludes or full_key in excludes:
                continue

            # 包含检查（仅顶层）
            if includes is not None and not prefix:
                # 检查是否有该字段的嵌套规则
                has_nested = any(f.startswith(f"{key}.") for f in includes)
                if key not in includes and not has_nested:
                    continue

            # 递归处理嵌套
            if isinstance(value, dict):
                result[key] = _apply_filter(value, includes, excludes, full_key)
            elif isinstance(value, list):
                result[key] = [
                    _apply_filter(item, includes, excludes, full_key)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                result[key] = value

        return result
    elif isinstance(data, list):
        return [_apply_filter(item, includes, excludes, prefix) for item in data]

    return data


def get_fields_from_query(query_params: dict) -> str | None:
    """从查询参数提取 fields。"""
    return query_params.get("fields")
