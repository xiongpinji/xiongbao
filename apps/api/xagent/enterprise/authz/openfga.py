"""OpenFGA 细粒度授权适配器（Google Zanzibar 模型）。

把 X-Agent 的 RBAC 升级为关系型授权（ReBAC），天然适合多租户：
  tenant -> user -> role -> resource
OpenFGA 服务部署后可独立于内置 RBAC 运行。
"""

from __future__ import annotations

import os
from functools import lru_cache

from xagent.enterprise.auth.principal import Principal
from xagent.infra.logging import get_logger

logger = get_logger("xagent.openfga")


class OpenFGAEnforcer:
    """OpenFGA 授权引擎代理。未部署 OpenFGA 时返回 None（回退内置 RBAC）。"""

    def __init__(self) -> None:
        self._client = None
        self._store_id = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def check(self, principal: Principal, resource: str, action: str) -> bool:
        client = self._client
        if client is None:
            return False
        try:
            resp = client.check(
                user=f"user:{principal.user_id}",
                relation=action,
                object=f"resource:{resource}",
            )
            return resp.allowed
        except Exception as exc:
            logger.warning("openfga_check_failed", error=str(exc))
            return False


@lru_cache
def get_openfga_enforcer() -> OpenFGAEnforcer:
    enforcer = OpenFGAEnforcer()
    url = os.environ.get("XAGENT_OPENFGA_URL", "")
    if not url:
        logger.info("openfga_disabled", detail="XAGENT_OPENFGA_URL 未设置，使用内置 RBAC")
        return enforcer
    try:
        from openfga_sdk import OpenFgaClient
        from openfga_sdk.credentials import Credentials
        enforcer._client = OpenFgaClient(base_url=url, credentials=Credentials())
        logger.info("openfga_ready", url=url)
    except Exception as exc:
        logger.warning("openfga_init_failed", error=str(exc))
    return enforcer


def reset_openfga() -> None:
    get_openfga_enforcer.cache_clear()
