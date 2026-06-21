"""鉴权层：Principal（认证主体）+ JWT 签发/校验 + FastAPI 依赖。

设计：
- ``Principal`` 是贯穿全栈的身份对象，**必带 tenant_id**，是租户隔离的根。
- lite 模式（require_auth=False）下，无 token 时回退为匿名 Principal（默认租户），
  保证单机演示零配置可用；full/enterprise 模式强制校验 JWT。
- ``get_principal`` 是所有业务端点的统一依赖；缺失/无效 token 抛 401。
"""

from xagent.enterprise.auth.dependencies import get_principal, require_role
from xagent.enterprise.auth.jwt_auth import (
    InvalidTokenError,
    create_access_token,
    decode_token,
)
from xagent.enterprise.auth.principal import Principal

__all__ = [
    "Principal",
    "create_access_token",
    "decode_token",
    "InvalidTokenError",
    "get_principal",
    "require_role",
]
