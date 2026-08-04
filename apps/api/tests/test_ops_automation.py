"""P1 自动化运营增强 — 补证测试。

覆盖三项 SOT §7 P1 待勾选能力的联动验证：

- ``xagent.infra.auto_recovery.AutoRecoveryEngine``
  LLM 连续超时→fallback、Worker 连续失败→重启、DB 池耗尽→回收、
  readiness 失败升级；所有动作落 RecoveryLogger 证据。
- ``scripts/post_deploy_summary.py``
  发布前后指标对比 / 健康判定（HEALTHY/DEGRADED/ROLLBACK_RECOMMENDED）/
  CLI 端到端产物。
- ``scripts/auto_archive_evidence.py``
  归档联动：recovery 日志收集 + tar.gz 归档包含 manifest 与证据文件。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tarfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = API_ROOT / "scripts"


def _load_script(name: str):
    path = SCRIPTS_DIR / f"{name}.py"
    assert path.exists(), f"missing script: {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


summary_mod = _load_script("post_deploy_summary")
archive_mod = _load_script("auto_archive_evidence")

from xagent.infra.auto_recovery import AutoRecoveryEngine  # noqa: E402
from xagent.infra.recovery_log import RecoveryAction, RecoverySeverity  # noqa: E402


class FakeRecoveryLogger:
    """捕获 RecoveryLogger.log 调用，替代文件落盘。"""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def log(self, action, severity, target, message, details=None, success=True):
        self.records.append(
            {
                "action": action,
                "severity": severity,
                "target": target,
                "message": message,
                "details": details or {},
                "success": success,
            }
        )


def _make_engine(**overrides) -> tuple[AutoRecoveryEngine, FakeRecoveryLogger]:
    """构造阈值可控的引擎（默认 2 次即触发，便于测试）。"""
    fake = FakeRecoveryLogger()
    engine = AutoRecoveryEngine(recovery_logger=fake)
    engine._settings = SimpleNamespace(
        enabled=True,
        max_consecutive_llm_timeouts=overrides.get("llm_threshold", 2),
        fallback_on_llm_failure=overrides.get("fallback_on_llm_failure", True),
        worker_restart_threshold=overrides.get("worker_threshold", 2),
        evidence_output_dir="./data/recovery-evidence",
    )
    return engine, fake


# ---------------------------------------------------------------------------
# AutoRecoveryEngine：LLM 超时 → fallback
# ---------------------------------------------------------------------------


async def test_llm_timeout_below_threshold_no_action() -> None:
    engine, fake = _make_engine(llm_threshold=3)
    await engine.report_llm_timeout("p", "m")
    await engine.report_llm_timeout("p", "m")
    assert engine.get_fallback_model() is None
    assert fake.records == []


async def test_llm_timeout_threshold_triggers_fallback_with_evidence() -> None:
    engine, fake = _make_engine(llm_threshold=2)
    await engine.report_llm_timeout("openai", "gpt-4o")
    await engine.report_llm_timeout("openai", "gpt-4o")

    fallback = engine.get_fallback_model()
    assert fallback is not None and fallback != "gpt-4o"
    assert engine.state.total_recovery_actions == 1

    assert len(fake.records) == 1
    rec = fake.records[0]
    assert rec["action"] == RecoveryAction.LLM_FALLBACK
    assert rec["severity"] == RecoverySeverity.WARNING
    assert rec["target"] == "llm"
    assert rec["details"]["failed_model"] == "gpt-4o"
    assert rec["details"]["fallback_model"] == fallback


async def test_llm_success_resets_timeout_counter() -> None:
    engine, fake = _make_engine(llm_threshold=2)
    await engine.report_llm_timeout("p", "m")
    await engine.report_llm_success("p")
    assert engine.state.llm_consecutive_timeouts == 0
    await engine.report_llm_timeout("p", "m")
    assert engine.get_fallback_model() is None


async def test_llm_fallback_without_fallback_models_logs_critical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.infra.auto_recovery as ar

    engine, fake = _make_engine(llm_threshold=1)
    real_get_settings = ar.get_settings

    class _NoFallback:
        class llm:
            fallback_models: list[str] = []

    monkeypatch.setattr(ar, "get_settings", lambda: _NoFallback())
    await engine.report_llm_timeout("p", "m")
    monkeypatch.setattr(ar, "get_settings", real_get_settings)

    assert engine.get_fallback_model() is None
    assert fake.records[0]["severity"] == RecoverySeverity.CRITICAL
    assert fake.records[0]["success"] is False


async def test_llm_fallback_manual_reset() -> None:
    engine, _ = _make_engine(llm_threshold=1)
    await engine.report_llm_timeout("p", "m")
    assert engine.get_fallback_model() is not None
    engine.reset_llm_fallback()
    assert engine.get_fallback_model() is None
    assert engine.state.llm_consecutive_timeouts == 0


async def test_engine_disabled_is_noop() -> None:
    engine, fake = _make_engine(llm_threshold=1)
    engine._settings.enabled = False
    await engine.report_llm_timeout("p", "m")
    await engine.report_worker_failure("t", "e")
    await engine.report_db_pool_exhausted(10, 10)
    await engine.report_readiness_failure([{"name": "db", "healthy": False}])
    assert fake.records == []
    assert engine.state.total_recovery_actions == 0


# ---------------------------------------------------------------------------
# AutoRecoveryEngine：Worker 失败 → 重启（含 60s 节流）
# ---------------------------------------------------------------------------


async def test_worker_failure_threshold_triggers_restart_evidence() -> None:
    engine, fake = _make_engine(worker_threshold=2)
    await engine.report_worker_failure("task_a", "boom")
    assert fake.records == []  # 未达阈值
    await engine.report_worker_failure("task_a", "boom")

    assert engine.state.total_recovery_actions == 1
    assert engine.state.worker_consecutive_failures == 0  # 重启后清零
    rec = fake.records[0]
    assert rec["action"] == RecoveryAction.WORKER_RESTART
    assert rec["target"] == "worker"
    assert "restart_detail" in rec["details"]


async def test_worker_restart_throttled_within_60s() -> None:
    engine, fake = _make_engine(worker_threshold=1)
    engine._state.worker_last_restart_at = time.time()  # 刚重启过
    await engine.report_worker_failure("task_a", "boom")
    assert fake.records == []  # 被节流
    assert engine.state.total_recovery_actions == 0


async def test_worker_success_resets_failures() -> None:
    engine, _ = _make_engine(worker_threshold=3)
    await engine.report_worker_failure("t", "e")
    await engine.report_worker_success()
    assert engine.state.worker_consecutive_failures == 0


# ---------------------------------------------------------------------------
# AutoRecoveryEngine：DB 池回收（含 30s 节流）
# ---------------------------------------------------------------------------


async def test_db_pool_exhausted_triggers_recycle_evidence() -> None:
    engine, fake = _make_engine()
    await engine.report_db_pool_exhausted(20, 20)
    assert engine.state.total_recovery_actions == 1
    rec = fake.records[0]
    assert rec["action"] == RecoveryAction.DB_POOL_RECYCLE
    assert rec["target"] == "db"
    assert rec["details"]["active_connections"] == 20


async def test_db_pool_recycle_throttled_within_30s() -> None:
    engine, fake = _make_engine()
    engine._state.db_last_recycle_at = time.time()
    await engine.report_db_pool_exhausted(20, 20)
    assert fake.records == []


# ---------------------------------------------------------------------------
# AutoRecoveryEngine：readiness 失败升级与恢复
# ---------------------------------------------------------------------------


async def test_readiness_failure_severity_escalates() -> None:
    engine, fake = _make_engine()
    components = [{"name": "db", "healthy": False}, {"name": "redis", "healthy": True}]
    await engine.report_readiness_failure(components)
    await engine.report_readiness_failure(components)
    assert fake.records[-1]["severity"] == RecoverySeverity.WARNING
    await engine.report_readiness_failure(components)
    rec = fake.records[-1]
    assert rec["severity"] == RecoverySeverity.CRITICAL
    assert rec["details"]["unhealthy_components"] == ["db"]


async def test_readiness_success_after_failure_logs_recovery() -> None:
    engine, fake = _make_engine()
    await engine.report_readiness_failure([{"name": "db", "healthy": False}])
    await engine.report_readiness_success()
    assert engine.state.readiness_failures == 0
    rec = fake.records[-1]
    assert rec["severity"] == RecoverySeverity.INFO
    assert rec["details"]["previous_failures"] == 1


async def test_get_status_snapshot_shape() -> None:
    engine, _ = _make_engine(llm_threshold=1)
    await engine.report_llm_timeout("p", "m")
    status = engine.get_status()
    assert status["enabled"] is True
    assert status["llm"]["fallback_active"] is True
    assert status["total_recovery_actions"] == 1
    assert set(status) >= {"enabled", "llm", "worker", "db", "readiness"}


# ---------------------------------------------------------------------------
# post_deploy_summary：指标对比与健康判定
# ---------------------------------------------------------------------------


def _comparison(before: dict, after: dict) -> dict:
    return summary_mod.compare_metrics(before, after)


def test_compare_metrics_normal_and_none_and_zero() -> None:
    cmp_ = _comparison(
        {"error_rate_5xx": 1.0, "p95_latency_seconds": 0.0, "pod_restarts": None},
        {"error_rate_5xx": 3.0, "p95_latency_seconds": 2.0, "pod_restarts": 4},
    )
    assert cmp_["error_rate_5xx"]["change"] == 2.0
    assert cmp_["error_rate_5xx"]["change_percent"] == 200.0
    assert cmp_["p95_latency_seconds"]["change_percent"] == 0  # before=0 防除零
    assert cmp_["pod_restarts"]["status"] == "unknown"  # None → unknown


def test_evaluate_health_verdicts() -> None:
    healthy = _comparison(
        {"error_rate_5xx": 1.0, "p95_latency_seconds": 1.0, "pod_restarts": 1},
        {"error_rate_5xx": 1.5, "p95_latency_seconds": 1.2, "pod_restarts": 2},
    )
    assert summary_mod.evaluate_health(healthy) == ("HEALTHY", [])

    degraded = _comparison(
        {"error_rate_5xx": 1.0},
        {"error_rate_5xx": 4.0},  # +3 > 阈值 2.0
    )
    verdict, issues = summary_mod.evaluate_health(degraded)
    assert verdict == "DEGRADED" and len(issues) == 1

    rollback = _comparison(
        {"error_rate_5xx": 1.0, "pod_restarts": 1},
        {"error_rate_5xx": 4.0, "pod_restarts": 5},  # 两项越线
    )
    verdict, issues = summary_mod.evaluate_health(rollback)
    assert verdict == "ROLLBACK_RECOMMENDED" and len(issues) == 2


def test_evaluate_health_threshold_boundary_not_triggered() -> None:
    # 恰好等于阈值不触发（判定为 >）
    cmp_ = _comparison(
        {"error_rate_5xx": 1.0},
        {"error_rate_5xx": 3.0},  # change = 2.0 == 阈值
    )
    assert summary_mod.evaluate_health(cmp_) == ("HEALTHY", [])


def test_render_markdown_contains_verdict_and_issues() -> None:
    summary = {
        "generated_at": "2026-08-04T00:00:00+00:00",
        "wait_seconds": 0,
        "namespace": "default",
        "verdict": "ROLLBACK_RECOMMENDED",
        "issues": ["5xx 错误率上升 3.00%"],
        "comparison": _comparison({"error_rate_5xx": 1.0}, {"error_rate_5xx": 4.0}),
        "before": {"error_rate_5xx": 1.0},
        "after": {"error_rate_5xx": 4.0},
    }
    md = summary_mod.render_markdown(summary)
    assert "## 判定: ROLLBACK_RECOMMENDED" in md
    assert "5xx 错误率上升" in md
    assert "| 指标 | 发布前 | 发布后 |" in md


def test_main_end_to_end_healthy_and_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metrics = {
        "error_rate_5xx": 1.0,
        "p95_latency_seconds": 1.0,
        "pod_restarts": 0,
        "worker_queue_depth": 5,
        "llm_timeout_rate": 1.0,
    }
    monkeypatch.setattr(summary_mod, "collect_metrics", lambda ns: dict(metrics))

    out = tmp_path / "summary"
    monkeypatch.setattr(
        sys, "argv", ["prog", "--skip-wait", "--format", "both", "--output", str(out)]
    )
    assert summary_mod.main() == 0
    payload = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert payload["verdict"] == "HEALTHY"
    assert "判定: HEALTHY" in out.with_suffix(".md").read_text(encoding="utf-8")

    # 发布后恶化：before 健康 / after 两项越线 → 退出码 1
    # main() 依次调用 collect_metrics 两次（before / after），用迭代器区分
    bad_after = dict(metrics, error_rate_5xx=9.0, pod_restarts=10)
    calls = iter([dict(metrics), dict(bad_after)])
    monkeypatch.setattr(summary_mod, "collect_metrics", lambda ns: next(calls))
    monkeypatch.setattr(sys, "argv", ["prog", "--skip-wait", "--format", "json"])
    assert summary_mod.main() == 1


# ---------------------------------------------------------------------------
# auto_archive_evidence：归档联动（recovery 日志 + manifest）
# ---------------------------------------------------------------------------


def test_collect_recovery_logs_filters_by_recency(tmp_path: Path) -> None:
    recent = tmp_path / "recovery-2026-08-04.jsonl"
    recent.write_text("{}\n", encoding="utf-8")
    old = tmp_path / "recovery-2020-01-01.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    # 过滤依据是 mtime 而非文件名日期：把 old 的 mtime 拨到 48 小时前
    old_ts = time.time() - 48 * 3600
    os.utime(old, (old_ts, old_ts))

    files = archive_mod.collect_recovery_logs(24, tmp_path)
    assert recent in files
    assert old not in files
    assert archive_mod.collect_recovery_logs(24, tmp_path / "nonexistent") == []


def test_create_archive_bundles_evidence(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "recovery-evidence"
    evidence_dir.mkdir()
    (evidence_dir / "recovery-2026-08-04.jsonl").write_text(
        '{"action": "llm_fallback"}\n', encoding="utf-8"
    )

    archive = archive_mod.create_archive(24, tmp_path / "out", evidence_dir)
    assert archive is not None and archive.exists()

    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
        assert any(n.endswith("manifest.json") for n in names)
        assert any("recovery-logs/recovery-2026-08-04.jsonl" in n for n in names)
        assert any(n.endswith("health-snapshot.json") for n in names)
        assert any(n.endswith("prometheus-metrics.json") for n in names)
        manifest = json.loads(
            tar.extractfile(next(n for n in names if n.endswith("manifest.json"))).read()
        )
    assert manifest["archive_version"] == "1.1"
    assert manifest["recovery_log_count"] == 1
    assert "recovery-logs/" in manifest["contents"]
