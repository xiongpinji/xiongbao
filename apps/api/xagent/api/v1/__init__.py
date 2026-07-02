"""``/api/v1`` 路由聚合。所有业务端点强制鉴权 + RBAC + 租户隔离。"""

from fastapi import APIRouter

from xagent.api.v1 import (
    agents,
    audit,
    auth,
    billing,
    canvas,
    creative_studio,
    editor,
    memory,
    open_source,
    runs,
    stream,
    system,
    tasks,
    workflows,
)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(agents.router)
api_v1.include_router(stream.router)
api_v1.include_router(tasks.router)
api_v1.include_router(memory.router)
api_v1.include_router(workflows.router)
api_v1.include_router(runs.router)
api_v1.include_router(canvas.router)
api_v1.include_router(creative_studio.router)
api_v1.include_router(editor.router)
api_v1.include_router(open_source.router)
api_v1.include_router(billing.router)
api_v1.include_router(audit.router)
api_v1.include_router(system.router)

__all__ = ["api_v1"]
