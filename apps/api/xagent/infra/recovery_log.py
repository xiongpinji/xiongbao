"""恢复动作结构化日志。

输出格式：JSON Lines（每行一条恢复事件），支持写入文件和 stdout。
用于审计追踪自动恢复引擎的所有动作。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RecoveryAction(str, Enum):
    """恢复动作类型。"""

    LLM_FALLBACK = "llm_fallback"
    WORKER_RESTART = "worker_restart"
    DB_POOL_RECYCLE = "db_pool_recycle"
    READINESS_RECOVERY = "readiness_recovery"
    MANUAL_OVERRIDE = "manual_override"


class RecoverySeverity(str, Enum):
    """恢复事件严重级别。"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RecoveryLogger:
    """恢复动作日志记录器。

    将恢复事件以 JSON Lines 格式写入指定目录，同时输出到 stdout。
    文件按日期滚动：recovery-YYYY-MM-DD.jsonl
    """

    def __init__(self, output_dir: str | Path = "./data/recovery-evidence") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_file(self) -> Path:
        """获取当天的日志文件路径。"""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._output_dir / f"recovery-{date_str}.jsonl"

    def log(
        self,
        action: RecoveryAction,
        severity: RecoverySeverity,
        component: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        success: bool = True,
    ) -> dict[str, Any]:
        """记录一条恢复事件。

        Args:
            action: 恢复动作类型
            severity: 严重级别
            component: 受影响组件 (llm/worker/db/api)
            message: 人类可读描述
            details: 附加上下文数据
            success: 恢复动作是否成功

        Returns:
            完整的事件字典（用于进一步处理）
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action.value,
            "severity": severity.value,
            "component": component,
            "message": message,
            "success": success,
            "details": details or {},
        }

        # 写入 JSONL 文件
        try:
            log_file = self._get_log_file()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.error("Failed to write recovery log: %s", exc)

        # 同时输出到 stdout（容器日志收集）
        log_line = json.dumps(event, ensure_ascii=False)
        if severity == RecoverySeverity.CRITICAL:
            logger.critical("[RECOVERY] %s", log_line)
        elif severity == RecoverySeverity.WARNING:
            logger.warning("[RECOVERY] %s", log_line)
        else:
            logger.info("[RECOVERY] %s", log_line)

        return event

    def get_recent_events(self, hours: int = 24) -> list[dict[str, Any]]:
        """获取最近 N 小时的恢复事件。"""
        events: list[dict[str, Any]] = []
        cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600

        for log_file in sorted(self._output_dir.glob("recovery-*.jsonl"), reverse=True):
            try:
                with open(log_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                            ts = datetime.fromisoformat(event["timestamp"]).timestamp()
                            if ts >= cutoff:
                                events.append(event)
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue
            except OSError:
                continue

            # 如果文件日期早于 cutoff，停止扫描
            try:
                file_date_str = log_file.stem.replace("recovery-", "")
                file_date = datetime.strptime(file_date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                if file_date.timestamp() < cutoff - 86400:
                    break
            except ValueError:
                continue

        return events


# 全局单例（延迟初始化）
_recovery_logger: RecoveryLogger | None = None


def get_recovery_logger(output_dir: str | Path | None = None) -> RecoveryLogger:
    """获取全局 RecoveryLogger 单例。"""
    global _recovery_logger
    if _recovery_logger is None:
        from xagent.infra.settings import get_settings

        cfg = get_settings().recovery
        _recovery_logger = RecoveryLogger(output_dir or cfg.evidence_output_dir)
    return _recovery_logger


def reset_recovery_logger() -> None:
    """重置单例（测试用）。"""
    global _recovery_logger
    _recovery_logger = None
