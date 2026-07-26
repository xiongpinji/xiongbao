"""自动恢复引擎。

监听系统异常并执行自动恢复动作：
- LLM 连续超时 -> 自动切换 fallback model
- Worker 任务失败率过高 -> 通过 Celery control 重启 worker
- DB 连接池耗尽 -> 自动回收连接 + 告警
- Readiness 失败 -> 记录证据并触发恢复流程

所有恢复动作通过 RecoveryLogger 记录到证据日志。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from xagent.infra.recovery_log import (
    RecoveryAction,
    RecoveryLogger,
    RecoverySeverity,
    get_recovery_logger,
)
from xagent.infra.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RecoveryState:
    """恢复引擎内部状态。"""

    # LLM 连续超时计数
    llm_consecutive_timeouts: int = 0
    llm_fallback_active: bool = False
    llm_fallback_model: str = ""
    llm_last_timeout_at: float = 0.0

    # Worker 失败计数
    worker_consecutive_failures: int = 0
    worker_last_restart_at: float = 0.0

    # DB 连接池状态
    db_pool_exhausted_count: int = 0
    db_last_recycle_at: float = 0.0

    # Readiness 状态
    readiness_failures: int = 0
    readiness_last_failure_at: float = 0.0

    # 统计
    total_recovery_actions: int = 0
    last_action_at: float = 0.0


class AutoRecoveryEngine:
    """自动恢复引擎。

    提供以下能力：
    1. report_llm_timeout() - 报告 LLM 超时，达到阈值自动切换 fallback
    2. report_llm_success() - 报告 LLM 成功，重置超时计数
    3. report_worker_failure() - 报告 Worker 失败，达到阈值触发重启
    4. report_db_pool_exhausted() - 报告连接池耗尽，触发回收
    5. report_readiness_failure() - 报告 readiness 失败
    6. get_fallback_model() - 获取当前应使用的 fallback model（如果有）
    """

    def __init__(self, recovery_logger: RecoveryLogger | None = None) -> None:
        self._settings = get_settings().recovery
        self._logger = recovery_logger or get_recovery_logger()
        self._state = RecoveryState()
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    @property
    def state(self) -> RecoveryState:
        return self._state

    # ─── LLM 超时与 Fallback ────────────────────────────────────────────

    async def report_llm_timeout(self, provider: str, model: str) -> None:
        """报告一次 LLM 超时。达到阈值时自动切换 fallback model。"""
        if not self.enabled:
            return

        async with self._lock:
            self._state.llm_consecutive_timeouts += 1
            self._state.llm_last_timeout_at = time.time()

            threshold = self._settings.max_consecutive_llm_timeouts
            count = self._state.llm_consecutive_timeouts

            logger.warning(
                "LLM timeout reported: provider=%s model=%s count=%d/%d",
                provider, model, count, threshold,
            )

            if count >= threshold and self._settings.fallback_on_llm_failure:
                await self._activate_llm_fallback(provider, model)

    async def report_llm_success(self, provider: str) -> None:
        """报告 LLM 调用成功，重置超时计数。"""
        if not self.enabled:
            return

        async with self._lock:
            if self._state.llm_consecutive_timeouts > 0:
                logger.info(
                    "LLM success: provider=%s, resetting timeout count (was %d)",
                    provider, self._state.llm_consecutive_timeouts,
                )
            self._state.llm_consecutive_timeouts = 0

            # 如果 fallback 已激活且连续成功，可以考虑恢复（暂不自动恢复，需人工确认）

    async def _activate_llm_fallback(self, provider: str, failed_model: str) -> None:
        """激活 LLM fallback model。"""
        settings = get_settings()
        fallback_models = settings.llm.fallback_models

        if not fallback_models:
            self._logger.log(
                RecoveryAction.LLM_FALLBACK,
                RecoverySeverity.CRITICAL,
                "llm",
                f"LLM 连续超时 {self._state.llm_consecutive_timeouts} 次，但无可用 fallback model",
                details={"provider": provider, "failed_model": failed_model},
                success=False,
            )
            return

        # 选择第一个不同于当前失败模型的 fallback
        fallback_model = fallback_models[0]
        for m in fallback_models:
            if m != failed_model:
                fallback_model = m
                break

        self._state.llm_fallback_active = True
        self._state.llm_fallback_model = fallback_model
        self._state.total_recovery_actions += 1
        self._state.last_action_at = time.time()

        self._logger.log(
            RecoveryAction.LLM_FALLBACK,
            RecoverySeverity.WARNING,
            "llm",
            f"LLM 连续超时 {self._state.llm_consecutive_timeouts} 次，自动切换到 fallback model: {fallback_model}",
            details={
                "provider": provider,
                "failed_model": failed_model,
                "fallback_model": fallback_model,
                "consecutive_timeouts": self._state.llm_consecutive_timeouts,
            },
        )

    def get_fallback_model(self) -> str | None:
        """获取当前激活的 fallback model（如果有的话）。

        Returns:
            fallback model 名称，或 None（未激活 fallback）
        """
        if self._state.llm_fallback_active:
            return self._state.llm_fallback_model
        return None

    def reset_llm_fallback(self) -> None:
        """手动重置 LLM fallback 状态（恢复使用主模型）。"""
        self._state.llm_fallback_active = False
        self._state.llm_fallback_model = ""
        self._state.llm_consecutive_timeouts = 0
        logger.info("LLM fallback manually reset")

    # ─── Worker 失败与重启 ──────────────────────────────────────────────

    async def report_worker_failure(self, task_name: str, error: str) -> None:
        """报告 Worker 任务失败。达到阈值时触发 worker 重启。"""
        if not self.enabled:
            return

        async with self._lock:
            self._state.worker_consecutive_failures += 1
            threshold = self._settings.worker_restart_threshold
            count = self._state.worker_consecutive_failures

            logger.warning(
                "Worker failure: task=%s count=%d/%d error=%s",
                task_name, count, threshold, error[:200],
            )

            if count >= threshold:
                await self._restart_worker(task_name, error)

    async def report_worker_success(self) -> None:
        """报告 Worker 任务成功，重置失败计数。"""
        if not self.enabled:
            return

        async with self._lock:
            self._state.worker_consecutive_failures = 0

    async def _restart_worker(self, failed_task: str, error: str) -> None:
        """通过 Celery control 重启 unhealthy worker。"""
        # 防止频繁重启（至少间隔 60 秒）
        now = time.time()
        if now - self._state.worker_last_restart_at < 60:
            logger.warning("Worker restart throttled (last restart < 60s ago)")
            return

        self._state.worker_last_restart_at = now
        self._state.worker_consecutive_failures = 0
        self._state.total_recovery_actions += 1
        self._state.last_action_at = now

        restart_success = False
        restart_detail = ""

        try:
            # 尝试通过 Celery control 发送 pool_restart 命令
            from celery import current_app

            celery_app = current_app._get_current_object()
            # 广播 pool_restart 到所有 worker
            responses = celery_app.control.broadcast(
                "pool_restart",
                arguments={"reloader": None},
                reply=True,
                timeout=10,
            )
            restart_success = True
            restart_detail = f"Broadcast pool_restart, responses: {len(responses or [])}"
            logger.info("Worker restart initiated via Celery control: %s", restart_detail)
        except ImportError:
            restart_detail = "Celery not available, skipping worker restart"
            logger.warning(restart_detail)
        except Exception as exc:
            restart_detail = f"Worker restart failed: {exc}"
            logger.error(restart_detail)

        self._logger.log(
            RecoveryAction.WORKER_RESTART,
            RecoverySeverity.CRITICAL if not restart_success else RecoverySeverity.WARNING,
            "worker",
            f"Worker 连续失败 {self._settings.worker_restart_threshold} 次，触发自动重启",
            details={
                "failed_task": failed_task,
                "error": error[:500],
                "restart_detail": restart_detail,
            },
            success=restart_success,
        )

    # ─── DB 连接池回收 ──────────────────────────────────────────────────

    async def report_db_pool_exhausted(self, active_connections: int, pool_size: int) -> None:
        """报告 DB 连接池耗尽。触发连接回收。"""
        if not self.enabled:
            return

        async with self._lock:
            self._state.db_pool_exhausted_count += 1
            now = time.time()

            # 防止频繁回收（至少间隔 30 秒）
            if now - self._state.db_last_recycle_at < 30:
                logger.warning("DB pool recycle throttled")
                return

            self._state.db_last_recycle_at = now
            self._state.total_recovery_actions += 1
            self._state.last_action_at = now

        recycle_success = False
        recycle_detail = ""

        try:
            from xagent.infra import db

            # 尝试 dispose 连接池（SQLAlchemy async engine）
            engine = db.get_engine()
            if hasattr(engine, "dispose"):
                await engine.dispose()
                recycle_success = True
                recycle_detail = "Connection pool disposed and will be recreated on next use"
            else:
                recycle_detail = "Engine does not support dispose"
        except Exception as exc:
            recycle_detail = f"Pool recycle failed: {exc}"
            logger.error(recycle_detail)

        self._logger.log(
            RecoveryAction.DB_POOL_RECYCLE,
            RecoverySeverity.CRITICAL,
            "db",
            f"DB 连接池耗尽 (active={active_connections}, pool_size={pool_size})，触发自动回收",
            details={
                "active_connections": active_connections,
                "pool_size": pool_size,
                "recycle_detail": recycle_detail,
                "exhausted_count": self._state.db_pool_exhausted_count,
            },
            success=recycle_success,
        )

    # ─── Readiness 失败 ─────────────────────────────────────────────────

    async def report_readiness_failure(self, components: list[dict[str, Any]]) -> None:
        """报告 readiness 检查失败。"""
        if not self.enabled:
            return

        async with self._lock:
            self._state.readiness_failures += 1
            self._state.readiness_last_failure_at = time.time()

            unhealthy = [c for c in components if not c.get("healthy", True)]
            unhealthy_names = [c.get("name", "unknown") for c in unhealthy]

            # 连续失败 3 次以上记录为 critical
            severity = (
                RecoverySeverity.CRITICAL
                if self._state.readiness_failures >= 3
                else RecoverySeverity.WARNING
            )

            self._logger.log(
                RecoveryAction.READINESS_RECOVERY,
                severity,
                "api",
                f"Readiness 检查失败 (连续第 {self._state.readiness_failures} 次): {', '.join(unhealthy_names)}",
                details={
                    "unhealthy_components": unhealthy_names,
                    "consecutive_failures": self._state.readiness_failures,
                },
                success=False,
            )

    async def report_readiness_success(self) -> None:
        """报告 readiness 恢复正常。"""
        if not self.enabled:
            return

        async with self._lock:
            if self._state.readiness_failures > 0:
                self._logger.log(
                    RecoveryAction.READINESS_RECOVERY,
                    RecoverySeverity.INFO,
                    "api",
                    f"Readiness 恢复正常 (此前连续失败 {self._state.readiness_failures} 次)",
                    details={"previous_failures": self._state.readiness_failures},
                )
            self._state.readiness_failures = 0

    # ─── 状态查询 ───────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """获取恢复引擎当前状态快照。"""
        return {
            "enabled": self.enabled,
            "llm": {
                "consecutive_timeouts": self._state.llm_consecutive_timeouts,
                "fallback_active": self._state.llm_fallback_active,
                "fallback_model": self._state.llm_fallback_model,
            },
            "worker": {
                "consecutive_failures": self._state.worker_consecutive_failures,
            },
            "db": {
                "pool_exhausted_count": self._state.db_pool_exhausted_count,
            },
            "readiness": {
                "consecutive_failures": self._state.readiness_failures,
            },
            "total_recovery_actions": self._state.total_recovery_actions,
        }


# ─── 全局单例 ───────────────────────────────────────────────────────────

_engine: AutoRecoveryEngine | None = None


def get_recovery_engine() -> AutoRecoveryEngine:
    """获取全局 AutoRecoveryEngine 单例。"""
    global _engine
    if _engine is None:
        _engine = AutoRecoveryEngine()
    return _engine


def reset_recovery_engine() -> None:
    """重置单例（测试用）。"""
    global _engine
    _engine = None
