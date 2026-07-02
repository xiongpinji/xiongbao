"""工具协议与数据类型。

工具调用上下文带 Principal（租户/角色），工具内部可据此做隔离与限权。
``ToolSpec`` 用 JSON Schema 描述参数，便于喂给 LLM 做 function-calling。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from xagent.enterprise.auth.principal import Principal


@dataclass
class ToolSpec:
    name: str
    description: str
    # JSON Schema（function-calling 用）
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})


@dataclass
class ToolResult:
    ok: bool
    output: Any = None
    error: str | None = None


@dataclass
class ToolContext:
    principal: Principal
    session: Any | None = None
    run_id: str | None = None


@runtime_checkable
class Tool(Protocol):
    spec: ToolSpec

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult: ...
