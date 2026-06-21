"""Hatchet 工作流引擎适配：持久化执行 + 重试 + 超时。"""

from __future__ import annotations

import os

from xagent.infra.logging import get_logger

logger = get_logger("xagent.workflow.hatchet")


class HatchetWorkflowBackend:
    """把 X-Agent 工作流桥接到 Hatchet 执行引擎。

    lite 模式回退到内存 WorkflowEngine；full/enterprise 走 Hatchet。
    """

    def __init__(self) -> None:
        self._client = None
        self._has_hatchet = self._check()
        if self._has_hatchet:
            logger.info("hatchet_available", detail="Hatchet 已安装，可用作工作流持久化后端")
        else:
            logger.info("hatchet_not_available", detail="回退到内存 WorkflowEngine")

    def _check(self) -> bool:
        try:
            import hatchet_sdk  # noqa: F401
            return True
        except ImportError:
            return False

    def get_client(self):
        if self._client is not None:
            return self._client
        if not self._has_hatchet:
            return None
        import hatchet_sdk

        self._client = hatchet_sdk.Hatchet(
            host=os.environ.get("XAGENT_HATCHET_HOST", "localhost"),
            port=int(os.environ.get("XAGENT_HATCHET_PORT", "7070")),
        )
        return self._client


# 单例
_backend = None


def get_hatchet_backend() -> HatchetWorkflowBackend:
    global _backend
    if _backend is None:
        _backend = HatchetWorkflowBackend()
    return _backend


def reset_hatchet_backend() -> None:
    global _backend
    _backend = None