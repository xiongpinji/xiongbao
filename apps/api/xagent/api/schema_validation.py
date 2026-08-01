"""Schema 校验中间件：请求体结构验证。

功能：
- 轻量 JSON Schema 子集校验
- 中间件自动校验（按路径注册）
- 详细错误定位（JSONPath）
- 嵌套对象/数组支持

用法：
    from xagent.api.schema_validation import SchemaValidator, SchemaMiddleware

    schema = {
        "type": "object",
        "required": ["name", "model"],
        "properties": {
            "name": {"type": "string", "maxLength": 200},
            "model": {"type": "string", "enum": ["gpt-4", "claude-3"]},
            "temperature": {"type": "number", "minimum": 0, "maximum": 2},
            "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
        },
    }
    validator = SchemaValidator(schema)
    errors = validator.validate(payload)
"""

from __future__ import annotations

import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.schema")


class SchemaValidator:
    """轻量 JSON Schema 校验器。"""

    def __init__(self, schema: dict[str, Any]):
        self.schema = schema

    def validate(self, data: Any, path: str = "$") -> list[dict[str, str]]:
        """校验数据，返回错误列表。"""
        errors: list[dict[str, str]] = []
        self._validate_node(data, self.schema, path, errors)
        return errors

    def _validate_node(
        self, data: Any, schema: dict, path: str, errors: list
    ) -> None:
        # 类型检查
        expected_type = schema.get("type")
        if expected_type and not self._check_type(data, expected_type):
            errors.append({"path": path, "message": f"期望类型 {expected_type}", "code": "type"})
            return

        # 枚举
        if "enum" in schema and data not in schema["enum"]:
            errors.append({"path": path, "message": f"必须是 {schema['enum']} 之一", "code": "enum"})

        # 字符串约束
        if isinstance(data, str):
            if "minLength" in schema and len(data) < schema["minLength"]:
                errors.append({"path": path, "message": f"长度不能少于 {schema['minLength']}", "code": "minLength"})
            if "maxLength" in schema and len(data) > schema["maxLength"]:
                errors.append({"path": path, "message": f"长度不能超过 {schema['maxLength']}", "code": "maxLength"})
            if "pattern" in schema:
                import re
                if not re.match(schema["pattern"], data):
                    errors.append({"path": path, "message": f"格式不匹配", "code": "pattern"})

        # 数值约束
        if isinstance(data, (int, float)):
            if "minimum" in schema and data < schema["minimum"]:
                errors.append({"path": path, "message": f"不能小于 {schema['minimum']}", "code": "minimum"})
            if "maximum" in schema and data > schema["maximum"]:
                errors.append({"path": path, "message": f"不能大于 {schema['maximum']}", "code": "maximum"})

        # 对象
        if isinstance(data, dict) and expected_type == "object":
            # 必填
            for field in schema.get("required", []):
                if field not in data:
                    errors.append({"path": f"{path}.{field}", "message": "必填字段缺失", "code": "required"})

            # 属性
            properties = schema.get("properties", {})
            for key, prop_schema in properties.items():
                if key in data:
                    self._validate_node(data[key], prop_schema, f"{path}.{key}", errors)

        # 数组
        if isinstance(data, list) and expected_type == "array":
            if "minItems" in schema and len(data) < schema["minItems"]:
                errors.append({"path": path, "message": f"至少 {schema['minItems']} 项", "code": "minItems"})
            if "maxItems" in schema and len(data) > schema["maxItems"]:
                errors.append({"path": path, "message": f"最多 {schema['maxItems']} 项", "code": "maxItems"})

            items_schema = schema.get("items")
            if items_schema:
                for i, item in enumerate(data):
                    self._validate_node(item, items_schema, f"{path}[{i}]", errors)

    @staticmethod
    def _check_type(data: Any, expected: str) -> bool:
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }
        expected_types = type_map.get(expected)
        if expected_types is None:
            return True
        return isinstance(data, expected_types)


class SchemaMiddleware(BaseHTTPMiddleware):
    """Schema 校验中间件。"""

    def __init__(self, app, schemas: dict[str, dict] | None = None):
        """
        Args:
            schemas: {路径前缀: schema} 映射
        """
        super().__init__(app)
        self.schemas = schemas or {}
        self._validators = {
            path: SchemaValidator(schema) for path, schema in self.schemas.items()
        }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 仅校验写方法
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        path = request.url.path
        validator = self._find_validator(path)
        if not validator:
            return await call_next(request)

        # 解析请求体
        try:
            body = await request.body()
            data = json.loads(body) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_json", "message": "请求体不是有效 JSON"},
            )

        errors = validator.validate(data)
        if errors:
            logger.debug("schema validation failed: %s (%d errors)", path, len(errors))
            return JSONResponse(
                status_code=422,
                content={
                    "error": "validation_error",
                    "message": "请求体校验失败",
                    "details": errors[:20],
                },
            )

        return await call_next(request)

    def _find_validator(self, path: str) -> SchemaValidator | None:
        for prefix, validator in self._validators.items():
            if path.startswith(prefix):
                return validator
        return None
